"""Tests for the Indeed collector.

Split by concern: pure decision logic
(URL building, captcha/no-results detection, JSON-LD parsing, job
construction) is tested directly with plain strings and real fixture data —
no browser at all. `collect()`'s orchestration, including the captcha
self-retry path, is tested against a small scripted stand-in for
DrissionPage's `ChromiumPage`. No live network, no real browser.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from queue import Empty

import pytest

from rove import config, events
from rove.collectors.indeed import (
    IndeedCollector,
    _build_job,
    _CaptchaCoordination,
    _days_old_from_iso,
    build_job_view_url,
    build_search_url,
    extract_job_id_from_card,
    is_captcha_page,
    is_search_no_results,
    parse_detail_page,
    parse_job_ld,
)
from rove.models import RemoteStatus

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "indeed_jobs.json").read_text(encoding="utf-8")
)


def _detail_from_fixture(fixture: dict) -> dict[str, str]:
    return {
        "title": fixture["title"],
        "company": fixture["company"],
        "description": fixture["description"],
        "posted": "",
    }


def _ld_html(
    *, title: str, company: str, description: str = "", date_posted: str = ""
) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "hiringOrganization": {"@type": "Organization", "name": company},
        # Indeed's real field name — confirmed live, not schema.org's usual "datePublished".
        "datePosted": date_posted,
    }
    return (
        "<html><head>"
        f'<script type="application/ld+json">{json.dumps(payload)}</script>'
        "</head><body>"
        f'<div id="jobDescriptionText">{description}</div>'
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# Pure decision logic
# ---------------------------------------------------------------------------


def test_build_search_url_has_recency_and_remote_filters():
    url = build_search_url("analista de datos", start=0)
    assert "fromage=14" in url
    assert "sc=0kf%3Aattr%28DSQF7%29%3B" in url
    assert "start=0" in url


def test_build_search_url_paginates_by_10():
    url = build_search_url("analista de datos", start=20)
    assert "start=20" in url


def test_build_job_view_url():
    assert build_job_view_url("abc123") == "https://mx.indeed.com/viewjob?jk=abc123"


@pytest.mark.parametrize("html", ["Security Check", "Verifica que eres humano"])
def test_is_captcha_page_true_for_specific_html_markers(html):
    assert is_captcha_page(html)


def test_is_captcha_page_false_for_a_normal_page():
    assert not is_captcha_page("Analista de Datos - MAVI - Indeed.com")


def test_is_captcha_page_checks_title_too():
    assert is_captcha_page("", title="Security Check | Indeed")


def test_is_captcha_page_bare_captcha_word_in_title_still_counts():
    # A short, curated string — much less likely than the full page body to
    # pick up an incidental mention (e.g. a defensive reCAPTCHA badge).
    assert is_captcha_page("", title="Please solve this captcha")


@pytest.mark.parametrize(
    "html",
    [
        "www.indeed.com needs to review the security of your connection before proceeding.",
        '<div id="cf-browser-verification">Checking your browser...</div>',
        '<script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>',
        "Necesita revisar la seguridad de tu conexión antes de continuar.",
    ],
)
def test_is_captcha_page_true_for_real_cloudflare_interstitial_copy(html):
    # Kevin confirmed (2026-08-16) Indeed's real challenge is Cloudflare's
    # own interstitial — this is its actual narrative copy/markup, only
    # ever present when it's replaced the whole page.
    assert is_captcha_page(html)


def test_is_captcha_page_true_for_cloudflare_title():
    assert is_captcha_page("", title="Just a moment...")


def test_is_captcha_page_bare_captcha_word_in_html_body_no_longer_false_alarms():
    # EATP-023 (Kevin, live, 2026-08-16): a bare "captcha" mention anywhere
    # in the full page HTML (e.g. a reCAPTCHA badge Indeed embeds on
    # ordinary, non-challenge pages) was popping false alarms. Only the
    # specific phrases count in the body now; the title still trusts a bare
    # "captcha" (see the test above) since it's a much lower-noise string.
    assert not is_captcha_page(
        "Normal listing page. This site is protected by reCAPTCHA."
    )


def test_is_search_no_results():
    assert is_search_no_results("no matching jobs found")
    assert not is_search_no_results("10 empleos")


def test_extract_job_id_from_card_prefers_data_jk():
    assert extract_job_id_from_card("abc123", "") == "abc123"


def test_extract_job_id_from_card_falls_back_to_title_id():
    html = '<a id="jobTitle-deadbeef1234">Analista</a>'
    assert extract_job_id_from_card(None, html) == "deadbeef1234"


def test_extract_job_id_from_card_none_when_nothing_found():
    assert extract_job_id_from_card(None, "<a>no id here</a>") is None


# ---------------------------------------------------------------------------
# JSON-LD parsing — synthetic HTML, real shape (no fixture HTML available)
# ---------------------------------------------------------------------------


def test_parse_job_ld_extracts_the_job_posting_block():
    html = _ld_html(
        title="Analista de Datos", company="Acme", date_posted="2026-08-01T00:00:00Z"
    )
    ld = parse_job_ld(html)
    assert ld is not None
    assert ld["title"] == "Analista de Datos"
    assert ld["hiringOrganization"]["name"] == "Acme"


def test_parse_job_ld_returns_none_without_a_job_posting_block():
    assert parse_job_ld("<html><body>captcha</body></html>") is None


def test_parse_detail_page_maps_title_company_description():
    html = _ld_html(
        title="Analista BI",
        company="Acme",
        description="Descripción larga del puesto.",
        date_posted="2026-08-01T00:00:00Z",
    )
    detail = parse_detail_page(html)
    assert detail == {
        "title": "Analista BI",
        "company": "Acme",
        "description": "Descripción larga del puesto.",
        "posted": "2026-08-01T00:00:00Z",
    }


def test_parse_detail_page_returns_none_when_no_ld_block():
    assert parse_detail_page("<html><body>captcha</body></html>") is None


def test_days_old_from_iso_parses_utc_timestamp():
    from datetime import UTC, datetime

    recent = datetime.now(UTC).isoformat()
    assert _days_old_from_iso(recent) == 0


def test_days_old_from_iso_returns_999_for_garbage():
    assert _days_old_from_iso("not-a-date") == 999
    assert _days_old_from_iso("") == 999


# ---------------------------------------------------------------------------
# _build_job — real fixture data, no network
# ---------------------------------------------------------------------------


def test_build_job_maps_real_fixture_into_new_job_shape():
    fixture = FIXTURES[0]
    job = _build_job(fixture["job_id"], _detail_from_fixture(fixture))

    assert job is not None
    assert job.source == "indeed"
    assert job.title == fixture["title"]
    assert job.company == fixture["company"]
    # Never hardcoded — the gate (EATP-009) decides remote_status, not the collector.
    assert job.remote_status == RemoteStatus.UNKNOWN


def test_build_job_rejects_absolute_excluded_company():
    fixture = dict(FIXTURES[0])
    detail = _detail_from_fixture(fixture)
    detail["company"] = "BairesDev"

    assert _build_job(fixture["job_id"], detail) is None


def test_build_job_flags_thin_description():
    fixture = dict(FIXTURES[0])
    detail = _detail_from_fixture(fixture)
    detail["description"] = "corta"

    job = _build_job(fixture["job_id"], detail)
    assert job.thin_description is True


def test_build_job_returns_none_without_a_title():
    assert (
        _build_job(
            "1", {"title": "", "company": "Acme", "description": "x", "posted": ""}
        )
        is None
    )


# ---------------------------------------------------------------------------
# collect() orchestration — scripted fake page, no real browser
# ---------------------------------------------------------------------------


class _FakeLink:
    def __init__(self, data_jk: str | None, html: str = ""):
        self._data_jk = data_jk
        self.html = html

    def attr(self, name: str) -> str | None:
        return self._data_jk if name == "data-jk" else None


class _FakeCard:
    def __init__(self, link: _FakeLink | None):
        self._link = link

    def ele(self, selector: str, timeout: float | None = None):
        return self._link


class _FakeWait:
    def doc_loaded(self) -> None:
        pass


class _FakeWindow:
    def __init__(self, calls: list[str] | None = None) -> None:
        self._calls = calls if calls is not None else []

    def max(self) -> None:
        self._calls.append("max")

    def mini(self) -> None:
        pass

    def normal(self) -> None:
        self._calls.append("normal")


class _FakeSet:
    def __init__(self) -> None:
        self.bring_to_front_calls: list[str] = []
        self.window = _FakeWindow(self.bring_to_front_calls)

    def activate(self) -> None:
        self.bring_to_front_calls.append("activate")


class _ScriptedPage:
    """Maps each requested URL to a queue of canned (html, cards, title)
    responses, popped in order per URL (so the same URL can captcha once and
    recover on retry). URL-keyed rather than call-order-keyed because 2
    detail tabs pull job ids off a shared queue concurrently — which tab
    reaches `.get()` first isn't deterministic, but which URL it asks for
    always is. Per-thread "current" state models each tab having its own
    independent view, same as real browser tabs.
    """

    def __init__(self, responses: dict[str, list[tuple[str, list[_FakeCard], str]]]):
        self._responses = {url: list(items) for url, items in responses.items()}
        self._lock = threading.Lock()
        self._current_by_thread: dict[int, tuple[str, str, list, str]] = {}
        self.wait = _FakeWait()
        self.set = _FakeSet()
        self.quit_called = False
        self.new_tab_calls = 0
        self.process_id = 999001  # mirrors real ChromiumPage.process_id (browser.forget_page)
        self.get_calls: list[str] = []
        # Set to N to model Kevin actually solving the challenge: after N
        # reads of the captcha page, Indeed swaps it for the real page *in
        # place*, with no navigation from us. That in-place swap is the
        # point — EATP-025's bug was the collector re-navigating on every
        # poll instead of waiting for it, which destroyed the captcha he was
        # halfway through solving.
        self.captcha_clears_after_html_reads: int | None = None
        # Per-thread (= per-tab) and reset on every `get`, so two tabs each
        # hitting their own captcha — and a second episode later in the same
        # run — are independent, exactly like real pages.
        self._captcha_reads_by_thread: dict[int, int] = {}

    def get(self, url: str) -> None:
        with self._lock:
            self.get_calls.append(url)
            queue = self._responses.get(url)
            html, cards, title = queue.pop(0) if queue else ("", [], "")
        self._current_by_thread[threading.get_ident()] = (url, html, cards, title)
        self._captcha_reads_by_thread[threading.get_ident()] = 0

    def _current(self):
        return self._current_by_thread.get(threading.get_ident())

    def _captcha_is_solved(self) -> bool:
        limit = self.captcha_clears_after_html_reads
        if limit is None:
            return False
        return self._captcha_reads_by_thread.get(threading.get_ident(), 0) > limit

    @property
    def url(self) -> str:
        current = self._current()
        return current[0] if current else ""

    @property
    def html(self) -> str:
        # Production reads html first, then title, for one `is_captcha_page`
        # check — so the counter advances here and `title` only reads the
        # result. Otherwise a single check would count as two.
        current = self._current()
        if current is None:
            return ""
        html, title = current[1], current[3]
        if self.captcha_clears_after_html_reads is not None and is_captcha_page(html, title):
            thread_id = threading.get_ident()
            self._captcha_reads_by_thread[thread_id] = (
                self._captcha_reads_by_thread.get(thread_id, 0) + 1
            )
            if self._captcha_is_solved():
                return "1 resultado"
        return html

    @property
    def title(self) -> str:
        current = self._current()
        if current is None:
            return ""
        if is_captcha_page(current[1], current[3]) and self._captcha_is_solved():
            return ""
        return current[3]

    def eles(self, selector: str) -> list[_FakeCard]:
        current = self._current()
        return current[2] if current else []

    def ele(self, selector: str, timeout: float | None = None):
        # Content is already fully "rendered" in these fixtures — the real
        # wait is what protects against a slow-loading page, not modeled here.
        return object()

    def new_tab(self):
        self.new_tab_calls += 1
        return self

    def quit(self) -> None:
        self.quit_called = True


def _card_for(fixture: dict) -> _FakeCard:
    return _FakeCard(_FakeLink(fixture["job_id"]))


def _responses_for(
    *entries: tuple[str, str, list[_FakeCard], str],
) -> dict[str, list[tuple[str, list[_FakeCard], str]]]:
    """Group scripted (url, html, cards, title) entries by url, preserving
    per-url order (a url requested twice — e.g. captcha then retry — gets
    its responses in the order given)."""
    grouped: dict[str, list[tuple[str, list[_FakeCard], str]]] = {}
    for url, html, cards, title in entries:
        grouped.setdefault(url, []).append((html, cards, title))
    return grouped


def _detail_response(fixture: dict) -> tuple[str, str, list[_FakeCard], str]:
    html = _ld_html(
        title=fixture["title"],
        company=fixture["company"],
        description=fixture["description"],
        date_posted="2026-08-01T00:00:00Z",
    )
    return (build_job_view_url(fixture["job_id"]), html, [], "")


@pytest.fixture(autouse=True)
def _fake_clock(monkeypatch):
    """`time.sleep` advances a fake clock instead of actually sleeping, and
    `time.monotonic` reads that same clock — so the captcha wait's real
    deadline logic runs at full fidelity (the right number of polls, in the
    right order) without a test ever taking wall-clock seconds. Also shrinks
    the wait/poll constants so a "persistent captcha" test needs only a
    couple of scripted responses, not real-sized ones (300s / 10s -> 30
    polls' worth of fixture data)."""
    clock = {"t": 0.0}

    def fake_sleep(seconds: float) -> None:
        clock["t"] += seconds

    monkeypatch.setattr("rove.collectors.indeed.time.sleep", fake_sleep)
    monkeypatch.setattr(
        "rove.collectors.indeed.time.monotonic", lambda: clock["t"]
    )
    monkeypatch.setattr(
        "rove.collectors.browser.human_pause", lambda *a, **k: None
    )
    # `indeed.py` and `browser.py` both do a plain `import time` — that's
    # the SAME module object, so patching `indeed.time.sleep` above already
    # covers `browser.py`'s calls (including `bring_to_front`'s repaint
    # nudge) too. A second, separate `browser.time.sleep` patch here would
    # silently *replace* the fake-clock-advancing one above instead of
    # adding to it (whichever `setattr` runs last wins on the shared
    # object) — froze the fake clock at 0 and broke the deadline math in
    # exactly the way that looked like a real regression.
    monkeypatch.setattr("rove.collectors.indeed._CAPTCHA_WAIT_SECONDS", 20)
    monkeypatch.setattr("rove.collectors.indeed._CAPTCHA_POLL_SECONDS", 10)


def test_collect_yields_real_fixture_jobs_across_search_and_detail(monkeypatch):
    # 2 fixtures + the default 2 detail workers: exercises the real parallel
    # path (2 tabs), not just the single-tab-clamped case.
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_response = (
        build_search_url("analista de datos", 0),
        "2 resultados",
        [_card_for(f) for f in fixtures],
        "",
    )
    page = _ScriptedPage(
        _responses_for(search_response, *[_detail_response(f) for f in fixtures])
    )

    collector = IndeedCollector(page_factory=lambda: page)
    jobs = list(collector.collect())

    assert {job.title for job in jobs} == {f["title"] for f in fixtures}
    assert page.new_tab_calls == 1  # 2 fixtures -> 2 workers -> 1 extra tab
    assert page.quit_called is True


def test_collect_stops_on_no_results_marker(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    page = _ScriptedPage(
        _responses_for(
            (build_search_url("analista de datos", 0), "no matching jobs found", [], "")
        )
    )

    collector = IndeedCollector(page_factory=lambda: page)
    jobs = list(collector.collect())

    assert jobs == []


def test_report_and_get_deadline_reports_exactly_once_under_true_concurrency():
    # Indeed's block is session-wide (module docstring) — multiple tabs can
    # genuinely discover the SAME still-active captcha within the same
    # instant. EATP-023 (Kevin, live report): before gating `bring_to_front`
    # on this exact signal, every tab that independently discovered it
    # raced to activate/maximize itself — exactly the chaos he saw (wrong
    # tab shown, a fullscreen-like flash). A `Barrier` forces genuine
    # concurrent access (unlike scripting fake responses, which just
    # serializes onto whichever thread the GIL happens to run first).
    coord = _CaptchaCoordination()
    worker_count = 5
    barrier = threading.Barrier(worker_count)
    results: list[bool] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait(timeout=2)
        _, is_new = coord.report_and_get_deadline("Indeed pide verificación humana")
        with results_lock:
            results.append(is_new)

    threads = [threading.Thread(target=worker) for _ in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert results.count(True) == 1
    assert results.count(False) == worker_count - 1


def test_collect_waits_for_captcha_resolution_then_recovers(monkeypatch):
    # A single fixture clamps detail_workers down to 1 tab — deterministic.
    fixtures = FIXTURES[:1]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_url = build_search_url("analista de datos", 0)
    captcha_response = (search_url, "Security Check", [], "Security Check")
    # The single re-load, once the challenge is actually gone.
    real_response = (search_url, "1 resultado", [_card_for(fixtures[0])], "")
    page = _ScriptedPage(
        _responses_for(captcha_response, real_response, _detail_response(fixtures[0]))
    )
    # Kevin "solves" it between the initial hit (which reads the page twice,
    # once either side of the debounce) and the first poll check.
    page.captcha_clears_after_html_reads = 2

    subscriber = events.bus.subscribe()
    try:
        collector = IndeedCollector(page_factory=lambda: page)
        jobs = list(collector.collect())

        assert [job.title for job in jobs] == [fixtures[0]["title"]]
        event = subscriber.get(timeout=1)
        assert event.status == "needs_intervention"
        assert event.phase == "collect:indeed"
        assert "resuélvela en la ventana del navegador" in event.message

        # EATP-020: Kevin's report — the banner stayed on screen forever
        # after he'd already solved it. Once resolved, a paired event must
        # arrive so the frontend can clear that specific notice immediately,
        # not wait for a later pipeline phase.
        resolved_event = subscriber.get(timeout=1)
        assert resolved_event.status == "intervention_resolved"
        assert resolved_event.phase == "collect:indeed"
    finally:
        events.bus.unsubscribe(subscriber)


def test_collect_gives_up_cleanly_after_persistent_captcha(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_url = build_search_url("analista de datos", 0)
    captcha_response = (search_url, "Security Check", [], "Security Check")
    # Every attempt — the initial hit plus every poll (2, at the fixture's
    # shrunk 20s/10s wait/poll) — keeps hitting a captcha, so it never clears.
    page = _ScriptedPage(_responses_for(*([captcha_response] * 3)))

    subscriber = events.bus.subscribe()
    try:
        collector = IndeedCollector(page_factory=lambda: page)
        jobs = list(collector.collect())

        assert jobs == []
        assert page.quit_called is True
        events_seen = []
        while True:
            try:
                events_seen.append(subscriber.get(timeout=1))
            except Empty:
                break
        assert len(events_seen) == 2
        assert all(e.status == "needs_intervention" for e in events_seen)
        assert "se omite Indeed" in events_seen[-1].message
    finally:
        events.bus.unsubscribe(subscriber)


def test_collect_never_navigates_while_kevin_is_solving_the_captcha(monkeypatch):
    """EATP-025 (Kevin, live 2026-08-18): same report as LinkedIn's login
    wall — the page kept reloading and never gave him a chance to finish.

    The captcha wait used to `tab.get(url)` on every poll. A captcha is only
    clearable by hand, so a wait that reloads the page mid-attempt can never
    succeed. Pins the requirement: no navigation at all between discovering
    the challenge and it clearing.
    """
    fixtures = FIXTURES[:1]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_url = build_search_url("analista de datos", 0)
    page = _ScriptedPage(
        _responses_for(
            (search_url, "Security Check", [], "Security Check"),
            (search_url, "1 resultado", [_card_for(fixtures[0])], ""),
            _detail_response(fixtures[0]),
        )
    )
    # He takes his time: still unsolved on the first poll.
    page.captcha_clears_after_html_reads = 3

    collector = IndeedCollector(page_factory=lambda: page)
    jobs = list(collector.collect())

    assert [job.title for job in jobs] == [fixtures[0]["title"]]
    # The search URL is fetched exactly twice: the initial hit that found
    # the challenge, and the single re-load once it cleared. Every poll in
    # between touched nothing.
    assert page.get_calls.count(search_url) == 2


def test_collect_notifies_separately_for_a_second_captcha_later_in_the_run(monkeypatch):
    # Kevin's report (2026-08-13): a captcha can clear, the run continues,
    # and a SECOND, unrelated captcha shows up minutes later — that second
    # one must get its own fresh wait + its own "resuélvela" notification,
    # not silently reuse the first captcha's already-spent deadline.
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos", "analista de negocios"])

    search_url_1 = build_search_url("analista de datos", 0)
    search_url_2 = build_search_url("analista de negocios", 0)
    page = _ScriptedPage(
        _responses_for(
            (search_url_1, "Security Check", [], "Security Check"),
            (search_url_1, "1 resultado", [_card_for(fixtures[0])], ""),
            (search_url_2, "Security Check", [], "Security Check"),
            (search_url_2, "1 resultado", [_card_for(fixtures[1])], ""),
            _detail_response(fixtures[0]),
            _detail_response(fixtures[1]),
        )
    )
    # Each episode is solved between its initial hit and its first poll.
    page.captcha_clears_after_html_reads = 2

    subscriber = events.bus.subscribe()
    try:
        collector = IndeedCollector(page_factory=lambda: page, detail_workers=1)
        jobs = list(collector.collect())

        assert {job.title for job in jobs} == {f["title"] for f in fixtures}

        prompts = []
        while True:
            try:
                event = subscriber.get(timeout=1)
            except Empty:
                break
            if "resuélvela en la ventana del navegador" in event.message:
                prompts.append(event)
        # One fresh notification per captcha episode — not one for the
        # whole run. Before the fix, only the first would ever fire.
        assert len(prompts) == 2
    finally:
        events.bus.unsubscribe(subscriber)


def test_collect_preserves_jobs_already_yielded_when_captcha_hits_during_details(
    monkeypatch,
):
    # Forced to 1 detail worker: deterministic ordering, since this test is
    # about progress preservation, not the parallel path (already covered
    # above).
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_response = (
        build_search_url("analista de datos", 0),
        "2 resultados",
        [_card_for(f) for f in fixtures],
        "",
    )
    captcha_url = build_job_view_url(fixtures[1]["job_id"])
    captcha_response = (captcha_url, "Security Check", [], "Security Check")
    page = _ScriptedPage(
        _responses_for(
            search_response,
            _detail_response(fixtures[0]),
            captcha_response,  # initial hit
            captcha_response,  # poll 1
            captcha_response,  # poll 2 — deadline passes, still captcha
        )
    )

    collector = IndeedCollector(page_factory=lambda: page, detail_workers=1)
    jobs = list(collector.collect())

    assert [job.title for job in jobs] == [fixtures[0]["title"]]
    assert page.new_tab_calls == 0
