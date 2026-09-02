"""Tests for the daily pre-run submit sweep (EATP-035, ADR-011 §5).

`submit_application` is monkeypatched — the real fill/submit mechanics are
already covered end-to-end by `test_apply_submit.py`; this tests the
sweep's own orchestration (which drafts it picks up, what it skips, what it
reports), same test-boundary principle used throughout this project.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rove import config
from rove.apply import store as apply_store
from rove.apply import sweep as sweep_module
from rove.apply.store import ApplicationEntry, ApplicationStatus
from rove.inbox import store as inbox_store
from rove.models import Job, ScoredJob
from rove.profile import load_profile

PROFILE = load_profile()


@pytest.fixture(autouse=True)
def _isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")
    monkeypatch.setattr(config, "INBOX_FILE", tmp_path / "inbox.jsonl")


def _scored(source_job_id: str) -> ScoredJob:
    job = Job(
        source="lever",
        source_job_id=source_job_id,
        title="Data Analyst",
        company=f"Company-{source_job_id}",
        description="x" * 250,
        url=f"https://fixture.test/lever/{source_job_id}",
    )
    return ScoredJob(job=job, prefilter_score=75, prefilter_passed=True)


def _seed_inbox(*scored_jobs: ScoredJob) -> None:
    inbox_store.append_run(list(scored_jobs), datetime.now(UTC))


def test_no_drafts_returns_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(sweep_module, "submit_application", lambda *a, **k: calls.append(a))

    results = sweep_module.sweep_pending_applications(PROFILE)

    assert results == {}
    assert calls == []


def test_submits_every_draft_ready_entry(monkeypatch):
    a = _scored("1")
    b = _scored("2")
    _seed_inbox(a, b)
    apply_store.record_entry(ApplicationEntry(signature=a.job.signature, status=ApplicationStatus.DRAFT_READY))
    apply_store.record_entry(ApplicationEntry(signature=b.job.signature, status=ApplicationStatus.DRAFT_READY))

    calls = []

    def fake_submit(job, profile, entry, **kwargs):
        calls.append(job.signature)
        return entry.model_copy(update={"status": ApplicationStatus.SUBMITTED})

    monkeypatch.setattr(sweep_module, "submit_application", fake_submit)

    results = sweep_module.sweep_pending_applications(PROFILE)

    assert set(calls) == {a.job.signature, b.job.signature}
    assert results == {a.job.signature: "submitted", b.job.signature: "submitted"}


def test_ignores_non_draft_ready_entries(monkeypatch):
    ready = _scored("1")
    manual = _scored("2")
    submitted = _scored("3")
    _seed_inbox(ready, manual, submitted)
    apply_store.record_entry(ApplicationEntry(signature=ready.job.signature, status=ApplicationStatus.DRAFT_READY))
    apply_store.record_entry(ApplicationEntry(signature=manual.job.signature, status=ApplicationStatus.MANUAL_REQUIRED))
    apply_store.record_entry(ApplicationEntry(signature=submitted.job.signature, status=ApplicationStatus.SUBMITTED))

    calls = []
    monkeypatch.setattr(
        sweep_module,
        "submit_application",
        lambda job, profile, entry, **k: (calls.append(job.signature), entry)[1],
    )

    sweep_module.sweep_pending_applications(PROFILE)

    assert calls == [ready.job.signature]


def test_skips_a_draft_with_no_matching_inbox_entry(monkeypatch, caplog):
    apply_store.record_entry(ApplicationEntry(signature="orphan-sig", status=ApplicationStatus.DRAFT_READY))

    calls = []
    monkeypatch.setattr(sweep_module, "submit_application", lambda *a, **k: calls.append(a))

    results = sweep_module.sweep_pending_applications(PROFILE)

    assert calls == []
    assert results == {}


def test_uses_the_loaded_profile_when_none_given(monkeypatch):
    a = _scored("1")
    _seed_inbox(a)
    apply_store.record_entry(ApplicationEntry(signature=a.job.signature, status=ApplicationStatus.DRAFT_READY))

    seen_profiles = []

    def fake_submit(job, profile, entry, **kwargs):
        seen_profiles.append(profile)
        return entry.model_copy(update={"status": ApplicationStatus.SUBMITTED})

    monkeypatch.setattr(sweep_module, "submit_application", fake_submit)

    sweep_module.sweep_pending_applications()

    assert seen_profiles[0].name == PROFILE.name
