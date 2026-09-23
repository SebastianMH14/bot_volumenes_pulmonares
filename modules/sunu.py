"""
Automatización web de Sunu (Selenium) para volúmenes pulmonares.

Adaptado de bot_espirometrias/modules/nube.py y subir_sunu.py, que ya están
probados en producción (login, búsqueda global de pacientes, modal de adjuntos).
Lo que cambia es la pestaña del perfil: Volúmenes Pulmonares en vez de
Espirometría. Sus selectores se configuran en config.py (SEL_TAB_VOLUMENES,
SEL_CONTENEDOR_VOLUMENES) y están PENDIENTES de confirmar con explorar_sunu.py.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config

logger = logging.getLogger("bot_volumenes")

URL_PACIENTES = config.URL_NUBE.rstrip("/") + "/pacientes"


def diagnostico(driver: WebDriver, tag: str) -> None:
    """Guarda screenshot + HTML en debug/ (contienen datos de pacientes)."""
    try:
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{tag}"
        driver.save_screenshot(os.path.join(config.DEBUG_DIR, f"{name}.png"))
        with open(os.path.join(config.DEBUG_DIR, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info("Debug guardado: %s", name)
    except Exception:
        pass


# ── Sesión ──────────────────────────────────────────────────

def init_browser() -> WebDriver:
    opts = webdriver.ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    return webdriver.Chrome(options=opts)


def login(driver: WebDriver) -> WebDriver:
    driver.get(config.URL_NUBE)
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='email']"))
    ).send_keys(config.USUARIO)
    driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(config.PASSWORD)
    driver.find_element(By.XPATH, "//button[contains(text(), 'Ingresar')]").click()
    WebDriverWait(driver, 15).until(
        lambda d: "login" not in d.current_url.lower() and "auth" not in d.current_url.lower()
    )
    logger.info("Login exitoso - %s", driver.current_url)
    return driver


def driver_vivo(driver: WebDriver) -> bool:
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


# ── Perfil del paciente ─────────────────────────────────────

def abrir_paciente(driver: WebDriver, wait: WebDriverWait, cedula: str) -> None:
    """Busca por cédula con el buscador global de /pacientes y abre el perfil.

    Raises:
        TimeoutException: si el paciente no aparece.
    """
    driver.get(URL_PACIENTES)
    cedula_num = re.sub(r"[^\d]", "", cedula)

    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.pgs__trigger"))).click()
    wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "input.pgs__input"))
    ).send_keys(cedula_num)

    # Estado terminal real: hay resultados o el widget dice explícitamente que no hay
    wait.until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "#patient-global-search-list button.pgs__row")
        or "No encontramos" in d.find_element(By.ID, "patient-global-search-list").text
    )

    resultado = None
    for r in driver.find_elements(By.CSS_SELECTOR, "#patient-global-search-list button.pgs__row"):
        try:
            doc_text = r.find_element(By.CSS_SELECTOR, ".pgs__row-document").text
        except NoSuchElementException:
            continue
        if re.sub(r"[^\d]", "", doc_text) == cedula_num:
            resultado = r
            break
    if resultado is None:
        raise TimeoutException(f"Paciente {cedula_num} no encontrado en búsqueda global de Sunu")

    resultado.click()
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.pgs__open-profile"))).click()
    wait.until(EC.presence_of_element_located((By.XPATH, "//a[@href='#tab-citas']")))
    logger.debug("Perfil del paciente %s cargado", cedula_num)


def abrir_pestania_volumenes(driver: WebDriver, wait: WebDriverWait) -> None:
    tab = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, config.SEL_TAB_VOLUMENES)))
    driver.execute_script("arguments[0].click();", tab)


def buscar_fila_por_fecha(driver: WebDriver, wait: WebDriverWait, fecha: date) -> WebElement | None:
    """Fila de la tabla de volúmenes cuya primera celda es la fecha (DD/MM/AAAA).

    Todos los selectores se anclan al contenedor de la pestaña: en Sunu el id
    "table" se repite en varias pestañas del perfil.
    """
    cont = config.SEL_CONTENEDOR_VOLUMENES
    fecha_str = fecha.strftime("%d/%m/%Y")
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"{cont} table tbody")))
    except TimeoutException:
        logger.warning("No se encontró la tabla de volúmenes pulmonares")
        return None

    for _ in range(20):  # páginas del DataTable
        for fila in driver.find_elements(By.CSS_SELECTOR, f"{cont} table tbody tr"):
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if celdas and celdas[0].text.strip() == fecha_str:
                return fila
        siguiente = driver.find_elements(
            By.CSS_SELECTOR, f"{cont} .paginate_button.next:not(.disabled)"
        )
        if not siguiente:
            break
        driver.execute_script("arguments[0].click();", siguiente[0])
        time.sleep(0.5)
    return None


# ── Modal de adjuntos ───────────────────────────────────────

def _ya_cargado(driver: WebDriver) -> bool:
    """Con un adjunto previo, el modal muestra el visor en vez del input de subida."""
    if driver.find_elements(By.CSS_SELECTOR, "div.adjuntos-formato-proceso, iframe.visorPdfAdjuntoFormato"):
        return True
    try:
        texto = (driver.find_element(By.CSS_SELECTOR, "div.modal-body").text or "").lower()
        if any(i in texto for i in ("ya cargado", "archivo cargado", "adjunto cargado", "cargado anteriormente")):
            return True
    except NoSuchElementException:
        pass
    return False


def _esperar_confirmacion(driver: WebDriver, timeout: int = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        estados = driver.find_elements(By.CSS_SELECTOR, ".estadoSubidaAdjuntoFormato")
        if estados:
            texto = (estados[0].text or "").lower()
            if texto and "error" not in texto:
                return True
        if not driver.find_elements(By.CSS_SELECTOR, "div.modal.in, div.modal.fade.in, div.modal.show"):
            return True
        time.sleep(0.5)
    return False


def cerrar_modal(driver: WebDriver) -> None:
    try:
        for modal in driver.find_elements(By.CSS_SELECTOR, "div.modal.in, div.modal.fade.in, div.modal.show"):
            cerrar = modal.find_elements(By.CSS_SELECTOR, "[data-dismiss='modal'], .close")
            if cerrar:
                driver.execute_script("arguments[0].click();", cerrar[0])
                time.sleep(0.3)
                return
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    except Exception:
        pass


def subir_pdf(driver: WebDriver, wait: WebDriverWait, fila: WebElement, pdf_path: str) -> str:
    """Abre el modal de adjuntos DE ESA FILA y sube el PDF.

    Returns:
        "ok" | "ya_cargado" | "boton_adjuntos_no_encontrado" | "modal_no_abrio" |
        "boton_cargar_no_encontrado" | "sin_confirmacion"
    """
    # El botón se busca dentro de la fila encontrada, no en todo el documento:
    # con varios exámenes (o pestañas) hay varios botones de adjuntos en el DOM.
    botones = fila.find_elements(By.CSS_SELECTOR, "a.btnVerAdjuntosFormato")
    if not botones:
        return "boton_adjuntos_no_encontrado"
    driver.execute_script("arguments[0].click();", botones[0])

    try:
        file_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input.inputAdjuntoFormatoPdf"))
        )
    except TimeoutException:
        if _ya_cargado(driver):
            cerrar_modal(driver)
            return "ya_cargado"
        diagnostico(driver, "modal_no_abrio")
        cerrar_modal(driver)
        return "modal_no_abrio"

    file_input.send_keys(os.path.abspath(pdf_path))

    btn = driver.find_elements(By.CSS_SELECTOR, "button.btnSubirAdjuntoFormato")
    if not btn:
        cerrar_modal(driver)
        return "boton_cargar_no_encontrado"
    btn[0].click()

    if not _esperar_confirmacion(driver):
        diagnostico(driver, "subida_sin_confirmacion")
        cerrar_modal(driver)
        return "sin_confirmacion"

    cerrar_modal(driver)
    return "ok"
