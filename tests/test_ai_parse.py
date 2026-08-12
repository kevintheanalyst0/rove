"""ai/parse.py — tolerant parse-and-repair (P11). Never crashes; drops what
it can't salvage instead."""

from __future__ import annotations

import pytest

from career_radar.ai.base import AiResult
from career_radar.ai.parse import (
    coerce_result,
    extract_json,
    match_ai_results,
    parse_batch_response,
    strip_code_fences,
)


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
