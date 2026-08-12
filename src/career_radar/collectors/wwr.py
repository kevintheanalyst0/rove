"""We Work Remotely collector — RSS, parsed with the stdlib
`xml.etree.ElementTree` (no new dependency: RSS is plain XML, feedparser
buys nothing here).

Verified live: the old "remote-data-jobs" / "remote-business-jobs" category
feeds now 301 — WWR restructured its categories at some point and neither
exists any more. The closest surviving category is
"remote-management-and-finance-jobs" (confirmed 200, contains real BI/data/
business-analyst postings, e.g. "Business Analyst - ..."), but it's broader
than just data/BI roles, so this collector still applies a client-side
keyword match on top of it (same pattern as RemoteOK/Himalayas).

WWR titles come as "Company: Job Title" — split on the first ": ".
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar import config, criteria
from career_radar.collectors.http import RetryableHTTPError, build_client, get
from career_radar.collectors.parsing import clean_text, matches_any_term
from career_radar.models import Job

SOURCE = "wwr"

_FEED_URL = "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss"
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _split_company_and_title(raw_title: str) -> tuple[str, str]:
    if ": " in raw_title:
        company, title = raw_title.split(": ", 1)
        return clean_text(company) or "Unknown", clean_text(title)
    return "Unknown", clean_text(raw_title)


def _parse_posted_at(raw: str) -> tuple[date | None, int]:
    try:
        posted = parsedate_to_datetime(raw)
    except (ValueError, TypeError):
        return None, 999
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    days_old = max((datetime.now(UTC) - posted).days, 0)
    return posted.date(), days_old


def _job_id_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


class WWRCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _fetch_items(self) -> list[ET.Element]:
        try:
            response = get(self._client, _FEED_URL)
        except _REQUEST_ERRORS:
            return []
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            return []
        return root.findall("./channel/item")

    def _to_job(self, item: ET.Element) -> Job | None:
        raw_title = (item.findtext("title") or "").strip()
        company, title = _split_company_and_title(raw_title)
        if not title:
            return None

        # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
        if criteria.title_is_rejected(title, company):
            return None
        if not matches_any_term(title, config.ENGLISH_SEARCH_TERMS):
            return None

        url = (item.findtext("link") or "").strip()
        if not url:
            return None

        description = clean_text(
            BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ")
        )
        if not description:
            return None

        posted_at, days_old = _parse_posted_at(item.findtext("pubDate") or "")

        return Job(
            source=SOURCE,
            source_job_id=_job_id_from_url(url),
            title=title,
            company=company,
            description=description,
            url=url,
            posted_at=posted_at,
            days_old=days_old,
            location_raw=clean_text(item.findtext("region")),
        )

    def collect(self) -> Iterator[Job]:
        seen_ids: set[str] = set()
        for item in self._fetch_items():
            job = self._to_job(item)
            if job is None:
                continue
            if job.source_job_id in seen_ids:
                continue
            seen_ids.add(job.source_job_id)
            yield job
