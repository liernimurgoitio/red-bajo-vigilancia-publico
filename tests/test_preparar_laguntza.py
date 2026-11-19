from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from preparar_laguntza import preparar


class PreparacionLaguntza(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.origen = self.raiz / 'dist'
        (self.origen / 'assets').mkdir(parents=True)
        (self.origen / 'index.html').write_text('<script src="./assets/app.js"></script>')
        (self.origen / 'assets/app.js').write_text('const version = 1;')
        self.destino = self.raiz / 'web/laguntza'

    def test_instalacion_y_version_anterior_conservada(self):
        self.assertIsNone(preparar(self.origen, self.destino))
        (self.origen / 'assets/app.js').write_text('const version = 2;')
        anterior = preparar(self.origen, self.destino)
        self.assertIn('version = 1', (anterior / 'assets/app.js').read_text())
        self.assertIn('version = 2', (self.destino / 'assets/app.js').read_text())

    def test_archivo_privado_no_modifica_interfaz_instalada(self):
        preparar(self.origen, self.destino)
        (self.origen / '.env').write_text('EJEMPLO=ficticio')
        with self.assertRaises(ValueError):
            preparar(self.origen, self.destino)
        self.assertTrue((self.destino / 'index.html').is_file())
        self.assertFalse((self.destino / '.env').exists())

    def test_no_admite_origen_y_destino_solapados(self):
        with self.assertRaises(ValueError):
            preparar(self.origen, self.origen / 'copia')


if __name__ == '__main__':
    unittest.main()
