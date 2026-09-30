"""
Diagnóstico: confirma los selectores de la pestaña Volúmenes Pulmonares en Sunu.

Uso:
    python explorar_sunu.py <cedula_de_un_paciente_con_volumenes>

Abre el perfil del paciente, lista todas las pestañas del perfil (texto + href)
y guarda en debug/ el HTML de la pestaña de volúmenes para ajustar
SEL_TAB_VOLUMENES y SEL_CONTENEDOR_VOLUMENES en el .env.
No sube ni modifica nada en Sunu.
"""

import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from modules import sunu
from modules.logger import setup_logger


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    cedula = sys.argv[1]
    logger = setup_logger()

    driver = sunu.init_browser()
    try:
        sunu.login(driver)
        wait = WebDriverWait(driver, 15)
        sunu.abrir_paciente(driver, wait, cedula)

        logger.info("Pestañas del perfil (texto → href):")
        for a in driver.find_elements(By.CSS_SELECTOR, "a[href^='#tab-']"):
            texto = (a.get_attribute("textContent") or "").strip()
            logger.info("  %-35s → %s", texto[:35], a.get_attribute("href").split("#", 1)[-1])

        # En Sunu la pestaña se llama "Volúmenes Pulmonares": comparar sin tildes
        candidatos = [
            a for a in driver.find_elements(By.CSS_SELECTOR, "a[href^='#tab-']")
            if "volumen" in _sin_tildes(a.get_attribute("textContent") or "").lower()
        ]
        if not candidatos:
            logger.warning("No se encontró una pestaña cuyo texto contenga 'volumen'")
            sunu.diagnostico(driver, "explorar_perfil")
            return

        tab = candidatos[0]
        destino = tab.get_attribute("href").split("#", 1)[-1]
        logger.info("Pestaña de volúmenes: a[href='#%s'] (clases: %s)", destino, tab.get_attribute("class"))
        driver.execute_script("arguments[0].click();", tab)

        # La tabla puede cargar después del clic; se espera igual que en el bot
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"#{destino} table tbody")))
        except TimeoutException:
            logger.warning("La pestaña no mostró ninguna tabla en 15 s")

        cont = driver.find_element(By.ID, destino)
        out = Path(config.DEBUG_DIR) / f"{datetime.now():%Y%m%d_%H%M%S}_tab_volumenes.html"
        out.write_text(cont.get_attribute("outerHTML"), encoding="utf-8")
        logger.info("HTML de la pestaña guardado en %s", out)
        logger.info("Filas en la tabla: %d", len(cont.find_elements(By.CSS_SELECTOR, "table tbody tr")))
        logger.info("Botones de adjuntos: %d", len(cont.find_elements(By.CSS_SELECTOR, "a.btnVerAdjuntosFormato")))
        logger.info(
            "Sugerencia para .env:\n  SEL_TAB_VOLUMENES=a[href='#%s']\n  SEL_CONTENEDOR_VOLUMENES=#%s",
            destino, destino,
        )
    finally:
        input("Revisa el navegador y presiona Enter para cerrar…")
        driver.quit()


if __name__ == "__main__":
    main()
