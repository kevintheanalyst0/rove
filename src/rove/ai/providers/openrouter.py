"""OpenRouter — aggregator with `:free` models behind one OpenAI-compatible
key. Most variable in quality and smallest free daily cap of the four, so
it's the last resort in the default `AI_PROVIDER_ORDER`."""

from __future__ import annotations

from rove import config
from rove.ai.providers._openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    id = "openrouter"
    base_url = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(
            api_key or config.OPENROUTER_API_KEY, model or config.OPENROUTER_MODEL
        )
