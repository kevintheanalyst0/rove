"""Tests for the Computrabajo collector.

Uses real fixture data (`tests/fixtures/computrabajo_jobs.json`) wrapped in
Computrabajo's actual wire format (search-page cards inside
`article.box_offer`, the real end-of-results marker, and the `{"o": {"ld":
...}}` description-detail JSON) and served through a mocked httpx transport
— no live network.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

from career_radar import config
from career_radar.collectors.computrabajo import _END_MARKER, ComputrabajoCollector
from career_radar.models import RemoteStatus

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "computrabajo_jobs.json").read_text()
)
# "Docente Online" (EIDHI International University) is an education posting —
# used on its own to test the title-exclusion pre-filter, not in the
# "everything should pass through" fixtures.
PASSING_FIXTURES = [f for f in FIXTURES if "Docente" not in f["title"]]
EDUCATION_FIXTURE = next(f for f in FIXTURES if "Docente" in f["title"])


def _numeric_id(fixture: dict) -> str:
    return fixture["job_id"].removeprefix("CT_")


def _href(fixture: dict) -> str:
    return urlparse(fixture["url"]).path + "#lc=ListOffers-Score3-0"


def _card_html(fixture: dict) -> str:
    return f"""
    <article class="box_offer" data-id="{_numeric_id(fixture)}">
      <a class="js-o-link fc_base" href="{_href(fixture)}">{fixture["title"]}</a>
      <a class="fc_base t_ellipsis" href="/empresa">{fixture["company"]}</a>
      <p class="fs13 fc_aux mt15">Hace 2 horas</p>
    </article>
    """


def _search_html(fixtures: list[dict], *, with_end_marker: bool) -> str:
    cards = "".join(_card_html(f) for f in fixtures)
    tail = _END_MARKER if with_end_marker else ""
    return f"<html><body>{cards}{tail}</body></html>"


def _detail_json(fixture: dict) -> dict:
    return {"o": {"ld": fixture["description"]}}


def _make_transport(fixtures: list[dict]) -> httpx.MockTransport:
    by_id = {_numeric_id(f): f for f in fixtures}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "mx.computrabajo.com/trabajo-de-" in url:
            page = int(request.url.params.get("p", "1"))
            if page == 1:
                return httpx.Response(200, text=_search_html(fixtures, with_end_marker=True))
            return httpx.Response(200, text=_search_html([], with_end_marker=True))
        if "oferta.computrabajo.com/offer/" in url:
            job_id = url.split("/offer/")[1].split("/")[0]
            fixture = by_id.get(job_id)
            if fixture is None:
                return httpx.Response(404)
            return httpx.Response(200, json=_detail_json(fixture))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("career_radar.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def test_collect_parses_real_fixture_jobs_into_new_job_shape(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_make_transport(PASSING_FIXTURES))
    jobs = list(ComputrabajoCollector(client=client).collect())

    assert len(jobs) == len(PASSING_FIXTURES)
    assert {job.title for job in jobs} == {f["title"] for f in PASSING_FIXTURES}
    for job in jobs:
        assert job.source == "computrabajo"
        assert job.remote_status == RemoteStatus.UNKNOWN
        assert job.url.startswith("https://mx.computrabajo.com/")


def test_stops_at_the_real_end_of_results_marker(monkeypatch):
    """Cards appearing after the marker must never be scraped."""
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    real, ghost = PASSING_FIXTURES[0], PASSING_FIXTURES[1]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "mx.computrabajo.com/trabajo-de-" in url:
            html = _card_html(real) + _END_MARKER + _card_html(ghost)
            return httpx.Response(200, text=f"<html><body>{html}</body></html>")
        if "oferta.computrabajo.com/offer/" in url:
            job_id = url.split("/offer/")[1].split("/")[0]
            fixture = real if job_id == _numeric_id(real) else ghost
            return httpx.Response(200, json=_detail_json(fixture))
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(ComputrabajoCollector(client=client).collect())

    assert [job.title for job in jobs] == [real["title"]]


def test_excluded_title_skips_the_description_request_entirely(monkeypatch):
    """The education pre-filter must fire before any detail fetch happens."""
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    fetched_detail = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "mx.computrabajo.com/trabajo-de-" in url:
            return httpx.Response(
                200, text=_search_html([EDUCATION_FIXTURE], with_end_marker=True)
            )
        if "oferta.computrabajo.com/offer/" in url:
            fetched_detail["called"] = True
            return httpx.Response(200, json=_detail_json(EDUCATION_FIXTURE))
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(ComputrabajoCollector(client=client).collect())

    assert jobs == []
    assert fetched_detail["called"] is False


def test_thin_description_flag_flows_through_from_the_model(monkeypatch):
    fixture = dict(PASSING_FIXTURES[0])
    fixture["description"] = "corta"
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])

    client = httpx.Client(transport=_make_transport([fixture]))
    jobs = list(ComputrabajoCollector(client=client).collect())

    assert jobs[0].thin_description is True


def test_a_failed_description_fetch_still_yields_the_job_flagged_thin(monkeypatch):
    """Unlike OCC, the card already has title+company — losing the
    description fetch is a quality problem (P21), not a reason to drop the
    job entirely."""
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    fixture = PASSING_FIXTURES[0]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "mx.computrabajo.com/trabajo-de-" in url:
            return httpx.Response(200, text=_search_html([fixture], with_end_marker=True))
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(ComputrabajoCollector(client=client).collect())

    assert len(jobs) == 1
    assert jobs[0].title == fixture["title"]
    assert jobs[0].description == ""
    assert jobs[0].thin_description is True
