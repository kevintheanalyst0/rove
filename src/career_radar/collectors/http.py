"""Shared HTTP layer for HTTP/JSON collectors: one client, one retry policy,
one pacing helper. Replaces the ad-hoc `requests.Session` copied per legacy
collector (see `legacy/jobmatch/collectors/utils.py::make_session`).
"""

from __future__ import annotations

import random
import time

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=10.0)

# Statuses worth retrying: rate-limited or the server having a bad moment.
# Anything else (404, 401, ...) is a real error and should surface immediately.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    """A response worth retrying (429/5xx). Tenacity retries on this type."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"retryable status {response.status_code} for {response.url}")


def build_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> httpx.Client:
    """One keep-alive client per collector run — reuses connections."""
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    return httpx.Client(headers=merged, timeout=timeout, follow_redirects=True)


def gentle_pause(min_seconds: float = 0.8, max_seconds: float = 2.2) -> None:
    """Randomized pacing between requests — avoids a fixed, bot-like cadence."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def _raise_if_retryable(response: httpx.Response) -> httpx.Response:
    if response.status_code in _RETRYABLE_STATUS:
        raise RetryableHTTPError(response)
    response.raise_for_status()
    return response


@retry(
    retry=retry_if_exception_type((RetryableHTTPError, httpx.TransportError)),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)
def get(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
    """GET with backoff on transient failures (429/5xx/network); gives up
    after 4 attempts and raises the last error."""
    response = client.get(url, **kwargs)
    return _raise_if_retryable(response)
