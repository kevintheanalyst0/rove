"""Groq — OpenAI-compatible endpoint, fast LPU inference, generous free
daily request cap. Second in the default `AI_PROVIDER_ORDER` (quality-first:
Gemini Flash goes first — see AI-PROVIDERS.md amendment, 2026-08-12)."""

from __future__ import annotations

import time

from rove import config
from rove.ai.base import AiResult
from rove.ai.providers._openai_compatible import OpenAICompatibleProvider
from rove.models import Job
from rove.profile import Profile

# Groq's free tier allows 8,000 tokens per minute; a batch of 10 jobs asked for 9,353 and was refused (HTTP 413,
# 2026-11-24). Send it in halves, one per minute window.
GROQ_CHUNK = 5
GROQ_CHUNK_PAUSE_SECONDS = 61.0


class GroqProvider(OpenAICompatibleProvider):
    id = "groq"
    base_url = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(api_key or config.GROQ_API_KEY, model or config.GROQ_MODEL)

    def evaluate_batch(self, jobs: list[Job], profile: Profile) -> list[AiResult]:
        results: list[AiResult] = []
        for start in range(0, len(jobs), GROQ_CHUNK):
            if start:
                time.sleep(GROQ_CHUNK_PAUSE_SECONDS)
            results.extend(super().evaluate_batch(jobs[start : start + GROQ_CHUNK], profile))
        return results
