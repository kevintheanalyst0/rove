# EATP-024 — Pause/Cancel reliability + Indeed browser visibility

## Objective
Three concrete problems Kevin hit live on 2026-08-16/17, after EATP-023 was already
marked ✅ closed: the "Pausar" button doesn't visibly respond when clicked in the real
browser UI; there's no real one-click "Cancelar" (discarding a run currently requires
Pausar, then a second click to start fresh); and Indeed's automation Chrome window
still doesn't reliably appear on screen, even after reverting to the pre-EATP-023
always-maximized-from-launch behavior. This project exists specifically because
EATP-023 sprawled well past its own charter and Kevin asked to split the remaining,
still-open issues into a dedicated project instead of continuing ad hoc.

## Problems solved
Not from the original P#/R# list — these are implementation gaps/regressions
surfaced live during EATP-023's extended debugging session (2026-08-16), not
originally-scoped product requirements. Traceability is to EATP-023 itself, not to
Kevin's P#/R# backlog.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `projects/EATP-023-polish-window-focus-and-headless-launcher/CHECKLIST.md` | Full history of every window-focus/visibility attempt already tried and how each one failed — read this FIRST, before trying another "bring the window forward" trick, to avoid repeating dead ends (CDP activate/max/normal dance, `document.title` marker + `powershell.exe` `SetForegroundWindow`, WM_CLOSE on a ghost window, `shell:AppsFolder` activation). |
| `src/rove/web/static/js/app.js` | Pausar/Cancelar button wiring, SSE event handling, state machine. |
| `src/rove/web/server.py` | `/cancel`, `/run`, `/status` routes; `state`/`lock`; the background `_worker`. |
| `src/rove/cancellation.py` | The cooperative cancellation flag + `RunCancelled`. |
| `src/rove/collectors/browser.py` | `build_page`, `kill_all_browsers`, `bring_to_front`, `_force_windows_foreground` — all the window-management machinery built/tried so far. |
| `src/rove/collectors/indeed.py` | Current (reverted) window behavior: opens maximized at creation, no raise-on-captcha logic. |
| `src/rove/pipeline.py` | `RunStatus.PAUSED`, checkpoint semantics (`resume`), what "cancelling" currently actually does end to end. |

## Dependencies
- **Projects:** EATP-023 (✅, but see Objective — this project exists because of its
  loose ends, not despite them being resolved).
- **Libraries:** none expected to be new; if the Pausar/Cancelar frontend fix or the
  Chrome-visibility investigation turns up a real need, announce it first (CLAUDE.md §8).

## Scope
**In:**
- Diagnose why clicking "Pausar" in Kevin's real Edge session appears to do nothing —
  the backend itself was curl-verified working end to end (kills the browser, flips
  `running` to `false`, writes `RunStatus.PAUSED`) during the live debugging that led
  to this charter, so the bug is most likely in the frontend (SSE handling, a stuck
  `disabled` state, a swallowed fetch error) — but verify that assumption, don't
  assume it.
- Add a real one-click "Cancelar" distinct from "Pausar": today, actually discarding
  a run's checkpoint requires Pausar, then a second click on "Empezar de nuevo" —
  Kevin wants both actions available directly from the working/running state.
- Get Indeed's automation Chrome window to actually be visible to Kevin from the
  moment the collector starts. This is now a *different* problem than what EATP-023
  chased (raising an already-created, already-minimized window on demand) — Indeed no
  longer starts minimized at all, so if the window still isn't appearing, the window
  is either never being created as a real visible surface in the first place, or
  WSLg's compositor is failing to display it even when Chromium itself thinks it's
  shown. Needs fresh diagnosis, not another re-application of the tricks already
  tried and already failed for the old minimized-window problem.

**Out:**
- LinkedIn's window behavior — Kevin explicitly confirmed it stays as-is
  (minimized until a login wall, `bring_to_front` on that one moment).
- The taskbar icon / AUMID work (already solved and live-verified this session).
- AI provider request-timeout tuning (already solved this session).

## Key design decisions & constraints
- Read EATP-023's CHECKLIST.md in full before touching any window-focus code — it
  documents several attempts that looked correct on paper and failed live anyway
  (WSLg specifically does not reliably respond to CDP-only focus/state calls, and a
  Windows-side `powershell.exe`/`user32.dll` force-focus call *also* failed to bring
  the window forward in Kevin's last live test). Treat "the window exists but Windows
  won't show/raise it" as the working hypothesis, not "the code forgot to ask."
- The underlying Chrome process and CDP connection are not the problem — port 9222 is
  reachable, navigation succeeds, `page.set.activate()`/`.window.max()` return
  normally. This is specifically about what WSLg does (or doesn't do) with that
  window on the Windows side.
- For Pausar/Cancelar: the `/cancel` endpoint, `cancellation.py`, and
  `browser.kill_all_browsers()` are already built and already confirmed to work via
  direct `curl` — first confirm whether the real bug is frontend-only before touching
  any backend code.

## Definition of Done
- [ ] Kevin can see Indeed's Chrome window from the moment the collector starts
      (live-verified by Kevin, not just "the code looks right").
- [ ] Clicking "Pausar" visibly and promptly changes the UI, live-verified in Kevin's
      real browser (not just curl against `/cancel`).
- [ ] A "Cancelar" action exists that discards a run's checkpoint in one click,
      without requiring Pausar first.
- [ ] `pytest` green (fixtures, no live AI/browser).
- [ ] No known OOM/crash risk left unaddressed.
- [ ] Checklist ticked, time logged.
- [ ] ROADMAP status → ✅ for EATP-024, with date + total time.
- [ ] Session notes written.
- [ ] Committed to git (CLAUDE.md §10).

## Estimated time
The Pausar UI bug and the new Cancelar button are well-scoped and should be quick
(~30–60 min combined) once the actual frontend bug is found. The Chrome-visibility
problem is open-ended: three separate approaches already failed live during EATP-023
(CDP-only raise, Windows-side `powershell.exe` force-focus, `shell:AppsFolder`
activation was for the *Edge* web-UI window, not this browser). This may need a truly
different angle (checking WSLg's own logs, testing without GPU acceleration, or
accepting a different mitigation entirely) rather than another quick fix — flagging
this honestly rather than promising a time that already has 3 broken promises behind it.

## Open questions for Kevin
- Should "Cancelar" (the new, immediate-discard action) ask for confirmation first
  (like "Limpiar caché" does), since it throws away real progress in one click? Or
  should it be a plain, no-confirmation button like "Pausar" is today?
- For the Chrome-visibility problem: are you open to trying a few more diagnostic/fix
  angles (e.g. disabling GPU acceleration, a common WSLg rendering fix; checking
  WSLg's own logs for errors), or would you rather I first check whether this is a
  known WSLg limitation before writing any more code that might not fix it either?
