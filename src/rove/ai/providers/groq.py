"""Groq — OpenAI-compatible endpoint, fast LPU inference, generous free
daily request cap. Second in the default `AI_PROVIDER_ORDER` (quality-first:
Gemini Flash goes first — see AI-PROVIDERS.md amendment, 2026-08-12)."""

from __future__ import annotations

from rove import config
from rove.ai.providers._openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    id = "groq"
    base_url = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(api_key or config.GROQ_API_KEY, model or config.GROQ_MODEL)
