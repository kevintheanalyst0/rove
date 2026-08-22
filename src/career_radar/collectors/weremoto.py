"""WeRemoto collector — HTTP-only, category-page listing + JSON-LD detail.

EATP-030 viability spike (2026-08-21): `weremoto.com` has no public search
API and its `sitemap.xml` only covers blog/event pages, not job postings —
but job postings themselves are plain server-rendered HTML (not a
client-side SPA, unlike LaPieza's dead end), reachable through fixed category
pages (`/categoria-de-trabajo/<slug>`) that list `/job-posts/<slug>` links
directly in the page body. Each posting page embeds the same schema.org
`JobPosting` JSON-LD block as Hireline/RemotoJob (`parsing.py`'s
`extract_job_posting_ld_json`), already plain text here (no HTML tags, no
stray entities).

Category list is hand-curated (same "grow it as you find more" spirit as
`config.ATS_COMPANIES`) rather than exhaustive — this board doesn't expose a
categories index worth scraping for one that's a genuine keyword match.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar import cancellation, criteria
from career_radar.collectors.http import RetryableHTTPError, build_client, gentle_pause, get
from career_radar.collectors.parsing import clean_text, extract_job_posting_ld_json
from career_radar.models import Job

SOURCE = "weremoto"

_BASE_URL = "https://www.weremoto.com"
# Live-verified 2026-08-21 to carry Data/BI-adjacent postings ("it" and
# "programacion" were near-empty that day but are the right categories for
# this profile long-term — a quiet day isn't a reason to drop them, per
# ROADMAP.md's own "measure per source, don't chase volume" principle).
_CATEGORIES = ("analista-de-datos", "it", "programacion")
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _list_job_urls(client: Client, category: str) -> list[str]:
    url = f"{_BASE_URL}/categoria-de-trabajo/{category}"
    try:
        response = get(client, url)
    except _REQUEST_ERRORS:
        return []
    # No JSON/XML on this listing page — a plain href scan is the cheapest
    # correct extraction (BeautifulSoup would parse the whole page just to
    # find <a> tags this regex-free approach gets in one pass); duplicates
    # across categories are deduped by the caller's `seen` set.
    return list(
        {
            urljoin(_BASE_URL, href)
            for href in _extract_job_post_hrefs(response.text)
        }
    )


def _extract_job_post_hrefs(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    return [
        a["href"]
        for a in soup.find_all("a", href=True)
        if "/job-posts/" in a["href"]
    ]


def _url_slug(url: str) -> str:
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else ""


def _parse_date_posted(raw: str) -> tuple[date | None, int]:
    try:
        posted = datetime.fromisoformat(raw.replace("Z", "+00:00"))
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

    description = clean_text(posting.get("description", ""))
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


class WeremotoCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def collect(self) -> Iterator[Job]:
        seen: set[str] = set()
        for category in _CATEGORIES:
            cancellation.check()
            for url in _list_job_urls(self._client, category):
                if url in seen:
                    continue
                seen.add(url)

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
