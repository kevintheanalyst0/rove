# EATP-010 — Dedup, content-signature cache & run history — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Dedup
- [x] rapidfuzz dedup
- [x] tests

### Phase 2 — Signature cache
- [x] load/save signatures.jsonl
- [x] seen-within-N-days
- [x] update-after-run
- [x] tests

### Phase 3 — Run history
- [x] append store
- [x] 'new since last run'
- [x] tests

### Phase 4 — Close
- [x] extend gate()
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | 1+2+3+4 (single session) | ~45 min | Kevin confirmed 30-day cache window (kept EATP-003 default) before build |

**Total project time:** ~45 min

## Session notes
Legacy verdict: `jobmatch/collectors/utils.py::is_duplicate` was **rebuilt, not ported**
— it required both title AND description similarity (>=0.90/0.95), the exact anti-pattern
SCRAPING-GOTCHAS.md #4.3 flags (a reworded-title repost failed the title half and got
saved twice). The new `quality/dedup.py` groups by normalized company then decides purely
on rapidfuzz description similarity (threshold 90) — title is never read for the decision.

- `quality/cache.py`: `SignatureCache` class, JSONL-backed, `seen_recently()` /
  `update()` / `save()` / `load()`. Kevin kept the existing 30-day window from EATP-003
  rather than the charter's proposed 21.
- `history/store.py`: one append-only JSONL per run under `data/history/`, named by
  run timestamp; `known_signatures()` + `mark_new()` give "new since last run" (ADR-007).
  Callers must call `mark_new()` before `record_run()` for the same run.
- `quality/filters.py::gate()` extended with `dedup: bool = True` and `cache:
  SignatureCache | None = None` params, composing Layer 1 -> dedup -> cache-skip in one
  entry point, exactly as the charter asked ("extend gate() to include dedup +
  cache-skip"). Fully backward-compatible: all of EATP-009's existing tests pass
  unchanged (verified — none of the 12 kept fixture jobs share a company, so dedup
  never touches that count; `cache=None` by default skips the cache step entirely).
- Applied/dismissed tracking is explicitly out of scope here (EATP-016).
