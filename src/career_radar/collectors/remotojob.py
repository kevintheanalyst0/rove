"""RemotoJob collector — HTTP-only, sitemap-discovered listing + JSON-LD detail.

EATP-030 viability spike (2026-08-21): `remotojob.com` is a WordPress board
with no public search API, but its sitemap index (`sitemap_index.xml`) lists
several `rj-job-sitemap{N}.xml` files, each ~200 postings, `N=1` confirmed
live as the most-recently-updated batch (entries from the same day as the
spike; higher `N` trails off older). Each posting page embeds a standard
schema.org `JobPosting` JSON-LD block — same shape as Hireline/WeRemoto, see
`parsing.py::extract_job_posting_ld_json` — except this site emits a raw,
unescaped newline inside the description string, which breaks strict JSON;
the shared helper already parses with `strict=False` to tolerate it.

Only sitemap 1 is fetched (recency over exhaustiveness, SEARCH-STRATEGY.md) —
the older batches are backlog, not worth a full crawl every run.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar import cancellation, criteria
from career_radar.collectors.http import RetryableHTTPError, build_client, gentle_pause, get
from career_radar.collectors.parsing import (
    clean_text,
    extract_job_posting_ld_json,
    matches_any_term,
    slug_to_text,
)
from career_radar.config import ENGLISH_SEARCH_TERMS, SEARCH_TERMS
from career_radar.models import Job

SOURCE = "remotojob"

_SITEMAP_URL = "https://remotojob.com/rj-job-sitemap1.xml"
_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)
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


def _url_slug(url: str) -> str:
    """".../oferta/responsable-de-plataforma-sap/" -> "responsable-de-plataforma-sap"."""
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else ""


def _parse_date_posted(raw: str) -> tuple[date | None, int]:
    try:
        posted = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None, 999
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    days_old = max((datetime.now(UTC) - posted.astimezone(UTC)).days, 0)
    return posted.date(), days_old


def _build_job(url: str, posting: dict) -> Job | None:
    title = clean_text(posting.get("title", ""))
    if not title:
        return None
    organization = posting.get("hiringOrganization") or {}
    company = clean_text(organization.get("name", "")) or "Unknown"

    if criteria.title_is_rejected(title, company):
        return None

    # WP Job Manager (the plugin behind this board) embeds real HTML in the
    # description, unlike Hireline's entity-only text.
    description = clean_text(BeautifulSoup(posting.get("description", ""), "html.parser").get_text(" "))
    if not description:
        return None

    posted_at, days_old = _parse_date_posted(posting.get("datePosted", ""))

    return Job(
        source=SOURCE,
        source_job_id=_url_slug(url),
        title=title,
        company=company,
        description=description,
        url=url,
        posted_at=posted_at,
        days_old=days_old,
    )


class RemotoJobCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def collect(self) -> Iterator[Job]:
        urls = _list_job_urls(self._client)
        # Cheap prefilter on the slug alone, same reasoning as Hireline: the
        # sitemap gives no title text, and ~200 postings/batch is too many to
        # fetch in full every run.
        candidates = [url for url in urls if matches_any_term(slug_to_text(_url_slug(url)), _ALL_TERMS)]

        for url in candidates:
            cancellation.check()
            try:
                response = get(self._client, url)
            except _REQUEST_ERRORS:
                continue
            posting = extract_job_posting_ld_json(response.text)
            if posting is None:
                continue
            job = _build_job(url, posting)
            if job is not None:
                yield job
            gentle_pause()
