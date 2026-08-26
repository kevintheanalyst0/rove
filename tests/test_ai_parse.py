"""ai/parse.py — tolerant parse-and-repair (P11). Never crashes; drops what
it can't salvage instead."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rove.ai.base import AiResult
from rove.ai.parse import (
    coerce_result,
    extract_json,
    match_ai_results,
    parse_batch_response,
    strip_code_fences,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_strip_code_fences_removes_markdown_json_fence():
    text = "```json\n[1, 2]\n```"
    assert strip_code_fences(text) == "[1, 2]"


def test_extract_json_ignores_prose_around_array():
    text = 'Here is the result:\n[{"id": "a", "score": 90}]\nHope this helps!'
    assert extract_json(text) == [{"id": "a", "score": 90}]


def test_extract_json_handles_fenced_object():
    text = '```json\n{"results": [{"id": "a", "score": 50}]}\n```'
    assert extract_json(text) == {"results": [{"id": "a", "score": 50}]}


def test_extract_json_raises_on_no_json():
    with pytest.raises(ValueError):
        extract_json("no json here at all")


def test_coerce_result_clamps_score_out_of_range():
    result = coerce_result(
        {"id": "sig1", "score": 150, "pros": [], "contras": [], "summary": "s"}
    )
    assert result.ai_score == 100

    result = coerce_result({"id": "sig1", "score": -10})
    assert result.ai_score == 0


def test_coerce_result_drops_missing_id():
    assert coerce_result({"score": 80}) is None


def test_coerce_result_drops_unparseable_score():
    assert coerce_result({"id": "sig1", "score": "not-a-number"}) is None


def test_coerce_result_coerces_non_list_pros_contras_to_empty():
    result = coerce_result(
        {"id": "sig1", "score": 80, "pros": "not a list", "contras": None}
    )
    assert result.pros == []
    assert result.contras == []


def test_coerce_result_filters_non_string_items_from_lists():
    result = coerce_result(
        {"id": "sig1", "score": 80, "pros": ["ok", 5, None, "also ok"]}
    )
    assert result.pros == ["ok", "also ok"]


def test_parse_batch_response_bare_array():
    text = '[{"id": "s1", "score": 90, "pros": [], "contras": [], "summary": "great"}]'
    results = parse_batch_response(text)
    assert len(results) == 1
    assert results[0].signature == "s1"
    assert results[0].ai_score == 90


def test_parse_batch_response_wrapped_in_results_object():
    text = '{"results": [{"id": "s1", "score": 70}]}'
    results = parse_batch_response(text)
    assert len(results) == 1
    assert results[0].signature == "s1"


def test_parse_batch_response_drops_unsalvageable_items_without_crashing():
    text = '[{"id": "s1", "score": 70}, {"score": 80}, {"id": "s2", "score": "bad"}]'
    results = parse_batch_response(text)
    assert [r.signature for r in results] == ["s1"]


def test_parse_batch_response_totally_malformed_returns_empty_list():
    assert parse_batch_response("this is not json at all, sorry!") == []


def test_parse_batch_response_non_list_non_results_dict_returns_empty():
    assert parse_batch_response('{"unexpected": "shape"}') == []


class _FakeJob:
    def __init__(self, signature: str) -> None:
        self.signature = signature


def test_match_ai_results_normal_case():
    jobs = [_FakeJob("s1"), _FakeJob("s2")]
    results = [
        AiResult(signature="s1", ai_score=80),
        AiResult(signature="s2", ai_score=60),
    ]
    matched = match_ai_results(jobs, results)
    assert set(matched) == {"s1", "s2"}
    assert matched["s1"].ai_score == 80


def test_match_ai_results_drops_id_not_in_requested_jobs():
    """EATP-026 / SEC-5: an id the model invented (or an attacker injected)
    that doesn't belong to any job actually sent must never surface as a
    result — this is the core containment ADR-006 relies on."""
    jobs = [_FakeJob("s1")]
    results = [
        AiResult(signature="s1", ai_score=40),
        AiResult(signature="attacker-injected", ai_score=100),
    ]
    matched = match_ai_results(jobs, results)
    assert set(matched) == {"s1"}


def test_match_ai_results_drops_ambiguous_duplicate_entirely():
    """Two competing results for the same id (e.g. an attacker trying to get
    a second, higher-scored copy accepted) are dropped entirely, not
    resolved by picking either one — see match_ai_results' own docstring."""
    jobs = [_FakeJob("s1")]
    results = [
        AiResult(signature="s1", ai_score=10),
        AiResult(signature="s1", ai_score=99),
    ]
    matched = match_ai_results(jobs, results)
    assert matched == {}


# --- EATP-026 / SEC-5: adversarial job-description fixture -----------------
#
# These don't call live AI (CLAUDE.md §7). Each fixture case's
# `simulated_llm_response` stands in for what a model *might* be tricked
# into emitting if `malicious_job_description` (embedded verbatim into the
# prompt by ai/prompts.py) actually succeeded at manipulating it. The test
# proves that even a "successful" injection at the LLM-output level still
# can't get an unrequested/duplicate id treated as a real result, because
# match_ai_results' signature-allowlist (ADR-006) sits between the raw model
# text and anything the app trusts.

with open(_FIXTURES_DIR / "adversarial_jobs.json", encoding="utf-8") as _f:
    _ADVERSARIAL_FIXTURE = json.load(_f)

_ADVERSARIAL_JOBS = [_FakeJob(job["signature"]) for job in _ADVERSARIAL_FIXTURE["jobs"]]


@pytest.mark.parametrize(
    "case",
    _ADVERSARIAL_FIXTURE["adversarial_cases"],
    ids=[case["name"] for case in _ADVERSARIAL_FIXTURE["adversarial_cases"]],
)
def test_adversarial_injection_is_contained(case):
    results = parse_batch_response(case["simulated_llm_response"])
    matched = match_ai_results(_ADVERSARIAL_JOBS, results)

    for signature in case["expect_signatures_present"]:
        assert signature in matched, f"expected {signature!r} to survive containment"
    for signature in case["expect_signatures_absent"]:
        assert signature not in matched, (
            f"{signature!r} should have been dropped by match_ai_results "
            f"but leaked through ({case['name']})"
        )
