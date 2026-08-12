"""Capa de IA (Gemini).

Regla nº 1 — máxima velocidad evitando 429:
- Pacing adaptativo THREAD-SAFE: varios lotes se envían en paralelo y el
  semáforo garantiza que ninguno supera el límite de peticiones/minuto.
- Reintento inteligente: 429 por minuto → backoff y reintento en ese hilo;
  429 de cuota diaria → QuotaExceededError (el pipeline se pausa).
- Validación completa de cada respuesta (no revienta si falta un campo).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from json import JSONDecoder
from pathlib import Path

from jobmatch import config
from jobmatch.console import console
from jobmatch.pipeline.prompts import ANALYZE_BATCH_PROMPT


class QuotaExceededError(Exception):
    """Cuota DIARIA de Gemini agotada: el pipeline se pausa y se reanuda luego."""


# ---------------------------------------------------------------------------
# Cliente único (perezoso)
# ---------------------------------------------------------------------------
_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            from google import genai
            _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Pacing adaptativo THREAD-SAFE (semáforo de peticiones/minuto)
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_last_call = 0.0


def _respect_rate_limit() -> None:
    """Bloquea el hilo que llama hasta que puede enviar sin exceder el RPM."""
    global _last_call
    min_interval = 60.0 / max(config.AI_REQUESTS_PER_MINUTE, 1)
    with _rate_lock:
        elapsed = time.monotonic() - _last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_call = time.monotonic()


# ---------------------------------------------------------------------------
# Depuración opcional
# ---------------------------------------------------------------------------
def _save_debug(prefix: str, content: str) -> None:
    if not config.SAVE_AI_DEBUG:
        return
    config.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = config.DEBUG_DIR / f"{timestamp}_{prefix}.txt"
    Path(path).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Parseo y validación
# ---------------------------------------------------------------------------
def extract_json(text: str):
    text = text.replace("```json", "").replace("```", "").strip()
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        raise ValueError("No JSON found.")
    obj, _ = JSONDecoder().raw_decode(text[min(starts):])
    return obj


def _looks_like_daily_quota(error: Exception) -> bool:
    text = str(error).lower()
    return any(h in text for h in ("per day", "perday", "per-day", "daily limit", "quota exceeded"))


def _status_code(error: Exception) -> int | None:
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code
    text = str(error)
    if "429" in text:
        return 429
    if "503" in text:
        return 503
    return None


def coerce_result(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    job_id = item.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        return None
    try:
        score = int(item.get("gemini_score"))
    except (TypeError, ValueError):
        return None
    score = max(0, min(score, 100))
    pros = item.get("pros")
    contras = item.get("contras")
    summary = item.get("summary")
    return {
        "job_id": job_id,
        "gemini_score": score,
        "pros": pros if isinstance(pros, list) else [],
        "contras": contras if isinstance(contras, list) else [],
        "summary": summary if isinstance(summary, str) else "",
    }


# ---------------------------------------------------------------------------
# Llamada individual con reintentos (corre en su propio hilo)
# ---------------------------------------------------------------------------
def _generate(prompt: str) -> str:
    from google.genai import errors as genai_errors

    client = _get_client()

    for attempt in range(config.AI_MAX_RETRIES):
        _respect_rate_limit()

        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )
            return response.text

        except genai_errors.ClientError as error:
            if _status_code(error) == 429:
                if _looks_like_daily_quota(error):
                    raise QuotaExceededError(str(error)) from error
                if attempt < config.AI_MAX_RETRIES - 1:
                    _backoff(attempt, "429")
                    continue
                raise QuotaExceededError(str(error)) from error
            raise

        except genai_errors.ServerError as error:
            if attempt < config.AI_MAX_RETRIES - 1:
                _backoff(attempt, "503")
                continue
            raise

    raise RuntimeError("Gemini falló de forma inesperada.")


def _backoff(attempt: int, code: str) -> None:
    wait = config.AI_RETRY_BACKOFF_SECONDS * (2 ** attempt)
    console.warning(f"Gemini {code}: reintentando en {wait:.0f}s (intento {attempt + 1}/{config.AI_MAX_RETRIES})...")
    time.sleep(wait)


# ---------------------------------------------------------------------------
# Lote individual
# ---------------------------------------------------------------------------
def _build_jobs_text(jobs_batch: list[dict]) -> str:
    parts = []
    for index, item in enumerate(jobs_batch, start=1):
        job = item["job"]
        parts.append(
            f"\n\nVACANTE_{index}\n\n"
            f"TITLE:\n{job.get('title', '')}\n\n"
            f"MATCHER SCORE:\n{item['matcher_score']}\n\n"
            f"DESCRIPTION:\n{job.get('description', '')}\n"
        )
    return "".join(parts)


def analyze_jobs_batch(jobs_batch: list[dict], profile) -> list[dict]:
    """Analiza un lote. Puede lanzar QuotaExceededError."""
    prompt = ANALYZE_BATCH_PROMPT.format(profile=profile, jobs=_build_jobs_text(jobs_batch))
    _save_debug("prompt", prompt)

    text = _generate(prompt)
    _save_debug("response", text)

    try:
        raw = extract_json(text)
    except (ValueError, json.JSONDecodeError) as error:
        console.error(f"JSON inválido recibido de Gemini: {error}")
        raise

    if not isinstance(raw, list):
        raise TypeError(f"Gemini devolvió {type(raw).__name__}, se esperaba una lista.")

    return [r for item in raw if (r := coerce_result(item)) is not None]


# ---------------------------------------------------------------------------
# Análisis PARALELO de todos los lotes
# ---------------------------------------------------------------------------
def analyze_all_batches(
    batches: list[list[dict]],
    profile,
    on_batch_done=None,
) -> tuple[list[tuple[int, list[dict]]], bool]:
    """Envía todos los lotes en paralelo respetando el límite de RPM.

    Devuelve:
        results  — lista de (batch_index, resultados) en orden de llegada.
        quota_hit — True si algún lote encontró cuota diaria agotada.

    `on_batch_done(batch_index, n_results)` se llama en el hilo del worker
    cada vez que un lote termina (para actualizar el progreso en pantalla).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Usar tantos workers como lotes, pero no más de AI_REQUESTS_PER_MINUTE
    # (no tiene sentido tener más hilos que peticiones permitidas por minuto).
    workers = min(len(batches), max(config.AI_REQUESTS_PER_MINUTE, 1))

    results: list[tuple[int, list[dict]]] = []
    quota_hit = False
    results_lock = threading.Lock()

    def run_batch(batch_index: int, batch: list[dict]):
        nonlocal quota_hit
        try:
            batch_results = analyze_jobs_batch(batch, profile)
            with results_lock:
                results.append((batch_index, batch_results))
            if on_batch_done:
                on_batch_done(batch_index, len(batch_results))
        except QuotaExceededError:
            with results_lock:
                quota_hit = True
        except Exception as error:
            console.error(f"Lote {batch_index} falló: {error}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_batch, i, batch): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            future.result()  # propaga excepciones no capturadas

    return results, quota_hit


def generate_json(prompt: str):
    """Envía un prompt y devuelve el JSON de la respuesta."""
    return extract_json(_generate(prompt))
