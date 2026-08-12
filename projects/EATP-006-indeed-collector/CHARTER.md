# EATP-006 — Indeed collector — optimize & reduce captchas

**Complexity:** Medium

## Objective
Keep Indeed as a first-class source and make it robust: cut captcha frequency with a stealthier browser and human-like pacing, parse listings/details reliably (JSON-LD), and handle the occasional captcha WITHOUT blocking the whole run or the terminal — it pauses only Indeed and surfaces a UI-facing event while other sources continue.

## Problems solved
P5 (captchas) — this project's core purpose; P1, P13.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/SEARCH-STRATEGY.md` | Terms, recency, gentle pacing, Indeed remote filter. |
| `docs/governance/DATA-CONTRACTS.md` | Job shape. |
| `docs/governance/SCRAPING-GOTCHAS.md` | Indeed's pagination loop-detection, rate-limit tab coordination, duplicate-job pitfalls. |
| `src/career_radar/collectors/{base,browser}.py` | Framework + stealth base (EATP-003). |
| `legacy/jobmatch/collectors/indeed.py` | Reference: JSON-LD parsing, remote attr (DSQF7), captcha points, tab threading. |
| `tests/fixtures/indeed_jobs.json` | Real records for tests. |

## Dependencies
- **Projects:** EATP-003.
- **Libraries:** (from framework).

## Scope
**In:**
- Port Indeed onto the framework with a STEALTHIER config: realistic fingerprint/viewport/headers, randomized human pacing, fewer parallel tabs, session/profile reuse, avoid rapid sequential navigation.
- Reliable parsing: search-page ids, JSON-LD title/company/datePublished, description, remote attr filter (fromage + remote).
- Captcha handling that is EVENT-BASED and NON-BLOCKING: detect captcha -> pause ONLY Indeed, emit a 'captcha needed' event (for the UI to prompt later), let the rest of the run continue; resume Indeed when solved or skip it. NEVER input().
- Make Indeed a normal enabled source (NOT optional-to-drop), but resilient so a captcha never fails the whole run.
- Tests: JSON-LD parse from fixtures; captcha-detection path is exercised with a saved captcha page (no live calls).

**Out:**
- Other collectors.
- Gate/AI/UI.

## Deliverables
- src/career_radar/collectors/indeed.py
- tests/test_collector_indeed.py (incl. captcha-detection path)

## Key design decisions & constraints
- Indeed STAYS a first-class source; the goal is fewer captchas + graceful handling, not dropping it (per Kevin).
- Captcha/login are event-based and isolated to Indeed; the run never blocks on them and never uses input().
- Tune pacing empirically: prefer fewer, slower requests over speed here — quality/robustness first.
- ADR-009: don't skip fetching a posting's detail based on an ambiguous title to save a request — only the absolute exclusion categories justify that.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2.5-3 h). Captcha behaviour is empirical; may need one tuning pass.

## Open questions for Kevin
- When a captcha appears and the UI isn't watching (e.g. a scheduled run), should Indeed auto-skip after a short wait, or pause the run until solved? (Default: wait briefly, then skip Indeed for that run and flag it.)
