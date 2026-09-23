"""Reporte diario: archivo local en data/ + correo (mismo formato que bot_espirometrias)."""

from __future__ import annotations

import logging
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import config

logger = logging.getLogger("bot_volumenes")


def etiqueta_instancia() -> str:
    return f"{config.SEDE_LOCAL} - Consultorio {config.CONSULTORIO}"


def construir_cuerpo(resultados: dict, fecha: str, alerta: str | None = None) -> str:
    """resultados: {"subidos": [...], "ya_cargados": [...], "pendientes": [...], "errores": [...]}.

    Cada item es un dict con al menos "archivo"; "cedula" y "motivo" cuando aplican.
    """
    partes = []
    if alerta:
        partes += [f"*** {alerta} ***", ""]
    partes += [
        f"Sede: {etiqueta_instancia()}",
        f"Fecha de ejecución: {fecha}",
        "",
        "── Volúmenes pulmonares ──",
        f"  Subidos a Sunu:        {len(resultados['subidos'])}",
        f"  Ya estaban cargados:   {len(resultados['ya_cargados'])}",
        f"  Pendientes (reintento): {len(resultados['pendientes'])}",
        f"  Enviados a errores/:   {len(resultados['errores'])}",
    ]
    for titulo, clave in (("Subidos", "subidos"), ("Pendientes", "pendientes"), ("Errores (revisión manual)", "errores")):
        items = resultados[clave]
        if not items:
            continue
        partes += ["", f"── {titulo} ──"]
        for it in items:
            linea = f"  - {it.get('cedula') or 'sin cédula'} | {it['archivo']}"
            if it.get("motivo"):
                linea += f" | {it['motivo']}"
            partes.append(linea)
    return "\n".join(partes)


def guardar_local(cuerpo: str) -> Path:
    path = Path(config.DATA_DIR) / f"reporte_{datetime.now():%Y%m%d_%H%M%S}.txt"
    path.write_text(cuerpo, encoding="utf-8")
    logger.info("Reporte local guardado en %s", path)
    return path


def enviar_email(cuerpo: str, fecha: str, alerta: str | None = None) -> None:
    """Reintenta 3 veces; si no sale, deja copia en data/ para que no se pierda."""
    if not all([config.EMAIL_REMITENTE, config.EMAIL_PASSWORD, config.EMAIL_DESTINATARIOS]):
        logger.warning("Configuración de email incompleta, no se envió reporte")
        return

    asunto = (
        f"{'[ALERTA] ' if alerta else ''}Reporte diario Bot Volúmenes Pulmonares - "
        f"{etiqueta_instancia()} - {fecha}"
    )
    msg = MIMEMultipart()
    msg["From"] = config.EMAIL_REMITENTE
    msg["To"] = config.EMAIL_DESTINATARIOS
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    for intento in range(1, 4):
        try:
            with smtplib.SMTP(config.EMAIL_SMTP_HOST, config.EMAIL_SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(config.EMAIL_REMITENTE, config.EMAIL_PASSWORD)
                server.send_message(msg)
            logger.info("Reporte enviado por correo a %s", config.EMAIL_DESTINATARIOS)
            return
        except Exception as e:
            logger.warning("Intento %d/3 de envío de correo falló: %s", intento, e)
            if intento < 3:
                time.sleep(10 * intento)

    fallback = Path(config.DATA_DIR) / f"EMAIL_NO_ENVIADO_{datetime.now():%Y%m%d_%H%M%S}.txt"
    fallback.write_text(f"Asunto: {asunto}\n\n{cuerpo}", encoding="utf-8")
    logger.error("No se pudo enviar el correo. Copia guardada en %s", fallback)
