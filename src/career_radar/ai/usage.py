"""Per-provider daily usage tracker (ADR-003) — persisted at
`config.AI_USAGE_FILE` so a restart still remembers what's been spent today,
and a provider marked exhausted is never re-hit until the date rolls over.

Same load-once/save-atomically pattern as `quality/cache.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from career_radar import config
from career_radar.storage import read_json, write_json


def _today() -> date:
    return datetime.now(UTC).date()


class ProviderUsage(BaseModel):
    date: date
    requests: int = 0
    exhausted: bool = False


class UsageTracker:
    def __init__(self, records: dict[str, ProviderUsage] | None = None) -> None:
        self._records = records if records is not None else {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> UsageTracker:
        raw = read_json(path or config.AI_USAGE_FILE, default={}) or {}
        records: dict[str, ProviderUsage] = {}
        for provider_id, data in raw.items():
            try:
                records[provider_id] = ProviderUsage(**data)
            except (TypeError, ValueError):
                continue
        return cls(records)

    def _current(self, provider_id: str, *, today: date | None = None) -> ProviderUsage:
        today = today or _today()
        record = self._records.get(provider_id)
        if record is None or record.date != today:
            record = ProviderUsage(date=today)
            self._records[provider_id] = record
        return record

    def is_exhausted(self, provider_id: str, *, today: date | None = None) -> bool:
        return self._current(provider_id, today=today).exhausted

    def record_request(
        self, provider_id: str, *, count: int = 1, today: date | None = None
    ) -> None:
        self._current(provider_id, today=today).requests += count

    def mark_exhausted(self, provider_id: str, *, today: date | None = None) -> None:
        self._current(provider_id, today=today).exhausted = True

    def save(self, path: str | Path | None = None) -> None:
        write_json(
            path or config.AI_USAGE_FILE,
            {
                provider_id: record.model_dump(mode="json")
                for provider_id, record in self._records.items()
            },
        )
