"""Lever collector — HTTP-only, public per-company postings JSON API.

Same shape as `greenhouse.py`: iterates a curated company list
(`config.ATS_COMPANIES["lever"]`), one full-board fetch per company, no
server-side search to lean on. Lever's public board is a thinner ATS to draw
from live — of ~20 well-known companies probed while building this, only a
couple still have an active public board — so the curated list here is
intentionally short; grow it as real ones are found.

Unlike Greenhouse, a posting has no `company_name` field of its own (it's
implicit in which board you queried), and it ships plain-text description
fields directly (`descriptionPlain`) — no HTML stripping needed.

ADR-009: the full body is already in this same response, so the keyword
match runs against title + description together, not title alone.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from httpx import Client, HTTPError

from career_radar import config, criteria
from career_radar.collectors.http import (
    RetryableHTTPError,
    build_client,
    gentle_pause,
    get,
)
from career_radar.collectors.parsing import clean_text, matches_any_term
from career_radar.models import Job

SOURCE = "lever"

_POSTINGS_URL = "https://api.lever.co/v0/postings/{company}"
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _parse_posted_at(epoch_millis: object) -> tuple[date | None, int]:
    try:
        posted = datetime.fromtimestamp(int(epoch_millis) / 1000, tz=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError, OSError):
        return None, 999
    days_old = max((datetime.now(UTC) - posted).days, 0)
    return posted.date(), days_old


def _display_company(company_slug: str) -> str:
    return company_slug.replace("-", " ").title()


class LeverCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _fetch_company(self, company: str) -> list[dict]:
        url = _POSTINGS_URL.format(company=company)
        try:
            response = get(self._client, url, params={"mode": "json"})
        except _REQUEST_ERRORS:
            return []
        try:
            postings = response.json()
        except ValueError:
            return []
        return postings if isinstance(postings, list) else []

    def _to_job(self, raw: dict, company: str) -> Job | None:
        title = clean_text(raw.get("text", ""))
        company_name = _display_company(company)
        if not title:
            return None

        # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
        if criteria.title_is_rejected(title, company_name):
            return None

        description = clean_text(raw.get("descriptionPlain", ""))
        if not description:
            return None

        if not matches_any_term(f"{title} {description}", config.ENGLISH_SEARCH_TERMS):
            return None

        posted_at, days_old = _parse_posted_at(raw.get("createdAt"))
        categories = raw.get("categories") or {}

        return Job(
            source=SOURCE,
            source_job_id=str(raw.get("id", "")),
            title=title,
            company=company_name,
            description=description,
            url=raw.get("hostedUrl", ""),
            posted_at=posted_at,
            days_old=days_old,
            location_raw=clean_text(categories.get("location")),
        )

    def collect(self) -> Iterator[Job]:
        for company in config.ATS_COMPANIES.get("lever", []):
            for raw in self._fetch_company(company):
                job = self._to_job(raw, company)
                if job is not None:
                    yield job
            gentle_pause()
