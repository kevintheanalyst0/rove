"""In-process progress event bus.

The orchestrator (EATP-014) publishes phase/status/percent updates as it
works through a run; the web UI (EATP-015) subscribes to show the spinner and
live status text instead of a terminal (ADR-004). Built on `queue.Queue` so
it's thread-safe and trivially consumable from a FastAPI endpoint (e.g. by
looping `queue.get()` inside a Server-Sent-Events generator).
"""

from __future__ import annotations

import queue
import threading
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ProgressEvent(BaseModel):
    phase: str
    status: str
    percent: float = 0.0
    message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Thread-safe pub/sub: one `Queue` per subscriber, fed by `publish`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue[ProgressEvent]] = []

    def subscribe(self) -> queue.Queue[ProgressEvent]:
        q: queue.Queue[ProgressEvent] = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[ProgressEvent]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def subscriber_count(self) -> int:
        """EATP-023: lets the web server notice when the last connected
        browser tab (its `/events` SSE connection) has gone away, so it can
        shut itself down instead of Kevin needing a visible terminal to
        close."""
        with self._lock:
            return len(self._subscribers)

    def publish(self, phase: str, status: str, percent: float = 0.0, message: str = "") -> None:
        event = ProgressEvent(phase=phase, status=status, percent=percent, message=message)
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put(event)


# Shared default bus: the orchestrator publishes here, the web server subscribes here.
bus = EventBus()
