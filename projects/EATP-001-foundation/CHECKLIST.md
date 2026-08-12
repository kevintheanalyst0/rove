# EATP-001 — Foundation & core contracts — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Setup & deps
- [x] venv
- [x] install core+dev
- [x] verify imports
- [x] package importable

### Phase 2 — Config & models
- [x] config.py
- [x] models.py (enums, signature, grade)
- [x] docstrings

### Phase 3 — Storage & events
- [x] storage.py (atomic+JSONL)
- [x] events.py
- [x] logging

### Phase 4 — Tests & close
- [x] test_models.py
- [x] test_storage.py
- [x] pytest green
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Phase 1 | ~10 min | No system `python3-venv` package and no sudo access; worked around via `venv --without-pip` + `get-pip.py` bootstrap inside the venv. |
| 2026-08-12 | Phases 2-4 | ~15 min | config/models/storage/events written, smoke-tested, then covered by pytest; ruff clean. |

**Total project time:** ~25 min (08:16-08:21, 2026-08-12)

## Session notes
- Built `config.py` (paths/.env/search terms/tunables/logging), `models.py` (Job/ScoredJob/RunResult,
  enums, `content_signature()` per ADR-001, `grade_from_score()` — the one mapping), `storage.py`
  (atomic JSON + streaming JSONL), `events.py` (thread-safe `EventBus`/`ProgressEvent` for the future UI).
- `Job.signature` and `ScoredJob.final_score`/`grade` are auto-derived by pydantic validators, not
  trusted from the caller — closes off the legacy "B grade with no cons" bug class at the type level.
- Environment note for next sessions: no system `python3-venv`/sudo in this WSL box. `.venv` was
  bootstrapped via `python3 -m venv --without-pip` + `get-pip.py`; reuse the existing `.venv`, don't
  recreate it with plain `python3 -m venv` (it will fail the same way).
- 34/34 tests green, `ruff check` clean. Next: EATP-002 (candidate profile & criteria).
