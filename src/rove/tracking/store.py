"""Append-only log of Kevin's actions on a job (ADR-007): 'aplicué' or 'no me
interesa', keyed by the job's content signature — the same stable identity
`quality/cache.py` already uses (ADR-001), so a repost of a dismissed job is
still recognized as the same posting.

Append-only, not a keyed store: a signature can appear more than once (e.g.
dismissed, then later marked applied by mistake and corrected). `latest_*()`
resolves that by taking each signature's most recent entry — same discipline
as `history/store.py`'s crash-safety (a crash mid-write only loses the last
line, never corrupts the file).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from rove import config
from rove.storage import append_jsonl, read_jsonl


class TrackingAction(str, Enum):
    APPLIED = "applied"
    DISMISSED = "dismissed"


class TrackingEntry(BaseModel):
    signature: str
    action: TrackingAction
    tracked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def record_action(signature: str, action: TrackingAction) -> None:
    entry = TrackingEntry(signature=signature, action=action)
    append_jsonl(config.TRACKING_FILE, entry.model_dump(mode="json"))


def latest_actions() -> dict[str, TrackingAction]:
    """Signature -> most recent action. A later entry for the same signature
    overrides an earlier one, since entries are always appended in order."""
    actions: dict[str, TrackingAction] = {}
    for raw in read_jsonl(config.TRACKING_FILE):
        try:
            entry = TrackingEntry(**raw)
        except (TypeError, ValueError):
            continue
        actions[entry.signature] = entry.action
    return actions


def dismissed_signatures() -> set[str]:
    """Fed back into `quality/filters.gate()` so a dismissed posting doesn't
    reappear in a future run (ADR-007)."""
    return {
        sig
        for sig, action in latest_actions().items()
        if action == TrackingAction.DISMISSED
    }
