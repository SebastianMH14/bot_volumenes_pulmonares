import unittest
from datetime import date

from modules.lector_pdf import (
    extraer_cedula, extraer_fecha, fecha_desde_nombre, parse_fecha_es,
)

HOY = date(2026, 9, 23)

# Texto con la forma del informe mostrado en el kickoff (datos ficticios).
# pdfplumber mezcla las dos columnas ("Detalles del paciente" | "Detalles de la sesión").
INFORME = """CEMDE
NEUMOLOGIA
Informe de prueba de función pulmonar
Detalles del paciente Detalles de la sesión
ID: 12345678 Fecha de nac.: 05 abr. 1948 Altura: 152 cm Fecha: lu 22 sep. 2026
Nombre de pila: Ana Edad: 78.4 Peso: 64 kg Hora: 11:02 a. m.
Apellido: Perez Gomez Género: Mujer IMC: 27.7 Técnico: Xxxx
"""


class TestParseFecha(unittest.TestCase):
    def test_formatos(self):
        casos = {
            "22/09/2026": date(2026, 9, 22),
            "22-09-2026": date(2026, 9, 22),
            "2026-09-22": date(2026, 9, 22),
            "22 sep. 2026": date(2026, 9, 22),
            "22 sept 2026": date(2026, 9, 22),
            "22 de septiembre de 2026": date(2026, 9, 22),
            "lu 22 sep. 2026": date(2026, 9, 22),
            "lunes 22/09/2026": date(2026, 9, 22),
            "5 abr. 1948": date(1948, 4, 5),
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(parse_fecha_es(texto), esperado)

    def test_invalidas(self):
        for texto in ("31/02/2026", "sin fecha", "22 xyz 2026", ""):
            with self.subTest(texto=texto):
                self.assertIsNone(parse_fecha_es(texto))


class TestExtraccion(unittest.TestCase):
    def test_cedula(self):
        self.assertEqual(extraer_cedula(INFORME), "12345678")

    def test_cedula_variantes(self):
        self.assertEqual(extraer_cedula("Identificación: 1000123456"), "1000123456")
        self.assertEqual(extraer_cedula("C.C. 43123456"), "43123456")
        self.assertIsNone(extraer_cedula("Paciente sin documento"))
        # "ID" dentro de otra palabra no cuenta
        self.assertIsNone(extraer_cedula("VALID 12345678"))

    def test_fecha_ignora_nacimiento_en_linea_mezclada(self):
        self.assertEqual(extraer_fecha(INFORME, HOY), date(2026, 9, 22))

    def test_fecha_prefiere_etiqueta_de_sesion(self):
        texto = "Fecha impresión: 23/09/2026\nFecha de la sesión: 21/09/2026"
        self.assertEqual(extraer_fecha(texto, HOY), date(2026, 9, 21))

    def test_fecha_sin_dos_puntos(self):
        self.assertEqual(extraer_fecha("Fecha 22/09/2026 Hora 11:02", HOY), date(2026, 9, 22))

    def test_fecha_descarta_futuras_y_antiguas(self):
        self.assertIsNone(extraer_fecha("Fecha: 01/01/2030", HOY))
        self.assertIsNone(extraer_fecha("Fecha: 01/01/2020", HOY))

    def test_fecha_desde_nombre(self):
        self.assertEqual(
            fecha_desde_nombre("Ana perez gomez_LVM_22092026_110217.pdf"), date(2026, 9, 22)
        )
        self.assertEqual(fecha_desde_nombre("12345678_2026-09-22.pdf"), date(2026, 9, 22))
        self.assertIsNone(fecha_desde_nombre("informe.pdf"))


if __name__ == "__main__":
    unittest.main()
