"""Greenhouse collector — HTTP-only, public per-company board JSON API.

Iterates a curated company list (`config.ATS_COMPANIES["greenhouse"]`) — no
company/keyword search exists on this API, only a full per-company board
listing (`content=true` includes the full job body in the same response).

Gotcha confirmed live: `content` is HTML-entity-escaped HTML (e.g. the raw
field literally contains `&lt;div&gt;`, not `<div>`) — `html.unescape()` is
required *before* handing it to BeautifulSoup, or the escaped tags come back
out as visible text instead of being stripped.

ADR-009: since the full body is already in this same response (no separate
detail fetch to save by pre-filtering on title alone), the keyword match runs
against title + description together, not title alone.
"""

from __future__ import annotations

import html
from collections.abc import Iterator
from datetime import UTC, date, datetime

from bs4 import BeautifulSoup
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

SOURCE = "greenhouse"

_BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _parse_posted_at(raw: str) -> tuple[date | None, int]:
    try:
        posted = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None, 999
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    days_old = max((datetime.now(UTC) - posted.astimezone(UTC)).days, 0)
    return posted.date(), days_old


class GreenhouseCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _fetch_company(self, company: str) -> list[dict]:
        url = _BOARD_URL.format(company=company)
        try:
            response = get(self._client, url, params={"content": "true"})
        except _REQUEST_ERRORS:
            return []
        try:
            return response.json().get("jobs", [])
        except ValueError:
            return []

    def _to_job(self, raw: dict, company: str) -> Job | None:
        title = clean_text(raw.get("title", ""))
        company_name = clean_text(raw.get("company_name")) or company
        if not title:
            return None

        # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
        if criteria.title_is_rejected(title, company_name):
            return None

        description = clean_text(
            BeautifulSoup(html.unescape(raw.get("content", "")), "html.parser").get_text(" ")
        )
        if not description:
            return None

        if not matches_any_term(f"{title} {description}", config.ENGLISH_SEARCH_TERMS):
            return None

        posted_at, days_old = _parse_posted_at(raw.get("updated_at", ""))
        location = raw.get("location") or {}

        return Job(
            source=SOURCE,
            source_job_id=str(raw.get("id", "")),
            title=title,
            company=company_name,
            description=description,
            url=raw.get("absolute_url", ""),
            posted_at=posted_at,
            days_old=days_old,
            location_raw=clean_text(location.get("name")),
        )

    def collect(self) -> Iterator[Job]:
        for company in config.ATS_COMPANIES.get("greenhouse", []):
            for raw in self._fetch_company(company):
                job = self._to_job(raw, company)
                if job is not None:
                    yield job
            gentle_pause()
