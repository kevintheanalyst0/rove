# EATP-018 — QA, hardening, automation & GitHub publish — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Verify
- [x] E2E run
- [x] Playwright UI verification
- [x] timing check

### Phase 2 — Automate
- [x] one-click run verified (Playwright click on the real UI control drove a real run start)
- [x] optional scheduler — documented only, not activated: `docs/governance/AUTOMATION.md`
- [x] optional notification/hook — Kevin declined it (2026-08-12); explicitly not built, noted in AUTOMATION.md

### Phase 3 — Docs & harden
- [x] README/how-to (ES)
- [x] CHANGELOG
- [x] secret/gitignore audit — `.env` and `data/` (incl. `browser_profile/`) confirmed
      gitignored and never committed (`git log --all -- .env` empty)

### Phase 4 — Publish
- [x] Kevin approval — público, nombre `career-radar` (2026-08-12, chat)
- [x] init/clean — audited: `.env`/`data/` (incl. browser_profile, cookies) gitignored
      and never committed; `legacy/` has no secrets; no stray files in `git status`
- [x] push to GitHub — https://github.com/kevintheanalyst0/career-radar (public)
- [x] ROADMAP all done + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Phase 1 start | — | Prior session's live run stalled: Chrome window wasn't visible in WSL to solve Indeed's captcha (WSLg issue), had to restart Ubuntu. Discarded misleading README/CHANGELOG drafts that claimed EATP-018 was finished when it wasn't. DISPLAY/WAYLAND_DISPLAY look healthy now; re-running fresh (no resume) to retest indeed/linkedin, which the stale checkpoint had marked "empty". |
| 2026-08-12 | Phase 1 done | ~16 min (run) + verification | E2E run via the real web UI: 232 collected -> 48 gated -> 48 AI-evaluated -> 48 final (A+:2, A:1, B:3, D:42). Indeed's captcha resolved manually with the Chrome window visible (WSLg confirmed working post-restart). linkedin/lever/remoteok came back "zero — posible bloqueo" (source-health flagged it correctly, not a crash). Playwright screenshots (spinner state via a fake-pipeline instance on a throwaway port, no live calls; results dashboard via the real, already-populated server) both render correctly — dots spinner+status text, dashboard cards/sidebar with no overlap. |
| 2026-08-12 | Phase 2-3 done | ~25 min | Confirmed linkedin/lever/remoteok's zero results were genuine (checked their APIs directly, no blocking). Wrote `docs/governance/AUTOMATION.md` (documented, not activated). Kevin declined the match-notification hook. Wrote real `README.md`/`CHANGELOG.md`. `pytest`: 326 passed, no live AI. |

**Total project time:** ~1 h 10 min (this session; prior aborted session not separately timed)

## Session notes
E2E-verified the full pipeline through the real web UI (48 final matches from 232
collected); the WSLg/Chrome-visibility issue that blocked the previous session was
resolved by restarting Ubuntu and is now documented in the README as a known fix.
Playwright confirms both the spinner and results-dashboard UI states render correctly.
Wrote `docs/governance/AUTOMATION.md` for an opt-in daily scheduled run (Kevin can
activate later); explicitly did not build a match-notification hook per Kevin's call.
Replaced the previous session's misleading README/CHANGELOG drafts (which claimed
finished work — Playwright checks, notification hook, GitHub publish — that had never
actually happened) with an honest account. Publishing to GitHub (public, `career-radar`)
next, with Kevin's explicit approval.
