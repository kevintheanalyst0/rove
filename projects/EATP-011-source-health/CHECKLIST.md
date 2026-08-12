# EATP-011 — Source health & self-check — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Classifier
- [x] ok/low/zero/error + reasons
- [x] tests

### Phase 2 — Baseline
- [x] rolling baseline from history
- [x] 'low vs norm'

### Phase 3 — Close
- [x] surface in RunResult
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | 1+2+3 (single session) | ~35 min | Light complexity as charter predicted |

**Total project time:** ~35 min

## Session notes
Key design decision, not spelled out explicitly in the charter but required to make
ADR-008 actually work: the rolling baseline must be built from each source's **raw**
collector yield (`CollectorResult.yielded`, pre-gate), never the post-gate "shown" count.
`history/store.py` (EATP-010) only tracks shown jobs — baselining against that would
conflate normal quality attrition (a day where every posting happens to be hybrid) with
an actually broken scraper, exactly the false alarm ADR-008 exists to prevent. So this
session adds its own small, separate append-only log: `data/health/yields.jsonl`, one
row per source per run — distinct from `history/`'s per-job files, different consumer.

- `models.py`: added `SourceHealthStatus` enum + `SourceHealth` model, and
  `RunResult.source_health: list[SourceHealth]` — the contract EATP-014's orchestrator
  will populate later, same pattern as EATP-009's `Job.title_caution_flags`.
- `health/check.py`: `classify_source()` (pure) + `yield_baseline()` / `record_yields()`
  (the tiny persistence) + `check_sources()` (the entry point). Needs
  `config.HEALTH_MIN_RUNS_FOR_BASELINE` (2) runs of history before trusting a baseline
  at all — a brand-new source with a low count is `ok`, not a false `low` alarm.
  "Low" = below `config.HEALTH_LOW_YIELD_RATIO` (30%) of its own rolling average
  (last `config.HEALTH_BASELINE_MAX_RUNS` = 10 runs).
- Reasons are calm Spanish strings, not shown-to-Kevin severity language, per the charter.
- Never crashes: `classify_source`/`check_sources` are pure/read-only over
  `storage.read_jsonl`, which already never raises on a missing/corrupt file.
