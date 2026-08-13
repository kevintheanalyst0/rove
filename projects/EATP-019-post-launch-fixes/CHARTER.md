# EATP-019 — Post-launch fixes: captcha/browser UX, self-serve launcher, cache reset, source reliability

## Objective
A batch of fixes/improvements Kevin asked for after using the published product for the
first time: two real bugs (Indeed's captcha handling only works once per run; LinkedIn
silently returns zero with no visibility into why), and three usability gaps (no
self-serve way to run the pipeline without Claude Code, no way to reset to a clean state
for testing, the manual-intervention Chrome window sometimes opens tiny instead of
full-screen). Kevin explicitly asked to do this **in phases, easiest to hardest** — this
charter is ordered that way and each phase gets its own confirmation before the next.

## Problems solved
Not on the original P1-P25 list — these are new, raised directly by Kevin after EATP-018
shipped (2026-08-12). Related to P5 (Indeed captchas) and P15/P20 (missing matches /
silent source failure), which this extends.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `src/career_radar/collectors/browser.py` | Chrome launch options — window size/fullscreen. |
| `src/career_radar/collectors/indeed.py` | Captcha coordination bug (Phase 5). |
| `src/career_radar/collectors/linkedin.py` | Silent-empty diagnosis (Phase 6). |
| `src/career_radar/web/server.py` + `web/static/` | Cache-reset button (Phase 3). |
| `src/career_radar/config.py` | Data file paths, `CHROME_USER_DATA_DIR`. |
| `docs/governance/AUTOMATION.md` | Existing WSL/`wsl.exe` launch pattern to reuse for Phase 2. |

## Dependencies
- **Projects:** EATP-018 (done — this only makes sense against the shipped product).
- **Libraries:** none new expected.

## Scope
**In (ordered easiest → hardest, per Kevin):**
1. Chrome opens **maximized/full-screen** for the manual-intervention window (currently
   a random small viewport, ~1366×768 to 1920×1080 — never full-screen; new tabs can
   look tiny because of it).
2. A **self-serve launcher** so Kevin can start the pipeline without Claude Code open —
   a Windows-side script (double-click) that runs the WSL command + opens the browser,
   replacing the mental model of the old legacy `.bat` file.
3. A **"Limpiar caché" button** next to "Iniciar búsqueda" — wipes previous-run data
   (checkpoint, raw/gated jobs, AI checkpoint, results, status, content-signature cache,
   run history, source-health log) so Kevin can get a clean run while testing. Does
   **not** touch the browser profile/cookies (see open question below).
4. **Indeed session persistence** — verify/document that the existing shared browser
   profile (`CHROME_USER_DATA_DIR`, already `use_profile=True` for both collectors)
   is what makes a logged-in Indeed session stick between runs, the same mechanism
   LinkedIn already relies on. Likely just needs Kevin to log into indeed.com once in
   that profile; not a code change unless investigation says otherwise.
5. **Indeed: support more than one captcha per run.** Confirmed bug: `indeed.py`'s
   `_CaptchaCoordination` sets its wait deadline once per `collect()` call and never
   resets it after a captcha clears — a second captcha later in the same run reuses the
   stale (already-past) deadline, so Indeed gives up on itself silently instead of
   asking Kevin again. Fix: reset the coordinator after each resolved captcha so every
   occurrence gets its own fresh 5-minute wait + notification.
6. **LinkedIn returning zero — diagnose and fix.** `linkedin.py` has several silent
   early-returns (`_find_results_panel` finds nothing, `_load_cards` finds nothing,
   `page_has_no_real_results` matches) that all look identical from the outside — a
   real block/DOM-drift and "genuinely nothing matched today" are indistinguishable in
   the current logs/events. Hardest item: needs better instrumentation first, likely a
   supervised live run to see what LinkedIn is actually showing right now, then a fix.

**Out:** anything not listed above (no scope creep into other backlog items —
notifications, CV tailoring, etc. stay out per Kevin's existing "no" on notifications).

## Deliverables
- `browser.py`: full-screen/maximized launch.
- A launcher script + short doc/README note for running without Claude Code.
- `POST /reset` (or similar) endpoint + UI button + tests.
- A short note confirming (or fixing) Indeed session persistence.
- `indeed.py`: multi-captcha fix + test.
- `linkedin.py`: better empty-result diagnostics, and a fix once root-caused.

## Key design decisions & constraints
- Cache reset must refuse while a run is in progress (mirrors the existing `/run`
  re-entrancy guard).
- Cache reset must NOT delete `data/browser_profile/` (cookies/login sessions) unless
  Kevin says otherwise — confirm in the plan.
- Phase 6 (LinkedIn) may need a live, Kevin-supervised run to diagnose — flag this
  rather than guessing blind.

## Definition of Done
- [ ] All 6 phases built, confirmed with Kevin between each
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left
- [ ] Checklist ticked, time logged
- [ ] ROADMAP status → ✅
- [ ] Session notes written
- [ ] Committed to git (CLAUDE.md §10)

## Estimated time
~2.5–4 h total across all 6 phases (Phase 6 is the wide part of that range —
open-ended until root-caused).

## Open questions for Kevin
- Cache-reset scope: confirmed plan is "wipe run data, keep browser login/cookies" —
  say so now if you actually want it to also force a fresh login.
