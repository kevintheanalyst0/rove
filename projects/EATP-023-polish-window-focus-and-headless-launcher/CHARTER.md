# EATP-023 — Final polish: window focus, and a launcher with no visible terminal

## Objective
Three product-feel fixes Kevin asked for after EATP-022, framed as the last things
before closing out the whole project: (1) LinkedIn's Chrome window shouldn't steal
focus since it almost never needs him, (2) Indeed's Chrome window should stay out of
the way too, but jump to the front the moment it actually needs him (a captcha), and
(3) the visible CMD terminal the `.bat` launcher opens contradicts the whole point of
building a polished web UI in the first place — Rove should feel like a real
product, not a local script with a console window behind it.

## Problems solved
New (2026-08-15), Kevin's own framing: closes out the product-feel goal from
ADR-004/R11-R12 (`docs/adr/ADR-004-web-ui-over-terminal.md`) that EATP-015 started —
the runner UI existed so Kevin never has to watch a terminal, but the launcher itself
still opened one.

## Context to load (already loaded/built this session — no separate session needed)
| File | Why |
|------|-----|
| `src/rove/collectors/browser.py` | Window state (`start_minimized`, `bring_to_front`). |
| `src/rove/collectors/indeed.py`, `linkedin.py` | Where `bring_to_front` gets called — exactly when a captcha/login-wall fires. |
| `src/rove/web/server.py` | Auto-shutdown watcher (tab-close detection). |
| `src/rove/events.py` | `EventBus.subscriber_count()`. |
| `Rove.vbs`, `scripts/run_web.sh` | The hidden launcher. |

## Dependencies
- **Projects:** EATP-022 (done).
- **Libraries:** none new — VBScript is built into Windows, DrissionPage's window
  control was already a dependency.

## Scope
**In:**
1. **Window focus** — `browser.build_page(start_minimized=True)` (new param): LinkedIn
   and Indeed both start minimized instead of maximized-and-focused.
   `browser.bring_to_front(page)` raises and **maximizes** (Kevin's explicit
   requirement — a window that finally needs him must never be one of the old
   randomized tiny sizes) the window, called exactly once, at the moment a
   captcha/login-wall is first detected (`_wait_for_captcha_resolution` /
   `_wait_for_login`) — never on every launch.
2. **No visible terminal** — `Rove.vbs` replaces `Rove.bat`, launching
   the same `wsl.exe` command via `WScript.Shell.Run(..., 0, False)` (hidden window
   style, fire-and-forget). This also incidentally fixes the UNC-path warning Kevin
   saw (`cmd.exe` can't set its CWD to a `\\wsl.localhost\...` path) — the `.vbs`
   never goes through `cmd.exe` at all, so that warning has nothing to come from.
3. **Auto-shutdown on tab close** — Kevin's explicit call: no "Detener" button (risk of
   forgetting to press it before just closing the browser) — the server watches its
   own SSE (`/events`) subscriber count and self-terminates (`SIGTERM`) once it's been
   at zero for `_SHUTDOWN_GRACE_SECONDS` (20s) straight. Never fires before the first
   tab ever connects (don't kill a slow WSL boot before Kevin's browser loads) or while
   a run is in progress (closing the tab mid-scrape must not abort it).

**Out:** anything not explicitly asked — no new UI elements, no changes to the
scoring/collector logic itself.

## Deliverables
- `browser.py`: `start_minimized` + `bring_to_front`.
- `indeed.py` / `linkedin.py`: wired to start minimized, bring-to-front on
  captcha/login-wall only.
- `server.py` + `events.py`: auto-shutdown watcher, `enable_auto_shutdown` defaulting
  to **off** (only the real production `app` turns it on — too dangerous a default for
  any test process).
- `Rove.vbs` (replaces `Rove.bat`), README updated.

## Key design decisions & constraints
- `enable_auto_shutdown` must default to `False` in `create_app()` — a bug that
  enabled the real `os.kill(os.getpid(), SIGTERM)` inside a test process would kill
  the test run itself. Only `app = create_app(enable_auto_shutdown=True)` at the
  bottom of `server.py` (the real production instance) turns it on.
- Minimizing risked breaking LinkedIn's lazy-loaded results panel (JS visibility APIs
  sometimes throttle background tabs) — live-verified before trusting it, not assumed.
- Bring-to-front must **maximize**, not just un-minimize — Kevin's direct correction,
  tied to a real past problem (randomized small viewports that were hard to see/click).
- Kevin cannot be asked to test Windows-side `.vbs`/window-focus behavior from within
  this WSL session — flagged explicitly as needing his own real-world confirmation.

## Definition of Done
- [ ] Deliverables above exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left; no risk of the shutdown watcher ever running live in a test
- [ ] Checklist ticked, time logged
- [ ] ROADMAP status → ✅ (and the whole product marked closed, per Kevin's framing)
- [ ] Session notes written
- [ ] Committed to git (CLAUDE.md §10)
- [ ] **Kevin confirms live**: window focus behaves as expected, `.vbs` launches with
      no visible window, and the server shuts down on tab-close — none of this is
      testable from inside WSL.

## Estimated time
~2h.

## Open questions for Kevin
- None outstanding — every design point above was confirmed directly in conversation.
  The one open item is **his own live confirmation** once he tries the new launcher,
  not a question for me to ask.
