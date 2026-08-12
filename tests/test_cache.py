"""Tests for the content-signature cache (ADR-001, EATP-010)."""

from __future__ import annotations

from datetime import date

from career_radar.quality.cache import SignatureCache


def test_empty_cache_has_never_seen_anything():
    cache = SignatureCache()
    assert cache.seen_recently("abc123") is False


def test_update_then_seen_recently_within_window_is_true():
    cache = SignatureCache()
    cache.update("abc123", today=date(2026, 1, 1))

    assert cache.seen_recently("abc123", window_days=30, today=date(2026, 1, 15)) is True


def test_seen_recently_is_false_once_the_window_has_passed():
    cache = SignatureCache()
    cache.update("abc123", today=date(2026, 1, 1))

    assert cache.seen_recently("abc123", window_days=30, today=date(2026, 3, 1)) is False


def test_update_on_an_existing_signature_bumps_last_seen_without_losing_first_seen():
    cache = SignatureCache()
    cache.update("abc123", today=date(2026, 1, 1))
    cache.update("abc123", today=date(2026, 1, 10))

    record = cache._records["abc123"]
    assert record.first_seen == date(2026, 1, 1)
    assert record.last_seen == date(2026, 1, 10)


def test_update_stores_the_final_score_and_keeps_it_on_later_updates_without_one():
    cache = SignatureCache()
    cache.update("abc123", final_score=82, today=date(2026, 1, 1))
    cache.update("abc123", today=date(2026, 1, 10))

    assert cache._records["abc123"].final_score == 82


def test_update_all_touches_every_signature():
    cache = SignatureCache()
    cache.update_all(["a", "b", "c"], today=date(2026, 1, 1))

    assert len(cache) == 3
    assert cache.seen_recently("b", today=date(2026, 1, 1)) is True


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "signatures.jsonl"
    cache = SignatureCache()
    cache.update("abc123", final_score=90, today=date(2026, 1, 1))
    cache.save(path)

    reloaded = SignatureCache.load(path)

    assert len(reloaded) == 1
    assert reloaded.seen_recently("abc123", today=date(2026, 1, 5)) is True
    assert reloaded._records["abc123"].final_score == 90


def test_load_on_a_missing_file_returns_an_empty_cache(tmp_path):
    cache = SignatureCache.load(tmp_path / "does_not_exist.jsonl")
    assert len(cache) == 0
