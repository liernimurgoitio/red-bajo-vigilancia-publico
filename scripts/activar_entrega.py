"""Activa una entrega local revisada; conserva código, interfaz y base anterior."""
from contextlib import closing
from datetime import datetime
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid


SERVICIO = 'red-vigilancia.service'
COPIA_SERVICIO = 'red-vigilancia-backup.service'
TEMPORIZADOR = 'red-vigilancia-backup.timer'
NOMBRE_BASE = 'incidencias.local.sqlite3'
ARCHIVOS = frozenset({
    'panel-ssh.html', 'scripts/incidencias.py', 'scripts/intercambio_zaintza.py',
    'scripts/preparar_laguntza.py', 'scripts/vigilar_router.py', 'scripts/copias_seguridad.py',
    'scripts/verificar_copia.py', 'README.md', 'integracion-laguntza.md',
    'intercambio-zaintza.md', 'hoja-ruta-zaintza.md', 'copias-seguridad.md', 'pruebas-automaticas.md',
})
TIPOS_WEB = {'.html', '.js', '.css', '.svg', '.png', '.ico', '.woff2'}


def ejecutar(*comando):
    subprocess.run(comando, check=True, timeout=180)


def activo(unidad):
    return subprocess.run(['systemctl', 'is-active', '--quiet', unidad], timeout=15).returncode == 0


def cargar(entrega, nombre):
    spec = importlib.util.spec_from_file_location('entrega_' + nombre, entrega / 'archivos/scripts' / (nombre + '.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def validar(entrega, proyecto):
    manifiesto = json.loads((entrega / 'manifest.json').read_text(encoding='utf-8'))
    if manifiesto.get('formato') != 1 or not isinstance(manifiesto.get('sha256'), dict):
        raise ValueError('Manifiesto no compatible.')
    sumas = manifiesto['sha256']
    nombres = set()
    for carpeta in ('archivos', 'interfaz'):
        for archivo in (entrega / carpeta).rglob('*'):
            if archivo.is_symlink():
                raise ValueError('La entrega no puede contener enlaces.')
            if archivo.is_file():
                nombres.add(archivo.relative_to(entrega).as_posix())
    if nombres != set(sumas):
        raise ValueError('Los archivos de la entrega no coinciden con el manifiesto.')
    if {n[len('archivos/'):] for n in nombres if n.startswith('archivos/')} != ARCHIVOS:
        raise ValueError('La selección de archivos no corresponde a esta entrega.')
    for nombre, esperado in sumas.items():
        relativa = PurePosixPath(nombre)
        if (relativa.is_absolute() or '..' in relativa.parts or '\\' in nombre
            or relativa.parts[0] not in ('archivos', 'interfaz')
            or not isinstance(esperado, str) or not re.fullmatch(r'[a-f0-9]{64}', esperado)):
            raise ValueError('Ruta o suma no válida.')
        ruta = entrega.joinpath(*relativa.parts)
        if not ruta.resolve().is_relative_to(entrega) or hashlib.sha256(ruta.read_bytes()).hexdigest() != esperado:
            raise ValueError('Un archivo no coincide con su suma de comprobación.')
        if relativa.parts[0] == 'interfaz' and ruta.suffix not in TIPOS_WEB:
            raise ValueError('La interfaz contiene un archivo que no debe servirse.')
        if nombre.endswith('.py'):
            compile(ruta.read_bytes(), nombre, 'exec')
    indice = (entrega / 'interfaz/index.html').read_text(encoding='utf-8')
    if 'laguntza-mode' in indice or './assets/' not in indice or 'Laguntza IT' not in indice:
        raise ValueError('La interfaz debe ser la compilación privada, sin modo demo fijo.')
    for referencia in re.findall(r'(?:src|href)="(\./[^"?#]+)"', indice):
        if 'interfaz/' + referencia[2:] not in sumas:
            raise ValueError('Falta un archivo al que hace referencia la interfaz.')
    for nombre in [*ARCHIVOS, NOMBRE_BASE, 'web/laguntza']:
        ruta = proyecto / nombre
        if ruta.is_symlink() or not ruta.resolve().is_relative_to(proyecto):
            raise ValueError('El proyecto no puede utilizar rutas enlazadas para esta actualización.')
    if not (proyecto / NOMBRE_BASE).is_file():
        raise ValueError('Falta la base de incidencias existente; no se ha actualizado el panel.')
    return manifiesto


def capturar_base(origen, destino):
    limite = time.monotonic() + 30
    def progreso(*_):
        if time.monotonic() > limite:
            raise TimeoutError('La captura de incidencias no ha terminado a tiempo.')
    with closing(sqlite3.connect(origen.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as entrada:
        with closing(sqlite3.connect(destino)) as salida:
            entrada.backup(salida, pages=128, progress=progreso)
            if salida.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('La captura de incidencias no supera la comprobación de integridad.')
    destino.chmod(0o600)


def comprobar_conservacion(anterior, actual):
    with closing(sqlite3.connect(anterior.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as antes:
        with closing(sqlite3.connect(actual.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as despues:
            if despues.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('La base actual no supera la comprobación de integridad.')
            if despues.execute('PRAGMA user_version').fetchone()[0] != 2:
                raise ValueError('No se ha completado la actualización de la base de incidencias.')
            antes.row_factory = despues.row_factory = sqlite3.Row
            mutables = {'status', 'priority', 'resolution', 'updated_at', 'version'}
            for tabla in ('incidencias', 'actividad_incidencias'):
                for fila in antes.execute('SELECT * FROM ' + tabla):
                    nueva = despues.execute('SELECT * FROM ' + tabla + ' WHERE id=?', (fila['id'],)).fetchone()
                    if nueva is None:
                        raise ValueError('La base actual no conserva todos los registros anteriores.')
                    for columna in fila.keys():
                        if tabla == 'incidencias' and columna in mutables and nueva['version'] > fila['version']:
                            continue  # Una revisión legítima posterior no borra el seguimiento anterior.
                        if nueva[columna] != fila[columna]:
                            raise ValueError('Un registro previo ha cambiado de forma no compatible.')
            return {'incidencias': antes.execute('SELECT COUNT(*) FROM incidencias').fetchone()[0],
                    'actividad': antes.execute('SELECT COUNT(*) FROM actividad_incidencias').fetchone()[0]}


def comprobar_servicio(proyecto, entrega, manifiesto):
    interfaces = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'dev', 'eth0'], text=True))
    ip = next(info['local'] for interfaz in interfaces for info in interfaz['addr_info'] if info['scope'] == 'global')
    secreto = (Path.home() / '.config/red-vigilancia/panel-password').read_text().strip()
    autorizacion = 'Basic ' + base64.b64encode(('panel:' + secreto).encode()).decode()
    ficheros = {n[len('interfaz/'):]: h for n, h in manifiesto['sha256'].items() if n.startswith('interfaz/')}
    limite = time.monotonic() + 45
    while time.monotonic() < limite:
        try:
            for nombre, esperado in ficheros.items():
                ruta = '' if nombre == 'index.html' else nombre
                peticion = urllib.request.Request(f'http://{ip}:8765/soporte/{ruta}', headers={'Authorization': autorizacion})
                with urllib.request.urlopen(peticion, timeout=3) as respuesta:
                    if hashlib.sha256(respuesta.read()).hexdigest() != esperado:
                        raise ValueError('La interfaz servida no coincide con la entrega.')
            peticion = urllib.request.Request(f'http://{ip}:8765/api/incidencias', headers={'Authorization': autorizacion})
            with urllib.request.urlopen(peticion, timeout=3) as respuesta:
                if not isinstance(json.load(respuesta).get('tickets'), list):
                    raise ValueError('La API de incidencias no devuelve el formato esperado.')
            return
        except (OSError, ValueError, KeyError):
            time.sleep(1)
    raise RuntimeError('La interfaz y la API no han superado la comprobación de arranque.')


def copia_nueva(copias, verificar):
    previas = {p.name for p in copias.glob('copia-red-*.tar.gz')}
    ejecutar('sudo', 'systemctl', 'start', COPIA_SERVICIO)
    nuevas = [p for p in copias.glob('copia-red-*.tar.gz') if p.name not in previas and p.is_file() and not p.is_symlink()]
    if not nuevas:
        raise ValueError('No se ha generado una copia nueva. El panel no debe actualizarse sin ella.')
    copia = max(nuevas, key=lambda p: p.stat().st_mtime_ns)
    return copia, verificar(copia)


def restaurar_base(proyecto, reversion):
    # Con el servicio detenido, conservar incluso los cambios de una activación fallida.
    fallida = reversion / 'base-activacion-fallida'
    fallida.mkdir(mode=0o700)
    rutas = [proyecto / (NOMBRE_BASE + sufijo) for sufijo in ('', '-wal', '-shm', '-journal')]
    for ruta in rutas:
        if ruta.is_symlink():
            raise ValueError('No se puede restaurar una base enlazada.')
        if ruta.is_file():
            shutil.copyfile(ruta, fallida / ruta.name)
    for ruta in rutas[1:]:
        if ruta.is_file():
            ruta.unlink()
    temporal = proyecto / ('incidencias-restauracion-' + uuid.uuid4().hex + '.tmp')
    shutil.copyfile(reversion / NOMBRE_BASE, temporal)
    temporal.chmod(0o600)
    temporal.replace(proyecto / NOMBRE_BASE)


def activar(entrega, proyecto, copias):
    if proyecto.is_symlink():
        raise ValueError('La carpeta del proyecto no puede ser un enlace.')
    entrega, proyecto, copias = entrega.resolve(), proyecto.resolve(), copias.resolve()
    manifiesto = validar(entrega, proyecto)
    preparar = cargar(entrega, 'preparar_laguntza').preparar
    verificar = cargar(entrega, 'verificar_copia').verificar_copia
    if not activo(SERVICIO):
        raise ValueError('El panel debe estar activo antes de preparar esta actualización.')
    print('Entrega verificada. Introduce tu contraseña de administración si se solicita.', flush=True)
    ejecutar('sudo', '-v')
    timer_activo = activo(TEMPORIZADOR)
    if timer_activo:
        ejecutar('sudo', 'systemctl', 'stop', TEMPORIZADOR)
    try:
        copia_previa, _ = copia_nueva(copias, verificar)
        reversion = proyecto.parent / ('red-vigilancia-reversion-' + datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
        reversion.mkdir(mode=0o700)
        existentes = set()
        for nombre in ARCHIVOS:
            origen = proyecto / nombre
            if origen.is_file():
                destino = reversion / 'archivos' / nombre
                destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(origen, destino)
                existentes.add(nombre)
        interfaz_anterior = None
        interfaz_cambiada = False
        base_capturada = False
        ejecutar('sudo', 'systemctl', 'stop', SERVICIO)
        try:
            capturar_base(proyecto / NOMBRE_BASE, reversion / NOMBRE_BASE)
            base_capturada = True
            for nombre in ARCHIVOS:
                destino = proyecto / nombre
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(entrega / 'archivos' / nombre, destino)
                destino.chmod(0o600)
            interfaz_anterior = preparar(entrega / 'interfaz', proyecto / 'web/laguntza')
            interfaz_cambiada = True
            ejecutar('sudo', 'systemctl', 'start', SERVICIO)
            comprobar_servicio(proyecto, entrega, manifiesto)
            conservados = comprobar_conservacion(reversion / NOMBRE_BASE, proyecto / NOMBRE_BASE)
        except Exception as error:
            ejecutar('sudo', 'systemctl', 'stop', SERVICIO)
            for nombre in ARCHIVOS:
                destino = proyecto / nombre
                if nombre in existentes:
                    shutil.copyfile(reversion / 'archivos' / nombre, destino)
                elif destino.is_file():
                    destino.unlink()
            if interfaz_cambiada:
                (proyecto / 'web/laguntza').rename(reversion / 'interfaz-activacion-fallida')
                if interfaz_anterior:
                    interfaz_anterior.rename(proyecto / 'web/laguntza')
            if base_capturada:
                restaurar_base(proyecto, reversion)
            ejecutar('sudo', 'systemctl', 'start', SERVICIO)
            raise RuntimeError('La activación ha fallado. Se han recuperado los archivos y la base anteriores. '
                               'Los datos de la activación fallida se conservan en ' + str(reversion)) from error
        try:
            copia_final, resultado = copia_nueva(copias, verificar)
        except Exception as error:
            raise RuntimeError('El panel nuevo sigue activo y conserva los datos, pero la copia final no se ha completado. Revisa el servicio de copias antes de continuar.') from error
        if resultado['incidencias'] is None:
            raise RuntimeError('El panel está actualizado, pero la copia final no incluye incidencias. Revisa las copias antes de continuar.')
        recibo = {'entrega': manifiesto.get('entrega'), 'conservados': conservados,
                  'copia_previa': str(copia_previa), 'copia_final': str(copia_final),
                  'reversion': str(reversion), 'fecha': datetime.now().astimezone().isoformat()}
        (reversion / 'activacion.json').write_text(json.dumps(recibo, indent=2), encoding='utf-8')
        print('Actualización activada: interfaz privada, API y copia de incidencias comprobadas.')
        print(f"Conservados: {conservados['incidencias']} incidencias y {conservados['actividad']} registros anteriores de seguimiento.")
        print('No se han creado incidencias de prueba en tus datos.')
        print('Archivos y base anteriores conservados en: ' + str(reversion))
        return recibo
    finally:
        if timer_activo:
            try:
                ejecutar('sudo', 'systemctl', 'start', TEMPORIZADOR)
            except Exception as error:
                raise RuntimeError('No se ha podido reactivar el temporizador de copias. Revisa red-vigilancia-backup.timer antes de continuar.') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entrega', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--comprobar', action='store_true', help='Validar la entrega y leer la base actual, sin activar cambios ni pedir sudo.')
    args = parser.parse_args()
    usuario = Path.home().resolve()
    if not hasattr(os, 'geteuid') or os.geteuid() == 0 or usuario.name != 'admin-lab':
        parser.exit(1, 'Ejecuta el activador como admin-lab, sin anteponer sudo.\n')
    os.umask(0o077)
    if not args.entrega.resolve().is_relative_to(usuario):
        parser.exit(1, 'La entrega debe estar en una carpeta privada de tu usuario.\n')
    try:
        proyecto = usuario / 'red-bajo-vigilancia'
        if args.comprobar:
            if proyecto.is_symlink():
                raise ValueError('La carpeta del proyecto no puede ser un enlace.')
            validar(args.entrega.resolve(), proyecto.resolve())
            with closing(sqlite3.connect((proyecto / NOMBRE_BASE).resolve().as_uri() + '?mode=ro', uri=True)) as db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version not in (1, 2) or db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise ValueError('La base actual no es compatible o no supera la comprobación.')
            print('Entrega privada verificada y base actual compatible. No se ha activado ningún cambio.')
        else:
            activar(args.entrega, proyecto, Path('/var/lib/red-vigilancia-copias'))
    except Exception as error:
        parser.exit(1, 'No se ha completado la activación: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
