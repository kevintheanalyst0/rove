"""Configuración central del proyecto.

Todo lo que antes estaba hardcodeado y disperso por decenas de archivos
vive ahora aquí: términos de búsqueda, rutas, parámetros de la IA, pesos
de scoring y perfil de navegador. Si algo hay que ajustar, se ajusta en
un solo sitio.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
DEBUG_DIR = BASE_DIR / "debug"
ASSETS_DIR = BASE_DIR / "assets"
RESUME_DIR = BASE_DIR / "resume"

# Archivos de datos y estado
JOBS_FILE = DATA_DIR / "jobs.json"                    # merge de todas las fuentes
LATEST_JOBS_FILE = DATA_DIR / "latest_jobs.json"      # salida que consume la app
ANALYZED_JOBS_FILE = DATA_DIR / "analyzed_jobs.json"  # caché permanente
BATCHES_FILE = DATA_DIR / "batches.json"              # progreso reanudable
STATUS_FILE = DATA_DIR / "system_status.json"


def source_file(source: str) -> Path:
    """Ruta del JSON de una fuente concreta (p. ej. 'indeed' -> data/indeed_jobs.json)."""
    return DATA_DIR / f"{source}_jobs.json"


# ---------------------------------------------------------------------------
# Búsqueda (única fuente de verdad; antes estaba repetida en 4 colectores)
# ---------------------------------------------------------------------------
# Términos en español: casi todas las búsquedas eran en inglés, lo que hacía
# salir vacantes en inglés que luego se penalizaban por exigir inglés avanzado.
# Buscar en español sesga hacia el mercado local, con menos barrera de idioma.
# (Sin acentos a propósito: los portales normalizan acentos en la búsqueda y
# así la URL no da problemas.)
SEARCH_TERMS = [
    "analista de datos",
    "analista de negocios",
    "analista de inteligencia de negocios",
    "analista bi",
    "analista power bi",
    "analista de reportes",
    "analista de informacion",
    "especialista en datos",
    "analista funcional",
]

# Se descartan vacantes con más de N días de antigüedad.
MAX_DAYS_OLD = 15

# ---------------------------------------------------------------------------
# IA (Gemini)
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# Regla nº 1: máxima velocidad evitando 429.
# - Lotes más grandes = menos llamadas = menos 429 y menos espera total.
# - El ritmo se controla por peticiones/minuto (pacing adaptativo): solo se
#   espera lo justo para no pasarse del límite, en lugar de una pausa fija.
AI_BATCH_SIZE = 30            # vacantes por lote (antes 25)
AI_TOP_JOBS = 500            # solo las N mejores (por matcher) pasan a la IA
AI_REQUESTS_PER_MINUTE = 10  # AJÚSTALO a tu plan de Gemini (free ≈ 10). Súbelo si tu cuota lo permite.
AI_MAX_RETRIES = 3           # reintentos ante 429 por minuto / 503
AI_RETRY_BACKOFF_SECONDS = 30  # espera base ante 429/503 (se duplica en cada reintento)

# Guardar prompts/respuestas en debug/ (antes era un efecto permanente sin control).
SAVE_AI_DEBUG = os.getenv("SAVE_AI_DEBUG", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Scoring por reglas (matcher)
# ---------------------------------------------------------------------------
ROLE_WEIGHTS = {
    "business intelligence": 40,
    "business solutions": 40,
    "reporting analyst": 35,
    "business systems": 30,
    "business analyst": 30,
    "analytics": 25,
    "supply chain": 20,
    "data analyst": 15,
}

SKILL_WEIGHTS = {
    "Power BI": 25,
    "SQL": 25,
    "Reporting": 20,
    "Business Intelligence": 20,
    "Automation": 15,
    "SAP": 15,
    "Tableau": 10,
    "Power Apps": 10,
    "Power Automate": 10,
    "Python": 5,
}

REMOTE_BONUS = 20

# Bonus por recencia: (antigüedad_máxima_en_días, puntos). Se evalúa en orden.
RECENCY_BONUS = [
    (3, 10),
    (7, 8),
    (14, 5),
    (30, 2),
]

# ---------------------------------------------------------------------------
# Navegador (scrapers con Chromium)
# ---------------------------------------------------------------------------
# Se conserva la sesión iniciada reutilizando un perfil persistente.
# Antes estaba escrito a fuego dentro del colector de Indeed; ahora es
# configurable por variable de entorno.
CHROME_BROWSER_PATH = os.getenv(
    "CHROME_BROWSER_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
CHROME_USER_DATA_PATH = os.getenv(
    "CHROME_USER_DATA_PATH",
    r"C:\Users\kevin\ChromeAutomationProfile",
)
CHROME_PROFILE_DIRECTORY = os.getenv("CHROME_PROFILE_DIRECTORY", "Profile 1")

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-MX,es;q=0.9",
    "Referer": "https://www.google.com/",
}
