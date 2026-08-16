"""FastAPI backend for the runner UI (EATP-015, ADR-004).

Serves the single-page app in `web/static/` and drives one pipeline run at a
time in a background thread: `pipeline.run()` is a long, blocking call
(network/browser I/O), so it can't run on FastAPI's own event loop. Progress
reaches the page over Server-Sent Events, fed by the same `EventBus`
(EATP-014/events.py) the orchestrator already publishes to.

Kevin wants an explicit "Iniciar" button, not an auto-started run on page
load (his call, EATP-015 planning) — so this only ever starts a run when
`POST /run` is called.

EATP-023: Kevin wants Career Radar to feel like a real product, not "a
cheap local app" — no visible terminal window. The launcher (`.vbs`, see
`scripts/run_web.sh`) hides the console, but that console used to be the
off switch (close the window / Ctrl+C). Without it, the server needs to
notice on its own when Kevin is done: `_watch_for_tab_close` polls the
`EventBus`'s SSE subscriber count and self-terminates once it's been at
zero (no browser tab holding an `/events` connection open) for
`_SHUTDOWN_GRACE_SECONDS` straight — long enough to survive a page refresh
or a brief network blip (the browser's `EventSource` auto-reconnects on its
own), short enough that closing the tab actually feels like "off". Never
fires before the first subscriber ever connects (a slow WSL boot shouldn't
kill itself before Kevin's browser even loads the page), and never while a
run is in progress (closing the tab mid-scrape must not abort it — it waits
for the run to finish, then re-checks).
"""

from __future__ import annotations

import asyncio
import os
import queue
import signal
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from career_radar import config
from career_radar.config import get_logger
from career_radar.eval import labels as eval_labels_store
from career_radar.eval.labels import BadReason, Label
from career_radar.events import EventBus, ProgressEvent
from career_radar.events import bus as default_bus
from career_radar.pipeline import reset_all_run_data
from career_radar.pipeline import run as run_pipeline
from career_radar.storage import read_json
from career_radar.tracking import store as tracking_store
from career_radar.tracking.store import TrackingAction

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Bounds how long a leaked SSE thread can outlive a client that disconnected
# mid-wait: q.get() would otherwise block a thread forever (no way to cancel
# a raw blocking call from outside), leaking one thread per dropped
# connection over a session. Polling instead means the worst case is one
# thread blocked for at most this long (CLAUDE.md golden rule 3).
_EVENTS_POLL_SECONDS = 1.0

# EATP-023 — auto-shutdown when the last browser tab goes away (see module
# docstring). Grace period survives a page refresh (EventSource reconnects
# in ~3s by default) or a brief network blip; poll interval just needs to be
# comfortably smaller than the grace period.
_SHUTDOWN_GRACE_SECONDS = 20.0
_SHUTDOWN_POLL_SECONDS = 2.0


def _should_shutdown(
    *,
    subscriber_count: int,
    ever_connected: bool,
    disconnected_since: float | None,
    running: bool,
    now: float,
    grace_seconds: float = _SHUTDOWN_GRACE_SECONDS,
) -> bool:
    """Pure decision logic, tested directly — no asyncio/timing involved."""
    if not ever_connected or subscriber_count > 0 or running or disconnected_since is None:
        return False
    return (now - disconnected_since) >= grace_seconds


async def _watch_for_tab_close(
    event_bus: EventBus,
    is_running: Callable[[], bool],
    shutdown: Callable[[], None],
    poll_seconds: float = _SHUTDOWN_POLL_SECONDS,
    grace_seconds: float = _SHUTDOWN_GRACE_SECONDS,
) -> None:
    """Runs for the lifetime of the app; never raises out (a bug here must
    never take the whole server down harder than it already would)."""
    ever_connected = False
    disconnected_since: float | None = None
    try:
        while True:
            await asyncio.sleep(poll_seconds)
            count = event_bus.subscriber_count()
            if count > 0:
                ever_connected = True
                disconnected_since = None
                continue
            if not ever_connected:
                continue
            if disconnected_since is None:
                disconnected_since = time.monotonic()
            if _should_shutdown(
                subscriber_count=count,
                ever_connected=ever_connected,
                disconnected_since=disconnected_since,
                running=is_running(),
                now=time.monotonic(),
                grace_seconds=grace_seconds,
            ):
                shutdown()
                return
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - a bug in the watcher must not crash the server
        logger.exception("tab-close watcher failed")


def _terminate_process() -> None:
    """Real shutdown action: SIGTERM is what uvicorn already treats as a
    graceful-stop signal (same as Ctrl+C in the old visible terminal)."""
    os.kill(os.getpid(), signal.SIGTERM)


class RunRequest(BaseModel):
    mode: str = "thorough"
    sources: list[str] | None = None
    ai_cap: int | None = None
    recency_days: int | None = None
    resume: bool = True


class TrackRequest(BaseModel):
    signature: str
    action: TrackingAction


class LabelRequest(BaseModel):
    signature: str
    label: Label
    reason: BadReason | None = None


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
    reset_run_data: Callable[[], None] = reset_all_run_data,
    enable_auto_shutdown: bool = False,
    shutdown: Callable[[], None] = _terminate_process,
) -> FastAPI:
    """App factory. Tests inject a private `event_bus` and a fake
    `pipeline_run` instead of the process-wide bus and the real pipeline, so
    a route test never triggers a live scrape/AI call (CLAUDE.md §7) and
    never shares SSE subscribers with other tests. `reset_run_data` is
    injectable the same way, so a route test never touches real files on
    disk either.

    `enable_auto_shutdown` defaults to **off** on purpose (EATP-023): the
    real self-kill (`shutdown`, default `_terminate_process` -> SIGTERM) is
    dangerous to ever run inside a test process by accident, so only the
    real production `app` at the bottom of this module turns it on. Tests
    that do want to exercise the watcher inject a harmless fake for
    `shutdown`.
    """
    # Local single-user app, one browser tab: a plain lock + dict is enough
    # to keep a double-click on "Iniciar" from firing two overlapping runs.
    lock = threading.Lock()
    state = {"running": False}

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        watcher_task = (
            asyncio.create_task(
                _watch_for_tab_close(event_bus, lambda: state["running"], shutdown)
            )
            if enable_auto_shutdown
            else None
        )
        try:
            yield
        finally:
            if watcher_task is not None:
                watcher_task.cancel()

    app = FastAPI(title="Career Radar", lifespan=_lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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

    @app.get("/favicon.ico")
    def favicon() -> FileResponse:
        # Edge's --app mode (scripts/run_web.sh) reads this to pick the
        # Windows taskbar icon — it requests /favicon.ico directly, not
        # just the <link rel="icon"> in index.html.
        return FileResponse(STATIC_DIR / "favicon.ico")

    @app.post("/run")
    def start_run(request: RunRequest) -> JSONResponse:
        with lock:
            if state["running"]:
                return JSONResponse({"status": "already_running"})
            state["running"] = True
        threading.Thread(target=_worker, args=(request,), daemon=True).start()
        return JSONResponse({"status": "started"}, status_code=202)

    @app.post("/reset")
    def reset_data() -> JSONResponse:
        """"Limpiar caché" (EATP-019, Kevin's call): wipe every derived
        run artifact for a clean test run. Refuses while a run is active —
        same reasoning as `/run`'s re-entrancy guard, since wiping
        `raw/*.jsonl`/checkpoints out from under an in-progress run would
        corrupt it, not just waste time."""
        with lock:
            if state["running"]:
                return JSONResponse({"status": "run_in_progress"}, status_code=409)
        reset_run_data()
        return JSONResponse({"status": "ok"})

    @app.get("/status")
    def get_status() -> JSONResponse:
        last = read_json(config.STATUS_FILE, default=None)
        return JSONResponse({"running": state["running"], "last": last})

    @app.get("/results")
    def get_results() -> JSONResponse:
        """The last completed run, plus Kevin's current applied/dismissed
        status per job — computed fresh on every call (unlike `new_signatures`
        on the `RunResult` itself, tracking status has no ordering hazard, so
        there's no need to freeze it at persist time)."""
        result = read_json(config.RESULTS_FILE, default=None)
        tracking = {
            signature: action.value
            for signature, action in tracking_store.latest_actions().items()
        }
        return JSONResponse({"result": result, "tracking": tracking})

    @app.post("/track")
    def track(request: TrackRequest) -> JSONResponse:
        tracking_store.record_action(request.signature, request.action)
        return JSONResponse({"status": "ok", "signature": request.signature, "action": request.action.value})

    @app.get("/eval/labels")
    def get_eval_labels() -> JSONResponse:
        """Kevin's good/bad labels so far, for the match-quality harness
        (EATP-017) — keyed by signature so the dashboard can show what's
        already labeled without re-asking."""
        labels = {
            signature: entry.model_dump(mode="json")
            for signature, entry in eval_labels_store.latest_labels().items()
        }
        return JSONResponse(labels)

    @app.post("/eval/label")
    def label_job(request: LabelRequest) -> JSONResponse:
        eval_labels_store.record_label(request.signature, request.label, request.reason)
        return JSONResponse({
            "status": "ok",
            "signature": request.signature,
            "label": request.label.value,
            "reason": request.reason.value if request.reason else None,
        })

    @app.get("/events")
    async def stream_events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _stream_events(event_bus, request.is_disconnected),
            media_type="text/event-stream",
        )

    return app


app = create_app(enable_auto_shutdown=True)
