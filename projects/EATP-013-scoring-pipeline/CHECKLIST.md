# EATP-013 — Scoring & evaluation pipeline — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Pre-filter
- [x] score+reject+cap
- [x] tests

### Phase 2 — AI evaluate
- [x] rubric prompt (already built in EATP-012, `ai/prompts.py`; reused as-is)
- [x] id-based call
- [x] assemble ScoredJobs
- [x] mock tests

### Phase 3 — Validation guards
- [x] repair/drop (redundant clamp; the real repair lives in EATP-012's `ai/parse.py`)
- [x] contradiction strip
- [x] remote/english re-check
- [x] grade recompute (auto via `ScoredJob`'s validator; also extended to `fit` — see notes)
- [x] tests

### Phase 4 — Close
- [x] rank into RunResult (`scoring.rank_scored_jobs` / `scoring.score_jobs`)
- [x] full pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Orient + plan (Step A-C) | ~10 min | Loaded charter/rubric/profile/contracts/ADR-009, verified deps, confirmed AI cap (50) with Kevin |
| 2026-08-12 | Build (Phases 1-4) | ~15 min | prefilter/evaluate/validate/rank, `fit_from_score`, criteria.toml fix, 18 new tests + 1 updated |

**Total project time:** ~25 min

## Session notes

- Built `scoring/{prefilter,evaluate,validate}.py` + `scoring/__init__.py` (Layers 2-4 of
  EVALUATION-RUBRIC.md). `AI_cap_top_n` set to 50 (was a 500 placeholder from EATP-002) to
  actually protect the Gemini free-tier quota — confirmed with Kevin.
- Found and fixed a real gap while testing ADR-009 fidelity: `criteria.toml`'s
  `title_caution_words.administrator` was English-only and never matched Spanish
  "administrativo" — the exact case ADR-009 is named after. Added an `administrativ` stem;
  updated the EATP-009 test that had (incorrectly) asserted "no caution flags" for that title.
- `ScoredJob.fit` had no producer anywhere in the pipeline (not in the AI prompt's output
  schema, not derived like `grade`). Added `fit_from_score()` to `models.py`, mirroring
  `grade_from_score()` with the exact score bands the AI prompt's SCORE GUIDE already uses —
  same "ONE mapping" philosophy DATA-CONTRACTS.md already applies to grade.
- Layer 4's remote/English re-check independently re-derives from job text (not from
  `job.remote_status`/`english_required`, which could be stale) — belt-and-suspenders per the
  rubric. Next project (EATP-014) should know: a job whose description doesn't literally state
  a remote phrase will get `remote_uncertain`-flagged even if upstream fields say remote — real
  scraped descriptions should carry that signal naturally since Layer 1 derived `remote_status`
  from the same text in the first place.
- `pytest`: 279 passed (18 new in `test_scoring.py`, 1 fixed in `test_filters.py`), no live AI.
