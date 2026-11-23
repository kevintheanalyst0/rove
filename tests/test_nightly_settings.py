"""Kill switch for the nightly run (EATP-037). Fails closed: anything unreadable
means "off"."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from rove import config
from rove.nightly import settings


@pytest.fixture(autouse=True)
def _isolated_settings_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "NIGHTLY_SETTINGS_FILE", tmp_path / "nightly_settings.json")


def test_defaults_are_off_and_cap_is_70():
    current = settings.load()
    assert current.enabled is False
    assert current.skip_next_run is False
    assert current.pause_until is None
    assert current.weekly_cap_pct == 70


def test_corrupt_file_fails_closed_to_defaults():
    config.NIGHTLY_SETTINGS_FILE.write_text("{ not json", encoding="utf-8")
    assert settings.load().enabled is False


def test_wrong_shape_fails_closed_to_defaults():
    config.NIGHTLY_SETTINGS_FILE.write_text('["enabled", true]', encoding="utf-8")
    assert settings.load().enabled is False


def test_invalid_values_in_file_fail_closed_to_defaults():
    config.NIGHTLY_SETTINGS_FILE.write_text('{"enabled": true, "weekly_cap_pct": 5000}', encoding="utf-8")
    assert settings.load().enabled is False


def test_update_persists_and_stamps_updated_at():
    updated = settings.update(enabled=True, weekly_cap_pct=60)
    assert updated.enabled is True and updated.weekly_cap_pct == 60
    assert updated.updated_at is not None
    assert settings.load().weekly_cap_pct == 60


def test_update_is_partial_and_keeps_other_fields():
    settings.update(enabled=True, weekly_cap_pct=55)
    settings.update(skip_next_run=True)
    current = settings.load()
    assert current.enabled is True and current.weekly_cap_pct == 55 and current.skip_next_run is True


@pytest.mark.parametrize("bad", [0, 9, 101, -5])
def test_update_rejects_out_of_range_cap_without_touching_the_file(bad):
    settings.update(enabled=True, weekly_cap_pct=70)
    with pytest.raises(ValidationError):
        settings.update(weekly_cap_pct=bad)
    assert settings.load().weekly_cap_pct == 70


def test_decide_off_by_default():
    decision = settings.decide(settings.load(), today=date(2026, 11, 23))
    assert decision.allowed is False and decision.reason == "apagado"


def test_decide_on_runs():
    settings.update(enabled=True)
    decision = settings.decide(settings.load(), today=date(2026, 11, 23))
    assert decision.allowed is True


def test_decide_skip_next_run_blocks():
    settings.update(enabled=True, skip_next_run=True)
    decision = settings.decide(settings.load(), today=date(2026, 11, 23))
    assert decision.allowed is False and "saltar" in decision.reason


def test_decide_pause_until_is_inclusive_then_resumes():
    settings.update(enabled=True, pause_until=date(2026, 11, 25))
    assert settings.decide(settings.load(), today=date(2026, 11, 25)).allowed is False
    assert settings.decide(settings.load(), today=date(2026, 11, 26)).allowed is True


def test_off_wins_over_everything():
    settings.update(enabled=False, pause_until=date(2020, 1, 1))
    assert settings.decide(settings.load(), today=date(2026, 11, 23)).reason == "apagado"


def test_consume_skip_clears_only_the_skip():
    settings.update(enabled=True, skip_next_run=True, weekly_cap_pct=65)
    after = settings.consume_skip()
    assert after.skip_next_run is False
    assert after.enabled is True and after.weekly_cap_pct == 65
    assert settings.decide(settings.load(), today=date(2026, 11, 23)).allowed is True


def test_consume_skip_when_nothing_to_clear_is_a_noop():
    assert settings.consume_skip().skip_next_run is False
    assert not config.NIGHTLY_SETTINGS_FILE.exists()


def test_today_local_uses_kevins_timezone(monkeypatch):
    from datetime import UTC, datetime

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # 03:00 UTC on the 24th is still the 23rd in Mexico City (UTC-6).
            return datetime(2026, 11, 24, 3, 0, tzinfo=UTC).astimezone(tz) if tz else datetime(2026, 11, 24, 3, 0)

    monkeypatch.setattr(settings, "datetime", _FakeDatetime)
    assert settings.today_local() == date(2026, 11, 23)
