"""Tests for the collector framework: registry, per-source envelope, the
shared HTTP layer's pacing/retry, and the browser base's path resolution +
event-based manual intervention. No network, no real browser launch — fully
offline (a real `ChromiumPage` is never instantiated here; that's a live
browser process, out of scope for a unit test).
"""

from __future__ import annotations

import httpx
import pytest

from career_radar.collectors import browser as browser_mod
from career_radar.collectors.base import (
    CollectorRegistry,
    CollectorStatus,
    run_collector,
)
from career_radar.collectors.http import RetryableHTTPError, build_client, get
from career_radar.events import EventBus
from career_radar.models import Job


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


# ---------------------------------------------------------------------------
# Browser base: path resolution + event-based manual intervention
# ---------------------------------------------------------------------------


def test_resolve_chrome_path_prefers_config_override(monkeypatch):
    monkeypatch.setattr(browser_mod.config, "CHROME_BROWSER_PATH", "/custom/chrome")
    assert browser_mod.resolve_chrome_path() == "/custom/chrome"


def test_resolve_chrome_path_falls_back_to_playwright_chromium(monkeypatch):
    monkeypatch.setattr(browser_mod.config, "CHROME_BROWSER_PATH", None)
    monkeypatch.setattr(browser_mod, "_find_playwright_chromium", lambda: "/fake/chrome-linux64/chrome")
    assert browser_mod.resolve_chrome_path() == "/fake/chrome-linux64/chrome"


def test_resolve_chrome_path_none_when_nothing_found(monkeypatch):
    monkeypatch.setattr(browser_mod.config, "CHROME_BROWSER_PATH", None)
    monkeypatch.setattr(browser_mod, "_find_playwright_chromium", lambda: None)
    assert browser_mod.resolve_chrome_path() is None


def test_build_options_sets_resolved_browser_path(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_mod.config, "CHROME_BROWSER_PATH", "/custom/chrome")
    monkeypatch.setattr(browser_mod.config, "CHROME_USER_DATA_DIR", str(tmp_path))
    options = browser_mod.build_options()
    assert options.browser_path == "/custom/chrome"
    assert options.user_data_path == str(tmp_path)
    assert any(arg.startswith("--window-size=") for arg in options.arguments)


def test_build_options_without_profile_skips_user_data_path(monkeypatch):
    monkeypatch.setattr(browser_mod.config, "CHROME_BROWSER_PATH", "/custom/chrome")
    options = browser_mod.build_options(use_profile=False)
    assert not any(arg.startswith("--user-data-dir=") for arg in options.arguments)


def test_build_options_disables_gpu_under_wsl(monkeypatch, tmp_path):
    # EATP-024/025: WSLg's GPU driver was confirmed to drop compositor
    # context mid-session, then later to crash the whole Chrome process
    # outright (live `--enable-logging` captures both times) — disabling the
    # GPU process entirely avoids both instabilities from the first launch.
    monkeypatch.setattr(browser_mod, "_is_wsl", lambda: True)
    monkeypatch.setattr(browser_mod.config, "CHROME_BROWSER_PATH", "/custom/chrome")
    monkeypatch.setattr(browser_mod.config, "CHROME_USER_DATA_DIR", str(tmp_path))
    options = browser_mod.build_options()
    assert "--disable-gpu" in options.arguments


def test_build_options_keeps_the_gpu_off_wsl(monkeypatch, tmp_path):
    # EATP-025: the flag is a workaround for WSLg's virtualized driver, not
    # a general setting — on native Windows (where the project now runs, on
    # a real GPU) forcing software rendering would only slow things down.
    monkeypatch.setattr(browser_mod, "_is_wsl", lambda: False)
    monkeypatch.setattr(browser_mod.config, "CHROME_BROWSER_PATH", "/custom/chrome")
    monkeypatch.setattr(browser_mod.config, "CHROME_USER_DATA_DIR", str(tmp_path))
    options = browser_mod.build_options()
    assert "--disable-gpu" not in options.arguments


def test_request_manual_intervention_publishes_event_not_input():
    test_bus = EventBus()
    original_bus = browser_mod.bus
    try:
        browser_mod.bus = test_bus
        subscriber = test_bus.subscribe()
        browser_mod.request_manual_intervention("indeed", "captcha detected")
        event = subscriber.get(timeout=1)
    finally:
        browser_mod.bus = original_bus

    assert event.phase == "collect:indeed"
    assert event.status == "needs_intervention"
    assert event.message == "captcha detected"
