"""LinkedIn collector — HTTP-only, both listing and detail via guest endpoints.

Rewrite (EATP-019, 2026-08-13). The previous version drove a real browser
through `https://www.linkedin.com/jobs/search/` to list job ids. That broke:
LinkedIn shipped a new authenticated "AI job search" UI (its own banner says
so — "algunos filtros ya no estén disponibles") that silently drops the
`f_WT`/`f_JT` filters this collector sent, and renders results through React
Server Components with no stable scraping hooks left (no
`data-occludable-job-id`, no `jobs/view` hrefs, only build-hashed CSS classes
that change per deployment). Confirmed live it wasn't a captcha, a block, or
genuinely zero results — the page had 99 real matches, just nothing left to
grab them by.

Fix: LinkedIn's public **guest** search endpoint
(`jobs-guest/jobs/api/seeMoreJobPostings/search`) is unaffected — it's the
same stable, logged-out, server-rendered surface `linkedin_api.py` already
uses for job *details*, and it still serves classic HTML with
`data-entity-urn="urn:li:jobPosting:<id>"` on every card. Moving the listing
phase onto it too means this collector no longer touches a browser at all:
no login wall, no captcha, no account-ban risk (P23) — not just a bugfix,
strictly simpler and safer than the browser version ever was. Confirmed live
that `f_TPR`/`f_WT`/`f_JT`/`location`/`start` all still work as filters on
this endpoint, and that pagination (`start`) returns distinct pages with no
overlap.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from httpx import Client, HTTPError

from career_radar import config, criteria
from career_radar.collectors.http import (
    RetryableHTTPError,
    build_client,
    gentle_pause,
    get,
)
from career_radar.collectors.linkedin_api import fetch_job_details
from career_radar.collectors.parsing import clean_text, parse_days_old_es
from career_radar.models import Job

SOURCE = "linkedin"

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LOCATION = "México"
# Confirmed live (2026-08-13): this endpoint returns 10 cards per page, not
# the 25 the old browser-based `/jobs/search/` UI used.
_PAGE_SIZE = 10
_MAX_PAGES_PER_TERM = 10

_JOB_ID_PATTERN = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')

# get() exhausts its retries and reraises either of these — a request that
# never recovers means "skip this term", not "crash the collector" (same
# shape as OCC/Computrabajo/Lever).
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


# ---------------------------------------------------------------------------
# Pure decision logic — no network needed, fully unit-testable.
# ---------------------------------------------------------------------------


def build_search_url(query: str, start: int = 0) -> str:
    return (
        f"{_SEARCH_URL}"
        f"?keywords={quote(query)}"
        f"&location={quote(LOCATION)}"
        f"&f_TPR=r86400"  # posted in the last 24h
        f"&f_WT=2"  # remote
        f"&f_JT=F"  # full-time
        f"&start={start}"
    )


def build_job_view_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def extract_job_ids(html: str) -> list[str]:
    """Ids in page order, de-duplicated within the page."""
    seen: set[str] = set()
    ids: list[str] = []
    for job_id in _JOB_ID_PATTERN.findall(html or ""):
        if job_id not in seen:
            seen.add(job_id)
            ids.append(job_id)
    return ids


def _build_job(job_id: str, detail: dict[str, str]) -> Job | None:
    title = clean_text(detail.get("title", ""))
    company = clean_text(detail.get("company", "")) or "Unknown"
    if not title:
        return None

    # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
    if criteria.title_is_rejected(title, company):
        return None

    description = clean_text(detail.get("description", ""))
    days_old = parse_days_old_es(detail.get("posted", ""))
    posted_at = (
        (datetime.now(UTC) - timedelta(days=days_old)).date() if days_old < 999 else None
    )

    return Job(
        source=SOURCE,
        source_job_id=job_id,
        title=title,
        company=company,
        description=description,
        url=build_job_view_url(job_id),
        days_old=days_old,
        posted_at=posted_at,
        location_raw=clean_text(detail.get("location", "")),
    )


# ---------------------------------------------------------------------------
# HTTP orchestration — thin; calls the pure functions above.
# ---------------------------------------------------------------------------


class LinkedInCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None, detail_fetcher=fetch_job_details) -> None:
        self._client = client or build_client()
        self._detail_fetcher = detail_fetcher

    def collect(self) -> Iterator[Job]:
        seen: set[str] = set()
        ordered_ids: list[str] = []
        for term in config.SEARCH_TERMS:
            for job_id in self._collect_term_ids(term):
                if job_id not in seen:
                    seen.add(job_id)
                    ordered_ids.append(job_id)

        details = self._detail_fetcher(ordered_ids)
        for job_id in ordered_ids:
            detail = details.get(job_id)
            if detail is None:
                continue
            job = _build_job(job_id, detail)
            if job is not None:
                yield job

    def _collect_term_ids(self, term: str) -> Iterator[str]:
        for page_number in range(_MAX_PAGES_PER_TERM):
            start = page_number * _PAGE_SIZE
            try:
                response = get(self._client, build_search_url(term, start))
            except _REQUEST_ERRORS:
                return

            page_ids = extract_job_ids(response.text)
            if not page_ids:
                return

            yield from page_ids

            if len(page_ids) < _PAGE_SIZE:
                return
            gentle_pause()
