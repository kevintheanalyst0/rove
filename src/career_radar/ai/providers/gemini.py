"""Gemini — native structured output via `response_schema`. One class backs
both `gemini_flash` (best quality, tiny free daily cap — first in the
default `AI_PROVIDER_ORDER`) and `gemini_flash_lite` (solid quality, big
free daily cap — the broad-quota fallback), differing only by model id.
"""

from __future__ import annotations

from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from career_radar import config
from career_radar.ai.base import AiResult, Provider, ProviderError, QuotaExceededError
from career_radar.ai.parse import parse_batch_response
from career_radar.ai.prompts import build_prompt
from career_radar.ai.providers._common import is_daily_quota_error, is_transient_error
from career_radar.config import get_logger
from career_radar.models import Job
from career_radar.profile import Profile

logger = get_logger(__name__)


class _ResultItem(BaseModel):
    id: str
    score: int
    pros: list[str] = []
    contras: list[str] = []
    summary: str = ""


class _BatchResponse(BaseModel):
    results: list[_ResultItem]


class GeminiProvider(Provider):
    def __init__(
        self, provider_id: str, model: str, api_key: str | None = None
    ) -> None:
        self.id = provider_id
        self._model = model
        self._api_key = api_key or config.GEMINI_API_KEY
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(
                    timeout=int(config.AI_REQUEST_TIMEOUT_SECONDS * 1000)
                ),
            )
        return self._client

    def _generate(self, prompt: str) -> str:
        from google.genai import types

        client = self._get_client()
        response = client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_BatchResponse,
            ),
        )
        return response.text or ""

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
            return self._generate(prompt)

        try:
            text = _call()
        except Exception as error:
            if is_daily_quota_error(error):
                raise QuotaExceededError(str(error)) from error
            raise ProviderError(str(error)) from error

        return parse_batch_response(text)


def gemini_flash(api_key: str | None = None) -> GeminiProvider:
    return GeminiProvider("gemini_flash", config.GEMINI_FLASH_MODEL, api_key)


def gemini_flash_lite(api_key: str | None = None) -> GeminiProvider:
    return GeminiProvider("gemini_flash_lite", config.GEMINI_FLASH_LITE_MODEL, api_key)
