"""Preparar el modelo de recorte ligero antes de iniciar el servicio."""
from pathlib import Path
import hashlib
import os
import tempfile
import urllib.request
from fondo_ligero import MODELO,MODELO_SHA256


def main():
    import onnxruntime
    import numpy
    import PIL
    if MODELO.is_file() and hashlib.sha256(MODELO.read_bytes()).hexdigest()==MODELO_SHA256:
        print("Modelo ligero ya preparado y verificado.")
        return
    MODELO.parent.mkdir(parents=True,exist_ok=True)
    print("Descargando el modelo ligero (unos 4,6 MB). No se envían fotografías.",flush=True)
    url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
    descriptor, temporal=tempfile.mkstemp(prefix=".modelo-",dir=MODELO.parent)
    try:
        digest=hashlib.sha256();total=0
        with os.fdopen(descriptor,"wb") as archivo:
            with urllib.request.urlopen(url,timeout=45) as response:
                while True:
                    bloque=response.read(256*1024)
                    if not bloque:break
                    total+=len(bloque)
                    if total>6_000_000:raise ValueError("La descarga supera el tamaño esperado.")
                    digest.update(bloque);archivo.write(bloque)
            archivo.flush();os.fsync(archivo.fileno())
        if digest.hexdigest()!=MODELO_SHA256:
            raise ValueError("El modelo descargado no coincide con el esperado.")
        os.replace(temporal,MODELO)
        print("Modelo ligero preparado y verificado. Ya puedes reiniciar el servicio.")
    finally:
        if os.path.exists(temporal):os.unlink(temporal)

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("No se ha podido preparar el modelo:",type(error).__name__,str(error))
        raise SystemExit(1)
