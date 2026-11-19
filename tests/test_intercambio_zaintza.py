from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from incidencias import Incidencias, ConflictoIncidencia
from intercambio_zaintza import validar_intercambio
from copias_seguridad import crear_copia
from verificar_copia import verificar_copia

EJEMPLO = json.loads((Path(__file__).parent / 'fixtures/zaintza-demo-v1.json').read_text())


class IntercambioZaintza(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.db = Incidencias(self.raiz / 'incidencias.local.sqlite3')

    def datos(self, **cambios):
        return {'requestId': 'a' * 32, 'title': 'Prueba de Zaintza ficticia',
                'description': 'He preparado una prueba ficticia de intercambio entre proyectos.',
                'category': 'Acceso y cuentas', 'priority': 'medium', 'deviceId': '',
                'source': copy.deepcopy(EJEMPLO), 'confirmDemo': True, **cambios}

    def test_referencia_persiste_y_reimportacion_no_sobrescribe(self):
        ticket = self.db.importar_zaintza(self.datos())
        self.assertFalse(ticket['importReused'])
        self.db.actualizar(ticket['id'], {'version': 1, 'note': 'He revisado el escenario ficticio.'})
        reiniciado = Incidencias(self.db.ruta)
        repetida = reiniciado.importar_zaintza(self.datos(requestId='b' * 32, title='Otro título propuesto'))
        self.assertTrue(repetida['importReused'])
        self.assertEqual(repetida['id'], ticket['id'])
        self.assertEqual(repetida['title'], ticket['title'])
        self.assertEqual(repetida['version'], 2)
        self.assertEqual(repetida['context']['source'], validar_intercambio(EJEMPLO))
        self.assertEqual(reiniciado.listar()['total'], 1)

    def test_misma_referencia_con_evidencia_distinta_es_conflicto(self):
        self.db.importar_zaintza(self.datos())
        otro = copy.deepcopy(EJEMPLO)
        otro['detection']['firstSeen'] = '2026-09-15T07:59:59.000Z'
        with self.assertRaises(ConflictoIncidencia):
            self.db.importar_zaintza(self.datos(requestId='b' * 32, source=otro))
        self.assertEqual(self.db.listar()['total'], 1)

    def test_importacion_simultanea_no_duplica(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(lambda r: self.db.importar_zaintza(self.datos(requestId=r)), ['a' * 32, 'b' * 32]))
        self.assertEqual(len({r['id'] for r in resultados}), 1)
        self.assertEqual(sum(not r['importReused'] for r in resultados), 1)

    def test_rechaza_datos_reales_campos_extra_y_formato_desconocido(self):
        for cambio in ({'version': 2}, {'version': True}, {'environment': 'real'}, {'sourceInstanceId': 'otro'},
                       {'username': 'dato-no-permitido'}, {'detection': []}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.db.importar_zaintza(self.datos(source={**copy.deepcopy(EJEMPLO), **cambio}))
        for cambio in ({'eventCount': True}, {'eventCount': 0}, {'evidenceRefs': []},
                       {'firstSeen': '2026-09-15T07:00:00.000Z'}, {'lastSeen': 'mal'}, {'sourceIp': '192.0.2.1'}):
            origen = copy.deepcopy(EJEMPLO); origen['detection'].update(cambio)
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.db.importar_zaintza(self.datos(source=origen))
        for cambio in ({'confirmDemo': False}, {'deviceId': 'impresora'}, {'category': 'Otros'}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.db.importar_zaintza(self.datos(**cambio))
        self.assertEqual(self.db.listar()['total'], 0)

    def test_migracion_v1_conserva_incidencia_existente(self):
        ticket = self.db.crear({k: v for k, v in self.datos().items() if k not in ('source', 'confirmDemo')})
        with closing(sqlite3.connect(self.db.ruta)) as conn, conn:
            conn.execute('DROP INDEX idx_incidencia_origen')
            conn.execute('ALTER TABLE incidencias DROP COLUMN source_key')
            conn.execute('PRAGMA user_version=1')
        migrada = Incidencias(self.db.ruta)
        self.assertEqual(migrada.detalle(ticket['id'])['title'], ticket['title'])
        imported = migrada.importar_zaintza(self.datos(requestId='b' * 32))
        self.assertNotEqual(imported['id'], ticket['id'])
        self.assertEqual(migrada.listar()['total'], 2)

    def test_copia_recupera_referencia_seguimiento_y_no_duplica(self):
        proyecto = self.raiz / 'proyecto'; proyecto.mkdir()
        claves = self.raiz / 'claves'; claves.mkdir()
        (proyecto / 'dispositivos.local.json').write_text('{"dispositivos": []}')
        for nombre in ('router-user', 'router-password', 'panel-password'):
            (claves / nombre).write_text('credencial-ficticia')
        db = Incidencias(proyecto / 'incidencias.local.sqlite3')
        ticket = db.importar_zaintza(self.datos())
        db.actualizar(ticket['id'], {'version': 1, 'status': 'resolved', 'resolution': 'He completado la revisión de esta prueba ficticia.'})
        copia = crear_copia(proyecto, claves, self.raiz / 'copias')
        resultado = verificar_copia(copia, self.raiz / 'recuperada')
        self.assertEqual(resultado['incidencias'], 1)
        recuperada = Incidencias(self.raiz / 'recuperada/proyecto/incidencias.local.sqlite3')
        existente = recuperada.importar_zaintza(self.datos(requestId='b' * 32))
        self.assertTrue(existente['importReused'])
        self.assertEqual(existente['status'], 'resolved')
        self.assertEqual(existente['version'], 2)


if __name__ == '__main__':
    unittest.main()
