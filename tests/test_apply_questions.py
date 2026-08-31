"""Tests for AI-answered screening questions (EATP-034, ADR-011). Uses a
mocked `Provider` — no live AI calls (CLAUDE.md §7)."""

from __future__ import annotations

import json

import pytest

from rove import config
from rove.ai.base import Provider, ProviderError
from rove.ai.router import AiRouter
from rove.ai.usage import UsageTracker
from rove.apply.browser import FieldKind, FormField
from rove.apply.questions import answer_form_questions, parse_answers_response
from rove.profile import load_profile

PROFILE = load_profile()


@pytest.fixture(autouse=True)
def _isolate_usage_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AI_USAGE_FILE", tmp_path / "ai_usage.json")


class MockQuestionProvider(Provider):
    """`behavior` is either an Exception to raise or a raw text string to
    return from `answer_questions`."""

    def __init__(self, provider_id: str, behavior) -> None:
        self.id = provider_id
        self._behavior = behavior
        self.prompts: list[str] = []

    @property
    def configured(self) -> bool:
        return True

    def evaluate_batch(self, jobs, profile):
        raise NotImplementedError

    def answer_questions(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self._behavior, Exception):
            raise self._behavior
        return self._behavior


def _router(provider: Provider) -> AiRouter:
    return AiRouter({provider.id: provider}, order=[provider.id], usage=UsageTracker())


def _custom_field(label: str, options: list[str] | None = None, multi: bool = False) -> FormField:
    return FormField(
        selector=f"#{label}",
        kind=FieldKind.CUSTOM,
        label=label,
        options=options or [],
        multi=multi,
    )


# ---------------------------------------------------------------------------
# parse_answers_response
# ---------------------------------------------------------------------------


def test_parse_answers_response_matches_by_id():
    text = json.dumps({"answers": [{"id": "q0", "answer": "Inmediata"}]})
    assert parse_answers_response(text, expected_ids={"q0"}) == {"q0": "Inmediata"}


def test_parse_answers_response_strips_markdown_fences():
    text = "```json\n" + json.dumps({"answers": [{"id": "q0", "answer": "Sí"}]}) + "\n```"
    assert parse_answers_response(text, expected_ids={"q0"}) == {"q0": "Sí"}


def test_parse_answers_response_drops_an_invented_id():
    text = json.dumps({"answers": [{"id": "q99", "answer": "..."}]})
    assert parse_answers_response(text, expected_ids={"q0"}) == {}


def test_parse_answers_response_drops_duplicate_ids_rather_than_guessing():
    text = json.dumps(
        {"answers": [{"id": "q0", "answer": "A"}, {"id": "q0", "answer": "B"}]}
    )
    assert parse_answers_response(text, expected_ids={"q0"}) == {}


def test_parse_answers_response_returns_empty_on_garbage():
    assert parse_answers_response("not json at all", expected_ids={"q0"}) == {}


# ---------------------------------------------------------------------------
# answer_form_questions
# ---------------------------------------------------------------------------


def test_answer_form_questions_returns_empty_when_no_custom_fields():
    identity_only = [FormField(selector="#email", kind=FieldKind.IDENTITY, label="email")]
    provider = MockQuestionProvider("mock", "should never be called")
    result = answer_form_questions(
        _router(provider),
        identity_only,
        company="Acme",
        job_title="Data Analyst",
        job_description="...",
        profile=PROFILE,
    )
    assert result == {}
    assert provider.prompts == []


def test_answer_form_questions_maps_ids_back_to_labels():
    fields = [_custom_field("LinkedIn Profile"), _custom_field("Why this role?")]
    response = json.dumps(
        {
            "answers": [
                {"id": "q0", "answer": "https://linkedin.com/in/kevin"},
                {"id": "q1", "answer": "Porque encaja con mi experiencia en BI."},
            ]
        }
    )
    provider = MockQuestionProvider("mock", response)

    result = answer_form_questions(
        _router(provider),
        fields,
        company="Acme",
        job_title="Data Analyst",
        job_description="...",
        profile=PROFILE,
    )

    assert result == {
        "LinkedIn Profile": "https://linkedin.com/in/kevin",
        "Why this role?": "Porque encaja con mi experiencia en BI.",
    }
    # the prompt actually carries the question text and job context
    assert "LinkedIn Profile" in provider.prompts[0]
    assert "Acme" in provider.prompts[0]
    assert "Data Analyst" in provider.prompts[0]


def test_answer_form_questions_includes_options_for_constrained_choice_fields():
    fields = [_custom_field("Are you authorized to work?", options=["Yes", "No"])]
    provider = MockQuestionProvider("mock", json.dumps({"answers": []}))

    answer_form_questions(
        _router(provider),
        fields,
        company="Acme",
        job_title="Data Analyst",
        job_description="...",
        profile=PROFILE,
    )

    assert "OPTIONS: Yes, No" in provider.prompts[0]


def test_answer_form_questions_never_states_a_real_salary_number_in_the_prompt():
    fields = [_custom_field("What are your salary expectations?")]
    provider = MockQuestionProvider("mock", json.dumps({"answers": []}))

    answer_form_questions(
        _router(provider),
        fields,
        company="Acme",
        job_title="Data Analyst",
        job_description="...",
        profile=PROFILE,
    )

    prompt = provider.prompts[0]
    assert str(PROFILE.application.salary_numeric_placeholder) in prompt
    assert "SALARY POLICY" in prompt


def test_answer_form_questions_returns_empty_when_every_provider_fails():
    fields = [_custom_field("Why this role?")]
    provider = MockQuestionProvider("mock", ProviderError("boom"))

    result = answer_form_questions(
        _router(provider),
        fields,
        company="Acme",
        job_title="Data Analyst",
        job_description="...",
        profile=PROFILE,
    )

    assert result == {}
