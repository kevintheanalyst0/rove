"""Append-only log of auto-apply state per job (EATP-034), keyed by the job's
content signature — same stable identity `tracking/store.py` and
`inbox/store.py` already use.

Append-only, not a keyed store, for the same crash-safety reason as
`tracking/store.py`: a crash mid-write only loses the last line, never
corrupts the file. `latest_entries()` resolves multiple entries for the same
signature by taking the most recent one (e.g. `draft_ready` -> `submitted`
once Kevin sends it, or `manual_required` after a captcha blocked the read).

This store is deliberately separate from `tracking/store.py`: an
"applied"/"dismissed" `TrackingAction` is Kevin's own decision about a job;
an `ApplicationEntry` is this engine's own state machine for a job it is
(or was) trying to apply to on his behalf.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from rove import config
from rove.storage import append_jsonl, read_jsonl


class ApplicationStatus(str, Enum):
    DRAFT_READY = "draft_ready"
    MANUAL_REQUIRED = "manual_required"
    SUBMITTED = "submitted"
    FAILED = "failed"


class ApplicationEntry(BaseModel):
    signature: str
    status: ApplicationStatus
    answers: dict[str, str] = Field(default_factory=dict)
    resume_path: str | None = None
    note: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def record_entry(entry: ApplicationEntry) -> None:
    append_jsonl(config.APPLICATIONS_FILE, entry.model_dump(mode="json"))


def latest_entries() -> dict[str, ApplicationEntry]:
    """Signature -> most recent entry. A later entry for the same signature
    overrides an earlier one, since entries are always appended in order."""
    entries: dict[str, ApplicationEntry] = {}
    for raw in read_jsonl(config.APPLICATIONS_FILE):
        try:
            entry = ApplicationEntry(**raw)
        except (TypeError, ValueError):
            continue
        entries[entry.signature] = entry
    return entries


def already_prepared_signatures() -> set[str]:
    """Signatures the pipeline hook should NOT try to prepare again this run.
    `failed` is deliberately excluded — a transient failure (network hiccup,
    a form the site changed) gets retried on the next run rather than stuck
    forever; `draft_ready`, `manual_required`, and `submitted` are all
    terminal-ish for the prepare stage's purposes."""
    return {
        signature
        for signature, entry in latest_entries().items()
        if entry.status != ApplicationStatus.FAILED
    }


def draft_ready_entries() -> dict[str, ApplicationEntry]:
    """Every signature whose latest entry is still an unsent draft — what the
    dashboard shows for review/manual-send, and what EATP-035's sweep sends
    automatically once it ships."""
    return {
        signature: entry
        for signature, entry in latest_entries().items()
        if entry.status == ApplicationStatus.DRAFT_READY
    }
