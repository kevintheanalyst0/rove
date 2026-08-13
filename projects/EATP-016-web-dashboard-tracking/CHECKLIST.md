# EATP-016 — Web UI — results dashboard + job tracking — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Dashboard
- [x] job cards + grade pills + remote badge
- [x] filters + apply
- [x] self-hosted fonts/assets (reuses EATP-015's vendored Inter, no new assets needed)

### Phase 2 — Tracking
- [x] applied/dismissed endpoints + store
- [x] NEW badge from history
- [x] hide-dismissed default

### Phase 3 — Close
- [x] dashboard + tracking tests
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 20:33 | start |  | Sesión iniciada tras confirmación de Kevin ("sigue, con el default") |
| 2026-08-12 20:33–20:46 | Fases 1-3 | ~13 min | Backend, dashboard+tracking, verificación visual con Playwright (estático y en vivo), tests, cierre |

**Total project time:** ~13 min

**Total project time:** _tbd_

## Session notes
- Backend: `GET /results` (last `RunResult` + Kevin's applied/dismissed status per job,
  merged fresh on every call) and `POST /track` (records to new `tracking/store.py`,
  mirrors `history/store.py`'s append-only-latest-wins shape). Dismissed signatures feed
  back into `quality/filters.gate()` via a new `dismissed` param, wired in `pipeline.py`.
- `RunResult` gained `new_signatures` — computed in `pipeline._persist()` via
  `history_store.mark_new()` **before** `record_run()` (ordering matters: after
  `record_run()`, every job in this run would already count as "known"). Tracking status,
  by contrast, has no such ordering hazard, so it's resolved live at request time instead
  of frozen into `RunResult`.
- Frontend: `results` is one more state in EATP-015's same SPA state machine, not a
  second page — `done` holds on the checkmark ~1.1s then cross-fades into the dashboard
  (`transitionToState()`), exactly the transition Kevin asked for while planning
  EATP-015. Job cards, grade pills, filters (grade/source/remote-only/search/hide-
  dismissed), NEW badge, pros/contras expander, and the two tracking actions all client-
  rendered from `/results` — no new backend routes needed per filter.
- Verified visually with Playwright against a real running server, not just pytest:
  static dashboard render + filters + dismiss/reveal + persistence across reload, AND
  the full live flow (idle → click Iniciar → working → done → fade → results) with
  zero console errors. `main.wide` widens the glass panel only for the results state.
- 305/305 tests pass repo-wide (11 new); `ruff check` clean on every changed file.
