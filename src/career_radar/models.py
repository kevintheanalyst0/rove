"""Typed data contracts — one shape for a job, one for a scored job, one for a run.

Replaces the ad-hoc dicts every legacy collector built by hand (see
`legacy/jobmatch/models.py`). Collectors, filters, cache, scoring, and the UI
all speak these pydantic models; see `docs/governance/DATA-CONTRACTS.md` for
the authoritative field-by-field spec this file implements.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, date, datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RemoteStatus(str, Enum):
    """ADR-002: remote is a hard-gated enum, never a soft bool."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class SeniorityHint(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    UNKNOWN = "unknown"


class Grade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class Fit(str, Enum):
    IDEAL = "ideal"
    STRONG = "strong"
    GOOD = "good"
    MODERATE = "moderate"
    WEAK = "weak"
    POOR = "poor"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PAUSED = "paused"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Content signature (ADR-001) — the stable identity, not a volatile site id
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
# Volatile-looking tokens: req-ids and other long digit runs (e.g. "REQ12345",
# "12345"). Heuristic, not exhaustive — tuned further in EATP-003/010 as real
# source data comes in.
_REQID_RE = re.compile(r"^[a-z]{0,3}\d{4,}$")
_VOLATILE_WORDS = {"hoy", "ayer", "publicado", "publicada", "nuevo", "nueva", "urgente"}


def normalize(text: str) -> str:
    """Lowercase, strip accents/punctuation, collapse whitespace, drop volatile tokens."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", text)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = _DATE_RE.sub(" ", value)
    value = _PUNCT_RE.sub(" ", value)
    tokens = [
        tok
        for tok in value.split()
        if tok not in _VOLATILE_WORDS and not _REQID_RE.match(tok)
    ]
    return _WHITESPACE_RE.sub(" ", " ".join(tokens)).strip()


def content_signature(company: str, title: str, description: str) -> str:
    """sha1(normalize(company) | normalize(title) | normalize(description)[:400]) — ADR-001."""
    payload = "|".join(
        [
            normalize(company),
            normalize(title),
            normalize(description)[:400],
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The single canonical score -> grade mapping (used EVERYWHERE)
# ---------------------------------------------------------------------------


def grade_from_score(score: int) -> Grade:
    """The ONE place a score becomes a grade. See DATA-CONTRACTS.md."""
    if score >= 90:
        return Grade.A_PLUS
    if score >= 80:
        return Grade.A
    if score >= 70:
        return Grade.B
    if score >= 55:
        return Grade.C
    return Grade.D


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Job(BaseModel):
    """A normalized vacancy — collector output, common to all sources."""

    source: str
    source_job_id: str
    signature: str = ""
    title: str
    company: str = "Unknown"
    description: str = ""
    url: str
    remote_status: RemoteStatus = RemoteStatus.UNKNOWN
    remote_evidence: list[str] = Field(default_factory=list)
    posted_at: date | None = None
    days_old: int = 999
    location_raw: str = ""
    english_required: bool = False
    seniority_hint: SeniorityHint = SeniorityHint.UNKNOWN
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _fill_signature(self) -> Job:
        # Collectors normally don't need to compute this themselves.
        if not self.signature:
            self.signature = content_signature(self.company, self.title, self.description)
        return self


class ScoredJob(BaseModel):
    """A `Job` after pre-filter + AI — scoring output."""

    job: Job
    prefilter_score: int
    prefilter_passed: bool
    ai_evaluated: bool = False
    ai_score: int | None = None
    final_score: int = 0
    grade: Grade = Grade.D
    fit: Fit
    pros: list[str] = Field(default_factory=list)
    contras: list[str] = Field(default_factory=list)
    summary: str = ""
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_score_and_grade(self) -> ScoredJob:
        # Enforced here, not left to callers: this is exactly the invariant
        # that broke in the legacy system (two scales -> "B" with "No cons").
        self.final_score = self.ai_score if (self.ai_evaluated and self.ai_score is not None) else self.prefilter_score
        self.grade = grade_from_score(self.final_score)
        return self


class RunResult(BaseModel):
    """The output of one full run."""

    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    message: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    jobs: list[ScoredJob] = Field(default_factory=list)
    ai_usage: dict[str, int] = Field(default_factory=dict)
