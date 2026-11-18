"""Copia privada del proyecto; SQLite se captura mediante su API de backup."""
import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from contextlib import closing
import tarfile
import tempfile
import time
import uuid


PATRON = re.compile(r"copia-red-\d{8}T\d{6}-[a-f0-9]{8}\.tar\.gz$")


def crear_copia(proyecto, credenciales, destino, conservar=7):
    proyecto, credenciales, destino = map(Path, (proyecto, credenciales, destino))
    if conservar < 1:
        raise ValueError("Debe conservarse al menos una copia.")
    if not proyecto.is_dir():
        raise ValueError("No existe la carpeta del proyecto.")
    destino.mkdir(parents=True, exist_ok=True, mode=0o700)
    destino.chmod(0o700)
    nombre = datetime.now().strftime('copia-red-%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8] + '.tar.gz'
    final = destino / nombre
    parcial = destino / (nombre + '.partial')
    hashes = {}

    def agregar(archivo, nombre_interno, datos):
        ficha = tarfile.TarInfo(nombre_interno)
        ficha.size = len(datos)
        ficha.mode = 0o600
        archivo.addfile(ficha, io.BytesIO(datos))
        hashes[nombre_interno] = hashlib.sha256(datos).hexdigest()

    try:
        # Validar antes de producir una copia que parezca correcta.
        config = (proyecto / 'dispositivos.local.json').read_bytes()
        json.loads(config)
        with tempfile.TemporaryDirectory(dir=destino) as temporal:
            temporal = Path(temporal)
            with parcial.open('xb') as salida:
                parcial.chmod(0o600)
                with tarfile.open(fileobj=salida, mode='w:gz', compresslevel=1) as archivo:
                    agregar(archivo, 'proyecto/dispositivos.local.json', config)
                    candidatos = list(proyecto.glob('*.html')) + list(proyecto.glob('*.md'))
                    candidatos += list(proyecto.glob('requirements*.txt')) + list(proyecto.glob('*.service')) + list(proyecto.glob('*.timer'))
                    candidatos += list((proyecto / 'scripts').glob('*.py'))
                    candidatos += list((proyecto / 'scripts').glob('*.ps1'))
                    candidatos += list((proyecto / 'fotos-aparatos').glob('*'))
                    remoto = proyecto / 'tailscale.local.json'
                    if remoto.exists():
                        json.loads(remoto.read_text(encoding='utf-8'))
                        candidatos.append(remoto)
                    for ruta in sorted(set(candidatos)):
                        if ruta.is_file() and not ruta.is_symlink():
                            agregar(archivo, 'proyecto/' + ruta.relative_to(proyecto).as_posix(), ruta.read_bytes())
                    for nombre_credencial in ('router-user', 'router-password', 'panel-password'):
                        ruta = credenciales / nombre_credencial
                        if ruta.is_symlink():
                            raise ValueError('Las credenciales no deben ser enlaces.')
                        agregar(archivo, 'credenciales/' + nombre_credencial, ruta.read_bytes())
                    base = proyecto / 'historial-red.local.sqlite3'
                    if base.exists():
                        limite = time.monotonic() + 30

                        def progreso(*_):
                            if time.monotonic() > limite:
                                raise TimeoutError('El historial no ha podido copiarse a tiempo.')

                        snapshot = temporal / 'historial.sqlite3'
                        with closing(sqlite3.connect(base.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as origen:
                            with closing(sqlite3.connect(snapshot)) as copia:
                                origen.backup(copia, pages=128, progress=progreso)
                                if copia.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                                    raise ValueError('La copia del historial no supera la comprobación.')
                        agregar(archivo, 'proyecto/historial-red.local.sqlite3', snapshot.read_bytes())
                    manifiesto = json.dumps({'formato': 1, 'sha256': dict(hashes)}, ensure_ascii=False, indent=2).encode()
                    agregar(archivo, 'manifest.json', manifiesto)
                salida.flush()
                import os
                os.fsync(salida.fileno())
            # Releer el archivo completo antes de anunciarlo y rotar copias anteriores.
            with tarfile.open(parcial, 'r:gz') as archivo:
                for nombre_interno, esperado in hashes.items():
                    with archivo.extractfile(nombre_interno) as entrada:
                        if hashlib.sha256(entrada.read()).hexdigest() != esperado:
                            raise ValueError('No coincide la verificación de la copia.')
            parcial.replace(final)
        suma = hashlib.sha256(final.read_bytes()).hexdigest()
        sello = final.with_name(final.name + '.sha256')
        sello.write_text(suma + '  ' + final.name + '\n', encoding='ascii')
        sello.chmod(0o600)
        anteriores = sorted((p for p in destino.iterdir() if PATRON.fullmatch(p.name) and p.is_file() and not p.is_symlink()), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for antigua in anteriores[conservar:]:
            antigua.unlink()
            suma_antigua = antigua.with_name(antigua.name + '.sha256')
            if suma_antigua.is_file() and not suma_antigua.is_symlink():
                suma_antigua.unlink()
        return final
    finally:
        if parcial.exists():
            parcial.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proyecto', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--credenciales', type=Path, default=Path.home() / '.config/red-vigilancia')
    parser.add_argument('--destino', type=Path, default=Path.home() / 'copias-red-vigilancia')
    parser.add_argument('--conservar', type=int, default=7)
    args = parser.parse_args()
    try:
        copia = crear_copia(args.proyecto, args.credenciales, args.destino, args.conservar)
    except (OSError, ValueError, sqlite3.Error, TimeoutError, tarfile.TarError) as error:
        parser.exit(1, f'No se ha completado la copia: {error}\n')
    print(f'Copia privada creada y verificada: {copia}')


if __name__ == '__main__':
    main()
