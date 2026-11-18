"""Arranque de una copia ficticia recuperada; nunca usa dispositivos reales."""
import base64
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from test_recuperacion import preparar_proyecto, crear_copia, verificar_copia

DEPENDENCIAS = all(importlib.util.find_spec(nombre) for nombre in ('sagemcom_api', 'aiohttp'))


@unittest.skipUnless(DEPENDENCIAS, 'Instala requirements-servidor.txt para probar el panel recuperado.')
class PanelRecuperado(unittest.TestCase):
    def test_arranque_protecciones_corte_y_reinicio(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            proyecto, credenciales = preparar_proyecto(raiz, con_codigo=True)
            copia = crear_copia(proyecto, credenciales, raiz / 'copias')
            verificar_copia(copia, raiz / 'recuperado')
            restaurado = raiz / 'recuperado/proyecto'
            control = restaurado / 'control-prueba.json'

            def cambiar(**datos):
                nuevo = control.with_suffix('.tmp')
                nuevo.write_text(json.dumps(datos))
                nuevo.replace(control)

            cambiar(activo=True)
            with socket.socket() as seleccion:
                seleccion.bind(('127.0.0.1', 0))
                puerto = seleccion.getsockname()[1]
            autorizacion = 'Basic ' + base64.b64encode(b'panel:clave-panel-ficticia-prueba').decode()
            proceso = None

            def arrancar():
                return subprocess.Popen([sys.executable, str(Path(__file__).with_name('servidor_simulado.py')),
                                         str(restaurado), str(puerto)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            def detener():
                if proceso is not None and proceso.poll() is None:
                    proceso.terminate()
                    proceso.wait(timeout=8)

            def solicitar(ruta, metodo='GET', autenticado=True, extra=None):
                cabeceras = {'Host': '127.0.0.1:8765'}
                if autenticado:
                    cabeceras['Authorization'] = autorizacion
                cabeceras.update(extra or {})
                conexion = http.client.HTTPConnection('127.0.0.1', puerto, timeout=2)
                try:
                    conexion.request(metodo, ruta, body=b'{}' if metodo == 'POST' else None, headers=cabeceras)
                    respuesta = conexion.getresponse()
                    return respuesta.status, respuesta.read()
                finally:
                    conexion.close()

            def esperar(condicion, limite=15):
                hasta = time.monotonic() + limite
                while time.monotonic() < hasta:
                    self.assertIsNone(proceso.poll(), 'El panel recuperado ha terminado inesperadamente.')
                    try:
                        codigo, cuerpo = solicitar('/api/estado')
                        if codigo == 200:
                            estado = json.loads(cuerpo)
                            if condicion(estado):
                                return estado
                    except (OSError, http.client.HTTPException):
                        pass
                    time.sleep(0.1)
                self.fail('El panel no ha alcanzado el estado esperado.')

            try:
                proceso = arrancar()
                estado = esperar(lambda e: e.get('ultima_comprobacion') is not None)
                self.assertEqual(estado['inventario'][0]['alias'], 'Equipo simulado')
                self.assertEqual(solicitar('/')[0], 200)
                self.assertEqual(json.loads(solicitar('/api/historial')[1])['total'], 1)
                for ruta in ('/', '/api/estado', '/api/historial'):
                    self.assertEqual(solicitar(ruta, autenticado=False)[0], 401)
                self.assertEqual(solicitar('/api/estado', extra={'Host': 'otro.ejemplo:8765'})[0], 403)
                self.assertEqual(solicitar('/api/aparato', metodo='POST')[0], 403)
                self.assertEqual(solicitar('/api/aparato', metodo='POST', extra={
                    'X-Panel-Token': estado['edicion_token'], 'Origin': 'http://otro.ejemplo'})[0], 403)
                cambiar(activo=True, error=True)
                esperar(lambda e: e.get('error') == 'Consulta fallida: ConnectionError')
                self.assertEqual(json.loads(solicitar('/api/historial')[1])['total'], 1)
                cambiar(activo=True)
                esperar(lambda e: e.get('error') is None)
                self.assertEqual(json.loads(solicitar('/api/historial')[1])['total'], 1)
                cambiar(activo=False)
                esperar(lambda e: e['equipos_router'][0]['estado'] == 'desconectado')
                self.assertEqual(json.loads(solicitar('/api/historial')[1])['total'], 2)
                detener()
                proceso = arrancar()
                esperar(lambda e: e.get('ultima_comprobacion') is not None)
                self.assertEqual(json.loads(solicitar('/api/historial')[1])['total'], 2)
            finally:
                detener()


if __name__ == '__main__':
    unittest.main()
