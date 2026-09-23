"""
Bot Volúmenes Pulmonares — carga los informes PDF de pletismografía a Sunu.

Flujo:
  1. Lectura: toma los PDF de CARPETA_ENTRADA y extrae cédula + fecha del examen.
  2. Carga: por cada informe válido abre el perfil del paciente en Sunu,
     pestaña Volúmenes Pulmonares, ubica la fila de esa fecha y adjunta el PDF.
  3. Reporte: archivo local en data/ y correo diario.
"""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

import config
from modules import sunu
from modules.bandeja import Registro, hash_archivo, listar_pdfs, mover
from modules.circuit_breaker import CircuitBreaker
from modules.lector_pdf import ErrorLectura, leer_informe
from modules.logger import setup_logger
from modules.reporte import construir_cuerpo, enviar_email, guardar_local

TIEMPO_MAXIMO_S = 3600
MAX_REINICIOS_NAVEGADOR = 2


def fase_lectura(logger, registro: Registro, resultados: dict, simular: bool) -> list[dict]:
    """Lee los PDF de la bandeja. Los ilegibles van a errores/ (salvo en simulación)."""
    pdfs = listar_pdfs(config.CARPETA_ENTRADA)
    logger.info("=== LECTURA: %d PDF en %s ===", len(pdfs), config.CARPETA_ENTRADA)
    validos: list[dict] = []

    for pdf in pdfs:
        h = hash_archivo(pdf)

        if registro.ya_finalizado(h):
            logger.info("%s ya fue cargado antes (mismo archivo). Se archiva.", pdf.name)
            previo = registro.get(h)
            resultados["ya_cargados"].append({"archivo": pdf.name, "cedula": previo.get("cedula")})
            if not simular:
                mover(pdf, config.CARPETA_PROCESADOS)
            continue

        try:
            datos = leer_informe(pdf)
        except ErrorLectura as e:
            logger.warning("%s: %s", pdf.name, e)
            resultados["errores"].append({"archivo": pdf.name, "motivo": e.motivo})
            if not simular:
                registro.registrar(h, pdf.name, "error", motivo=e.motivo)
                mover(pdf, config.CARPETA_ERRORES)
            continue

        logger.info(
            "%s → cédula %s, fecha %s (desde %s)",
            pdf.name, datos.cedula, datos.fecha.isoformat(), datos.fuente_fecha,
        )
        validos.append({
            "pdf": pdf, "hash": h, "cedula": datos.cedula,
            "fecha": datos.fecha, "fuente_fecha": datos.fuente_fecha,
        })
    return validos


def _marcar_pendiente(logger, registro: Registro, resultados: dict, item: dict, motivo: str) -> None:
    """Queda en la bandeja para la próxima corrida; tras MAX_INTENTOS pasa a errores/."""
    pdf: Path = item["pdf"]
    entrada = registro.registrar(
        item["hash"], pdf.name, "pendiente",
        cedula=item["cedula"], fecha=item["fecha"].isoformat(), motivo=motivo,
    )
    info = {"archivo": pdf.name, "cedula": item["cedula"], "motivo": motivo}
    if entrada["intentos"] >= config.MAX_INTENTOS:
        registro.registrar(item["hash"], pdf.name, "error", motivo=f"{motivo} (tras {entrada['intentos']} intentos)")
        mover(pdf, config.CARPETA_ERRORES)
        info["motivo"] = f"{motivo} tras {entrada['intentos']} intentos"
        resultados["errores"].append(info)
        logger.warning("%s agotó %d intentos → errores/", pdf.name, entrada["intentos"])
    else:
        resultados["pendientes"].append(info)


def fase_carga(logger, validos: list[dict], registro: Registro, resultados: dict) -> str | None:
    """Sube los informes a Sunu. Retorna un texto de alerta si hubo fallo sistémico."""
    logger.info("=== CARGA A SUNU: %d informes ===", len(validos))
    try:
        driver = sunu.init_browser()
        sunu.login(driver)
    except Exception as e:
        # Fallo de sesión: no se cuenta como intento de ningún informe
        logger.error("No se pudo iniciar sesión en Sunu: %s", e)
        return f"No se pudo iniciar sesión en Sunu ({e}). Ningún informe fue procesado."

    wait = WebDriverWait(driver, 15)
    breaker = CircuitBreaker(umbral=5)
    deadline = time.monotonic() + TIEMPO_MAXIMO_S
    reinicios = 0
    alerta: str | None = None

    for i, item in enumerate(validos, 1):
        if time.monotonic() > deadline:
            alerta = "Tiempo máximo de ejecución alcanzado; los informes restantes quedan para la próxima corrida."
            logger.warning(alerta)
            break

        if not sunu.driver_vivo(driver):
            if reinicios >= MAX_REINICIOS_NAVEGADOR:
                alerta = "El navegador dejó de responder y se agotaron los reinicios."
                logger.error(alerta)
                break
            reinicios += 1
            logger.warning("Navegador sin respuesta. Reiniciando (%d/%d)…", reinicios, MAX_REINICIOS_NAVEGADOR)
            try:
                driver.quit()
            except Exception:
                pass
            try:
                driver = sunu.init_browser()
                sunu.login(driver)
            except Exception as e:
                alerta = f"No se pudo reiniciar el navegador ({e}); los informes restantes quedan para la próxima corrida."
                logger.error(alerta)
                break
            wait = WebDriverWait(driver, 15)

        pdf: Path = item["pdf"]
        cedula = item["cedula"]
        logger.info("[%d/%d] %s - %s", i, len(validos), cedula, pdf.name)
        motivo: str | None = None

        try:
            try:
                sunu.abrir_paciente(driver, wait, cedula)
            except TimeoutException:
                motivo = "PACIENTE_NO_ENCONTRADO"
            else:
                sunu.abrir_pestania_volumenes(driver, wait)
                fila = sunu.buscar_fila_por_fecha(driver, wait, item["fecha"])
                if fila is None:
                    motivo = "FILA_NO_ENCONTRADA"
                else:
                    res = sunu.subir_pdf(driver, wait, fila, str(pdf.resolve()))
                    if res in ("ok", "ya_cargado"):
                        estado = "subido" if res == "ok" else "ya_cargado"
                        registro.registrar(item["hash"], pdf.name, estado,
                                           cedula=cedula, fecha=item["fecha"].isoformat())
                        mover(pdf, config.CARPETA_PROCESADOS)
                        clave = "subidos" if res == "ok" else "ya_cargados"
                        resultados[clave].append({"archivo": pdf.name, "cedula": cedula})
                    else:
                        motivo = res.upper()
        except TimeoutException as e:
            logger.warning("Timeout con %s: %s", cedula, e)
            motivo = "TIMEOUT"
            sunu.cerrar_modal(driver)
            sunu.diagnostico(driver, f"timeout_{cedula}")
        except Exception as e:
            logger.exception("Error inesperado con %s: %s", cedula, e)
            motivo = "ERROR_INESPERADO"
            sunu.cerrar_modal(driver)
            sunu.diagnostico(driver, f"error_{cedula}")

        if motivo:
            logger.warning("%s queda pendiente: %s", pdf.name, motivo)
            _marcar_pendiente(logger, registro, resultados, item, motivo)

        aviso = breaker.registrar(ok=motivo is None, causa=motivo)
        if aviso:
            logger.critical(aviso)
            alerta = aviso
            break

    try:
        driver.quit()
    except Exception:
        pass
    return alerta


def _limpiar_debug_antiguo(logger) -> None:
    limite = time.time() - config.DEBUG_RETENTION_DAYS * 86400
    borrados = 0
    for f in Path(config.DEBUG_DIR).iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < limite:
                f.unlink()
                borrados += 1
        except OSError:
            continue
    if borrados:
        logger.info("Limpieza de debug/: %d archivo(s) eliminados", borrados)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot Volúmenes Pulmonares — carga de informes a Sunu")
    parser.add_argument("--solo-leer", action="store_true",
                        help="Solo lee los PDF y muestra cédula/fecha. No entra a Sunu ni mueve archivos.")
    parser.add_argument("--sin-correo", action="store_true", help="No envía el reporte por correo.")
    args = parser.parse_args()

    logger = setup_logger()
    _limpiar_debug_antiguo(logger)
    logger.info("Instancia: %s - Consultorio %s", config.SEDE_LOCAL, config.CONSULTORIO)

    registro = Registro(config.REGISTRO_FILE)
    resultados = {"subidos": [], "ya_cargados": [], "pendientes": [], "errores": []}

    validos = fase_lectura(logger, registro, resultados, simular=args.solo_leer)

    if args.solo_leer:
        logger.info("=== MODO SOLO LECTURA: %d informes válidos, %d ilegibles ===",
                    len(validos), len(resultados["errores"]))
        return

    if not all([config.USUARIO, config.PASSWORD]):
        logger.error("Faltan USUARIO/PASSWORD de Sunu en el .env")
        return

    alerta = fase_carga(logger, validos, registro, resultados) if validos else None

    fecha = date.today().isoformat()
    cuerpo = construir_cuerpo(resultados, fecha, alerta)
    guardar_local(cuerpo)
    if not args.sin_correo:
        enviar_email(cuerpo, fecha, alerta)
    logger.info("=== FIN ===")


if __name__ == "__main__":
    main()
