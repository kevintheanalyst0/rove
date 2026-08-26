"""Layer 2 — the matcher pre-filter (EVALUATION-RUBRIC.md). Unlike the legacy
matcher (`legacy/jobmatch/pipeline/matcher.py`), which only ranked, this one
also REJECTS below a floor and CAPS how many reach the AI (P10, P12, P14).

Scores against the FULL job text (title + description) — a title-only score
is exactly the rigidity ADR-009 rules out. `title_caution_flags()` may
nudge the score down slightly, and only when the description doesn't
independently confirm the role either — it never rejects on its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from rove.criteria import Criteria, load_criteria, title_caution_flags
from rove.models import Job, RemoteStatus

# A caution-flagged title that the description doesn't rescue either costs a
# small, fixed amount — enough to matter on a borderline job, never enough by
# itself to sink a job the description otherwise supports (ADR-009: advisory,
# not a verdict).
_TITLE_CAUTION_PENALTY = 5


@dataclass
class PrefilterOutcome:
    """Every job Layer 2 saw, split by what happens to it next."""

    scores: dict[str, int]  # job.signature -> prefilter_score, for every job seen
    selected: list[Job] = field(default_factory=list)  # passed the floor, within the AI cap
    deferred: list[Job] = field(default_factory=list)  # passed the floor, beyond the AI cap
    rejected: list[Job] = field(default_factory=list)  # below the floor


def _unrescued_caution_flags(job: Job, criteria: Criteria) -> list[str]:
    """A caution flag only survives to penalize the score if the FULL
    description also fails to confirm the role — the title alone flagging it
    is not enough (ADR-009)."""
    flags = title_caution_flags(job.title, criteria)
    if not flags:
        return []
    description = job.description.lower()
    return [
        trigger
        for trigger in flags
        if trigger in criteria.title_caution_words
        and not any(word in description for word in criteria.title_caution_words[trigger])
    ]


def prefilter_score(job: Job, criteria: Criteria | None = None) -> int:
    """Cheap rule score, 0-100, evaluated against title + description."""
    criteria = criteria or load_criteria()
    text = f"{job.title}\n{job.description}".lower()

    raw = 0
    for role, weight in criteria.matcher.role_weights.items():
        if role in text:
            raw += weight
    for skill, weight in criteria.matcher.skill_weights.items():
        if skill.lower() in text:
            raw += weight
    if job.remote_status == RemoteStatus.REMOTE:
        raw += criteria.matcher.remote_bonus
    for max_days, bonus in criteria.matcher.recency_bonus:
        if job.days_old <= max_days:
            raw += bonus
            break

    if _unrescued_caution_flags(job, criteria):
        raw -= _TITLE_CAUTION_PENALTY

    return max(0, min(raw, 100))


def run_prefilter(jobs: Iterable[Job], criteria: Criteria | None = None) -> PrefilterOutcome:
    """Score every job, reject below the floor, and cap the survivors to the
    top N (by score) that proceed to the AI — the rest are `deferred`
    (plausible, but the AI budget doesn't stretch to them this run)."""
    criteria = criteria or load_criteria()
    floor = criteria.matcher.score_floors.prefilter_reject_floor
    cap = criteria.matcher.score_floors.ai_cap_top_n

    scored = [(job, prefilter_score(job, criteria)) for job in jobs]
    scores = {job.signature: score for job, score in scored}

    rejected = [job for job, score in scored if score < floor]
    passed = sorted(
        (pair for pair in scored if pair[1] >= floor),
        key=lambda pair: pair[1],
        reverse=True,
    )

    return PrefilterOutcome(
        scores=scores,
        selected=[job for job, _ in passed[:cap]],
        deferred=[job for job, _ in passed[cap:]],
        rejected=rejected,
    )
