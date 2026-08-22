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


class EnglishRequirement(str, Enum):
    """EATP-028: was a bare bool (`english_required`) that hard-rejected on
    any English mention, ambiguous or not. Three-way now, same shape as
    `RemoteStatus` — `COMPATIBLE` is the default (no signal, or an explicit
    B2/intermediate mention); `INDETERMINATE` is ambiguous phrasing ("English
    required", "professional English") that doesn't specify a level — kept
    visible with a `confirm_english` flag instead of dropped; `REJECT` is an
    explicit C1/C2/native/bilingual requirement, still a hard gate."""

    COMPATIBLE = "compatible"
    INDETERMINATE = "indeterminate"
    REJECT = "reject"


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


class SourceHealthStatus(str, Enum):
    """ADR-008: a source's raw collector yield classified against its own
    rolling baseline — never a global threshold."""

    OK = "ok"
    LOW = "low"
    ZERO = "zero"
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


def fit_from_score(score: int) -> Fit:
    """The ONE place a score becomes a `fit` label — same score guide the AI
    prompt is given (`ai/prompts.py`'s SCORE GUIDE), so `fit` and the number
    it's shown next to can never read as contradictory (same fix as
    `grade_from_score`, applied to the other label EATP-012's prompt output
    doesn't itself carry)."""
    if score >= 95:
        return Fit.IDEAL
    if score >= 85:
        return Fit.STRONG
    if score >= 70:
        return Fit.GOOD
    if score >= 50:
        return Fit.MODERATE
    if score >= 30:
        return Fit.WEAK
    return Fit.POOR


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


# A description this short (after stripping) can't give the AI enough to evaluate
# fairly (P21) — flag it instead of guessing at a threshold per source.
_MIN_DESCRIPTION_LENGTH = 200


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
    english_requirement: EnglishRequirement = EnglishRequirement.COMPATIBLE
    english_evidence: list[str] = Field(default_factory=list)
    seniority_hint: SeniorityHint = SeniorityHint.UNKNOWN
    thin_description: bool = False
    # ADR-009: advisory only — a caution word (e.g. "engineer", "manager")
    # present with no rescue word nearby. Set by the quality gate (EATP-009)
    # for the matcher (EATP-013) to weigh against the full description; NEVER
    # a reason to reject a job at the gate itself.
    title_caution_flags: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _fill_signature(self) -> Job:
        # Collectors normally don't need to compute this themselves.
        if not self.signature:
            self.signature = content_signature(self.company, self.title, self.description)
        return self

    @model_validator(mode="after")
    def _flag_thin_description(self) -> Job:
        # Auto-derived so every collector gets this for free (P21) instead of
        # each one deciding its own threshold, the way the legacy collectors did.
        if not self.thin_description and len(self.description.strip()) < _MIN_DESCRIPTION_LENGTH:
            self.thin_description = True
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
    fit: Fit = Fit.POOR
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
        self.fit = fit_from_score(self.final_score)
        return self


class SourceHealth(BaseModel):
    """ADR-008: one source's health verdict for this run — informational
    only, a broken source never blocks or crashes the run."""

    source: str
    status: SourceHealthStatus
    yielded: int
    baseline: float | None = None
    reason: str = ""


class RunResult(BaseModel):
    """The output of one full run."""

    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    message: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    # EATP-028 (P28): per-source breakdown of every gate-rejection reason
    # (`quality/filters.py`'s reason strings, e.g. "advanced_english_required",
    # "not_remote:hybrid", "stale", "duplicate_within_run", "cached_recently",
    # "dismissed_by_kevin") — {source: {reason: count}}. Answers "did the
    # market produce little, or did a specific stage/source quietly filter a
    # lot" without guessing from the aggregate `counts` alone.
    funnel: dict[str, dict[str, int]] = Field(default_factory=dict)
    source_health: list[SourceHealth] = Field(default_factory=list)
    jobs: list[ScoredJob] = Field(default_factory=list)
    ai_usage: dict[str, int] = Field(default_factory=dict)
    # Signatures unseen in any prior run's history (ADR-007) — computed once
    # at persist time, before this run's own jobs are recorded into history
    # (see pipeline.py's docstring note on `history_store.mark_new` ordering:
    # computing it later would make every job "already known" against itself).
    new_signatures: list[str] = Field(default_factory=list)
