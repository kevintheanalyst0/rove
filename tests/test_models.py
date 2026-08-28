from __future__ import annotations

import pytest
from pydantic import ValidationError

from rove.models import (
    Fit,
    Grade,
    Job,
    RemoteStatus,
    ScoredJob,
    content_signature,
    grade_from_score,
    normalize,
)


def make_job(**overrides) -> Job:
    defaults = {
        "source": "greenhouse",
        "source_job_id": "1",
        "title": "Analista de Datos",
        "company": "Acme",
        "description": "Buscamos analista con SQL y Power BI",
        "url": "https://example.com/1",
    }
    defaults.update(overrides)
    return Job(**defaults)


# ---------------------------------------------------------------------------
# Job validation
# ---------------------------------------------------------------------------


def test_job_requires_core_fields():
    with pytest.raises(ValidationError):
        Job(source="greenhouse")  # missing source_job_id, title, url


def test_job_defaults():
    job = make_job()
    assert job.company == "Acme"
    assert job.remote_status == RemoteStatus.UNKNOWN
    assert job.days_old == 999
    assert job.remote_evidence == []


def test_job_company_defaults_to_unknown_when_omitted():
    job = Job(source="occ", source_job_id="2", title="Analista", url="https://x")
    assert job.company == "Unknown"


# ---------------------------------------------------------------------------
# Thin-description flag (P21)
# ---------------------------------------------------------------------------


def test_thin_description_flagged_when_short():
    job = make_job(description="Muy corta")
    assert job.thin_description is True


def test_thin_description_flagged_when_empty():
    job = make_job(description="")
    assert job.thin_description is True


def test_thin_description_false_for_a_real_description():
    job = make_job(description="A" * 250)
    assert job.thin_description is False


# ---------------------------------------------------------------------------
# Content signature (ADR-001)
# ---------------------------------------------------------------------------


def test_signature_is_populated_automatically():
    job = make_job()
    assert job.signature
    assert len(job.signature) == 40  # sha1 hexdigest


def test_signature_stable_for_identical_content():
    job1 = make_job()
    job2 = make_job()
    assert job1.signature == job2.signature


def test_signature_ignores_case_accents_and_whitespace():
    job1 = make_job(company="Acme", title="Analista de Datos")
    job2 = make_job(company="  ACME  ", title="analísta   de dátos")
    assert job1.signature == job2.signature


def test_signature_ignores_dates_and_req_ids():
    job1 = make_job(description="Vacante publicada hoy req12345, unete ya")
    job2 = make_job(description="Vacante publicada ayer req99999, unete ya")
    assert job1.signature == job2.signature


def test_signature_changes_with_real_content():
    job1 = make_job(title="Analista de Datos")
    job2 = make_job(title="Analista de Negocios")
    assert job1.signature != job2.signature


def test_content_signature_truncates_description_to_400_normalized_chars():
    long_desc = "palabra " * 200  # far more than 400 chars once normalized
    sig1 = content_signature("Acme", "Analista", long_desc + "cola-diferente-1")
    sig2 = content_signature("Acme", "Analista", long_desc + "cola-diferente-2")
    assert sig1 == sig2  # the differing tail falls past the 400-char cut


def test_normalize_handles_empty_string():
    assert normalize("") == ""


# ---------------------------------------------------------------------------
# grade_from_score — the single canonical mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, Grade.A_PLUS),
        (90, Grade.A_PLUS),
        (89, Grade.A),
        (80, Grade.A),
        (79, Grade.B),
        (70, Grade.B),
        (69, Grade.C),
        (55, Grade.C),
        (54, Grade.D),
        (0, Grade.D),
    ],
)
def test_grade_from_score_boundaries(score, expected):
    assert grade_from_score(score) == expected


# ---------------------------------------------------------------------------
# ScoredJob — final_score/grade are derived, never trusted from the caller
# ---------------------------------------------------------------------------


def test_scored_job_uses_ai_score_when_evaluated():
    job = make_job()
    scored = ScoredJob(
        job=job,
        prefilter_score=40,
        prefilter_passed=True,
        ai_evaluated=True,
        ai_score=92,
        fit=Fit.STRONG,
    )
    assert scored.final_score == 92
    assert scored.grade == Grade.A_PLUS


def test_scored_job_uses_prefilter_score_when_not_ai_evaluated():
    job = make_job()
    scored = ScoredJob(
        job=job,
        prefilter_score=60,
        prefilter_passed=True,
        fit=Fit.MODERATE,
    )
    assert scored.final_score == 60
    assert scored.grade == Grade.C


def test_scored_job_grade_always_matches_final_score_even_if_caller_passes_wrong_grade():
    job = make_job()
    scored = ScoredJob(
        job=job,
        prefilter_score=10,
        prefilter_passed=False,
        fit=Fit.POOR,
        grade=Grade.A_PLUS,  # caller passes a wrong/stale grade
    )
    assert scored.grade == Grade.D  # recomputed from final_score, not trusted
