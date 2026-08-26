"""Himalayas collector — HTTP-only, public JSON API.

Verified live: `search=`/`keywords=`/`categories[]=` query params are all
silently ignored (identical results regardless), but `offset`/`limit`
genuinely paginate, newest-first. No server-side filter to lean on, so this
paginates a bounded number of recent pages and applies a client-side keyword
match (same pattern as RemoteOK/WWR) instead of trying to fetch its 100k+
total postings.

The API never signals "end of results" for a plain offset walk (it just
keeps returning `limit`-sized pages), so `_MAX_PAGES` is a hard cap — the
loop-safety net from docs/governance/SCRAPING-GOTCHAS.md #2, applied here
even though nothing has been observed looping.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from rove import cancellation, config, criteria
from rove.collectors.http import (
    RetryableHTTPError,
    build_client,
    gentle_pause,
    get,
)
from rove.collectors.parsing import clean_text, matches_any_term
from rove.models import Job

SOURCE = "himalayas"

_API_URL = "https://himalayas.app/jobs/api"
_PAGE_SIZE = 100
_MAX_PAGES = 5
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _parse_posted_at(epoch_seconds: object) -> tuple[date | None, int]:
    try:
        posted = datetime.fromtimestamp(int(epoch_seconds), tz=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError, OSError):
        return None, 999
    days_old = max((datetime.now(UTC) - posted).days, 0)
    return posted.date(), days_old


def _job_id_from_guid(guid: str) -> str:
    return guid.rstrip("/").rsplit("/", 1)[-1]


class HimalayasCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _fetch_page(self, offset: int) -> list[dict]:
        try:
            response = get(
                self._client, _API_URL, params={"limit": _PAGE_SIZE, "offset": offset}
            )
        except _REQUEST_ERRORS:
            return []
        try:
            return response.json().get("jobs", [])
        except ValueError:
            return []

    def _to_job(self, raw: dict) -> Job | None:
        title = clean_text(raw.get("title", ""))
        company = clean_text(raw.get("companyName")) or "Unknown"
        if not title:
            return None

        # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
        if criteria.title_is_rejected(title, company):
            return None
        if not matches_any_term(title, config.ENGLISH_SEARCH_TERMS):
            return None

        description = clean_text(
            BeautifulSoup(raw.get("description", ""), "html.parser").get_text(" ")
        )
        if not description:
            return None

        url = raw.get("applicationLink") or raw.get("guid", "")
        if not url:
            return None

        posted_at, days_old = _parse_posted_at(raw.get("pubDate"))
        locations = raw.get("locationRestrictions") or []

        return Job(
            source=SOURCE,
            source_job_id=_job_id_from_guid(raw.get("guid", url)),
            title=title,
            company=company,
            description=description,
            url=url,
            posted_at=posted_at,
            days_old=days_old,
            location_raw=clean_text(", ".join(locations)),
        )

    def collect(self) -> Iterator[Job]:
        # EATP-024: see greenhouse.py's identical comment — pagination needs
        # its own cancellation check.
        seen_ids: set[str] = set()
        for page in range(_MAX_PAGES):
            cancellation.check()
            raws = self._fetch_page(page * _PAGE_SIZE)
            if not raws:
                break

            for raw in raws:
                job = self._to_job(raw)
                if job is None:
                    continue
                if job.source_job_id in seen_ids:
                    continue
                seen_ids.add(job.source_job_id)
                yield job

            gentle_pause()
