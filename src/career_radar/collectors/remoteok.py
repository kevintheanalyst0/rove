"""RemoteOK collector — HTTP-only, public JSON API.

Verified live: `?search=`/`?tags=` query params are silently ignored by the
API (same ~100 most-recent postings come back regardless), so there is no
server-side filter to lean on here — one fetch, then a client-side keyword
match against title + tags (see docs/governance/SCRAPING-GOTCHAS.md #3, which
prefers site-native filters when they exist; this one doesn't).

The first element of the response array is always a legal notice, not a job
— skip it rather than trusting "index 0 = first result".
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar import config, criteria
from career_radar.collectors.http import RetryableHTTPError, build_client, get
from career_radar.collectors.parsing import clean_text, matches_any_term
from career_radar.models import Job

SOURCE = "remoteok"

_API_URL = "https://remoteok.com/api"
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _parse_posted_at(raw: str) -> tuple[date | None, int]:
    try:
        posted = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None, 999
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    days_old = max((datetime.now(UTC) - posted).days, 0)
    return posted.date(), days_old


class RemoteOKCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _fetch_all(self) -> list[dict]:
        try:
            response = get(self._client, _API_URL)
        except _REQUEST_ERRORS:
            return []
        try:
            entries = response.json()
        except ValueError:
            return []
        # entries[0] is the API's legal notice, not a job (no "id" field).
        return [entry for entry in entries if isinstance(entry, dict) and "id" in entry]

    def _to_job(self, raw: dict) -> Job | None:
        title = clean_text(raw.get("position", ""))
        company = clean_text(raw.get("company")) or "Unknown"
        if not title:
            return None

        # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
        if criteria.title_is_rejected(title, company):
            return None

        haystack = f"{title} {' '.join(raw.get('tags', []))}"
        if not matches_any_term(haystack, config.ENGLISH_SEARCH_TERMS):
            return None

        description = clean_text(
            BeautifulSoup(raw.get("description", ""), "html.parser").get_text(" ")
        )
        if not description:
            return None

        posted_at, days_old = _parse_posted_at(raw.get("date", ""))

        return Job(
            source=SOURCE,
            source_job_id=str(raw.get("id", "")),
            title=title,
            company=company,
            description=description,
            url=raw.get("url", ""),
            posted_at=posted_at,
            days_old=days_old,
            location_raw=clean_text(raw.get("location")),
        )

    def collect(self) -> Iterator[Job]:
        seen_ids: set[str] = set()
        for raw in self._fetch_all():
            job_id = str(raw.get("id", ""))
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            job = self._to_job(raw)
            if job is not None:
                yield job
