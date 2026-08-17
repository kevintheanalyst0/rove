"""Remotive collector — HTTP-only, public JSON API with real server-side
search (`?search=<term>`), confirmed live against remotive.com/api. Tier-1
per SEARCH-STRATEGY.md: clean feed, no captcha, low competition.

No pagination needed — a search returns its full result set in one call.
No "recommended jobs" padding either: it's a plain JSON API, not a scraped
listing page (see docs/governance/SCRAPING-GOTCHAS.md #1).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar import cancellation, config, criteria
from career_radar.collectors.http import (
    RetryableHTTPError,
    build_client,
    gentle_pause,
    get,
)
from career_radar.collectors.parsing import clean_text
from career_radar.models import Job

SOURCE = "remotive"

_SEARCH_URL = "https://remotive.com/api/remote-jobs"
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _parse_posted_at(raw: str) -> tuple[date | None, int]:
    try:
        posted = datetime.fromisoformat(raw).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None, 999
    days_old = max((datetime.now(UTC) - posted).days, 0)
    return posted.date(), days_old


class RemotiveCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _fetch_term(self, term: str) -> list[dict]:
        try:
            response = get(self._client, _SEARCH_URL, params={"search": term})
        except _REQUEST_ERRORS:
            return []
        try:
            return response.json().get("jobs", [])
        except ValueError:
            return []

    def _to_job(self, raw: dict) -> Job | None:
        title = clean_text(raw.get("title", ""))
        company = clean_text(raw.get("company_name")) or "Unknown"
        if not title:
            return None

        # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
        if criteria.title_is_rejected(title, company):
            return None

        description = clean_text(
            BeautifulSoup(raw.get("description", ""), "html.parser").get_text(" ")
        )
        if not description:
            return None

        posted_at, days_old = _parse_posted_at(raw.get("publication_date", ""))

        return Job(
            source=SOURCE,
            source_job_id=str(raw.get("id", "")),
            title=title,
            company=company,
            description=description,
            url=raw.get("url", ""),
            posted_at=posted_at,
            days_old=days_old,
            location_raw=clean_text(raw.get("candidate_required_location")),
        )

    def collect(self) -> Iterator[Job]:
        # EATP-024: see greenhouse.py's identical comment — per-term
        # fetching needs its own cancellation check.
        seen_ids: set[str] = set()
        for term in config.ENGLISH_SEARCH_TERMS:
            cancellation.check()
            for raw in self._fetch_term(term):
                job_id = str(raw.get("id", ""))
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                job = self._to_job(raw)
                if job is not None:
                    yield job
            gentle_pause()
