"""LinkedIn collector — browser lists job ids, the guest API (linkedin_api.py)
fetches details.

Deliberately NOT ported from `legacy/jobmatch/collectors/linkedin.py` as-is
(CLAUDE.md golden rule 12): legacy ran 4 browser tabs in parallel with a
thread-coordinated global pause on rate-limiting — an aggressive pattern that
raises account-ban risk (P23) and complexity for a source
`docs/governance/SEARCH-STRATEGY.md` already calls "supplementary, not the
centerpiece." Rebuilt as a single sequential browser, one term at a time:
slower, but gentler on Kevin's real account and far simpler to reason about.

What's kept, because it's genuinely correct site knowledge: the recommended-
jobs card boundary, the page-health/rate-limit markers, and the search filter
params (remote / posted ≤24h / full-time). Login/checkpoint is handled by
publishing an event and polling with a bounded wait — never `input()`
(ADR-004) — so a stuck login pauses only this source, not the whole run.

The DOM-touching parts of `collect()` are kept as thin as possible; the
decision logic (recommendation-card / login / health detection, URL
building, job construction) lives in plain functions above it so it's fully
unit-testable without a real browser.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from career_radar import config, criteria
from career_radar.collectors import browser
from career_radar.collectors.linkedin_api import fetch_job_details
from career_radar.collectors.parsing import clean_text, parse_days_old_es
from career_radar.models import Job

SOURCE = "linkedin"

BASE_URL = "https://www.linkedin.com/jobs/search/"
LOCATION = "México"
_PAGE_SIZE = 25
_MAX_PAGES_PER_TERM = 5
_LOGIN_WAIT_SECONDS = 120
_LOGIN_POLL_SECONDS = 5

_LOGIN_MARKERS = ("/login", "/checkpoint", "/authwall")

_RECOMMENDATION_MARKERS = [
    "empleos que podrían interesarte",
    "principales empleos que te recomendamos",
    "jobs you may be interested in",
    "top job picks for you",
]

_NO_RESULTS_MARKERS = [
    "no se han encontrado empleos para esta búsqueda",
    "no matching jobs found",
    "no jobs found for this search",
]

_UNHEALTHY_MARKERS = [
    "http error 429",
    "esta página no funciona",
    "there was an error loading filters",
    "hubo un error al cargar los filtros",
    "error al cargar los filtros",
    "we couldn't load search filters",
]


# ---------------------------------------------------------------------------
# Pure decision logic — no browser needed, fully unit-testable.
# ---------------------------------------------------------------------------


def build_search_url(query: str, page: int = 1) -> str:
    start = (page - 1) * _PAGE_SIZE
    return (
        f"{BASE_URL}"
        f"?keywords={quote(query)}"
        f"&location={quote(LOCATION)}"
        f"&sortBy=DD"
        f"&f_TPR=r86400"  # posted in the last 24h
        f"&f_WT=2"  # remote
        f"&f_JT=F"  # full-time
        f"&start={start}"
    )


def build_job_view_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def is_login_page(url: str) -> bool:
    lowered = (url or "").lower()
    return any(marker in lowered for marker in _LOGIN_MARKERS)


def is_recommendation_card(card_text: str) -> bool:
    lowered = clean_text(card_text).lower()
    return any(marker in lowered for marker in _RECOMMENDATION_MARKERS)


def page_has_no_real_results(html_lower: str) -> bool:
    return any(marker in html_lower for marker in _NO_RESULTS_MARKERS)


def is_page_healthy(html_lower: str) -> bool:
    return not any(marker in html_lower for marker in _UNHEALTHY_MARKERS)


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
# Browser orchestration — thin; calls the pure functions above.
# ---------------------------------------------------------------------------


class LinkedInCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, page_factory=None, detail_fetcher=fetch_job_details) -> None:
        self._page_factory = page_factory or (lambda: browser.build_page(use_profile=True))
        self._detail_fetcher = detail_fetcher

    def collect(self) -> Iterator[Job]:
        page = self._page_factory()
        try:
            seen: set[str] = set()
            ordered_ids: list[str] = []
            for term in config.SEARCH_TERMS:
                for job_id in self._collect_term_ids(page, term):
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
        finally:
            page.quit()

    def _collect_term_ids(self, page, term: str) -> Iterator[str]:
        for page_number in range(1, _MAX_PAGES_PER_TERM + 1):
            page.get(build_search_url(term, page_number))
            page.wait.doc_loaded()
            browser.human_pause()

            if not self._resolve_login_if_needed(page, term, page_number):
                return

            html_lower = (page.html or "").lower()
            if not is_page_healthy(html_lower):
                browser.request_manual_intervention(
                    SOURCE,
                    f"LinkedIn parece estar limitando el ritmo (término '{term}', "
                    f"página {page_number}); se omite el resto de este término.",
                )
                return
            if page_has_no_real_results(html_lower):
                return

            results_panel = self._find_results_panel(page)
            if results_panel is None:
                return

            cards = self._load_cards(results_panel)
            if not cards:
                return

            page_ids: list[str] = []
            hit_recommendations = False
            for card in cards:
                if is_recommendation_card(card.text):
                    hit_recommendations = True
                    break
                job_id = card.attr("data-occludable-job-id") or card.attr("data-job-id")
                if job_id and str(job_id).strip().isdigit():
                    page_ids.append(str(job_id).strip())

            yield from page_ids

            if hit_recommendations or len(page_ids) < _PAGE_SIZE:
                return

            browser.human_pause()

    def _find_results_panel(self, page):
        for selector in ("css:div.jobs-search-results-list", "css:div.scaffold-layout__list"):
            try:
                panel = page.ele(selector, timeout=2)
            except Exception:  # noqa: BLE001 - a missing/slow selector means "try the next one"
                panel = None
            if panel:
                return panel
        return None

    def _load_cards(self, results_panel):
        for selector in ("css:li[data-occludable-job-id]", "css:li[data-job-id]"):
            try:
                cards = results_panel.eles(selector)
            except Exception:  # noqa: BLE001 - a missing selector means "try the next one"
                cards = None
            if cards:
                return cards
        return []

    def _resolve_login_if_needed(self, page, term: str, page_number: int) -> bool:
        if not is_login_page(page.url or ""):
            return True

        browser.request_manual_intervention(
            SOURCE,
            f"LinkedIn pide iniciar sesión (término '{term}', página {page_number}). "
            "Resuélvelo en la ventana del navegador — la corrida espera unos minutos.",
        )
        deadline = time.monotonic() + _LOGIN_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(_LOGIN_POLL_SECONDS)
            if not is_login_page(page.url or ""):
                return True
        return False
