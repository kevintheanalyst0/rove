"""Provider-internals tests: retry/backoff, daily-quota vs transient error
classification, and the `response_format` fallback — with a fake SDK client,
never a live call (CLAUDE.md §7)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from career_radar import config
from career_radar.ai.base import ProviderError, QuotaExceededError
from career_radar.ai.providers.gemini import GeminiProvider
from career_radar.ai.providers.groq import GroqProvider
from career_radar.models import Job
from career_radar.profile import load_profile


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    # Keep retry backoff near-instant so retry tests don't sleep for real.
    monkeypatch.setattr(config, "AI_MAX_RETRIES", 3)
    monkeypatch.setattr(config, "AI_RETRY_BACKOFF_SECONDS", 0.001)


PROFILE = load_profile()
RESULT_TEXT = '{"results": [{"id": "s1", "score": 80, "pros": [], "contras": [], "summary": "ok"}]}'


def _job() -> Job:
    return Job(
        source="test",
        source_job_id="1",
        title="Data Analyst",
        description="x" * 250,
        url="http://example.com/1",
    )


class _ApiError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FakeCompletions:
    def __init__(self, outcomes: list) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict] = []

    def create(self, *, model, messages, response_format=None):
        self.calls.append({"model": model, "response_format": response_format})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))]
        )


class _FakeOpenAIClient:
    def __init__(self, outcomes: list) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(outcomes))


def _wire_fake_client(provider: GroqProvider, outcomes: list) -> _FakeOpenAIClient:
    fake = _FakeOpenAIClient(outcomes)
    provider._client = fake
    return fake


def test_groq_happy_path_returns_parsed_results():
    provider = GroqProvider(api_key="fake-key")
    fake = _wire_fake_client(provider, [RESULT_TEXT])

    results = provider.evaluate_batch([_job()], PROFILE)

    assert len(results) == 1
    assert results[0].signature == "s1"
    assert fake.chat.completions.calls[0]["response_format"] == {"type": "json_object"}


def test_groq_without_api_key_raises_provider_error_without_calling_client():
    provider = GroqProvider(api_key=None)
    with pytest.raises(ProviderError):
        provider.evaluate_batch([_job()], PROFILE)


def test_groq_falls_back_when_response_format_unsupported():
    provider = GroqProvider(api_key="fake-key")
    unsupported = _ApiError(
        "400 invalid: response_format not supported for this model", 400
    )
    fake = _wire_fake_client(provider, [unsupported, RESULT_TEXT])

    results = provider.evaluate_batch([_job()], PROFILE)

    assert len(results) == 1
    assert fake.chat.completions.calls[0]["response_format"] == {"type": "json_object"}
    assert fake.chat.completions.calls[1]["response_format"] is None


def test_groq_daily_quota_error_raises_quota_exceeded_without_retrying():
    provider = GroqProvider(api_key="fake-key")
    daily = _ApiError("429: rate limit reached, requests per day quota exceeded", 429)
    fake = _wire_fake_client(provider, [daily])

    with pytest.raises(QuotaExceededError):
        provider.evaluate_batch([_job()], PROFILE)

    assert len(fake.chat.completions.calls) == 1  # no retry burned against quota


def test_groq_transient_error_is_retried_then_succeeds():
    provider = GroqProvider(api_key="fake-key")
    transient = _ApiError("503 service unavailable", 503)
    fake = _wire_fake_client(provider, [transient, RESULT_TEXT])

    results = provider.evaluate_batch([_job()], PROFILE)

    assert len(results) == 1
    assert len(fake.chat.completions.calls) == 2


def test_groq_transient_error_beyond_retry_budget_raises_provider_error():
    provider = GroqProvider(api_key="fake-key")
    transient = _ApiError("503 service unavailable", 503)
    _wire_fake_client(provider, [transient, transient, transient])

    with pytest.raises(ProviderError):
        provider.evaluate_batch([_job()], PROFILE)


class _FakeModels:
    def __init__(self, outcomes: list) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def generate_content(self, *, model, contents, config):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


def test_gemini_happy_path_returns_parsed_results():
    provider = GeminiProvider("gemini_flash", "gemini-2.5-flash", api_key="fake-key")
    fake_models = _FakeModels([RESULT_TEXT])
    provider._client = SimpleNamespace(models=fake_models)

    results = provider.evaluate_batch([_job()], PROFILE)

    assert len(results) == 1
    assert results[0].signature == "s1"


def test_gemini_daily_quota_error_raises_quota_exceeded():
    provider = GeminiProvider("gemini_flash", "gemini-2.5-flash", api_key="fake-key")
    daily = _ApiError("429 RESOURCE_EXHAUSTED: daily quota exceeded", 429)
    provider._client = SimpleNamespace(models=_FakeModels([daily]))

    with pytest.raises(QuotaExceededError):
        provider.evaluate_batch([_job()], PROFILE)
