"""Hireline collector — HTTP-only, sitemap-discovered listing + JSON-LD detail.

EATP-030 viability spike (2026-08-21): `hireline.io` has no public search API
(`robots.txt` explicitly disallows crawling `/empleos?k=*`, its query-string
search), but `/mx/sitemap_ofertas.xml` lists every currently-open Mexico
posting's URL directly — real, live, `lastmod` updated the same day as the
spike. Each posting page embeds a standard schema.org `JobPosting` JSON-LD
block (title, description, company, location, `datePosted`) alongside two
unrelated blocks (`WebSite`, `EmploymentAgency`) — `parsing.py`'s
`extract_job_posting_ld_json` already knows to pick the right one out.

No company watchlist needed (unlike Greenhouse/Lever): the sitemap covers
every company posting on the board, not one company's own listings.
"""

from __future__ import annotations

import html
from collections.abc import Iterator
from datetime import UTC, date, datetime
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from rove import cancellation, criteria
from rove.collectors.http import RetryableHTTPError, build_client, gentle_pause, get
from rove.collectors.parsing import (
    clean_text,
    extract_job_posting_ld_json,
    matches_any_term,
    slug_to_text,
)
from rove.config import ENGLISH_SEARCH_TERMS, SEARCH_TERMS
from rove.models import Job

SOURCE = "hireline"

# Mexico only (EATP-030 scope: Kevin's stated market, see Rove's
# Notion purpose statement). Hireline also runs /co/ and /us/ sitemaps —
# revisit only if MX yield turns out thin.
_SITEMAP_URL = "https://hireline.io/mx/sitemap_ofertas.xml"
_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)

# Both term lists — postings are in Spanish, but a bilingual title ("Data
# Analyst Sr.") is common enough on this board to be worth matching too.
_ALL_TERMS = [t.lower() for t in (*SEARCH_TERMS, *ENGLISH_SEARCH_TERMS)]


def _list_job_urls(client: Client) -> list[str]:
    try:
        response = get(client, _SITEMAP_URL)
    except _REQUEST_ERRORS:
        return []
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return []
    return [
        loc.text.strip()
        for loc in root.findall(".//sm:url/sm:loc", _SITEMAP_NS)
        if loc.text
    ]


def _url_parts(url: str) -> tuple[str, str]:
    """".../empleos/sql-developer/112726" -> ("sql-developer", "112726") —
    (slug for the pre-fetch keyword filter, numeric id for `source_job_id`)."""
    parts = [p for p in url.rstrip("/").split("/") if p]
    if len(parts) < 2:
        return (parts[-1] if parts else "", "")
    return parts[-2], parts[-1]


def _parse_date_posted(raw: str) -> tuple[date | None, int]:
    try:
        posted = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None, 999
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    days_old = max((datetime.now(UTC) - posted.astimezone(UTC)).days, 0)
    return posted.date(), days_old


def _build_job(url: str, job_id: str, posting: dict) -> Job | None:
    # `html.unescape` first (Hireline's description carries literal `&nbsp;`
    # entities, same gotcha as Greenhouse's — SCRAPING-GOTCHAS.md), then strip
    # any incidental markup the same way.
    title = clean_text(html.unescape(posting.get("title", "")))
    if not title:
        return None
    organization = posting.get("hiringOrganization") or {}
    company = clean_text(html.unescape(organization.get("name", ""))) or "Unknown"

    if criteria.title_is_rejected(title, company):
        return None

    description = clean_text(
        BeautifulSoup(html.unescape(posting.get("description", "")), "html.parser").get_text(" ")
    )
    if not description:
        return None

    posted_at, days_old = _parse_date_posted(posting.get("datePosted", ""))

    address = (posting.get("jobLocation") or {}).get("address") or {}
    location_raw = clean_text(
        ", ".join(
            part
            for part in (address.get("addressLocality"), address.get("addressRegion"))
            if part
        )
    )

    return Job(
        source=SOURCE,
        source_job_id=job_id or url,
        title=title,
        company=company,
        description=description,
        url=url,
        posted_at=posted_at,
        days_old=days_old,
        location_raw=location_raw,
    )


class HirelineCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def collect(self) -> Iterator[Job]:
        urls = _list_job_urls(self._client)
        # Cheap prefilter on the slug alone — the sitemap gives no title text,
        # and fetching all ~200+ postings on every run would be impolite and
        # slow for a board this size (SEARCH-STRATEGY.md: prefer recent and
        # relevant over exhaustive).
        candidates = []
        for url in urls:
            slug, job_id = _url_parts(url)
            if matches_any_term(slug_to_text(slug), _ALL_TERMS):
                candidates.append((url, job_id))

        for url, job_id in candidates:
            cancellation.check()
            try:
                response = get(self._client, url)
            except _REQUEST_ERRORS:
                continue
            posting = extract_job_posting_ld_json(response.text)
            if posting is None:
                continue
            job = _build_job(url, job_id, posting)
            if job is not None:
                yield job
            gentle_pause()
