# EATP-014 — Orchestrator & resumable/memory-safe run — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Wire the flow
- [x] streamed collect->gate->dedup->cache
- [x] prefilter->AI->validate->rank
- [x] persist status/results

### Phase 2 — Resume & memory safety
- [x] checkpoints (per-source collect, gate, per-batch AI)
- [x] resume logic
- [x] block-wise writes
- [x] OOM review

### Phase 3 — Knobs, events & health
- [x] fast/thorough modes (+ explicit source subset, ai_cap, recency_days)
- [x] progress events (ES)
- [x] wire source-health

### Phase 4 — Close
- [x] full-run + resume tests
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | start | — | Session started 23:03 UTC |
| 2026-08-12 | Phases 1-4 | ~9 min | 23:03 -> 23:12 UTC. Single session, no blockers. |

**Total project time:** ~9 min (2026-08-12)

## Session notes
- Built `pipeline.py`: `run()` composes collect -> health -> gate/dedup/cache ->
  prefilter -> AI evaluate -> validate -> rank -> persist out of the modules
  EATP-003-013 already built; nothing in those modules was modified.
- Resume is checkpoint-file-based, not exception-catching: each source's raw
  JSONL, `gated.jsonl`, and per-AI-batch `ai_checkpoint.jsonl` (id-matched,
  ADR-006) are the durable state. A fresh `run()` call after a crash reuses
  whatever's on disk instead of re-scraping/re-paying. `checkpoint.json` pins
  a checkpoint to the exact `mode`/`sources` it was made for — a different
  request discards it rather than resuming wrong.
- `RunStatus.PAUSED` is unused here on purpose: EATP-012's AI router already
  degrades an exhausted-quota day to `ai_evaluated=False` instead of raising,
  so there's no distinct "paused" state to represent — only a genuine crash
  needs resuming, and `RunStatus.ERROR` covers that.
- Added `collectors.build_registry()` (wires all 10 real collectors) and
  `collectors.BROWSER_SOURCES` (LinkedIn/Indeed — what `mode='fast'` drops).
  Wired `history.store.record_run()` at persist time, which had zero callers
  before this project — EATP-016 now has real data to compute "new since last
  run" from.
- Default mode is `thorough` (Kevin, this session).
- Next: EATP-015 (web UI backend + spinner) calls `pipeline.run()` directly
  and subscribes to `events.bus` for progress.
