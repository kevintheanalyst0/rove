"""Tests for the ATS board collectors (EATP-008): Greenhouse, Lever.

Get on Board and Torre are NOT covered here — neither shipped this session
(see the EATP-008 checklist session notes): Get on Board has no discoverable
public API, and Torre's search endpoint ignores every query/pagination
param it was sent (confirmed live), always returning the same static
snapshot — not usable as a real source.

Uses real fixture data (`tests/fixtures/ats_jobs.json`) wrapped in each
source's actual wire format (confirmed live against the real APIs while
building these collectors) and served through a mocked httpx transport — no
live network calls.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import httpx
import pytest

from career_radar import cancellation, config
from career_radar.collectors.base import Collector, CollectorRegistry, CollectorStatus
from career_radar.collectors.greenhouse import GreenhouseCollector
from career_radar.collectors.lever import LeverCollector
from career_radar.models import RemoteStatus

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "ats_jobs.json").read_text(encoding="utf-8"))

_OFF_TOPIC = {
    "id": "9999",
    "title": "Senior Frontend Engineer",
    "company": "Pixel Foundry",
    "description": "Build delightful React interfaces for our flagship product alongside a small, senior team.",
    "location": "Remote",
}


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # gentle_pause()'s own sleep, and tenacity's retry backoff sleep.
    monkeypatch.setattr("career_radar.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------


def _greenhouse_payload(fixtures: list[dict]) -> dict:
    return {
        "jobs": [
            {
                "id": int(f["id"]),
                "title": f["title"],
                "company_name": f["company"],
                # Real wire format: HTML-entity-escaped HTML — double-encoded.
                "content": html.escape(f"<p>{f['description']}</p>"),
                "updated_at": "2026-08-10T16:52:46-04:00",
                "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{f['id']}",
                "location": {"name": f["location"]},
            }
            for f in fixtures
        ]
    }


def _greenhouse_transport(fixtures_by_company: dict[str, list[dict]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        company = str(request.url).split("/boards/")[1].split("/jobs")[0]
        fixtures = fixtures_by_company.get(company, [])
        return httpx.Response(200, json=_greenhouse_payload(fixtures))

    return httpx.MockTransport(handler)


def test_greenhouse_parses_real_fixture_jobs_and_unescapes_double_encoded_content(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": ["gitlab"], "lever": []})
    client = httpx.Client(transport=_greenhouse_transport({"gitlab": FIXTURES}))

    jobs = list(GreenhouseCollector(client=client).collect())

    assert len(jobs) == len(FIXTURES)
    by_title = {job.title: job for job in jobs}
    for f in FIXTURES:
        job = by_title[f["title"]]
        assert job.company == f["company"]
        assert job.source == "greenhouse"
        # Never hardcoded — the gate (EATP-009) decides remote_status, not the collector.
        assert job.remote_status == RemoteStatus.UNKNOWN
        assert job.url.startswith("https://job-boards.greenhouse.io/")
        # The double-escaped content was correctly unescaped and tag-stripped.
        assert "<p>" not in job.description
        assert "&lt;" not in job.description
        assert f["description"] in job.description


def test_greenhouse_iterates_every_curated_company(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": ["gitlab", "stripe"], "lever": []})
    client = httpx.Client(
        transport=_greenhouse_transport({"gitlab": FIXTURES[:1], "stripe": FIXTURES[1:2]})
    )

    jobs = list(GreenhouseCollector(client=client).collect())

    assert {job.title for job in jobs} == {FIXTURES[0]["title"], FIXTURES[1]["title"]}


def test_greenhouse_stops_at_the_next_company_once_cancellation_is_requested(monkeypatch):
    # EATP-024: pipeline.py only checks cancellation *between* whole
    # sources — a curated company list needs its own check so Pausar/
    # Cancelar doesn't have to wait out this entire source first.
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": ["gitlab", "stripe"], "lever": []})
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        company = str(request.url).split("/boards/")[1].split("/jobs")[0]
        fetched.append(company)
        if company == "gitlab":
            cancellation.request()
        return httpx.Response(200, json=_greenhouse_payload(FIXTURES[:1]))

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(cancellation.RunCancelled):
        list(GreenhouseCollector(client=client).collect())

    assert fetched == ["gitlab"]  # stripe never fetched


def test_greenhouse_filters_out_postings_that_do_not_match_any_search_term(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": ["gitlab"], "lever": []})
    client = httpx.Client(
        transport=_greenhouse_transport({"gitlab": [FIXTURES[0], _OFF_TOPIC]})
    )

    jobs = list(GreenhouseCollector(client=client).collect())

    assert len(jobs) == 1
    assert jobs[0].title == FIXTURES[0]["title"]


def test_greenhouse_absolute_excluded_company_is_filtered_out(monkeypatch):
    fixture = dict(FIXTURES[0])
    fixture["company"] = "BairesDev"
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": ["bairesdev"], "lever": []})
    client = httpx.Client(transport=_greenhouse_transport({"bairesdev": [fixture]}))

    jobs = list(GreenhouseCollector(client=client).collect())

    assert jobs == []


# ---------------------------------------------------------------------------
# Lever
# ---------------------------------------------------------------------------


def _lever_payload(fixtures: list[dict]) -> list[dict]:
    return [
        {
            "id": f["id"],
            "text": f["title"],
            "categories": {"location": f["location"]},
            "createdAt": 1786568427000,
            "hostedUrl": f"https://jobs.lever.co/acme/{f['id']}",
            "descriptionPlain": f["description"],
        }
        for f in fixtures
    ]


def _lever_transport(fixtures_by_company: dict[str, list[dict]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        company = str(request.url).split("/postings/")[1].split("?")[0]
        fixtures = fixtures_by_company.get(company, [])
        return httpx.Response(200, json=_lever_payload(fixtures))

    return httpx.MockTransport(handler)


def test_lever_parses_real_fixture_jobs_into_new_job_shape(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": [], "lever": ["palantir"]})
    client = httpx.Client(transport=_lever_transport({"palantir": FIXTURES}))

    jobs = list(LeverCollector(client=client).collect())

    assert len(jobs) == len(FIXTURES)
    assert {job.title for job in jobs} == {f["title"] for f in FIXTURES}
    for job in jobs:
        assert job.source == "lever"
        assert job.company == "Palantir"
        assert job.remote_status == RemoteStatus.UNKNOWN
        assert job.url.startswith("https://jobs.lever.co/")


def test_lever_stops_at_the_next_company_once_cancellation_is_requested(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": [], "lever": ["palantir", "figma"]})
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        company = str(request.url).split("/postings/")[1].split("?")[0]
        fetched.append(company)
        if company == "palantir":
            cancellation.request()
        return httpx.Response(200, json=_lever_payload(FIXTURES[:1]))

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(cancellation.RunCancelled):
        list(LeverCollector(client=client).collect())

    assert fetched == ["palantir"]


def test_lever_filters_out_postings_that_do_not_match_any_search_term(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": [], "lever": ["palantir"]})
    client = httpx.Client(
        transport=_lever_transport({"palantir": [FIXTURES[0], _OFF_TOPIC]})
    )

    jobs = list(LeverCollector(client=client).collect())

    assert len(jobs) == 1
    assert jobs[0].title == FIXTURES[0]["title"]


def test_lever_skips_a_company_whose_board_request_fails(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": [], "lever": ["ghost-co"]})
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(404))
    )

    jobs = list(LeverCollector(client=client).collect())

    assert jobs == []


# ---------------------------------------------------------------------------
# Registration — both satisfy the shared Collector protocol/registry
# ---------------------------------------------------------------------------


def _empty_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"jobs": []})))


def test_both_satisfy_the_collector_protocol():
    assert isinstance(GreenhouseCollector(client=_empty_client()), Collector)
    assert isinstance(LeverCollector(client=_empty_client()), Collector)


def test_both_register_and_run_through_the_registry(monkeypatch):
    monkeypatch.setattr(config, "ATS_COMPANIES", {"greenhouse": ["gitlab"], "lever": ["palantir"]})

    registry = CollectorRegistry()
    registry.register("greenhouse", lambda: GreenhouseCollector(client=_empty_client()))
    registry.register("lever", lambda: LeverCollector(client=_empty_client()))

    assert set(registry.enabled_names()) == {"greenhouse", "lever"}

    results = registry.run_enabled()

    assert set(results) == {"greenhouse", "lever"}
    for source, (jobs, result) in results.items():
        assert jobs == []
        assert result.source == source
        assert result.status == CollectorStatus.EMPTY
