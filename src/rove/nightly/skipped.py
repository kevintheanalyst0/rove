"""Vacancies the nightly runner could not finish and left for Kevin (EATP-037).

Append-only JSONL, latest entry per id wins — the same discipline as
`tracking/store.py` and `apply/store.py`, so a crash mid-write only loses the
last line. The id is derived from the vacancy URL, so the runner skipping the
same vacancy twice shows up once, not twice.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from rove import config
from rove.storage import append_jsonl, read_jsonl


class SkipReason(str, Enum):
    CAPTCHA = "captcha"
    ACCOUNT_REQUIRED = "account_required"
    GOVERNMENT_ID = "government_id"  # e.g. the form asks for the CURP — Claude never types it
    PENDING_QUESTION = "pending_question"
    EMPLOYMENT_QUESTION = "employment_question"
    SUSPECTED_SCAM = "suspected_scam"
    RESIDENCE_REQUIREMENT = "residence_requirement"
    OFFER_GONE = "offer_gone"
    OTHER = "other"


class SkipStatus(str, Enum):
    OPEN = "open"
    DONE = "done"


class SkippedEntry(BaseModel):
    id: str
    url: str = Field(max_length=2000)
    title: str = Field(default="", max_length=300)
    company: str = Field(default="", max_length=300)
    source: str = Field(default="", max_length=80)
    reason: SkipReason
    note: str = Field(default="", max_length=500)
    signature: str | None = Field(default=None, max_length=200)
    status: SkipStatus = SkipStatus.OPEN
    noted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        # The dashboard renders this as a link: refuse javascript:, data: etc.
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("url must be an absolute http(s) URL")
        return value


def make_id(url: str) -> str:
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:12]


def record(
    url: str,
    reason: SkipReason,
    *,
    title: str = "",
    company: str = "",
    source: str = "",
    note: str = "",
    signature: str | None = None,
) -> SkippedEntry:
    entry = SkippedEntry(
        id=make_id(url),
        url=url,
        title=title,
        company=company,
        source=source,
        reason=reason,
        note=note,
        signature=signature,
    )
    append_jsonl(config.NIGHTLY_SKIPPED_FILE, entry.model_dump(mode="json"))
    return entry


def latest() -> dict[str, SkippedEntry]:
    entries: dict[str, SkippedEntry] = {}
    for raw in read_jsonl(config.NIGHTLY_SKIPPED_FILE):
        try:
            entry = SkippedEntry(**raw)
        except (TypeError, ValueError):
            continue
        entries[entry.id] = entry
    return entries


def list_open() -> list[SkippedEntry]:
    """Open entries, newest first."""
    open_entries = [e for e in latest().values() if e.status == SkipStatus.OPEN]
    return sorted(open_entries, key=lambda e: e.noted_at, reverse=True)


def resolve(entry_id: str) -> SkippedEntry | None:
    """Kevin handled it himself. `None` if the id is unknown."""
    current = latest().get(entry_id)
    if current is None:
        return None
    resolved = current.model_copy(
        update={"status": SkipStatus.DONE, "resolved_at": datetime.now(UTC)}
    )
    append_jsonl(config.NIGHTLY_SKIPPED_FILE, resolved.model_dump(mode="json"))
    return resolved
