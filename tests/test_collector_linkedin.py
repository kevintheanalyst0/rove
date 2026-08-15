"""Tests for the LinkedIn collector.

Rewrite (EATP-019, 2026-08-13): the collector is now HTTP-only (the guest
search endpoint replaced the browser-driven listing phase — see
`collectors/linkedin.py`'s module docstring for why). Search responses are
served through a mocked httpx transport, same pattern as
`test_collector_computrabajo.py`; `detail_fetcher` stays a plain injectable
callable, unchanged from before, since `linkedin_api.py` (job details) was
never touched by this rewrite.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from career_radar import config
from career_radar.collectors.linkedin import (
    LinkedInCollector,
    _build_job,
    build_job_view_url,
    build_search_url,
    extract_job_ids,
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
# Pure decision logic
# ---------------------------------------------------------------------------


def test_build_search_url_has_remote_recency_and_fulltime_filters():
    url = build_search_url("analista de datos", start=0)
    assert "f_WT=2" in url
    assert "f_TPR=r86400" in url
    assert "f_JT=F" in url
    assert "start=0" in url
    assert "jobs-guest/jobs/api/seeMoreJobPostings/search" in url


def test_build_search_url_uses_geo_id_not_free_text_location():
    # EATP-020: free-text `location=México` was live-verified to be silently
    # ignored for remote (f_WT=2) results (returned Miami/Texas/DC postings);
    # `geoId=103323778` is the resolved id that actually restricts to Mexico.
    url = build_search_url("analista de datos", start=0)
    assert "geoId=103323778" in url
    assert "location=" not in url


def test_build_job_view_url():
    assert build_job_view_url("123") == "https://www.linkedin.com/jobs/view/123/"


def _card(job_id: str) -> str:
    return f'<li><div data-entity-urn="urn:li:jobPosting:{job_id}"></div></li>'


def test_extract_job_ids_parses_ids_in_page_order():
    html = "<html><body>" + _card("111") + _card("222") + "</body></html>"
    assert extract_job_ids(html) == ["111", "222"]


def test_extract_job_ids_dedupes_within_the_page():
    html = "<html><body>" + _card("111") + _card("111") + "</body></html>"
    assert extract_job_ids(html) == ["111"]


def test_extract_job_ids_empty_for_no_markers():
    assert extract_job_ids("<html><body>no jobs here</body></html>") == []


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
# collect() orchestration — mocked httpx transport for search, injected fake
# detail_fetcher (no live network at all).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("career_radar.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def _search_transport(pages: dict[int, list[str]]) -> httpx.MockTransport:
    """`pages` maps `start` -> list of job ids to render on that page."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "jobs-guest/jobs/api/seeMoreJobPostings/search" in str(request.url)
        start = int(request.url.params.get("start", "0"))
        ids = pages.get(start, [])
        html = "<html><body>" + "".join(_card(jid) for jid in ids) + "</body></html>"
        return httpx.Response(200, text=html)

    return httpx.MockTransport(handler)


def test_collect_yields_real_fixture_jobs_from_a_single_page(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_search_transport({0: [f["job_id"] for f in fixtures]}))
    collector = LinkedInCollector(client=client, detail_fetcher=_detail_fetcher_from_fixtures(fixtures))
    jobs = list(collector.collect())

    assert {job.title for job in jobs} == {f["title"] for f in fixtures}


def test_collect_paginates_until_a_short_page(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    full_page = [str(i) for i in range(10)]  # exactly _PAGE_SIZE -> keep paginating
    short_page = ["10", "11"]  # fewer than _PAGE_SIZE -> this is the last page
    # Registered but must never be fetched — proves the stop condition is
    # "page came back short", not just "the next page happened to be empty".
    unreachable_page = ["20", "21", "22"]

    client = httpx.Client(
        transport=_search_transport({0: full_page, 10: short_page, 20: unreachable_page})
    )
    seen_ids = []
    collector = LinkedInCollector(
        client=client, detail_fetcher=lambda ids: (seen_ids.extend(ids), {})[1]
    )
    list(collector.collect())

    assert seen_ids == full_page + short_page


def test_collect_stops_a_term_cleanly_on_a_request_error(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = LinkedInCollector(client=client, detail_fetcher=lambda ids: {})
    jobs = list(collector.collect())

    assert jobs == []


def test_collect_returns_nothing_when_search_has_no_cards(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_search_transport({0: []}))
    collector = LinkedInCollector(client=client, detail_fetcher=lambda ids: {})
    jobs = list(collector.collect())

    assert jobs == []


def test_collect_merges_multiple_terms_in_deterministic_order(monkeypatch):
    # Terms are fetched concurrently (EATP-020) but must still merge in
    # config.SEARCH_TERMS order — regardless of which thread finishes first.
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos", "analista de negocios"])
    ids_by_term = {"analista de datos": ["1", "2"], "analista de negocios": ["3", "4"]}

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import unquote

        term = unquote(request.url.params.get("keywords"))
        ids = ids_by_term[term]
        html = "<html><body>" + "".join(_card(jid) for jid in ids) + "</body></html>"
        return httpx.Response(200, text=html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    seen_ids: list[str] = []
    collector = LinkedInCollector(
        client=client, detail_fetcher=lambda ids: (seen_ids.extend(ids), {})[1]
    )
    list(collector.collect())

    assert seen_ids == ["1", "2", "3", "4"]


def test_collect_skips_a_job_whose_detail_never_came_back(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_search_transport({0: [f["job_id"] for f in fixtures]}))
    # Only the first fixture's detail resolves — the second is dropped, not crashed on.
    collector = LinkedInCollector(
        client=client, detail_fetcher=_detail_fetcher_from_fixtures(fixtures[:1])
    )
    jobs = list(collector.collect())

    assert [job.title for job in jobs] == [fixtures[0]["title"]]
