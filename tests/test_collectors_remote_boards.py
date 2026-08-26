"""Tests for the Tier-1 remote-first board collectors (EATP-007): Remotive,
RemoteOK, We Work Remotely, Himalayas.

Uses real fixture data (`tests/fixtures/remote_boards_jobs.json`) wrapped in
each source's actual wire format (confirmed live against the real APIs/feed
while building these collectors) and served through a mocked httpx
transport — no live network calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from rove.collectors.base import Collector, CollectorRegistry, CollectorStatus
from rove.collectors.himalayas import HimalayasCollector
from rove.collectors.remoteok import RemoteOKCollector
from rove.collectors.remotive import RemotiveCollector
from rove.collectors.wwr import WWRCollector
from rove.models import RemoteStatus

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "remote_boards_jobs.json").read_text(encoding="utf-8")
)

_OFF_TOPIC = {
    "id": "9999",
    "title": "Senior Frontend Engineer",
    "company": "Pixel Foundry",
    "description": "Build delightful React interfaces for our flagship product alongside a small, senior team.",
    "location": "Worldwide",
}


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # gentle_pause()'s own sleep, and tenacity's retry backoff sleep.
    monkeypatch.setattr("rove.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


# ---------------------------------------------------------------------------
# Remotive
# ---------------------------------------------------------------------------


def _remotive_payload(fixtures: list[dict]) -> dict:
    return {
        "jobs": [
            {
                "id": int(f["id"]),
                "url": f"https://remotive.com/remote-jobs/data/{f['id']}",
                "title": f["title"],
                "company_name": f["company"],
                "description": f"<p>{f['description']}</p>",
                "publication_date": "2026-08-08T21:48:06",
                "candidate_required_location": f["location"],
            }
            for f in fixtures
        ]
    }


def _remotive_transport(fixtures: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "remotive.com/api/remote-jobs" in str(request.url)
        assert request.url.params.get("search")
        return httpx.Response(200, json=_remotive_payload(fixtures))

    return httpx.MockTransport(handler)


def test_remotive_parses_real_fixture_jobs_into_new_job_shape():
    client = httpx.Client(transport=_remotive_transport(FIXTURES))
    jobs = list(RemotiveCollector(client=client).collect())

    assert len(jobs) == len(FIXTURES)
    assert {job.title for job in jobs} == {f["title"] for f in FIXTURES}
    for job in jobs:
        assert job.source == "remotive"
        # Never hardcoded — the gate (EATP-009) decides remote_status, not the collector.
        assert job.remote_status == RemoteStatus.UNKNOWN
        assert job.url.startswith("https://remotive.com/")


def test_remotive_dedups_the_same_job_across_search_terms():
    # Every search term returns the same fixture set (mocked), like a job
    # legitimately matching more than one of our terms.
    client = httpx.Client(transport=_remotive_transport(FIXTURES[:1]))
    jobs = list(RemotiveCollector(client=client).collect())

    assert len(jobs) == 1


# ---------------------------------------------------------------------------
# RemoteOK
# ---------------------------------------------------------------------------


def _remoteok_payload(fixtures: list[dict]) -> list[dict]:
    legal_notice = {"legal": "API Terms of Service..."}
    jobs = [
        {
            "id": f["id"],
            "slug": f["title"].lower().replace(" ", "-"),
            "company": f["company"],
            "position": f["title"],
            "tags": ["remote", "data"],
            "description": f"<p>{f['description']}</p>",
            "location": f["location"],
            "date": "2026-08-10T12:00:00+00:00",
            "url": f"https://remoteok.com/remote-jobs/{f['id']}",
        }
        for f in fixtures
    ]
    return [legal_notice, *jobs]


def test_remoteok_skips_the_legal_notice_and_parses_real_fixture_jobs():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_remoteok_payload(FIXTURES))
        )
    )
    jobs = list(RemoteOKCollector(client=client).collect())

    assert len(jobs) == len(FIXTURES)
    assert {job.title for job in jobs} == {f["title"] for f in FIXTURES}
    for job in jobs:
        assert job.source == "remoteok"
        assert job.remote_status == RemoteStatus.UNKNOWN


def test_remoteok_filters_out_postings_that_do_not_match_any_search_term():
    payload = _remoteok_payload(FIXTURES[:1])
    payload.append(
        {
            "id": _OFF_TOPIC["id"],
            "slug": "frontend-engineer",
            "company": _OFF_TOPIC["company"],
            "position": _OFF_TOPIC["title"],
            "tags": ["react", "frontend"],
            "description": f"<p>{_OFF_TOPIC['description']}</p>",
            "location": _OFF_TOPIC["location"],
            "date": "2026-08-10T12:00:00+00:00",
            "url": "https://remoteok.com/remote-jobs/9999",
        }
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    jobs = list(RemoteOKCollector(client=client).collect())

    assert len(jobs) == 1
    assert jobs[0].title == FIXTURES[0]["title"]


# ---------------------------------------------------------------------------
# We Work Remotely
# ---------------------------------------------------------------------------


def _wwr_rss(fixtures: list[dict]) -> str:
    items = "".join(
        f"""
        <item>
          <title>{f['company']}: {f['title']}</title>
          <region>{f['location']}</region>
          <category>Management and Finance</category>
          <link>https://weworkremotely.com/remote-jobs/{f['id']}-slug</link>
          <guid>https://weworkremotely.com/remote-jobs/{f['id']}-slug</guid>
          <pubDate>Thu, 06 Aug 2026 15:25:55 +0000</pubDate>
          <description>&lt;p&gt;{f['description']}&lt;/p&gt;</description>
        </item>
        """
        for f in fixtures
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>WWR</title>{items}</channel></rss>"""


def test_wwr_splits_company_and_title_from_the_combined_rss_title():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=_wwr_rss(FIXTURES))
        )
    )
    jobs = list(WWRCollector(client=client).collect())

    assert len(jobs) == len(FIXTURES)
    by_title = {job.title: job for job in jobs}
    for f in FIXTURES:
        job = by_title[f["title"]]
        assert job.company == f["company"]
        assert job.source == "wwr"
        assert job.remote_status == RemoteStatus.UNKNOWN
        assert job.url.startswith("https://weworkremotely.com/")


def test_wwr_filters_out_items_that_do_not_match_any_search_term():
    rss = _wwr_rss([FIXTURES[0], _OFF_TOPIC])
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=rss))
    )
    jobs = list(WWRCollector(client=client).collect())

    assert len(jobs) == 1
    assert jobs[0].title == FIXTURES[0]["title"]


# ---------------------------------------------------------------------------
# Himalayas
# ---------------------------------------------------------------------------


def _himalayas_payload(fixtures: list[dict]) -> dict:
    return {
        "jobs": [
            {
                "title": f["title"],
                "companyName": f["company"],
                "description": f"<p>{f['description']}</p>",
                "pubDate": 1786568427,
                "applicationLink": f"https://himalayas.app/companies/acme/jobs/{f['id']}",
                "guid": f"https://himalayas.app/companies/acme/jobs/{f['id']}",
                "locationRestrictions": [f["location"]],
            }
            for f in fixtures
        ]
    }


def test_himalayas_parses_real_fixture_jobs_and_stops_pagination_on_an_empty_page():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        calls.append(offset)
        if offset == 0:
            return httpx.Response(200, json=_himalayas_payload(FIXTURES))
        return httpx.Response(200, json={"jobs": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(HimalayasCollector(client=client).collect())

    assert len(jobs) == len(FIXTURES)
    assert {job.title for job in jobs} == {f["title"] for f in FIXTURES}
    for job in jobs:
        assert job.source == "himalayas"
        assert job.remote_status == RemoteStatus.UNKNOWN
    # Stops the moment a page comes back empty — never loops forever.
    assert calls == [0, 100]


def test_himalayas_filters_out_postings_that_do_not_match_any_search_term():
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        if offset == 0:
            return httpx.Response(
                200, json=_himalayas_payload([FIXTURES[0], _OFF_TOPIC])
            )
        return httpx.Response(200, json={"jobs": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(HimalayasCollector(client=client).collect())

    assert len(jobs) == 1
    assert jobs[0].title == FIXTURES[0]["title"]


# ---------------------------------------------------------------------------
# Registration — all four satisfy the shared Collector protocol/registry
# ---------------------------------------------------------------------------


def _empty_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"jobs": []})))


def test_all_four_satisfy_the_collector_protocol():
    assert isinstance(RemotiveCollector(client=_empty_client()), Collector)
    assert isinstance(RemoteOKCollector(client=_empty_client()), Collector)
    assert isinstance(WWRCollector(client=_empty_client()), Collector)
    assert isinstance(HimalayasCollector(client=_empty_client()), Collector)


def test_all_four_register_and_run_through_the_registry():
    registry = CollectorRegistry()
    registry.register("remotive", lambda: RemotiveCollector(client=_empty_client()))
    registry.register("remoteok", lambda: RemoteOKCollector(client=_empty_client()))
    registry.register("wwr", lambda: WWRCollector(client=_empty_client()))
    registry.register("himalayas", lambda: HimalayasCollector(client=_empty_client()))

    assert set(registry.enabled_names()) == {"remotive", "remoteok", "wwr", "himalayas"}

    results = registry.run_enabled()

    assert set(results) == {"remotive", "remoteok", "wwr", "himalayas"}
    for source, (jobs, result) in results.items():
        assert jobs == []
        assert result.source == source
        assert result.status == CollectorStatus.EMPTY
