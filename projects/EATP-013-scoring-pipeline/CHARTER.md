# EATP-013 — Scoring & evaluation pipeline

**Complexity:** Medium

## Objective
Turn gated jobs into ranked, trustworthy results. Repurpose the matcher as a cheap pre-filter WITH reject+cap power, run the AI deep-eval with the fixed rubric (id-based), and apply deterministic post-validation guards that fix the exact defects Kevin saw.

## Problems solved
P4, P6, P7 (criteria + grade), P10 (matcher purpose), P11/P17 (validation + id-safety), P14 (cap AI cost).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/EVALUATION-RUBRIC.md` | Layers 2-4 — the heart of this project. |
| `docs/governance/CANDIDATE-PROFILE.md` | The values the rubric encodes. |
| `docs/governance/DATA-CONTRACTS.md` | ScoredJob + the ONE grade mapping. |
| `docs/adr/ADR-009-title-is-a-signal-not-a-verdict.md` | Matcher/AI must judge full text; title_caution_flags feed the score, they don't gate it. |
| `src/rove/ai/base.py` | The AI layer this calls (EATP-012). |
| `src/rove/criteria.py` | Weights/floors/signals (EATP-002). |
| `legacy/jobmatch/pipeline/matcher.py` | Reference: old ranking-only matcher. |
| `legacy/jobmatch/pipeline/process.py` | Reference: old orchestration + the positional mapping to avoid. |

## Dependencies
- **Projects:** EATP-002, EATP-009, EATP-012.
- **Libraries:** (none new).

## Scope
**In:**
- scoring/prefilter.py: matcher score from criteria weights; REJECT below floor; CAP how many reach AI (config; default favors quality).
- scoring/evaluate.py: build the batch prompt from rubric + profile; call the AI layer with STABLE IDS; assemble ScoredJobs.
- scoring/validate.py: Layer-4 guards — repair/drop malformed, strip contradictory contras, remote re-check + demote/flag, english re-check + cap/flag, ALWAYS recompute grade from final_score.
- Final ranking (best first) into RunResult.
- Tests (mock AI + fixtures): finance-intern is rejected/capped low; 'high score + empty contras' stays consistent; non-remote high-AI-score is demoted+flagged; malformed/omitted AI item never crashes or mis-attributes; a caution-flagged-but-genuinely-good job (title like "Analista administrativo" with a strong BI description) scores well, not low; a friendly-titled job ("Data Analyst") with an off-field description (heavy Linux/dev/DBA) gets capped low by Layer 3, not waved through on title.

**Out:**
- Collecting/gating (done).
- End-to-end wiring (014).
- UI (015-016).

## Deliverables
- src/rove/scoring/{prefilter,evaluate,validate}.py
- the finalized batch prompt
- tests/test_scoring.py

## Key design decisions & constraints
- Matcher now REJECTS + CAPS, not just ranks (P10); cap protects quota (P14).
- Grade ALWAYS recomputed from final_score (P7); never trust an AI-written grade.
- Round-trip is id-based (P17); guards are deterministic and run on every AI result.
- Prompt encodes rubric philosophy + hard caps + Spanish output; fix the legacy prompt's looseness.
- **ADR-009: title is a signal, never a verdict.** The matcher's role-keyword score and any reject/cap decision must be justified by the FULL job text, not the title in isolation; `title_caution_flags()` may nudge the score, never reject alone. The prompt must tell the AI explicitly to judge the body's daily responsibilities, not the title.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2.5-3 h).

## Open questions for Kevin
- Default AI cap per run (max jobs to the AI)? Suggest ~40-60 to stay within free quotas while covering plausible matches. Confirm or adjust.
