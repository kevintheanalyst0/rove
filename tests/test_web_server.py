"""Web UI backend (EATP-015). Routes + SSE only — `pipeline.run()` is always
replaced by a fake here, so no test ever triggers a live scrape/AI call
(CLAUDE.md §7). Each test builds its own `create_app()` with a private
`EventBus` so SSE subscribers never leak between tests.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from career_radar import config
from career_radar.events import EventBus
from career_radar.storage import write_json
from career_radar.web.server import _stream_events, create_app


def _make_client(pipeline_run, reset_run_data=lambda: None) -> tuple[TestClient, EventBus]:
    bus = EventBus()
    app = create_app(event_bus=bus, pipeline_run=pipeline_run, reset_run_data=reset_run_data)
    return TestClient(app), bus


def test_index_serves_html() -> None:
    client, _bus = _make_client(pipeline_run=lambda **_: None)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Career Radar" in response.text


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


def test_status_reflects_running_state_and_last_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "STATUS_FILE", tmp_path / "status.json")

    client, _bus = _make_client(pipeline_run=lambda **_: None)
    empty = client.get("/status").json()
    assert empty == {"running": False, "last": None}

    write_json(config.STATUS_FILE, {"status": "success", "message": "3 vacantes encontradas"})
    populated = client.get("/status").json()
    assert populated["running"] is False
    assert populated["last"]["message"] == "3 vacantes encontradas"


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
