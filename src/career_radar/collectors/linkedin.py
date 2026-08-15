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

EATP-020: `location=México` (free text) turned out to be silently ignored for
`f_WT=2` (remote) results — live-verified it was returning jobs based in
Miami/Texas/Washington DC, not Mexico. Switched to `geoId=103323778`
(LinkedIn's resolved region id for Mexico — the same id its own UI would
resolve "México" to server-side before searching); live-verified this
actually restricts results to real Mexico-based postings (15/15 sampled:
Ciudad de México, Nuevo León, Querétaro, Guadalajara). Also parallelized
listing across search terms (`_MAX_TERM_WORKERS`, mirrors the worker-pool
`fetch_job_details` already used for detail-fetch) — pagination *within* one
term stays sequential (page N depends on knowing page N-1 wasn't short), but
different terms have nothing in common and don't need to wait on each other.

Live full-run verification (all 9 `config.SEARCH_TERMS`, 2026-08-14): 534.6s
total (listing + detail-fetch) vs. the ~459s EATP-019 Phase 6 measured for
just 3 terms sequentially (~23 min extrapolated to 9) — a >2x speedup. Yielded
134 jobs (down from the old free-text version's 321 on the same real run),
overwhelmingly real Mexico locations (Ciudad de México, Monterrey,
Guadalajara, Querétaro, Mexicali, ...) — fewer raw jobs, but that's the geo
fix working as intended: the old 321 included jobs based in Miami/Texas/DC
that were never actually reachable for Kevin.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# LinkedIn's resolved geo id for Mexico (live-verified 2026-08-14 — see module
# docstring). Not a free-text `location=` param: that one is silently ignored
# for remote (`f_WT=2`) results.
_GEO_ID = "103323778"
# Confirmed live (2026-08-13): this endpoint returns 10 cards per page, not
# the 25 the old browser-based `/jobs/search/` UI used.
_PAGE_SIZE = 10
_MAX_PAGES_PER_TERM = 10
# Search terms have nothing in common with each other — safe to run this many
# at once against a public, logged-out endpoint (mirrors the detail-fetch
# worker count in `linkedin_api.py`).
#
# EATP-021 (2026-08-15): tried bumping this to 5. Live A/B on the same real
# run (back-to-back, same moment): workers=5 -> 92.2s but only 14 jobs;
# workers=3 -> 316.5s but 42 jobs — a 3x drop in real vacancies found, not
# just noise. `_collect_term_ids` can't tell "genuinely reached the end of
# results" apart from "this page's request got rate-limited and gave up"
# (`_REQUEST_ERRORS` stops the term silently either way) — more concurrent
# terms hitting LinkedIn's guest endpoint at once means more of them get
# rate-limited and quietly truncated. Reverted to 3 — faster isn't better if
# it's silently losing real matches, which is exactly the P20 failure mode
# this whole codebase tries to avoid.
_MAX_TERM_WORKERS = 3

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
        f"&geoId={_GEO_ID}"
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
        # Terms don't depend on each other — fetch them concurrently, then
        # merge in a fixed order (config.SEARCH_TERMS, then page order within
        # a term) so the result is deterministic regardless of which thread
        # finishes first.
        ids_by_term: dict[str, list[str]] = {}
        with ThreadPoolExecutor(max_workers=_MAX_TERM_WORKERS) as executor:
            future_to_term = {
                executor.submit(lambda t=term: list(self._collect_term_ids(t))): term
                for term in config.SEARCH_TERMS
            }
            for future in as_completed(future_to_term):
                ids_by_term[future_to_term[future]] = future.result()

        seen: set[str] = set()
        ordered_ids: list[str] = []
        for term in config.SEARCH_TERMS:
            for job_id in ids_by_term.get(term, []):
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
