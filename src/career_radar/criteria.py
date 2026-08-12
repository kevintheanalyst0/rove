"""Typed loader + classification helpers for `criteria.toml`.

Encodes what "a good job for Kevin" means as data (see
`docs/governance/CANDIDATE-PROFILE.md` and `EVALUATION-RUBRIC.md` for the
rationale), plus the small pure functions that classify a title/description
against it. Ported and EXPANDED from `legacy/jobmatch/collectors/filters.py`.

Wiring these into the actual collect -> gate -> reject pipeline (writing
`gated.jsonl`, computing `Job.remote_status`/`remote_evidence` for real
scraped postings, counting rejections) is EATP-009's job, not this module's.

Design note (see the header of `criteria.toml`): a title can never be the
final verdict on its own. `title_is_rejected()` only hard-rejects on the
small, absolute `excluded_title_keywords` categories (designer, sales,
marketing, ...) where no description could change the outcome. Ambiguous
words ("engineer", "administrator", "developer", "manager", "security", ...)
live in `title_caution_words` and are exposed only as an ADVISORY flag via
`title_caution_flags()` — real jobs like "Analista administrativo" must reach
the description-reading stages before anything rejects them.
"""

from __future__ import annotations

import re
import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from career_radar.config import CRITERIA_FILE
from career_radar.models import RemoteStatus

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AdvancedEnglish(BaseModel):
    phrases: list[str]
    regex: list[str]


class RemoteSignals(BaseModel):
    positive_phrases: list[str]
    hybrid_phrases: list[str]
    onsite_phrases: list[str]
    onsite_per_week_regex: str
    onsite_per_month_regex: str
    onsite_per_week_regex_en: str
    onsite_per_month_regex_en: str
    max_onsite_days_per_month: int


class ScoreFloors(BaseModel):
    prefilter_reject_floor: int
    ai_cap_top_n: int


class Matcher(BaseModel):
    role_weights: dict[str, int]
    skill_weights: dict[str, int]
    remote_bonus: int
    recency_bonus: list[tuple[int, int]]
    score_floors: ScoreFloors


class Criteria(BaseModel):
    excluded_companies: list[str]
    excluded_title_keywords: dict[str, list[str]]
    title_caution_words: dict[str, list[str]]
    advanced_english: AdvancedEnglish
    remote_signals: RemoteSignals
    matcher: Matcher

    @property
    def flat_excluded_title_keywords(self) -> set[str]:
        return {kw for group in self.excluded_title_keywords.values() for kw in group}


@lru_cache(maxsize=1)
def load_criteria(path: str | Path = CRITERIA_FILE) -> Criteria:
    """Load and validate `criteria.toml`. Cached — it's static within a run."""
    with open(path, "rb") as file:
        data = tomllib.load(file)
    return Criteria(**data)


# ---------------------------------------------------------------------------
# Title classification
# ---------------------------------------------------------------------------


def is_excluded_company(company: str, criteria: Criteria | None = None) -> bool:
    if not company:
        return False
    criteria = criteria or load_criteria()
    company = company.lower().strip()
    return any(blocked in company for blocked in criteria.excluded_companies)


def has_excluded_title(title: str, criteria: Criteria | None = None) -> bool:
    if not title:
        return False
    criteria = criteria or load_criteria()
    title = title.lower()
    return any(keyword in title for keyword in criteria.flat_excluded_title_keywords)


def title_caution_flags(title: str, criteria: Criteria | None = None) -> list[str]:
    """Ambiguous trigger words present with no rescue word nearby.

    ADVISORY ONLY — this is a signal for the matcher/AI (which read the full
    job) to weigh, never a reason to reject a job before its description is
    read. A title like "Analista administrativo" can be a genuinely great
    match despite looking unremarkable; a "Data Analyst" title can hide a
    Linux/dev-heavy job despite looking great. See `criteria.toml` header.
    """
    if not title:
        return []
    criteria = criteria or load_criteria()
    lowered = title.lower()
    flags = []
    for trigger, rescue_words in criteria.title_caution_words.items():
        if trigger in lowered and not any(word in lowered for word in rescue_words):
            flags.append(trigger)
    return flags


def title_is_rejected(title: str, company: str, criteria: Criteria | None = None) -> bool:
    """Filters needing only title + company — cheap, applied before fetching detail.

    Deliberately narrow: only the absolute `excluded_title_keywords`
    categories hard-reject here. Anything ambiguous is `title_caution_flags`,
    not a reject — the description always gets read first.
    """
    criteria = criteria or load_criteria()
    return is_excluded_company(company, criteria) or has_excluded_title(title, criteria)


# ---------------------------------------------------------------------------
# Advanced English
# ---------------------------------------------------------------------------


def requires_advanced_english(title: str, description: str, criteria: Criteria | None = None) -> bool:
    criteria = criteria or load_criteria()
    text = f"{title}\n{description}".lower()
    if any(phrase in text for phrase in criteria.advanced_english.phrases):
        return True
    return any(re.search(pattern, text) for pattern in criteria.advanced_english.regex)


# ---------------------------------------------------------------------------
# Remote classification (ADR-002) — anti-remote overrides positive.
# ---------------------------------------------------------------------------


def classify_remote_with_evidence(
    text: str, criteria: Criteria | None = None
) -> tuple[RemoteStatus, list[str]]:
    """Classify free text (title + description) into a `RemoteStatus`, plus
    the phrase(s) that decided it (DATA-CONTRACTS.md's `remote_evidence` —
    auditable, so a rejection is never just "trust me").

    Anti-remote signals override positive ones. A weekly on-site cadence, or a
    monthly cadence beyond `max_onsite_days_per_month`, is treated as hybrid
    (partial remote); a bare "presencial"/"onsite" phrase with no remote
    component is onsite. Within the monthly tolerance -> the "~1 day/month"
    exception -> remote-ok (the tolerance match is kept as supporting
    evidence alongside whatever ultimately confirms it as remote). No signal
    at all -> unknown, never counted as remote by default.
    """
    if not text:
        return RemoteStatus.UNKNOWN, []
    criteria = criteria or load_criteria()
    signals = criteria.remote_signals
    lowered = text.lower()
    evidence: list[str] = []

    hybrid_phrase = next((p for p in signals.hybrid_phrases if p in lowered), None)
    if hybrid_phrase:
        return RemoteStatus.HYBRID, [hybrid_phrase]

    for pattern in (signals.onsite_per_week_regex, signals.onsite_per_week_regex_en):
        match = re.search(pattern, lowered)
        if match and int(match.group(1)) >= 1:
            return RemoteStatus.HYBRID, [match.group(0)]

    for pattern in (signals.onsite_per_month_regex, signals.onsite_per_month_regex_en):
        match = re.search(pattern, lowered)
        if match:
            days = int(match.group(1))
            if days > signals.max_onsite_days_per_month:
                return RemoteStatus.HYBRID, [match.group(0)]
            # Within tolerance -> falls through to the positive-signal check
            # below, keeping this match as context for why it's still remote.
            evidence.append(match.group(0))

    onsite_phrase = next((p for p in signals.onsite_phrases if p in lowered), None)
    if onsite_phrase:
        return RemoteStatus.ONSITE, [*evidence, onsite_phrase]

    positive_phrase = next((p for p in signals.positive_phrases if p in lowered), None)
    if positive_phrase:
        return RemoteStatus.REMOTE, [*evidence, positive_phrase]

    return RemoteStatus.UNKNOWN, evidence


def classify_remote(text: str, criteria: Criteria | None = None) -> RemoteStatus:
    """Classify free text (title + description) into a `RemoteStatus`.

    See `classify_remote_with_evidence()` for the full decision logic and the
    matched-phrase evidence; this is the status-only convenience wrapper most
    callers (including this module's own tests) use.
    """
    return classify_remote_with_evidence(text, criteria)[0]
