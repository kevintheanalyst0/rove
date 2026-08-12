"""The orchestrator (EATP-014) — runs the full pipeline end to end:

    collect -> health -> gate/dedup/cache -> prefilter -> AI evaluate ->
    validate -> rank -> persist

Streams each source to its own `data/raw/<source>.jsonl` and checkpoints
after collect (per source), after gate, and after every AI batch, so a run
interrupted by a crash, an OOM kill, or Ctrl+C can be resumed by simply
calling `run()` again — never re-scraping a source it already finished, and
never re-paying an AI provider for a job it already scored (CLAUDE.md golden
rule 3; ADR-006 id-based matching makes the AI checkpoint safe to replay).

Not ported from `legacy/jobmatch/pipeline/{process,state}.py` (CLAUDE.md
golden rule 12): the legacy version matched AI results back by list position
(`VACANTE_{N}`, exactly the P17 bug already fixed in EATP-012/013) and kept
state as one monolithic `jobs.json`/`batches.json`/`analyzed.json` trio. Here
state is the same streamed JSONL files the rest of the pipeline already
produces (`raw/<source>.jsonl`, `gated.jsonl`) plus one small checkpoint
file — composing modules EATP-003-013 already built, not reinventing them.

Note on "pause": `RunStatus.PAUSED` exists for a UI-initiated stop, but the
AI router (EATP-012) already degrades a fully-exhausted-quota day to
`ai_evaluated=False` results instead of raising — so quota exhaustion alone
never halts a run here; it just means some jobs are ranked on their
prefilter score alone. What this module resumes is a genuine interruption of
the *process* (crash/kill), not a modeled quota pause.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from career_radar import config
from career_radar.ai.base import AiResult
from career_radar.ai.parse import match_ai_results
from career_radar.ai.router import AiRouter, build_default_router
from career_radar.collectors import BROWSER_SOURCES, build_registry
from career_radar.collectors.base import (
    CollectorRegistry,
    CollectorResult,
)
from career_radar.config import get_logger
from career_radar.criteria import Criteria, load_criteria
from career_radar.events import EventBus
from career_radar.events import bus as default_bus
from career_radar.health.check import classify_source, record_yields, yield_baseline
from career_radar.history import store as history_store
from career_radar.models import Job, RunResult, RunStatus, ScoredJob, SourceHealth
from career_radar.profile import Profile, load_profile
from career_radar.quality.cache import SignatureCache
from career_radar.quality.filters import gate
from career_radar.scoring import rank_scored_jobs
from career_radar.scoring.evaluate import build_deferred
from career_radar.scoring.prefilter import run_prefilter
from career_radar.scoring.validate import validate_all
from career_radar.storage import (
    append_jsonl,
    read_json,
    read_jsonl,
    write_json,
    write_jsonl,
)

logger = get_logger(__name__)

# Progress percent budget per stage — used only to give the UI (EATP-015) a
# smoothly moving number, not a precise cost model.
_COLLECT_START, _COLLECT_END = 0.0, 45.0
_GATE_START, _GATE_END = 45.0, 50.0
_PREFILTER_END = 55.0
_AI_START, _AI_END = 55.0, 95.0
_PERSIST_START = 95.0


class _Checkpoint(BaseModel):
    """Resumable state for one in-progress run, persisted to
    `config.CHECKPOINT_FILE`. `mode`/`sources` pin the checkpoint to the
    exact run it belongs to — a request with a different shape discards it
    rather than resuming into the wrong sources."""

    run_started_at: datetime
    mode: str
    sources: list[str]
    stage: str = "collecting"  # collecting -> gated -> scoring
    collected_sources: list[str] = Field(default_factory=list)
    collector_results: dict[str, dict] = Field(default_factory=dict)
    source_health: dict[str, dict] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)


def _load_checkpoint(mode: str, sources: list[str]) -> _Checkpoint | None:
    raw = read_json(config.CHECKPOINT_FILE)
    if not raw:
        return None
    try:
        checkpoint = _Checkpoint(**raw)
    except (TypeError, ValueError):
        return None
    if checkpoint.stage not in ("collecting", "gated", "scoring"):
        return None
    if checkpoint.mode != mode or checkpoint.sources != sources:
        logger.info("discarding stale checkpoint: requested run shape changed")
        return None
    return checkpoint


def _save_checkpoint(checkpoint: _Checkpoint) -> None:
    write_json(config.CHECKPOINT_FILE, checkpoint.model_dump(mode="json"))


def _clear_run_artifacts() -> None:
    """Wipe checkpoint/gate/AI-checkpoint files — called both when starting
    a genuinely fresh run (no stale partial state should leak in) and when a
    run finishes successfully (nothing left to resume into)."""
    for path in (config.CHECKPOINT_FILE, config.GATED_FILE, config.AI_CHECKPOINT_FILE):
        Path(path).unlink(missing_ok=True)


def _requested_sources(
    registry: CollectorRegistry, mode: str, sources: list[str] | None
) -> list[str]:
    enabled = registry.enabled_names()
    if sources is not None:
        requested = [name for name in sources if name in enabled]
    elif mode == "fast":
        requested = [name for name in enabled if name not in BROWSER_SOURCES]
    else:
        requested = list(enabled)
    return sorted(requested)


def _collect_stage(
    registry: CollectorRegistry,
    requested: list[str],
    checkpoint: _Checkpoint,
    event_bus: EventBus,
) -> tuple[list[Job], list[CollectorResult], list[SourceHealth]]:
    """Runs (or reuses, per source) every requested collector. A source
    already in `checkpoint.collected_sources` is loaded back from its raw
    JSONL instead of re-scraped. Baselines are snapshotted once up front so a
    source's health is never classified against a baseline that already
    includes this same run's own yield (see `health/check.py`'s docstring on
    call ordering)."""
    baselines = {
        source: yield_baseline(source)
        for source in requested
        if source not in checkpoint.collected_sources
    }

    all_jobs: list[Job] = []
    results: list[CollectorResult] = []
    healths: list[SourceHealth] = []
    total = len(requested)

    for index, source in enumerate(requested, start=1):
        percent = _COLLECT_START + (_COLLECT_END - _COLLECT_START) * index / max(total, 1)

        if source in checkpoint.collected_sources:
            jobs = [Job(**raw) for raw in read_jsonl(config.raw_source_file(source))]
            result = CollectorResult(**checkpoint.collector_results[source])
            health = SourceHealth(**checkpoint.source_health[source])
            event_bus.publish(
                "collect", "running", percent,
                f"{source}: reanudado desde el checkpoint ({len(jobs)} vacantes)",
            )
        else:
            event_bus.publish("collect", "running", percent, f"Buscando en {source}...")
            jobs, result = registry.run(source)
            write_jsonl(config.raw_source_file(source), (job.model_dump(mode="json") for job in jobs))
            health = classify_source(result, baselines[source])
            record_yields([result], checkpoint.run_started_at)

            checkpoint.collected_sources.append(source)
            checkpoint.collector_results[source] = result.model_dump(mode="json")
            checkpoint.source_health[source] = health.model_dump(mode="json")
            _save_checkpoint(checkpoint)

        all_jobs.extend(jobs)
        results.append(result)
        healths.append(health)

    event_bus.publish(
        "collect", "done", _COLLECT_END, f"Recolección completa: {len(all_jobs)} vacantes"
    )
    return all_jobs, results, healths


def _gate_stage(
    all_jobs: list[Job],
    checkpoint: _Checkpoint,
    cache: SignatureCache,
    recency_days: int | None,
    event_bus: EventBus,
) -> list[Job]:
    event_bus.publish("gate", "running", _GATE_START, "Filtrando y depurando duplicados...")

    original_max_days_old = config.MAX_DAYS_OLD
    if recency_days is not None:
        config.MAX_DAYS_OLD = recency_days
    try:
        gate_result = gate(all_jobs, cache=cache)
    finally:
        config.MAX_DAYS_OLD = original_max_days_old

    write_jsonl(config.GATED_FILE, (job.model_dump(mode="json") for job in gate_result.kept))
    checkpoint.stage = "gated"
    checkpoint.counts["collected"] = len(all_jobs)
    checkpoint.counts["gated_kept"] = len(gate_result.kept)
    checkpoint.counts["gated_rejected"] = len(gate_result.rejected)
    _save_checkpoint(checkpoint)

    event_bus.publish(
        "gate", "done", _GATE_END, f"{len(gate_result.kept)} vacantes pasaron el filtro de calidad"
    )
    return gate_result.kept


def _collect_and_gate(
    registry: CollectorRegistry,
    requested: list[str],
    checkpoint: _Checkpoint,
    cache: SignatureCache,
    recency_days: int | None,
    event_bus: EventBus,
) -> tuple[list[Job], list[SourceHealth]]:
    """Fast path: if a prior attempt already finished gating this exact run
    (`gated.jsonl` + a `gated`/`scoring` checkpoint), skip collect and gate
    entirely — the whole point of the checkpoint (no re-scrape)."""
    if checkpoint.stage in ("gated", "scoring") and Path(config.GATED_FILE).exists():
        kept = [Job(**raw) for raw in read_jsonl(config.GATED_FILE)]
        healths = [SourceHealth(**raw) for raw in checkpoint.source_health.values()]
        event_bus.publish(
            "gate", "done", _GATE_END, f"Reanudado: {len(kept)} vacantes ya filtradas"
        )
        return kept, healths

    all_jobs, _results, healths = _collect_stage(registry, requested, checkpoint, event_bus)
    kept = _gate_stage(all_jobs, checkpoint, cache, recency_days, event_bus)
    return kept, healths


def _chunk(items: list[Job], size: int) -> list[list[Job]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _to_scored_job(job: Job, prefilter_score: int, ai_result: AiResult | None) -> ScoredJob:
    if ai_result is None:
        return ScoredJob(job=job, prefilter_score=prefilter_score, prefilter_passed=True)
    return ScoredJob(
        job=job,
        prefilter_score=prefilter_score,
        prefilter_passed=True,
        ai_evaluated=True,
        ai_score=ai_result.ai_score,
        pros=ai_result.pros,
        contras=ai_result.contras,
        summary=ai_result.summary,
    )


def _load_ai_checkpoint() -> dict[str, ScoredJob]:
    scored: dict[str, ScoredJob] = {}
    for raw in read_jsonl(config.AI_CHECKPOINT_FILE):
        try:
            item = ScoredJob(**raw)
        except (TypeError, ValueError):
            continue
        scored[item.job.signature] = item
    return scored


def _score_stage(
    kept: list[Job],
    criteria: Criteria,
    router: AiRouter,
    profile: Profile,
    checkpoint: _Checkpoint,
    event_bus: EventBus,
) -> list[ScoredJob]:
    outcome = run_prefilter(kept, criteria)
    checkpoint.counts["prefilter_rejected"] = len(outcome.rejected)
    checkpoint.counts["prefilter_selected"] = len(outcome.selected)
    checkpoint.counts["prefilter_deferred"] = len(outcome.deferred)
    checkpoint.stage = "scoring"
    _save_checkpoint(checkpoint)
    event_bus.publish(
        "prefilter", "done", _PREFILTER_END,
        f"{len(outcome.selected)} vacantes para evaluar con IA, {len(outcome.deferred)} en espera",
    )

    already_scored = _load_ai_checkpoint()
    pending = [job for job in outcome.selected if job.signature not in already_scored]
    batches = _chunk(pending, config.AI_BATCH_SIZE)
    ai_scored: list[ScoredJob] = list(already_scored.values())

    if not batches:
        event_bus.publish("ai", "running", _AI_START, "Sin vacantes nuevas para evaluar con IA")

    for index, batch in enumerate(batches, start=1):
        percent = _AI_START + (_AI_END - _AI_START) * index / len(batches)
        event_bus.publish(
            "ai", "running", percent, f"Evaluando con IA: lote {index}/{len(batches)}..."
        )
        ai_results = router.evaluate_batch(batch, profile)
        matched = match_ai_results(batch, ai_results)
        for job in batch:
            scored = _to_scored_job(job, outcome.scores[job.signature], matched.get(job.signature))
            ai_scored.append(scored)
            append_jsonl(config.AI_CHECKPOINT_FILE, scored.model_dump(mode="json"))

    checkpoint.counts["ai_evaluated"] = sum(1 for item in ai_scored if item.ai_evaluated)
    _save_checkpoint(checkpoint)

    deferred_scored = build_deferred(outcome.deferred, outcome.scores)
    validated = validate_all(ai_scored, criteria)
    ranked = rank_scored_jobs([*validated, *deferred_scored])

    event_bus.publish("ai", "done", _AI_END, f"Evaluación con IA completa: {len(ai_scored)} vacantes")
    return ranked


def _ai_usage_snapshot() -> dict[str, int]:
    raw = read_json(config.AI_USAGE_FILE, default={}) or {}
    today = datetime.now(UTC).date().isoformat()
    return {
        provider: data.get("requests", 0)
        for provider, data in raw.items()
        if isinstance(data, dict) and data.get("date") == today
    }


def _persist(
    ranked: list[ScoredJob],
    source_health: list[SourceHealth],
    counts: dict[str, int],
    run_started_at: datetime,
    cache: SignatureCache,
    event_bus: EventBus,
) -> RunResult:
    event_bus.publish("persist", "running", _PERSIST_START, "Guardando resultados...")

    for scored in ranked:
        cache.update(scored.job.signature, final_score=scored.final_score)
    cache.save()
    history_store.record_run([scored.job for scored in ranked], run_started_at)

    counts = {**counts, "final": len(ranked)}
    result = RunResult(
        started_at=run_started_at,
        finished_at=datetime.now(UTC),
        status=RunStatus.SUCCESS,
        message=f"{len(ranked)} vacantes encontradas",
        counts=counts,
        source_health=source_health,
        jobs=ranked,
        ai_usage=_ai_usage_snapshot(),
    )
    write_json(config.RESULTS_FILE, result.model_dump(mode="json"))
    write_json(config.STATUS_FILE, result.model_dump(mode="json"))
    _clear_run_artifacts()

    event_bus.publish("persist", "done", 100.0, f"Listo: {len(ranked)} vacantes")
    return result


def _with_ai_cap(criteria: Criteria, ai_cap: int | None) -> Criteria:
    if ai_cap is None:
        return criteria
    score_floors = criteria.matcher.score_floors.model_copy(update={"ai_cap_top_n": ai_cap})
    matcher = criteria.matcher.model_copy(update={"score_floors": score_floors})
    return criteria.model_copy(update={"matcher": matcher})


def run(
    *,
    mode: str = "thorough",
    sources: list[str] | None = None,
    ai_cap: int | None = None,
    recency_days: int | None = None,
    resume: bool = True,
    registry: CollectorRegistry | None = None,
    router: AiRouter | None = None,
    profile: Profile | None = None,
    criteria: Criteria | None = None,
    event_bus: EventBus | None = None,
) -> RunResult:
    """Run the full pipeline once and return its `RunResult`.

    `mode='thorough'` (default) runs every registered source, including the
    browser-driven ones (LinkedIn/Indeed) — best coverage, per Kevin (P4: a
    short list of genuinely good matches beats a long one). `mode='fast'`
    drops the browser sources for a quick HTTP/JSON-only pass. `sources`
    overrides both with an explicit subset (mainly for tests/debugging).

    If a checkpoint from a matching, unfinished run exists and `resume` is
    true (the default), already-collected sources and already-AI-scored jobs
    are loaded from disk instead of redone. Any exception aborts the run
    without losing that progress: everything already checkpointed stays on
    disk for the next call to pick up.
    """
    config.configure_logging()
    event_bus = event_bus or default_bus
    profile = profile or load_profile()
    criteria = _with_ai_cap(criteria or load_criteria(), ai_cap)
    router = router or build_default_router()
    registry = registry or build_registry()

    requested = _requested_sources(registry, mode, sources)
    checkpoint = _load_checkpoint(mode, requested) if resume else None
    if checkpoint is None:
        _clear_run_artifacts()
        checkpoint = _Checkpoint(run_started_at=datetime.now(UTC), mode=mode, sources=requested)

    run_started_at = checkpoint.run_started_at
    cache = SignatureCache.load()

    try:
        kept, source_health = _collect_and_gate(
            registry, requested, checkpoint, cache, recency_days, event_bus
        )
        ranked = _score_stage(kept, criteria, router, profile, checkpoint, event_bus)
        return _persist(ranked, source_health, checkpoint.counts, run_started_at, cache, event_bus)
    except BaseException as exc:
        logger.error("run interrupted: %s", exc)
        write_json(
            config.STATUS_FILE,
            {
                "started_at": run_started_at.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "status": RunStatus.ERROR.value,
                "message": f"{type(exc).__name__}: {exc}",
                "counts": checkpoint.counts,
            },
        )
        event_bus.publish("error", "error", 0.0, f"Corrida interrumpida: {exc}")
        raise
