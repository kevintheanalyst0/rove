"""Collector protocol + registry — the contract every source plugs into.

A collector's only job is to yield normalized `Job`s (see DATA-CONTRACTS.md).
No gating, no dedup, no cache lookups here — those live downstream in
EATP-009/010. This keeps every collector dumb, testable, and swappable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from career_radar.models import Job


@runtime_checkable
class Collector(Protocol):
    """Every source implements this."""

    name: str

    def collect(self) -> Iterator[Job]: ...


class CollectorStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    ERROR = "error"


class CollectorResult(BaseModel):
    """Per-source outcome: yield count + health. Feeds EATP-011's self-check."""

    source: str
    status: CollectorStatus
    yielded: int = 0
    error: str | None = None
    started_at: datetime
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0


def run_collector(
    collector: Collector, on_job: Callable[[Job], None] | None = None
) -> tuple[list[Job], CollectorResult]:
    """Run one collector to completion. Never raises: a broken source can't
    take down a whole run — the failure is captured in the returned envelope
    (`status=error`) instead.

    Pass `on_job` to stream each `Job` out as it's collected (e.g. write it to
    `data/raw/<source>.jsonl`) instead of buffering the whole source in
    memory; in that case the returned list is empty and `result.yielded` is
    the count.
    """
    started = datetime.now(UTC)
    jobs: list[Job] = []
    count = 0
    error: str | None = None
    try:
        for job in collector.collect():
            count += 1
            if on_job is not None:
                on_job(job)
            else:
                jobs.append(job)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: one bad source must not crash the run
        error = str(exc)
    finished = datetime.now(UTC)

    if error:
        status = CollectorStatus.ERROR
    elif count:
        status = CollectorStatus.OK
    else:
        status = CollectorStatus.EMPTY

    result = CollectorResult(
        source=collector.name,
        status=status,
        yielded=count,
        error=error,
        started_at=started,
        finished_at=finished,
        duration_seconds=(finished - started).total_seconds(),
    )
    return jobs, result


class CollectorRegistry:
    """Registers a collector factory per source name; enable/disable per source."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Collector]] = {}
        self._enabled: dict[str, bool] = {}

    def register(
        self, name: str, factory: Callable[[], Collector], *, enabled: bool = True
    ) -> None:
        self._factories[name] = factory
        self._enabled[name] = enabled

    def _check_known(self, name: str) -> None:
        if name not in self._factories:
            raise KeyError(f"unknown collector: {name!r}")

    def enable(self, name: str) -> None:
        self._check_known(name)
        self._enabled[name] = True

    def disable(self, name: str) -> None:
        self._check_known(name)
        self._enabled[name] = False

    def is_enabled(self, name: str) -> bool:
        self._check_known(name)
        return self._enabled[name]

    def names(self) -> list[str]:
        return list(self._factories)

    def enabled_names(self) -> list[str]:
        return [name for name, enabled in self._enabled.items() if enabled]

    def run(
        self, name: str, on_job: Callable[[Job], None] | None = None
    ) -> tuple[list[Job], CollectorResult]:
        self._check_known(name)
        collector = self._factories[name]()
        return run_collector(collector, on_job=on_job)

    def run_enabled(self) -> dict[str, tuple[list[Job], CollectorResult]]:
        return {name: self.run(name) for name in self.enabled_names()}
