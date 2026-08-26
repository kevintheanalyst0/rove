"""Error classification shared across providers — tells the router whether a
failure means "this provider is done for today" (daily quota) or just "this
one batch failed, try again next time" (transient: per-minute rate limit,
5xx, network blip). Works across SDKs (OpenAI-compatible, google-genai)
because it falls back to substring matching on `str(error)` when an SDK
doesn't expose a `status_code`/`code` attribute.
"""

from __future__ import annotations

_DAILY_QUOTA_HINTS = (
    "per day",
    "perday",
    "per-day",
    "daily limit",
    "daily quota",
    "requests per day",
    "quota exceeded",
)


def status_code(error: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    text = str(error)
    for candidate in (429, 503, 500, 402):
        if str(candidate) in text:
            return candidate
    return None


def is_daily_quota_error(error: Exception) -> bool:
    if status_code(error) != 429:
        return False
    text = str(error).lower()
    return any(hint in text for hint in _DAILY_QUOTA_HINTS)


def is_transient_error(error: Exception) -> bool:
    """A retryable-within-this-batch error: anything that isn't a confirmed
    daily-quota exhaustion (that case must never be retried against the same
    provider — CLAUDE.md §7)."""
    return not is_daily_quota_error(error)


def is_unsupported_response_format_error(error: Exception) -> bool:
    """Some free OpenAI-compatible models 400 on `response_format`. When that
    happens we retry once without it rather than give up the whole provider."""
    return status_code(error) == 400 and "response_format" in str(error).lower()
