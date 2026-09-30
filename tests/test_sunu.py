"""Confirmación de la carga en el modal de adjuntos (sin navegador ni Sunu)."""

import unittest
from unittest import mock

from selenium.common.exceptions import StaleElementReferenceException

from modules import sunu

SEL_FALLO = ".estadoSubidaAdjuntoFormato.alert-danger"
SEL_SESION = ".estadoSesionAdjuntoFormato:not(.hidden)"


class _Elemento:
    def __init__(self, text: str = ""):
        self.text = text


class _Input:
    """Input del modal: deja de existir (stale) después de `consultas` consultas."""

    def __init__(self, consultas: float):
        self.consultas = consultas

    def is_enabled(self) -> bool:
        if self.consultas <= 0:
            raise StaleElementReferenceException()
        self.consultas -= 1
        return True


class _Driver:
    def __init__(self, por_selector: dict | None = None):
        self.por_selector = por_selector or {}

    def find_elements(self, by, selector):
        return self.por_selector.get(selector, [])


@mock.patch.object(sunu.time, "sleep", lambda s: None)
class TestEsperarConfirmacion(unittest.TestCase):
    def test_ok_cuando_sunu_reemplaza_el_modal(self):
        self.assertTrue(sunu._esperar_confirmacion(_Driver(), _Input(consultas=3), timeout=5))

    def test_subiendo_parte_no_es_confirmacion(self):
        # El estado "Subiendo parte 1 de 3..." sigue visible y el input nunca se reemplaza
        self.assertFalse(sunu._esperar_confirmacion(_Driver(), _Input(consultas=float("inf")), timeout=0.05))

    def test_alerta_roja_es_fallo(self):
        driver = _Driver({SEL_FALLO: [_Elemento("No fue posible cargar el PDF.")]})
        self.assertFalse(sunu._esperar_confirmacion(driver, _Input(consultas=float("inf")), timeout=5))

    def test_aviso_de_sesion_es_fallo(self):
        driver = _Driver({SEL_SESION: [_Elemento("La sesión cambió.")]})
        self.assertFalse(sunu._esperar_confirmacion(driver, _Input(consultas=float("inf")), timeout=5))


class TestYaCargado(unittest.TestCase):
    def test_modal_sin_archivos_no_cuenta(self):
        # El contenedor del modal existe siempre; sin archivo listado ni visor no hay adjunto
        self.assertFalse(sunu._ya_cargado(_Driver({"div.adjuntos-formato-proceso": [_Elemento()]})))

    def test_archivo_listado_o_visor(self):
        self.assertTrue(sunu._ya_cargado(_Driver({sunu.SEL_EVIDENCIA_ADJUNTO: [_Elemento()]})))


if __name__ == "__main__":
    unittest.main()
