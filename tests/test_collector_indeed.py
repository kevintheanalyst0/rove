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
    *, title: str, company: str, description: str = "", date_published: str = ""
) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "hiringOrganization": {"@type": "Organization", "name": company},
        "datePublished": date_published,
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


@pytest.mark.parametrize(
    "html", ["Security Check", "Verifica que eres humano", "please solve this captcha"]
)
def test_is_captcha_page_true_for_known_markers(html):
    assert is_captcha_page(html)


def test_is_captcha_page_false_for_a_normal_page():
    assert not is_captcha_page("Analista de Datos - MAVI - Indeed.com")


def test_is_captcha_page_checks_title_too():
    assert is_captcha_page("", title="Security Check | Indeed")


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
        title="Analista de Datos", company="Acme", date_published="2026-08-01T00:00:00Z"
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
        date_published="2026-08-01T00:00:00Z",
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


class _ScriptedPage:
    """One scripted (url, html, cards, title) response per `.get()` call, in order."""

    def __init__(self, responses: list[tuple[str, str, list[_FakeCard], str]]):
        self._responses = list(responses)
        self._current: tuple[str, str, list[_FakeCard], str] | None = None
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

    @property
    def title(self) -> str:
        return self._current[3] if self._current else ""

    def eles(self, selector: str) -> list[_FakeCard]:
        return self._current[2] if self._current else []

    def quit(self) -> None:
        self.quit_called = True


def _card_for(fixture: dict) -> _FakeCard:
    return _FakeCard(_FakeLink(fixture["job_id"]))


def _detail_response(fixture: dict) -> tuple[str, str, list[_FakeCard], str]:
    html = _ld_html(
        title=fixture["title"],
        company=fixture["company"],
        description=fixture["description"],
        date_published="2026-08-01T00:00:00Z",
    )
    return (build_job_view_url(fixture["job_id"]), html, [], "")


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(
        "career_radar.collectors.indeed.time.sleep", lambda seconds: None
    )
    monkeypatch.setattr(
        "career_radar.collectors.browser.human_pause", lambda *a, **k: None
    )


def test_collect_yields_real_fixture_jobs_across_search_and_detail(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_response = (
        build_search_url("analista de datos", 0),
        "2 resultados",
        [_card_for(f) for f in fixtures],
        "",
    )
    responses = [search_response, *[_detail_response(f) for f in fixtures]]
    page = _ScriptedPage(responses)

    collector = IndeedCollector(page_factory=lambda: page)
    jobs = list(collector.collect())

    assert {job.title for job in jobs} == {f["title"] for f in fixtures}
    assert page.quit_called is True


def test_collect_stops_on_no_results_marker(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    page = _ScriptedPage(
        [(build_search_url("analista de datos", 0), "no matching jobs found", [], "")]
    )

    collector = IndeedCollector(page_factory=lambda: page)
    jobs = list(collector.collect())

    assert jobs == []


def test_collect_retries_once_on_captcha_then_recovers(monkeypatch):
    fixtures = FIXTURES[:1]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    captcha_response = (
        build_search_url("analista de datos", 0),
        "Security Check",
        [],
        "Security Check",
    )
    real_response = (
        build_search_url("analista de datos", 0),
        "1 resultado",
        [_card_for(fixtures[0])],
        "",
    )
    responses = [captcha_response, real_response, _detail_response(fixtures[0])]
    page = _ScriptedPage(responses)

    subscriber = events.bus.subscribe()
    try:
        collector = IndeedCollector(page_factory=lambda: page)
        jobs = list(collector.collect())

        assert [job.title for job in jobs] == [fixtures[0]["title"]]
        event = subscriber.get(timeout=1)
        assert event.status == "needs_intervention"
        assert event.phase == "collect:indeed"
    finally:
        events.bus.unsubscribe(subscriber)


def test_collect_gives_up_cleanly_after_persistent_captcha(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    captcha_response = (
        build_search_url("analista de datos", 0),
        "Security Check",
        [],
        "Security Check",
    )
    # Both the first attempt and the single retry hit a captcha.
    page = _ScriptedPage([captcha_response, captcha_response])

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


def test_collect_preserves_jobs_already_yielded_when_captcha_hits_during_details(
    monkeypatch,
):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    search_response = (
        build_search_url("analista de datos", 0),
        "2 resultados",
        [_card_for(f) for f in fixtures],
        "",
    )
    captcha_response = (
        build_job_view_url(fixtures[1]["job_id"]),
        "Security Check",
        [],
        "Security Check",
    )
    responses = [
        search_response,
        _detail_response(fixtures[0]),
        captcha_response,
        captcha_response,  # retry also captchas
    ]
    page = _ScriptedPage(responses)

    collector = IndeedCollector(page_factory=lambda: page)
    jobs = list(collector.collect())

    assert [job.title for job in jobs] == [fixtures[0]["title"]]
