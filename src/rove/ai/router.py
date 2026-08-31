"""The AI router (ADR-003) — tries providers in `AI_PROVIDER_ORDER`, falls
back on quota/error, and never re-hits a provider already exhausted today.

A daily-quota error (`QuotaExceededError`) marks the provider exhausted for
the rest of today (persisted, so it survives a restart). A transient error
(`ProviderError`) only skips that provider for the current batch — it's
tried again on the next one. If every provider fails, the batch degrades to
an empty result rather than crashing the run (P11/P12): the scoring pipeline
(EATP-013) treats those jobs as unevaluated and falls back to their
prefilter score.
"""

from __future__ import annotations

from rove import config
from rove.ai.base import AiResult, Provider, ProviderError, QuotaExceededError
from rove.ai.usage import UsageTracker
from rove.config import get_logger
from rove.models import Job
from rove.profile import Profile

logger = get_logger(__name__)


class AiRouter:
    def __init__(
        self,
        providers: dict[str, Provider],
        *,
        order: list[str] | None = None,
        usage: UsageTracker | None = None,
    ) -> None:
        self._providers = providers
        self._order = order if order is not None else config.AI_PROVIDER_ORDER
        self._usage = usage if usage is not None else UsageTracker.load()

    def evaluate_batch(self, jobs: list[Job], profile: Profile) -> list[AiResult]:
        """Evaluate one batch with the first available, under-quota provider,
        falling back down `AI_PROVIDER_ORDER` on quota/error."""
        if not jobs:
            return []

        last_error: Exception | None = None
        for provider_id in self._order:
            provider = self._providers.get(provider_id)
            if provider is None or not provider.configured:
                continue
            if self._usage.is_exhausted(provider_id):
                logger.info("skipping %s: exhausted for today", provider_id)
                continue

            try:
                results = provider.evaluate_batch(jobs, profile)
            except QuotaExceededError as error:
                logger.warning(
                    "%s: daily quota exhausted (%s) — falling back", provider_id, error
                )
                self._usage.mark_exhausted(provider_id)
                self._usage.save()
                last_error = error
                continue
            except ProviderError as error:
                logger.warning(
                    "%s: failed for this batch (%s) — falling back", provider_id, error
                )
                last_error = error
                continue

            self._usage.record_request(provider_id)
            self._usage.save()
            return results

        logger.error(
            "all AI providers unavailable for this batch (last error: %s)", last_error
        )
        return []

    def answer_questions(self, prompt: str) -> str:
        """EATP-034 — same fallback discipline as `evaluate_batch`, over
        `Provider.answer_questions`'s freeform prompt/response shape instead
        of the scoring-specific one. Empty string on total failure, mirroring
        `evaluate_batch`'s "degrade, don't crash" contract (P11/P12) — the
        caller (`rove.apply.questions`) treats that the same as "the AI
        didn't answer this question."""
        last_error: Exception | None = None
        for provider_id in self._order:
            provider = self._providers.get(provider_id)
            if provider is None or not provider.configured:
                continue
            if self._usage.is_exhausted(provider_id):
                logger.info("skipping %s: exhausted for today", provider_id)
                continue

            try:
                text = provider.answer_questions(prompt)
            except QuotaExceededError as error:
                logger.warning(
                    "%s: daily quota exhausted (%s) — falling back", provider_id, error
                )
                self._usage.mark_exhausted(provider_id)
                self._usage.save()
                last_error = error
                continue
            except ProviderError as error:
                logger.warning(
                    "%s: failed for this batch (%s) — falling back", provider_id, error
                )
                last_error = error
                continue

            self._usage.record_request(provider_id)
            self._usage.save()
            return text

        logger.error(
            "all AI providers unavailable for question-answering (last error: %s)", last_error
        )
        return ""


def build_default_router() -> AiRouter:
    """Wire up the real providers from `.env` config. Used by the
    orchestrator (EATP-014); tests build an `AiRouter` directly with mocks
    instead of calling this."""
    from rove.ai.providers.gemini import gemini_flash, gemini_flash_lite
    from rove.ai.providers.groq import GroqProvider
    from rove.ai.providers.openrouter import OpenRouterProvider

    providers: dict[str, Provider] = {
        "groq": GroqProvider(),
        "openrouter": OpenRouterProvider(),
        "gemini_flash": gemini_flash(),
        "gemini_flash_lite": gemini_flash_lite(),
    }
    return AiRouter(providers)
