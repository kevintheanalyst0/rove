"""Tests for the accumulated inbox store (EATP-031)."""

from __future__ import annotations

from datetime import UTC, datetime

from rove.inbox.store import append_run, latest_entries, open_entries
from rove.models import Job, ScoredJob


def _scored(signature: str, score: int = 80) -> ScoredJob:
    job = Job(
        source="occ",
        source_job_id=signature,
        signature=signature,
        title="Data Analyst",
        company="Acme",
        description="x" * 250,
        url=f"https://example.com/{signature}",
    )
    return ScoredJob(
        job=job, prefilter_score=score, prefilter_passed=True,
        ai_evaluated=True, ai_score=score,
    )


def test_append_run_writes_one_entry_per_job(tmp_path):
    path = tmp_path / "inbox.jsonl"
    run_started_at = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)

    append_run([_scored("sig-1"), _scored("sig-2")], run_started_at, path=path)

    entries = latest_entries(path)
    assert set(entries) == {"sig-1", "sig-2"}
    assert entries["sig-1"].first_seen_at == run_started_at


def test_open_entries_excludes_resolved_signatures(tmp_path):
    path = tmp_path / "inbox.jsonl"
    run_started_at = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    append_run([_scored("sig-1"), _scored("sig-2")], run_started_at, path=path)

    open_ = {entry.signature for entry in open_entries({"sig-1"}, path=path)}

    assert open_ == {"sig-2"}


def test_a_job_untouched_across_two_runs_keeps_its_original_first_seen_at(tmp_path):
    """Kevin's own scenario: a job first shown Tuesday, still unresolved
    when a later run touches the same signature again (the rare edge case —
    normally the 30-day cache stops this from happening at all), must not
    jump to the later run's date."""
    path = tmp_path / "inbox.jsonl"
    tuesday = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    thursday = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)

    append_run([_scored("sig-1", score=70)], tuesday, path=path)
    append_run([_scored("sig-1", score=95)], thursday, path=path)  # refreshed score

    entry = latest_entries(path)["sig-1"]
    assert entry.first_seen_at == tuesday  # NOT thursday
    assert entry.scored.final_score == 95  # but the data is the latest


def test_open_entries_sorted_newest_first_seen_first(tmp_path):
    path = tmp_path / "inbox.jsonl"
    older = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
    newer = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
    append_run([_scored("old")], older, path=path)
    append_run([_scored("new")], newer, path=path)

    ordered = [entry.signature for entry in open_entries(path=path)]

    assert ordered == ["new", "old"]


def test_no_file_yet_reads_as_empty(tmp_path):
    path = tmp_path / "inbox.jsonl"
    assert latest_entries(path) == {}
    assert open_entries(path=path) == []
