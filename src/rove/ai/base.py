"""The provider contract — every concrete provider (`ai/providers/*.py`) adapts
its own SDK to this shape, so the router and the scoring pipeline (EATP-013)
never touch a provider-specific detail.

ADR-006: results are matched back to jobs **by `Job.signature`**, never by
position. `AiResult.signature` carries that id through the round-trip.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from rove.models import Job
from rove.profile import Profile


class AiResult(BaseModel):
    """One job's AI evaluation, identified by `Job.signature` (ADR-006)."""

    signature: str
    ai_score: int
    pros: list[str] = Field(default_factory=list)
    contras: list[str] = Field(default_factory=list)
    summary: str = ""


class QuotaExceededError(Exception):
    """This provider's DAILY quota is exhausted. The router marks it
    exhausted for the rest of today and never re-hits it (CLAUDE.md §7)."""


class ProviderError(Exception):
    """This provider failed for this one batch (not a daily quota issue) —
    the router falls back to the next provider for this batch only; this
    provider is tried again on the next one."""


class Provider(ABC):
    """A single AI provider. Concrete providers live in `ai/providers/`."""

    id: str

    @property
    def configured(self) -> bool:
        """Whether this provider has what it needs (e.g. an API key) to run."""
        return True

    @abstractmethod
    def evaluate_batch(self, jobs: list[Job], profile: Profile) -> list[AiResult]:
        """Evaluate a batch of jobs. Raises `QuotaExceededError` or
        `ProviderError` on failure — never returns a partial/guessed result
        for a job it isn't confident about; see `ai/parse.py::match_ai_results`
        for how missing/duplicate ids are handled downstream."""
        raise NotImplementedError

    @abstractmethod
    def answer_questions(self, prompt: str) -> str:
        """EATP-034: a raw prompt -> raw text completion, JSON-mode but with
        no fixed response schema (unlike `evaluate_batch`'s scoring shape) —
        `rove.apply.questions` builds the prompt and parses the response
        itself. Same `QuotaExceededError`/`ProviderError` contract."""
        raise NotImplementedError
