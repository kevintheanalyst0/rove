"""Central configuration — the single source of truth.

Paths, search terms, and tunables used to be scattered across the legacy
collectors (see `legacy/jobmatch/config.py`). Every later project reads its
settings from here instead of hardcoding them locally.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"

GATED_FILE = DATA_DIR / "gated.jsonl"
RESULTS_FILE = DATA_DIR / "results.json"
STATUS_FILE = DATA_DIR / "status.json"
SIGNATURES_FILE = CACHE_DIR / "signatures.jsonl"


def raw_source_file(source: str) -> Path:
    """Path to a source's raw JSONL file (e.g. 'linkedin' -> data/raw/linkedin.jsonl)."""
    return RAW_DIR / f"{source}.jsonl"


# Versioned criteria data (EATP-002) — who Kevin is, what a good job means.
PROFILE_FILE = BASE_DIR / "profile.toml"
CRITERIA_FILE = BASE_DIR / "criteria.toml"


# ---------------------------------------------------------------------------
# Search (single source of truth; was duplicated across collectors)
# ---------------------------------------------------------------------------
# Spanish terms: searching in Spanish biases toward the local/LatAm market and
# avoids English postings that later get penalized for requiring advanced
# English (see legacy config.py for the same rationale).
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

# English terms: for remote-first/global boards (Remotive, RemoteOK, We Work
# Remotely, Himalayas — EATP-007) that post almost exclusively in English.
# See docs/governance/SEARCH-STRATEGY.md.
ENGLISH_SEARCH_TERMS = [
    "data analyst",
    "business intelligence analyst",
    "reporting analyst",
    "business analyst",
    "bi analyst",
    "analytics analyst",
]

# ---------------------------------------------------------------------------
# Browser (Chromium via DrissionPage — LinkedIn/Indeed collectors)
# ---------------------------------------------------------------------------
# Empty by default: browser.py resolves to the standalone Chromium Playwright
# downloads (`playwright install chromium`) if this isn't set. Override only
# to point at a different Chrome/Chromium binary.
CHROME_BROWSER_PATH = os.getenv("CHROME_BROWSER_PATH") or None

# Persistent profile dir: keeps LinkedIn/Indeed logins between runs so fewer
# captchas trigger (mirrors legacy CHROME_USER_DATA_PATH, now cross-platform
# and gitignored under data/).
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR") or str(DATA_DIR / "browser_profile")

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
MAX_DAYS_OLD = 15

# How many days a content signature is considered "already seen" (ADR-001).
# Owned here; enforced by the cache in EATP-010.
SIGNATURE_SEEN_WINDOW_DAYS = 30

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_configured = False


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once. Quiet by default (WARNING).

    Callers (orchestrator, web server, ad-hoc scripts) call this at startup.
    Importing this module never configures logging on its own — no side
    effects on import.
    """
    global _configured
    if _configured:
        return
    resolved = (level or os.getenv("LOG_LEVEL", "WARNING")).upper()
    logging.basicConfig(level=resolved, format=_LOG_FORMAT)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
