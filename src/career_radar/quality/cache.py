"""Content-signature cache (ADR-001) — recognizes a daily repost regardless
of the site minting a new volatile id for it (P9).

Persisted as JSONL keyed by signature at `config.SIGNATURES_FILE`
(DATA-CONTRACTS.md: `{signature, first_seen, last_seen, final_score}`),
loaded once per run into an in-memory dict — trivially small even at
thousands of postings — and saved back atomically at the end.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from career_radar import config
from career_radar.storage import read_jsonl, write_jsonl


def _today() -> date:
    return datetime.now(UTC).date()


class SignatureRecord(BaseModel):
    signature: str
    first_seen: date
    last_seen: date
    final_score: int | None = None


class SignatureCache:
    """In-memory view of the signature cache. Call `load()` once at the
    start of a run, `update()` per shown job, `save()` once at the end."""

    def __init__(self, records: dict[str, SignatureRecord] | None = None) -> None:
        self._records = records if records is not None else {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> SignatureCache:
        records: dict[str, SignatureRecord] = {}
        for raw in read_jsonl(path or config.SIGNATURES_FILE):
            try:
                record = SignatureRecord(**raw)
            except (TypeError, ValueError):
                continue
            records[record.signature] = record
        return cls(records)

    def seen_recently(
        self,
        signature: str,
        *,
        window_days: int = config.SIGNATURE_SEEN_WINDOW_DAYS,
        today: date | None = None,
    ) -> bool:
        record = self._records.get(signature)
        if record is None:
            return False
        return ((today or _today()) - record.last_seen).days < window_days

    def update(self, signature: str, *, final_score: int | None = None, today: date | None = None) -> None:
        today = today or _today()
        existing = self._records.get(signature)
        if existing is None:
            self._records[signature] = SignatureRecord(
                signature=signature, first_seen=today, last_seen=today, final_score=final_score
            )
            return
        existing.last_seen = today
        if final_score is not None:
            existing.final_score = final_score

    def update_all(self, signatures: Iterable[str], *, today: date | None = None) -> None:
        today = today or _today()
        for signature in signatures:
            self.update(signature, today=today)

    def save(self, path: str | Path | None = None) -> None:
        write_jsonl(
            path or config.SIGNATURES_FILE,
            (record.model_dump(mode="json") for record in self._records.values()),
        )

    def __len__(self) -> int:
        return len(self._records)
