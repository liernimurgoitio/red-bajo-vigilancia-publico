import base64
import hashlib
"""Persistencia del inventario privado y su documento Markdown derivado."""

import copy
import hashlib
import html
import json
import os
import re
import tempfile
import importlib.util
import unicodedata
import uuid
from datetime import date
from pathlib import Path


INICIO = "<!-- inventario-panel:inicio -->"
FIN = "<!-- inventario-panel:fin -->"
CAMPOS = ("alias", "tipo", "conexion", "funcion", "revision")


class ConflictoInventario(ValueError):
    pass


def clave_alias(valor):
    normalizado = unicodedata.normalize("NFD", str(valor).casefold())
    return "".join(letra for letra in normalizado if not unicodedata.combining(letra))


def leer_tabla(texto):
    filas = []
    dentro = False
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea.startswith("|"):
            if dentro and filas:
                break
            continue
        celdas = [html.unescape(celda.strip()) for celda in linea.strip("|").split("|")]
        if not dentro:
            dentro = len(celdas) == 5 and clave_alias(celdas[0]) == "alias"
            continue
        if all(re.fullmatch(r":?-+:?", celda) for celda in celdas):
            continue
        if len(celdas) != 5 or any(not celda for celda in celdas):
            raise ValueError("El inventario existente tiene una fila incompleta. Revisala antes de iniciar.")
        filas.append(dict(zip(CAMPOS, celdas)))
    if not filas:
        raise ValueError("No se ha encontrado la tabla del inventario existente.")
    if len({clave_alias(fila["alias"]) for fila in filas}) != len(filas):
        raise ValueError("El inventario existente tiene nombres repetidos.")
    return filas


def escribir_atomico(ruta, texto):
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=ruta.parent, prefix=".panel-", suffix=".local.tmp",
                                         delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(texto)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()


class AlmacenInventario:
    def __init__(self, raiz):
        self.configuracion = raiz / "dispositivos.local.json"
        self.documento = raiz / "inventario-red.md"

    def leer(self):
        datos = self.configuracion.read_bytes()
        contenido = json.loads(datos.decode("utf-8-sig"))
        if not isinstance(contenido, dict) or not isinstance(contenido.get("dispositivos"), list):
            raise ValueError("Revisa la lista dispositivos de la configuracion privada.")
        for dispositivo in contenido["dispositivos"]:
            if not isinstance(dispositivo, dict) or not isinstance(dispositivo.get("alias"), str):
                raise ValueError("Cada dispositivo necesita un nombre.")
        alias = [clave_alias(item["alias"]) for item in contenido["dispositivos"]]
        if len(set(alias)) != len(alias):
            raise ValueError("Hay nombres repetidos en la configuracion privada.")
        return contenido, hashlib.sha256(datos).hexdigest()

    def guardar(self, contenido, version):
        _, actual = self.leer()
        if actual != version:
            raise ConflictoInventario("Los datos han cambiado. Cierra el formulario y vuelve a abrirlo.")
        texto = json.dumps(contenido, ensure_ascii=False, indent=2) + "\n"
        escribir_atomico(self.configuracion, texto)
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()

    def iniciar(self):
        if not self.configuracion.exists():
            escribir_atomico(self.configuracion, '{"intervalo_segundos":60,"dispositivos":[]}\n')
        contenido, version = self.leer()
        if contenido.get("inventario_panel_version") != 1:
            existentes = leer_tabla(self.documento.read_text(encoding="utf-8-sig")) if self.documento.exists() else []
            configurados = {clave_alias(item["alias"]): item for item in contenido["dispositivos"]}
            for fila in existentes:
                dispositivo = configurados.get(clave_alias(fila["alias"]))
                if dispositivo is None:
                    dispositivo = {"alias": fila["alias"], "pendiente": True}
                    contenido["dispositivos"].append(dispositivo)
                for campo in CAMPOS[1:]:
                    dispositivo.setdefault(campo, fila[campo])
            for dispositivo in contenido["dispositivos"]:
                dispositivo.setdefault("panel_id", "registro-" + uuid.uuid4().hex)
            contenido["inventario_panel_version"] = 1
            self.guardar(contenido, version)
        return self.leer()

    def publicos(self, contenido):
        return [{"id": item["panel_id"], **{campo: item.get(campo, "Pendiente") for campo in CAMPOS},
                 "foto": item.get("foto", ""), "pendiente": bool(item.get("pendiente"))} for item in contenido["dispositivos"]]

    def editar(self, contenido, objetivo, valores, documento_actual=None):
        nuevo = copy.deepcopy(contenido)
        datos = {}
        for campo in CAMPOS:
            valor = valores.get(campo, "")
            if not isinstance(valor, str) or len(valor) > (300 if campo == "funcion" else 100) or any(ord(letra) < 32 for letra in valor):
                raise ValueError("Revisa los campos del formulario. Usa texto en una sola linea.")
            datos[campo] = valor.strip()
        if not datos["alias"]:
            raise ValueError("Escribe un nombre para el aparato.")
        if datos["revision"]:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datos["revision"]):
                    raise ValueError("Formato de fecha no valido.")
                date.fromisoformat(datos["revision"])
            except ValueError as error:
                raise ValueError("Selecciona una fecha de revision valida.") from error
        datos = {campo: valor or "Pendiente" for campo, valor in datos.items()}
        seleccion = valores.get("vincular_id") or documento_actual
        registro = next((item for item in nuevo["dispositivos"] if item["panel_id"] == seleccion), None)
        if seleccion and registro is None:
            raise ConflictoInventario("El aparato documentado ya no existe. Actualiza el formulario.")
        if registro and seleccion != documento_actual and not registro.get("pendiente"):
            raise ValueError("Ese nombre ya esta asociado a otro aparato.")
        if any(clave_alias(item["alias"]) == clave_alias(datos["alias"]) and item is not registro
               and item["panel_id"] != documento_actual for item in nuevo["dispositivos"]):
            raise ValueError("Ya existe ese nombre. Seleccionalo en Aparato ya documentado para asociarlo.")
        if registro is None:
            registro = {"panel_id": "registro-" + uuid.uuid4().hex}
            nuevo["dispositivos"].append(registro)
        if documento_actual and documento_actual != registro["panel_id"]:
            nuevo["dispositivos"] = [item for item in nuevo["dispositivos"] if item["panel_id"] != documento_actual]
        if objetivo is not None:
            for campo in ("mac", "ip", "detectar", "router_uid", "pendiente"):
                registro.pop(campo, None)
            registro.update(objetivo)
        if valores.get("foto_existente") and "foto_data" not in valores:
            foto = valores["foto_existente"]
            permitidas = {item.get("foto") for item in contenido["dispositivos"] if item.get("foto")}
            if not isinstance(foto, str) or not re.fullmatch(r"fotos-aparatos/[0-9a-f]{64}\.(?:jpg|png)", foto) or foto not in permitidas or not (self.documento.parent / foto).is_file():
                raise ValueError("Esa foto ya no está disponible. Vuelve a abrir el aparato.")
            registro["foto"] = foto
        if valores.get("quitar_fondo_actual") and "foto_data" not in valores:
            actual = registro.get("foto", "")
            if not re.fullmatch(r"fotos-aparatos/[0-9a-f]{64}\.(?:jpg|png)", actual):
                raise ValueError("Este aparato no tiene una foto guardada.")
            try:
                imagen_actual = (self.documento.parent / actual).read_bytes()
            except OSError as error:
                raise ValueError("No se ha encontrado la foto guardada.") from error
            valores = dict(valores, foto_data="data:image/png;base64," + base64.b64encode(quitar_fondo_foto(imagen_actual)).decode("ascii"), fondo_listo=True)
        if "foto_data" in valores:
            foto = valores["foto_data"]
            if foto == "":
                registro.pop("foto", None)
            else:
                if not isinstance(foto, str) or not foto.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")) or len(foto) > 6000000:
                    raise ValueError("Selecciona una foto JPG, PNG o WebP de tamaño válido.")
                try:
                    imagen = base64.b64decode(foto.split(",", 1)[1], validate=True)
                except ValueError as error:
                    raise ValueError("La imagen no es válida.") from error
                png = foto.startswith("data:image/png;")
                if png:
                    valido = imagen.startswith(b"\x89PNG\r\n\x1a\n")
                else:
                    valido = imagen.startswith(b"\xff\xd8\xff") and imagen.endswith(b"\xff\xd9")
                if not valido:
                    raise ValueError("La imagen no tiene formato válido.")
                if not valores.get("fondo_listo") and valores.get("quitar_fondo_nueva",True) and recorte_disponible():
                    imagen = quitar_fondo_foto(imagen)
                    png = True
                carpeta = self.documento.parent / "fotos-aparatos"
                carpeta.mkdir(exist_ok=True)
                nombre = hashlib.sha256(imagen).hexdigest() + (".png" if png else ".jpg")
                destino = carpeta / nombre
                if not destino.exists():
                    destino.write_bytes(imagen)
                registro["foto"] = "fotos-aparatos/" + nombre
        registro.update(datos)
        return nuevo

    def exportar(self, contenido):
        def celda(valor):
            return html.escape(str(valor), quote=False).replace("|", "&#124;").replace("\n", " ")

        lineas = [INICIO, "| Alias | Tipo de dispositivo | Conexión | Función | Fecha de revisión |",
                  "| --- | --- | --- | --- | --- |"]
        for dispositivo in contenido["dispositivos"]:
            lineas.append("| " + " | ".join(celda(dispositivo.get(campo, "Pendiente")) for campo in CAMPOS) + " |")
        lineas.append(FIN)
        bloque = "\n".join(lineas)
        original = self.documento.read_text(encoding="utf-8-sig") if self.documento.exists() else "# Inventario de la red doméstica\n\n"
        if INICIO in original and FIN in original:
            inicio, fin = original.index(INICIO), original.index(FIN) + len(FIN)
            texto = original[:inicio] + bloque + original[fin:]
        else:
            lineas_originales = original.splitlines(keepends=True)
            inicio = next((indice for indice, linea in enumerate(lineas_originales)
                           if linea.strip().startswith("|") and clave_alias(linea.strip().strip("|").split("|")[0].strip()) == "alias"), None)
            if inicio is None:
                texto = original.rstrip() + "\n\n" + bloque + "\n"
            else:
                fin = inicio
                while fin < len(lineas_originales) and lineas_originales[fin].strip().startswith("|"):
                    fin += 1
                texto = "".join(lineas_originales[:inicio]) + bloque + "\n" + "".join(lineas_originales[fin:])
        if texto != original:
            escribir_atomico(self.documento, texto)

def recorte_disponible():
    from fondo_ligero import disponible
    return disponible() or (os.name == "nt" and importlib.util.find_spec("rembg") is not None)


_SESION_FONDO = None

def quitar_fondo_foto(imagen):
    """Segmentación local: no envía la fotografía a un servicio externo."""
    from fondo_ligero import disponible, recortar
    if disponible():
        return recortar(imagen)
    global _SESION_FONDO
    try:
        from rembg import new_session, remove
        from PIL import Image
        import io
        if _SESION_FONDO is None:
            _SESION_FONDO = new_session("isnet-general-use", providers=["CPUExecutionProvider"])
        resultado = remove(imagen, session=_SESION_FONDO)
        with Image.open(io.BytesIO(resultado)) as foto:
            foto = foto.convert("RGBA")
            alfa = foto.getchannel("A")
            histograma = alfa.histogram()
            proporcion = sum(histograma[128:]) / (foto.width * foto.height)
            if proporcion < 0.25:
                raise ValueError("El recorte eliminaría demasiado aparato. La foto anterior se conserva. Usa una foto con un fondo que contraste con el aparato.")
            limites = alfa.getbbox()
            if limites is None:
                raise ValueError("No se ha reconocido el aparato. Prueba con otra foto.")
            foto = foto.crop(limites)
            salida = io.BytesIO()
            foto.save(salida, format="PNG")
            return salida.getvalue()
    except ImportError as error:
        raise ValueError("Falta instalar la herramienta para quitar el fondo. Reinicia el programa tras instalar requirements-fotos.txt.") from error
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("No se ha podido quitar el fondo. La foto anterior se conserva. Vuelve a intentarlo.") from error
