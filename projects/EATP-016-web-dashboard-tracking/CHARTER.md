# EATP-016 — Web UI — results dashboard + job tracking

**Complexity:** Medium

## Objective
The results the run produces, plus the ability to actually manage a job hunt: a dark/violet dashboard of ranked job cards, and tracking so Kevin can mark 'applied' or 'not interested' (dismissed jobs stop reappearing) and see what's NEW since the last run.

## Problems solved
P7 UX (consistent grades), P8 UX (remote-only default), and proactive P18 (new-since-last) + P19 (applied/dismissed tracking).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/DESIGN-SYSTEM.md` | Dashboard spec + tokens. |
| `docs/adr/ADR-007-run-history-and-tracking.md` | Tracking + 'new since last' design. |
| `src/rove/history/store.py` | Run history for 'new' (EATP-010). |
| `src/rove/web/server.py` | Backend to extend (EATP-015). |
| `src/rove/models.py` | ScoredJob + grade mapping (EATP-001). |

## Dependencies
- **Projects:** EATP-010, EATP-014, EATP-015.
- **Libraries:** (none new).

## Scope
**In:**
- Backend: GET /results (RunResult), plus tracking endpoints (mark applied / dismissed, persisted server-side).
- web/static: results grid — job cards (title, company, grade pill by the ONE mapping, true-remote badge, source, age, one-line summary, expander for pros/contras, apply button).
- Filters: grade, source, remote-only (ON by default), search; a NEW badge for jobs unseen in prior runs; a 'hide dismissed' default.
- Tracking: 'Apliqué' and 'No me interesa' actions; dismissed jobs are hidden from future runs; applied jobs are marked.
- Empty/paused/error states in calm Spanish.
- Tests: results render; tracking persists; a dismissed job is excluded next run; 'new' badge is correct.

**Out:**
- Scheduling/notifications (018).

## Deliverables
- extended web/server.py + web/static (dashboard)
- a small tracking store (data/tracking.jsonl)
- tests/test_web_dashboard.py

## Key design decisions & constraints
- Remote-only filter ON by default; grades colored by the ONE mapping; empty contras render cleanly.
- Dismissed feeds back into the pipeline's skip logic (a dismissed signature won't be shown again).
- Keep it single-viewport-friendly and minimal per Kevin's taste; no browser storage APIs.
- **Runner -> dashboard transition (Kevin, captured in EATP-015):** when the run finishes,
  don't hard-swap or reload the page into the dashboard — fade/slide from the runner's
  "Listo" state into the results grid. EATP-015 built `web/static/` as a single-page app
  with CSS/JS-driven state views (`working` / `attention` / `error` / `done`) for exactly
  this reason: this project adds a `results` state to that same state machine and animates
  `done -> results`, it doesn't introduce a second page/navigation.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1-2 sessions (~3-4 h).

## Open questions for Kevin
- For 'No me interesa', hide that exact posting only, or also similar reposts by the same company/title? (Default: hide that signature; offer a 'hide all from this company' option later.)
