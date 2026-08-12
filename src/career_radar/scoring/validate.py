"""Layer 4 — deterministic post-validation guards (EVALUATION-RUBRIC.md), run
on every AI-evaluated result before it's shown. These catch the exact
defects Kevin saw in the legacy system:

- Contradiction strip: a contra that cancels itself out, or that names
  seniority/overqualification (CANDIDATE-PROFILE.md: never a con), is
  removed. Empty `contras` afterward is fine — a genuinely good job doesn't
  need a manufactured downside.
- Remote / English re-check: independently RE-DERIVED from the job text
  (not just trusting `job.remote_status`/`job.english_required`, which may
  be stale or the AI may have caught something the gate's regex missed) —
  a job can't be A-grade and non-remote, or A-grade and requiring advanced
  English the candidate doesn't have.
- Grade (and `fit`) are never touched here directly — reconstructing the
  `ScoredJob` re-runs its own validator, which is the ONE place a score
  becomes a grade/fit (P7). Never trust a label the AI wrote.

Malformed/missing AI fields are already repaired-or-dropped one layer down
(`ai/parse.py::coerce_result`, `ai/parse.py::match_ai_results`); this module
adds one more clamp on `ai_score` as cheap, redundant insurance.
"""

from __future__ import annotations

from career_radar.criteria import Criteria, classify_remote, load_criteria, requires_advanced_english
from career_radar.models import RemoteStatus, ScoredJob

# A contra naming any of these is a rubric violation regardless of context —
# CANDIDATE-PROFILE.md is explicit that overqualification/seniority is NEVER
# a con, so any mention (even a "positive" one) is stripped rather than
# guessed at.
_SENIORITY_MARKERS = (
    "sobrecalificad",
    "sobre calificad",
    "overqualified",
    "senior",
    "junior",
    "demasiada experiencia",
    "exceso de experiencia",
)

# A contra that hedges itself with a rescuing positive clause is
# self-cancelling ("no maneja Power BI, pero sí tiene experiencia en Tableau")
# — the AI is told never to write these, but Layer 4 is belt-and-suspenders.
_CONTRAST_CONJUNCTIONS = ("pero ", "aunque ", "sin embargo")
_POSITIVE_MARKERS = ("sí ", "si cuenta", "cuenta con", "tiene experiencia", "sí tiene", "sí maneja")

# A score demoted for a remote/English defect must land outside the A band —
# 79 is the top of B (models.py::grade_from_score) — so it can never still
# read as "A-grade and non-remote" after the guard runs.
_DEMOTE_CEILING = 79


def _is_contradictory(contra: str) -> bool:
    lowered = contra.lower()
    if any(marker in lowered for marker in _SENIORITY_MARKERS):
        return True
    has_conjunction = any(conj in lowered for conj in _CONTRAST_CONJUNCTIONS)
    has_rescue = any(marker in lowered for marker in _POSITIVE_MARKERS)
    return has_conjunction and has_rescue


def strip_contradictions(contras: list[str]) -> list[str]:
    """Remove any contra that contradicts itself, or violates a profile rule
    the AI was told to never break. Empty output is legitimate."""
    return [contra for contra in contras if not _is_contradictory(contra)]


def _remote_disagrees(job, criteria: Criteria) -> bool:
    """Re-derived from the full text, independent of `job.remote_status` —
    a stale/mis-set field must never let a non-remote job read as A-grade."""
    status = classify_remote(f"{job.title}\n{job.description}", criteria)
    return status != RemoteStatus.REMOTE


def _english_required(job, criteria: Criteria) -> bool:
    return requires_advanced_english(job.title, job.description, criteria)


def validate(scored: ScoredJob, criteria: Criteria | None = None) -> ScoredJob:
    """Run every Layer-4 guard on one result. Deterministic and idempotent —
    running it twice on its own output changes nothing."""
    if not scored.ai_evaluated or scored.ai_score is None:
        # Nothing to guard: an unevaluated job carries only its prefilter
        # score, which Layer 2 already bounded.
        return scored

    criteria = criteria or load_criteria()
    job = scored.job
    contras = strip_contradictions(scored.contras)
    flags = list(scored.flags)
    ai_score = max(0, min(scored.ai_score, 100))

    if ai_score > _DEMOTE_CEILING:
        if _remote_disagrees(job, criteria):
            ai_score = _DEMOTE_CEILING
            if "remote_uncertain" not in flags:
                flags.append("remote_uncertain")
        if _english_required(job, criteria):
            ai_score = _DEMOTE_CEILING
            if "english_required" not in flags:
                flags.append("english_required")

    return ScoredJob(
        job=job,
        prefilter_score=scored.prefilter_score,
        prefilter_passed=scored.prefilter_passed,
        ai_evaluated=True,
        ai_score=ai_score,
        pros=scored.pros,
        contras=contras,
        summary=scored.summary,
        flags=flags,
    )


def validate_all(scored_jobs: list[ScoredJob], criteria: Criteria | None = None) -> list[ScoredJob]:
    criteria = criteria or load_criteria()
    return [validate(item, criteria) for item in scored_jobs]
