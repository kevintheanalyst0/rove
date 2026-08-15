"""LinkedIn's public "guest" job-detail API — HTTP-only, no login needed.

Keeping every detail fetch on this anonymous endpoint (regardless of whether
listing uses a logged-in profile) is what keeps account risk (P23) off this
path entirely: a captcha or block here never touches Kevin's real session.

Rebuilt from `legacy/jobmatch/collectors/linkedin_api.py`, not ported as-is:
`http.py`'s retry already backs off on a 429 with the RATE_LIMIT sentinel
legacy needed manually, so the two-phase collect-then-retry dance is gone —
a job that still fails after retries is simply skipped (returns None), same
as OCC/Computrabajo.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar.collectors.http import (
    RetryableHTTPError,
    build_client,
    gentle_pause,
    get,
)
from career_radar.collectors.parsing import clean_text

# EATP-021 (2026-08-15): tried bumping this alongside `linkedin.py`'s
# `_MAX_TERM_WORKERS`, both to 5 — live A/B showed a 3x drop in real jobs
# found (rate-limiting-induced silent truncation, see that file's comment
# for the numbers). Reverted together since the two weren't tested in
# isolation from each other; 3 is the last value confirmed safe.
_MAX_WORKERS = 3
# get() exhausts its retries and reraises either of these — a request that
# never recovers means "skip this job," not "crash the collector."
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _detail_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


def _text(soup: BeautifulSoup, selector: str) -> str:
    tag = soup.select_one(selector)
    return clean_text(tag.get_text(" ")) if tag else ""


def fetch_job_detail(client: Client, job_id: str) -> dict[str, str] | None:
    """Fetch and parse one job's detail. Never raises — a failure just means
    this job isn't yielded."""
    gentle_pause(0.5, 1.5)
    try:
        response = get(client, _detail_url(job_id))
    except _REQUEST_ERRORS:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    description = ""
    description_tag = soup.select_one(".show-more-less-html__markup")
    if description_tag:
        description = clean_text(description_tag.get_text(" "))

    return {
        "title": _text(soup, "h2.top-card-layout__title"),
        "company": _text(soup, ".topcard__org-name-link"),
        "location": _text(soup, ".topcard__flavor--bullet"),
        "posted": _text(soup, ".posted-time-ago__text"),
        "description": description,
    }


def fetch_job_details(
    job_ids: list[str],
    client: Client | None = None,
    max_workers: int = _MAX_WORKERS,
) -> dict[str, dict[str, str]]:
    """Fetch details for many ids with modest, polite concurrency."""
    client = client or build_client()
    results: dict[str, dict[str, str]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(fetch_job_detail, client, job_id): job_id for job_id in job_ids
        }
        for future in as_completed(future_map):
            job_id = future_map[future]
            detail = future.result()
            if detail is not None:
                results[job_id] = detail

    return results
