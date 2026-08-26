"""Standalone live test for the Indeed collector only — no AI, no other
sources, no web server (EATP-023, Kevin's ask: verifying a collector-level
fix — captcha detection, window behavior — shouldn't cost a ~10 min full
run + real AI quota every time).

Subscribes to the same `EventBus` the real web dashboard reads from, so a
captcha/login-wall notice shows up here as plain terminal text too — not
just as a (possibly unreliable) Chrome window jumping to the front. Kevin's
report (2026-08-16): a second captcha gave no signal at all because this
script, unlike the dashboard, never printed anything for it.

Run via `Probar Indeed.bat`, or directly:
    .venv/bin/python scripts/test_indeed_live.py
"""

from __future__ import annotations

import queue
import threading
import time

from rove.collectors.indeed import IndeedCollector
from rove.events import bus


def _watch_events(stop: threading.Event) -> None:
    subscriber = bus.subscribe()
    try:
        while not stop.is_set():
            try:
                event = subscriber.get(timeout=0.5)
            except queue.Empty:
                continue
            if event.status == "needs_intervention":
                print(f"\n>>> {event.message}\n", flush=True)
            elif event.status == "intervention_resolved":
                print("\n>>> Resuelto — la corrida sigue normal.\n", flush=True)
    finally:
        bus.unsubscribe(subscriber)


def main() -> None:
    print("Corriendo el collector de Indeed (sin IA, sin las demás fuentes)...", flush=True)
    print("Si sale un captcha real, va a aparecer un aviso aquí mismo en la", flush=True)
    print("terminal, y la ventana de Chrome debería subirse sola al frente.\n", flush=True)

    stop = threading.Event()
    watcher = threading.Thread(target=_watch_events, args=(stop,), daemon=True)
    watcher.start()

    start = time.monotonic()
    jobs = list(IndeedCollector().collect())
    elapsed = time.monotonic() - start
    stop.set()

    print(f"\nListo: {elapsed:.1f}s — {len(jobs)} vacantes encontradas.\n", flush=True)
    for job in jobs:
        print(f" - {job.title} | {job.company}", flush=True)


if __name__ == "__main__":
    main()
