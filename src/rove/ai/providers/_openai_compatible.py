"""Shared base for OpenAI-compatible providers (Groq, OpenRouter) — one
client, one call shape, `response_format` JSON mode where supported. Gemini
uses its own SDK/response schema (`gemini.py`) and doesn't subclass this.
"""

from __future__ import annotations

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from rove import config
from rove.ai.base import AiResult, Provider, ProviderError, QuotaExceededError
from rove.ai.parse import parse_batch_response
from rove.ai.prompts import build_prompt
from rove.ai.providers._common import (
    is_daily_quota_error,
    is_transient_error,
    is_unsupported_response_format_error,
)
from rove.config import get_logger
from rove.models import Job
from rove.profile import Profile

logger = get_logger(__name__)


class OpenAICompatibleProvider(Provider):
    """Base for any provider reachable through an OpenAI-compatible
    `/chat/completions` endpoint."""

    base_url: str

    def __init__(self, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self.base_url,
                timeout=config.AI_REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    def _complete(self, prompt: str) -> str:
        client = self._get_client()
        messages = [{"role": "user", "content": prompt}]
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except Exception as error:
            if is_unsupported_response_format_error(error):
                response = client.chat.completions.create(
                    model=self._model, messages=messages
                )
            else:
                raise
        return response.choices[0].message.content or ""

    def evaluate_batch(self, jobs: list[Job], profile: Profile) -> list[AiResult]:
        if not self.configured:
            raise ProviderError(f"{self.id}: no API key configured")

        prompt = build_prompt(jobs, profile)

        @retry(
            stop=stop_after_attempt(config.AI_MAX_RETRIES),
            wait=wait_exponential(multiplier=config.AI_RETRY_BACKOFF_SECONDS),
            retry=retry_if_exception(is_transient_error),
            reraise=True,
        )
        def _call() -> str:
            return self._complete(prompt)

        try:
            text = _call()
        except Exception as error:
            if is_daily_quota_error(error):
                raise QuotaExceededError(str(error)) from error
            raise ProviderError(str(error)) from error

        return parse_batch_response(text)
