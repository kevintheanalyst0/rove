"""Append-only accumulated inbox (EATP-031), keyed by the job's content
signature — same identity `quality/cache.py` and `tracking/store.py` already
use.

Why this doesn't need to worry about the same signature showing up twice a
day: the quality gate already refuses to re-surface a signature it cached
within the last `SIGNATURE_SEEN_WINDOW_DAYS` (`quality/filters.gate`,
`cached_recently`), so in the normal case `append_run` only ever sees a
signature once while it's genuinely new. The first-seen lookup below exists
for the rare edge case anyway (a signature reappearing after that window
expires while somehow still unresolved) — in that case we keep the newest
score/details but never move `first_seen_at` forward, so a job doesn't jump
to "today" in the dashboard just because the pipeline touched it again.

Append-only, not a keyed store, for the same crash-safety reason as
`tracking/store.py`: a crash mid-write only loses the last line, never
corrupts the file.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from rove import config
from rove.models import ScoredJob
from rove.storage import append_jsonl, read_jsonl


class InboxEntry(BaseModel):
    signature: str
    first_seen_at: datetime
    scored: ScoredJob


def _first_seen_by_signature(path: str | Path) -> dict[str, datetime]:
    earliest: dict[str, datetime] = {}
    for raw in read_jsonl(path):
        try:
            entry = InboxEntry(**raw)
        except (TypeError, ValueError):
            continue
        current = earliest.get(entry.signature)
        if current is None or entry.first_seen_at < current:
            earliest[entry.signature] = entry.first_seen_at
    return earliest


def append_run(
    scored_jobs: Iterable[ScoredJob],
    run_started_at: datetime | None = None,
    path: str | Path | None = None,
) -> None:
    """Appends one `InboxEntry` per job from this run's `ranked` list."""
    run_started_at = run_started_at or datetime.now(UTC)
    target = Path(path or config.INBOX_FILE)
    first_seen = _first_seen_by_signature(target)
    for scored in scored_jobs:
        entry = InboxEntry(
            signature=scored.job.signature,
            first_seen_at=first_seen.get(scored.job.signature, run_started_at),
            scored=scored,
        )
        append_jsonl(target, entry.model_dump(mode="json"))


def latest_entries(path: str | Path | None = None) -> dict[str, InboxEntry]:
    """Signature -> most recent entry. A later entry for the same signature
    overrides an earlier one (its `first_seen_at` already carries the
    original date forward — see module docstring)."""
    target = Path(path or config.INBOX_FILE)
    entries: dict[str, InboxEntry] = {}
    for raw in read_jsonl(target):
        try:
            entry = InboxEntry(**raw)
        except (TypeError, ValueError):
            continue
        entries[entry.signature] = entry
    return entries


def open_entries(
    resolved_signatures: set[str] | None = None,
    path: str | Path | None = None,
) -> list[InboxEntry]:
    """Every accumulated entry Kevin hasn't applied or dismissed yet, newest
    `first_seen_at` first. `resolved_signatures` is normally
    `tracking.store.latest_actions().keys()` — any signature with EITHER
    action removes it here, applied or dismissed alike."""
    resolved = resolved_signatures or set()
    entries = [
        entry for signature, entry in latest_entries(path).items() if signature not in resolved
    ]
    entries.sort(key=lambda entry: entry.first_seen_at, reverse=True)
    return entries
