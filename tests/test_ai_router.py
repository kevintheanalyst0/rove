"""ai/router.py — provider fallback order, daily-quota bookkeeping, and
graceful degradation when every provider fails. Uses a mock `Provider`;
no live AI calls (CLAUDE.md §7)."""

from __future__ import annotations

import pytest

from rove import config
from rove.ai.base import AiResult, Provider, ProviderError, QuotaExceededError
from rove.ai.router import AiRouter
from rove.ai.usage import UsageTracker
from rove.models import Job
from rove.profile import load_profile


@pytest.fixture(autouse=True)
def _isolate_usage_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AI_USAGE_FILE", tmp_path / "ai_usage.json")


class MockProvider(Provider):
    """Scripted provider: `behavior` is either an exception to raise or a
    list[AiResult] to return. `calls` records every invocation for assertions."""

    def __init__(self, provider_id: str, behavior, *, configured: bool = True) -> None:
        self.id = provider_id
        self._behavior = behavior
        self._configured = configured
        self.calls = 0

    @property
    def configured(self) -> bool:
        return self._configured

    def evaluate_batch(self, jobs, profile):
        self.calls += 1
        if isinstance(self._behavior, Exception):
            raise self._behavior
        return self._behavior


def _job(source_job_id: str = "1") -> Job:
    return Job(
        source="test",
        source_job_id=source_job_id,
        title="Data Analyst",
        description="x" * 250,
        url=f"http://example.com/{source_job_id}",
    )


PROFILE = load_profile()


def test_uses_the_first_configured_provider_in_order():
    ok_result = [AiResult(signature="s1", ai_score=90)]
    first = MockProvider("a", ok_result)
    second = MockProvider("b", ok_result)
    router = AiRouter({"a": first, "b": second}, order=["a", "b"], usage=UsageTracker())

    results = router.evaluate_batch([_job()], PROFILE)

    assert results == ok_result
    assert first.calls == 1
    assert second.calls == 0


def test_falls_back_to_next_provider_on_quota_exceeded_and_marks_exhausted():
    usage = UsageTracker()
    ok_result = [AiResult(signature="s1", ai_score=70)]
    first = MockProvider("a", QuotaExceededError("daily quota exceeded per day"))
    second = MockProvider("b", ok_result)
    router = AiRouter({"a": first, "b": second}, order=["a", "b"], usage=usage)

    results = router.evaluate_batch([_job()], PROFILE)

    assert results == ok_result
    assert first.calls == 1
    assert second.calls == 1
    assert usage.is_exhausted("a") is True
    assert usage.is_exhausted("b") is False


def test_exhausted_provider_from_persisted_usage_is_never_called():
    usage = UsageTracker()
    usage.mark_exhausted("a")
    ok_result = [AiResult(signature="s1", ai_score=70)]
    first = MockProvider("a", ok_result)  # would succeed, but must not be tried
    second = MockProvider("b", ok_result)
    router = AiRouter({"a": first, "b": second}, order=["a", "b"], usage=usage)

    results = router.evaluate_batch([_job()], PROFILE)

    assert results == ok_result
    assert first.calls == 0
    assert second.calls == 1


def test_provider_error_falls_back_for_this_batch_but_is_not_marked_exhausted():
    usage = UsageTracker()
    ok_result = [AiResult(signature="s1", ai_score=70)]
    first = MockProvider("a", ProviderError("transient failure"))
    second = MockProvider("b", ok_result)
    router = AiRouter({"a": first, "b": second}, order=["a", "b"], usage=usage)

    router.evaluate_batch([_job()], PROFILE)

    assert usage.is_exhausted("a") is False

    # Next batch: "a" is tried again since it was never marked exhausted.
    first._behavior = ok_result
    results = router.evaluate_batch([_job()], PROFILE)
    assert results == ok_result
    assert first.calls == 2


def test_unconfigured_provider_is_skipped():
    ok_result = [AiResult(signature="s1", ai_score=70)]
    first = MockProvider("a", ok_result, configured=False)
    second = MockProvider("b", ok_result)
    router = AiRouter({"a": first, "b": second}, order=["a", "b"], usage=UsageTracker())

    router.evaluate_batch([_job()], PROFILE)

    assert first.calls == 0
    assert second.calls == 1


def test_all_providers_failing_degrades_to_empty_list_without_raising():
    first = MockProvider("a", QuotaExceededError("per day"))
    second = MockProvider("b", ProviderError("boom"))
    router = AiRouter({"a": first, "b": second}, order=["a", "b"], usage=UsageTracker())

    results = router.evaluate_batch([_job()], PROFILE)

    assert results == []


def test_empty_job_list_returns_empty_without_calling_any_provider():
    provider = MockProvider("a", [AiResult(signature="s1", ai_score=70)])
    router = AiRouter({"a": provider}, order=["a"], usage=UsageTracker())

    assert router.evaluate_batch([], PROFILE) == []
    assert provider.calls == 0
