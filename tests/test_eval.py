"""Match-quality evaluation harness (EATP-017, P22): the labels store and the
precision/false-positive report computed from it. No live AI here — labels
are Kevin's, fixtures stand in for them (CLAUDE.md §7)."""

from __future__ import annotations

import pytest

from rove import config
from rove.eval import labels as labels_store
from rove.eval import report as report_mod
from rove.eval.labels import BadReason, Label


@pytest.fixture(autouse=True)
def _isolated_eval_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVAL_LABELS_FILE", tmp_path / "labels.jsonl")
    monkeypatch.setattr(config, "EVAL_BASELINE_FILE", tmp_path / "baseline.json")


# ---------------------------------------------------------------------------
# labels.py
# ---------------------------------------------------------------------------


def test_record_and_read_back_a_single_label():
    labels_store.record_label("sig-1", Label.GOOD)

    entries = labels_store.latest_labels()
    assert entries["sig-1"].label == Label.GOOD
    assert entries["sig-1"].reason is None


def test_bad_label_keeps_its_reason():
    labels_store.record_label("sig-1", Label.BAD, BadReason.NOT_REMOTE)

    assert labels_store.latest_labels()["sig-1"].reason == BadReason.NOT_REMOTE


def test_good_label_ignores_a_reason_if_one_is_passed():
    labels_store.record_label("sig-1", Label.GOOD, BadReason.OTHER)

    assert labels_store.latest_labels()["sig-1"].reason is None


def test_a_later_label_overrides_an_earlier_one_for_the_same_signature():
    labels_store.record_label("sig-1", Label.BAD, BadReason.OFF_ROLE)
    labels_store.record_label("sig-1", Label.GOOD)

    entries = labels_store.latest_labels()
    assert entries["sig-1"].label == Label.GOOD
    assert entries["sig-1"].reason is None


def test_no_file_yet_reads_as_empty():
    assert labels_store.latest_labels() == {}


# ---------------------------------------------------------------------------
# report.py — compute_report
# ---------------------------------------------------------------------------


def test_compute_report_with_no_labels_has_no_precision():
    report = report_mod.compute_report([])

    assert report.total_labeled == 0
    assert report.precision is None
    assert report.fp_reasons == {}


def test_compute_report_precision_and_fp_breakdown():
    labels_store.record_label("sig-1", Label.GOOD)
    labels_store.record_label("sig-2", Label.GOOD)
    labels_store.record_label("sig-3", Label.BAD, BadReason.NOT_REMOTE)
    labels_store.record_label("sig-4", Label.BAD, BadReason.NOT_REMOTE)
    labels_store.record_label("sig-5", Label.BAD, BadReason.ENGLISH)

    report = report_mod.compute_report(labels_store.latest_labels().values())

    assert report.total_labeled == 5
    assert report.good == 2
    assert report.bad == 3
    assert report.precision == pytest.approx(2 / 5)
    assert report.fp_reasons == {"not_remote": 2, "english": 1}


def test_compute_report_counts_a_bad_label_without_a_reason_as_unspecified():
    labels_store.record_label("sig-1", Label.BAD)

    report = report_mod.compute_report(labels_store.latest_labels().values())

    assert report.fp_reasons == {"unspecified": 1}


# ---------------------------------------------------------------------------
# report.py — baseline + generate_report
# ---------------------------------------------------------------------------


def test_first_report_ever_becomes_the_baseline_with_nothing_to_compare():
    labels_store.record_label("sig-1", Label.GOOD)
    labels_store.record_label("sig-2", Label.BAD, BadReason.OFF_ROLE)

    report, baseline = report_mod.generate_report()

    assert report.precision == pytest.approx(0.5)
    assert baseline is None
    assert report_mod.load_baseline().precision == pytest.approx(0.5)


def test_a_later_report_compares_against_the_saved_baseline():
    labels_store.record_label("sig-1", Label.GOOD)
    labels_store.record_label("sig-2", Label.BAD, BadReason.OFF_ROLE)
    report_mod.generate_report()  # sets the baseline at 50%

    labels_store.record_label("sig-3", Label.GOOD)
    labels_store.record_label("sig-4", Label.GOOD)
    report, baseline = report_mod.generate_report()

    assert report.precision == pytest.approx(3 / 4)
    assert baseline.precision == pytest.approx(0.5)


def test_set_baseline_resets_the_comparison_point():
    labels_store.record_label("sig-1", Label.BAD, BadReason.OFF_ROLE)
    report_mod.generate_report()  # baseline at 0%

    labels_store.record_label("sig-2", Label.GOOD)
    report, baseline = report_mod.generate_report(set_baseline=True)

    assert baseline is None
    assert report_mod.load_baseline().precision == report.precision


def test_load_baseline_is_none_when_nothing_saved_yet():
    assert report_mod.load_baseline() is None


def test_generate_report_with_no_labels_never_creates_an_empty_baseline():
    report, baseline = report_mod.generate_report()
    assert report.precision is None
    assert baseline is None
    assert report_mod.load_baseline() is None  # no meaningless baseline locked in

    labels_store.record_label("sig-1", Label.GOOD)
    report, baseline = report_mod.generate_report()  # first real report still becomes the baseline
    assert report.precision == pytest.approx(1.0)
    assert baseline is None
    assert report_mod.load_baseline().precision == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# report.py — format_report
# ---------------------------------------------------------------------------


def test_format_report_with_no_labels():
    report = report_mod.compute_report([])

    assert "todavía" in report_mod.format_report(report, None)


def test_format_report_includes_precision_and_fp_reasons():
    labels_store.record_label("sig-1", Label.GOOD)
    labels_store.record_label("sig-2", Label.BAD, BadReason.NOT_REMOTE)
    report = report_mod.compute_report(labels_store.latest_labels().values())

    text = report_mod.format_report(report, None)

    assert "50%" in text
    assert "not_remote" in text


def test_format_report_shows_the_delta_against_a_baseline():
    baseline_report = report_mod.compute_report(
        [labels_store.LabelEntry(signature="sig-1", label=Label.BAD, reason=BadReason.OFF_ROLE)]
    )
    current_report = report_mod.compute_report(
        [
            labels_store.LabelEntry(signature="sig-1", label=Label.GOOD),
            labels_store.LabelEntry(signature="sig-2", label=Label.GOOD),
        ]
    )

    text = report_mod.format_report(current_report, baseline_report)

    assert "Baseline: 0%" in text
    assert "100%" in text
