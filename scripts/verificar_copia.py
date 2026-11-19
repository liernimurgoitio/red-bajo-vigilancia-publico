"""Verifica una copia privada y, opcionalmente, la extrae en una carpeta nueva."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tarfile
import tempfile


MAX_TOTAL = 1024 * 1024 * 1024
REQUERIDOS = {
    'proyecto/dispositivos.local.json',
    'credenciales/router-user', 'credenciales/router-password',
    'credenciales/panel-password',
}


def nombre_seguro(nombre):
    ruta = PurePosixPath(nombre)
    return (not ruta.is_absolute() and '\\' not in nombre and ':' not in nombre
            and ruta.as_posix() == nombre
            and all(parte not in ('', '.', '..') for parte in ruta.parts)
            and (nombre == 'manifest.json' or (len(ruta.parts) >= 2
                 and ruta.parts[0] in ('proyecto', 'credenciales'))))


def leer_json(archivo, nombre):
    miembro = archivo.getmember(nombre)
    if miembro.size > 10 * 1024 * 1024:
        raise ValueError('Un documento JSON supera el tamaño permitido.')
    with archivo.extractfile(miembro) as entrada:
        return json.load(entrada)


def verificar_copia(ruta, destino=None):
    """No imprime ni devuelve el contenido de las credenciales."""
    destino = Path(destino).absolute() if destino is not None else None
    if destino is not None and (destino.exists() or destino.is_symlink()):
        raise ValueError('El destino ya existe. Elige una carpeta nueva.')
    with tarfile.open(ruta, 'r:gz') as archivo:
        miembros = archivo.getmembers()
        if not miembros or len(miembros) > 20000:
            raise ValueError('La copia tiene una cantidad de archivos no válida.')
        nombres = [m.name for m in miembros]
        if len(set(nombres)) != len(nombres):
            raise ValueError('La copia contiene nombres repetidos.')
        if any(not m.isfile() or not nombre_seguro(m.name) for m in miembros):
            raise ValueError('La copia contiene rutas o enlaces no permitidos.')
        if any(m.size < 0 for m in miembros) or sum(m.size for m in miembros) > MAX_TOTAL:
            raise ValueError('La copia supera el tamaño permitido.')
        if 'manifest.json' not in nombres:
            raise ValueError('Falta el manifiesto de comprobación.')
        manifiesto = leer_json(archivo, 'manifest.json')
        if not isinstance(manifiesto, dict) or manifiesto.get('formato') != 1:
            raise ValueError('Formato de manifiesto no admitido.')
        sumas = manifiesto.get('sha256')
        if not isinstance(sumas, dict) or set(sumas) != set(nombres) - {'manifest.json'}:
            raise ValueError('Los archivos no coinciden con el manifiesto.')
        if not REQUERIDOS.issubset(sumas):
            raise ValueError('Faltan archivos necesarios de la copia.')
        for nombre, esperado in sumas.items():
            if not isinstance(esperado, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', esperado):
                raise ValueError('Una suma de comprobación no es válida.')
            resumen = hashlib.sha256()
            with archivo.extractfile(nombre) as entrada:
                for bloque in iter(lambda: entrada.read(1024 * 1024), b''):
                    resumen.update(bloque)
            if resumen.hexdigest() != esperado.lower():
                raise ValueError('Un archivo no coincide con su suma de comprobación.')
        inventario = leer_json(archivo, 'proyecto/dispositivos.local.json')
        dispositivos = inventario.get('dispositivos') if isinstance(inventario, dict) else None
        if not isinstance(dispositivos, list) or any(not isinstance(d, dict) or not isinstance(d.get('alias'), str) for d in dispositivos):
            raise ValueError('El inventario no contiene una lista de dispositivos válida.')
        if 'proyecto/tailscale.local.json' in sumas:
            leer_json(archivo, 'proyecto/tailscale.local.json')
        registros = None
        if 'proyecto/historial-red.local.sqlite3' in sumas:
            with tempfile.TemporaryDirectory() as temporal:
                base = Path(temporal) / 'historial.sqlite3'
                with archivo.extractfile('proyecto/historial-red.local.sqlite3') as entrada, base.open('wb') as salida:
                    shutil.copyfileobj(entrada, salida)
                base.chmod(0o600)
                try:
                    with closing(sqlite3.connect(base.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
                        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                            raise ValueError('El historial no supera la comprobación de integridad.')
                        registros = db.execute('SELECT COUNT(*) FROM eventos').fetchone()[0]
                except sqlite3.Error as error:
                    raise ValueError('El historial no se puede leer como una base del proyecto.') from error
        numero_incidencias = None
        if 'proyecto/incidencias.local.sqlite3' in sumas:
            with tempfile.TemporaryDirectory() as temporal:
                base = Path(temporal) / 'incidencias.sqlite3'
                with archivo.extractfile('proyecto/incidencias.local.sqlite3') as entrada, base.open('wb') as salida:
                    shutil.copyfileobj(entrada, salida)
                base.chmod(0o600)
                try:
                    with closing(sqlite3.connect(base.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
                        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                            raise ValueError('Las incidencias no superan la comprobación de integridad.')
                        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                            raise ValueError('La versión de incidencias no es compatible.')
                        db.execute('SELECT id,request_id,payload_hash,title,description,category,priority,status,device_id,device_name,context_json,resolution,created_at,updated_at,version,search_text FROM incidencias LIMIT 0')
                        numero_incidencias = db.execute('SELECT COUNT(*) FROM incidencias').fetchone()[0]
                        db.execute('SELECT COUNT(*) FROM actividad_incidencias').fetchone()
                        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                            raise ValueError('El seguimiento de incidencias tiene referencias inconsistentes.')
                except sqlite3.Error as error:
                    raise ValueError('La base de incidencias no se puede leer.') from error
        # Validar todo antes de crear la carpeta; nunca sobrescribir el panel.
        if destino is not None:
            destino.mkdir(mode=0o700)
            for miembro in miembros:
                salida = destino.joinpath(*PurePosixPath(miembro.name).parts)
                salida.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archivo.extractfile(miembro) as entrada, salida.open('xb') as fichero:
                    salida.chmod(0o600)
                    shutil.copyfileobj(entrada, fichero)
        return {'archivos': len(sumas), 'dispositivos': len(dispositivos), 'registros_historial': registros, 'incidencias': numero_incidencias}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('copia', type=Path)
    parser.add_argument('--extraer', type=Path, help='Carpeta nueva para extraer; nunca debe ser la carpeta del panel activo.')
    argumentos = parser.parse_args()
    try:
        resultado = verificar_copia(argumentos.copia, argumentos.extraer)
    except (OSError, ValueError, tarfile.TarError, EOFError, RecursionError):
        parser.exit(1, 'La copia no ha superado la comprobación o no se ha podido leer o extraer. No uses la carpeta de extracción si ha quedado incompleta.\n')
    print(f"Archivos verificados: {resultado['archivos']}")
    print(f"Aparatos en el inventario: {resultado['dispositivos']}")
    registros = resultado['registros_historial']
    print('Historial: no incluido.' if registros is None else f'Historial íntegro y legible: {registros} registros.')
    if resultado['incidencias'] is not None:
        print(f"Incidencias íntegras y legibles: {resultado['incidencias']}")
    if argumentos.extraer:
        print('Extracción completada en la carpeta nueva. Todavía no se ha iniciado un servidor con estos datos.')
    else:
        print('Comprobación completada. No se ha extraído ni sustituido ningún archivo del panel.')


if __name__ == '__main__':
    main()
