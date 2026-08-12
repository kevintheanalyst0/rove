"""Estado del pipeline, sobre almacenamiento atómico.

Reemplaza los tres gestores separados (history/batches/status), cada uno con
su propio patrón de leer/guardar JSON. Ahora todo pasa por `storage`, que
escribe de forma atómica (no puede corromperse a mitad).
"""

from __future__ import annotations

import time

from jobmatch import config
from jobmatch.storage import read_json, write_json

PROVIDER = "Gemini"


# --- Caché permanente de vacantes ya analizadas ---
def load_analyzed_jobs() -> list:
    return read_json(config.ANALYZED_JOBS_FILE, default=[])


def save_analyzed_jobs(jobs: list) -> None:
    write_json(config.ANALYZED_JOBS_FILE, jobs)


# --- Progreso reanudable por lotes ---
_EMPTY_BATCHES = {"processed_jobs": [], "last_completed_batch": -1}


def load_batches() -> dict:
    data = read_json(config.BATCHES_FILE, default=None)
    return data if isinstance(data, dict) else dict(_EMPTY_BATCHES)


def save_batches(processed_jobs: list) -> None:
    write_json(config.BATCHES_FILE, {"processed_jobs": processed_jobs})


def clear_batches() -> None:
    if config.BATCHES_FILE.exists():
        config.BATCHES_FILE.unlink()


def batches_exist() -> bool:
    return config.BATCHES_FILE.exists()


# --- Estado del sistema (lo consume la app) ---
def load_status() -> dict:
    return read_json(
        config.STATUS_FILE,
        default={
            "last_run": "Never",
            "status": "Not executed",
            "provider": PROVIDER,
            "jobs_processed": 0,
            "message": "",
        },
    )


def save_status(status: dict) -> None:
    write_json(config.STATUS_FILE, status)


def set_status(status: str, message: str, jobs_processed: int = 0) -> None:
    """Atajo para escribir el estado sin repetir el diccionario cada vez."""
    save_status(
        {
            "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "provider": PROVIDER,
            "jobs_processed": jobs_processed,
            "message": message,
        }
    )
