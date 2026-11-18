"""Prueba local de lectura de dispositivos del router Sagemcom."""

import argparse
import asyncio
import getpass
import ipaddress
import logging
from collections import Counter

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import ApiMode, EncryptionMethod


def direccion_privada(texto):
    try:
        direccion = ipaddress.ip_address(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Introduce solo la IP del router.") from error
    redes = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if direccion.version != 4 or not any(direccion in ipaddress.ip_network(red) for red in redes):
        raise argparse.ArgumentTypeError("Usa una IPv4 privada de tu red domestica.")
    return str(direccion)


async def consultar(opciones, usuario, clave):
    metodo = EncryptionMethod(opciones.metodo)
    async with SagemcomClient(
        opciones.router,
        usuario,
        clave,
        authentication_method=metodo,
        api_mode=ApiMode.LEGACY,
    ) as cliente:
        conectado = False
        try:
            print("Comprobando el acceso al router...", flush=True)
            async with asyncio.timeout(45):
                await cliente.login()
                conectado = True
                print("Acceso aceptado. Consultando la lista de aparatos...", flush=True)
                equipos = await cliente.get_hosts()

            activos = sum(equipo.active is True for equipo in equipos)
            inactivos = sum(equipo.active is False for equipo in equipos)
            desconocidos = len(equipos) - activos - inactivos
            print("\nLectura completada.")
            print(f"Equipos que conoce el router: {len(equipos)}")
            print(f"Marcados como conectados: {activos}")
            print(f"Marcados como desconectados: {inactivos}")
            print(f"Estado sin informar: {desconocidos}")
            conexiones = Counter(str(equipo.interface_type or "Sin especificar") for equipo in equipos if equipo.active is True)
            for conexion, cantidad in sorted(conexiones.items()):
                print(f"  {conexion}: {cantidad}")
        finally:
            if conectado:
                try:
                    async with asyncio.timeout(5):
                        await cliente.logout()
                except Exception:
                    print("La consulta ha terminado, pero no se ha podido confirmar el cierre de su sesion.")


def main():
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--router", type=direccion_privada, default="192.168.1.1")
    argumentos.add_argument("--metodo", choices=("MD5", "MD5_NONCE", "SHA512"), default="MD5")
    opciones = argumentos.parse_args()
    logging.getLogger("sagemcom_api").setLevel(logging.CRITICAL)
    usuario = input("Usuario del router [user]: ").strip() or "user"
    clave = getpass.getpass("Contrasena del router (no se muestra al escribir): ")
    if not clave:
        raise SystemExit("No se ha introducido una contrasena.")
    print(f"Metodo seleccionado para esta prueba: {opciones.metodo}")
    try:
        asyncio.run(consultar(opciones, usuario, clave))
    except KeyboardInterrupt:
        print("\nPrueba interrumpida.")
    except Exception as error:
        print("\nLa lectura no se ha completado.")
        print("Tipo de error: " + type(error).__name__)
        print("Comparte solo ese tipo de error para revisar el siguiente paso.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
