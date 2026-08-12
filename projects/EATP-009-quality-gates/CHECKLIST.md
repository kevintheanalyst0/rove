# EATP-009 — Quality gates — filters + remote hard-gate — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Exclusion + English gates
- [x] port + expand (already existed from EATP-002: `criteria.title_is_rejected`,
      `requires_advanced_english` — this session wires them into the gate)
- [x] tests

### Phase 2 — Remote hard-gate
- [x] remote_status computation (already existed: `criteria.classify_remote`)
- [x] evidence (new: `criteria.classify_remote_with_evidence`)
- [x] on-site tolerance (already existed, verified via gate tests)
- [x] tests on the real fixture leaks

### Phase 3 — Close
- [x] gate() entry point
- [x] staleness
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | 1+2+3 (single session) | ~40 min | Most classification logic already existed from EATP-002; this session was mostly wiring + evidence + tests |

**Total project time:** ~40 min

## Session notes
Turned out lighter than the charter's 2-2.5h estimate: EATP-002 had already built
`criteria.py`'s pure classification functions (`title_is_rejected`,
`title_caution_flags`, `requires_advanced_english`, `classify_remote`) — this session's
real job was wiring them into a single `gate(jobs) -> GateResult` entry point
(`src/career_radar/quality/filters.py`) plus two small additions:

- `criteria.classify_remote_with_evidence()` — new sibling of `classify_remote()`
  (unchanged signature/behavior, all its existing tests still pass) that returns the
  matched phrase(s) alongside the status, so `remote_evidence` is populated from the
  same decision logic instead of a separate re-scan that could drift out of sync.
- `Job.title_caution_flags: list[str]` — new field (also added to DATA-CONTRACTS.md).
  ADR-009 requires caution flags to travel as data, never as a gate reject; there was no
  field to hold them until now.
- Gate order matches EVALUATION-RUBRIC.md Layer 1 exactly: title/company exclusion ->
  English -> remote hard-gate -> staleness. Cache/dedup stays out of scope (EATP-010).
- Verified end-to-end against the real fixture (`tests/fixtures/latest_jobs.json`, 30
  real historical postings, legacy `remote:true/false` bool deliberately never read):
  12 kept as genuinely remote, 18 rejected — matches ADR-002's point that the legacy
  bool can't be trusted; the gate classifies from title+description text alone.
- `gate()` never raises: an exception on one job becomes a `gate_error:` rejection
  reason for that job, not a crashed batch (same discipline as `collectors/base.py`).
