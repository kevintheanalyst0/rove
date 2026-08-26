"""Tolerant parse-and-repair for AI responses (P11) + the stable-id round-trip
match (ADR-006).

A model response is never trusted at face value: it may wrap JSON in markdown
fences, include stray prose, clamp scores outside 0-100, omit fields, or —
the specific bug ADR-006 exists to catch — reorder, drop, duplicate, or
invent an id. Nothing here ever raises past its own function; malformed input
is dropped, not crashed on.
"""

from __future__ import annotations

from collections.abc import Iterable
from json import JSONDecodeError, JSONDecoder
from typing import Any

from rove.ai.base import AiResult
from rove.config import get_logger
from rove.models import Job

logger = get_logger(__name__)

_decoder = JSONDecoder()


def strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` / ``` ... ``` fences some models wrap output in."""
    return text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()


def extract_json(text: str) -> Any:
    """Extract the first balanced JSON array or object found in `text`.

    Tolerates leading/trailing prose around the JSON (models sometimes add a
    sentence before or after despite instructions not to).
    """
    text = strip_code_fences(text)
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        raise ValueError("No JSON object or array found in response.")
    obj, _ = _decoder.raw_decode(text[min(starts) :])
    return obj


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def coerce_result(item: Any) -> AiResult | None:
    """Validate + coerce one raw result item. Returns None if unsalvageable
    (never raises) — the id-round-trip fix, not the type coercion, is what
    protects correctness here; this just protects against crashing."""
    if not isinstance(item, dict):
        return None

    signature = item.get("id") or item.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        return None

    try:
        score = int(item.get("score", item.get("ai_score")))
    except (TypeError, ValueError):
        return None
    score = max(0, min(score, 100))

    summary = item.get("summary")

    return AiResult(
        signature=signature,
        ai_score=score,
        pros=_coerce_str_list(item.get("pros")),
        contras=_coerce_str_list(item.get("contras")),
        summary=summary if isinstance(summary, str) else "",
    )


def parse_batch_response(text: str) -> list[AiResult]:
    """Parse a full batch response into `AiResult`s. Never raises: a totally
    malformed response yields an empty list rather than failing the run."""
    try:
        raw = extract_json(text)
    except (ValueError, JSONDecodeError) as error:
        logger.warning("could not extract JSON from AI response: %s", error)
        return []

    if isinstance(raw, dict):
        raw = raw.get("results", [])
    if not isinstance(raw, list):
        logger.warning(
            "AI response JSON was not a list or {'results': [...]}: %s",
            type(raw).__name__,
        )
        return []

    return [result for item in raw if (result := coerce_result(item)) is not None]


def match_ai_results(
    jobs: Iterable[Job], results: Iterable[AiResult]
) -> dict[str, AiResult]:
    """ADR-006: match results back to jobs BY SIGNATURE, never by position.

    Any id that doesn't belong to one of `jobs` is dropped (the model
    invented or mangled it). Any id that appears more than once is dropped
    entirely — an ambiguous duplicate is treated as unanalyzed rather than
    guessing which copy is correct. A job with no matching id simply has no
    entry in the returned dict; callers treat it as unevaluated (falls back
    to the prefilter score, per `ScoredJob`).
    """
    valid_signatures = {job.signature for job in jobs}

    counts: dict[str, int] = {}
    last_seen: dict[str, AiResult] = {}
    for result in results:
        counts[result.signature] = counts.get(result.signature, 0) + 1
        last_seen[result.signature] = result

    matched: dict[str, AiResult] = {}
    for signature, result in last_seen.items():
        if signature not in valid_signatures:
            logger.warning(
                "AI returned an id that doesn't match any requested job: %s", signature
            )
            continue
        if counts[signature] > 1:
            logger.warning(
                "AI returned duplicate results for id %s — treating as unanalyzed",
                signature,
            )
            continue
        matched[signature] = result

    return matched
