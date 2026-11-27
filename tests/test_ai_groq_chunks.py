"""Groq refuses big batches on its free tier, so the provider sends them in halves."""

from rove import config
from rove.ai.providers import groq
from rove.ai.providers._openai_compatible import OpenAICompatibleProvider


def test_batches_are_split_and_paced(monkeypatch):
    sizes: list[int] = []
    pauses: list[float] = []

    def fake(self, jobs, profile):
        sizes.append(len(jobs))
        return list(jobs)

    monkeypatch.setattr(OpenAICompatibleProvider, "evaluate_batch", fake)
    monkeypatch.setattr(groq.time, "sleep", pauses.append)

    out = groq.GroqProvider(api_key="x").evaluate_batch(list(range(12)), None)

    assert sizes == [5, 5, 2]
    assert pauses == [groq.GROQ_CHUNK_PAUSE_SECONDS] * 2
    assert out == list(range(12))


def test_small_batch_does_not_wait(monkeypatch):
    pauses: list[float] = []
    monkeypatch.setattr(OpenAICompatibleProvider, "evaluate_batch", lambda self, jobs, profile: [])
    monkeypatch.setattr(groq.time, "sleep", pauses.append)
    groq.GroqProvider(api_key="x").evaluate_batch([1, 2, 3], None)
    assert pauses == []


def test_openrouter_default_is_the_free_alias():
    assert config.OPENROUTER_MODEL.endswith("free")
