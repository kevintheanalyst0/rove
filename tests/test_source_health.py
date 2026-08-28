"""Tests for source health & self-check (ADR-008, EATP-011)."""

from __future__ import annotations

from datetime import UTC, datetime

from rove.collectors.base import CollectorResult, CollectorStatus
from rove.health.check import (
    _yields_file,
    check_sources,
    classify_source,
    record_yields,
    yield_baseline,
)
from rove.models import SourceHealthStatus
from rove.storage import read_jsonl

_NOW = datetime(2026, 1, 15, tzinfo=UTC)


def _result(
    source="greenhouse", status=CollectorStatus.OK, yielded=10, error=None, duration_seconds=0.0
) -> CollectorResult:
    return CollectorResult(
        source=source,
        status=status,
        yielded=yielded,
        error=error,
        started_at=_NOW,
        duration_seconds=duration_seconds,
    )


# ---------------------------------------------------------------------------
# classify_source — pure, no I/O
# ---------------------------------------------------------------------------


def test_error_status_is_flagged_error_regardless_of_yield():
    result = _result(status=CollectorStatus.ERROR, yielded=0, error="timeout")
    health = classify_source(result, baseline=50.0)

    assert health.status == SourceHealthStatus.ERROR
    assert "timeout" in health.reason


def test_zero_yield_is_flagged_even_without_a_baseline():
    result = _result(yielded=0)
    health = classify_source(result, baseline=None)

    assert health.status == SourceHealthStatus.ZERO
    assert "bloqueo" in health.reason


def test_zero_yield_is_flagged_even_when_baseline_is_also_historically_zero():
    result = _result(yielded=0)
    health = classify_source(result, baseline=0.0)

    assert health.status == SourceHealthStatus.ZERO


def test_normal_yield_against_its_baseline_is_ok():
    result = _result(yielded=45)
    health = classify_source(result, baseline=50.0)

    assert health.status == SourceHealthStatus.OK


def test_yield_far_below_baseline_is_flagged_low():
    result = _result(yielded=5)
    health = classify_source(result, baseline=50.0)

    assert health.status == SourceHealthStatus.LOW
    assert "revisar" in health.reason


def test_nonzero_yield_with_no_baseline_is_ok_not_low():
    # Not enough history to judge "low against what" — informational, never
    # a false alarm just because the source is new.
    result = _result(yielded=3)
    health = classify_source(result, baseline=None)

    assert health.status == SourceHealthStatus.OK


def test_health_report_always_carries_the_source_and_yielded_count():
    result = _result(source="remotive", yielded=7)
    health = classify_source(result, baseline=None)

    assert health.source == "remotive"
    assert health.yielded == 7


# ---------------------------------------------------------------------------
# yield_baseline / record_yields — the rolling baseline persistence
# ---------------------------------------------------------------------------


def test_record_yields_persists_duration_seconds(tmp_path):
    # EATP-021: checkpoint.json (which also has duration_seconds) gets
    # deleted once a run completes — yields.jsonl is the lasting record.
    record_yields([_result(duration_seconds=283.14)], run_started_at=_NOW, health_dir=tmp_path)

    rows = list(read_jsonl(_yields_file(tmp_path)))
    assert rows[0]["duration_seconds"] == 283.14


def test_yield_baseline_is_none_with_no_history(tmp_path):
    assert yield_baseline("greenhouse", health_dir=tmp_path) is None


def test_yield_baseline_is_none_with_only_one_past_run(tmp_path):
    record_yields([_result(yielded=40)], run_started_at=_NOW, health_dir=tmp_path)

    assert yield_baseline("greenhouse", health_dir=tmp_path) is None


def test_yield_baseline_averages_past_runs_once_there_are_enough(tmp_path):
    for yielded, day in [(40, 1), (60, 2), (50, 3)]:
        record_yields(
            [_result(yielded=yielded)],
            run_started_at=datetime(2026, 1, day, tzinfo=UTC),
            health_dir=tmp_path,
        )

    assert yield_baseline("greenhouse", health_dir=tmp_path) == 50.0


def test_yield_baseline_only_counts_matching_source(tmp_path):
    record_yields(
        [_result(source="greenhouse", yielded=40), _result(source="occ", yielded=100)],
        run_started_at=datetime(2026, 1, 1, tzinfo=UTC),
        health_dir=tmp_path,
    )
    record_yields(
        [_result(source="greenhouse", yielded=60)],
        run_started_at=datetime(2026, 1, 2, tzinfo=UTC),
        health_dir=tmp_path,
    )

    assert yield_baseline("greenhouse", health_dir=tmp_path) == 50.0


def test_yield_baseline_only_uses_the_most_recent_max_runs(tmp_path):
    # An old bad run (yielded=0) should age out of a short window.
    record_yields([_result(yielded=0)], run_started_at=datetime(2026, 1, 1, tzinfo=UTC), health_dir=tmp_path)
    record_yields([_result(yielded=50)], run_started_at=datetime(2026, 1, 2, tzinfo=UTC), health_dir=tmp_path)
    record_yields([_result(yielded=50)], run_started_at=datetime(2026, 1, 3, tzinfo=UTC), health_dir=tmp_path)

    assert yield_baseline("greenhouse", max_runs=2, health_dir=tmp_path) == 50.0


# ---------------------------------------------------------------------------
# check_sources — end to end, multiple sources
# ---------------------------------------------------------------------------


def test_check_sources_classifies_every_source_independently(tmp_path):
    for day in (1, 2, 3):
        record_yields(
            [_result(source="greenhouse", yielded=50), _result(source="occ", yielded=20)],
            run_started_at=datetime(2026, 1, day, tzinfo=UTC),
            health_dir=tmp_path,
        )

    this_run = [
        _result(source="greenhouse", yielded=2),  # far below its own baseline
        _result(source="occ", yielded=22),  # normal for its own baseline
        _result(source="wwr", yielded=0),  # brand new, zero
    ]
    reports = check_sources(this_run, health_dir=tmp_path)

    by_source = {r.source: r for r in reports}
    assert by_source["greenhouse"].status == SourceHealthStatus.LOW
    assert by_source["occ"].status == SourceHealthStatus.OK
    assert by_source["wwr"].status == SourceHealthStatus.ZERO


def test_check_sources_never_raises_on_a_source_with_no_baseline_history(tmp_path):
    reports = check_sources([_result(source="himalayas", yielded=4)], health_dir=tmp_path)

    assert reports[0].status == SourceHealthStatus.OK
    assert reports[0].baseline is None
