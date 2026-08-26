"""Web UI backend (EATP-015). Routes + SSE only — `pipeline.run()` is always
replaced by a fake here, so no test ever triggers a live scrape/AI call
(CLAUDE.md §7). Each test builds its own `create_app()` with a private
`EventBus` so SSE subscribers never leak between tests.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from rove import cancellation, config
from rove.events import EventBus
from rove.quality.cache import SignatureCache
from rove.storage import write_json
from rove.web.server import (
    _SHUTDOWN_GRACE_SECONDS,
    _should_shutdown,
    _stream_events,
    _watch_for_tab_close,
    create_app,
)


def _make_client(pipeline_run, reset_run_data=lambda: None) -> tuple[TestClient, EventBus]:
    bus = EventBus()
    app = create_app(event_bus=bus, pipeline_run=pipeline_run, reset_run_data=reset_run_data)
    # EATP-026: base_url matches what run_web.sh actually binds to (127.0.0.1:8000,
    # the ROVE_PORT default), so TestClient's Host header passes the
    # same-origin check in server.py instead of the httpx default "testserver".
    return TestClient(app, base_url="http://127.0.0.1:8000"), bus


def test_index_serves_html() -> None:
    client, _bus = _make_client(pipeline_run=lambda **_: None)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Rove" in response.text


def test_static_assets_served() -> None:
    client, _bus = _make_client(pipeline_run=lambda **_: None)
    css = client.get("/static/css/style.css")
    js = client.get("/static/js/app.js")
    font = client.get("/static/fonts/Inter-500.woff2")
    assert css.status_code == 200
    assert js.status_code == 200
    assert font.status_code == 200


def test_run_starts_background_pipeline_and_blocks_a_second_call() -> None:
    calls: list[dict] = []

    def slow_run(**kwargs):
        calls.append(kwargs)
        time.sleep(0.3)

    client, _bus = _make_client(pipeline_run=slow_run)

    first = client.post("/run", json={"mode": "fast"})
    assert first.status_code == 202
    assert first.json() == {"status": "started"}

    second = client.post("/run", json={})
    assert second.json() == {"status": "already_running"}

    time.sleep(0.4)
    assert len(calls) == 1
    assert calls[0]["mode"] == "fast"


def test_run_passes_resume_false_through_for_a_clean_run() -> None:
    # Kevin's request (2026-08-16): "Empezar de nuevo" must actually discard
    # the checkpoint, not silently resume it like every prior "Iniciar" did.
    calls: list[dict] = []
    client, _bus = _make_client(pipeline_run=lambda **kwargs: calls.append(kwargs))

    response = client.post("/run", json={"resume": False})

    assert response.status_code == 202
    time.sleep(0.1)
    assert calls[0]["resume"] is False


def test_cancel_refuses_when_no_run_is_in_progress() -> None:
    client, _bus = _make_client(pipeline_run=lambda **_: None)

    response = client.post("/cancel")

    assert response.status_code == 409
    assert response.json() == {"status": "not_running"}
    assert cancellation.is_requested() is False


def test_cancel_requests_cancellation_while_a_run_is_in_progress() -> None:
    def slow_run(**kwargs):
        time.sleep(0.3)

    client, _bus = _make_client(pipeline_run=slow_run)
    client.post("/run", json={})

    response = client.post("/cancel")

    assert response.status_code == 202
    assert response.json() == {"status": "cancelling"}
    assert cancellation.is_requested() is True
    assert cancellation.is_discard_requested() is False
    time.sleep(0.4)  # let the background thread finish so it doesn't leak


def test_cancel_with_discard_sets_the_discard_flag() -> None:
    # EATP-024: "Cancelar" (distinct from "Pausar") — the new request body.
    def slow_run(**kwargs):
        time.sleep(0.3)

    client, _bus = _make_client(pipeline_run=slow_run)
    client.post("/run", json={})

    response = client.post("/cancel", json={"discard": True})

    assert response.status_code == 202
    assert cancellation.is_requested() is True
    assert cancellation.is_discard_requested() is True
    time.sleep(0.4)  # let the background thread finish so it doesn't leak


def test_reset_calls_injected_reset_and_returns_ok() -> None:
    calls: list[str] = []
    client, _bus = _make_client(pipeline_run=lambda **_: None, reset_run_data=lambda: calls.append("reset"))

    response = client.post("/reset")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == ["reset"]


def test_reset_refuses_while_a_run_is_in_progress() -> None:
    calls: list[str] = []

    def slow_run(**kwargs):
        time.sleep(0.3)

    client, _bus = _make_client(pipeline_run=slow_run, reset_run_data=lambda: calls.append("reset"))
    client.post("/run", json={})

    response = client.post("/reset")

    assert response.status_code == 409
    assert response.json() == {"status": "run_in_progress"}
    assert calls == []


def test_reset_rejects_cross_origin_request() -> None:
    """ADR-010 / EATP-026 / SEC-3, SEC-4: a same-machine cross-origin tab must
    not be able to trigger a real side effect (here, wiping run data) via a
    simple POST — see server.py's _verify_same_origin."""
    calls: list[str] = []
    client, _bus = _make_client(pipeline_run=lambda **_: None, reset_run_data=lambda: calls.append("reset"))

    response = client.post("/reset", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 403
    assert calls == []


def test_reset_rejects_spoofed_host_header() -> None:
    """Same protection, other half: Origin can look legitimate while Host is
    forged (proxy/DNS-rebinding-style attack) — both must match."""
    calls: list[str] = []
    client, _bus = _make_client(pipeline_run=lambda **_: None, reset_run_data=lambda: calls.append("reset"))

    response = client.post(
        "/reset",
        headers={"Origin": "http://127.0.0.1:8000", "Host": "evil.example.com"},
    )

    assert response.status_code == 403
    assert calls == []


def test_reset_allows_same_origin_request() -> None:
    """The real frontend's fetch("/reset") — Origin present and legitimate —
    must keep working, not just get blocked by accident."""
    calls: list[str] = []
    client, _bus = _make_client(pipeline_run=lambda **_: None, reset_run_data=lambda: calls.append("reset"))

    response = client.post("/reset", headers={"Origin": "http://127.0.0.1:8000"})

    assert response.status_code == 200
    assert calls == ["reset"]


def test_get_cache_returns_records_most_recently_seen_first(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "SIGNATURES_FILE", tmp_path / "signatures.jsonl")
    cache = SignatureCache()
    cache.update("old", title="Old One", company="Acme", source="occ", today=date(2026, 1, 1))
    cache.update("new", title="New One", company="Beta", source="indeed", today=date(2026, 1, 20))
    cache.save()

    client, _bus = _make_client(pipeline_run=lambda **_: None)
    response = client.get("/cache")

    assert response.status_code == 200
    records = response.json()["records"]
    assert [r["signature"] for r in records] == ["new", "old"]
    assert records[0]["title"] == "New One"
    assert records[0]["company"] == "Beta"


def test_reset_cache_wipes_only_the_signature_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "SIGNATURES_FILE", tmp_path / "signatures.jsonl")
    cache = SignatureCache()
    cache.update("abc123", title="Data Analyst", today=date(2026, 1, 1))
    cache.save()

    client, _bus = _make_client(pipeline_run=lambda **_: None)
    response = client.post("/cache/reset", headers={"Origin": "http://127.0.0.1:8000"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(SignatureCache.load()) == 0


def test_reset_cache_refuses_while_a_run_is_in_progress() -> None:
    def slow_run(**kwargs):
        time.sleep(0.3)

    client, _bus = _make_client(pipeline_run=slow_run)
    client.post("/run", json={})

    response = client.post("/cache/reset")

    assert response.status_code == 409
    assert response.json() == {"status": "run_in_progress"}
    time.sleep(0.4)  # let the background thread finish so it doesn't leak


def test_reset_cache_rejects_cross_origin_request() -> None:
    client, _bus = _make_client(pipeline_run=lambda **_: None)

    response = client.post("/cache/reset", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 403


def test_get_status_is_unaffected_by_a_hostile_origin() -> None:
    """Read-only routes are deliberately NOT origin-checked (see
    _verify_same_origin's docstring) — the browser's own same-origin policy
    already blocks a cross-origin page from reading the JSON response."""
    client, _bus = _make_client(pipeline_run=lambda **_: None)

    response = client.get("/status", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 200


def test_status_reflects_running_state_and_last_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(config, "CHECKPOINT_FILE", tmp_path / "checkpoint.json")

    client, _bus = _make_client(pipeline_run=lambda **_: None)
    empty = client.get("/status").json()
    assert empty == {"running": False, "last": None, "has_checkpoint": False}

    write_json(config.STATUS_FILE, {"status": "success", "message": "3 vacantes encontradas"})
    populated = client.get("/status").json()
    assert populated["running"] is False
    assert populated["last"]["message"] == "3 vacantes encontradas"


def test_status_has_checkpoint_true_when_a_checkpoint_file_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(config, "CHECKPOINT_FILE", tmp_path / "checkpoint.json")
    write_json(config.CHECKPOINT_FILE, {"mode": "thorough"})

    client, _bus = _make_client(pipeline_run=lambda **_: None)

    assert client.get("/status").json()["has_checkpoint"] is True


@pytest.mark.asyncio
async def test_stream_events_yields_published_events_and_cleans_up_on_close() -> None:
    # Exercises `_stream_events` directly rather than through an HTTP client:
    # httpx's in-process ASGI transport (sync TestClient and AsyncClient
    # alike) fully drains a response body before returning it, which
    # deadlocks against a generator that runs forever by design — only a
    # real socket (see the manual uvicorn check during EATP-015) proves the
    # HTTP layer streams incrementally.
    bus = EventBus()

    async def not_disconnected() -> bool:
        return False

    stream = _stream_events(bus, not_disconnected)

    first_task = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.05)  # let it subscribe and start blocking on the queue
    assert len(bus._subscribers) == 1
    bus.publish("collect", "running", 10.0, "Buscando en Remotive...")
    first = await asyncio.wait_for(first_task, timeout=2)
    assert "Buscando en Remotive" in first
    assert '"percent":10.0' in first

    second_task = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.05)
    bus.publish("persist", "done", 100.0, "Listo: 3 vacantes")
    second = await asyncio.wait_for(second_task, timeout=2)
    assert "Listo: 3 vacantes" in second
    assert '"status":"done"' in second

    await stream.aclose()
    assert len(bus._subscribers) == 0


@pytest.mark.asyncio
async def test_stream_events_stops_once_client_disconnects() -> None:
    bus = EventBus()
    disconnected = False

    async def is_disconnected() -> bool:
        return disconnected

    stream = _stream_events(bus, is_disconnected)
    task = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.05)
    disconnected = True

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(task, timeout=2)
    assert len(bus._subscribers) == 0


# ---------------------------------------------------------------------------
# EATP-023 — auto-shutdown when the last browser tab (SSE connection) closes
# ---------------------------------------------------------------------------


def test_should_shutdown_false_before_any_subscriber_ever_connected():
    # A slow WSL boot shouldn't kill the server before the browser even
    # loads the page — subscriber_count=0 with ever_connected=False must
    # never trigger, no matter how long "disconnected_since" claims to be.
    assert not _should_shutdown(
        subscriber_count=0, ever_connected=False, disconnected_since=0.0,
        running=False, now=9999.0,
    )


def test_should_shutdown_false_while_a_tab_is_still_connected():
    assert not _should_shutdown(
        subscriber_count=1, ever_connected=True, disconnected_since=None,
        running=False, now=9999.0,
    )


def test_should_shutdown_false_while_a_run_is_in_progress():
    # Closing the tab mid-scrape must not abort it.
    assert not _should_shutdown(
        subscriber_count=0, ever_connected=True, disconnected_since=0.0,
        running=True, now=9999.0,
    )


def test_should_shutdown_false_before_the_grace_period_elapses():
    assert not _should_shutdown(
        subscriber_count=0, ever_connected=True, disconnected_since=100.0,
        running=False, now=100.0 + _SHUTDOWN_GRACE_SECONDS - 1, grace_seconds=_SHUTDOWN_GRACE_SECONDS,
    )


def test_should_shutdown_true_once_the_grace_period_elapses_with_no_tabs_left():
    assert _should_shutdown(
        subscriber_count=0, ever_connected=True, disconnected_since=100.0,
        running=False, now=100.0 + _SHUTDOWN_GRACE_SECONDS, grace_seconds=_SHUTDOWN_GRACE_SECONDS,
    )


@pytest.mark.asyncio
async def test_watch_for_tab_close_shuts_down_after_grace_period():
    bus = EventBus()
    q = bus.subscribe()  # simulates a connected browser tab
    shutdown_calls = []

    task = asyncio.ensure_future(
        _watch_for_tab_close(
            bus, lambda: False, lambda: shutdown_calls.append(True),
            poll_seconds=0.02, grace_seconds=0.1,
        )
    )
    await asyncio.sleep(0.05)
    assert shutdown_calls == []  # still "connected" — must not fire yet

    bus.unsubscribe(q)  # the tab closes
    await asyncio.wait_for(task, timeout=2)
    assert shutdown_calls == [True]


@pytest.mark.asyncio
async def test_watch_for_tab_close_survives_a_reconnect_within_the_grace_period():
    # Models a page refresh: the old EventSource drops, the new one
    # reconnects almost immediately — must never shut down.
    bus = EventBus()
    q = bus.subscribe()
    shutdown_calls = []

    task = asyncio.ensure_future(
        _watch_for_tab_close(
            bus, lambda: False, lambda: shutdown_calls.append(True),
            poll_seconds=0.02, grace_seconds=0.3,
        )
    )
    await asyncio.sleep(0.05)
    bus.unsubscribe(q)
    await asyncio.sleep(0.05)
    bus.subscribe()  # reconnects well before the 0.3s grace period is up
    await asyncio.sleep(0.5)

    task.cancel()
    assert shutdown_calls == []


@pytest.mark.asyncio
async def test_watch_for_tab_close_waits_out_an_in_progress_run():
    bus = EventBus()
    q = bus.subscribe()
    shutdown_calls = []
    running = {"value": True}

    task = asyncio.ensure_future(
        _watch_for_tab_close(
            bus, lambda: running["value"], lambda: shutdown_calls.append(True),
            poll_seconds=0.02, grace_seconds=0.05,
        )
    )
    await asyncio.sleep(0.03)
    bus.unsubscribe(q)
    await asyncio.sleep(0.15)
    assert shutdown_calls == []  # grace period passed, but a run is active

    running["value"] = False
    await asyncio.wait_for(task, timeout=2)
    assert shutdown_calls == [True]


def test_create_app_never_enables_auto_shutdown_by_default():
    # The dangerous default: a test (or any caller) that doesn't explicitly
    # opt in must never get a live self-kill watcher.
    client, _bus = _make_client(pipeline_run=lambda **_: None)
    with client:
        pass  # lifespan runs on enter/exit; no watcher task means nothing to cancel
