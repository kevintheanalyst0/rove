# EATP-017 — Match-quality evaluation harness

**Complexity:** Light-medium

## Objective
Prove the rebuild actually surfaces better remote DA/BI jobs (not just different ones). A small harness where Kevin labels a handful of recent results as good/bad, and the system reports precision (how many shown jobs are genuinely relevant + remote) so we can trust P4/P15 are solved and tune thresholds with evidence.

## Problems solved
Proactive P22 (no way to measure if quality improved); validates P4, P6, P15.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/EVALUATION-RUBRIC.md` | What 'good' means (the target). |
| `docs/governance/CANDIDATE-PROFILE.md` | Kevin's definition of a good job. |
| `src/rove/pipeline.py` | Produces the runs we evaluate (EATP-014). |
| `src/rove/history/store.py` | Where results/history live (EATP-010). |

## Dependencies
- **Projects:** EATP-013, EATP-014.
- **Libraries:** (none new).

## Scope
**In:**
- A tiny labeling flow: take a run's shown jobs, let Kevin mark each good/bad (a simple CLI-free step or a minimal page), store labels.
- eval/report.py: compute precision@shown, false-positive reasons (non-remote / off-role / English), and a short summary.
- A baseline snapshot so future tuning can be compared ('this change raised precision from X to Y').
- Tests: metrics compute correctly on a labeled fixture set.

**Out:**
- Automated ground-truth (out of scope; labels are Kevin's).
- Model training (out of scope).

## Deliverables
- src/rove/eval/report.py + a minimal labeling entry point
- tests/test_eval.py
- a baseline metrics snapshot

## Key design decisions & constraints
- Keep labeling lightweight (a dozen or two jobs is enough to catch regressions).
- Report false positives by reason so tuning is targeted (remote gate vs field cap vs English).

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~1.5-2 h) — intentionally light.

## Open questions for Kevin
- Prefer to label via a small web page (reuse the dashboard), or a simple file you edit? (Default: a small page tied to the dashboard.)
