"""pipeline.run() — the orchestrator (EATP-014). AI is always mocked via a
scripted `Provider`; collectors are always fakes. Never a live call/scrape
(CLAUDE.md §7).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator

import pytest

from career_radar import cancellation, config, pipeline
from career_radar.ai.base import AiResult, Provider
from career_radar.ai.router import AiRouter
from career_radar.ai.usage import UsageTracker
from career_radar.collectors.base import Collector, CollectorRegistry
from career_radar.criteria import (
    AdvancedEnglish,
    Criteria,
    Matcher,
    RemoteSignals,
    ScoreFloors,
)
from career_radar.models import Job, RemoteStatus, RunStatus
from career_radar.profile import load_profile

PROFILE = load_profile()


@pytest.fixture(autouse=True)
def _isolated_data_dir(monkeypatch, tmp_path):
    """Every path pipeline.py touches, redirected under `tmp_path` — a test
    run must never read or write the real `data/` directory."""
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "GATED_FILE", tmp_path / "gated.jsonl")
    monkeypatch.setattr(config, "RESULTS_FILE", tmp_path / "results.json")
    monkeypatch.setattr(config, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(config, "CHECKPOINT_FILE", tmp_path / "checkpoint.json")
    monkeypatch.setattr(config, "AI_CHECKPOINT_FILE", tmp_path / "ai_checkpoint.jsonl")
    monkeypatch.setattr(config, "SIGNATURES_FILE", tmp_path / "cache" / "signatures.jsonl")
    monkeypatch.setattr(config, "HEALTH_DIR", tmp_path / "health")
    monkeypatch.setattr(config, "AI_USAGE_FILE", tmp_path / "ai_usage.json")
    monkeypatch.setattr(config, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")
    monkeypatch.setattr(config, "AI_BATCH_SIZE", 1)


def _job(
    *,
    source: str = "occ",
    source_job_id: str = "1",
    title: str = "Data Analyst",
    days_old: int = 1,
) -> Job:
    return Job(
        source=source,
        source_job_id=source_job_id,
        title=title,
        company=f"Company {source_job_id}",
        description=(
            "Buscamos analista de datos. Posición 100% remote. Power BI y SQL diario."
            + "x" * 200
        ),
        url=f"http://example.com/{source}/{source_job_id}",
        remote_status=RemoteStatus.UNKNOWN,
        days_old=days_old,
    )


def _criteria(*, ai_cap_top_n: int = 50) -> Criteria:
    """A minimal, self-contained `Criteria` for the matcher/validator — the
    gate itself always reads the real `criteria.toml` (quality/filters.py
    doesn't take a criteria param), so test jobs must independently satisfy
    the real remote-signal/title rules (see `_job()`'s description)."""
    return Criteria(
        excluded_companies=[],
        excluded_title_keywords={},
        title_caution_words={},
        advanced_english=AdvancedEnglish(phrases=[], regex=[]),
        remote_signals=RemoteSignals(
            positive_phrases=["remote", "remoto"],
            hybrid_phrases=["hybrid", "híbrido"],
            onsite_phrases=["onsite", "presencial"],
            onsite_per_week_regex=r"(\d+)\s*days?\s*a\s*week",
            onsite_per_month_regex=r"(\d+)\s*days?\s*a\s*month",
            onsite_per_week_regex_en=r"(\d+)\s*days?\s*a\s*week",
            onsite_per_month_regex_en=r"(\d+)\s*days?\s*a\s*month",
            max_onsite_days_per_month=1,
        ),
        matcher=Matcher(
            role_weights={"analista de datos": 30, "data analyst": 30},
            skill_weights={"Power BI": 25, "SQL": 25},
            remote_bonus=20,
            recency_bonus=[(7, 10)],
            score_floors=ScoreFloors(prefilter_reject_floor=10, ai_cap_top_n=ai_cap_top_n),
        ),
    )


class FakeCollector(Collector):
    def __init__(self, name: str, jobs: list[Job]) -> None:
        self.name = name
        self._jobs = jobs
        self.calls = 0

    def collect(self) -> Iterator[Job]:
        self.calls += 1
        yield from self._jobs


def _registry(**sources: list[Job]) -> tuple[CollectorRegistry, dict[str, FakeCollector]]:
    registry = CollectorRegistry()
    collectors: dict[str, FakeCollector] = {}
    for name, jobs in sources.items():
        collector = FakeCollector(name, jobs)
        collectors[name] = collector
        registry.register(name, lambda c=collector: c)
    return registry, collectors


class ScriptedProvider(Provider):
    """Same script-by-signature shape as `test_scoring.py`'s (ADR-006:
    matched by id, never position)."""

    def __init__(self, results_by_signature: dict[str, AiResult]) -> None:
        self.id = "scripted"
        self._by_sig = results_by_signature
        self.batches: list[list[Job]] = []

    def evaluate_batch(self, jobs: list[Job], profile) -> list[AiResult]:
        self.batches.append(jobs)
        return [self._by_sig[job.signature] for job in jobs if job.signature in self._by_sig]


class CrashingProvider(Provider):
    """Scores normally until the `fail_on_call`-th batch, where it raises a
    plain (unmodeled) exception — simulating a process crash mid-AI, not a
    quota/provider error `AiRouter` already knows how to degrade past."""

    def __init__(self, results_by_signature: dict[str, AiResult], *, fail_on_call: int) -> None:
        self.id = "crashing"
        self._by_sig = results_by_signature
        self._fail_on_call = fail_on_call
        self.calls = 0

    def evaluate_batch(self, jobs: list[Job], profile) -> list[AiResult]:
        self.calls += 1
        if self.calls == self._fail_on_call:
            raise RuntimeError("simulated crash mid-batch")
        return [self._by_sig[job.signature] for job in jobs if job.signature in self._by_sig]


def _router(provider: Provider) -> AiRouter:
    return AiRouter({provider.id: provider}, order=[provider.id], usage=UsageTracker())


def _ai_result(job: Job, score: int = 85) -> AiResult:
    return AiResult(
        signature=job.signature,
        ai_score=score,
        pros=["Buen match de skills"],
        contras=[],
        summary="Buen candidato para el rol.",
    )


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------


def test_full_run_over_fixtures_yields_a_valid_run_result():
    remote_job = _job(source="occ", source_job_id="1")
    onsite_job = _job(source="remotive", source_job_id="2")
    onsite_job = onsite_job.model_copy(
        update={"description": "Puesto 100% presencial en oficina, sin excepciones." + "x" * 200}
    )
    registry, _collectors = _registry(occ=[remote_job], remotive=[onsite_job])

    provider = ScriptedProvider({remote_job.signature: _ai_result(remote_job)})
    router = _router(provider)

    result = pipeline.run(
        registry=registry, router=router, profile=PROFILE, criteria=_criteria(), resume=False
    )

    assert result.status == RunStatus.SUCCESS
    assert [scored.job.signature for scored in result.jobs] == [remote_job.signature]
    assert result.jobs[0].ai_evaluated is True
    assert result.jobs[0].final_score == 85
    assert result.counts["collected"] == 2
    assert result.counts["gated_kept"] == 1  # onsite_job rejected by the real remote hard-gate
    assert {health.source for health in result.source_health} == {"occ", "remotive"}

    assert config.RESULTS_FILE.exists()
    assert config.STATUS_FILE.exists()
    # A successful run leaves nothing to resume into.
    assert not config.CHECKPOINT_FILE.exists()
    assert not config.GATED_FILE.exists()
    assert not config.AI_CHECKPOINT_FILE.exists()
    # Never shown before -> new (EATP-016's NEW badge).
    assert result.new_signatures == [remote_job.signature]


def test_dismissed_job_is_excluded_from_the_run():
    """EATP-016: a job Kevin marked 'no me interesa' on the dashboard never
    reappears — tracking.dismissed_signatures() feeds gate() the same way
    EATP-010's cache already does."""
    from career_radar.tracking import store as tracking_store
    from career_radar.tracking.store import TrackingAction

    job = _job(source="occ", source_job_id="1")
    tracking_store.record_action(job.signature, TrackingAction.DISMISSED)

    registry, _collectors = _registry(occ=[job])
    provider = ScriptedProvider({job.signature: _ai_result(job)})
    router = _router(provider)

    result = pipeline.run(
        registry=registry, router=router, profile=PROFILE, criteria=_criteria(), resume=False
    )

    assert result.jobs == []
    assert result.counts["gated_kept"] == 0


def test_new_signatures_excludes_a_job_already_in_history():
    """A job already recorded in a prior run's history must not be flagged
    NEW again, even though it still passes the (separate) recency cache."""
    from datetime import UTC, datetime

    from career_radar.history import store as history_store

    job = _job(source="occ", source_job_id="1")
    history_store.record_run([job], datetime.now(UTC))

    registry, _collectors = _registry(occ=[job])
    provider = ScriptedProvider({job.signature: _ai_result(job)})
    router = _router(provider)

    result = pipeline.run(
        registry=registry, router=router, profile=PROFILE, criteria=_criteria(), resume=False
    )

    assert [scored.job.signature for scored in result.jobs] == [job.signature]
    assert result.new_signatures == []


def test_fast_mode_never_touches_browser_sources():
    # LinkedIn moved back to real-browser listing in EATP-022 (2026-08-15) —
    # both it and Indeed are in BROWSER_SOURCES, so 'fast' mode skips both;
    # OCC (plain HTTP) is the one it should still run.
    occ_job = _job(source="occ", source_job_id="1")
    linkedin_job = _job(source="linkedin", source_job_id="2")
    indeed_job = _job(source="indeed", source_job_id="3")
    registry, collectors = _registry(occ=[occ_job], linkedin=[linkedin_job], indeed=[indeed_job])

    router = _router(ScriptedProvider({occ_job.signature: _ai_result(occ_job)}))

    result = pipeline.run(
        registry=registry, router=router, profile=PROFILE, criteria=_criteria(),
        mode="fast", resume=False,
    )

    assert collectors["indeed"].calls == 0
    assert collectors["linkedin"].calls == 0
    assert collectors["occ"].calls == 1
    assert result.counts["collected"] == 1


def test_ai_cap_override_defers_jobs_beyond_the_cap():
    job_a = _job(source="occ", source_job_id="1")
    job_b = _job(source="occ", source_job_id="2")
    registry, _collectors = _registry(occ=[job_a, job_b])

    provider = ScriptedProvider({job_a.signature: _ai_result(job_a), job_b.signature: _ai_result(job_b)})
    router = _router(provider)

    result = pipeline.run(
        registry=registry, router=router, profile=PROFILE, criteria=_criteria(),
        ai_cap=1, resume=False,
    )

    assert result.counts["prefilter_selected"] == 1
    assert result.counts["prefilter_deferred"] == 1
    evaluated = [scored for scored in result.jobs if scored.ai_evaluated]
    assert len(evaluated) == 1


# ---------------------------------------------------------------------------
# Resume: a mid-run crash never re-scrapes or re-pays for an already-scored job
# ---------------------------------------------------------------------------


def test_resume_after_a_mid_ai_crash_skips_collect_and_already_scored_jobs():
    jobs = [_job(source="occ", source_job_id=str(i)) for i in range(1, 4)]
    registry, collectors = _registry(occ=jobs)

    results_by_sig = {job.signature: _ai_result(job) for job in jobs}
    crashing_provider = CrashingProvider(results_by_sig, fail_on_call=2)
    crashing_router = _router(crashing_provider)

    with pytest.raises(RuntimeError, match="simulated crash"):
        pipeline.run(registry=registry, router=crashing_router, profile=PROFILE, criteria=_criteria())

    assert collectors["occ"].calls == 1
    assert config.GATED_FILE.exists()
    assert crashing_provider.calls == 2  # job 1 succeeded, job 2's batch crashed
    status = config.STATUS_FILE.read_bytes()
    assert b"error" in status.lower()

    working_provider = ScriptedProvider(results_by_sig)
    working_router = _router(working_provider)

    result = pipeline.run(registry=registry, router=working_router, profile=PROFILE, criteria=_criteria())

    # The collector was never re-run — resume reused the checkpointed raw jobs.
    assert collectors["occ"].calls == 1
    # Only the two jobs NOT already checkpointed by the crashed run were sent.
    sent_signatures = {job.signature for batch in working_provider.batches for job in batch}
    assert sent_signatures == {jobs[1].signature, jobs[2].signature}

    assert result.status == RunStatus.SUCCESS
    assert {scored.job.signature for scored in result.jobs} == {job.signature for job in jobs}
    assert all(scored.ai_evaluated for scored in result.jobs)
    assert not config.CHECKPOINT_FILE.exists()


def test_resume_false_ignores_an_existing_checkpoint_and_starts_clean():
    job = _job(source="occ", source_job_id="1")
    registry, collectors = _registry(occ=[job])
    crashing_router = _router(CrashingProvider({job.signature: _ai_result(job)}, fail_on_call=1))

    with pytest.raises(RuntimeError):
        pipeline.run(registry=registry, router=crashing_router, profile=PROFILE, criteria=_criteria())
    assert collectors["occ"].calls == 1

    working_router = _router(ScriptedProvider({job.signature: _ai_result(job)}))
    result = pipeline.run(
        registry=registry, router=working_router, profile=PROFILE, criteria=_criteria(), resume=False
    )

    # resume=False discards the checkpoint, so the source is collected again.
    assert collectors["occ"].calls == 2
    assert result.status == RunStatus.SUCCESS


# ---------------------------------------------------------------------------
# Cancellation (the "Cancelar" button)
# ---------------------------------------------------------------------------


class CancellingCollector(Collector):
    """Simulates the "Cancelar" button being clicked while this source is
    still being scraped — collect() itself requests cancellation, mirroring
    what `browser.start_cancellation_watcher` does to a collector's own
    `giveup` switch in the real browser-driven collectors."""

    def __init__(self, name: str, jobs: list[Job]) -> None:
        self.name = name
        self._jobs = jobs
        self.calls = 0

    def collect(self) -> Iterator[Job]:
        self.calls += 1
        cancellation.request()
        yield from self._jobs


def test_cancellation_during_collect_stops_before_the_next_source():
    jobs_a = [_job(source="occ", source_job_id="1")]
    jobs_b = [_job(source="remotive", source_job_id="2")]
    registry = CollectorRegistry()
    registry.register("occ", lambda: CancellingCollector("occ", jobs_a))
    remotive_collector = FakeCollector("remotive", jobs_b)
    registry.register("remotive", lambda: remotive_collector)

    with pytest.raises(cancellation.RunCancelled):
        pipeline.run(
            registry=registry,
            router=_router(ScriptedProvider({})),
            profile=PROFILE,
            criteria=_criteria(),
        )

    # "occ" sorts before "remotive" (_requested_sources sorts) — the
    # stage-boundary check catches cancellation before remotive ever runs.
    assert remotive_collector.calls == 0
    assert config.raw_source_file("occ").exists()
    status = json.loads(config.STATUS_FILE.read_bytes())
    assert status["status"] == "paused"
    assert status["message"] == "Corrida cancelada."


class DiscardingCollector(FakeCollector):
    """Same shape as `CancellingCollector`, but requests a discard —
    models the new "Cancelar" button (EATP-024), not "Pausar"."""

    def collect(self) -> Iterator[Job]:
        self.calls += 1
        cancellation.request(discard=True)
        yield from self._jobs


class HangingProvider(Provider):
    """Never returns on its own — models a genuinely stuck/hung AI call
    (EATP-024, Kevin's live report: Pausar/Cancelar must react in ~5-10s,
    not wait out a call that may never come back)."""

    def __init__(self) -> None:
        self.id = "hanging"
        self.released = threading.Event()

    def evaluate_batch(self, jobs: list[Job], profile) -> list[AiResult]:
        self.released.wait()
        return []


def test_cancellation_during_a_hung_ai_call_does_not_wait_for_it(monkeypatch):
    monkeypatch.setattr(pipeline, "_CANCEL_POLL_SECONDS", 0.05)  # keep the test fast
    jobs = [_job(source="occ", source_job_id="1")]
    registry, _collectors = _registry(occ=jobs)
    provider = HangingProvider()
    outcome = {}

    def _run() -> None:
        try:
            pipeline.run(registry=registry, router=_router(provider), profile=PROFILE, criteria=_criteria())
        except cancellation.RunCancelled:
            outcome["cancelled"] = True

    thread = threading.Thread(target=_run, daemon=True)
    start = time.monotonic()
    thread.start()
    time.sleep(0.2)  # let the pipeline actually reach the hung AI call
    cancellation.request()
    thread.join(timeout=5)
    elapsed = time.monotonic() - start

    try:
        assert not thread.is_alive()
        assert outcome.get("cancelled") is True
        # Well under the old ~3 min worst case (AI_MAX_RETRIES x
        # AI_REQUEST_TIMEOUT_SECONDS + backoff) — bounded by
        # `_CANCEL_POLL_SECONDS` now instead.
        assert elapsed < 3
    finally:
        provider.released.set()  # let the abandoned background thread finish cleanly


def test_discard_cancellation_wipes_the_checkpoint():
    jobs_a = [_job(source="occ", source_job_id="1")]
    registry = CollectorRegistry()
    registry.register("occ", lambda: DiscardingCollector("occ", jobs_a))

    with pytest.raises(cancellation.RunCancelled):
        pipeline.run(
            registry=registry,
            router=_router(ScriptedProvider({})),
            profile=PROFILE,
            criteria=_criteria(),
        )

    assert not config.CHECKPOINT_FILE.exists()
    status = json.loads(config.STATUS_FILE.read_bytes())
    assert status["status"] == "paused"
    assert status["message"] == "Corrida descartada."

    # A fresh "Iniciar" (resume=True, the default) must not pick anything
    # back up — the checkpoint is gone, so occ gets scraped again.
    fresh_collector = FakeCollector("occ", jobs_a)
    registry2 = CollectorRegistry()
    registry2.register("occ", lambda: fresh_collector)
    result = pipeline.run(
        registry=registry2, router=_router(ScriptedProvider({})), profile=PROFILE, criteria=_criteria()
    )
    assert fresh_collector.calls == 1
    assert result.status == RunStatus.SUCCESS


class CancellingProvider(Provider):
    """Same shape as `CrashingProvider`, but requests cancellation instead
    of raising — models the AI-scoring phase getting cancelled mid-run."""

    def __init__(self, results_by_signature: dict[str, AiResult], *, cancel_on_call: int) -> None:
        self.id = "cancelling"
        self._by_sig = results_by_signature
        self._cancel_on_call = cancel_on_call
        self.calls = 0

    def evaluate_batch(self, jobs: list[Job], profile) -> list[AiResult]:
        self.calls += 1
        if self.calls == self._cancel_on_call:
            cancellation.request()
        return [self._by_sig[job.signature] for job in jobs if job.signature in self._by_sig]


def test_cancellation_during_ai_scoring_stops_before_the_next_batch():
    jobs = [_job(source="occ", source_job_id=str(i)) for i in range(1, 4)]
    registry, collectors = _registry(occ=jobs)
    results_by_sig = {job.signature: _ai_result(job) for job in jobs}
    provider = CancellingProvider(results_by_sig, cancel_on_call=2)

    with pytest.raises(cancellation.RunCancelled):
        pipeline.run(registry=registry, router=_router(provider), profile=PROFILE, criteria=_criteria())

    assert collectors["occ"].calls == 1
    assert provider.calls == 2  # the third job's batch never sent
    status = json.loads(config.STATUS_FILE.read_bytes())
    assert status["status"] == "paused"


def test_resume_after_cancellation_reuses_checkpointed_progress():
    jobs = [_job(source="occ", source_job_id=str(i)) for i in range(1, 4)]
    registry, collectors = _registry(occ=jobs)
    results_by_sig = {job.signature: _ai_result(job) for job in jobs}
    cancelling_provider = CancellingProvider(results_by_sig, cancel_on_call=2)

    with pytest.raises(cancellation.RunCancelled):
        pipeline.run(
            registry=registry, router=_router(cancelling_provider), profile=PROFILE, criteria=_criteria()
        )
    assert collectors["occ"].calls == 1

    working_router = _router(ScriptedProvider(results_by_sig))
    result = pipeline.run(registry=registry, router=working_router, profile=PROFILE, criteria=_criteria())

    assert collectors["occ"].calls == 1  # never re-scraped
    assert result.status == RunStatus.SUCCESS
    assert {scored.job.signature for scored in result.jobs} == {job.signature for job in jobs}


def test_reset_all_run_data_wipes_derived_files_but_keeps_tracking():
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    config.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    config.HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    config.SIGNATURES_FILE.parent.mkdir(parents=True, exist_ok=True)

    (config.RAW_DIR / "occ.jsonl").write_text('{"id": 1}\n')
    (config.HISTORY_DIR / "run_1.jsonl").write_text('{"signature": "abc"}\n')
    (config.HEALTH_DIR / "yields.jsonl").write_text('{"source": "occ"}\n')
    config.SIGNATURES_FILE.write_text('{"signature": "abc"}\n')
    config.RESULTS_FILE.write_text("{}")
    config.STATUS_FILE.write_text("{}")
    config.CHECKPOINT_FILE.write_text("{}")
    config.GATED_FILE.write_text('{"id": 1}\n')
    config.AI_CHECKPOINT_FILE.write_text('{"id": 1}\n')

    # Not touched by reset — Kevin's own decisions, not run-derived cache.
    config.TRACKING_FILE.write_text('{"signature": "abc", "action": "applied"}\n')

    pipeline.reset_all_run_data()

    assert not (config.RAW_DIR / "occ.jsonl").exists()
    assert not (config.HISTORY_DIR / "run_1.jsonl").exists()
    assert not (config.HEALTH_DIR / "yields.jsonl").exists()
    assert not config.SIGNATURES_FILE.exists()
    assert not config.RESULTS_FILE.exists()
    assert not config.STATUS_FILE.exists()
    assert not config.CHECKPOINT_FILE.exists()
    assert not config.GATED_FILE.exists()
    assert not config.AI_CHECKPOINT_FILE.exists()

    assert config.TRACKING_FILE.exists()
    assert "applied" in config.TRACKING_FILE.read_text()
