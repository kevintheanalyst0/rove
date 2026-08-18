"""Indeed collector — sequential search, 2 parallel tabs for job details.

Deliberately NOT ported from `legacy/jobmatch/collectors/indeed.py` as-is
(CLAUDE.md golden rule 12): legacy ran 2 search tabs + 3 detail tabs
coordinated with a captcha lock/event, and blocked the whole run on
`input()` the moment any tab hit a captcha — the exact anti-pattern
ADR-004/R11-R12 rule out. It also scraped `hiringOrganization`/`datePosted`
with regex over raw HTML instead of parsing the `JobPosting` JSON-LD block
Indeed actually embeds.

Rebuilt: JSON-LD parsing via BeautifulSoup + `json.loads`, and captcha
handling mirrors LinkedIn's login flow (`collectors/linkedin.py`) instead of
the original zero-intervention design: Kevin watched a live run through the
EATP-015 runner UI (2026-08-12) and decided he'd rather solve a captcha
himself than lose Indeed for that run. On captcha it publishes ONE event
asking him to resolve it in the browser window, then polls (no re-navigation
spam — a passive re-check every `_CAPTCHA_POLL_SECONDS`) for up to
`_CAPTCHA_WAIT_SECONDS`; if it clears, the run continues as if nothing
happened. Only past that deadline — an unattended/scheduled run, say — does
Indeed give up cleanly for this run.

EATP-022 (2026-08-15): search-id collection now fans out across 2 tabs too
(was single-tab/sequential) — legacy's own proven search-tab count, same
worker-per-tab-pulling-a-shared-queue shape as detail-fetch below. Detail
fetching — one request per job — uses its own small pool of browser tabs (3,
bumped from 2 in EATP-021, matching legacy's own detail-tab count). Because
Indeed's captcha is session/IP-wide, not per-tab, more tabs (search or
detail) don't make captchas "block everything" any worse than a single tab
would: captcha in any one tab starts the SAME shared wait (one deadline, one
published event — not one per tab) that every other tab waits out too, and
whatever was already fetched before that point is preserved (each detail tab
streams its own successes into a shared result queue).

What's kept from legacy because it's genuine site knowledge: the search
filter params (`fromage=14` / remote attr `DSQF7`), the pagination
loop-detection via page-id signatures (SCRAPING-GOTCHAS.md #2 flags this as
a general safety net worth carrying forward, not just an Indeed quirk), and
the captcha marker strings.

EATP-022 (2026-08-15): Kevin ran legacy directly and got Indeed done in ~79s
(27 jobs) vs. our ~213-380s for a similar count — closed most of that gap
without touching captcha handling. Two changes: (1) search-id collection now
uses 2 tabs (above), and (2) detail-page navigation's pause shrank from the
default 1.5-4.0s to 0.3-0.8s (`_fetch_detail_html`'s `pause_range` — search
pages keep the longer default, they have no dedicated content-ready wait the
way `_wait_for_detail_content`'s selector-based wait already gives detail
pages, so shrinking search's pause risked silently under-reading a
half-rendered results page the same way EATP-021's LinkedIn concurrency bump
silently lost jobs). Live-verified twice, same real job set both times
(identical 29 jobs, same titles/companies): 233.6s before the pacing change,
102.9s after — more than 2x, with zero evidence of under-collection.

EATP-023 (2026-08-16, Kevin, live x2): two real bugs surfaced from watching
actual captchas happen.
- Indeed's block is session-wide, so multiple tabs can genuinely discover
  the *same* still-active captcha within the same instant — `bring_to_front`
  was called by every tab that detected it, not just the one reporting the
  episode, so they raced to activate/maximize themselves. Fixed by gating
  it on `report_and_get_deadline`'s new `is_new_episode` return.
- Persistent false alarms — confirmed by Kevin as real detection false
  positives, not a rendering artifact (his proof: in legacy, a genuine
  captcha froze *every* tab until he pressed Enter; a "false" one there
  left everything running normally when he checked, which our own code
  reproduces the same way — a false marker match doesn't actually block
  anything either). A marker match right after `human_pause()` can be a
  transient loading state that clears within a couple seconds on its own;
  `_navigate` now waits `_CAPTCHA_DEBOUNCE_SECONDS` and checks once more
  before ever reporting anything — a genuine block is still there, a
  transient one usually isn't.

EATP-023, reverted (2026-08-16, Kevin, live): the "start minimized,
`bring_to_front()` only on captcha" behavior above never worked reliably in
practice across several live rounds (WSLg wouldn't reliably raise/repaint
the window) and Kevin asked to drop it entirely — back to the pre-EATP-023
behavior this collector had all along: the window opens maximized and stays
visible for the whole run, so he can just watch it and solve a captcha the
moment it appears, no window-raising logic needed at all. The `needs_intervention`/
`intervention_resolved` notice banner in the web UI (unrelated — EATP-020) stays.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from queue import Empty, Queue
from urllib.parse import quote

from bs4 import BeautifulSoup

from career_radar import config, criteria
from career_radar.collectors import browser
from career_radar.collectors.parsing import clean_text
from career_radar.models import Job

SOURCE = "indeed"
# EATP-021: bumped 2->3 (Kevin's call, 2026-08-15, after Indeed was confirmed
# a real time sink and the captcha-banner UX got fixed in EATP-020) — back up
# to legacy's own proven detail-tab count, not beyond it. Captcha risk is
# still bounded the same way regardless of tab count: Indeed's block is
# session/IP-wide, not per-tab (see `_CaptchaCoordination`), so more tabs
# don't multiply captcha exposure, just how fast legitimate pages get read.
_DETAIL_WORKERS = 3
# EATP-022: search-id collection was single-tab/sequential — legacy ran 2
# parallel search tabs. Same session/IP-wide captcha-risk reasoning as
# `_DETAIL_WORKERS` applies (more tabs don't multiply exposure).
_SEARCH_WORKERS = 2

BASE_URL = "https://mx.indeed.com/jobs"
DETAIL_URL = "https://mx.indeed.com/viewjob"
_PAGE_SIZE = 10
_MAX_PAGES_PER_TERM = (
    20  # safety net; fromage=14 means real listings rarely go this deep
)

# EATP-023 (Kevin, live, 2026-08-16): a false captcha alarm popped a blank
# window — root-caused separately (see `browser.bring_to_front`), but while
# investigating, the bare `"captcha"` marker stood out as the likely reason
# a *normal* page reads as a captcha in the first place: this checks the
# entire page HTML, and a bare mention of the word (e.g. a defensive
# reCAPTCHA badge/script Indeed may embed on ordinary pages, not just
# challenge pages) is enough to false-trigger — legacy had this exact same
# bare-word check and Kevin confirmed it had the same false-alarm behavior
# there too, so this isn't a regression, just never fixed. Split the check:
# the full HTML body only trusts specific, low-noise phrases; a bare
# "captcha" is still trusted in the page *title* (a short, curated string —
# far less likely to pick up incidental boilerplate than the whole body).
#
# Kevin confirmed (2026-08-16) the actual challenge is Cloudflare's own
# interstitial, not something Indeed built — added its real, narrative copy
# (only ever shown when it's replaced the *entire* page — never boilerplate
# sitting quietly on a normal one, unlike a bare "captcha"/CDN mention) as
# stronger, more specific signals alongside the originals.
_HTML_CAPTCHA_MARKERS = (
    "security check",
    "verifica que eres humano",
    "checking your browser before accessing",
    "needs to review the security of your connection",
    "necesita revisar la seguridad de tu conexión",
    "cf-browser-verification",
    "cdn-cgi/challenge-platform",
)
_TITLE_CAPTCHA_MARKERS = (
    "security check",
    "verifica que eres humano",
    "captcha",
    "just a moment",
    "un momento",
)
_NO_RESULTS_MARKERS = (
    "no ha producido ningún resultado",
    "no matching jobs found",
    "no results found",
)

# Kevin's call (2026-08-12, after watching a live run): wait for HIM to solve
# it, same bounded-wait shape as LinkedIn's login flow, not a blind cooldown.
_CAPTCHA_WAIT_SECONDS = 300
_CAPTCHA_POLL_SECONDS = 10
# EATP-023: before trusting a captcha marker match enough to notify Kevin,
# wait this long and check once more — a transient loading state usually
# clears within a few seconds; a real block doesn't.
_CAPTCHA_DEBOUNCE_SECONDS = 3


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
    html_lower = (html or "").lower()
    title_lower = (title or "").lower()
    return any(marker in html_lower for marker in _HTML_CAPTCHA_MARKERS) or any(
        marker in title_lower for marker in _TITLE_CAPTCHA_MARKERS
    )


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
        # Indeed's real JSON-LD uses "datePosted", not schema.org's usual
        # "datePublished" — confirmed against a live detail page.
        "posted": clean_text(str(ld.get("datePosted") or "")),
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


class _CaptchaCoordination:
    """Shared across the search tab and every detail tab for one `collect()`
    call. The moment any one of them hits a captcha, all of them wait out the
    SAME deadline (set once, by whichever tab hits it first) instead of each
    starting its own timer, and only one `needs_intervention` event is
    published — not one per tab. `giveup` still means "stop everything": set
    once the shared deadline passes without the captcha clearing.

    Kevin's experience (2026-08-13): a single run can hit more than one
    captcha, minutes apart. `_deadline` is reset back to `None` once a
    captcha clears (`resolved()`) specifically so the *next* occurrence gets
    its own fresh `_CAPTCHA_WAIT_SECONDS` window and its own notification —
    without the reset, a second captcha would silently reuse the first one's
    already-expired deadline and Indeed would give up on itself without ever
    telling Kevin.
    """

    def __init__(self) -> None:
        self.giveup = threading.Event()
        self._lock = threading.Lock()
        self._deadline: float | None = None

    def report_and_get_deadline(self, message: str) -> tuple[float, bool]:
        """Returns `(deadline, is_new_episode)` — `is_new_episode` tells the
        caller whether *this* call was the one that just reported (vs. a
        concurrent tab piling onto an already-reported episode), so only one
        tab ever tries to `bring_to_front()` itself per episode (EATP-023,
        Kevin's report: multiple tabs independently racing to activate/
        maximize themselves — the block is session-wide, so several of them
        can genuinely hit it within milliseconds of each other — produced
        exactly the chaos he saw: the wrong tab shown, an odd fullscreen-like
        flash, and total silence on a later episode where the "losing" tab's
        CDP calls apparently never took effect)."""
        with self._lock:
            is_new = self._deadline is None
            if is_new:
                self._deadline = time.monotonic() + _CAPTCHA_WAIT_SECONDS
                browser.request_manual_intervention(SOURCE, message)
            return self._deadline, is_new

    def resolved(self) -> None:
        with self._lock:
            self._deadline = None


class IndeedCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(
        self,
        page_factory=None,
        detail_workers: int = _DETAIL_WORKERS,
        search_workers: int = _SEARCH_WORKERS,
    ) -> None:
        self._page_factory = page_factory or (lambda: browser.build_page(use_profile=True))
        self._detail_workers = detail_workers
        self._search_workers = search_workers

    def collect(self) -> Iterator[Job]:
        page = self._page_factory()
        coord = _CaptchaCoordination()
        browser.start_cancellation_watcher(coord.giveup)
        try:
            ids_by_term: dict[str, list[str]] = {}
            browser.run_bounded(
                lambda: self._collect_all_term_ids(page, coord, ids_by_term),
                coord.giveup,
                SOURCE,
            )

            seen: set[str] = set()
            ordered_ids: list[str] = []
            for term in config.SEARCH_TERMS:
                for job_id in ids_by_term.get(term, []):
                    if job_id not in seen:
                        seen.add(job_id)
                        ordered_ids.append(job_id)

            yield from self._fetch_details(page, ordered_ids, coord)
        finally:
            browser.close_page(page)

    def _collect_all_term_ids(
        self, page, coord: _CaptchaCoordination, results: dict[str, list[str]]
    ) -> None:
        """Fan search terms out across a small pool of tabs — legacy's own
        proven search-tab count (2), EATP-022. Same worker-per-tab-pulling-
        a-shared-queue shape as `_fetch_details` below, just for listing.

        Writes into the caller-owned `results` dict rather than returning
        one: the caller runs this whole method inside `browser.run_bounded`
        (EATP-025), which can abandon it mid-flight if the browser dies —
        writing in place means whatever terms had already finished are still
        there for the caller to use even then."""
        worker_count = max(1, min(self._search_workers, len(config.SEARCH_TERMS)))
        tabs = [page] + [page.new_tab() for _ in range(worker_count - 1)]

        term_queue: Queue[str] = Queue()
        for term in config.SEARCH_TERMS:
            term_queue.put(term)
        results_lock = threading.Lock()

        def worker(tab) -> None:
            while not coord.giveup.is_set():
                try:
                    term = term_queue.get_nowait()
                except Empty:
                    return
                try:
                    ids = self._collect_term_ids(tab, term, coord)
                    with results_lock:
                        results[term] = ids
                finally:
                    term_queue.task_done()

        threads = [threading.Thread(target=worker, args=(tab,)) for tab in tabs]
        for thread in threads:
            thread.start()
            browser.human_pause(0.3, 0.8)  # stagger tab starts, not a single burst
        for thread in threads:
            thread.join()

    def _collect_term_ids(
        self, page, term: str, coord: _CaptchaCoordination
    ) -> list[str]:
        term_ids: list[str] = []
        seen_ids: set[str] = set()
        seen_page_signatures: set[tuple[str, ...]] = set()

        for page_number in range(1, _MAX_PAGES_PER_TERM + 1):
            if coord.giveup.is_set():
                break
            start = (page_number - 1) * _PAGE_SIZE
            url = build_search_url(term, start)
            if not self._navigate(
                page, url, f"búsqueda '{term}' página {page_number}", coord
            ):
                break

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

    def _fetch_details(
        self, page, job_ids: list[str], coord: _CaptchaCoordination
    ) -> Iterator[Job]:
        """Fan out detail fetches across a small pool of browser tabs.

        Each tab is its own thread pulling from a shared queue — one job
        never blocks another's tab. Results collect into a shared queue and
        are yielded once every tab has finished (or given up), so a
        mid-phase captcha still preserves every job successfully fetched
        before it hit.
        """
        if not job_ids or coord.giveup.is_set():
            return

        job_queue: Queue[str] = Queue()
        for job_id in job_ids:
            job_queue.put(job_id)
        results: Queue[Job] = Queue()

        def worker(tab) -> None:
            while not coord.giveup.is_set():
                try:
                    job_id = job_queue.get_nowait()
                except Empty:
                    return
                try:
                    detail_html = self._fetch_detail_html(tab, job_id, coord)
                    if detail_html is None:
                        continue
                    detail = parse_detail_page(detail_html)
                    if detail is None:
                        continue
                    job = _build_job(job_id, detail)
                    if job is not None:
                        results.put(job)
                finally:
                    job_queue.task_done()

        def run() -> None:
            # Tab setup (`new_tab()`) runs here too, not just the workers —
            # EATP-025: opening this pool's own tabs is just as capable of
            # blocking forever on a dead browser as anything a worker does
            # afterward, so it needs to be inside `run_bounded`'s wrapped
            # call, not before it.
            worker_count = max(1, min(self._detail_workers, len(job_ids)))
            tabs = [page] + [page.new_tab() for _ in range(worker_count - 1)]
            threads = [threading.Thread(target=worker, args=(tab,)) for tab in tabs]
            for thread in threads:
                thread.start()
                browser.human_pause(0.3, 0.8)  # stagger tab starts, not a single burst
            for thread in threads:
                thread.join()

        browser.run_bounded(run, coord.giveup, SOURCE)

        while not results.empty():
            yield results.get_nowait()

    def _fetch_detail_html(
        self, tab, job_id: str, coord: _CaptchaCoordination
    ) -> str | None:
        url = build_job_view_url(job_id)
        # EATP-022: detail pages have a real content-ready wait right below
        # (`_wait_for_detail_content`, selector-based, not a blind pause) —
        # `_navigate`'s own pause can be much shorter here without losing
        # that safety net. Search pages have no such selector wait, so they
        # keep the longer default (see `_navigate`).
        if not self._navigate(tab, url, f"detalle {job_id}", coord, pause_range=(0.3, 0.8)):
            return None
        self._wait_for_detail_content(tab)
        return tab.html or ""

    def _wait_for_detail_content(self, tab) -> None:
        """Give a slow-rendering detail page a bounded chance to finish
        before reading its HTML. Without this, a real posting that's just
        slower to render (heavier JS, or 2 tabs competing for resources)
        reads as an empty page — no JSON-LD yet — and gets silently
        skipped as if it never existed. Same idea as legacy's
        `wait.ele_loaded(..., timeout=5)`, which the initial build dropped."""
        try:
            tab.ele("css:#jobDescriptionText", timeout=5)
        except Exception:  # noqa: BLE001, S110 - a missing/slow element just means "read whatever's there"
            pass

    def _navigate(
        self,
        tab,
        url: str,
        context: str,
        coord: _CaptchaCoordination,
        pause_range: tuple[float, float] = (1.5, 4.0),
    ) -> bool:
        """Load `url` on `tab`; on captcha, wait for Kevin to solve it (see
        `_wait_for_captcha_resolution`); report failure so the caller moves
        on if it never clears.

        `pause_range` defaults to `browser.human_pause`'s own default —
        search pages have no dedicated content-ready wait, so this pause is
        what gives Indeed's results time to render before `_extract_ids`
        reads the page. Detail fetches pass a shorter range (EATP-022):
        `_wait_for_detail_content` already does the real, selector-based
        wait for those."""
        if coord.giveup.is_set():
            return False

        tab.get(url)
        browser.human_pause(*pause_range)
        if not is_captcha_page(tab.html or "", getattr(tab, "title", "") or ""):
            return True

        # EATP-023 (Kevin, live): confirmed these are real detection false
        # positives, not a rendering issue — in legacy, a genuine captcha
        # froze every tab until he pressed Enter; a "false" one left
        # everything running normally when he checked. A marker match right
        # after `human_pause()` can be a transient loading state, not the
        # final page — give it a moment to settle and check again before
        # ever telling Kevin: a real block is still there a few seconds
        # later, a transient one has usually cleared on its own.
        time.sleep(_CAPTCHA_DEBOUNCE_SECONDS)
        if not is_captcha_page(tab.html or "", getattr(tab, "title", "") or ""):
            return True

        return self._wait_for_captcha_resolution(tab, url, context, coord)

    def _wait_for_captcha_resolution(
        self, tab, url: str, context: str, coord: _CaptchaCoordination
    ) -> bool:
        """Kevin's call (2026-08-12): he'd rather solve a captcha himself in
        the browser window than have Indeed auto-skip after a short cooldown
        — mirrors LinkedIn's login wait (`linkedin.py`'s
        `_resolve_login_if_needed`). Publishes ONE event for the whole
        `collect()` call (via `coord.report_and_get_deadline`, not one per
        tab) and polls passively — re-navigating only to check, never
        hammering — until it clears or the shared deadline passes.
        """
        deadline, _is_new = coord.report_and_get_deadline(
            f"Indeed pide verificación humana ({context}); resuélvela en la ventana "
            f"del navegador — la corrida espera hasta {_CAPTCHA_WAIT_SECONDS // 60} "
            "minutos."
        )

        while time.monotonic() < deadline:
            if coord.giveup.is_set():
                return False
            time.sleep(_CAPTCHA_POLL_SECONDS)
            if coord.giveup.is_set():
                return False

            tab.get(url)
            browser.human_pause()
            if not is_captcha_page(tab.html or "", getattr(tab, "title", "") or ""):
                coord.resolved()
                browser.clear_manual_intervention(SOURCE)
                return True

        if not coord.giveup.is_set():
            coord.giveup.set()
            browser.request_manual_intervention(
                SOURCE,
                f"Indeed sigue pidiendo verificación tras esperar ({context}); "
                "se omite Indeed en esta corrida.",
            )
        return False
