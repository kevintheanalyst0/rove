"""Append each run's shown jobs (signature + timestamp) to
`data/history/<run-timestamp>.jsonl`. Append-only, one file per run — runs
never collide or overwrite each other, and a crash mid-write only loses the
last line (same discipline as `storage.append_jsonl`).

`known_signatures()` reads every prior run's file to answer "has this
signature ever been shown before" — the basis for `mark_new()`'s "new since
last run" badge (ADR-007). Callers must compute `mark_new()` *before*
calling `record_run()` for the same run, or that run's own jobs would count
as "already known" against themselves.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from rove import config
from rove.models import Job
from rove.storage import append_jsonl, read_jsonl


class HistoryEntry(BaseModel):
    signature: str
    source: str
    title: str
    company: str
    shown_at: datetime


def run_history_file(run_started_at: datetime, history_dir: str | Path | None = None) -> Path:
    directory = Path(history_dir or config.HISTORY_DIR)
    return directory / f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}.jsonl"


def record_run(
    jobs: Iterable[Job],
    run_started_at: datetime | None = None,
    history_dir: str | Path | None = None,
) -> Path:
    """Appends one `HistoryEntry` per job to this run's history file."""
    run_started_at = run_started_at or datetime.now(UTC)
    path = run_history_file(run_started_at, history_dir)
    for job in jobs:
        entry = HistoryEntry(
            signature=job.signature,
            source=job.source,
            title=job.title,
            company=job.company,
            shown_at=run_started_at,
        )
        append_jsonl(path, entry.model_dump(mode="json"))
    return path


def known_signatures(history_dir: str | Path | None = None) -> set[str]:
    """Every signature shown in any prior run's history file."""
    directory = Path(history_dir or config.HISTORY_DIR)
    if not directory.exists():
        return set()

    signatures: set[str] = set()
    for path in sorted(directory.glob("*.jsonl")):
        for raw in read_jsonl(path):
            signature = raw.get("signature")
            if signature:
                signatures.add(signature)
    return signatures


def mark_new(
    jobs: Iterable[Job],
    known: set[str] | None = None,
    history_dir: str | Path | None = None,
) -> list[tuple[Job, bool]]:
    """Pairs each job with whether it's new — its signature absent from
    every prior run's history. Pass `known` to avoid rereading disk when
    called for the same batch more than once."""
    known = known_signatures(history_dir) if known is None else known
    return [(job, job.signature not in known) for job in jobs]
