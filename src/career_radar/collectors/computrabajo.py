"""Computrabajo collector — HTTP-only, no browser needed.

Search cards already carry title + company, so the absolute title/company
pre-filter (ADR-009) genuinely saves a request here: an excluded company or
title skips the description fetch entirely, unlike OCC where title/company
only exist inside the detail payload. The real end-of-results HTML marker
(anything after it on a search page isn't a job card) was already correct in
legacy — kept as-is; OCC's collector adopted the same technique.

Deliberately NOT ported from `legacy/jobmatch/collectors/computrabajo.py`
as-is (CLAUDE.md golden rule 12): hardcoded `remote=True`, the staleness
reject, the inline English check, and the in-collector fuzzy dedup are all
centralized in EATP-009/010 now (docs/governance/SCRAPING-GOTCHAS.md §4/§7).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar import cancellation, config, criteria
from career_radar.collectors.http import (
    RetryableHTTPError,
    build_client,
    gentle_pause,
    get,
)
from career_radar.collectors.parsing import clean_text, parse_days_old_es
from career_radar.models import Job

SOURCE = "computrabajo"

# Real "end of results" marker: Computrabajo appends non-result content after
# this wrapper on every search page; anything past it is not a job card.
_END_MARKER = '<div class="tc mbB pt30 pb30">'
_MAX_PAGES_PER_TERM = 10
# get() exhausts its retries and reraises either of these — a request that
# never recovers means "skip this page/job", not "crash the collector".
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _search_url(term: str, page: int) -> str:
    slug = quote(term)
    base = f"https://mx.computrabajo.com/trabajo-de-{slug}-en-remoto"
    return base if page == 1 else f"{base}?p={page}"


def _detail_url(job_id: str) -> str:
    return f"https://oferta.computrabajo.com/offer/{job_id}/d/j?ipo=2&iapo=1"


class ComputrabajoCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _fetch_description(self, job_id: str) -> str:
        try:
            response = get(self._client, _detail_url(job_id))
        except _REQUEST_ERRORS:
            return ""
        try:
            return response.json()["o"]["ld"]
        except (ValueError, KeyError):
            return ""

    def collect(self) -> Iterator[Job]:
        # EATP-024: see greenhouse.py's identical comment — per-page (and,
        # below, per-card, since each card is its own description fetch)
        # cancellation checks.
        seen_ids: set[str] = set()
        for term in config.SEARCH_TERMS:
            for page in range(1, _MAX_PAGES_PER_TERM + 1):
                cancellation.check()
                try:
                    response = get(self._client, _search_url(term, page))
                except _REQUEST_ERRORS:
                    break

                html = response.text
                marker_found = _END_MARKER in html
                if marker_found:
                    html = html.split(_END_MARKER)[0]

                cards = BeautifulSoup(html, "html.parser").select("article.box_offer")
                if not cards:
                    break

                for card in cards:
                    cancellation.check()
                    title_element = card.select_one("a.js-o-link.fc_base")
                    if not title_element:
                        continue

                    job_id = card.get("data-id")
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title = clean_text(title_element.get_text())
                    company_element = card.select_one("a.fc_base.t_ellipsis")
                    company = (
                        clean_text(company_element.get_text()) if company_element else "Unknown"
                    )

                    # Absolute-list-only pre-filter (ADR-009) — real savings
                    # here: skips the description request entirely.
                    if criteria.title_is_rejected(title, company):
                        continue

                    date_element = card.select_one("p.fs13.fc_aux.mt15")
                    posted_text = clean_text(date_element.get_text()) if date_element else ""
                    days_old = parse_days_old_es(posted_text)

                    gentle_pause()
                    description = self._fetch_description(job_id)

                    href = title_element.get("href") or ""
                    posted_at = (
                        (datetime.now(UTC) - timedelta(days=days_old)).date()
                        if days_old < 999
                        else None
                    )

                    yield Job(
                        source=SOURCE,
                        source_job_id=job_id,
                        title=title,
                        company=company,
                        description=description,
                        url=f"https://mx.computrabajo.com{href}",
                        days_old=days_old,
                        posted_at=posted_at,
                    )

                if marker_found:
                    break
                gentle_pause()
