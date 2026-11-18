"""Preparar credenciales privadas del servicio en Linux, fuera del repositorio."""
import getpass
import os
import tempfile
from pathlib import Path


def guardar_secreto(carpeta,nombre,valor):
    descriptor, temporal = tempfile.mkstemp(prefix=".cred-",dir=carpeta)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8",newline="") as archivo:
            archivo.write(valor)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.chmod(temporal,0o600)
        os.replace(temporal,carpeta/nombre)
    finally:
        if os.path.exists(temporal):
            os.unlink(temporal)


def main():
    if os.name != "posix":
        raise SystemExit("Ejecuta este asistente en la Raspberry, no en Windows.")
    carpeta = Path.home()/".config"/"red-vigilancia"
    if carpeta.is_symlink():
        raise SystemExit("La carpeta privada no puede ser un enlace simbólico.")
    usuario = input("Usuario del router [user]: ").strip() or "user"
    clave = getpass.getpass("Contraseña del router: ")
    panel = getpass.getpass("Contraseña del panel (mínimo 12 caracteres): ")
    confirmar = getpass.getpass("Repite la contraseña del panel: ")
    if not clave or len(clave.encode("utf-8")) > 1024:
        raise SystemExit("La contraseña del router no es válida.")
    if not 12 <= len(panel) <= 256 or panel == clave or panel != confirmar:
        raise SystemExit("La contraseña del panel debe coincidir, tener entre 12 y 256 caracteres y ser distinta de la del router.")
    if any("\n" in dato or "\r" in dato for dato in (usuario,clave,panel)):
        raise SystemExit("Los datos deben estar en una sola línea.")
    carpeta.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(carpeta,0o700)
    for nombre,valor in (("router-user",usuario),("router-password",clave),("panel-password",panel)):
        guardar_secreto(carpeta,nombre,valor)
    print("Credenciales guardadas en la carpeta privada de tu usuario, fuera del proyecto.")
    print("La contraseña del panel se conservará al reiniciar. Todavía no se ha activado el servicio.")

if __name__=="__main__":
    main()
