"""Utilidades compartidas por todos los colectores.

Estas funciones estaban antes copiadas (con variaciones) en cada colector:
`clean_text`, el parseo de fechas, la detección de duplicados, la detección
de remoto y la sesión HTTP. Aquí hay una sola versión de cada una.
"""

from __future__ import annotations

import difflib
import random
import re
import time
from datetime import datetime

import requests

from jobmatch import config
from jobmatch.models import Job


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def make_session() -> requests.Session:
    """Sesión con keep-alive (reutiliza conexiones = más rápido)."""
    session = requests.Session()
    session.headers.update(config.DEFAULT_HEADERS)
    return session


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def clean_text(text: str | None) -> str:
    """Colapsa espacios en blanco y recorta."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def random_sleep(min_seconds: float, max_seconds: float) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


# ---------------------------------------------------------------------------
# Fechas relativas en español (OCC y Computrabajo)
# ---------------------------------------------------------------------------
_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def parse_days_old_es(text: str | None) -> int:
    """Convierte una fecha relativa en español a días de antigüedad.

    Cubre los formatos de OCC y Computrabajo: 'hace X horas', 'ayer',
    'X días', 'X semanas', 'X meses', 'más de 30 días' y 'DD de MES'.
    Devuelve 999 si no se puede interpretar (así queda fuera del filtro).
    """
    text = (text or "").lower().strip()
    if not text:
        return 999

    if "más de 30" in text or "mas de 30" in text:
        return 31
    if text == "ayer":
        return 1
    if "hora" in text or "minuto" in text or "hoy" in text or "recién" in text:
        return 0

    digits = "".join(c for c in text if c.isdigit())

    if "semana" in text:
        return (int(digits) if digits else 1) * 7
    if "mes" in text:
        return (int(digits) if digits else 1) * 30
    if "día" in text or "dia" in text:
        return int(digits) if digits else 0

    # Formato "DD de MES"
    try:
        parts = text.split(" de ")
        day = int(parts[0].strip())
        month = _MONTHS_ES[parts[1].strip()]
        posted = datetime(datetime.now().year, month, day)
        return max((datetime.now() - posted).days, 0)
    except (ValueError, KeyError, IndexError):
        return 999


# ---------------------------------------------------------------------------
# Detección de remoto
# ---------------------------------------------------------------------------
_REMOTE_KEYWORDS = [
    "en remoto", "remoto", "remote", "trabajo remoto", "empleo remoto",
    "trabajo desde casa", "home office", "100% remoto", "fully remote",
    "work from anywhere",
]


def detect_remote(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in _REMOTE_KEYWORDS)


# ---------------------------------------------------------------------------
# Deduplicación (misma vacante vista dos veces)
# ---------------------------------------------------------------------------
def is_highly_similar(text_a: str, text_b: str, threshold: float = 0.95) -> bool:
    """Similitud rápida con corte previo por longitud (evita comparar textos
    de tamaños muy distintos)."""
    if not text_a or not text_b:
        return False

    length_ratio = min(len(text_a), len(text_b)) / max(len(text_a), len(text_b))
    if length_ratio < 0.8:
        return False

    return difflib.SequenceMatcher(None, text_a, text_b).quick_ratio() >= threshold


def is_duplicate(
    job: Job,
    existing: list[Job],
    title_threshold: float = 0.90,
    desc_threshold: float = 0.95,
) -> bool:
    """True si `job` ya está en `existing` (misma empresa + título y
    descripción muy similares)."""
    company = clean_text(job.company).lower()
    title = clean_text(job.title).lower()
    description = clean_text(job.description).lower()

    for saved in existing:
        if clean_text(saved.company).lower() != company:
            continue
        if not is_highly_similar(clean_text(saved.title).lower(), title, title_threshold):
            continue
        if is_highly_similar(clean_text(saved.description).lower(), description, desc_threshold):
            return True

    return False
