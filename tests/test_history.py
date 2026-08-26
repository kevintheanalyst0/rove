"""Tests for the run-history store (ADR-007, EATP-010)."""

from __future__ import annotations

from datetime import UTC, datetime

from rove.history.store import (
    known_signatures,
    mark_new,
    record_run,
    run_history_file,
)
from rove.models import Job


def _job(**overrides) -> Job:
    defaults = {
        "source": "occ",
        "source_job_id": "1",
        "title": "Data Analyst",
        "company": "Acme",
        "description": "Un puesto remoto de analista de datos con SQL y Power BI.",
        "url": "https://example.com/1",
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_run_history_file_is_named_by_run_timestamp(tmp_path):
    run_started_at = datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC)
    path = run_history_file(run_started_at, history_dir=tmp_path)
    assert path == tmp_path / "20260115T093000Z.jsonl"


def test_record_run_writes_one_entry_per_job(tmp_path):
    jobs = [_job(source_job_id="1"), _job(source_job_id="2", title="Business Analyst")]
    run_started_at = datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC)

    path = record_run(jobs, run_started_at, history_dir=tmp_path)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_known_signatures_is_empty_before_any_run(tmp_path):
    assert known_signatures(history_dir=tmp_path) == set()


def test_known_signatures_reads_across_multiple_run_files(tmp_path):
    first_run = datetime(2026, 1, 1, tzinfo=UTC)
    second_run = datetime(2026, 1, 8, tzinfo=UTC)
    job_a = _job(source_job_id="1", title="Data Analyst")
    job_b = _job(source_job_id="2", title="Business Analyst")

    record_run([job_a], first_run, history_dir=tmp_path)
    record_run([job_b], second_run, history_dir=tmp_path)

    known = known_signatures(history_dir=tmp_path)
    assert job_a.signature in known
    assert job_b.signature in known


def test_mark_new_flags_a_signature_absent_from_prior_runs(tmp_path):
    first_run = datetime(2026, 1, 1, tzinfo=UTC)
    seen_before = _job(source_job_id="1", title="Data Analyst")
    record_run([seen_before], first_run, history_dir=tmp_path)

    brand_new = _job(source_job_id="2", title="Business Analyst")
    pairs = mark_new([seen_before, brand_new], history_dir=tmp_path)

    results = {job.source_job_id: is_new for job, is_new in pairs}
    assert results["1"] is False
    assert results["2"] is True


def test_mark_new_with_no_history_at_all_flags_everything_new(tmp_path):
    jobs = [_job(source_job_id="1"), _job(source_job_id="2", title="Business Analyst")]

    pairs = mark_new(jobs, history_dir=tmp_path)

    assert all(is_new for _, is_new in pairs)


def test_mark_new_accepts_a_precomputed_known_set_without_touching_disk(tmp_path):
    job = _job(source_job_id="1")
    pairs = mark_new([job], known={job.signature})

    assert pairs == [(job, False)]
