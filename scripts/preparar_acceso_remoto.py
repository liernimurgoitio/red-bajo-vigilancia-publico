"""Preparar el acceso privado al panel mediante la IP local de Tailscale."""
import ipaddress
import json
import subprocess
from pathlib import Path
from inventario_panel import escribir_atomico


def main():
    resultado = subprocess.run(["tailscale","ip","-4"],capture_output=True,text=True,timeout=10,check=True)
    ip = ipaddress.ip_address(resultado.stdout.strip())
    if ip.version != 4 or ip not in ipaddress.ip_network("100.64.0.0/10"):
        raise ValueError("Tailscale no ha comunicado una IPv4 válida.")
    raiz = Path(__file__).resolve().parent.parent
    escribir_atomico(raiz/"tailscale.local.json",json.dumps({"ip":str(ip)},ensure_ascii=False,indent=2)+"\n")
    print("Acceso privado preparado. Reinicia el servicio para activarlo.")
    print(f"Dirección del panel mediante Tailscale: http://{ip}:8765")
    print("Se conserva la contraseña del panel y el acceso desde la red doméstica.")

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("No se ha podido preparar el acceso:",type(error).__name__)
        raise SystemExit(1)
