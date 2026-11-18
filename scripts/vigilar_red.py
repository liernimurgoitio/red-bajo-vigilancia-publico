"""Vigilancia local de las IP configuradas y panel servido en este PC."""

import ipaddress
import json
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


RAIZ = Path(__file__).resolve().parent.parent
REDES_DOMESTICAS = tuple(ipaddress.ip_network(red) for red in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
))


def ahora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def leer_configuracion(ruta):
    configuracion = json.loads(ruta.read_text(encoding="utf-8-sig"))
    intervalo = configuracion.get("intervalo_segundos", 60)
    if type(intervalo) is not int or not 15 <= intervalo <= 3600:
        raise ValueError("El intervalo debe ser un entero entre 15 y 3600 segundos.")
    dispositivos = configuracion.get("dispositivos", [])
    if not isinstance(dispositivos, list) or not 1 <= len(dispositivos) <= 64:
        raise ValueError("Configura entre 1 y 64 dispositivos.")
    alias_vistos, direcciones_vistas = set(), set()
    resultado = []
    for dispositivo in dispositivos:
        alias = dispositivo.get("alias", "").strip()
        direccion = ipaddress.ip_address(dispositivo.get("ip", ""))
        if not alias or len(alias) > 100:
            raise ValueError("Cada equipo necesita un alias de hasta 100 caracteres.")
        if direccion.version != 4 or not any(direccion in red for red in REDES_DOMESTICAS):
            raise ValueError("Usa direcciones IPv4 privadas de tu red domestica.")
        if alias.casefold() in alias_vistos or str(direccion) in direcciones_vistas:
            raise ValueError("Hay alias o direcciones repetidas en la configuracion.")
        alias_vistos.add(alias.casefold())
        direcciones_vistas.add(str(direccion))
        resultado.append({"alias": alias, "ip": str(direccion)})
    return intervalo, resultado


def comprobar(nmap, dispositivos):
    comando = [nmap, "-sn", "-n", "--host-timeout", "10s", "-oX", "-"]
    comando.extend(dispositivo["ip"] for dispositivo in dispositivos)
    opciones = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
    proceso = subprocess.run(comando, capture_output=True, timeout=45, **opciones)
    if proceso.returncode != 0:
        raise RuntimeError("Nmap no ha podido completar la comprobacion. Revisa Npcap y los permisos.")
    raiz = ET.fromstring(proceso.stdout)
    final = raiz.find("./runstats/finished")
    if final is None or final.get("exit") != "success":
        raise RuntimeError("Nmap ha devuelto una comprobacion incompleta.")
    detectados = set()
    for equipo in raiz.findall("host"):
        estado = equipo.find("status")
        if estado is not None and estado.get("state") == "up":
            for direccion in equipo.findall("address"):
                if direccion.get("addrtype") == "ipv4":
                    detectados.add(direccion.get("addr"))
    return detectados


def ejecutar():
    intervalo, dispositivos = leer_configuracion(RAIZ / "dispositivos.local.json")
    panel = RAIZ / "panel-ssh.html"
    if not panel.is_file():
        raise ValueError("Falta panel-ssh.html en la carpeta principal del proyecto.")
    nmap = shutil.which("nmap")
    if not nmap:
        raise ValueError("No se encuentra Nmap. Comprueba nmap --version en esta terminal.")

    bloqueo = threading.Lock()
    detener = threading.Event()
    estado = {
        "intervalo_segundos": intervalo,
        "ultima_comprobacion": None,
        "comprobando": False,
        "error": None,
        "dispositivos": [
            {"alias": dispositivo["alias"], "estado": "sin_comprobar", "ultima_deteccion": None}
            for dispositivo in dispositivos
        ],
    }

    def vigilar():
        while not detener.is_set():
            with bloqueo:
                estado["comprobando"] = True
            try:
                detectados = comprobar(nmap, dispositivos)
                fecha = ahora()
                with bloqueo:
                    for configurado, observado in zip(dispositivos, estado["dispositivos"]):
                        observado["estado"] = "detectado" if configurado["ip"] in detectados else "sin_respuesta"
                        if observado["estado"] == "detectado":
                            observado["ultima_deteccion"] = fecha
                    estado["ultima_comprobacion"] = fecha
                    estado["error"] = None
                print(f"{fecha} | Detectados: {sum(item['ip'] in detectados for item in dispositivos)}/{len(dispositivos)}", flush=True)
            except (OSError, subprocess.TimeoutExpired, ET.ParseError, RuntimeError) as error:
                with bloqueo:
                    estado["error"] = str(error)
                print("Error de comprobacion: " + str(error), flush=True)
            finally:
                with bloqueo:
                    estado["comprobando"] = False
            detener.wait(intervalo)

    class Peticion(BaseHTTPRequestHandler):
        def do_GET(self):
            # Se sirven exclusivamente el panel y su estado, nunca la configuracion.
            ruta = urlsplit(self.path).path
            if ruta == "/api/estado":
                with bloqueo:
                    contenido = json.dumps(estado, ensure_ascii=False).encode("utf-8")
                tipo = "application/json; charset=utf-8"
            elif ruta in ("/", "/panel-ssh.html"):
                contenido = panel.read_bytes()
                tipo = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(contenido)

        def log_message(self, formato, *argumentos):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 8765), Peticion)
    trabajador = threading.Thread(target=vigilar, daemon=True)
    trabajador.start()
    print("Abre http://127.0.0.1:8765 en este PC.", flush=True)
    print(f"Solo se comprueban los {len(dispositivos)} equipos configurados. Pausa entre rondas: {intervalo} segundos.", flush=True)
    print("Pulsa Ctrl+C para detener la vigilancia.", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nVigilancia detenida.")
    finally:
        detener.set()
        servidor.server_close()
        trabajador.join(timeout=2)


if __name__ == "__main__":
    try:
        ejecutar()
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise SystemExit("No se ha podido iniciar: " + str(error))
