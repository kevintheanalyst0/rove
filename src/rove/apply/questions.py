"""AI-answered screening questions (EATP-034, ADR-011) — reads a job's real
apply-form questions plus Kevin's lean `[application]` profile, and asks the
existing `AiRouter` for an answer per question. Matched back by a synthetic
per-call id, never by position — the same round-trip discipline ADR-006
already established for job scoring, applied here to a differently-shaped
batch (screening questions instead of jobs).

No fixed Q&A bank (Kevin's explicit call, ADR-011 §2) — every question is
answered fresh from the profile and the job's own context each time.
"""

from __future__ import annotations

from json import JSONDecodeError, JSONDecoder
from typing import Any

from rove.ai.prompts import build_application_prompt
from rove.ai.router import AiRouter
from rove.apply.browser import FieldKind, FormField
from rove.config import get_logger
from rove.profile import Profile

logger = get_logger(__name__)

_decoder = JSONDecoder()


def _strip_code_fences(text: str) -> str:
    return text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()


def _extract_json(text: str) -> Any:
    text = _strip_code_fences(text)
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        raise ValueError("No JSON object or array found in response.")
    obj, _ = _decoder.raw_decode(text[min(starts) :])
    return obj


def parse_answers_response(text: str, expected_ids: set[str]) -> dict[str, str]:
    """Tolerant parse, matched by id (never position) — same ADR-006
    discipline as `ai/parse.py`'s job-scoring round trip. An id the model
    invented, or answered more than once, is dropped rather than guessed at."""
    try:
        raw = _extract_json(text)
    except (ValueError, JSONDecodeError) as error:
        logger.warning("could not extract JSON from question-answer response: %s", error)
        return {}

    if isinstance(raw, dict):
        raw = raw.get("answers", [])
    if not isinstance(raw, list):
        return {}

    counts: dict[str, int] = {}
    last_seen: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        field_id = item.get("id")
        answer = item.get("answer")
        if not isinstance(field_id, str) or not isinstance(answer, str) or not answer.strip():
            continue
        counts[field_id] = counts.get(field_id, 0) + 1
        last_seen[field_id] = answer.strip()

    matched: dict[str, str] = {}
    for field_id, answer in last_seen.items():
        if field_id not in expected_ids:
            logger.warning(
                "AI returned an id that doesn't match any asked question: %s", field_id
            )
            continue
        if counts[field_id] > 1:
            logger.warning(
                "AI returned duplicate answers for id %s — treating as unanswered", field_id
            )
            continue
        matched[field_id] = answer

    return matched


def answer_form_questions(
    router: AiRouter,
    fields: list[FormField],
    *,
    company: str,
    job_title: str,
    job_description: str,
    profile: Profile,
) -> dict[str, str]:
    """Answers every `CUSTOM` field in `fields` — identity/EEO/unsupported
    fields are ignored, that's not AI's job. Returns `{field.label: answer}`;
    a field missing from the result means the AI didn't answer it (the
    caller decides whether that's fatal, based on the field's `required`
    flag — see `apply/browser.py::fill_form`).

    Keyed by label rather than the internal per-call id, matching
    `fill_form`'s own lookup key — two CUSTOM questions with the exact same
    label text on the same form would collide here; live-verified real forms
    never repeat a question's literal wording, so this is accepted as a
    theoretical, not practical, risk."""
    custom_fields = [f for f in fields if f.kind == FieldKind.CUSTOM]
    if not custom_fields:
        return {}

    id_by_index = {f"q{i}": field for i, field in enumerate(custom_fields)}
    questions = [
        (field_id, field.label, field.options) for field_id, field in id_by_index.items()
    ]

    prompt = build_application_prompt(
        questions,
        company=company,
        job_title=job_title,
        job_description=job_description,
        profile=profile,
    )
    text = router.answer_questions(prompt)
    if not text:
        return {}

    answers_by_id = parse_answers_response(text, expected_ids=set(id_by_index))
    return {id_by_index[field_id].label: answer for field_id, answer in answers_by_id.items()}
