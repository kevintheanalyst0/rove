"""Tests for the auto-apply state store (EATP-034, ADR-011)."""

from __future__ import annotations

import pytest

from rove import config
from rove.apply import store
from rove.apply.store import ApplicationEntry, ApplicationStatus


@pytest.fixture(autouse=True)
def _isolated_applications_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "APPLICATIONS_FILE", tmp_path / "applications.jsonl")


def test_record_and_read_back_a_single_entry():
    store.record_entry(
        ApplicationEntry(
            signature="sig-1",
            status=ApplicationStatus.DRAFT_READY,
            answers={"why_interested": "..."},
        )
    )

    entries = store.latest_entries()
    assert entries["sig-1"].status == ApplicationStatus.DRAFT_READY
    assert entries["sig-1"].answers == {"why_interested": "..."}


def test_no_file_yet_reads_as_empty():
    assert store.latest_entries() == {}
    assert store.already_prepared_signatures() == set()
    assert store.draft_ready_entries() == {}


def test_a_later_entry_overrides_an_earlier_one_for_the_same_signature():
    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.DRAFT_READY))
    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.SUBMITTED))

    entries = store.latest_entries()
    assert entries["sig-1"].status == ApplicationStatus.SUBMITTED


def test_already_prepared_excludes_failed_so_it_gets_retried():
    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.DRAFT_READY))
    store.record_entry(ApplicationEntry(signature="sig-2", status=ApplicationStatus.FAILED))
    store.record_entry(ApplicationEntry(signature="sig-3", status=ApplicationStatus.MANUAL_REQUIRED))
    store.record_entry(ApplicationEntry(signature="sig-4", status=ApplicationStatus.SUBMITTED))

    assert store.already_prepared_signatures() == {"sig-1", "sig-3", "sig-4"}


def test_a_retried_failed_entry_can_become_draft_ready():
    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.FAILED))
    assert store.already_prepared_signatures() == set()

    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.DRAFT_READY))
    assert store.already_prepared_signatures() == {"sig-1"}


def test_draft_ready_entries_only_includes_unsent_drafts():
    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.DRAFT_READY))
    store.record_entry(ApplicationEntry(signature="sig-2", status=ApplicationStatus.SUBMITTED))
    store.record_entry(ApplicationEntry(signature="sig-3", status=ApplicationStatus.MANUAL_REQUIRED))

    assert set(store.draft_ready_entries().keys()) == {"sig-1"}


def test_draft_ready_stops_once_sent():
    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.DRAFT_READY))
    assert set(store.draft_ready_entries().keys()) == {"sig-1"}

    store.record_entry(ApplicationEntry(signature="sig-1", status=ApplicationStatus.SUBMITTED))
    assert store.draft_ready_entries() == {}
