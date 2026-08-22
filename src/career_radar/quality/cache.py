"""Content-signature cache (ADR-001) — recognizes a daily repost regardless
of the site minting a new volatile id for it (P9).

Persisted as JSONL keyed by signature at `config.SIGNATURES_FILE`
(DATA-CONTRACTS.md: `{signature, first_seen, last_seen, final_score, title,
company, source}` — the last three added in EATP-029 purely for display,
see `records()`), loaded once per run into an in-memory dict — trivially
small even at thousands of postings — and saved back atomically at the end.
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
    # EATP-029 (P29): denormalized display fields, added so "Ver cacheadas"
    # doesn't need to cross-reference history/raw files to show something
    # human-readable. Optional/blank-default so an old signatures.jsonl
    # written before this project loads fine — it just shows blank until the
    # next run updates that signature.
    title: str = ""
    company: str = ""
    source: str = ""


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

    def update(
        self,
        signature: str,
        *,
        final_score: int | None = None,
        title: str = "",
        company: str = "",
        source: str = "",
        today: date | None = None,
    ) -> None:
        today = today or _today()
        existing = self._records.get(signature)
        if existing is None:
            self._records[signature] = SignatureRecord(
                signature=signature,
                first_seen=today,
                last_seen=today,
                final_score=final_score,
                title=title,
                company=company,
                source=source,
            )
            return
        existing.last_seen = today
        if final_score is not None:
            existing.final_score = final_score
        # A repost may resurface with a slightly reworded title (SCRAPING-
        # GOTCHAS.md #4) — keep the latest, only when actually provided
        # (never blank out an existing label with an empty default).
        if title:
            existing.title = title
        if company:
            existing.company = company
        if source:
            existing.source = source

    def update_all(self, signatures: Iterable[str], *, today: date | None = None) -> None:
        today = today or _today()
        for signature in signatures:
            self.update(signature, today=today)

    def save(self, path: str | Path | None = None) -> None:
        write_jsonl(
            path or config.SIGNATURES_FILE,
            (record.model_dump(mode="json") for record in self._records.values()),
        )

    def records(self) -> list[SignatureRecord]:
        """EATP-029: for the read-only 'Ver cacheadas' view — most-recently-
        seen first, so Kevin sees what's actively suppressing repeats before
        older, about-to-expire entries."""
        return sorted(self._records.values(), key=lambda record: record.last_seen, reverse=True)

    def reset(self) -> None:
        """EATP-029 (P29): wipe every cached signature, in memory only —
        caller must still call `save()` to persist it. Deliberately narrow:
        unlike `pipeline.reset_all_run_data()` ('Limpiar caché' in the UI,
        which also wipes results/raw/history/health), this touches nothing
        but the signature cache — Kevin's own decisions (tracking, eval
        labels) and every other derived file are untouched."""
        self._records = {}

    def __len__(self) -> int:
        return len(self._records)
