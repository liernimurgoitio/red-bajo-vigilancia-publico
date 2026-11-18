"""Vinculación y consulta de lectura del estado de una LG webOS."""
import asyncio
import json
import argparse
from pathlib import Path
import aiohttp

async def probar(ip, raiz):
    config = raiz / "dispositivos.local.json"
    contenido = json.loads(config.read_text(encoding="utf-8-sig"))
    ajustes = contenido.get("tv_webos", {}).get(ip, {})
    import copy
    from aiopylgtv.handshake import REGISTRATION_PAYLOAD
    payload = copy.deepcopy(REGISTRATION_PAYLOAD)
    payload["forcePairing"] = False
    if ajustes.get("client_key"):
        payload["client-key"] = ajustes["client_key"]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15,connect=5)) as session:
        async with session.ws_connect(f"http://{ip}:3000", timeout=aiohttp.ClientWSTimeout(ws_receive=10)) as ws:
            await ws.send_json({"id":"registro","type":"register","payload":payload})
            print("Consultando con la vinculación guardada…",flush=True)
            while True:
                mensaje = await ws.receive_json()
                if mensaje.get("type") == "error":
                    raise ValueError("La TV no ha aceptado la vinculación: " + str(mensaje.get("error","")))
                if mensaje.get("type") == "registered":
                    clave = mensaje.get("payload",{}).get("client-key")
                    if not clave:
                        raise ValueError("La TV no ha entregado la clave de vinculación.")
                    # Volver a leer para conservar otros cambios del inventario.
                    contenido = json.loads(config.read_text(encoding="utf-8-sig"))
                    contenido.setdefault("tv_webos",{})[ip] = {"client_key":clave}
                    from inventario_panel import escribir_atomico
                    escribir_atomico(config,json.dumps(contenido,ensure_ascii=False,indent=2)+"\n")
                    print("Vinculación guardada en la configuración privada.",flush=True)
                    break
            await ws.send_json({"id":"estado","type":"request","uri":"ssap://com.webos.service.tvpower/power/getPowerState","payload":{}})
            while True:
                mensaje = await asyncio.wait_for(ws.receive_json(),10)
                if mensaje.get("id") == "estado":
                    if mensaje.get("type") == "error":
                        print("La TV no permite consultar este estado:",mensaje.get("error"),flush=True)
                    else:
                        datos = mensaje.get("payload",{})
                        print("Estado comunicado por la TV:", datos.get("state", "Sin informar"),flush=True)
                    return

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip")
    args=parser.parse_args()
    try:
        asyncio.run(probar(args.ip,Path(__file__).resolve().parent.parent))
    except Exception as error:
        print("No se ha completado la prueba:",type(error).__name__,str(error),flush=True)
        raise SystemExit(1)
