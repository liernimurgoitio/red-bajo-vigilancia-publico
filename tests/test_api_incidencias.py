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

from test_recuperacion import preparar_proyecto

DEPENDENCIAS = all(importlib.util.find_spec(nombre) for nombre in ('sagemcom_api', 'aiohttp'))


@unittest.skipUnless(DEPENDENCIAS, 'Instala las dependencias del servidor.')
class ApiIncidencias(unittest.TestCase):
    def test_proteccion_persistencia_y_contrato_http(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            proyecto, _ = preparar_proyecto(raiz, con_codigo=True)
            (proyecto / 'control-prueba.json').write_text('{"activo": true}')
            interfaz = proyecto / 'web/laguntza'
            (interfaz / 'assets').mkdir(parents=True)
            (interfaz / 'index.html').write_text('<html>Laguntza IT de prueba</html>')
            (interfaz / 'assets/app.js').write_text('const prueba = true;')
            with socket.socket() as puerto_libre:
                puerto_libre.bind(('127.0.0.1', 0)); puerto = puerto_libre.getsockname()[1]
            credencial = 'Basic ' + base64.b64encode(b'panel:clave-panel-ficticia-prueba').decode()
            proceso = None

            def iniciar():
                return subprocess.Popen([sys.executable, str(Path(__file__).with_name('servidor_simulado.py')),
                    str(proyecto), str(puerto)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            def detener():
                if proceso is not None and proceso.poll() is None:
                    proceso.terminate(); proceso.wait(timeout=8)

            def consultar(ruta, metodo='GET', datos=None, auth=True, token=None, extra=None):
                headers = {'Host': '127.0.0.1:8765'}
                if auth: headers['Authorization'] = credencial
                if token: headers['X-Panel-Token'] = token
                if datos is not None: headers['Content-Type'] = 'application/json'
                headers.update(extra or {})
                body = json.dumps(datos).encode() if datos is not None else None
                conexion = http.client.HTTPConnection('127.0.0.1', puerto, timeout=3)
                try:
                    conexion.request(metodo, ruta, body=body, headers=headers)
                    response = conexion.getresponse()
                    contenido = response.read()
                    if 'application/json' in response.getheader('Content-Type', ''):
                        contenido = json.loads(contenido)
                    return response.status, contenido
                finally:
                    conexion.close()

            def esperar():
                limite = time.monotonic() + 15
                while time.monotonic() < limite:
                    self.assertIsNone(proceso.poll())
                    try:
                        status, data = consultar('/api/estado')
                        if status == 200 and data.get('ultima_comprobacion'):
                            return
                    except (OSError, http.client.HTTPException):
                        pass
                    time.sleep(0.1)
                self.fail('El servidor de prueba no ha arrancado.')

            try:
                proceso = iniciar(); esperar()
                for ruta in ('/soporte/', '/api/incidencias', '/api/incidencias/contexto'):
                    self.assertEqual(consultar(ruta, auth=False)[0], 401)
                self.assertEqual(consultar('/soporte/')[0], 200)
                self.assertEqual(consultar('/soporte/assets/app.js')[0], 200)
                self.assertEqual(consultar('/soporte/%2e%2e/%2e%2e/dispositivos.local.json')[0], 404)
                self.assertEqual(consultar('/api/incidencias', extra={'Host': 'otro.ejemplo:8765'})[0], 403)
                status, contexto = consultar('/api/incidencias/contexto')
                self.assertEqual(status, 200)
                token = contexto['token']
                equipo = next(item for item in contexto['devices'] if item['state'] == 'conectado')
                self.assertNotIn('ip', equipo); self.assertNotIn('mac', equipo)
                datos = {'requestId': 'a' * 32, 'title': 'Revisar aparato de prueba', 'description': 'Problema ficticio que se ha observado durante la prueba.',
                         'category': 'Equipos', 'priority': 'high', 'deviceId': equipo['id'], 'deviceName': 'Nombre no autorizado'}
                self.assertEqual(consultar('/api/incidencias', 'POST', datos)[0], 403)
                self.assertEqual(consultar('/api/incidencias', 'POST', datos, token=token,
                    extra={'Origin': 'http://otro.ejemplo'})[0], 403)
                status, ticket = consultar('/api/incidencias', 'POST', datos, token=token)
                self.assertEqual(status, 201)
                self.assertEqual(ticket['deviceName'], equipo['name'])
                self.assertEqual(consultar('/api/incidencias', 'POST', datos, token=token)[1]['id'], ticket['id'])
                self.assertEqual(consultar('/api/incidencias')[1]['total'], 1)
                ruta = '/api/incidencias/' + ticket['id']
                self.assertEqual(consultar(ruta, 'POST', {'version': 1, 'status': 'resolved'}, token=token)[0], 400)
                status, updated = consultar(ruta, 'POST', {'version': 1, 'status': 'in_progress', 'note': 'He comprobado el enlace de ejemplo.'}, token=token)
                self.assertEqual(status, 200); self.assertEqual(updated['version'], 2)
                self.assertEqual(consultar(ruta, 'POST', {'version': 1, 'note': 'Versión antigua.'}, token=token)[0], 409)
                self.assertEqual(consultar('/api/incidencias?page=0')[0], 400)
                self.assertEqual(consultar('/api/incidencias/INC-999999')[0], 404)
                source = json.loads((Path(__file__).parent / 'fixtures/zaintza-demo-v1.json').read_text())
                prueba = {**datos, 'requestId': 'b' * 32, 'deviceId': '', 'category': 'Acceso y cuentas', 'source': source, 'confirmDemo': True}
                self.assertEqual(consultar('/api/incidencias/importar-zaintza', 'POST', prueba)[0], 403)
                status, importada = consultar('/api/incidencias/importar-zaintza', 'POST', prueba, token=token)
                self.assertEqual(status, 201); self.assertFalse(importada['importReused'])
                self.assertEqual(importada['context']['source']['environment'], 'demo')
                detener(); proceso = iniciar(); esperar()
                nuevo_token = consultar('/api/incidencias/contexto')[1]['token']
                prueba['requestId'] = 'c' * 32
                status, repetida = consultar('/api/incidencias/importar-zaintza', 'POST', prueba, token=nuevo_token)
                self.assertEqual(status, 200); self.assertTrue(repetida['importReused'])
                self.assertEqual(repetida['id'], importada['id'])
                self.assertEqual(consultar('/api/incidencias')[1]['total'], 2)
                recuperada = consultar(ruta)[1]
                self.assertEqual(recuperada['version'], 2)
                self.assertTrue(any(item['type'] == 'note' for item in recuperada['activity']))
                self.assertEqual(consultar(ruta, 'POST', {'version': 2, 'note': 'Token anterior.'}, token=token)[0], 403)
            finally:
                detener()


if __name__ == '__main__':
    unittest.main()
