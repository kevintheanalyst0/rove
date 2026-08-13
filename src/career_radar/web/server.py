"""FastAPI backend for the runner UI (EATP-015, ADR-004).

Serves the single-page app in `web/static/` and drives one pipeline run at a
time in a background thread: `pipeline.run()` is a long, blocking call
(network/browser I/O), so it can't run on FastAPI's own event loop. Progress
reaches the page over Server-Sent Events, fed by the same `EventBus`
(EATP-014/events.py) the orchestrator already publishes to.

Kevin wants an explicit "Iniciar" button, not an auto-started run on page
load (his call, EATP-015 planning) — so this only ever starts a run when
`POST /run` is called.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from career_radar import config
from career_radar.config import get_logger
from career_radar.events import EventBus, ProgressEvent
from career_radar.events import bus as default_bus
from career_radar.pipeline import run as run_pipeline
from career_radar.storage import read_json

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Bounds how long a leaked SSE thread can outlive a client that disconnected
# mid-wait: q.get() would otherwise block a thread forever (no way to cancel
# a raw blocking call from outside), leaking one thread per dropped
# connection over a session. Polling instead means the worst case is one
# thread blocked for at most this long (CLAUDE.md golden rule 3).
_EVENTS_POLL_SECONDS = 1.0


class RunRequest(BaseModel):
    mode: str = "thorough"
    sources: list[str] | None = None
    ai_cap: int | None = None
    recency_days: int | None = None
    resume: bool = True


async def _stream_events(
    event_bus: EventBus, is_disconnected: Callable[[], Awaitable[bool]]
) -> AsyncIterator[str]:
    """The SSE body: one line per `ProgressEvent`, forever. Module-level (not
    a closure inside a route) so tests can drive it directly with `anext()`
    instead of through an HTTP client — httpx's in-process ASGI transport
    fully drains a response body before handing it back, which deadlocks on
    a genuinely never-ending generator like this one."""
    subscriber_queue = event_bus.subscribe()
    try:
        while True:
            if await is_disconnected():
                break
            try:
                event: ProgressEvent = await asyncio.to_thread(
                    subscriber_queue.get, timeout=_EVENTS_POLL_SECONDS
                )
            except queue.Empty:
                continue
            yield f"data: {event.model_dump_json()}\n\n"
    finally:
        event_bus.unsubscribe(subscriber_queue)


def create_app(
    event_bus: EventBus = default_bus,
    pipeline_run: Callable[..., Any] = run_pipeline,
) -> FastAPI:
    """App factory. Tests inject a private `event_bus` and a fake
    `pipeline_run` instead of the process-wide bus and the real pipeline, so
    a route test never triggers a live scrape/AI call (CLAUDE.md §7) and
    never shares SSE subscribers with other tests.
    """
    app = FastAPI(title="Career Radar")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Local single-user app, one browser tab: a plain lock + dict is enough
    # to keep a double-click on "Iniciar" from firing two overlapping runs.
    lock = threading.Lock()
    state = {"running": False}

    def _worker(request: RunRequest) -> None:
        try:
            pipeline_run(
                mode=request.mode,
                sources=request.sources,
                ai_cap=request.ai_cap,
                recency_days=request.recency_days,
                resume=request.resume,
            )
        except BaseException:
            # pipeline.run() already logs and publishes an "error" event on
            # the bus; this background thread has no caller left to reraise
            # to, so just make sure it's not swallowed silently.
            logger.exception("background run failed")
        finally:
            with lock:
                state["running"] = False

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/run")
    def start_run(request: RunRequest) -> JSONResponse:
        with lock:
            if state["running"]:
                return JSONResponse({"status": "already_running"})
            state["running"] = True
        threading.Thread(target=_worker, args=(request,), daemon=True).start()
        return JSONResponse({"status": "started"}, status_code=202)

    @app.get("/status")
    def get_status() -> JSONResponse:
        last = read_json(config.STATUS_FILE, default=None)
        return JSONResponse({"running": state["running"], "last": last})

    @app.get("/events")
    async def stream_events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _stream_events(event_bus, request.is_disconnected),
            media_type="text/event-stream",
        )

    return app


app = create_app()
