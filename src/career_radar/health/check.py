"""Source health & self-check (ADR-008).

Classifies each source's **raw** collector yield (`CollectorResult.yielded`,
from `collectors/base.py`, *before* the quality gate) against that source's
own rolling baseline from past runs — never a global threshold, and never
the gate's kept/shown count. Using the shown count would conflate normal
quality attrition (a day where every posting happens to be hybrid) with an
actually broken scraper, which is exactly the false alarm ADR-008 exists to
avoid.

Baselines are built from a small, dedicated append-only log
(`data/health/yields.jsonl`, one row per source per run) — separate from
`history/store.py`'s per-job run history (ADR-007, "what was shown to
Kevin"), which tracks a different thing for a different consumer.

EATP-021: each row also carries `duration_seconds` (from `CollectorResult`,
already computed by `collectors/base.py::run_collector`) — not used for
health classification, just so a run's per-collector timing survives past
`checkpoint.json` (which gets deleted once a run completes successfully),
making "was this run faster than last time" answerable after the fact.

Health is informational only: a broken source is flagged, never crashes the
run, and everything here is read-only over data the run already produces.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from career_radar import config
from career_radar.collectors.base import CollectorResult, CollectorStatus
from career_radar.models import SourceHealth, SourceHealthStatus
from career_radar.storage import append_jsonl, read_jsonl

_YIELDS_FILE_NAME = "yields.jsonl"


class _YieldEntry(BaseModel):
    run_started_at: datetime
    source: str
    yielded: int
    status: str
    duration_seconds: float = 0.0


def _yields_file(health_dir: str | Path | None = None) -> Path:
    return Path(health_dir or config.HEALTH_DIR) / _YIELDS_FILE_NAME


def record_yields(
    results: Iterable[CollectorResult],
    run_started_at: datetime | None = None,
    health_dir: str | Path | None = None,
) -> None:
    """Appends one row per source for this run — the raw material for
    future runs' baselines. Call once per run, after collection, and after
    `check_sources()` for this same run (or the run would be baselined
    against itself)."""
    run_started_at = run_started_at or datetime.now(UTC)
    path = _yields_file(health_dir)
    for result in results:
        entry = _YieldEntry(
            run_started_at=run_started_at,
            source=result.source,
            yielded=result.yielded,
            status=result.status.value,
            duration_seconds=result.duration_seconds,
        )
        append_jsonl(path, entry.model_dump(mode="json"))


def yield_baseline(
    source: str,
    max_runs: int = config.HEALTH_BASELINE_MAX_RUNS,
    health_dir: str | Path | None = None,
) -> float | None:
    """Average raw yield over this source's last `max_runs` recorded runs.
    `None` when there isn't yet `config.HEALTH_MIN_RUNS_FOR_BASELINE` worth
    of history — too little data to compare against, not zero.
    """
    counts = [
        raw["yielded"]
        for raw in read_jsonl(_yields_file(health_dir))
        if raw.get("source") == source and isinstance(raw.get("yielded"), int)
    ]
    if len(counts) < config.HEALTH_MIN_RUNS_FOR_BASELINE:
        return None
    recent = counts[-max_runs:]
    return sum(recent) / len(recent)


def classify_source(result: CollectorResult, baseline: float | None) -> SourceHealth:
    """Classify one source's result for this run against its own baseline."""
    if result.status == CollectorStatus.ERROR:
        return SourceHealth(
            source=result.source,
            status=SourceHealthStatus.ERROR,
            yielded=result.yielded,
            baseline=baseline,
            reason=f"{result.source}: error durante la recolección - {result.error}",
        )

    if result.yielded == 0:
        return SourceHealth(
            source=result.source,
            status=SourceHealthStatus.ZERO,
            yielded=0,
            baseline=baseline,
            reason=f"{result.source} no devolvió resultados - posible bloqueo",
        )

    if baseline is not None and baseline > 0 and result.yielded < baseline * config.HEALTH_LOW_YIELD_RATIO:
        return SourceHealth(
            source=result.source,
            status=SourceHealthStatus.LOW,
            yielded=result.yielded,
            baseline=baseline,
            reason=(
                f"{result.source}: {result.yielded} vacantes, muy por debajo de su "
                f"promedio (~{baseline:.0f}) - revisar"
            ),
        )

    return SourceHealth(
        source=result.source,
        status=SourceHealthStatus.OK,
        yielded=result.yielded,
        baseline=baseline,
        reason=f"{result.source}: {result.yielded} vacantes - normal",
    )


def check_sources(
    results: Iterable[CollectorResult],
    max_runs: int = config.HEALTH_BASELINE_MAX_RUNS,
    health_dir: str | Path | None = None,
) -> list[SourceHealth]:
    """Classify every source's result for this run. Read-only: does not
    record anything — call `record_yields()` separately once this run's
    results are final."""
    return [
        classify_source(result, yield_baseline(result.source, max_runs, health_dir))
        for result in results
    ]
