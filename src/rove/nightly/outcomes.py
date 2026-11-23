"""Reading what a nightly batch did, and recording it in Rove (EATP-037).

Claude ends each batch with a JSON block, one entry per vacancy. This module
turns that text into validated `Outcome`s without ever trusting it blindly:
a vacancy is only `applied` when the entry carries evidence (the confirmation
text the page showed), anything the model forgot to report becomes `pending`
(and is simply retried another night), and unknown reasons become `other`.

`record_outcomes` then writes them to Rove — Claude never marks vacancies
itself (charter rule 9): `applied` -> /track applied; reasons that can never
work (offer gone, residence requirement, probable scam) -> /track dismissed;
reasons that need Kevin (captcha, account, CURP...) -> his skipped list;
an unanswerable question -> his questions list.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from rove.nightly.client import RoveClient
from rove.nightly.selector import Candidate
from rove.nightly.skipped import SkipReason

NEVER_WORKS = frozenset({SkipReason.OFFER_GONE, SkipReason.RESIDENCE_REQUIREMENT, SkipReason.SUSPECTED_SCAM})
MIN_EVIDENCE_CHARS = 8


class Outcome(BaseModel):
    url: str
    status: Literal["applied", "skipped", "pending"]
    reason: SkipReason | None = None
    evidence: str = Field(default="", max_length=500)
    question: str | None = Field(default=None, max_length=1000)
    language: str = Field(default="es", pattern="^(es|en)$")
    note: str = Field(default="", max_length=500)


def _extract_json(text: str) -> Any | None:
    """The JSON the model put in its answer: the whole text, a fenced block
    (last one wins), or the widest {...} / [...] slice (the one that starts
    first, so a bare list of objects is not mistaken for its first object)."""
    candidates = [text.strip()]
    candidates += list(reversed(re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)))
    slices = []
    for opener, closer in (("{", "}"), ("[", "]")):
        first, last = text.find(opener), text.rfind(closer)
        if first != -1 and last > first:
            slices.append((first, text[first : last + 1]))
    candidates += [chunk for _, chunk in sorted(slices)]
    for chunk in candidates:
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    return None


def parse_batch_result(text: str, expected_urls: list[str]) -> list[Outcome]:
    """One validated `Outcome` per expected URL, always — missing, malformed or
    unconfirmed entries come back as `pending`."""
    data = _extract_json(text or "")
    if isinstance(data, dict) and "outcomes" not in data and "url" in data:
        data = [data]  # a single outcome with no wrapper
    entries = data.get("outcomes", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    by_url: dict[str, Outcome] = {}
    for raw in entries if isinstance(entries, list) else []:
        if not isinstance(raw, dict) or raw.get("url") not in expected_urls:
            continue
        try:
            outcome = Outcome(**{**raw, "reason": raw.get("reason") or None})
        except ValidationError:
            reason = raw.get("reason")
            safe = {k: v for k, v in raw.items() if k in {"url", "status", "evidence", "question", "language", "note"}}
            try:
                outcome = Outcome(**safe, reason=SkipReason.OTHER if reason else None)
            except ValidationError:
                continue
        by_url.setdefault(outcome.url, outcome)

    results: list[Outcome] = []
    for url in expected_urls:
        outcome = by_url.get(url)
        if outcome is None:
            outcome = Outcome(url=url, status="pending", note="el lote no reportó esta vacante")
        elif outcome.status == "applied" and len(outcome.evidence.strip()) < MIN_EVIDENCE_CHARS:
            outcome = Outcome(url=url, status="pending", note="sin prueba de confirmación, no se marca como enviada")
        elif outcome.status == "skipped" and outcome.reason is None:
            outcome = outcome.model_copy(update={"reason": SkipReason.OTHER})
        elif (
            outcome.status == "skipped"
            and outcome.reason == SkipReason.PENDING_QUESTION
            and not (outcome.question or "").strip()
        ):
            outcome = outcome.model_copy(update={"reason": SkipReason.OTHER, "note": "pregunta sin texto"})
        results.append(outcome)
    return results


@dataclass
class Recorded:
    applied: list[Outcome] = field(default_factory=list)
    dismissed: list[Outcome] = field(default_factory=list)
    for_kevin: list[Outcome] = field(default_factory=list)
    questions: list[Outcome] = field(default_factory=list)
    pending: list[Outcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def record_outcomes(
    client: RoveClient, candidates: dict[str, Candidate], outcomes: list[Outcome]
) -> Recorded:
    """Write outcomes to Rove. A failed call is collected in `errors`, never
    raised: one network blip must not lose the rest of the batch."""
    recorded = Recorded()
    for outcome in outcomes:
        candidate = candidates.get(outcome.url)
        if candidate is None:
            continue
        fields = {"title": candidate.title, "company": candidate.company, "source": candidate.source,
                  "note": outcome.note, "signature": candidate.signature}
        try:
            if outcome.status == "applied":
                client.track(candidate.signature, "applied")
                recorded.applied.append(outcome)
            elif outcome.status == "pending":
                recorded.pending.append(outcome)
            elif outcome.reason in NEVER_WORKS:
                client.track(candidate.signature, "dismissed")
                recorded.dismissed.append(outcome)
            elif outcome.reason == SkipReason.PENDING_QUESTION:
                client.add_question(
                    outcome.question or "",
                    outcome.language,
                    {"url": candidate.url, "title": candidate.title, "company": candidate.company},
                )
                recorded.questions.append(outcome)
            else:
                client.add_skipped(candidate.url, (outcome.reason or SkipReason.OTHER).value, **fields)
                recorded.for_kevin.append(outcome)
        except httpx.HTTPError as exc:
            recorded.errors.append(f"{outcome.url}: {exc}")
    return recorded
