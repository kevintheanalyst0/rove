"""Layer 3 — AI deep-evaluation (EVALUATION-RUBRIC.md). Sends the jobs the
pre-filter selected to the AI router in batches, matches results back BY
STABLE ID (ADR-006, never position — that's the exact bug legacy
`pipeline/process.py` had with its `VACANTE_{position}` lookup), and
assembles `ScoredJob`s.

A job the AI never scores — provider unavailable, malformed response, or
simply beyond the AI cap — is never dropped: it falls back to its prefilter
score with `ai_evaluated=False` (P11/P12), exactly like `AiRouter` and
`ai/parse.py::match_ai_results` already guarantee one layer down.
"""

from __future__ import annotations

from career_radar.ai.base import AiResult
from career_radar.ai.parse import match_ai_results
from career_radar.ai.router import AiRouter
from career_radar.config import AI_BATCH_SIZE
from career_radar.models import EnglishRequirement, Job, ScoredJob
from career_radar.profile import Profile


def _chunk(items: list[Job], size: int) -> list[list[Job]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _initial_flags(job: Job) -> list[str]:
    """Flags known the moment a `ScoredJob` is built, independent of whether
    the AI ever scores it (EATP-028/P27) — `confirm_english` must reach
    Kevin even for a job the AI cap defers, not only AI-evaluated ones."""
    if job.english_requirement == EnglishRequirement.INDETERMINATE:
        return ["confirm_english"]
    return []


def _assemble(job: Job, prefilter_score: int, ai_result: AiResult | None) -> ScoredJob:
    flags = _initial_flags(job)
    if ai_result is None:
        return ScoredJob(
            job=job, prefilter_score=prefilter_score, prefilter_passed=True, flags=flags
        )
    return ScoredJob(
        job=job,
        prefilter_score=prefilter_score,
        prefilter_passed=True,
        ai_evaluated=True,
        ai_score=ai_result.ai_score,
        pros=ai_result.pros,
        contras=ai_result.contras,
        summary=ai_result.summary,
        flags=flags,
    )


def evaluate_selected(
    selected: list[Job],
    prefilter_scores: dict[str, int],
    router: AiRouter,
    profile: Profile,
    *,
    batch_size: int = AI_BATCH_SIZE,
) -> list[ScoredJob]:
    """Send `selected` to the AI in batches, id-matched, one `ScoredJob` per
    job in — never fewer, regardless of what the AI actually returns."""
    results: dict[str, AiResult] = {}
    for batch in _chunk(selected, batch_size):
        batch_results = router.evaluate_batch(batch, profile)
        results.update(match_ai_results(batch, batch_results))

    return [
        _assemble(job, prefilter_scores[job.signature], results.get(job.signature))
        for job in selected
    ]


def build_deferred(deferred: list[Job], prefilter_scores: dict[str, int]) -> list[ScoredJob]:
    """Jobs that passed the pre-filter but fell outside the AI cap — ranked
    on their prefilter score alone, never sent to the AI (P14)."""
    return [
        ScoredJob(
            job=job,
            prefilter_score=prefilter_scores[job.signature],
            prefilter_passed=True,
            flags=_initial_flags(job),
        )
        for job in deferred
    ]
