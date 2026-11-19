from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from incidencias import Incidencias, ConflictoIncidencia, IncidenciaNoExiste
from copias_seguridad import crear_copia
from verificar_copia import verificar_copia


class IncidenciasTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.almacen = Incidencias(self.raiz / 'incidencias.local.sqlite3')
        self.equipo = {'id': 'equipo-ficticio', 'name': 'Impresora de ejemplo',
                       'state': 'desconectado', 'observedAt': '2026-11-19T10:00:00+01:00'}

    def datos(self, **cambios):
        valores = {'requestId': 'a' * 32, 'title': 'Revisar la impresora',
                   'description': 'La impresora de ejemplo no aparece conectada.',
                   'category': 'Red y conexión', 'priority': 'medium', 'deviceId': self.equipo['id']}
        return {**valores, **cambios}

    def crear(self, **cambios):
        return self.almacen.crear(self.datos(**cambios), self.equipo)

    def test_persistencia_y_evidencia_proceden_del_servidor(self):
        resultado = self.crear(deviceName='Nombre impuesto por el cliente', actor='otro')
        leido = Incidencias(self.almacen.ruta).detalle(resultado['id'])
        self.assertEqual(leido['deviceName'], self.equipo['name'])
        self.assertEqual(leido['context']['state'], 'desconectado')
        self.assertEqual(leido['activity'][0]['actor'], 'panel')
        self.assertEqual(leido['version'], 1)

    def test_reintento_no_duplica_y_no_admite_otros_datos(self):
        primera = self.crear()
        segunda = self.crear()
        self.assertEqual(primera['id'], segunda['id'])
        self.assertEqual(self.almacen.listar()['total'], 1)
        with self.assertRaises(ConflictoIncidencia):
            self.crear(title='Un problema diferente')

    def test_resolucion_obligatoria_y_reapertura_con_motivo(self):
        ticket = self.crear()
        with self.assertRaises(ValueError):
            self.almacen.actualizar(ticket['id'], {'version': 1, 'status': 'resolved'})
        cerrada = self.almacen.actualizar(ticket['id'], {'version': 1, 'status': 'resolved',
            'resolution': 'He comprobado el enlace y la impresora vuelve a responder.'})
        self.assertEqual(cerrada['status'], 'resolved')
        with self.assertRaises(ValueError):
            self.almacen.actualizar(ticket['id'], {'version': 2, 'status': 'in_progress'})
        abierta = self.almacen.actualizar(ticket['id'], {'version': 2, 'status': 'in_progress',
            'note': 'El problema ha vuelto a aparecer durante una prueba posterior.'})
        self.assertEqual(abierta['resolution'], '')
        self.assertTrue(any(item['type'] == 'resolution' for item in abierta['activity']))
        self.assertTrue(any(item['type'] == 'reopened' for item in abierta['activity']))

    def test_dos_editores_no_sobrescriben_seguimiento(self):
        ticket = self.crear()
        barrera = threading.Barrier(2)
        def cambiar(nota):
            barrera.wait(timeout=3)
            try:
                self.almacen.actualizar(ticket['id'], {'version': 1, 'note': nota})
                return 'guardado'
            except ConflictoIncidencia:
                return 'conflicto'
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(cambiar, ['Primera revisión de la conexión.', 'Segunda revisión desde otra vista.']))
        self.assertCountEqual(resultados, ['guardado', 'conflicto'])
        actual = self.almacen.detalle(ticket['id'])
        self.assertEqual(actual['version'], 2)
        self.assertEqual(sum(item['type'] == 'note' for item in actual['activity']), 1)

    def test_validacion_y_referencia_de_aparato(self):
        for cambios in ({'title': 'mal'}, {'description': 'corta'}, {'priority': 'urgente'},
                        {'category': 'inventada'}, {'requestId': 'invalid'}, {'deviceId': 'desconocido'}):
            with self.subTest(cambios=cambios), self.assertRaises(ValueError):
                self.crear(**cambios)
        self.assertEqual(self.almacen.listar()['total'], 0)
        with self.assertRaises(IncidenciaNoExiste):
            self.almacen.detalle('INC-999999')

    def test_filtros_paginacion_y_metricas_globales(self):
        for i in range(27):
            self.crear(requestId=f'{i:032x}', title=f'Impresora de ejemplo {i}', priority='high' if i == 0 else 'medium')
        pagina = self.almacen.listar(pagina=2)
        self.assertEqual(len(pagina['tickets']), 2)
        self.assertEqual(pagina['total'], 27)
        filtrada = self.almacen.listar(prioridad='high')
        self.assertEqual(filtrada['total'], 1)
        self.assertEqual(filtrada['summary']['total'], 27)
        self.assertEqual(filtrada['summary']['high'], 1)
        self.assertEqual(self.almacen.listar(q='%')['total'], 0)
        self.assertEqual(self.almacen.listar(q='IMPRESORA')['total'], 27)
        self.assertEqual(self.almacen.listar(q='INC-000001')['total'], 1)

    def test_textos_no_se_interpretan_como_sql(self):
        ticket = self.crear(title="Prueba '); DROP TABLE incidencias; --")
        self.assertEqual(self.almacen.detalle(ticket['id'])['title'], "Prueba '); DROP TABLE incidencias; --")
        self.assertEqual(self.almacen.listar()['total'], 1)

    def test_sin_cambios_no_crea_actividad_ni_version(self):
        ticket = self.crear()
        resultado = self.almacen.actualizar(ticket['id'], {'version': 1, 'note': ''})
        self.assertEqual(resultado['version'], 1)
        self.assertEqual(len(resultado['activity']), 1)

    def test_copia_y_restauracion_incluyen_incidencias_y_seguimiento(self):
        proyecto, credenciales = self.raiz / 'proyecto', self.raiz / 'credenciales'
        proyecto.mkdir(); credenciales.mkdir()
        (proyecto / 'dispositivos.local.json').write_text('{"dispositivos": []}')
        for nombre in ('router-user', 'router-password', 'panel-password'):
            (credenciales / nombre).write_text('credencial-ficticia')
        almacen = Incidencias(proyecto / 'incidencias.local.sqlite3')
        ticket = almacen.crear(self.datos(deviceId=None))
        almacen.actualizar(ticket['id'], {'version': 1, 'note': 'Nota que debe conservarse en la copia.'})
        archivo = crear_copia(proyecto, credenciales, self.raiz / 'copias')
        resultado = verificar_copia(archivo, self.raiz / 'restaurado')
        self.assertEqual(resultado['incidencias'], 1)
        recuperado = Incidencias(self.raiz / 'restaurado/proyecto/incidencias.local.sqlite3').detalle(ticket['id'])
        self.assertEqual(recuperado['version'], 2)
        self.assertTrue(any(item['type'] == 'note' for item in recuperado['activity']))


if __name__ == '__main__':
    unittest.main()
