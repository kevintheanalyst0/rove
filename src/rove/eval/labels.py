"""Append-only log of Kevin's good/bad judgment on a shown job (P22), keyed
by the job's content signature — same stable identity `tracking/store.py`
(ADR-007) and `quality/cache.py` (ADR-001) already use, so a repost of an
already-labeled job is still recognized as the same posting.

Append-only, not a keyed store: a signature can appear more than once (e.g.
labeled "bad", then corrected to "good"). `latest_labels()` resolves that by
taking each signature's most recent entry — same discipline as
`history/store.py` and `tracking/store.py` (a crash mid-write only loses the
last line, never corrupts the file).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from rove import config
from rove.storage import append_jsonl, read_jsonl


class Label(str, Enum):
    GOOD = "good"
    BAD = "bad"


class BadReason(str, Enum):
    """Why a "bad" job slipped through — mirrors the Layer-1/3 rejection
    categories in EVALUATION-RUBRIC.md so a report can point tuning at the
    right layer."""

    NOT_REMOTE = "not_remote"
    OFF_ROLE = "off_role"
    ENGLISH = "english"
    OTHER = "other"


class LabelEntry(BaseModel):
    signature: str
    label: Label
    reason: BadReason | None = None
    labeled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def record_label(signature: str, label: Label, reason: BadReason | None = None) -> None:
    entry = LabelEntry(signature=signature, label=label, reason=reason if label == Label.BAD else None)
    append_jsonl(config.EVAL_LABELS_FILE, entry.model_dump(mode="json"))


def latest_labels() -> dict[str, LabelEntry]:
    """Signature -> most recent label. A later entry for the same signature
    overrides an earlier one, since entries are always appended in order."""
    labels: dict[str, LabelEntry] = {}
    for raw in read_jsonl(config.EVAL_LABELS_FILE):
        try:
            entry = LabelEntry(**raw)
        except (TypeError, ValueError):
            continue
        labels[entry.signature] = entry
    return labels
