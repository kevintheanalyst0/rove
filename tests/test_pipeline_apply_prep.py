"""Tests for the auto-apply pipeline hook (EATP-034, ADR-011) —
`pipeline._prepare_applications`. Exercises the orchestration logic
(eligibility selection, skip-already-prepared, memory bail-out, cancellation,
event publishing) with `pipeline.prepare_application` monkeypatched to a
recording stub — real browser/AI mechanics are already covered by
`test_apply_prepare.py`; this is a different test boundary, same as how
`test_pipeline.py` mocks the AI provider rather than re-testing its SDK."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rove import cancellation, config, pipeline
from rove.apply import store as apply_store
from rove.apply.store import ApplicationEntry, ApplicationStatus
from rove.events import EventBus
from rove.inbox import store as inbox_store
from rove.models import Job, ScoredJob
from rove.profile import load_profile
from rove.tracking import store as tracking_store

PROFILE = load_profile()


@pytest.fixture(autouse=True)
def _isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")
    monkeypatch.setattr(config, "AUTO_APPLY_ENABLED", False)
    cancellation.reset()
    yield
    cancellation.reset()


def _scored(source: str, prefilter_score: int, source_job_id: str) -> ScoredJob:
    job = Job(
        source=source,
        source_job_id=source_job_id,
        title="Data Analyst",
        company=f"Company-{source_job_id}",
        description="x" * 250,
        url=f"https://fixture.test/{source}/{source_job_id}",
    )
    return ScoredJob(job=job, prefilter_score=prefilter_score, prefilter_passed=True)


def _seed_inbox(*scored_jobs: ScoredJob) -> None:
    inbox_store.append_run(list(scored_jobs), datetime.now(UTC))


def _recording_stub(calls: list[Job]):
    def _fake(job, profile, router, **kwargs):
        calls.append(job)
        return ApplicationEntry(signature=job.signature, status=ApplicationStatus.DRAFT_READY)

    return _fake


def test_disabled_by_default_never_calls_prepare(monkeypatch):
    calls: list[Job] = []
    monkeypatch.setattr(pipeline, "prepare_application", _recording_stub(calls))
    _seed_inbox(_scored("greenhouse", 75, "1"))  # grade B, eligible

    pipeline._prepare_applications(PROFILE, router=None, event_bus=EventBus())

    assert calls == []


def test_prepares_only_eligible_open_jobs(monkeypatch):
    monkeypatch.setattr(config, "AUTO_APPLY_ENABLED", True)
    calls: list[Job] = []
    monkeypatch.setattr(pipeline, "prepare_application", _recording_stub(calls))

    eligible_greenhouse = _scored("greenhouse", 75, "1")  # grade B
    eligible_lever = _scored("lever", 60, "2")  # grade C
    not_eligible_grade_d = _scored("greenhouse", 20, "3")  # grade D
    not_eligible_source = _scored("occ", 85, "4")  # grade A, wrong source
    _seed_inbox(eligible_greenhouse, eligible_lever, not_eligible_grade_d, not_eligible_source)

    pipeline._prepare_applications(PROFILE, router=None, event_bus=EventBus())

    prepared_signatures = {job.signature for job in calls}
    assert prepared_signatures == {
        eligible_greenhouse.job.signature,
        eligible_lever.job.signature,
    }


def test_skips_dismissed_and_applied_jobs(monkeypatch):
    monkeypatch.setattr(config, "AUTO_APPLY_ENABLED", True)
    calls: list[Job] = []
    monkeypatch.setattr(pipeline, "prepare_application", _recording_stub(calls))

    dismissed = _scored("greenhouse", 75, "1")
    already_applied_by_hand = _scored("greenhouse", 75, "2")
    open_one = _scored("greenhouse", 75, "3")
    _seed_inbox(dismissed, already_applied_by_hand, open_one)
    tracking_store.record_action(dismissed.job.signature, tracking_store.TrackingAction.DISMISSED)
    tracking_store.record_action(
        already_applied_by_hand.job.signature, tracking_store.TrackingAction.APPLIED
    )

    pipeline._prepare_applications(PROFILE, router=None, event_bus=EventBus())

    assert {job.signature for job in calls} == {open_one.job.signature}


def test_skips_already_prepared_but_retries_failed(monkeypatch):
    monkeypatch.setattr(config, "AUTO_APPLY_ENABLED", True)
    calls: list[Job] = []
    monkeypatch.setattr(pipeline, "prepare_application", _recording_stub(calls))

    already_draft = _scored("greenhouse", 75, "1")
    previously_failed = _scored("greenhouse", 75, "2")
    never_tried = _scored("greenhouse", 75, "3")
    _seed_inbox(already_draft, previously_failed, never_tried)
    apply_store.record_entry(
        ApplicationEntry(signature=already_draft.job.signature, status=ApplicationStatus.DRAFT_READY)
    )
    apply_store.record_entry(
        ApplicationEntry(signature=previously_failed.job.signature, status=ApplicationStatus.FAILED)
    )

    pipeline._prepare_applications(PROFILE, router=None, event_bus=EventBus())

    assert {job.signature for job in calls} == {
        previously_failed.job.signature,
        never_tried.job.signature,
    }


def test_stops_early_when_memory_is_tight(monkeypatch):
    monkeypatch.setattr(config, "AUTO_APPLY_ENABLED", True)
    monkeypatch.setattr(pipeline, "_has_memory_headroom", lambda: False)
    calls: list[Job] = []
    monkeypatch.setattr(pipeline, "prepare_application", _recording_stub(calls))
    _seed_inbox(_scored("greenhouse", 75, "1"), _scored("greenhouse", 75, "2"))

    bus = EventBus()
    events_q = bus.subscribe()
    pipeline._prepare_applications(PROFILE, router=None, event_bus=bus)

    assert calls == []
    messages = []
    while not events_q.empty():
        messages.append(events_q.get_nowait().message)
    assert any("memoria" in m.lower() for m in messages)


def test_respects_cancellation_mid_loop(monkeypatch):
    monkeypatch.setattr(config, "AUTO_APPLY_ENABLED", True)
    calls: list[Job] = []

    def _cancel_after_first(job, profile, router, **kwargs):
        calls.append(job)
        if len(calls) == 1:
            cancellation.request()
        return ApplicationEntry(signature=job.signature, status=ApplicationStatus.DRAFT_READY)

    monkeypatch.setattr(pipeline, "prepare_application", _cancel_after_first)
    _seed_inbox(_scored("greenhouse", 75, "1"), _scored("greenhouse", 75, "2"))

    with pytest.raises(cancellation.RunCancelled):
        pipeline._prepare_applications(PROFILE, router=None, event_bus=EventBus())

    assert len(calls) == 1


def test_publishes_a_done_event_with_no_candidates():
    bus = EventBus()
    events_q = bus.subscribe()

    pipeline._prepare_applications(PROFILE, router=None, event_bus=bus)
    # disabled by default -> _prepare_applications returns before publishing
    assert events_q.empty()
