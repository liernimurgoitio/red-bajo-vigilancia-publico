"""Lectura del estado webOS con una vinculación ya autorizada."""
import asyncio
import copy
import ipaddress
import aiohttp


def interpretar_estado(valor):
    if valor in ("Active", "Screen Saver"):
        return "encendida"
    return "no_disponible"


async def consultar_estado(ip, clave):
    try:
        direccion = ipaddress.ip_address(ip)
        if direccion.version != 4 or not direccion.is_private or direccion.is_loopback:
            return "no_disponible"
        from aiopylgtv.handshake import REGISTRATION_PAYLOAD
        payload = copy.deepcopy(REGISTRATION_PAYLOAD)
        payload.update({"forcePairing":False, "client-key":clave})
        async with asyncio.timeout(7):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{ip}:3000",timeout=aiohttp.ClientWSTimeout(ws_receive=4)) as ws:
                    await ws.send_json({"id":"registro","type":"register","payload":payload})
                    while True:
                        mensaje = await ws.receive_json()
                        if mensaje.get("type") == "registered":
                            break
                        if mensaje.get("type") == "error" or mensaje.get("payload",{}).get("pairingType"):
                            return "requiere_autorizacion"
                    await ws.send_json({"id":"estado","type":"request","uri":"ssap://com.webos.service.tvpower/power/getPowerState","payload":{}})
                    while True:
                        mensaje = await ws.receive_json()
                        if mensaje.get("id") == "estado":
                            return interpretar_estado(mensaje.get("payload",{}).get("state"))
    except Exception:
        return "no_disponible"


def enviar_encendido(mac):
    import re
    import socket
    limpia = str(mac or "").replace(":", "").replace("-", "")
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", limpia):
        raise ValueError("Falta la dirección física de la TV. Espera una consulta del router.")
    paquete = b"\xff" * 6 + bytes.fromhex(limpia) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conexion:
        conexion.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        conexion.sendto(paquete, ("255.255.255.255", 9))
    return "Solicitud de encendido enviada. Espera a que la TV confirme su estado; este modelo puede no admitir el encendido por red."


async def enviar_apagado(ip, clave):
    from aiopylgtv.handshake import REGISTRATION_PAYLOAD
    direccion = ipaddress.ip_address(ip)
    if direccion.version != 4 or not direccion.is_private or direccion.is_loopback:
        raise ValueError("La dirección de la TV no es válida.")
    payload = copy.deepcopy(REGISTRATION_PAYLOAD)
    payload.update({"forcePairing":False,"client-key":clave})
    try:
        async with asyncio.timeout(8):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://{ip}:3000",timeout=aiohttp.ClientWSTimeout(ws_receive=4)) as ws:
                    await ws.send_json({"id":"registro","type":"register","payload":payload})
                    while True:
                        mensaje = await ws.receive_json()
                        if mensaje.get("type") == "registered":
                            break
                        if mensaje.get("type") == "error" or mensaje.get("payload",{}).get("pairingType"):
                            raise ValueError("La TV necesita revisar su vinculación.")
                    await ws.send_json({"id":"apagar","type":"request","uri":"ssap://system/turnOff","payload":{}})
                    try:
                        while True:
                            mensaje = await ws.receive_json()
                            if mensaje.get("id") == "apagar":
                                if mensaje.get("type") == "error" or mensaje.get("payload",{}).get("returnValue") is False:
                                    raise ValueError("La TV ha rechazado la solicitud de apagado.")
                                break
                    except (aiohttp.ClientConnectionError,TypeError):
                        pass
        return "Solicitud de apagado enviada. El panel comprobará de nuevo el estado."
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("No se ha podido confirmar el envío del apagado. Comprueba la TV y vuelve a intentarlo.") from error
