"""Tests for the LinkedIn guest-API detail fetch.

Real fixture data (`tests/fixtures/linkedin_jobs.json`) wrapped in the guest
API's actual HTML shape and served through a mocked httpx transport — no
live network, no browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from career_radar.collectors.linkedin_api import fetch_job_detail, fetch_job_details

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "linkedin_jobs.json").read_text(encoding="utf-8")
)


def _detail_html(fixture: dict) -> str:
    return f"""
    <div>
      <h2 class="top-card-layout__title">{fixture["title"]}</h2>
      <a class="topcard__org-name-link">{fixture["company"]}</a>
      <span class="topcard__flavor--bullet">Remote</span>
      <span class="posted-time-ago__text">{fixture["posted"]}</span>
      <div class="show-more-less-html__markup">{fixture["description"]}</div>
    </div>
    """


def _make_transport(fixtures: list[dict]) -> httpx.MockTransport:
    by_id = {f["job_id"]: f for f in fixtures}

    def handler(request: httpx.Request) -> httpx.Response:
        job_id = str(request.url).rstrip("/").rsplit("/", 1)[-1]
        fixture = by_id.get(job_id)
        if fixture is None:
            return httpx.Response(404)
        return httpx.Response(200, text=_detail_html(fixture))

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("career_radar.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def test_fetch_job_detail_parses_real_fixture_fields():
    fixture = FIXTURES[0]
    client = httpx.Client(transport=_make_transport([fixture]))

    detail = fetch_job_detail(client, fixture["job_id"])

    assert detail is not None
    assert detail["title"] == fixture["title"]
    assert detail["company"] == fixture["company"]
    assert detail["posted"] == fixture["posted"]
    assert fixture["description"][:80] in detail["description"]


def test_fetch_job_detail_returns_none_on_persistent_failure():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))

    detail = fetch_job_detail(client, "999999")

    assert detail is None


def test_fetch_job_details_fetches_all_ids_concurrently():
    fixtures = FIXTURES[:5]
    client = httpx.Client(transport=_make_transport(fixtures))

    results = fetch_job_details([f["job_id"] for f in fixtures], client=client, max_workers=3)

    assert set(results) == {f["job_id"] for f in fixtures}
    for fixture in fixtures:
        assert results[fixture["job_id"]]["title"] == fixture["title"]


def test_fetch_job_details_skips_unresolvable_ids():
    fixtures = FIXTURES[:2]
    client = httpx.Client(transport=_make_transport(fixtures))

    results = fetch_job_details([*[f["job_id"] for f in fixtures], "does-not-exist"], client=client)

    assert set(results) == {f["job_id"] for f in fixtures}
