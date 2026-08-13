"""Tests for the applied/dismissed tracking store (EATP-016, ADR-007)."""

from __future__ import annotations

import pytest

from career_radar import config
from career_radar.tracking import store
from career_radar.tracking.store import TrackingAction


@pytest.fixture(autouse=True)
def _isolated_tracking_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TRACKING_FILE", tmp_path / "tracking.jsonl")


def test_record_and_read_back_a_single_action():
    store.record_action("sig-1", TrackingAction.APPLIED)

    assert store.latest_actions() == {"sig-1": TrackingAction.APPLIED}
    assert store.dismissed_signatures() == set()


def test_dismissed_signatures_only_includes_dismissed():
    store.record_action("sig-1", TrackingAction.APPLIED)
    store.record_action("sig-2", TrackingAction.DISMISSED)

    assert store.dismissed_signatures() == {"sig-2"}


def test_a_later_action_overrides_an_earlier_one_for_the_same_signature():
    store.record_action("sig-1", TrackingAction.DISMISSED)
    store.record_action("sig-1", TrackingAction.APPLIED)

    assert store.latest_actions() == {"sig-1": TrackingAction.APPLIED}
    assert store.dismissed_signatures() == set()


def test_no_file_yet_reads_as_empty():
    assert store.latest_actions() == {}
    assert store.dismissed_signatures() == set()
