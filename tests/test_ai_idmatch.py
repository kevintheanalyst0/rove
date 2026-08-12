"""ADR-006 — stable-id round-trip. An AI result must NEVER be attributed to
the wrong job. These tests simulate exactly the failure modes an LLM can
introduce: reordering, omitting, duplicating, or inventing an id.
"""

from __future__ import annotations

from career_radar.ai.base import AiResult
from career_radar.ai.parse import match_ai_results
from career_radar.models import Job


def _job(source_job_id: str, title: str) -> Job:
    return Job(
        source="test",
        source_job_id=source_job_id,
        title=title,
        description="x" * 250,
        url=f"http://example.com/{source_job_id}",
    )


def test_matches_every_job_when_ids_are_in_order():
    jobs = [
        _job("1", "Data Analyst"),
        _job("2", "BI Analyst"),
        _job("3", "Business Analyst"),
    ]
    results = [
        AiResult(signature=job.signature, ai_score=70 + i) for i, job in enumerate(jobs)
    ]

    matched = match_ai_results(jobs, results)

    assert len(matched) == 3
    for job, result in zip(jobs, results, strict=True):
        assert matched[job.signature] is result


def test_matches_correctly_even_when_ai_reorders_results():
    jobs = [
        _job("1", "Data Analyst"),
        _job("2", "BI Analyst"),
        _job("3", "Business Analyst"),
    ]
    # AI returns them in reverse order — must still land on the right job.
    results = [
        AiResult(signature=jobs[2].signature, ai_score=30, summary="third"),
        AiResult(signature=jobs[0].signature, ai_score=10, summary="first"),
        AiResult(signature=jobs[1].signature, ai_score=20, summary="second"),
    ]

    matched = match_ai_results(jobs, results)

    assert matched[jobs[0].signature].summary == "first"
    assert matched[jobs[1].signature].summary == "second"
    assert matched[jobs[2].signature].summary == "third"


def test_omitted_job_has_no_match_rather_than_a_guess():
    jobs = [_job("1", "Data Analyst"), _job("2", "BI Analyst")]
    # AI only returned a result for the first job.
    results = [AiResult(signature=jobs[0].signature, ai_score=80)]

    matched = match_ai_results(jobs, results)

    assert jobs[0].signature in matched
    assert jobs[1].signature not in matched


def test_duplicate_id_is_treated_as_unanalyzed_not_guessed():
    jobs = [_job("1", "Data Analyst")]
    # AI returned two different analyses for the same id — ambiguous, can't
    # trust either one, so neither is used.
    results = [
        AiResult(signature=jobs[0].signature, ai_score=90, summary="first copy"),
        AiResult(signature=jobs[0].signature, ai_score=10, summary="second copy"),
    ]

    matched = match_ai_results(jobs, results)

    assert jobs[0].signature not in matched


def test_invented_or_unknown_id_is_dropped_not_mismatched():
    jobs = [_job("1", "Data Analyst")]
    results = [
        AiResult(signature=jobs[0].signature, ai_score=80),
        AiResult(signature="this-id-was-never-sent", ai_score=99),
    ]

    matched = match_ai_results(jobs, results)

    assert set(matched) == {jobs[0].signature}


def test_empty_results_matches_nothing_without_erroring():
    jobs = [_job("1", "Data Analyst")]
    assert match_ai_results(jobs, []) == {}
