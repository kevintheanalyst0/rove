"""Tests for the LinkedIn collector.

Split in two halves: the pure decision logic (URL building, login/
recommendation/health detection, job construction) is tested directly with
plain strings and real fixture data — no browser at all. `collect()`'s
orchestration is tested against a small scripted stand-in for DrissionPage's
`ChromiumPage`, since the collector only ever touches a handful of its
methods (`get`, `wait.doc_loaded`, `url`, `html`, `ele`, `quit`). No live
network, no real browser, matches `tests/fixtures/linkedin_jobs.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_radar import config, events
from career_radar.collectors.linkedin import (
    LinkedInCollector,
    _build_job,
    build_job_view_url,
    build_search_url,
    is_login_page,
    is_page_healthy,
    is_recommendation_card,
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


# ---------------------------------------------------------------------------
# Pure decision logic
# ---------------------------------------------------------------------------


def test_build_search_url_has_remote_recency_and_fulltime_filters():
    url = build_search_url("analista de datos", page=1)
    assert "f_WT=2" in url
    assert "f_TPR=r86400" in url
    assert "f_JT=F" in url
    assert "start=0" in url


def test_build_search_url_paginates_by_25():
    url = build_search_url("analista de datos", page=3)
    assert "start=50" in url


def test_build_job_view_url():
    assert build_job_view_url("123") == "https://www.linkedin.com/jobs/view/123/"


@pytest.mark.parametrize("url", ["https://www.linkedin.com/checkpoint/x", "https://www.linkedin.com/authwall"])
def test_is_login_page_true_for_login_markers(url):
    assert is_login_page(url)


def test_is_login_page_false_for_a_normal_search_url():
    assert not is_login_page(build_search_url("analista de datos"))


@pytest.mark.parametrize(
    "text",
    [
        "Empleos que podrían interesarte",
        "Jobs you may be interested in",
        "Top job picks for you",
    ],
)
def test_is_recommendation_card_true_for_known_markers(text):
    assert is_recommendation_card(text)


def test_is_recommendation_card_false_for_a_real_job_card():
    assert not is_recommendation_card("Data Analyst at Acme · México (Remoto)")


def test_page_has_no_real_results():
    assert page_has_no_real_results("no matching jobs found for this search")
    assert not page_has_no_real_results("42 resultados")


def test_is_page_healthy():
    assert is_page_healthy("42 resultados")
    assert not is_page_healthy("http error 429 - too many requests")


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


class _FakeCard:
    def __init__(self, text: str, job_id: str | None = None):
        self.text = text
        self._job_id = job_id

    def attr(self, name: str) -> str | None:
        if name in ("data-occludable-job-id", "data-job-id"):
            return self._job_id
        return None


class _FakeResultsPanel:
    def __init__(self, cards: list[_FakeCard]):
        self._cards = cards

    def eles(self, selector: str) -> list[_FakeCard]:
        return self._cards


class _FakeWait:
    def doc_loaded(self) -> None:
        pass


class _ScriptedPage:
    """One scripted (url, html, panel) response per `.get()` call, in order."""

    def __init__(self, responses: list[tuple[str, str, _FakeResultsPanel | None]]):
        self._responses = list(responses)
        self._current: tuple[str, str, _FakeResultsPanel | None] | None = None
        self.wait = _FakeWait()
        self.quit_called = False

    def get(self, url: str) -> None:
        if self._responses:
            self._current = self._responses.pop(0)

    @property
    def url(self) -> str:
        return self._current[0] if self._current else ""

    @property
    def html(self) -> str:
        return self._current[1] if self._current else ""

    def ele(self, selector: str, timeout: float | None = None):
        return self._current[2] if self._current else None

    def quit(self) -> None:
        self.quit_called = True


def _detail_fetcher_from_fixtures(fixtures: list[dict]):
    detail_map = {f["job_id"]: _detail_from_fixture(f) for f in fixtures}
    return lambda ids: {jid: detail_map[jid] for jid in ids if jid in detail_map}


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("career_radar.collectors.linkedin.time.sleep", lambda seconds: None)
    monkeypatch.setattr("career_radar.collectors.browser.human_pause", lambda *a, **k: None)


def test_collect_yields_real_fixture_jobs_from_a_single_page(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    cards = [_FakeCard(f["title"], job_id=f["job_id"]) for f in fixtures]
    page = _ScriptedPage([("https://www.linkedin.com/jobs/search/", "42 resultados", _FakeResultsPanel(cards))])

    collector = LinkedInCollector(
        page_factory=lambda: page, detail_fetcher=_detail_fetcher_from_fixtures(fixtures)
    )
    jobs = list(collector.collect())

    assert {job.title for job in jobs} == {f["title"] for f in fixtures}
    assert page.quit_called is True


def test_collect_stops_before_a_recommendation_card(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    cards = [
        _FakeCard(fixtures[0]["title"], job_id=fixtures[0]["job_id"]),
        _FakeCard("Empleos que podrían interesarte"),
        _FakeCard(fixtures[1]["title"], job_id=fixtures[1]["job_id"]),
    ]
    page = _ScriptedPage([("https://www.linkedin.com/jobs/search/", "42 resultados", _FakeResultsPanel(cards))])

    collector = LinkedInCollector(
        page_factory=lambda: page, detail_fetcher=_detail_fetcher_from_fixtures(fixtures)
    )
    jobs = list(collector.collect())

    assert [job.title for job in jobs] == [fixtures[0]["title"]]


def test_collect_stops_and_publishes_an_event_on_an_unhealthy_page(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    page = _ScriptedPage([("https://www.linkedin.com/jobs/search/", "HTTP ERROR 429", None)])

    subscriber = events.bus.subscribe()
    try:
        collector = LinkedInCollector(page_factory=lambda: page, detail_fetcher=lambda ids: {})
        jobs = list(collector.collect())

        assert jobs == []
        event = subscriber.get(timeout=1)
        assert event.status == "needs_intervention"
        assert event.phase == "collect:linkedin"
    finally:
        events.bus.unsubscribe(subscriber)


def test_collect_gives_up_gracefully_when_login_never_resolves(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    monkeypatch.setattr("career_radar.collectors.linkedin._LOGIN_WAIT_SECONDS", 0)
    page = _ScriptedPage([("https://www.linkedin.com/checkpoint/challenge", "", None)])

    collector = LinkedInCollector(page_factory=lambda: page, detail_fetcher=lambda ids: {})
    jobs = list(collector.collect())

    assert jobs == []
    assert page.quit_called is True


def test_collect_calls_quit_even_when_the_first_page_has_no_results(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    page = _ScriptedPage(
        [("https://www.linkedin.com/jobs/search/", "no matching jobs found for this search", None)]
    )

    collector = LinkedInCollector(page_factory=lambda: page, detail_fetcher=lambda ids: {})
    jobs = list(collector.collect())

    assert jobs == []
    assert page.quit_called is True
