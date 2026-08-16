"""Tests for the Indeed collector.

Split the same way as `test_collector_linkedin.py`: pure decision logic
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

from career_radar import config, events
from career_radar.collectors.indeed import (
    IndeedCollector,
    _build_job,
    _days_old_from_iso,
    build_job_view_url,
    build_search_url,
    extract_job_id_from_card,
    is_captcha_page,
    is_search_no_results,
    parse_detail_page,
    parse_job_ld,
)
from career_radar.models import RemoteStatus

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "indeed_jobs.json").read_text()
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
    def max(self) -> None:
        pass

    def mini(self) -> None:
        pass


class _FakeSet:
    def __init__(self) -> None:
        self.window = _FakeWindow()

    def activate(self) -> None:
        pass


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

    def get(self, url: str) -> None:
        with self._lock:
            queue = self._responses.get(url)
            html, cards, title = queue.pop(0) if queue else ("", [], "")
        self._current_by_thread[threading.get_ident()] = (url, html, cards, title)

    def _current(self):
        return self._current_by_thread.get(threading.get_ident())

    @property
    def url(self) -> str:
        current = self._current()
        return current[0] if current else ""

    @property
    def html(self) -> str:
        current = self._current()
        return current[1] if current else ""

    @property
    def title(self) -> str:
        current = self._current()
        return current[3] if current else ""

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

    monkeypatch.setattr("career_radar.collectors.indeed.time.sleep", fake_sleep)
    monkeypatch.setattr(
        "career_radar.collectors.indeed.time.monotonic", lambda: clock["t"]
    )
    monkeypatch.setattr(
        "career_radar.collectors.browser.human_pause", lambda *a, **k: None
    )
    monkeypatch.setattr("career_radar.collectors.indeed._CAPTCHA_WAIT_SECONDS", 20)
    monkeypatch.setattr("career_radar.collectors.indeed._CAPTCHA_POLL_SECONDS", 10)


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


def test_collect_waits_for_captcha_resolution_then_recovers(monkeypatch):
    # A single fixture clamps detail_workers down to 1 tab — deterministic.
    fixtures = FIXTURES[:1]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_url = build_search_url("analista de datos", 0)
    captcha_response = (search_url, "Security Check", [], "Security Check")
    # Kevin "solves" it between the initial hit and the first poll check.
    real_response = (search_url, "1 resultado", [_card_for(fixtures[0])], "")
    page = _ScriptedPage(
        _responses_for(captcha_response, real_response, _detail_response(fixtures[0]))
    )

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
