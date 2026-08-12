# EATP-011 — Source health & self-check

**Complexity:** Light

## Objective
Make the system notice when a scraper silently breaks. Track per-source yield, detect a source returning ~0 or erroring (blocked/selector-changed), and report it in the run result so an unattended run can flag 'Indeed returned 0 - likely blocked' instead of quietly missing jobs.

## Problems solved
Proactive P20 (no source-health detection); supports R12 (unattended running) and P15.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/DATA-CONTRACTS.md` | RunResult counts + per-source usage. |
| `src/career_radar/collectors/base.py` | The result/health envelope (EATP-003). |
| `docs/adr/ADR-008-source-health.md` | Health-check rationale. |

## Dependencies
- **Projects:** EATP-003, and collectors 004-008 to monitor.
- **Libraries:** (none new).

## Scope
**In:**
- health/check.py: given per-source results, classify each source ok|low|zero|error, with a short human reason.
- A rolling baseline (from run history) so 'low vs its own norm' is meaningful, not just absolute zero.
- Surface health in RunResult (and later the UI) as calm Spanish notes ('Indeed no devolvio resultados - posible bloqueo').
- Tests: a source with 0 vs a healthy baseline is flagged; a normal yield is ok.

**Out:**
- Auto-repair of scrapers (out of scope).
- Notifications (018).

## Deliverables
- src/career_radar/health/check.py
- tests/test_source_health.py

## Key design decisions & constraints
- Compare against each source's own rolling baseline from run history (EATP-010), not a global threshold.
- Health is informational; a broken source never crashes the run.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~1-1.5 h) — intentionally light.

## Open questions for Kevin
- none.
