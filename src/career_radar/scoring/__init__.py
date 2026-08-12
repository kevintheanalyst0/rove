"""Scoring package (EVALUATION-RUBRIC.md, Layers 2-4): pre-filter, AI
deep-evaluation, and post-validation guards, composed into one ranked list
of `ScoredJob`. The orchestrator (EATP-014) is what wires `score_jobs()` to
real collected/gated jobs, retries, and `RunResult` bookkeeping — this
package only turns `list[Job]` into a ranked `list[ScoredJob]`.
"""

from __future__ import annotations

from career_radar.ai.router import AiRouter
from career_radar.criteria import Criteria, load_criteria
from career_radar.models import Job, ScoredJob
from career_radar.profile import Profile
from career_radar.scoring.evaluate import build_deferred, evaluate_selected
from career_radar.scoring.prefilter import run_prefilter
from career_radar.scoring.validate import validate_all

__all__ = ["rank_scored_jobs", "score_jobs"]


def rank_scored_jobs(scored_jobs: list[ScoredJob]) -> list[ScoredJob]:
    """Best first — the single ordering used wherever a ranked list is
    needed (`RunResult.jobs`)."""
    return sorted(scored_jobs, key=lambda item: item.final_score, reverse=True)


def score_jobs(
    jobs: list[Job],
    router: AiRouter,
    profile: Profile,
    criteria: Criteria | None = None,
) -> list[ScoredJob]:
    """Run Layers 2-4 end to end and return the ranked result. Jobs the
    pre-filter rejects are dropped entirely; everything else is returned,
    whether or not it reached the AI."""
    criteria = criteria or load_criteria()
    outcome = run_prefilter(jobs, criteria)
    ai_scored = evaluate_selected(outcome.selected, outcome.scores, router, profile)
    validated = validate_all(ai_scored, criteria)
    deferred = build_deferred(outcome.deferred, outcome.scores)
    return rank_scored_jobs([*validated, *deferred])
