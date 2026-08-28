"""Tests for the collector framework: registry, per-source envelope, and the
shared HTTP layer's pacing/retry. No network — fully offline.
"""

from __future__ import annotations

import httpx
import pytest

from rove.collectors.base import (
    CollectorRegistry,
    CollectorStatus,
    run_collector,
)
from rove.collectors.http import RetryableHTTPError, build_client, get
from rove.models import Job


class FakeCollector:
    """A minimal `Collector` for exercising the registry/envelope without a
    real source."""

    name = "fake"

    def __init__(self, jobs: list[Job] | None = None, error: Exception | None = None):
        self._jobs = jobs or []
        self._error = error

    def collect(self):
        yield from self._jobs
        if self._error:
            raise self._error


def make_job(i: int) -> Job:
    return Job(
        source="fake",
        source_job_id=str(i),
        title=f"Analista de datos {i}",
        company="ACME",
        url=f"https://example.com/{i}",
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_enable_disable():
    registry = CollectorRegistry()
    registry.register("fake", lambda: FakeCollector([make_job(1)]))
    assert registry.is_enabled("fake")

    registry.disable("fake")
    assert not registry.is_enabled("fake")
    assert "fake" not in registry.enabled_names()

    registry.enable("fake")
    assert "fake" in registry.enabled_names()


def test_registry_can_register_disabled_by_default():
    registry = CollectorRegistry()
    registry.register("fake", lambda: FakeCollector(), enabled=False)
    assert not registry.is_enabled("fake")
    assert registry.enabled_names() == []
    assert registry.names() == ["fake"]


def test_registry_unknown_source_raises():
    registry = CollectorRegistry()
    with pytest.raises(KeyError):
        registry.enable("nope")
    with pytest.raises(KeyError):
        registry.is_enabled("nope")


# ---------------------------------------------------------------------------
# run_collector envelope
# ---------------------------------------------------------------------------


def test_run_collector_ok():
    jobs, result = run_collector(FakeCollector([make_job(1), make_job(2)]))
    assert len(jobs) == 2
    assert result.source == "fake"
    assert result.status == CollectorStatus.OK
    assert result.yielded == 2
    assert result.error is None


def test_run_collector_empty():
    jobs, result = run_collector(FakeCollector([]))
    assert jobs == []
    assert result.status == CollectorStatus.EMPTY


def test_run_collector_error_is_captured_not_raised():
    jobs, result = run_collector(FakeCollector([make_job(1)], error=RuntimeError("boom")))
    # a job yielded before the failure is still kept
    assert len(jobs) == 1
    assert result.status == CollectorStatus.ERROR
    assert "boom" in (result.error or "")


def test_run_collector_streams_via_on_job_without_buffering():
    seen: list[Job] = []
    jobs, result = run_collector(
        FakeCollector([make_job(1), make_job(2)]), on_job=seen.append
    )
    assert jobs == []  # not buffered when streamed
    assert len(seen) == 2
    assert result.yielded == 2


# ---------------------------------------------------------------------------
# Registry <-> run_collector integration
# ---------------------------------------------------------------------------


def test_registry_run_integrates_fake_collector():
    registry = CollectorRegistry()
    registry.register("fake", lambda: FakeCollector([make_job(1)]))
    jobs, result = registry.run("fake")
    assert len(jobs) == 1
    assert result.source == "fake"
    assert result.status == CollectorStatus.OK


def test_registry_run_enabled_skips_disabled():
    registry = CollectorRegistry()
    registry.register("a", lambda: FakeCollector([make_job(1)]))
    registry.register("b", lambda: FakeCollector([make_job(2)]), enabled=False)
    results = registry.run_enabled()
    assert set(results) == {"a"}


# ---------------------------------------------------------------------------
# HTTP layer: pacing + retry (mocked transport, no real network)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Retry backoff really sleeps (tenacity.nap.sleep); skip it in tests."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def test_get_retries_on_500_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = get(client, "https://example.com")
    assert response.status_code == 200
    assert calls["n"] == 3


def test_get_gives_up_after_max_attempts():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RetryableHTTPError):
        get(client, "https://example.com")


def test_get_does_not_retry_on_404():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        get(client, "https://example.com")
    assert calls["n"] == 1  # not a retryable status - no backoff wasted


def test_build_client_merges_default_headers():
    client = build_client(headers={"X-Test": "1"})
    assert client.headers["X-Test"] == "1"
    assert "User-Agent" in client.headers
