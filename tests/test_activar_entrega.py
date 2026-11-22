"""Ensayo de actualización y reversión con bases reales y servicios simulados."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import activar_entrega as activador
from incidencias import Incidencias
from copias_seguridad import crear_copia
from verificar_copia import verificar_copia


class Activacion(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.proyecto = self.raiz / 'proyecto'
        self.entrega = self.raiz / 'entrega'
        self.copias = self.raiz / 'copias'
        self.claves = self.raiz / 'claves'
        self.proyecto.mkdir(); self.claves.mkdir()
        for nombre in ('router-user', 'router-password', 'panel-password'):
            (self.claves / nombre).write_text('credencial-ficticia')
        (self.proyecto / 'dispositivos.local.json').write_text('{"dispositivos": []}')
        self.db = Incidencias(self.proyecto / activador.NOMBRE_BASE)
        ticket = self.db.crear({'requestId': 'a' * 32, 'title': 'Incidencia que debe conservarse',
                               'description': 'Datos ficticios anteriores a la actualización.',
                               'category': 'Equipos', 'priority': 'medium'})
        self.id_ticket = ticket['id']
        self.db.actualizar(ticket['id'], {'version': 1, 'note': 'Nota anterior que debe conservarse.'})
        # Emular el esquema que está desplegado, no inicializar otra base vacía.
        with closing(sqlite3.connect(self.db.ruta)) as conn, conn:
            conn.execute('DROP INDEX idx_incidencia_origen')
            conn.execute('ALTER TABLE incidencias DROP COLUMN source_key')
            conn.execute('PRAGMA user_version=1')
        for nombre in activador.ARCHIVOS:
            nuevo = self.entrega / 'archivos' / nombre
            nuevo.parent.mkdir(parents=True, exist_ok=True)
            if nombre in ('scripts/preparar_laguntza.py', 'scripts/verificar_copia.py'):
                shutil.copyfile(SCRIPTS / Path(nombre).name, nuevo)
            else:
                nuevo.write_text('# version nueva' if nombre.endswith('.py') else 'version nueva')
            if nombre != 'scripts/intercambio_zaintza.py':
                anterior = self.proyecto / nombre
                anterior.parent.mkdir(parents=True, exist_ok=True)
                anterior.write_text('# version anterior' if nombre.endswith('.py') else 'version anterior')
        (self.proyecto / 'web/laguntza').mkdir(parents=True)
        (self.proyecto / 'web/laguntza/index.html').write_text('interfaz anterior')
        (self.entrega / 'interfaz/assets').mkdir(parents=True)
        (self.entrega / 'interfaz/index.html').write_text('<title>Laguntza IT</title><script src="./assets/app.js"></script>')
        (self.entrega / 'interfaz/assets/app.js').write_text('const version = 2;')
        self.manifiesto()
        self.servicios = {activador.SERVICIO: True, activador.TEMPORIZADOR: True}
        self.llamadas = []

    def manifiesto(self):
        sumas = {p.relative_to(self.entrega).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for carpeta in ('archivos', 'interfaz') for p in (self.entrega / carpeta).rglob('*') if p.is_file()}
        (self.entrega / 'manifest.json').write_text(json.dumps({'formato': 1, 'entrega': 'prueba', 'sha256': sumas}))

    def ejecutar(self, *comando):
        self.llamadas.append(comando)
        if comando == ('sudo', 'systemctl', 'start', activador.COPIA_SERVICIO):
            crear_copia(self.proyecto, self.claves, self.copias)
        elif len(comando) == 4 and comando[:2] == ('sudo', 'systemctl'):
            self.servicios[comando[3]] = comando[2] == 'start'
            if comando[2:] == ('start', activador.SERVICIO) and 'version nueva' in (self.proyecto / 'scripts/incidencias.py').read_text():
                Incidencias(self.proyecto / activador.NOMBRE_BASE)

    def activar(self, salud=None):
        with patch.object(activador, 'ejecutar', side_effect=self.ejecutar), \
             patch.object(activador, 'activo', side_effect=lambda unidad: self.servicios.get(unidad, False)), \
             patch.object(activador, 'comprobar_servicio', side_effect=salud):
            return activador.activar(self.entrega, self.proyecto, self.copias)

    def estado_base(self, ruta=None):
        with closing(sqlite3.connect(ruta or self.proyecto / activador.NOMBRE_BASE)) as conn:
            return (conn.execute('PRAGMA user_version').fetchone()[0],
                    conn.execute('SELECT COUNT(*) FROM incidencias').fetchone()[0],
                    conn.execute('SELECT detalle FROM actividad_incidencias ORDER BY id').fetchall())

    def test_actualiza_conservando_datos_y_copia_final(self):
        anterior = self.estado_base()
        resultado = self.activar()
        nueva = self.estado_base()
        self.assertEqual(nueva[0], 2)
        self.assertEqual(nueva[1:], anterior[1:])
        self.assertEqual(resultado['conservados'], {'incidencias': 1, 'actividad': 2})
        self.assertEqual(verificar_copia(Path(resultado['copia_final']))['incidencias'], 1)
        self.assertTrue(self.servicios[activador.SERVICIO]); self.assertTrue(self.servicios[activador.TEMPORIZADOR])
        self.assertEqual((self.proyecto / 'dispositivos.local.json').read_text(), '{"dispositivos": []}')

    def test_fallo_recupera_esquema_v1_y_conserva_base_fallida(self):
        anterior = self.estado_base()
        def fallo(*_):
            db = Incidencias(self.proyecto / activador.NOMBRE_BASE)
            db.actualizar(self.id_ticket, {'version': 2, 'note': 'Nota durante la activación fallida.'})
            raise RuntimeError('Fallo simulado de comprobación')
        with self.assertRaisesRegex(RuntimeError, 'recuperado los archivos y la base anteriores'):
            self.activar(salud=fallo)
        self.assertEqual(self.estado_base(), anterior)
        reversion = next(self.raiz.glob('red-vigilancia-reversion-*'))
        fallida = self.estado_base(reversion / 'base-activacion-fallida' / activador.NOMBRE_BASE)
        self.assertEqual(fallida[0], 2)
        self.assertIn(('Nota durante la activación fallida.',), fallida[2])
        self.assertEqual((self.proyecto / 'web/laguntza/index.html').read_text(), 'interfaz anterior')
        self.assertFalse((self.proyecto / 'scripts/intercambio_zaintza.py').exists())
        self.assertTrue(self.servicios[activador.SERVICIO]); self.assertTrue(self.servicios[activador.TEMPORIZADOR])

    def test_fallo_de_copia_previa_no_detiene_ni_modifica_panel(self):
        anterior = self.estado_base()
        with patch.object(activador, 'copia_nueva', side_effect=RuntimeError('Copia fallida')):
            with self.assertRaisesRegex(RuntimeError, 'Copia fallida'):
                self.activar()
        self.assertEqual(self.estado_base(), anterior)
        self.assertNotIn(('sudo', 'systemctl', 'stop', activador.SERVICIO), self.llamadas)
        self.assertTrue(self.servicios[activador.TEMPORIZADOR])

    def test_fallo_de_copia_final_informa_panel_nuevo_activo_sin_revertir_datos(self):
        original = activador.copia_nueva
        llamadas = 0
        def copia(*args):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                raise RuntimeError('Copia final fallida')
            return original(*args)
        with patch.object(activador, 'copia_nueva', side_effect=copia):
            with self.assertRaisesRegex(RuntimeError, 'panel nuevo sigue activo'):
                self.activar()
        self.assertEqual(self.estado_base()[0], 2)
        self.assertTrue(self.servicios[activador.SERVICIO]); self.assertTrue(self.servicios[activador.TEMPORIZADOR])

    def test_archivo_alterado_se_rechaza_antes_de_pedir_sudo(self):
        (self.entrega / 'interfaz/assets/app.js').write_text('contenido alterado')
        with self.assertRaisesRegex(ValueError, 'suma de comprobación'):
            self.activar()
        self.assertEqual(self.llamadas, [])

    def test_compilacion_de_demo_no_se_instala_en_servidor_privado(self):
        p = self.entrega / 'interfaz/index.html'
        p.write_text('<meta name="laguntza-mode" content="demo-integrada"><title>Laguntza IT</title><script src="./assets/app.js"></script>')
        self.manifiesto()
        with self.assertRaisesRegex(ValueError, 'sin modo demo fijo'):
            self.activar()
        self.assertEqual(self.llamadas, [])

    def test_fallo_de_copia_de_codigo_recupera_version_anterior(self):
        original = shutil.copyfile
        fallado = False
        def copiar(origen, destino, *args, **kwargs):
            nonlocal fallado
            if Path(origen).is_relative_to(self.entrega / 'archivos') and not fallado:
                fallado = True
                raise OSError('Fallo simulado de escritura')
            return original(origen, destino, *args, **kwargs)
        anterior = self.estado_base()
        with patch.object(shutil, 'copyfile', side_effect=copiar):
            with self.assertRaisesRegex(RuntimeError, 'recuperado los archivos y la base anteriores'):
                self.activar()
        self.assertEqual(self.estado_base(), anterior)
        self.assertEqual((self.proyecto / 'panel-ssh.html').read_text(), 'version anterior')
        self.assertTrue(self.servicios[activador.SERVICIO])


if __name__ == '__main__':
    unittest.main()
