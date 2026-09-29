"""
Lectura de los informes PDF de volúmenes pulmonares.

El nombre del archivo que genera el equipo NO trae la cédula
(ej. "Nombre apellido_LVM_22092026_110217.pdf"), así que la
identificación del paciente se extrae del contenido del PDF
("Detalles del paciente → ID: 12345678"). La fecha del examen se toma de la
etiqueta de la sesión ("Fecha de la sesión: 22 sep., 2026") y, si no se
encuentra, del nombre del archivo.

Validado el 2026-09-28 con 33 informes reales del consultorio 22.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

MESES = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "set": 9, "septiembre": 9, "setiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}

# Días de la semana abreviados que el equipo antepone a la fecha ("lu 22 sep. 2026")
_DIA_SEMANA = r"(?:(?:lu|ma|mi|ju|vi|sa|do)[a-záéíóú]*\.?\s+)?"

_RE_NUMERICA = re.compile(r"^\s*" + _DIA_SEMANA + r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", re.I)
_RE_ISO = re.compile(r"^\s*" + _DIA_SEMANA + r"(\d{4})-(\d{1,2})-(\d{1,2})\b", re.I)
_RE_TEXTO = re.compile(
    r"^\s*" + _DIA_SEMANA + r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]{3,10})\.?,?\s+(?:de\s+)?(\d{4})\b", re.I
)

_RE_CEDULA = re.compile(
    r"(?:^|[\s|])(?:ID|Identificaci[oó]n|N[uú]mero de documento|Documento|C\.?C\.?)"
    r"\s*(?:del paciente)?\s*[:#]?\s*(\d{5,12})\b",
    re.I | re.M,
)

# "resto" va en lookahead para no consumir una etiqueta "Fecha" que venga
# después en la misma línea (columnas mezcladas).
_RE_ETIQUETA_FECHA = re.compile(r"fecha(?P<etiqueta>[^:\n]{0,25}):?(?=(?P<resto>[^\n]{0,40}))", re.I)
_ETIQUETAS_PREFERIDAS = ("sesi", "examen", "prueba", "estudio")

# Nombre generado por el equipo: ..._LVM_DDMMAAAA_HHMMSS.pdf
_RE_FECHA_NOMBRE = re.compile(r"_(\d{2})(\d{2})(\d{4})_\d{6}")
_RE_FECHA_NOMBRE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


class ErrorLectura(Exception):
    """El PDF no se pudo leer o no trae los datos mínimos (cédula y fecha)."""

    def __init__(self, motivo: str, detalle: str = ""):
        super().__init__(f"{motivo}: {detalle}" if detalle else motivo)
        self.motivo = motivo


@dataclass
class DatosInforme:
    cedula: str
    fecha: date
    fuente_fecha: str  # "contenido" | "nombre_archivo"


def _crear_fecha(anio: int, mes: int, dia: int) -> date | None:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def parse_fecha_es(texto: str) -> date | None:
    """Interpreta una fecha al inicio de `texto` en los formatos usuales en español.

    Acepta "22/09/2026", "22-09-2026", "2026-09-22", "22 sep. 2026",
    "22 de septiembre de 2026" y variantes con día de la semana ("lu 22 sep. 2026").
    """
    m = _RE_ISO.match(texto)
    if m:
        return _crear_fecha(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _RE_NUMERICA.match(texto)
    if m:
        return _crear_fecha(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = _RE_TEXTO.match(texto)
    if m:
        mes = MESES.get(m.group(2).lower().rstrip("."))
        if mes:
            return _crear_fecha(int(m.group(3)), mes, int(m.group(1)))
    return None


def _fecha_plausible(f: date, hoy: date) -> bool:
    """Descarta fechas de nacimiento y fechas futuras: el examen es reciente."""
    return hoy - timedelta(days=365) <= f <= hoy + timedelta(days=1)


def extraer_cedula(texto: str) -> str | None:
    m = _RE_CEDULA.search(texto)
    return m.group(1) if m else None


def extraer_fecha(texto: str, hoy: date | None = None) -> date | None:
    """Fecha del examen según las etiquetas "Fecha ..." del informe.

    Ignora la fecha de nacimiento y prefiere etiquetas de sesión/examen.
    El texto de pdfplumber puede mezclar las dos columnas del informe en una
    misma línea, por eso se evalúa cada etiqueta "Fecha" por separado.
    """
    hoy = hoy or date.today()
    preferidas: list[date] = []
    otras: list[date] = []
    for m in _RE_ETIQUETA_FECHA.finditer(texto):
        etiqueta = m.group("etiqueta").lower()
        if "nac" in etiqueta:
            continue
        # Sin dos puntos ("Fecha 22/09/2026") la fecha queda dentro de "etiqueta"
        f = parse_fecha_es(m.group("resto")) or parse_fecha_es(m.group("etiqueta"))
        if f is None or not _fecha_plausible(f, hoy):
            continue
        (preferidas if any(p in etiqueta for p in _ETIQUETAS_PREFERIDAS) else otras).append(f)
    if preferidas:
        return preferidas[0]
    if otras:
        return otras[0]
    return None


def fecha_desde_nombre(nombre_archivo: str) -> date | None:
    stem = Path(nombre_archivo).stem
    m = _RE_FECHA_NOMBRE.search(stem)
    if m:
        return _crear_fecha(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = _RE_FECHA_NOMBRE_ISO.search(stem)
    if m:
        return _crear_fecha(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def extraer_texto(pdf_path: str | Path) -> str:
    import pdfplumber  # import diferido: los tests de parseo no lo necesitan

    with pdfplumber.open(str(pdf_path)) as pdf:
        # Los datos del paciente están en la primera página.
        # use_text_flow: en el informe el valor de la fecha se dibuja encima de
        # la etiqueta "Fecha de la sesión:" y, ordenando por posición, pdfplumber
        # intercala los caracteres ("Fecha de la2 s2e..."). En el orden del
        # PDF la línea sale limpia.
        return "\n".join((p.extract_text(use_text_flow=True) or "") for p in pdf.pages[:2])


def leer_informe(pdf_path: str | Path, hoy: date | None = None) -> DatosInforme:
    """Extrae cédula y fecha del examen de un informe PDF.

    Raises:
        ErrorLectura: con motivo PDF_ILEGIBLE, SIN_CEDULA o SIN_FECHA.
    """
    pdf_path = Path(pdf_path)
    try:
        texto = extraer_texto(pdf_path)
    except Exception as e:
        raise ErrorLectura("PDF_ILEGIBLE", str(e)) from e

    if not texto.strip():
        # PDF escaneado / imagen: no hay capa de texto
        raise ErrorLectura("PDF_ILEGIBLE", "el PDF no tiene texto extraíble")

    cedula = extraer_cedula(texto)
    if not cedula:
        raise ErrorLectura("SIN_CEDULA", "no se encontró la identificación del paciente")

    fecha = extraer_fecha(texto, hoy)
    if fecha:
        return DatosInforme(cedula, fecha, "contenido")

    fecha = fecha_desde_nombre(pdf_path.name)
    if fecha:
        return DatosInforme(cedula, fecha, "nombre_archivo")

    raise ErrorLectura("SIN_FECHA", "no se encontró la fecha del examen")
