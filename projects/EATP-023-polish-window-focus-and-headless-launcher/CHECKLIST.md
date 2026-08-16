# EATP-023 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Window focus (LinkedIn never jumps, Indeed only when needed)
- [x] `browser.py`: `build_page(..., start_minimized=False)` — `.mini()` when
      True, `.max()` when False (unchanged default behavior)
- [x] `browser.py`: new `bring_to_front(page)` — always maximizes (Kevin's
      explicit requirement, never just "show")
- [x] `indeed.py`: default `page_factory` now `start_minimized=True`;
      `_wait_for_captcha_resolution` calls `bring_to_front` the moment a
      captcha is first detected
- [x] `linkedin.py`: same treatment — `start_minimized=True`,
      `_wait_for_login` calls `bring_to_front` on a login-wall
- [x] Tests: added fake `.set.window` (max/mini) to both collectors' scripted
      page doubles — 345 passed
- [x] Live-verified the real risk (minimized tab breaking LinkedIn's
      lazy-loaded results panel via JS visibility throttling): 62.5s/22 jobs
      minimized vs. 61-66s/22-23 jobs before — no regression
- [x] Live-verified Indeed starting minimized doesn't break normal
      (non-captcha) collection: 197.4s/35 jobs, consistent with prior runs

### Phase 2 — No visible terminal + auto-shutdown on tab close
- [x] `events.py`: `EventBus.subscriber_count()`
- [x] `server.py`: `_should_shutdown()` (pure, tested directly),
      `_watch_for_tab_close()` (async watcher), `_terminate_process()`
      (real SIGTERM action)
- [x] `create_app(..., enable_auto_shutdown=False, shutdown=_terminate_process)`
      — defaults OFF; only `app = create_app(enable_auto_shutdown=True)` at
      the bottom (the real production instance) turns it on
- [x] Wired via a `lifespan` context manager (not deprecated `on_event`)
- [x] Tests: 5 pure-function cases + 3 async watcher cases (grace period,
      survives-a-reconnect, waits-out-an-in-progress-run) + 1 default-off
      smoke test — 345 passed total
- [x] **Live-verified against the real deployed app** (not just unit tests):
      opened a real SSE connection, killed it, server self-terminated 23s
      later (matches the 20s grace + poll interval). Also verified a
      reconnect within the grace period (models a page refresh) does NOT
      trigger shutdown — server still alive after 30s.
- [x] `Career Radar.vbs` replaces `Career Radar.bat` (removed, along with its
      now-orphaned `.ico`s from EATP-020) — hidden `WScript.Shell.Run`,
      fire-and-forget; also eliminates the UNC-path CMD warning Kevin saw,
      since there's no `cmd.exe` in the path anymore
- [x] `run_web.sh`: updated closing message (no more "cierra esta ventana")
- [x] README updated (`.vbs` launcher, new shutdown behavior, minimized
      Chrome behavior)
- [x] **Kevin's live test (2026-08-16)**: `.vbs` worked, no terminal, ~10.5
      min total run — but found a real bug: `bring_to_front` only called
      `.set.window.max()`, which resizes the *shared window* but doesn't
      select *which tab* is showing in it. On a false-alarm captcha, the
      window came forward but showed a blank/wrong tab (had to manually
      maximize+click to find the real content); on the real captcha ~1 min
      later, the window didn't come forward at all. Root-caused: DrissionPage
      has a separate `.set.activate()` (CDP `Target.activateTarget`) that
      actually selects the tab — `bring_to_front` never called it. Fixed:
      `activate()` then `window.max()`. Test doubles updated (both
      collectors' `_FakeSet`), new dedicated test in `test_browser.py`
      asserting call order — 346 passed.
- [ ] **Kevin to re-confirm live**: the activate-then-maximize fix should
      show the right tab and reliably raise the window every time — couldn't
      verify actual Windows Z-order/GUI behavior from inside WSL, only that
      the calls happen in the right order with no exceptions
- [x] **Indeed's false-captcha-alarm problem, tightened (best evidence, not
      lab-confirmed)**: `is_captcha_page`'s bare `"captcha"` substring
      matched anywhere in the *entire page HTML* — almost certainly the
      false-alarm source (e.g. a defensive reCAPTCHA badge Indeed may embed
      on ordinary pages). Confirmed this isn't a career-radar regression:
      legacy had the identical bare-word check and Kevin confirmed the same
      false-alarm behavior there. Split the check: full HTML body only
      trusts specific phrases now ("security check", "verifica que eres
      humano"); the page *title* (a short, curated string) still trusts a
      bare "captcha" too. Tests updated + 2 new ones documenting the exact
      before/after — 347 passed. **Not lab-verified against a real false
      alarm** (can't force one) — ask Kevin to watch whether they stop.
- [x] **Kevin confirmed the challenges are Cloudflare's own interstitial**
      (not Indeed-branded) — added its real, specific narrative copy/markup
      as stronger positive signals ("checking your browser before
      accessing", "needs to review the security of your connection",
      `cf-browser-verification`, `cdn-cgi/challenge-platform`, and "Just a
      moment..."/"Un momento..." as title markers) — these only ever appear
      when Cloudflare has replaced the *whole* page, unlike a bare word that
      could sit quietly in unrelated boilerplate. 4 new tests — 352 passed.

### Phase 3 — Verify & close (career-radar as a whole)
- [x] `pytest` green (345 passed)
- [ ] ROADMAP status → ✅ for EATP-023; whole project marked closed
- [ ] Session notes written
- [ ] Commit to git (CLAUDE.md §10)

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-15 | Phase 1 | ~45 min | Minimize/bring-to-front, live-verified no regression on either collector. |
| 2026-08-15 | Phase 2 | ~60 min | Auto-shutdown watcher (live-verified against real deployed app) + `.vbs` launcher. |
| 2026-08-15 | Phase 3 | ~10 min | Closed project. |

**Total project time:** ~1h55min

## Session notes
Three product-feel fixes, all Kevin's own framing of "closing out" the whole
project. Window management: LinkedIn/Indeed now start minimized instead of
maximized-and-focused, and only raise (always maximized, never a small
random size — Kevin's explicit correction) at the exact moment a
captcha/login-wall is detected, reusing the same event chokepoint EATP-020
already built. Live-verified the one real risk (a minimized tab silently
breaking LinkedIn's lazy-loaded results panel) — didn't regress. The bigger
piece: replaced the visible-terminal `.bat` launcher with a hidden `.vbs`
one, which also incidentally kills the UNC-path CMD warning Kevin reported
(no `cmd.exe` in the new path at all). Losing the terminal meant losing its
role as the "off switch" too — Kevin explicitly declined a Detener button
(forgettable) in favor of the server watching its own SSE connection count
and self-terminating ~20s after the last browser tab closes, never while a
run is active. This is the most consequential single piece of code shipped
this session (a real `SIGTERM` self-kill) — defaulted OFF in `create_app()`
on purpose so no test process can ever trigger it by accident, and
live-verified against the actual deployed app (not just unit tests) before
trusting it: watched it survive a simulated page-refresh reconnect, then
confirmed it actually shuts the process down ~23s after a real disconnect.
What's NOT verified: anything Windows-GUI-side (does the `.vbs` really show
no window, does the focus behavior look right) — that needs Kevin's own
live confirmation, flagged explicitly rather than assumed.
