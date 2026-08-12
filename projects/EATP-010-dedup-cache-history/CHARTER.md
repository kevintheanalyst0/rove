# EATP-010 — Dedup, content-signature cache & run history

**Complexity:** Medium

## Objective
Stop re-showing the same jobs and start tracking the hunt over time. Fuzzy cross-source dedup (rapidfuzz), the content-signature cache (ADR-001) that kills daily reposts regardless of volatile ids, and a run-history store that enables 'new since last run'.

## Problems solved
P9 (daily reposts), P15 (duplicates), and the proactive P18 (no run history / no 'new since last run').

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/adr/ADR-001-content-signature-cache.md` | Cache design. |
| `docs/adr/ADR-007-run-history-and-tracking.md` | Run history + tracking rationale. |
| `docs/governance/DATA-CONTRACTS.md` | signature() + cache/history file shapes. |
| `docs/governance/SCRAPING-GOTCHAS.md` | §4: three distinct duplicate cases — same-run cross-term, and the hard one (reworded title, same job): weight company+description over title, never require a title match. |
| `src/career_radar/quality/filters.py` | The gate this composes with (EATP-009). |
| `legacy/jobmatch/collectors/utils.py` | Reference: difflib dedup to replace with rapidfuzz. |

## Dependencies
- **Projects:** EATP-001, EATP-009.
- **Libraries:** rapidfuzz.

## Scope
**In:**
- quality/dedup.py: fast fuzzy cross-source dedup (rapidfuzz), replacing difflib.
- quality/cache.py: content-signature cache (data/cache/signatures.jsonl); 'seen within N days?' check; update after a run.
- history/store.py: append each run's shown jobs with signatures + timestamps so the UI can compute 'new since last run'.
- Extend the gate() entry point to include dedup + cache-skip.
- Tests: two near-duplicate fixtures collapse to one; a repeated signature is skipped on the second pass; a job absent from prior runs is marked 'new'.

**Out:**
- Applied/dismissed tracking (that's UI-side, 016).
- Matcher/AI.

## Deliverables
- src/career_radar/quality/{dedup,cache}.py
- src/career_radar/history/store.py
- tests/test_dedup.py, test_cache.py, test_history.py

## Key design decisions & constraints
- Cache is JSONL keyed by signature; loaded to a dict; written atomically.
- 'seen within N days' + description-prefix length are configurable (defaults ~21 days, 400 chars).
- Run history is append-only JSONL; 'new' = signature not seen in prior runs.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2-2.5 h).

## Open questions for Kevin
- Default 'seen within N days' cache window — 21 days OK? (A repost hidden ~3 weeks feels right; adjustable.)
