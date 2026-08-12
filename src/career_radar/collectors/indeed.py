"""Indeed collector — single sequential browser tab; JSON-LD parses details.

Deliberately NOT ported from `legacy/jobmatch/collectors/indeed.py` as-is
(CLAUDE.md golden rule 12): legacy ran 2 search tabs + 3 detail tabs
coordinated with a captcha lock/event, and blocked the whole run on
`input()` the moment any tab hit a captcha — the exact anti-pattern
ADR-004/R11-R12 rule out, and more account/complexity risk (P23) than a
source `docs/governance/SEARCH-STRATEGY.md` already treats as Tier 3. It
also scraped `hiringOrganization`/`datePublished` with regex over raw HTML
instead of parsing the `JobPosting` JSON-LD block Indeed actually embeds.

Rebuilt: one sequential tab (mirrors the LinkedIn rebuild, EATP-005), real
JSON-LD parsing via BeautifulSoup + `json.loads`, and — per Kevin's explicit
ask — a captcha requires ZERO intervention from him: it publishes an event
for visibility only, gets one self-retry after a long human-like cooldown
(a captcha here reads as a rate-limit signal, not an auth wall), and if it
still won't clear, Indeed stops cleanly for this run. Whatever was already
collected before the captcha hit is preserved (jobs stream out via `yield`
as they're built) — nothing is lost, nothing blocks, nothing asks.

What's kept from legacy because it's genuine site knowledge: the search
filter params (`fromage=14` / remote attr `DSQF7`), the pagination
loop-detection via page-id signatures (SCRAPING-GOTCHAS.md #2 flags this as
a general safety net worth carrying forward, not just an Indeed quirk), and
the captcha marker strings.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from bs4 import BeautifulSoup

from career_radar import config, criteria
from career_radar.collectors import browser
from career_radar.collectors.parsing import clean_text
from career_radar.models import Job

SOURCE = "indeed"

BASE_URL = "https://mx.indeed.com/jobs"
DETAIL_URL = "https://mx.indeed.com/viewjob"
_PAGE_SIZE = 10
_MAX_PAGES_PER_TERM = (
    20  # safety net; fromage=14 means real listings rarely go this deep
)

_CAPTCHA_MARKERS = ("security check", "verifica que eres humano", "captcha")
_NO_RESULTS_MARKERS = (
    "no ha producido ningún resultado",
    "no matching jobs found",
    "no results found",
)

# A captcha here is treated as a rate-limit signal, not an auth wall: one
# long human-like cooldown, one retry, then give up for this run — never a
# bounded wait-for-a-human like LinkedIn's login flow.
_CAPTCHA_RETRY_WAIT_SECONDS = (30.0, 90.0)


# ---------------------------------------------------------------------------
# Pure decision logic — no browser needed, fully unit-testable.
# ---------------------------------------------------------------------------


def build_search_url(query: str, start: int = 0) -> str:
    return (
        f"{BASE_URL}"
        f"?q={quote(query)}"
        f"&fromage=14"  # posted in the last 14 days
        f"&sc=0kf%3Aattr%28DSQF7%29%3B"  # remote attribute filter
        f"&start={start}"
    )


def build_job_view_url(job_id: str) -> str:
    return f"{DETAIL_URL}?jk={job_id}"


def is_captcha_page(html: str, title: str = "") -> bool:
    lowered = f"{html or ''} {title or ''}".lower()
    return any(marker in lowered for marker in _CAPTCHA_MARKERS)


def is_search_no_results(html_lower: str) -> bool:
    return any(marker in html_lower for marker in _NO_RESULTS_MARKERS)


def extract_job_id_from_card(data_jk: str | None, card_html: str = "") -> str | None:
    """Prefer the card link's `data-jk` attribute; fall back to the id
    embedded in the title link's own markup (`id="jobTitle-<hash>"`) —
    Indeed doesn't always render both consistently (kept from legacy)."""
    job_id = (data_jk or "").strip()
    if not job_id:
        match = re.search(r'id="jobTitle-([a-f0-9]+)"', card_html or "")
        if match:
            job_id = match.group(1)
    return job_id or None


def parse_job_ld(html: str) -> dict | None:
    """Parse the `JobPosting` JSON-LD block Indeed embeds on every detail page."""
    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return None


def _company_from_ld(ld: dict | None) -> str:
    org = (ld or {}).get("hiringOrganization")
    if isinstance(org, dict):
        return clean_text(org.get("name", ""))
    return ""


def parse_detail_page(html: str) -> dict[str, str] | None:
    """Extract title/company/description/posted-date from a rendered detail
    page. Returns None when there's no usable `JobPosting` data (captcha,
    pulled posting, etc.) — the caller treats that as "skip this job"."""
    ld = parse_job_ld(html)
    if not ld:
        return None

    soup = BeautifulSoup(html or "", "html.parser")
    description_tag = soup.select_one("#jobDescriptionText")
    description = clean_text(description_tag.get_text(" ")) if description_tag else ""

    return {
        "title": clean_text(ld.get("title", "")),
        "company": _company_from_ld(ld),
        "description": description,
        "posted": clean_text(str(ld.get("datePublished") or "")),
    }


def _days_old_from_iso(posted: str) -> int:
    if not posted:
        return 999
    try:
        published = datetime.fromisoformat(posted)
    except ValueError:
        return 999
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    return max((datetime.now(UTC) - published).days, 0)


def _build_job(job_id: str, detail: dict[str, str]) -> Job | None:
    title = clean_text(detail.get("title", ""))
    if not title:
        return None
    company = clean_text(detail.get("company", "")) or "Unknown"

    # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
    if criteria.title_is_rejected(title, company):
        return None

    days_old = _days_old_from_iso(detail.get("posted", ""))
    posted_at = (
        (datetime.now(UTC) - timedelta(days=days_old)).date()
        if days_old < 999
        else None
    )

    return Job(
        source=SOURCE,
        source_job_id=job_id,
        title=title,
        company=company,
        description=clean_text(detail.get("description", "")),
        url=build_job_view_url(job_id),
        days_old=days_old,
        posted_at=posted_at,
    )


# ---------------------------------------------------------------------------
# Browser orchestration — thin; calls the pure functions above.
# ---------------------------------------------------------------------------


class IndeedCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, page_factory=None) -> None:
        self._page_factory = page_factory or (
            lambda: browser.build_page(use_profile=True)
        )

    def collect(self) -> Iterator[Job]:
        page = self._page_factory()
        try:
            ordered_ids: list[str] = []
            seen: set[str] = set()
            for term in config.SEARCH_TERMS:
                term_ids = self._collect_term_ids(page, term)
                if term_ids is None:
                    # Persistent captcha, already retried once — stop
                    # entirely rather than keep hitting a source that's
                    # rate-limiting us term after term.
                    return
                for job_id in term_ids:
                    if job_id not in seen:
                        seen.add(job_id)
                        ordered_ids.append(job_id)

            for job_id in ordered_ids:
                detail_html = self._fetch_detail_html(page, job_id)
                if detail_html is None:
                    return
                detail = parse_detail_page(detail_html)
                if detail is None:
                    continue
                job = _build_job(job_id, detail)
                if job is not None:
                    yield job
        finally:
            page.quit()

    def _collect_term_ids(self, page, term: str) -> list[str] | None:
        term_ids: list[str] = []
        seen_ids: set[str] = set()
        seen_page_signatures: set[tuple[str, ...]] = set()

        for page_number in range(1, _MAX_PAGES_PER_TERM + 1):
            start = (page_number - 1) * _PAGE_SIZE
            url = build_search_url(term, start)
            if not self._navigate(page, url, f"búsqueda '{term}' página {page_number}"):
                return None

            html_lower = (page.html or "").lower()
            if is_search_no_results(html_lower):
                break

            page_ids = self._extract_ids(page)
            if not page_ids:
                break

            # Loop-detection safety net (SCRAPING-GOTCHAS.md #2): Indeed
            # sometimes serves the same page twice instead of advancing.
            signature = tuple(page_ids)
            if signature in seen_page_signatures:
                break
            seen_page_signatures.add(signature)

            new_ids = [job_id for job_id in page_ids if job_id not in seen_ids]
            if not new_ids:
                break
            seen_ids.update(new_ids)
            term_ids.extend(new_ids)

            if len(page_ids) < _PAGE_SIZE:
                break

            browser.human_pause()

        return term_ids

    def _extract_ids(self, page) -> list[str]:
        cards = page.eles("css:[data-testid='slider_item']")
        ids: list[str] = []
        for card in cards:
            link = card.ele("css:a[data-jk]", timeout=0)
            if not link:
                continue
            job_id = extract_job_id_from_card(link.attr("data-jk"), link.html or "")
            if job_id:
                ids.append(job_id)
        return ids

    def _fetch_detail_html(self, page, job_id: str) -> str | None:
        url = build_job_view_url(job_id)
        if not self._navigate(page, url, f"detalle {job_id}"):
            return None
        return page.html or ""

    def _navigate(self, page, url: str, context: str) -> bool:
        """Load `url`; on captcha, retry once after a long cooldown; on
        persistent captcha, publish an event (visibility only — nobody is
        asked to act) and report failure so the caller stops cleanly."""
        page.get(url)
        browser.human_pause()
        if not is_captcha_page(page.html or "", getattr(page, "title", "") or ""):
            return True

        browser.request_manual_intervention(
            SOURCE,
            f"Indeed mostró un captcha ({context}); se reintenta una vez tras una pausa.",
        )
        time.sleep(random.uniform(*_CAPTCHA_RETRY_WAIT_SECONDS))

        page.get(url)
        browser.human_pause()
        if not is_captcha_page(page.html or "", getattr(page, "title", "") or ""):
            return True

        browser.request_manual_intervention(
            SOURCE,
            f"Indeed sigue en captcha tras reintentar ({context}); se omite Indeed en esta corrida.",
        )
        return False
