# EATP-004 — HTTP collectors — OCC & Computrabajo (refactor)

**Complexity:** Light-medium

## Objective
Port the two fast, browser-free sources (OCC and Computrabajo) onto the framework. These are the cheap, reliable backbone of a run. Improve description quality where the source truncates it.

## Problems solved
P1 (clean methodology), P13 (fast HTTP path), P21 (description quality).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/DATA-CONTRACTS.md` | Job shape to emit. |
| `docs/governance/SEARCH-STRATEGY.md` | Terms + recency. |
| `docs/governance/SCRAPING-GOTCHAS.md` | Recommended-jobs cards, pagination end-signals, site filter params, duplicate-job pitfalls (Kevin's legacy incidents). |
| `src/rove/collectors/base.py` | Framework to plug into (EATP-003). |
| `legacy/jobmatch/collectors/occ.py` | Reference: OCC JSON endpoints (oferta.occ.com.mx). |
| `legacy/jobmatch/collectors/computrabajo.py` | Reference: Computrabajo cards + description API. |
| `tests/fixtures/{occ,computrabajo}_jobs.json` | Real records for tests. |

## Dependencies
- **Projects:** EATP-003.
- **Libraries:** (from framework).

## Scope
**In:**
- Port OCC to the framework (list ids -> detail JSON -> Job).
- Port Computrabajo to the framework (search cards -> description API -> Job).
- Description-quality handling: if a description is empty/too short, flag it so scoring can down-weight or skip (P21).
- Tests: each parses its saved fixture payload into valid Jobs (no live network).

**Out:**
- Browser sources (005-006).
- New sources (007-008).
- Gate/AI (later).

## Deliverables
- src/rove/collectors/{occ,computrabajo}.py
- tests/test_collector_occ.py, test_collector_computrabajo.py

## Key design decisions & constraints
- Keep them HTTP-only (fast, no browser).
- Emit remote_status='unknown' if unsure; the gate (009) decides remote definitively — do not hardcode remote=True like the legacy did.
- Carry a description_quality flag for short/empty descriptions.
- ADR-009: never skip fetching a job's detail based on an ambiguous title — only the absolute exclusion categories justify a title-only skip. Fetch first, judge on full text later.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~1.5-2.5 h).

## Open questions for Kevin
- none.
