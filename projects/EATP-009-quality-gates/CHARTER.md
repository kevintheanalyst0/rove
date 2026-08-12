# EATP-009 — Quality gates — filters + remote hard-gate

**Complexity:** Medium

## Objective
The quality backbone: deterministic gates every collected job must pass. Title/company/English exclusion gates from criteria, and the REMOTE HARD-GATE (ADR-002) that computes remote_status from positive AND anti-remote signals, with a hybrid phrase overriding remote. This is where 'remote means remote' becomes true.

## Problems solved
P4, P6 (quality), P8 (remote leaks — the 57/123 case).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/EVALUATION-RUBRIC.md` | Layer 1 hard filters + Layer 4 remote/english re-checks. |
| `docs/governance/DATA-CONTRACTS.md` | remote_status enum + evidence. |
| `docs/adr/ADR-002-remote-hard-gate.md` | Remote gate design. |
| `docs/adr/ADR-009-title-is-a-signal-not-a-verdict.md` | title_is_rejected() stays narrow (absolute categories only); title_caution_flags() is advisory, never a Layer-1 reject. |
| `docs/governance/SCRAPING-GOTCHAS.md` | §5: don't port legacy's conditional-title-rescue logic when porting `filters.py` — ADR-009 already replaced it. |
| `src/career_radar/criteria.py` | Signals/exclusions/weights + title_is_rejected/title_caution_flags (EATP-002). |
| `legacy/jobmatch/collectors/filters.py` | Reference: existing filters to port. |
| `tests/fixtures/latest_jobs.json` | Contains the 57 non-remote leaks to reject. |

## Dependencies
- **Projects:** EATP-002. (Best tested with real collector output from 004-008, but uses fixtures.)
- **Libraries:** python-dateutil.

## Scope
**In:**
- quality/filters.py: title/company/English gates (from criteria) + the REMOTE HARD-GATE computing remote_status (remote|hybrid|onsite|unknown) with anti-remote override + remote_evidence capture + on-site tolerance.
- Staleness gate (recency window).
- A gate(jobs) -> (kept, rejected_with_reasons) entry point (cache/dedup are added in 010).
- Tests: the 57 non-remote fixtures are rejected; a hybrid phrase overrides a remote phrase; advanced-English fixture rejected; on-site '1 dia al mes' passes; an ambiguous-but-caution-flagged title (e.g. "Financial Analyst", "Operations Manager") is NOT rejected by the title gate and reaches the matcher — only the absolute-category fixtures are.

**Out:**
- Dedup + cache + history (010).
- Matcher/AI (012-013).

## Deliverables
- src/career_radar/quality/filters.py
- tests/test_filters.py

## Key design decisions & constraints
- Anti-remote phrase present => hybrid/onsite even if a remote phrase also present (ADR-002).
- Ambiguous => unknown => not shown by default (surfaced separately as 'remoto incierto').
- Every rejection carries a reason string (for run counts/debug), not shown to Kevin in the UI.
- **ADR-009: title_is_rejected() is deliberately narrow.** Only `criteria.excluded_title_keywords` (absolute categories) may reject here. `title_caution_flags()` results must be attached to the job as data (e.g. a field/flag the matcher reads), never used to reject at this layer — a plain title is not proof of a bad job.

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
- none (on-site tolerance comes from EATP-002).
