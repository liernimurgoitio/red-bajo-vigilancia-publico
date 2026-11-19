"""Instala una compilación de Laguntza IT sin copiar fuentes ni dependencias."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
import uuid


EXTENSIONES = {'.html', '.js', '.css', '.svg', '.png', '.ico', '.woff2'}


def preparar(origen, destino):
    origen, destino = Path(origen).resolve(), Path(destino).absolute()
    if destino.is_symlink() or destino.parent.is_symlink():
        raise ValueError('El destino no puede ser un enlace.')
    destino = destino.resolve()
    if origen == destino or origen.is_relative_to(destino) or destino.is_relative_to(origen):
        raise ValueError('El origen y el destino deben ser carpetas independientes.')
    if not (origen / 'index.html').is_file():
        raise ValueError('Selecciona client/dist después de ejecutar npm run build.')
    archivos = list(origen.rglob('*'))
    if any(p.is_symlink() for p in archivos):
        raise ValueError('La compilación no puede contener enlaces.')
    archivos = [p for p in archivos if p.is_file()]
    if not archivos or any(p.suffix not in EXTENSIONES or any(parte.startswith('.') for parte in p.relative_to(origen).parts) for p in archivos):
        raise ValueError('La compilación contiene archivos que no se deben servir.')
    if sum(p.stat().st_size for p in archivos) > 25 * 1024 * 1024:
        raise ValueError('La compilación supera 25 MiB.')
    indice = (origen / 'index.html').read_text(encoding='utf-8')
    if './assets/' not in indice or not any(p.suffix == '.js' and p.parent.name == 'assets' for p in archivos):
        raise ValueError('Compila con base relativa para servir la interfaz en /soporte/.')
    destino.parent.mkdir(parents=True, exist_ok=True)
    anterior = None
    with tempfile.TemporaryDirectory(prefix='laguntza-preparacion-', dir=destino.parent) as temporal:
        preparado = Path(temporal) / 'interfaz'
        preparado.mkdir()
        for entrada in archivos:
            salida = preparado / entrada.relative_to(origen)
            salida.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(entrada, salida)
        if destino.exists():
            if not destino.is_dir():
                raise ValueError('El destino existente no es una carpeta.')
            sello = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
            anterior = destino.with_name(destino.name + '-anterior-' + sello + '-' + uuid.uuid4().hex[:8])
            destino.rename(anterior)
        try:
            preparado.rename(destino)
        except OSError:
            if anterior is not None:
                anterior.rename(destino)
            raise
    return anterior


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origen', required=True, type=Path, help='Carpeta client/dist de Laguntza IT.')
    parser.add_argument('--destino', type=Path, default=Path(__file__).resolve().parents[1] / 'web/laguntza')
    args = parser.parse_args()
    try:
        anterior = preparar(args.origen, args.destino)
    except (OSError, ValueError) as error:
        parser.exit(1, f'No se ha preparado la interfaz: {error}\n')
    print('Interfaz preparada. El servidor la ofrece en /soporte/.')
    if anterior:
        print('Versión anterior conservada en: ' + str(anterior))


if __name__ == '__main__':
    main()
