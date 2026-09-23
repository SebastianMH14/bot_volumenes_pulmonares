"""
Manejo de la carpeta estándar donde la terapeuta deja los informes.

    CARPETA_ENTRADA/
    ├── *.pdf                  ← pendientes (los deja la terapeuta)
    ├── procesados/AAAA-MM-DD/ ← cargados a Sunu (o ya estaban cargados)
    └── errores/AAAA-MM-DD/    ← ilegibles o agotaron MAX_INTENTOS; revisión manual

El registro (data/registro.json) guarda el estado por hash del archivo, para
no subir dos veces el mismo informe aunque lo vuelvan a copiar a la carpeta.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime
from pathlib import Path


def listar_pdfs(carpeta: str | Path) -> list[Path]:
    """PDFs en la raíz de la carpeta de entrada (no recorre subcarpetas)."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    return sorted(p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def hash_archivo(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def mover(path: str | Path, destino: str | Path, fecha: date | None = None) -> Path:
    """Mueve el archivo a destino/AAAA-MM-DD/ sin sobrescribir otro con el mismo nombre."""
    path = Path(path)
    carpeta = Path(destino) / (fecha or date.today()).isoformat()
    carpeta.mkdir(parents=True, exist_ok=True)

    final = carpeta / path.name
    n = 1
    while final.exists():
        final = carpeta / f"{path.stem}_{n}{path.suffix}"
        n += 1
    shutil.move(str(path), str(final))
    return final


class Registro:
    """Estado persistente por informe, indexado por hash SHA-256 del PDF.

    estados: "subido" | "ya_cargado" | "pendiente" | "error"
    """

    FINALES = {"subido", "ya_cargado"}

    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        self._datos: dict[str, dict] = {}
        if self.ruta.is_file():
            try:
                self._datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # Registro corrupto: se respalda y se arranca de cero. El peor
                # caso es reintentar un informe, que Sunu reporta como ya cargado.
                respaldo = self.ruta.with_suffix(f".corrupto_{datetime.now():%Y%m%d_%H%M%S}.json")
                shutil.copy(self.ruta, respaldo)
                self._datos = {}

    def get(self, h: str) -> dict | None:
        return self._datos.get(h)

    def ya_finalizado(self, h: str) -> bool:
        entrada = self._datos.get(h)
        return bool(entrada) and entrada.get("estado") in self.FINALES

    def intentos(self, h: str) -> int:
        return (self._datos.get(h) or {}).get("intentos", 0)

    def registrar(self, h: str, archivo: str, estado: str, **extra) -> dict:
        entrada = self._datos.setdefault(h, {"intentos": 0})
        entrada.update(extra)
        entrada["archivo"] = archivo
        entrada["estado"] = estado
        entrada["actualizado"] = datetime.now().isoformat(timespec="seconds")
        if estado == "pendiente":
            entrada["intentos"] = entrada.get("intentos", 0) + 1
        self.guardar()
        return entrada

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._datos, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.ruta)
