"""Copias y recuperación con datos ficticios y sin consultar el router real."""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
from copias_seguridad import crear_copia
from verificar_copia import verificar_copia
from historial_red import HistorialRed


def preparar_proyecto(base, con_codigo=False):
    proyecto, credenciales = base / 'origen', base / 'claves'
    proyecto.mkdir()
    credenciales.mkdir()
    contenido = {'inventario_panel_version': 1, 'dispositivos': [
        {'panel_id': 'registro-prueba', 'alias': 'Equipo simulado', 'mac': '02:00:00:00:00:01',
         'tipo': 'Ordenador', 'conexion': 'Ethernet', 'funcion': 'Prueba', 'revision': '2026-11-18'}]}
    (proyecto / 'dispositivos.local.json').write_text(json.dumps(contenido), encoding='utf-8')
    for nombre in ('router-user', 'router-password', 'panel-password'):
        (credenciales / nombre).write_text('credencial-ficticia-pruebas', encoding='utf-8')
    historial = HistorialRed(proyecto / 'historial-red.local.sqlite3')
    with historial.conexion() as db:
        db.execute("INSERT INTO eventos(fecha,equipo_id,alias,tipo) VALUES (?,?,?,?)",
                   ('2026-11-18T10:00:00+01:00', 'equipo-prueba', 'Equipo simulado', 'conectado'))
    if con_codigo:
        (proyecto / 'scripts').mkdir()
        for ruta in (RAIZ / 'scripts').glob('*.py'):
            (proyecto / 'scripts' / ruta.name).write_bytes(ruta.read_bytes())
        (proyecto / 'panel-ssh.html').write_bytes((RAIZ / 'panel-ssh.html').read_bytes())
    return proyecto, credenciales


def reescribir(ruta, cambios=None, adicional=None):
    cambios = cambios or {}
    with tarfile.open(ruta) as archivo:
        datos = {miembro.name: archivo.extractfile(miembro).read() for miembro in archivo}
    datos.update(cambios)
    with tarfile.open(ruta, 'w:gz') as archivo:
        for nombre, contenido in datos.items():
            miembro = tarfile.TarInfo(nombre)
            miembro.size = len(contenido)
            archivo.addfile(miembro, io.BytesIO(contenido))
        if adicional is not None:
            miembro, contenido = adicional
            archivo.addfile(miembro, io.BytesIO(contenido) if miembro.isfile() else None)


class Copias(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name)
        self.proyecto, self.credenciales = preparar_proyecto(self.base)
        self.archivo = crear_copia(self.proyecto, self.credenciales, self.base / 'copias')

    def test_copia_verificada_y_extraccion(self):
        destino = self.base / 'extraido'
        resultado = verificar_copia(self.archivo, destino)
        self.assertEqual(resultado['dispositivos'], 1)
        self.assertEqual(resultado['registros_historial'], 1)
        self.assertEqual((destino / 'proyecto/dispositivos.local.json').read_bytes(),
                         (self.proyecto / 'dispositivos.local.json').read_bytes())
        with closing(sqlite3.connect(destino / 'proyecto/historial-red.local.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM eventos').fetchone()[0], 1)

    def test_no_sobrescribir_carpeta_existente(self):
        marcador = self.proyecto / 'intacto.txt'
        marcador.write_text('conservar')
        with self.assertRaises(ValueError):
            verificar_copia(self.archivo, self.proyecto)
        self.assertEqual(marcador.read_text(), 'conservar')

    def test_archivo_modificado_rechazado_antes_de_extraer(self):
        reescribir(self.archivo, {'credenciales/router-password': b'alterado'})
        with self.assertRaises(ValueError):
            verificar_copia(self.archivo, self.base / 'no-crear')
        self.assertFalse((self.base / 'no-crear').exists())

    def test_archivo_ajeno_al_manifiesto(self):
        reescribir(self.archivo, {'proyecto/extra.txt': b'extra'})
        with self.assertRaises(ValueError):
            verificar_copia(self.archivo)

    def test_rutas_peligrosas(self):
        for nombre in ('../fuera.txt', '/fuera.txt', 'proyecto/../../fuera.txt',
                       'proyecto\\fuera.txt', 'proyecto/C:fuera.txt'):
            with self.subTest(nombre=nombre):
                archivo = crear_copia(self.proyecto, self.credenciales, self.base / 'copias')
                reescribir(archivo, {nombre: b'fuera'})
                with self.assertRaises(ValueError):
                    verificar_copia(archivo)

    def test_enlace_y_nombre_duplicado(self):
        miembro = tarfile.TarInfo('proyecto/enlace')
        miembro.type = tarfile.SYMTYPE
        miembro.linkname = '/fuera'
        reescribir(self.archivo, adicional=(miembro, b''))
        with self.assertRaises(ValueError):
            verificar_copia(self.archivo)
        otro = crear_copia(self.proyecto, self.credenciales, self.base / 'copias')
        miembro = tarfile.TarInfo('credenciales/router-user')
        miembro.size = 3
        reescribir(otro, adicional=(miembro, b'otro'[:3]))
        with self.assertRaises(ValueError):
            verificar_copia(otro)

    def test_historial_invalido_aunque_su_suma_coincida(self):
        with tarfile.open(self.archivo) as archivo:
            manifiesto = json.load(archivo.extractfile('manifest.json'))
        datos = b'no es sqlite'
        manifiesto['sha256']['proyecto/historial-red.local.sqlite3'] = hashlib.sha256(datos).hexdigest()
        reescribir(self.archivo, {'proyecto/historial-red.local.sqlite3': datos,
                                  'manifest.json': json.dumps(manifiesto).encode()})
        with self.assertRaises(ValueError):
            verificar_copia(self.archivo)

    def test_sqlite_en_uso_con_wal(self):
        with closing(sqlite3.connect(self.proyecto / 'historial-red.local.sqlite3')) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute("INSERT INTO eventos(fecha,equipo_id,alias,tipo) VALUES ('ahora','prueba','Prueba','conectado')")
            db.commit()
            copia = crear_copia(self.proyecto, self.credenciales, self.base / 'copias')
            self.assertEqual(verificar_copia(copia)['registros_historial'], 2)

    def test_rotacion_y_archivos_ajenos(self):
        ajeno = self.base / 'copias/no-borrar.tar.gz'
        ajeno.write_bytes(b'ajeno')
        for _ in range(8):
            crear_copia(self.proyecto, self.credenciales, self.base / 'copias')
        self.assertEqual(len(list((self.base / 'copias').glob('copia-red-*.tar.gz'))), 7)
        self.assertEqual(ajeno.read_bytes(), b'ajeno')

    def test_no_crear_copia_con_inventario_json_invalido(self):
        (self.proyecto / 'dispositivos.local.json').write_text('{invalido')
        with self.assertRaises(ValueError):
            crear_copia(self.proyecto, self.credenciales, self.base / 'copias')
        self.assertFalse(list((self.base / 'copias').glob('*.partial')))

    def test_incluir_programas_de_copia_de_windows(self):
        (self.proyecto / 'scripts').mkdir()
        (self.proyecto / 'scripts/copia.ps1').write_text('Write-Output "prueba"')
        copia = crear_copia(self.proyecto, self.credenciales, self.base / 'copias')
        with tarfile.open(copia) as archivo:
            self.assertIn('proyecto/scripts/copia.ps1', archivo.getnames())


class Historial(unittest.TestCase):
    def test_silencio_y_reinicio_no_inventan_desconexiones(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / 'historial.sqlite3'
            historial = HistorialRed(ruta)
            conectado = [{'id': 'a', 'alias': 'A', 'estado': 'conectado'}]
            historial.observar(conectado, '2026-11-18T10:00:00+01:00')
            historial.observar([], '2026-11-18T10:01:00+01:00')
            historial.observar(conectado, '2026-11-18T10:02:00+01:00')
            self.assertEqual(historial.consultar()['total'], 0)
            historial.observar([{'id': 'a', 'alias': 'A', 'estado': 'desconectado'}], '2026-11-18T10:03:00+01:00')
            self.assertEqual(historial.consultar()['total'], 1)
            reiniciado = HistorialRed(ruta)
            reiniciado.observar(conectado, '2026-11-18T10:04:00+01:00')
            self.assertEqual(reiniciado.consultar()['total'], 1)


if __name__ == '__main__':
    unittest.main()
