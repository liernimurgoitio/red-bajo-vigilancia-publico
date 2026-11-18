"""Recorte local ligero U²-NetP, aislado del proceso de vigilancia.

Modelo y normalización: github.com/danielgatis/rembg (U2netpSession).
No descarga modelos durante una petición ni envía fotos fuera del equipo.
"""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import threading

MODELO_SHA256 = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
MODELO = Path(__file__).resolve().parent.parent / "modelos" / "u2netp.onnx"
MAX_BYTES = 6_000_000
_BLOQUEO = threading.Lock()


def disponible():
    return MODELO.is_file() and all(importlib.util.find_spec(name) is not None for name in ("onnxruntime","numpy","PIL"))


def recortar(imagen):
    if not disponible():
        raise ValueError("Falta preparar el modelo de recorte automático.")
    if len(imagen) > MAX_BYTES:
        raise ValueError("La foto es demasiado grande.")
    if not _BLOQUEO.acquire(blocking=False):
        raise ValueError("Ya se está preparando otra foto. Espera a que termine y vuelve a guardar.")
    try:
        entorno = dict(os.environ)
        entorno.pop("CREDENTIALS_DIRECTORY",None)
        entorno.update(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
        try:
            resultado = subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),"--procesar"],input=imagen,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,env=entorno,check=False)
        except subprocess.TimeoutExpired as error:
            raise ValueError("El recorte ha tardado demasiado. La foto anterior se conserva; prueba con otra imagen.") from error
        if resultado.returncode != 0:
            aviso = resultado.stderr.decode("utf-8",errors="replace").splitlines()
            texto = next((line[6:] for line in aviso if line.startswith("ERROR:")),"No se ha podido recortar la foto. La foto anterior se conserva.")
            raise ValueError(texto)
        if not resultado.stdout.startswith(b"\x89PNG\r\n\x1a\n") or len(resultado.stdout) > MAX_BYTES:
            raise ValueError("El recorte no ha producido una imagen válida. La foto anterior se conserva.")
        return resultado.stdout
    finally:
        _BLOQUEO.release()


def procesar(imagen):
    if not imagen or len(imagen)>MAX_BYTES:
        raise ValueError("La imagen no tiene un tamaño válido.")
    from PIL import Image, ImageOps
    import numpy as np
    import onnxruntime as ort
    with Image.open(io.BytesIO(imagen)) as original:
        if original.width*original.height>4_000_000:
            raise ValueError("Usa una foto de menor resolución.")
        foto = ImageOps.exif_transpose(original).convert("RGBA")
    foto.thumbnail((800,800),Image.Resampling.LANCZOS)
    alfa_original = foto.getchannel("A")
    # Los PNG ya transparentes conservan su recorte.
    hist = alfa_original.histogram()
    if sum(hist[:16])/(foto.width*foto.height)<0.05:
        if hashlib.sha256(MODELO.read_bytes()).hexdigest()!=MODELO_SHA256:
            raise ValueError("El modelo no supera la verificación. Vuelve a prepararlo.")
        opciones = ort.SessionOptions()
        opciones.intra_op_num_threads = 1
        opciones.inter_op_num_threads = 1
        opciones.enable_cpu_mem_arena = False
        opciones.enable_mem_pattern = False
        opciones.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        session = ort.InferenceSession(str(MODELO),sess_options=opciones,providers=["CPUExecutionProvider"])
        rgb = foto.convert("RGB").resize((320,320),Image.Resampling.LANCZOS)
        datos = np.asarray(rgb,dtype=np.float32)
        datos /= max(float(datos.max()),1e-6)
        datos = (datos-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
        entrada = np.ascontiguousarray(datos.transpose(2,0,1)[None],dtype=np.float32)
        mascara = session.run(None,{session.get_inputs()[0].name:entrada})[0][0,0]
        minimo,maximo = float(mascara.min()),float(mascara.max())
        if not np.isfinite(mascara).all() or maximo-minimo<1e-6:
            raise ValueError("No se ha reconocido el aparato. Prueba con otra foto.")
        mascara = np.clip((mascara-minimo)/(maximo-minimo)*255,0,255).astype(np.uint8)
        alfa = Image.fromarray(mascara).resize(foto.size,Image.Resampling.LANCZOS)
        combinado = (np.asarray(alfa,dtype=np.uint16)*np.asarray(alfa_original,dtype=np.uint16)//255).astype(np.uint8)
        if float((combinado>127).mean())<0.20:
            raise ValueError("El recorte quitaría demasiado aparato. La foto anterior se conserva; usa un fondo que contraste más.")
        foto.putalpha(Image.fromarray(combinado))
    limites = foto.getchannel("A").point(lambda valor:255 if valor>24 else 0).getbbox()
    if limites is None:
        raise ValueError("El recorte está vacío. La foto anterior se conserva.")
    salida = io.BytesIO()
    foto.crop(limites).save(salida,format="PNG")
    return salida.getvalue()


if __name__ == "__main__":
    try:
        if sys.argv[1:] != ["--procesar"]:
            raise ValueError("Este módulo es un proceso auxiliar del panel.")
        if os.name=="posix":
            os.nice(10)
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(65,70))
        salida = procesar(sys.stdin.buffer.read(MAX_BYTES+1))
        sys.stdout.buffer.write(salida)
    except Exception as error:
        mensaje = str(error) if isinstance(error,ValueError) else "No se ha podido preparar la imagen. La foto anterior se conserva."
        print("ERROR:"+mensaje,file=sys.stderr)
        raise SystemExit(1)
