"""Tests for the LinkedIn collector.

Rewrite (EATP-022, 2026-08-15): back to real-browser listing (the classic
`/jobs/search/` UI came back after EATP-019's guest-HTTP workaround was
built around it being broken). Split the same way as
`test_collector_indeed.py`: pure decision logic (URL building, id
extraction, login-wall/no-results detection, job construction) is tested
directly with plain strings — no browser at all. `collect()`'s
orchestration, including the login-wait retry path, is tested against a
small scripted stand-in for DrissionPage's `ChromiumPage`. No live network,
no real browser. Detail-fetch (`linkedin_api.py`) is untouched by this
rewrite and stays covered by its own tests (accessed here only through an
injectable `detail_fetcher`, same as before).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from queue import Empty

import pytest

from career_radar import config, events
from career_radar.collectors.linkedin import (
    LinkedInCollector,
    _build_job,
    build_job_view_url,
    build_search_url,
    extract_job_ids,
    is_login_page,
    page_has_no_real_results,
)
from career_radar.models import RemoteStatus

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "linkedin_jobs.json").read_text()
)


def _detail_from_fixture(fixture: dict) -> dict[str, str]:
    return {
        "title": fixture["title"],
        "company": fixture["company"],
        "description": fixture["description"],
        "posted": fixture["posted"],
        "location": "",
    }


def _detail_fetcher_from_fixtures(fixtures: list[dict]):
    detail_map = {f["job_id"]: _detail_from_fixture(f) for f in fixtures}
    return lambda ids: {jid: detail_map[jid] for jid in ids if jid in detail_map}


# ---------------------------------------------------------------------------
# Pure decision logic — no network needed, fully unit-testable.
# ---------------------------------------------------------------------------


def test_build_search_url_has_remote_recency_and_fulltime_filters():
    url = build_search_url("analista de datos", start=0)
    assert "f_WT=2" in url
    assert "f_TPR=r86400" in url
    assert "f_JT=F" in url
    assert "start=0" in url
    assert "location=" in url
    assert "www.linkedin.com/jobs/search/" in url


def test_build_job_view_url():
    assert build_job_view_url("123") == "https://www.linkedin.com/jobs/view/123/"


def _card(job_id: str) -> str:
    return f'<li><div data-occludable-job-id="{job_id}"></div></li>'


def test_extract_job_ids_parses_ids_in_page_order():
    html = "<html><body>" + _card("111") + _card("222") + "</body></html>"
    assert extract_job_ids(html) == ["111", "222"]


def test_extract_job_ids_dedupes_within_the_page():
    html = "<html><body>" + _card("111") + _card("111") + "</body></html>"
    assert extract_job_ids(html) == ["111"]


def test_extract_job_ids_empty_for_no_markers():
    assert extract_job_ids("<html><body>no jobs here</body></html>") == []


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/login",
        "https://www.linkedin.com/checkpoint/lg/sign-in",
        "https://www.linkedin.com/authwall?trk=x",
    ],
)
def test_is_login_page_true_for_known_markers(url):
    assert is_login_page(url)


def test_is_login_page_false_for_a_normal_search_url():
    assert not is_login_page(build_search_url("analista de datos"))


def test_page_has_no_real_results():
    assert page_has_no_real_results("No se han encontrado empleos para esta búsqueda")
    assert not page_has_no_real_results("10 resultados")


# ---------------------------------------------------------------------------
# _build_job — real fixture data, no network
# ---------------------------------------------------------------------------


def test_build_job_maps_real_fixture_into_new_job_shape():
    fixture = FIXTURES[0]
    job = _build_job(fixture["job_id"], _detail_from_fixture(fixture))

    assert job is not None
    assert job.source == "linkedin"
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
    assert _build_job("1", {"title": "", "company": "Acme", "description": "x", "posted": ""}) is None


# ---------------------------------------------------------------------------
# collect() orchestration — scripted fake page, no real browser
# ---------------------------------------------------------------------------


class _FakeScroll:
    def down(self, amount: int) -> None:
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


class _FakeBrowserAttr:
    """`.browser.new_tab()` — every "tab" is the same shared scripted page
    (per-thread current-state models each tab having its own independent
    view), same simplification as `test_collector_indeed.py`'s `_ScriptedPage`."""

    def __init__(self, page: "_ScriptedPage") -> None:
        self._page = page

    def new_tab(self):
        self._page.new_tab_calls += 1
        return self._page


class _ScriptedPage:
    """Maps each requested URL to a queue of canned `(resulting_url, html)`
    responses, popped in order per URL (so the same URL can hit a login-wall
    once and recover on retry). `resulting_url` models a real redirect
    (e.g. to `/authwall`) — DrissionPage's `.url` reflects where the browser
    actually ended up, not what was requested. URL-keyed rather than
    call-order-keyed because multiple search tabs pull terms off a shared
    queue concurrently — which tab asks first isn't deterministic, but which
    URL it asks for always is."""

    def __init__(self, responses: dict[str, list[tuple[str, str]]]) -> None:
        self._responses = {url: list(items) for url, items in responses.items()}
        self._lock = threading.Lock()
        self._current_by_thread: dict[int, tuple[str, str]] = {}
        self.scroll = _FakeScroll()
        self.browser = _FakeBrowserAttr(self)
        self.set = _FakeSet()
        self.quit_called = False
        self.new_tab_calls = 0

    def get(self, url: str) -> None:
        with self._lock:
            queue = self._responses.get(url)
            resulting_url, html = queue.pop(0) if queue else (url, "")
        self._current_by_thread[threading.get_ident()] = (resulting_url, html)

    def _current(self) -> tuple[str, str] | None:
        return self._current_by_thread.get(threading.get_ident())

    @property
    def url(self) -> str:
        current = self._current()
        return current[0] if current else ""

    @property
    def html(self) -> str:
        current = self._current()
        return current[1] if current else ""

    def quit(self) -> None:
        self.quit_called = True


def _search_html(ids: list[str]) -> str:
    return "<html><body>" + "".join(_card(i) for i in ids) + "</body></html>"


def _ok_response(url: str, ids: list[str]) -> tuple[str, str, tuple[str, str]]:
    return (url, url, _search_html(ids))


def _login_response(url: str) -> tuple[str, str, tuple[str, str]]:
    return (url, "https://www.linkedin.com/authwall?trk=x", "")


def _responses_for(
    *entries: tuple[str, str, str],
) -> dict[str, list[tuple[str, str]]]:
    """Each entry is `(requested_url, resulting_url, html)`, grouped by
    `requested_url`, preserving per-url order."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for requested_url, resulting_url, html in entries:
        grouped.setdefault(requested_url, []).append((resulting_url, html))
    return grouped


@pytest.fixture(autouse=True)
def _fake_clock(monkeypatch):
    """Same shape as `test_collector_indeed.py`'s `_fake_clock` — a fake
    clock so the login-wait deadline logic runs at full fidelity without
    real wall-clock seconds, and shrunk wait/poll constants so a
    "persistent login-wall" test needs only a couple of scripted responses."""
    clock = {"t": 0.0}

    def fake_sleep(seconds: float) -> None:
        clock["t"] += seconds

    monkeypatch.setattr("career_radar.collectors.linkedin.time.sleep", fake_sleep)
    monkeypatch.setattr("career_radar.collectors.linkedin.time.monotonic", lambda: clock["t"])
    monkeypatch.setattr("career_radar.collectors.browser.human_pause", lambda *a, **k: None)
    monkeypatch.setattr("career_radar.collectors.linkedin._LOGIN_WAIT_SECONDS", 20)
    monkeypatch.setattr("career_radar.collectors.linkedin._LOGIN_POLL_SECONDS", 10)


def test_collect_yields_real_fixture_jobs_from_a_single_page(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    ids = [f["job_id"] for f in fixtures]

    url = build_search_url("analista de datos", 0)
    page = _ScriptedPage(_responses_for(_ok_response(url, ids)))
    collector = LinkedInCollector(
        page_factory=lambda: page, detail_fetcher=_detail_fetcher_from_fixtures(fixtures)
    )
    jobs = list(collector.collect())

    assert {job.title for job in jobs} == {f["title"] for f in fixtures}
    assert page.quit_called is True


def test_collect_paginates_until_a_short_page(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    full_page = [str(i) for i in range(25)]  # exactly _PAGE_SIZE -> keep paginating
    short_page = ["30", "31"]  # fewer than _PAGE_SIZE -> this is the last page
    # Registered but must never be fetched — proves the stop condition is
    # "page came back short", not just "the next page happened to be empty".
    unreachable_page = ["40", "41", "42"]

    url_p1 = build_search_url("analista de datos", 0)
    url_p2 = build_search_url("analista de datos", 25)
    url_p3 = build_search_url("analista de datos", 50)
    page = _ScriptedPage(
        _responses_for(
            _ok_response(url_p1, full_page),
            _ok_response(url_p2, short_page),
            _ok_response(url_p3, unreachable_page),
        )
    )
    seen_ids: list[str] = []
    collector = LinkedInCollector(
        page_factory=lambda: page, detail_fetcher=lambda ids: (seen_ids.extend(ids), {})[1]
    )
    list(collector.collect())

    assert seen_ids == full_page + short_page


def test_collect_stops_a_term_cleanly_on_no_results(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    url = build_search_url("analista de datos", 0)
    page = _ScriptedPage(
        _responses_for((url, url, "No se han encontrado empleos para esta búsqueda"))
    )
    collector = LinkedInCollector(page_factory=lambda: page, detail_fetcher=lambda ids: {})
    jobs = list(collector.collect())

    assert jobs == []


def test_collect_returns_nothing_when_search_has_no_cards(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    url = build_search_url("analista de datos", 0)
    page = _ScriptedPage(_responses_for(_ok_response(url, [])))
    collector = LinkedInCollector(page_factory=lambda: page, detail_fetcher=lambda ids: {})
    jobs = list(collector.collect())

    assert jobs == []


def test_collect_skips_a_job_whose_detail_never_came_back(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    ids = [f["job_id"] for f in fixtures]

    url = build_search_url("analista de datos", 0)
    page = _ScriptedPage(_responses_for(_ok_response(url, ids)))
    # Only the first fixture's detail resolves — the second is dropped, not crashed on.
    collector = LinkedInCollector(
        page_factory=lambda: page, detail_fetcher=_detail_fetcher_from_fixtures(fixtures[:1])
    )
    jobs = list(collector.collect())

    assert [job.title for job in jobs] == [fixtures[0]["title"]]


def test_collect_merges_multiple_terms_in_deterministic_order(monkeypatch):
    # Terms are fetched concurrently (multiple tabs) but must still merge in
    # config.SEARCH_TERMS order — regardless of which tab finishes first.
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos", "analista de negocios"])
    url_1 = build_search_url("analista de datos", 0)
    url_2 = build_search_url("analista de negocios", 0)
    page = _ScriptedPage(
        _responses_for(_ok_response(url_1, ["1", "2"]), _ok_response(url_2, ["3", "4"]))
    )
    seen_ids: list[str] = []
    collector = LinkedInCollector(
        page_factory=lambda: page, detail_fetcher=lambda ids: (seen_ids.extend(ids), {})[1]
    )
    list(collector.collect())

    assert seen_ids == ["1", "2", "3", "4"]


def test_collect_waits_for_login_then_recovers(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    fixtures = FIXTURES[:1]
    ids = [f["job_id"] for f in fixtures]
    url = build_search_url("analista de datos", 0)

    page = _ScriptedPage(
        _responses_for(
            _login_response(url),  # first hit: redirected to the authwall
            _ok_response(url, ids),  # Kevin "logs in" between the hit and the first poll
        )
    )

    subscriber = events.bus.subscribe()
    try:
        collector = LinkedInCollector(
            page_factory=lambda: page, detail_fetcher=_detail_fetcher_from_fixtures(fixtures)
        )
        jobs = list(collector.collect())

        assert [job.title for job in jobs] == [fixtures[0]["title"]]

        event = subscriber.get(timeout=1)
        assert event.status == "needs_intervention"
        assert event.phase == "collect:linkedin"
        assert "inicia sesión en la ventana del navegador" in event.message

        # EATP-020's fix, ported here too: a paired event once it's resolved.
        resolved_event = subscriber.get(timeout=1)
        assert resolved_event.status == "intervention_resolved"
        assert resolved_event.phase == "collect:linkedin"
    finally:
        events.bus.unsubscribe(subscriber)


def test_collect_gives_up_cleanly_after_a_persistent_login_wall(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    url = build_search_url("analista de datos", 0)
    # Every attempt — the initial hit plus every poll (2, at the fixture's
    # shrunk 20s/10s wait/poll) — keeps hitting the authwall, so it never clears.
    page = _ScriptedPage(_responses_for(*([_login_response(url)] * 3)))

    subscriber = events.bus.subscribe()
    try:
        collector = LinkedInCollector(page_factory=lambda: page, detail_fetcher=lambda ids: {})
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
        assert "se omite LinkedIn" in events_seen[-1].message
    finally:
        events.bus.unsubscribe(subscriber)
