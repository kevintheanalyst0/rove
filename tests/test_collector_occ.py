"""Tests for the OCC collector.

Uses real fixture data (`tests/fixtures/occ_jobs.json`) wrapped in OCC's
actual wire format (search-page HTML with `/empleo/oferta/<id>` links, and
the `{"o": {...}}` detail JSON shape) and served through a mocked httpx
transport — no live network.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from career_radar import config
from career_radar.collectors.occ import OCCCollector
from career_radar.models import RemoteStatus

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "occ_jobs.json").read_text())


def _numeric_id(fixture: dict) -> str:
    return fixture["job_id"].removeprefix("OCC_")


def _search_html(ids: list[str]) -> str:
    links = "".join(f'<a href="/empleo/oferta/{i}-slug">x</a>' for i in ids)
    return f"<html><body>{links}</body></html>"


def _detail_json(fixture: dict) -> dict:
    return {
        "o": {
            "t": fixture["title"],
            "cn": fixture["company"],
            "ld": f"<p>{fixture['description']}</p>",
            "dlur": "hace 2 horas",
            "ur": f"/empleo/oferta/{_numeric_id(fixture)}-slug",
        }
    }


def _make_transport(fixtures: list[dict]) -> httpx.MockTransport:
    by_id = {_numeric_id(f): f for f in fixtures}
    ids = list(by_id)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "occ.com.mx/empleos/de-" in url:
            page = int(request.url.params.get("page", "1"))
            return httpx.Response(200, text=_search_html(ids if page == 1 else []))
        if "oferta.occ.com.mx/offer/" in url:
            job_id = url.split("/offer/")[1].split("/")[0]
            fixture = by_id.get(job_id)
            if fixture is None:
                return httpx.Response(404)
            return httpx.Response(200, json=_detail_json(fixture))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # gentle_pause()'s own sleep, and tenacity's retry backoff sleep.
    monkeypatch.setattr("career_radar.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def test_collect_parses_real_fixture_jobs_into_new_job_shape(monkeypatch):
    fixtures = FIXTURES[:3]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_make_transport(fixtures))
    jobs = list(OCCCollector(client=client).collect())

    assert len(jobs) == 3
    assert {job.title for job in jobs} == {f["title"] for f in fixtures}
    for job in jobs:
        assert job.source == "occ"
        # Never hardcoded — the gate (EATP-009) decides remote_status, not the collector.
        assert job.remote_status == RemoteStatus.UNKNOWN
        assert job.url.startswith("https://www.occ.com.mx/")


def test_collect_fetches_each_id_once_across_search_terms(monkeypatch):
    fixtures = FIXTURES[:2]
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos", "analista de negocios"])

    client = httpx.Client(transport=_make_transport(fixtures))
    jobs = list(OCCCollector(client=client).collect())

    # Same two ids surface under both terms; each is only fetched once.
    assert len(jobs) == 2


def test_absolute_excluded_company_is_filtered_out(monkeypatch):
    fixture = dict(FIXTURES[0])
    fixture["company"] = "BairesDev"
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_make_transport([fixture]))
    jobs = list(OCCCollector(client=client).collect())

    assert jobs == []


def test_thin_description_flag_flows_through_from_the_model(monkeypatch):
    fixture = dict(FIXTURES[0])
    fixture["description"] = "corta"
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_make_transport([fixture]))
    jobs = list(OCCCollector(client=client).collect())

    assert jobs[0].thin_description is True


def test_collect_skips_a_job_whose_detail_request_fails(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    def handler(request: httpx.Request) -> httpx.Response:
        if "empleos/de-" in str(request.url):
            return httpx.Response(200, text=_search_html(["99999999"]))
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(OCCCollector(client=client).collect())

    assert jobs == []
