"""ai/usage.py — daily quota bookkeeping, persisted across restarts, reset
on date rollover."""

from __future__ import annotations

from datetime import date

from career_radar.ai.usage import ProviderUsage, UsageTracker


def test_fresh_tracker_reports_nothing_exhausted():
    tracker = UsageTracker()
    assert tracker.is_exhausted("groq") is False


def test_mark_exhausted_then_is_exhausted_true_same_day():
    tracker = UsageTracker()
    today = date(2026, 1, 1)
    tracker.mark_exhausted("groq", today=today)
    assert tracker.is_exhausted("groq", today=today) is True


def test_exhausted_flag_resets_on_a_new_day():
    tracker = UsageTracker()
    tracker.mark_exhausted("groq", today=date(2026, 1, 1))
    assert tracker.is_exhausted("groq", today=date(2026, 1, 2)) is False


def test_record_request_increments_count_and_resets_on_new_day():
    tracker = UsageTracker()
    tracker.record_request("groq", today=date(2026, 1, 1))
    tracker.record_request("groq", today=date(2026, 1, 1))
    assert tracker._records["groq"].requests == 2

    tracker.record_request("groq", today=date(2026, 1, 2))
    assert tracker._records["groq"].requests == 1


def test_save_then_load_round_trips_state(tmp_path):
    path = tmp_path / "ai_usage.json"
    tracker = UsageTracker()
    tracker.mark_exhausted("groq", today=date(2026, 1, 1))
    tracker.record_request("gemini_flash", today=date(2026, 1, 1))
    tracker.save(path)

    reloaded = UsageTracker.load(path)

    assert reloaded.is_exhausted("groq", today=date(2026, 1, 1)) is True
    assert reloaded._records["gemini_flash"].requests == 1


def test_load_missing_file_returns_empty_tracker(tmp_path):
    tracker = UsageTracker.load(tmp_path / "does_not_exist.json")
    assert tracker.is_exhausted("groq") is False


def test_provider_usage_model_defaults():
    usage = ProviderUsage(date=date(2026, 1, 1))
    assert usage.requests == 0
    assert usage.exhausted is False
