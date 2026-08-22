"""Layer 1 hard filters (EVALUATION-RUBRIC.md) — deterministic, no AI.

`gate()` runs every job through, in order:

1. `title_is_rejected()` — absolute title/company exclusion (ADR-009:
   deliberately narrow, never the ambiguous caution words).
2. `classify_english_requirement_with_evidence()` — only the `REJECT` tier
   (explicit C1/C2/native/bilingual) rejects here; `INDETERMINATE` (ambiguous
   phrasing, EATP-028/P27) is kept and flagged downstream instead.
3. The remote hard-gate (ADR-002) — `remote_status` must be `remote`.
4. Staleness — `days_old` beyond `config.MAX_DAYS_OLD`.
5. Cross-source fuzzy dedup (EATP-010, `quality/dedup.py`) — a repost from a
   second source within this same run.
6. The content-signature cache (EATP-010, `quality/cache.py`, ADR-001) — a
   posting seen within the configured window on a *prior* run, if a cache is
   passed in. Skipped entirely when `cache=None` (e.g. EATP-009's own tests,
   or any caller that doesn't have one yet).
7. Kevin's dismissed signatures (EATP-016, ADR-007) — 'no me interesa' from
   the dashboard, if a `dismissed` set is passed in. Skipped when `None`.

Each rejection carries its own reason string — tallied per-source into the
run's funnel diagnostic (EATP-028/P28), never shown per-job in the UI. The
matcher/AI (EATP-012/013) is out of scope here — a kept `Job` is just
"structurally plausible", nothing more.

A kept job's `title_caution_flags` (ADR-009) are computed and attached to it
as data — never a reject reason at this layer — so the matcher can weigh
them against the full description later.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from career_radar import config, criteria
from career_radar.config import get_logger
from career_radar.models import EnglishRequirement, Job, RemoteStatus
from career_radar.quality.cache import SignatureCache
from career_radar.quality.dedup import dedup as fuzzy_dedup

logger = get_logger(__name__)


@dataclass
class GateResult:
    kept: list[Job] = field(default_factory=list)
    rejected: list[tuple[Job, str]] = field(default_factory=list)


def _check_job(job: Job) -> tuple[Job, str | None]:
    """Returns `(possibly-updated job, rejection reason)`; reason is `None`
    when the job is kept."""
    if criteria.title_is_rejected(job.title, job.company):
        return job, "excluded_title_or_company"

    english_requirement, english_evidence = criteria.classify_english_requirement_with_evidence(
        job.title, job.description
    )
    if english_requirement != EnglishRequirement.COMPATIBLE:
        job = job.model_copy(
            update={"english_requirement": english_requirement, "english_evidence": english_evidence}
        )
        if english_requirement == EnglishRequirement.REJECT:
            return job, "advanced_english_required"
        # INDETERMINATE (EATP-028, P27): ambiguous phrasing ("English
        # required", "professional English") never specified a level — kept
        # visible instead of dropped; `confirm_english` gets attached to the
        # ScoredJob once evaluate.py assembles it (Layer 3), not here.

    remote_status, remote_evidence = criteria.classify_remote_with_evidence(
        f"{job.title}\n{job.description}"
    )
    job = job.model_copy(
        update={"remote_status": remote_status, "remote_evidence": remote_evidence}
    )
    if remote_status != RemoteStatus.REMOTE:
        return job, f"not_remote:{remote_status.value}"

    if job.days_old > config.MAX_DAYS_OLD:
        return job, "stale"

    caution_flags = criteria.title_caution_flags(job.title)
    if caution_flags:
        job = job.model_copy(update={"title_caution_flags": caution_flags})

    return job, None


def gate(
    jobs: Iterable[Job],
    *,
    dedup: bool = True,
    cache: SignatureCache | None = None,
    dismissed: set[str] | None = None,
) -> GateResult:
    """Run every job through Layer 1, then (by default) cross-source dedup,
    then the signature cache and Kevin's dismissed signatures if passed in.
    Never raises: one malformed job can't take down a whole run (same
    discipline as `collectors/base.py`'s `run_collector` — a single bad
    record becomes a rejection, not a crash).
    """
    result = GateResult()
    for job in jobs:
        try:
            updated, reason = _check_job(job)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            logger.warning("gate: unexpected error on job %s: %s", job.source_job_id, exc)
            result.rejected.append((job, f"gate_error:{exc}"))
            continue

        if reason is None:
            result.kept.append(updated)
        else:
            result.rejected.append((updated, reason))

    if dedup:
        deduped, dropped = fuzzy_dedup(result.kept)
        result.kept = deduped
        result.rejected.extend((job, "duplicate_within_run") for job in dropped)

    if cache is not None:
        still_kept: list[Job] = []
        for job in result.kept:
            if cache.seen_recently(job.signature):
                result.rejected.append((job, "cached_recently"))
            else:
                still_kept.append(job)
        result.kept = still_kept

    if dismissed:
        still_kept = []
        for job in result.kept:
            if job.signature in dismissed:
                result.rejected.append((job, "dismissed_by_kevin"))
            else:
                still_kept.append(job)
        result.kept = still_kept

    return result
