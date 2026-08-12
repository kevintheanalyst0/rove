# EATP-018 — QA, hardening, automation & GitHub publish

**Complexity:** Medium

## Objective
Final end-to-end verification (incl. a Playwright visual check of the UI), reduce remaining manual steps (verified one-click run, optional daily schedule, optional alert when a new A-grade remote match appears), finalize docs, audit for secrets, and publish the repo to Kevin's GitHub.

## Problems solved
P16 (GitHub), R12 (minimize manual actions), final P13/P14 check, overall hardening.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules — esp. 10 git/publish. |
| `ROADMAP.md` | Confirm all prior projects are done. |
| `docs/governance/ARCHITECTURE.md` | Confirm built system matches the design. |
| `src/career_radar/web/server.py` | The UI to visually verify (015-016). |
| `.gitignore` | Confirm secrets/data/personal artifacts excluded before publishing. |

## Dependencies
- **Projects:** all (001-017).
- **Libraries:** playwright (+ playwright install chromium).

## Scope
**In:**
- End-to-end run verifying the full flow + timing (fixtures, or a single Kevin-approved live run).
- Playwright visual verification of the UI (runner state + dashboard render correctly; screenshots).
- Automation: verified one-click launch; optional simple scheduler (documented cron/Task Scheduler) for a daily run; optional lightweight notification when a new A-grade remote match appears (implement the simplest reliable channel, or leave a clean hook + doc).
- Docs: finalize README, a short Spanish 'Como correrlo' for Kevin, and a CHANGELOG.
- Hardening: calm error states; secret/gitignore audit (.env, data/, browser profiles, CVs/cover letters).
- GitHub publish: after Kevin's approval, init/clean, push to his repo.

**Out:**
- New features (backlog: CV tailoring, app tracking beyond applied/dismissed).

## Deliverables
- passing E2E + Playwright verification
- verified one-click run (+ optional scheduler/notification or documented hook)
- finalized docs + CHANGELOG
- published GitHub repository

## Key design decisions & constraints
- Publish ONLY after Kevin's explicit approval; re-verify .gitignore covers secrets/data/personal files.
- Keep notifications simple and reliable; a clean hook + doc is acceptable if a full integration is risky.
- If a live E2E run is used, it's a single approved run (AI quota discipline).

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2-3 h).

## Open questions for Kevin
- GitHub: public or private, and repo name (default career-radar)? Want the daily auto-run + notification, and if so which channel (desktop / email / Telegram)?
