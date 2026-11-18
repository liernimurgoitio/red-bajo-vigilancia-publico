"""Arranca el código recuperado con un router ficticio, solo en loopback."""
import asyncio
import ipaddress
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

raiz, puerto = Path(sys.argv[1]), int(sys.argv[2])
sys.path.insert(0, str(raiz / 'scripts'))
import vigilar_router


class RouterFicticio:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def login(self):
        return None

    async def logout(self):
        return None

    async def get_hosts(self):
        datos = json.loads((raiz / 'control-prueba.json').read_text())
        if datos.get('error'):
            raise ConnectionError('Corte simulado')
        return [SimpleNamespace(phys_address='02:00:00:00:00:01', uid='1',
                ip_address='192.0.2.10', interface_type='Ethernet',
                user_friendly_name='Simulado', name='Simulado', active=datos['activo'])]


ServidorOriginal = vigilar_router.ThreadingHTTPServer


class ServidorPrueba(ServidorOriginal):
    def __init__(self, direccion, manejador):
        super().__init__(('127.0.0.1', puerto), manejador)


# Impedir que un cambio accidental de la prueba consulte un aparato real.
SocketOriginal = socket.socket


class SocketSoloLocal(SocketOriginal):
    def connect(self, direccion):
        if isinstance(direccion, tuple) and not ipaddress.ip_address(direccion[0]).is_loopback:
            raise AssertionError('La prueba no permite conexiones fuera de loopback.')
        return super().connect(direccion)


socket.socket = SocketSoloLocal
vigilar_router.RAIZ = raiz
vigilar_router.SagemcomClient = RouterFicticio
vigilar_router.ThreadingHTTPServer = ServidorPrueba
vigilar_router.direccion_del_pc = lambda _: '127.0.0.1'
vigilar_router.ejecutar(SimpleNamespace(router='192.0.2.1', red_local=True,
                       intervalo=1, servicio=True), 'ficticio', 'ficticio',
                       'clave-panel-ficticia-prueba')
