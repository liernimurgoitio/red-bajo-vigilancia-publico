"""Analisis educativo de asociaciones entre dos tipos de eventos SSH."""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path


TIPOS = ("acceso_aceptado", "conexion_sin_completar")


def leer_minutos(ruta, desde, hasta):
    minutos = {}
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        if lector.fieldnames != ["fecha_observada", "tipo_evento"]:
            raise ValueError("El CSV debe tener las columnas fecha_observada,tipo_evento.")

        for numero, fila in enumerate(lector, start=2):
            try:
                fecha = datetime.fromisoformat(fila["fecha_observada"])
                tipo = fila["tipo_evento"]
                if fecha.utcoffset() is None or tipo not in TIPOS or None in fila:
                    raise ValueError("Fecha sin zona horaria o tipo de evento desconocido.")
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"Revisa la fila {numero} del CSV: {error}") from error

            if desde is not None and fecha < desde:
                continue
            if hasta is not None and fecha >= hasta:
                continue

            minuto = fecha.replace(second=0, microsecond=0)
            minutos.setdefault(minuto, set()).add(tipo)

    return minutos


def calcular_reglas(minutos):
    grupos = list(minutos.values())
    total = len(grupos)
    if total == 0:
        return []

    ambos = sum(set(TIPOS).issubset(grupo) for grupo in grupos)
    reglas = []
    for origen, destino in (TIPOS, TIPOS[::-1]):
        con_origen = sum(origen in grupo for grupo in grupos)
        con_destino = sum(destino in grupo for grupo in grupos)
        if ambos == 0:
            continue
        soporte = ambos / total
        confianza = ambos / con_origen
        lift = confianza / (con_destino / total)
        reglas.append({
            "antecedente": origen,
            "consecuente": destino,
            "minutos_observados": total,
            "minutos_con_ambos": ambos,
            "soporte": soporte,
            "confianza": confianza,
            "lift": lift,
        })
    return reglas


def fecha_argumento(texto):
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Usa una fecha como 2026-11-12T17:43:00+01:00.") from error
    if fecha.utcoffset() is None:
        raise argparse.ArgumentTypeError("Incluye la zona horaria, por ejemplo +01:00.")
    return fecha


def main():
    raiz = Path(__file__).resolve().parent.parent
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--csv", type=Path, default=raiz / "datos" / "eventos_ssh.csv")
    argumentos.add_argument("--desde", type=fecha_argumento)
    argumentos.add_argument("--hasta", type=fecha_argumento, help="Limite final excluido.")
    opciones = argumentos.parse_args()
    if opciones.desde and opciones.hasta and opciones.desde >= opciones.hasta:
        argumentos.error("La fecha inicial debe ser anterior a la final.")

    try:
        minutos = leer_minutos(opciones.csv, opciones.desde, opciones.hasta)
        print(f"Minutos con eventos: {len(minutos)}")
        print("Cada minuto cuenta una vez, aunque haya mensajes repetidos.")
        print("Se incluyen solo minutos con eventos, no periodos de silencio.\n")
        for minuto, tipos in sorted(minutos.items()):
            print(f"{minuto.isoformat(timespec='minutes')}: {', '.join(sorted(tipos))}")

        reglas = calcular_reglas(minutos)
        if not reglas:
            print("\nNo hay reglas: hace falta al menos un minuto con ambos eventos.")
            return

        print("\nAsociaciones observadas dentro del mismo minuto:")
        for regla in reglas:
            print(f"\n{regla['antecedente']} -> {regla['consecuente']}")
            print(f"  Soporte: {regla['soporte']:.1%}")
            print(f"  Confianza: {regla['confianza']:.1%}")
            print(f"  Lift: {regla['lift']:.2f}")
        print("\nLa flecha no indica orden temporal ni causa.")
        print("Estos datos de pruebas controladas sirven para aprender el metodo.")
    except (OSError, ValueError, csv.Error) as error:
        print(f"No se pudo completar el analisis: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
