"""LinkedIn collector — real-browser listing + HTTP guest-endpoint detail-fetch.

History, so nobody re-does this dance:

1. Original: drove a real browser through `https://www.linkedin.com/jobs/search/`.
2. EATP-019 (2026-08-13): that page broke — LinkedIn had shipped a new
   authenticated "AI job search" UI with no stable scraping hooks left (no
   `data-occludable-job-id`, only build-hashed CSS classes). Confirmed live it
   wasn't a captcha/block/genuinely-zero-results — moved the whole collector
   onto the public **guest** search endpoint
   (`jobs-guest/jobs/api/seeMoreJobPostings/search`) instead: no browser, no
   login wall, no account-ban risk.
3. EATP-020 (2026-08-14): found the guest endpoint's `location=` param was
   silently ignored for remote results (real Miami/Texas/DC jobs came back);
   fixed with a resolved `geoId`. Parallelized listing across search terms.
4. EATP-021 (2026-08-15): tried more concurrency — live A/B proved it
   silently drops real jobs (rate-limiting mistaken for "end of results").
5. **EATP-022 (2026-08-15): the classic `/jobs/search/` UI is back.**
   Kevin ran the original legacy project directly and got 28 real, fresh
   LinkedIn jobs in ~5 minutes total (alongside 2 other sources + AI) using
   real-browser scraping. Live-retested here with career-radar's own existing
   isolated profile (not Kevin's personal Chrome — never needed that):
   `/jobs/search/` no longer redirects to the broken UI, `data-occludable-job-id`
   is back on every card. LinkedIn evidently reverted that redesign (or it was
   a temporary experiment) sometime between 2026-08-13 and 2026-08-15 — the
   EATP-019 finding was accurate for its moment, just went stale before
   anyone re-checked. Bonus: the real UI's `location=México` also turned out
   far more geo-accurate than the guest endpoint's ever was (14% U.S.-signal
   rate in a live sample vs. 44% before EATP-020's geoId fix) — logged-in
   session search resolves location properly where the anonymous guest
   endpoint didn't.

   Live-verified end to end (2026-08-15, real network + real browser, both
   headless and headful): 61-66s for 23 jobs on two runs, 164.8s for 69 jobs
   on a third (day-to-day/hour-to-hour variance in how much LinkedIn has to
   show) — every one of them a fraction of the guest endpoint's 534-580s.
   Geo accuracy on the 69-job run: only 6/69 (8.7%) carried a U.S.-eligibility
   signal in the description, and `location_raw` was overwhelmingly real
   Mexican cities/regions (México, Ciudad de México, Guadalajara, Monterrey,
   América Latina, ...) — better than even legacy's own 14% rate on the same
   kind of real-browser search.

So: listing moves back to the real browser (this file). Detail-fetch stays
exactly as EATP-019 left it — `linkedin_api.py`'s anonymous guest endpoint —
it was never the bottleneck and carries zero account risk regardless of
which surface lists the ids.

Multi-tab search + login-wall handling ported from
`legacy/jobmatch/collectors/linkedin.py`'s site knowledge (scrolling to load
the lazy-loaded results panel, `start=`-based pagination), NOT its code
as-is (CLAUDE.md golden rule 12): the blocking `input()` login flow and
inline gate logic don't belong here — login-wall handling mirrors
`indeed.py`'s non-blocking `_CaptchaCoordination` pattern (shared deadline
across tabs, one event per episode, `intervention_resolved` the moment it
clears), and every quality decision (title/English/remote) still lives
downstream in `quality/filters.py`, never inline in the collector.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from queue import Empty, Queue
from urllib.parse import quote

from career_radar import config, criteria
from career_radar.collectors import browser
from career_radar.collectors.linkedin_api import fetch_job_details
from career_radar.collectors.parsing import clean_text, parse_days_old_es
from career_radar.models import Job

SOURCE = "linkedin"

BASE_URL = "https://www.linkedin.com/jobs/search/"
LOCATION = "México"
# The real UI's classic panel size (confirmed live, EATP-022) — different
# from the guest endpoint's 10-per-page.
_PAGE_SIZE = 25
_MAX_PAGES_PER_TERM = 10
# Legacy's own proven tab count for listing (its docstring: "4 pestañas en
# paralelo"). Detail-fetch stays on the separate, cheap, anonymous HTTP path
# (`linkedin_api.py`) so this only costs browser-tab overhead, not account risk.
#
# EATP-025 (2026-08-17): briefly dropped to 2 on a memory theory that never
# held up — no kernel OOM ever appeared, and the WSL VM sat at ~1.1GB of
# 9.7GB used through every crash. Reverted to legacy's 4. The real cause was
# `page.quit()` hanging on an already-dead browser (see `browser.close_page`).
_SEARCH_WORKERS = 4

_JOB_ID_PATTERN = re.compile(r'data-occludable-job-id="(\d+)"')
_LOGIN_URL_MARKERS = ("/login", "/checkpoint", "/authwall")
_NO_RESULTS_MARKERS = (
    "no se han encontrado empleos para esta búsqueda",
    "no matching jobs found",
    "no jobs found for this search",
)

_LOGIN_WAIT_SECONDS = 300
_LOGIN_POLL_SECONDS = 10


# ---------------------------------------------------------------------------
# Pure decision logic — no network needed, fully unit-testable.
# ---------------------------------------------------------------------------


def build_search_url(query: str, start: int = 0) -> str:
    return (
        f"{BASE_URL}"
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


def is_login_page(url: str) -> bool:
    lowered = (url or "").lower()
    return any(marker in lowered for marker in _LOGIN_URL_MARKERS)


def page_has_no_real_results(html: str) -> bool:
    lowered = (html or "").lower()
    return any(marker in lowered for marker in _NO_RESULTS_MARKERS)


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
# Login-wall coordination — shared across search tabs for one `collect()`
# call, same shape as `indeed.py`'s `_CaptchaCoordination` (proven in
# EATP-020/021: one shared deadline, one event per episode, resettable so a
# second episode later in the same run gets its own fresh notification).
# ---------------------------------------------------------------------------


class _LoginCoordination:
    def __init__(self) -> None:
        self.giveup = threading.Event()
        self._lock = threading.Lock()
        self._deadline: float | None = None

    def report_and_get_deadline(self, message: str) -> tuple[float, bool]:
        """Returns `(deadline, is_new_episode)` — see `indeed.py`'s
        `_CaptchaCoordination.report_and_get_deadline` for why: only the tab
        that actually reported a new episode should `bring_to_front()`
        itself, not every tab that independently discovers the same
        session-wide block."""
        with self._lock:
            is_new = self._deadline is None
            if is_new:
                self._deadline = time.monotonic() + _LOGIN_WAIT_SECONDS
                browser.request_manual_intervention(SOURCE, message)
            return self._deadline, is_new

    def resolved(self) -> None:
        with self._lock:
            self._deadline = None
        browser.clear_manual_intervention(SOURCE)


# ---------------------------------------------------------------------------
# Browser orchestration
# ---------------------------------------------------------------------------


class LinkedInCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(
        self,
        page_factory=None,
        search_workers: int = _SEARCH_WORKERS,
        detail_fetcher=fetch_job_details,
    ) -> None:
        self._page_factory = page_factory or (
            lambda: browser.build_page(use_profile=True, start_minimized=True)
        )
        self._search_workers = search_workers
        self._detail_fetcher = detail_fetcher

    def collect(self) -> Iterator[Job]:
        page = self._page_factory()
        coord = _LoginCoordination()
        browser.start_cancellation_watcher(coord.giveup)
        ids_by_term: dict[str, list[str]] = {}
        try:
            browser.run_bounded(
                lambda: self._collect_all_term_ids(page, coord, ids_by_term),
                coord.giveup,
                SOURCE,
            )
        finally:
            browser.close_page(page)

        # Merge in a fixed order (config.SEARCH_TERMS, then page order within
        # a term) so the result is deterministic regardless of which tab
        # finished first.
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

    def _collect_all_term_ids(
        self, page, coord: _LoginCoordination, results: dict[str, list[str]]
    ) -> None:
        """Fan search terms out across a small pool of browser tabs — mirrors
        `indeed.py::_fetch_details`'s worker-per-tab-pulling-a-shared-queue
        shape, just for listing instead of detail-fetch.

        Writes into the caller-owned `results` dict rather than returning
        one: the caller runs this whole method inside `browser.run_bounded`
        (EATP-025), which can abandon it mid-flight if the browser dies —
        writing in place means whatever terms had already finished are still
        there for the caller to use even then."""
        worker_count = max(1, min(self._search_workers, len(config.SEARCH_TERMS)))
        tabs = [page] + [page.browser.new_tab() for _ in range(worker_count - 1)]

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

    def _collect_term_ids(self, tab, term: str, coord: _LoginCoordination) -> list[str]:
        term_ids: list[str] = []
        for page_number in range(_MAX_PAGES_PER_TERM):
            if coord.giveup.is_set():
                break
            start = page_number * _PAGE_SIZE
            url = build_search_url(term, start)
            if not self._navigate(tab, url, f"búsqueda '{term}' página {page_number + 1}", coord):
                break

            if page_has_no_real_results(tab.html or ""):
                break

            self._expand_results_panel(tab)
            page_ids = extract_job_ids(tab.html or "")
            if not page_ids:
                break

            term_ids.extend(page_ids)
            if len(page_ids) < _PAGE_SIZE:
                break
            browser.human_pause()

        return term_ids

    def _expand_results_panel(self, tab) -> None:
        """Scroll the lazy-loaded results panel until the card count stops
        growing (bounded — never an infinite scroll), same technique as
        legacy's `expand_results_panel`."""
        previous_count = -1
        stable_rounds = 0
        for _ in range(8):
            current_count = len(extract_job_ids(tab.html or ""))
            if current_count <= previous_count:
                stable_rounds += 1
                if stable_rounds >= 2:
                    break
            else:
                stable_rounds = 0
            previous_count = current_count
            try:
                tab.scroll.down(1200)
            except Exception:  # noqa: BLE001, S110 - a scroll failing just means "read what's there"
                pass
            time.sleep(0.2)

    def _navigate(self, tab, url: str, context: str, coord: _LoginCoordination) -> bool:
        if coord.giveup.is_set():
            return False
        tab.get(url)
        browser.human_pause()
        if not is_login_page(tab.url or ""):
            return True
        return self._wait_for_login(tab, url, context, coord)

    def _wait_for_login(
        self, tab, url: str, context: str, coord: _LoginCoordination
    ) -> bool:
        """Kevin's call (2026-08-12, mirrored from `indeed.py`): solve it
        himself in the browser window rather than the run giving up
        immediately. Publishes ONE event for the whole `collect()` call and
        polls passively — re-navigating only to check, never hammering."""
        deadline, is_new = coord.report_and_get_deadline(
            f"LinkedIn pide iniciar sesión ({context}); inicia sesión en la ventana "
            f"del navegador — la corrida espera hasta {_LOGIN_WAIT_SECONDS // 60} minutos."
        )
        if is_new:
            # EATP-023: starts minimized — this is the one moment it
            # actually needs his eyes, so raise it now, maximized. Only the
            # tab that reported this episode does it (see `indeed.py`'s
            # identical fix for why).
            browser.bring_to_front(tab)

        while time.monotonic() < deadline:
            if coord.giveup.is_set():
                return False
            time.sleep(_LOGIN_POLL_SECONDS)
            if coord.giveup.is_set():
                return False

            tab.get(url)
            browser.human_pause()
            if not is_login_page(tab.url or ""):
                coord.resolved()
                return True

        if not coord.giveup.is_set():
            coord.giveup.set()
            browser.request_manual_intervention(
                SOURCE,
                f"LinkedIn sigue pidiendo inicio de sesión tras esperar ({context}); "
                "se omite LinkedIn en esta corrida.",
            )
        return False
