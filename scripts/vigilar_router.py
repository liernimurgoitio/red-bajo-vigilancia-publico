"""Panel local alimentado por la lista de dispositivos del router Sagemcom."""

import argparse
import base64
import binascii
import hmac
import asyncio
import getpass
import hashlib
import json
import logging
import os
import signal
import re
import secrets
import socket
import sqlite3
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote

from inventario_panel import AlmacenInventario, ConflictoInventario, recorte_disponible
from estado_tv import consultar_estado, enviar_encendido, enviar_apagado
from historial_red import HistorialRed
from incidencias import Incidencias, ConflictoIncidencia, IncidenciaNoExiste

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import ApiMode, EncryptionMethod
from sagemcom_api.exceptions import (
    AuthenticationException,
    LoginRetryErrorException,
    MaximumSessionCountException,
    UnauthorizedException,
)


RAIZ = Path(__file__).resolve().parent.parent


def hora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def mac_normalizada(valor):
    return str(valor or "").replace(":", "").replace("-", "").upper()


def observar_cambio(observaciones, identificador, estado, fecha):
    if estado not in ("conectado", "desconectado"):
        observaciones.pop(identificador, None)
        return None
    anterior = observaciones.get(identificador)
    if anterior is None:
        observaciones[identificador] = {"confirmado": estado, "candidato": None, "fecha": fecha, "transicion": None}
        return None
    # Editar un nombre vuelve a preparar la misma lectura: no cuenta como otra consulta.
    if anterior["fecha"] == fecha:
        return anterior["transicion"]
    anterior["fecha"] = fecha
    if estado == anterior["confirmado"]:
        anterior.update(candidato=None, transicion=None)
    elif estado == anterior["candidato"]:
        anterior.update(confirmado=estado, candidato=None, transicion=None)
    else:
        anterior.update(candidato=estado, transicion="conexion_por_confirmar" if estado == "conectado" else "desconexion_por_confirmar")
    return anterior["transicion"]


def preparar_equipos(equipos, configurados, router, ip_pc, vistos, fecha, objetivos=None, detalles=None, observaciones=None):
    registros = []
    for equipo in equipos:
        identidad = str(equipo.phys_address or equipo.uid or equipo.ip_address or "")
        if not identidad:
            continue
        identificador = hashlib.sha256(identidad.upper().encode()).hexdigest()[:16]
        conexion = str(equipo.interface_type or "Sin especificar")
        grupo = "Wi-Fi" if "wifi" in conexion.lower() else "LAN" if "ethernet" in conexion.lower() else "Red"
        alias = f"Equipo {grupo} {identificador[:4].upper()}"
        identificado = False
        documento_id = None
        for configurado in configurados:
            # La identidad guardada tiene prioridad sobre la dirección del servidor.
            if configurado.get("mac"):
                coincide = mac_normalizada(configurado["mac"]) == mac_normalizada(equipo.phys_address)
            elif configurado.get("router_uid"):
                coincide = str(configurado["router_uid"]) == str(equipo.uid)
            elif configurado.get("ip"):
                coincide = configurado["ip"] == equipo.ip_address
            else:
                coincide = os.name == "nt" and configurado.get("detectar") == "este_pc" and equipo.ip_address == ip_pc
            if coincide:
                alias = configurado["alias"]
                identificado = True
                documento_id = configurado.get("panel_id")
                break
        if equipo.active is True:
            estado = "conectado"
            vistos[identificador] = fecha
        elif equipo.active is False:
            estado = "desconectado"
        else:
            estado = "sin_comprobar"
        if objetivos is not None:
            objetivo = {"mac": equipo.phys_address} if equipo.phys_address else {"router_uid": str(equipo.uid)} if equipo.uid is not None else None
            if objetivo is not None:
                objetivos[identificador] = objetivo
        if detalles is not None:
            detalles[identificador] = {"nombre_router": equipo.user_friendly_name or equipo.name or "Sin nombre", "ip": equipo.ip_address or "Sin informar", "mac": equipo.phys_address or "Sin informar"}
        registros.append({
            "id": identificador,
            "documento_id": documento_id,
            "alias": alias,
            "ip": equipo.ip_address or None,
            "identificado": identificado,
            "estado": estado,
            "transicion": observar_cambio(observaciones, identificador, estado, fecha) if observaciones is not None else None,
            "conexion": conexion,
            "ultima_deteccion": vistos.get(identificador),
        })
    # Conservar el último estado aunque el router omita temporalmente un aparato.
    registros.sort(key=lambda registro: (registro["estado"] != "conectado", registro["alias"]))
    inventario = list(registros)
    for configurado in configurados:
        if configurado.get("detectar") == "router" or configurado.get("ip") == router or configurado.get("alias") == "Router principal":
            inventario.append({"id": "router-principal", "documento_id": configurado.get("panel_id"), "alias": configurado["alias"], "identificado": True, "es_router": True, "ip": router, "conexion": "Router", "estado": "conectado", "ultima_deteccion": fecha})
            if objetivos is not None:
                objetivos["router-principal"] = {"detectar": "router"}
    return registros, inventario


def direccion_del_pc(router):
    # La seleccion de ruta de un socket UDP permite consultar la IP local sin enviar datos.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conexion:
        conexion.connect((router, 80))
        return conexion.getsockname()[0]


def leer_ip_tailscale(raiz):
    archivo = raiz / "tailscale.local.json"
    if not archivo.exists():
        return None
    import ipaddress
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        ip = ipaddress.ip_address(datos["ip"])
        if ip.version != 4 or ip not in ipaddress.ip_network("100.64.0.0/10"):
            raise ValueError("Dirección fuera de la red de Tailscale.")
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError("Revisa tailscale.local.json usando preparar_acceso_remoto.py.") from error
    return str(ip)


def ejecutar(opciones, usuario, clave, clave_panel=None):
    panel = RAIZ / "panel-ssh.html"
    if not panel.is_file():
        raise ValueError("Falta panel-ssh.html en la carpeta principal del proyecto.")
    if opciones.red_local and not clave_panel:
        raise ValueError("El acceso por red necesita una contraseña del panel.")
    direccion_panel = direccion_del_pc(opciones.router) if opciones.red_local else "127.0.0.1"
    hosts_panel = {"127.0.0.1:8765", "localhost:8765", direccion_panel + ":8765"}
    ip_tailscale = leer_ip_tailscale(RAIZ) if opciones.red_local else None
    if ip_tailscale:
        hosts_panel.add(ip_tailscale + ":8765")
    sal_panel = secrets.token_bytes(32)
    hash_panel = hashlib.sha256(sal_panel + clave_panel.encode("utf-8")).digest() if clave_panel else None
    clave_panel = None
    intentos_panel = {}
    bloqueo_acceso = threading.Lock()
    almacen = AlmacenInventario(RAIZ)
    contenido, _ = almacen.iniciar()
    intervalo = opciones.intervalo
    if type(intervalo) is not int or not 1 <= intervalo <= 3600:
        raise ValueError("Usa un intervalo de entre 1 y 3600 segundos.")
    historial = HistorialRed(RAIZ / "historial-red.local.sqlite3")
    incidencias = Incidencias(RAIZ / "incidencias.local.sqlite3")
    token = secrets.token_urlsafe(32)
    objetivos, detalles, observaciones = {}, {}, {}
    ultima_lectura = {"equipos": None, "pc": None}
    estados_tv = {}
    asociaciones_tv = {}
    ultimas_ordenes_tv = {}
    bloqueo = threading.Lock()
    detener = threading.Event()
    estado = {"fuente": "router", "intervalo_segundos": intervalo, "ultima_comprobacion": None,
              "comprobando": True, "error": None, "dispositivos": [], "equipos_router": []}

    ultimo_exportado = None

    def exportar_inventario(contenido):
        nonlocal ultimo_exportado
        if contenido == ultimo_exportado:
            return
        try:
            almacen.exportar(contenido)
            ultimo_exportado = json.loads(json.dumps(contenido))
            estado["error_exportacion"] = None
        except (OSError, ValueError) as error:
            estado["error_exportacion"] = "Los datos privados estan guardados, pero falta actualizar inventario-red.md: " + type(error).__name__

    def aplicar_estados_tv():
        for lista in (estado["dispositivos"], estado["equipos_router"]):
            for item in lista:
                if item["id"] in estados_tv:
                    item["estado_tv"] = estados_tv[item["id"]]
                    item["control_tv"] = True

    async def vigilar_televisores():
        while not detener.is_set():
            try:
                with bloqueo:
                    contenido_tv, version_tv = almacen.leer()
                    dispositivos = [dict(item) for item in estado["dispositivos"]]
                    consultas = []
                    guardar_asociacion = False
                    for ip_inicial, ajustes in contenido_tv.get("tv_webos", {}).items():
                        equipo_id = ajustes.get("equipo_id") or asociaciones_tv.get(ip_inicial)
                        equipo = next((item for item in dispositivos if item["id"] == equipo_id), None) if equipo_id else next((item for item in dispositivos if item.get("ip") == ip_inicial), None)
                        if equipo is None:
                            if equipo_id:
                                estados_tv[equipo_id] = "no_disponible"
                            continue
                        equipo_id = equipo["id"]
                        asociaciones_tv[ip_inicial] = equipo_id
                        if not ajustes.get("equipo_id"):
                            ajustes["equipo_id"] = equipo_id
                            guardar_asociacion = True
                        if estados_tv.get(equipo_id) == "requiere_autorizacion":
                            continue
                        estados_tv.setdefault(equipo_id,"consultando")
                        consultas.append((equipo_id,equipo.get("ip"),ajustes.get("client_key")))
                    if guardar_asociacion:
                        almacen.guardar(contenido_tv, version_tv)
                    aplicar_estados_tv()
                for identificador, ip, clave in consultas:
                    resultado = await consultar_estado(ip,clave) if ip and clave else "no_disponible"
                    with bloqueo:
                        estados_tv[identificador] = resultado
                        aplicar_estados_tv()
            except Exception:
                with bloqueo:
                    for identificador in estados_tv:
                        estados_tv[identificador] = "no_disponible"
                    aplicar_estados_tv()
            for _ in range(50):
                if detener.is_set():
                    return
                await asyncio.sleep(0.2)

    def actualizar_listas(equipos, contenido, fecha, pc, vistos):
        objetivos.clear()
        detalles.clear()
        registros, inventario = preparar_equipos(
            equipos, contenido["dispositivos"], opciones.router, pc,
            vistos, fecha, objetivos, detalles, observaciones,
        )
        estado.update(dispositivos=inventario, equipos_router=registros)
        aplicar_estados_tv()
        return registros

    vistos = {}
    exportar_inventario(contenido)

    async def recopilar():
        conectado = False
        try:
            async with SagemcomClient(opciones.router, usuario, clave,
                                      authentication_method=EncryptionMethod.MD5,
                                      api_mode=ApiMode.LEGACY) as cliente:
                try:
                    async with asyncio.timeout(45):
                        await cliente.login()
                    conectado = True
                    ultimo_resumen = None
                    ultimo_log = 0
                    while not detener.is_set():
                        inicio_consulta = time.monotonic()
                        with bloqueo:
                            estado["comprobando"] = True
                        try:
                            async with asyncio.timeout(45):
                                equipos = await cliente.get_hosts()
                            fecha = hora()
                            pc = direccion_del_pc(opciones.router)
                            with bloqueo:
                                contenido, _ = almacen.leer()
                                ultima_lectura.update(equipos=equipos, pc=pc)
                                registros = actualizar_listas(equipos, contenido, fecha, pc, vistos)
                                estado.update(ultima_comprobacion=fecha, error=None)
                                try:
                                    historial.observar(registros,fecha)
                                    estado["error_historial"] = None
                                except (OSError,sqlite3.Error):
                                    estado["error_historial"] = "No se ha podido guardar el historial. Revisa el espacio y los permisos de la carpeta."
                                exportar_inventario(contenido)
                            activos = sum(item["estado"] == "conectado" for item in registros)
                            resumen = (activos,len(registros))
                            if not opciones.servicio or resumen != ultimo_resumen or time.monotonic() - ultimo_log >= 60:
                                print(f"{fecha} | Router: {activos} conectados de {len(registros)} equipos conocidos.", flush=True)
                                ultimo_resumen, ultimo_log = resumen, time.monotonic()
                        except (AuthenticationException, UnauthorizedException, LoginRetryErrorException, MaximumSessionCountException):
                            with bloqueo:
                                estado["error"] = "El acceso requiere revision. Deten la vigilancia y vuelve a iniciarla."
                            print(estado["error"], flush=True)
                            break
                        except Exception as error:
                            with bloqueo:
                                estado["error"] = "Consulta fallida: " + type(error).__name__
                            print(estado["error"], flush=True)
                        finally:
                            with bloqueo:
                                estado["comprobando"] = False
                        # Una sola consulta a la vez; descontar el tiempo empleado en leer.
                        pausa = max(0, intervalo - (time.monotonic() - inicio_consulta))
                        if estado.get("error"):
                            pausa = max(pausa, 5)
                        limite = time.monotonic() + pausa
                        while not detener.is_set() and time.monotonic() < limite:
                            await asyncio.sleep(min(0.2, max(0, limite - time.monotonic())))
                finally:
                    if conectado:
                        try:
                            async with asyncio.timeout(5):
                                await cliente.logout()
                        except Exception:
                            print("No se ha podido confirmar el cierre de la sesion del router.", flush=True)
        except Exception as error:
            with bloqueo:
                estado.update(error="No se ha podido acceder: " + type(error).__name__, comprobando=False)
            print(estado["error"], flush=True)

    def equipos_soporte():
        with bloqueo:
            contenido, _ = almacen.leer()
            equipos = [{"id": item["id"], "name": item["alias"],
                        "state": "sin_informacion" if estado.get("error") else item.get("estado", "sin_comprobar"),
                        "observedAt": estado.get("ultima_comprobacion")}
                       for item in estado["dispositivos"]]
            documentos = {item.get("documento_id") for item in estado["dispositivos"]}
            for item in contenido["dispositivos"]:
                if item.get("panel_id") and item["panel_id"] not in documentos:
                    equipos.append({"id": "inventario-" + item["panel_id"], "name": item["alias"],
                                    "state": "pendiente_asociar", "observedAt": None})
            return equipos

    class Peticion(BaseHTTPRequestHandler):
        def leer_formulario_soporte(self):
            self.connection.settimeout(10)
            try:
                longitud = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("Longitud de formulario no válida.") from error
            if not 0 < longitud <= 32768 or self.headers.get_content_type() != "application/json":
                raise ValueError("El formulario debe ser JSON y no superar 32 KiB.")
            datos = json.loads(self.rfile.read(longitud).decode("utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("Formulario de incidencia no válido.")
            return datos

        def consultar_soporte(self, ruta):
            try:
                if ruta.path == "/api/incidencias/contexto":
                    self.responder({"devices": equipos_soporte(), "token": token, "source": "red-bajo-vigilancia"})
                elif ruta.path == "/api/incidencias":
                    consulta = parse_qs(ruta.query)
                    self.responder(incidencias.listar(consulta.get("q", [""])[0],
                        consulta.get("status", ["all"])[0], consulta.get("priority", ["all"])[0],
                        int(consulta.get("page", ["1"])[0])))
                elif re.fullmatch(r"/api/incidencias/INC-[0-9]{6,12}", ruta.path):
                    self.responder(incidencias.detalle(ruta.path.rsplit("/", 1)[1]))
                else:
                    self.responder({"error": "Ruta de incidencias no encontrada."}, 404)
            except IncidenciaNoExiste as error:
                self.responder({"error": str(error)}, 404)
            except (ValueError, TypeError) as error:
                self.responder({"error": str(error)}, 400)
            except (OSError, sqlite3.Error):
                self.responder({"error": "No se han podido consultar las incidencias. Revisa los permisos y el almacenamiento."}, 500)

        def guardar_soporte(self, ruta):
            if not self.autorizado():
                self.responder({"error": "Actualiza el panel de incidencias antes de guardar."}, 403)
                return
            try:
                datos = self.leer_formulario_soporte()
                if ruta.path == "/api/incidencias/importar-zaintza":
                    resultado = incidencias.importar_zaintza(datos)
                    self.responder(resultado, 200 if resultado.get("importReused") else 201)
                elif ruta.path == "/api/incidencias":
                    equipo = next((item for item in equipos_soporte() if item["id"] == datos.get("deviceId")), None)
                    self.responder(incidencias.crear(datos, equipo), 201)
                elif re.fullmatch(r"/api/incidencias/INC-[0-9]{6,12}", ruta.path):
                    self.responder(incidencias.actualizar(ruta.path.rsplit("/", 1)[1], datos))
                else:
                    self.responder({"error": "Ruta de incidencias no encontrada."}, 404)
            except IncidenciaNoExiste as error:
                self.responder({"error": str(error)}, 404)
            except ConflictoIncidencia as error:
                self.responder({"error": str(error)}, 409)
            except (ValueError, TypeError, UnicodeError) as error:
                self.responder({"error": str(error)}, 400)
            except (OSError, sqlite3.Error):
                self.responder({"error": "No se ha podido guardar la incidencia. Comprueba el almacenamiento y actualiza la bandeja antes de repetir."}, 500)

        def servir_soporte(self, ruta):
            base = (RAIZ / "web" / "laguntza").resolve()
            tipos = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                     ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                     ".ico": "image/x-icon", ".woff2": "font/woff2"}
            try:
                archivo = (base / (unquote(ruta.path[len("/soporte/"):]) or "index.html")).resolve()
                if not archivo.is_relative_to(base) or archivo.suffix not in tipos or not archivo.is_file():
                    raise ValueError("Archivo no válido.")
                self.responder(archivo.read_bytes(), tipo=tipos[archivo.suffix])
            except (ValueError, OSError):
                self.responder({"error": "No se ha encontrado la interfaz de Laguntza IT. Revisa su instalación."}, 404)

        def responder(self, contenido, codigo=200, tipo="application/json; charset=utf-8"):
            datos = json.dumps(contenido, ensure_ascii=False).encode("utf-8") if isinstance(contenido, dict) else contenido
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(datos)

        def destino_valido(self):
            return self.headers.get("Host") in hosts_panel

        def acceso_panel(self):
            if not self.destino_valido():
                self.responder({"error":"Dirección del panel no válida."},403)
                return False
            if hash_panel is None:
                return True
            remoto = self.client_address[0]
            ahora = time.monotonic()
            with bloqueo_acceso:
                fallos, ultimo = intentos_panel.get(remoto,(0,0))
            if fallos >= 5 and ahora - ultimo < 30:
                self.responder({"error":"Demasiados intentos. Espera 30 segundos."},429)
                return False
            correcto = False
            try:
                cabecera = self.headers.get("Authorization", "")
                if cabecera.startswith("Basic ") and len(cabecera) < 2048:
                    usuario_panel, password = base64.b64decode(cabecera[6:],validate=True).decode("utf-8").split(":",1)
                    correcto = usuario_panel == "panel" and hmac.compare_digest(hash_panel, hashlib.sha256(sal_panel + password.encode("utf-8")).digest())
            except (ValueError,UnicodeError,binascii.Error):
                pass
            if correcto:
                with bloqueo_acceso:
                    intentos_panel.pop(remoto,None)
                return True
            if self.headers.get("Authorization"):
                with bloqueo_acceso:
                    if len(intentos_panel) > 1024:
                        intentos_panel.clear()
                    intentos_panel[remoto] = ((fallos if ahora - ultimo < 30 else 0) + 1,ahora)
            datos = b"Introduce el usuario panel y la contrasena del panel."
            self.send_response(401)
            self.send_header("WWW-Authenticate",'Basic realm="Red bajo vigilancia", charset="UTF-8"')
            self.send_header("Content-Type","text/plain; charset=utf-8")
            self.send_header("Content-Length",str(len(datos)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(datos)
            return False

        def autorizado(self):
            origen = self.headers.get("Origin")
            return self.destino_valido() and (not origen or origen == "http://" + self.headers.get("Host")) and secrets.compare_digest(self.headers.get("X-Panel-Token", ""), token)

        def do_GET(self):
            if not self.acceso_panel():
                return
            if not self.destino_valido():
                self.responder({"error": "Direccion local no valida."}, 403)
                return
            ruta = urlsplit(self.path)
            if ruta.path == "/api/incidencias" or ruta.path.startswith("/api/incidencias/"):
                self.consultar_soporte(ruta)
            elif ruta.path == "/soporte":
                self.send_response(302)
                self.send_header("Location", "/soporte/" + ("?" + ruta.query if ruta.query else ""))
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif ruta.path.startswith("/soporte/"):
                self.servir_soporte(ruta)
            elif ruta.path == "/api/estado":
                with bloqueo:
                    respuesta = dict(estado)
                    respuesta["recorte_fotos"] = recorte_disponible()
                    try:
                        contenido, version = almacen.leer()
                        respuesta.update(inventario=almacen.publicos(contenido), version_inventario=version,
                                         edicion_token=token, error_inventario=None)
                    except (OSError, ValueError, KeyError) as error:
                        respuesta.update(inventario=[], error_inventario="Revisa la configuracion privada: " + type(error).__name__)
                self.responder(respuesta)
            elif ruta.path == "/api/historial":
                try:
                    with bloqueo:
                        respuesta = historial.consultar()
                        respuesta["error"] = estado.get("error_historial")
                    self.responder(respuesta)
                except (OSError,sqlite3.Error):
                    self.responder({"error":"No se ha podido leer el historial."},500)
            elif ruta.path == "/api/detalle":
                if not self.autorizado():
                    self.responder({"error": "Recarga el panel para consultar los datos."}, 403)
                    return
                identificador = parse_qs(ruta.query).get("id", [""])[0]
                with bloqueo:
                    detalle = detalles.get(identificador)
                self.responder(detalle or {"error": "No hay datos de reconocimiento para este registro."}, 200 if detalle else 404)
            elif re.fullmatch(r"/fotos-aparatos/[0-9a-f]{64}\.(?:jpg|png)", ruta.path):
                foto = RAIZ / ruta.path.lstrip("/")
                if foto.is_file():
                    self.responder(foto.read_bytes(), tipo="image/png" if foto.suffix == ".png" else "image/jpeg")
                else:
                    self.responder({"error": "Foto no encontrada."}, 404)
            elif ruta.path in ("/", "/panel-ssh.html"):
                self.responder(panel.read_bytes(), tipo="text/html; charset=utf-8")
            else:
                self.responder({"error": "No encontrado."}, 404)

        def controlar_televisor(self):
            if not self.autorizado():
                self.responder({"error":"Recarga el panel antes de usar los botones."},403)
                return
            try:
                longitud = int(self.headers.get("Content-Length","0"))
                if not 0 < longitud <= 2048 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Solicitud de TV no válida.")
                datos = json.loads(self.rfile.read(longitud).decode("utf-8"))
                if not isinstance(datos,dict):
                    raise ValueError("Solicitud de TV no válida.")
                identificador, accion = datos.get("id"), datos.get("accion")
                if not isinstance(identificador,str) or accion not in ("encender","apagar"):
                    raise ValueError("Acción de TV no válida.")
                with bloqueo:
                    contenido,_ = almacen.leer()
                    ajustes = next((cfg for ip,cfg in contenido.get("tv_webos",{}).items() if (cfg.get("equipo_id") or asociaciones_tv.get(ip)) == identificador),None)
                    registro = next((item for item in estado["dispositivos"] if item["id"] == identificador),None)
                    objetivo = objetivos.get(identificador,{})
                    if not ajustes or not ajustes.get("client_key") or not registro:
                        raise ValueError("Este aparato no es una TV vinculada para control.")
                    ahora = time.monotonic()
                    if ahora - ultimas_ordenes_tv.get(identificador,-100) < 4:
                        raise ValueError("Espera unos segundos antes de enviar otra solicitud.")
                    ultimas_ordenes_tv[identificador] = ahora
                    ip, clave, mac = registro.get("ip"), ajustes["client_key"], objetivo.get("mac")
                mensaje = enviar_encendido(mac) if accion == "encender" else asyncio.run(enviar_apagado(ip,clave))
                self.responder({"enviado":True,"mensaje":mensaje})
            except (ValueError,TypeError,KeyError,OSError) as error:
                self.responder({"error":str(error)},400)

        def do_POST(self):
            if not self.acceso_panel():
                return
            ruta = urlsplit(self.path)
            if ruta.path == "/api/incidencias" or ruta.path.startswith("/api/incidencias/"):
                self.guardar_soporte(ruta)
                return
            if urlsplit(self.path).path == "/api/tv":
                self.controlar_televisor()
                return
            if urlsplit(self.path).path != "/api/aparato" or not self.autorizado():
                self.responder({"error": "Recarga el panel antes de guardar."}, 403)
                return
            try:
                longitud = int(self.headers.get("Content-Length", "0"))
                if not 0 < longitud <= 6100000 or self.headers.get_content_type() != "application/json":
                    raise ValueError("La peticion no tiene un formato valido.")
                valores = json.loads(self.rfile.read(longitud).decode("utf-8"))
                if not isinstance(valores, dict):
                    raise ValueError("Revisa los datos del formulario.")
                identificador = valores.get("id")
                if not isinstance(identificador, str):
                    raise ValueError("Falta el aparato seleccionado.")
                with bloqueo:
                    contenido, version = almacen.leer()
                    if valores.get("version") != version:
                        raise ConflictoInventario("El inventario ha cambiado. Cierra y vuelve a abrir el formulario.")
                    documento_actual = None
                    objetivo = objetivos.get(identificador)
                    if identificador.startswith("inventario-"):
                        documento_actual = identificador[len("inventario-"):]
                        if not any(item["panel_id"] == documento_actual for item in contenido["dispositivos"]):
                            raise ConflictoInventario("Esta anotacion ya no existe. Actualiza el panel.")
                    else:
                        registro = next((item for item in estado["dispositivos"] if item.get("id") == identificador), None)
                        if registro is None or objetivo is None:
                            raise ConflictoInventario("Espera a una nueva consulta del router y vuelve a abrir el aparato.")
                        documento_actual = registro.get("documento_id")
                # El procesamiento de fotos no bloquea las consultas ni el panel.
                nuevo = almacen.editar(contenido, objetivo, valores, documento_actual)
                with bloqueo:
                    almacen.guardar(nuevo, version)
                    if ultima_lectura["equipos"] is not None:
                        actualizar_listas(ultima_lectura["equipos"], nuevo, estado["ultima_comprobacion"], ultima_lectura["pc"], vistos)
                    exportar_inventario(nuevo)
                    advertencia = estado.get("error_exportacion")
                self.responder({"guardado": True, "advertencia": advertencia})
            except ConflictoInventario as error:
                self.responder({"error": str(error)}, 409)
            except (ValueError, KeyError, TypeError) as error:
                self.responder({"error": str(error)}, 400)
            except OSError:
                self.responder({"error": "No se ha podido guardar el cambio. Comprueba los permisos y vuelve a cargar el panel."}, 500)

        def log_message(self, formato, *argumentos):
            pass

    class ServidorLocal(ThreadingHTTPServer):
        allow_reuse_address = os.name != "nt"
        allow_reuse_port = False
        daemon_threads = True

        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    def servir_tailscale():
        ultimo_aviso = -1000
        while not detener.is_set():
            try:
                remoto = ServidorLocal((ip_tailscale,8765),Peticion)
            except OSError:
                if time.monotonic()-ultimo_aviso >= 60:
                    print("Esperando a que la dirección privada de Tailscale esté disponible.",flush=True)
                    ultimo_aviso = time.monotonic()
                detener.wait(2)
                continue
            remoto.timeout = 0.5
            print(f"Panel privado Tailscale: http://{ip_tailscale}:8765",flush=True)
            try:
                while not detener.is_set():
                    remoto.handle_request()
            finally:
                remoto.server_close()
            return

    try:
        servidor = ServidorLocal((direccion_panel, 8765), Peticion)
    except OSError as error:
        raise ValueError(
            "La direccion del panel esta ocupada. Deten vigilar_red.py y cualquier "
            "otra vigilancia con Ctrl+C, y vuelve a iniciar vigilar_router.py."
        ) from error
    trabajador = threading.Thread(target=lambda: asyncio.run(recopilar()), daemon=True)
    trabajador.start()
    trabajador_remoto = None
    if ip_tailscale:
        trabajador_remoto = threading.Thread(target=servir_tailscale,daemon=True)
        trabajador_remoto.start()
    trabajador_tv = threading.Thread(target=lambda: asyncio.run(vigilar_televisores()), daemon=True)
    trabajador_tv.start()
    print(f"Abre http://{direccion_panel}:8765. Pulsa Ctrl+C para terminar.", flush=True)
    if opciones.red_local:
        print("Acceso con el usuario panel y la contraseña que has elegido. Red doméstica y Tailscale si está configurado.",flush=True)
    def finalizar_servicio(numero, marco):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,finalizar_servicio)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando la vigilancia y su sesion del router...", flush=True)
    finally:
        detener.set()
        servidor.server_close()
        trabajador.join(timeout=52)
        trabajador_tv.join(timeout=9)
        if trabajador_remoto is not None:
            trabajador_remoto.join(timeout=2)


def leer_credenciales_servicio():
    carpeta = os.environ.get("CREDENTIALS_DIRECTORY")
    if not carpeta:
        raise ValueError("El modo servicio debe iniciarse mediante systemd con las credenciales configuradas.")
    valores = []
    for nombre in ("router-user", "router-password", "panel-password"):
        archivo = Path(carpeta) / nombre
        try:
            contenido = archivo.read_bytes()
            if not contenido or len(contenido) > 1024:
                raise ValueError("Credencial vacía o demasiado larga.")
            valor = contenido.decode("utf-8")
            if "\n" in valor or "\r" in valor:
                raise ValueError("Credencial con formato no válido.")
        except (OSError,UnicodeError,ValueError) as error:
            raise ValueError("Revisa la credencial del servicio: " + nombre) from error
        valores.append(valor)
    usuario, clave, panel = valores
    if not 12 <= len(panel) <= 256 or panel == clave:
        raise ValueError("La contraseña del panel debe tener entre 12 y 256 caracteres y ser distinta de la del router.")
    return usuario, clave, panel


def main():
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--router", default="192.168.1.1")
    argumentos.add_argument("--intervalo", type=int, default=1, help="Segundos entre consultas al router (por defecto: 1).")
    argumentos.add_argument("--red-local",action="store_true",help="Permitir acceso desde la red doméstica con contraseña.")
    argumentos.add_argument("--servicio",action="store_true",help="Leer credenciales privadas de systemd sin preguntas interactivas.")
    opciones = argumentos.parse_args()
    import ipaddress
    direccion = ipaddress.ip_address(opciones.router)
    redes = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if direccion.version != 4 or not any(direccion in ipaddress.ip_network(red) for red in redes):
        argumentos.error("Usa la IPv4 privada del router domestico.")
    logging.getLogger("sagemcom_api").setLevel(logging.CRITICAL)
    if opciones.servicio:
        usuario, clave, clave_panel = leer_credenciales_servicio()
        ejecutar(opciones,usuario,clave,clave_panel)
        return
    usuario = input("Usuario del router [user]: ").strip() or "user"
    clave = getpass.getpass("Contrasena del router: ")
    if not clave:
        raise ValueError("Introduce la contrasena del router.")
    clave_panel = None
    if opciones.red_local:
        print("Elige una contraseña exclusiva para el panel; no reutilices la del router. No se guarda en archivos.")
        clave_panel = getpass.getpass("Nueva contraseña del panel (mínimo 12 caracteres): ")
        if len(clave_panel) < 12 or len(clave_panel) > 256 or clave_panel == clave:
            raise ValueError("Usa una contraseña propia del panel de entre 12 y 256 caracteres, distinta de la del router.")
        if getpass.getpass("Repite la contraseña del panel: ") != clave_panel:
            raise ValueError("Las contraseñas del panel no coinciden.")
    ejecutar(opciones, usuario, clave, clave_panel)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError) as error:
        raise SystemExit("No se ha podido iniciar: " + str(error))
