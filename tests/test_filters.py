"""Tests for the Layer 1 quality gate (EATP-009).

Two layers of coverage:
- Synthetic `Job`s isolate each individual check (title/company, English,
  remote, staleness, caution-flag attachment).
- The real fixture (`tests/fixtures/latest_jobs.json`, 30 real historical
  postings) exercises `gate()` end-to-end — this is the "57 non-remote
  leaks" scenario from ADR-002: most of this fixture's `remote: true/false`
  legacy bool is untrustworthy, so the gate must classify purely from
  title+description text, independent of that bool.
"""

from __future__ import annotations

import json
from pathlib import Path

from career_radar import config
from career_radar.models import Job, RemoteStatus
from career_radar.quality.filters import gate

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "latest_jobs.json").read_text())


def _job(**overrides) -> Job:
    defaults = {
        "source": "test",
        "source_job_id": "1",
        "title": "Data Analyst",
        "company": "Acme",
        "description": "Remoto 100%. Analiza datos con SQL y Power BI para el equipo de negocio.",
        "url": "https://example.com/1",
        "days_old": 1,
    }
    defaults.update(overrides)
    return Job(**defaults)


# ---------------------------------------------------------------------------
# Title/company exclusion (ADR-009: absolute categories only)
# ---------------------------------------------------------------------------


def test_absolute_excluded_title_is_rejected():
    result = gate([_job(title="Graphic Designer")])

    assert result.kept == []
    assert result.rejected[0][1] == "excluded_title_or_company"


def test_excluded_company_is_rejected():
    result = gate([_job(company="BairesDev")])

    assert result.kept == []
    assert result.rejected[0][1] == "excluded_title_or_company"


def test_ambiguous_caution_title_is_not_rejected_and_is_flagged_for_the_matcher():
    # Kevin's "Analista administrativo" case: an ambiguous title must reach
    # the description-reading stages, never hard-reject at the gate.
    result = gate([_job(title="Financial Analyst")])

    assert result.rejected == []
    assert result.kept[0].title_caution_flags  # advisory, attached as data


def test_plain_unremarkable_title_is_kept_with_no_caution_flags():
    result = gate([_job(title="Analista administrativo")])

    assert result.rejected == []
    assert result.kept[0].title_caution_flags == []


# ---------------------------------------------------------------------------
# Advanced English
# ---------------------------------------------------------------------------


def test_advanced_english_required_is_rejected_and_flag_is_set_on_the_job():
    result = gate([_job(description="Remoto 100%. Se requiere inglés avanzado.")])

    assert result.kept == []
    job, reason = result.rejected[0]
    assert reason == "advanced_english_required"
    assert job.english_required is True


# ---------------------------------------------------------------------------
# Remote hard-gate (ADR-002)
# ---------------------------------------------------------------------------


def test_remote_job_is_kept_with_status_and_evidence_set():
    result = gate([_job(description="Puesto 100% remoto, trabaja desde donde quieras.")])

    assert result.rejected == []
    job = result.kept[0]
    assert job.remote_status == RemoteStatus.REMOTE
    assert job.remote_evidence


def test_hybrid_phrase_overrides_remote_and_is_rejected():
    result = gate([_job(description="Remoto, modelo híbrido con 2 días en oficina.")])

    assert result.kept == []
    job, reason = result.rejected[0]
    assert reason == "not_remote:hybrid"
    assert job.remote_status == RemoteStatus.HYBRID
    assert job.remote_evidence


def test_ambiguous_remote_signal_is_rejected_as_unknown_not_shown_by_default():
    result = gate([_job(description="Analista de datos con experiencia en SQL.")])

    assert result.kept == []
    job, reason = result.rejected[0]
    assert reason == "not_remote:unknown"
    assert job.remote_status == RemoteStatus.UNKNOWN


def test_rare_onsite_within_monthly_tolerance_still_passes_as_remote():
    result = gate([_job(description="Trabajo remoto, 1 dia al mes en oficina.")])

    assert result.rejected == []
    assert result.kept[0].remote_status == RemoteStatus.REMOTE


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def test_stale_job_beyond_the_recency_window_is_rejected():
    result = gate([_job(days_old=config.MAX_DAYS_OLD + 1)])

    assert result.kept == []
    assert result.rejected[0][1] == "stale"


def test_job_within_the_recency_window_is_kept():
    result = gate([_job(days_old=config.MAX_DAYS_OLD)])

    assert result.rejected == []


# ---------------------------------------------------------------------------
# gate() never crashes the batch
# ---------------------------------------------------------------------------


def test_gate_processes_every_job_independently():
    jobs = [_job(source_job_id="1", title="Graphic Designer"), _job(source_job_id="2")]

    result = gate(jobs)

    assert len(result.kept) + len(result.rejected) == 2
    assert result.kept[0].source_job_id == "2"


# ---------------------------------------------------------------------------
# Real fixture — ADR-002's "57 non-remote leaks" scenario, end-to-end
# ---------------------------------------------------------------------------


def _job_from_fixture(item: dict) -> Job:
    j = item["job"]
    return Job(
        source=j["source"],
        source_job_id=j["job_id"],
        title=j["title"],
        company=j.get("company") or "Unknown",
        description=j.get("description", ""),
        url=j["url"],
        days_old=j.get("days_old", 999),
    )


def test_gate_on_real_fixture_rejects_every_non_remote_leak_independent_of_the_legacy_bool():
    jobs = [_job_from_fixture(item) for item in FIXTURES]

    result = gate(jobs)

    # Computed once from the real fixture text (independent of the legacy
    # `remote: true/false` bool, which this gate never even reads): 12 of
    # the 30 postings classify as genuinely remote from their own text.
    assert len(result.kept) == 12
    assert len(result.rejected) == 18
    assert all(job.remote_status == RemoteStatus.REMOTE for job in result.kept)

    kept_titles = {job.title for job in result.kept}
    assert "Data Analyst" in kept_titles
    assert "Business Analyst" in kept_titles

    # A genuinely non-remote leak from the fixture (legacy bool said nothing
    # useful either way) — rejected by the gate on the description text.
    rejected_titles = {job.title: reason for job, reason in result.rejected}
    assert rejected_titles["Consultor Qlik Sense"] == "not_remote:hybrid"
    assert rejected_titles["Analista de Reportes JR"] == "not_remote:onsite"
    # Absolute title exclusion still wins even for a remote-sounding posting.
    assert rejected_titles["Quality Assurance Engineer Senior"] == "excluded_title_or_company"
