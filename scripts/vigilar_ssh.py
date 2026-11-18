import csv
import sys
from datetime import datetime
from pathlib import Path

archivo_csv = Path(__file__).resolve().parent / "eventos_ssh.csv"

try:
    with archivo_csv.open("a", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)

        if archivo.tell() == 0:
            escritor.writerow(["fecha_observada", "tipo_evento"])
            archivo.flush()

        print(f"Guardando eventos en: {archivo_csv}", flush=True)
        print("Pulsa Ctrl+C para terminar.", flush=True)

        for linea in sys.stdin:
            if "Accepted publickey" in linea:
                tipo_evento = "acceso_aceptado"
                aviso = "ACCESO ACEPTADO"

            elif "[preauth]" in linea:
                tipo_evento = "conexion_sin_completar"
                aviso = "CONEXIÓN SIN COMPLETAR"

            else:
                continue

            fecha = datetime.now().astimezone().isoformat(timespec="seconds")
            escritor.writerow([fecha, tipo_evento])
            archivo.flush()

            print(f"{fecha} | {aviso}", flush=True)

except KeyboardInterrupt:
    print("\nVigilancia terminada.", flush=True)

except OSError as error:
    print(f"No se pudo guardar el archivo: {error}", file=sys.stderr)
    sys.exit(1)
