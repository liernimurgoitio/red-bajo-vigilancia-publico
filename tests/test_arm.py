from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analizar_arm import calcular_reglas, leer_minutos


class Asociaciones(unittest.TestCase):
    def test_muestra_controlada_soporte_confianza_lift(self):
        reglas = calcular_reglas({1: {'acceso_aceptado'}, 2: {'conexion_sin_completar'},
                                 3: {'acceso_aceptado', 'conexion_sin_completar'}})
        self.assertEqual(len(reglas), 2)
        for regla in reglas:
            self.assertAlmostEqual(regla['soporte'], 1 / 3)
            self.assertEqual(regla['confianza'], 0.5)
            self.assertEqual(regla['lift'], 0.75)

    def test_repeticiones_no_duplican_minutos_y_hasta_es_exclusivo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'eventos.csv'
            ruta.write_text('fecha_observada,tipo_evento\n'
                            '2026-11-18T10:00:01+01:00,acceso_aceptado\n'
                            '2026-11-18T10:00:02+01:00,acceso_aceptado\n'
                            '2026-11-18T10:01:00+01:00,conexion_sin_completar\n')
            minutos = leer_minutos(ruta, datetime.fromisoformat('2026-11-18T10:00:00+01:00'),
                                  datetime.fromisoformat('2026-11-18T10:01:00+01:00'))
            self.assertEqual(list(minutos.values()), [{'acceso_aceptado'}])

    def test_sin_coincidencias_no_hay_reglas(self):
        self.assertEqual(calcular_reglas({1: {'conexion_sin_completar'}}), [])


if __name__ == '__main__':
    unittest.main()
