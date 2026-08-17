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
- [x] **Kevin's live re-test (2026-08-16, via the new `Probar Indeed.bat`)**:
      no false alarms this run, but a real captcha showed a "New Tab" (not
      Indeed's content) in a fullscreen-like state with no taskbar, and a
      *second* captcha ~1 min later got zero response — no notice, no
      window raise. Root-caused: Indeed's block is session-wide
      (`indeed.py`'s own docstring), so multiple tabs (search + detail
      pool) can genuinely discover the *same* still-active captcha within
      the same instant — `bring_to_front` was called unconditionally by
      *every* tab that detected it, not just the one that actually reported
      the episode, so they raced to activate/maximize themselves. Fixed:
      `report_and_get_deadline` now returns `(deadline, is_new_episode)`;
      only the reporting tab calls `bring_to_front`. Verified with a real
      `threading.Barrier` forcing genuine concurrent access (scripted fake
      responses alone can't reproduce this under the GIL — an earlier
      collector-level test attempt just serialized instead of racing).
      Applied the same fix to `linkedin.py`'s `_LoginCoordination`.
- [x] **`scripts/test_indeed_live.py` never subscribed to the `EventBus`** —
      explains "la terminal nunca avisó" for the second captcha directly:
      there was no code path to print anything for it, regardless of window
      behavior. Now watches the same bus the real dashboard reads from and
      prints `needs_intervention`/`intervention_resolved` as plain text —
      a reliable signal even if the window-raise itself is ever flaky.
- [x] **Kevin's live re-test #2 (2026-08-16)**: terminal notice worked
      (confirmed by his screenshot), but the window's frame appeared with
      no content painted until he clicked it — corrected my "wrong tab"
      theory. Added an experimental repaint nudge (`bring_to_front`:
      maximized -> normal -> maximized) — **not verified visually**, still
      pending. Also, real second-captcha window-raise failure reproduced —
      traced to `bring_to_front` firing from *every* tab that independently
      hit the same session-wide block, not just the reporting one; fixed
      (see the `report_and_get_deadline` entry above) and verified with a
      real `threading.Barrier` forcing true concurrency.
- [x] **Kevin corrected the false-captcha theory entirely**: not a WSLg
      rendering issue — proven by comparing to legacy (no WSL at all, same
      false-alarm behavior there), where a *genuine* captcha froze every
      tab until he pressed Enter, but a false one left everything running
      normally. These are real detection false positives. Fixed with a
      debounce (`_CAPTCHA_DEBOUNCE_SECONDS=3`): `_navigate` rechecks once
      before ever reporting — `tab.html` is live (CDP), not cached, so a
      transient state that clears on its own is caught before Kevin ever
      hears about it. Found and fixed a real test-infra bug along the way:
      two `monkeypatch.setattr` calls both targeting `time.sleep` (same
      global module object via `indeed.py`/`browser.py`'s plain `import
      time`) were silently conflicting, freezing the fake clock and
      producing failures that looked like real regressions.
- [ ] **Kevin to re-confirm live once more**: false alarms should stop
      (debounce); the race fix + terminal notice should already be solid.
      The window repaint nudge is the one remaining unverified piece —
      still can't confirm actual Windows/WSLg rendering behavior from here.
- [ ] **Kevin's live report (2026-08-16, separate session)**: repaint nudge
      still didn't bring the window forward for a real captcha. Root cause:
      every focus call so far (`activate`, `window.max/normal`) only ever
      reaches Chromium's *own* internal state over CDP — none of them ever
      asked *Windows* (which owns the real WSLg-forwarded Win32 window) to
      raise it. Added `browser._force_windows_foreground`: shells out to
      `powershell.exe` (reachable from WSL via interop) to find the window
      via a marker string (`bring_to_front` now sets `document.title` to it
      first, avoiding a past false-match risk — the captcha tab's title was
      sometimes a generic "New Tab") and force it forward with
      `SetForegroundWindow`, preceded by a synthetic Alt keypress
      (`keybd_event`) — the standard workaround for Windows' foreground-lock,
      which normally blocks an unrelated process from stealing focus.
      Best-effort/non-fatal (wrapped, swallows errors) so a missing/stuck
      `powershell.exe` can never break the actual captcha-wait flow. Ran the
      generated PowerShell directly (rc 0, no errors) to confirm it at least
      compiles/executes on this box — **the actual foreground-steal still
      needs Kevin's live confirmation**, same caveat as the repaint nudge.
      Tests: `_is_wsl`/`_force_windows_foreground` unit-tested with
      `subprocess.run` faked; added an autouse `tests/conftest.py` fixture
      stubbing `_force_windows_foreground` to a no-op so no test suite run
      ever shells out to a real `powershell.exe` — 360 passed.
- [x] **Separately, found and fixed a real regression (2026-08-16,
      uncommitted, unrelated to captcha focus)**: `scripts/run_web.sh` had
      been changed to launch the web UI via `msedge --app-id=<hardcoded ID>`
      (an attempt at a custom taskbar icon via an installed PWA) instead of
      the proven `msedge --app=URL`. That ID was never confirmed installed
      on Kevin's machine — this is almost certainly why he couldn't open the
      app at all ("parece que ya está activa la ventana pero no sale nada").
      Reverted to `--app=URL` as the default; `CAREER_RADAR_EDGE_APP_ID` env
      var still available to opt back in once the PWA install + ID are
      actually live-verified.
- [x] **Taskbar icon, actually solved (2026-08-16)**: turned out Career
      Radar *was* correctly installed (`web_app_install_metrics` in Edge's
      own `Preferences` confirmed it, matching Kevin's `edge://apps`
      screenshot) — the earlier "not installed" theory above was wrong.
      Root cause of the missing icon: Edge runs a persistent background
      instance (`--no-startup-window`); both `msedge --app=URL` and
      `msedge --app-id=X` just forward the request via Chromium's
      single-instance IPC into a *new popup inside that same already-running
      process* — confirmed live by window-enumerating the resulting HWND
      (owned by the same long-lived PID either way) — so the window only
      ever carries Edge's own generic icon, no matter how "correct" the
      app-id is. The fix: activate via Shell instead of a raw exe flag —
      `explorer.exe "shell:AppsFolder\<AUMID>"`, the same path Windows uses
      opening a pinned/Start-menu app. AUMID found via `(New-Object
      -ComObject Shell.Application).NameSpace('shell:AppsFolder').Items()`:
      `127.0.0.1-4FF64651_pfncv7bjx4w4g!App`. Kevin confirmed live: this
      window showed the correct icon, the `--app=`/`--app-id=` ones moments
      before did not. `run_web.sh` updated to use this by default
      (`CAREER_RADAR_APP_AUMID` env var to override if Kevin ever
      reinstalls the app and gets a new AUMID); the old `--app=URL` path
      kept only as a fallback if the var is ever cleared. Also explains why
      `--app-id` alone "didn't open anything" originally: separately, the
      exact same command run from this automated/scripted context (not
      Kevin's own interactive double-click) reproducibly fails with
      "Acceso denegado" for *any* `msedge` invocation, app-id or not —
      root cause not fully pinned down (session/token nuance of how WSL
      interop spawns Windows GUI processes vs. a real Explorer-launched
      one), but `shell:AppsFolder` activation launches cleanly from both
      contexts, so it's the more robust choice for `run_web.sh` regardless.
- [x] **New: "Cancelar" button (2026-08-16, Kevin's request)**. Found live
      while diagnosing the above: a stuck/ghost Chrome window left a run
      hung at `running: true` with no way to stop it short of killing the
      whole server. New `career_radar/cancellation.py` — one process-wide
      `threading.Event`, reset at the start of every `pipeline.run()`.
      Two-pronged so it works whether a collector is blocked *between*
      calls or *inside* one: (1) cooperative — `pipeline.py` checks it at
      every stage boundary (each source, each AI batch); `browser.py`'s new
      `start_cancellation_watcher(coord.giveup)` (called once from
      `indeed.py`/`linkedin.py`'s `collect()`) mirrors it onto the
      collectors' own existing `giveup` switch, so a captcha/login wait's
      poll loop picks it up within ~0.5s for free, no other code touched.
      (2) forceful — `browser.py` now tracks every launched Chrome's real
      PID (`build_page`/`forget_page`); `/cancel` (server.py) also calls
      `browser.kill_all_browsers()` as a safety net for a call stuck
      *inside* a single blocking CDP operation, which no cooperative check
      between iterations can interrupt. Lands as `RunStatus.PAUSED` (an
      enum value that already existed for exactly this, unused until now) —
      not ERROR — since the checkpoint survives and `resume=True` (the
      default) picks the run back up instead of re-scraping. Frontend: a
      "Cancelar" text-btn in the working state, POSTs `/cancel`. Tests: new
      `test_cancellation.py`, kill/PID-tracking + watcher tests in
      `test_browser.py` (spawns real short-lived `sleep`/`true` processes to
      verify actual OS-level kill, not mocked), cancellation-mid-collect and
      cancellation-mid-AI-scoring + resume-after-cancel in `test_pipeline.py`,
      `/cancel` route tests in `test_web_server.py` — 376 passed. New
      autouse `tests/conftest.py` fixture resets the cancellation flag
      around every test so it can never leak between them. **Not yet
      live-verified** (server/UI, not just unit tests) — ask Kevin to click
      it on a real run.
- [x] **Real regression from the `shell:AppsFolder` fix (2026-08-16, Kevin's
      live test)**: `run_web.sh` opened the window (correct icon this time)
      but the page showed `ERR_CONNECTION_REFUSED` — the server was already
      dead. Root cause: `set -e` (top of the script) treats ANY nonzero exit
      as fatal, not just ones explicitly chained with `&&` — and
      `explorer.exe`'s exit code is unreliable (nonzero even on a
      successful activation, already noted above). So the script's own EXIT
      trap (`kill "$SERVER_PID"`) fired seconds after opening the browser,
      killing uvicorn out from under the window Kevin was looking at. Fixed
      with `|| true` on that line. Verified with a real end-to-end run
      (`bash scripts/run_web.sh`, not just `bash -n`): server responded 200
      mid-run, script reached its normal end instead of dying early.
- [x] **"Cancelar" didn't work on a resumed run (2026-08-16, Kevin's live
      test)**: clicked it, nothing happened. `/status` still showed
      `running: true` minutes later, 0% CPU, and — unlike every prior stuck
      case — no Chrome process existed at all, ruling out
      `kill_all_browsers` as a fix (nothing to kill). Root cause: neither AI
      provider SDK (`_openai_compatible.py`'s `OpenAI(...)`, `gemini.py`'s
      `genai.Client(...)`) was ever given an explicit request timeout, so a
      hung AI call blocks for however long the SDK's own default is (the
      OpenAI SDK's is 600s) — and cooperative cancellation (checked
      *between* AI batches) can't interrupt a call already in flight, the
      same class of gap `kill_all_browsers` covers for the browser
      collectors, just with no equivalent "kill the process" option for an
      in-thread HTTP call. Fixed: new `config.AI_REQUEST_TIMEOUT_SECONDS`
      (default 60s) wired into both SDK clients — bounds a single stuck
      call to 60s instead of ~600s+. Residual, honestly-not-fully-solved
      gap: `tenacity`'s retry wrapper means a *genuinely* hung batch can
      still take up to `AI_MAX_RETRIES` × 60s + backoff (~3 min worst case)
      before Cancelar actually takes effect, since cancellation isn't
      checked *between* retry attempts of the same batch — much better than
      before, not instant. 2 new tests verifying the timeout is actually
      passed to each real SDK client constructor (not just fakes, which
      every other provider test injects and which would never have caught
      this) — 378 passed.
- [x] **"Cancelar" is really "Pausar", and Kevin had no way to start clean
      (2026-08-16, Kevin's own framing)**: "Iniciar"/"Reintentar" always
      silently resumed a leftover checkpoint (`resume=True` default, no UI
      path to override it) — the backend already fully supported
      `resume=False` (discards the checkpoint via `_clear_run_artifacts`,
      already used by "Limpiar caché"), it just wasn't reachable except by
      that separate, confirm-dialog-gated button. Fixed: `/status` gained
      `has_checkpoint`; the idle screen now shows "Reanudar búsqueda" (label
      change) + a secondary "Empezar de nuevo (sin retomar)" button when one
      exists, hidden otherwise; the error/paused screen (what "Pausar" now
      correctly says instead of "Cancelar" — matches what it actually does)
      always offers both "Reanudar" and "Empezar de nuevo". `startRun()`
      takes an explicit `resume` param now; fixed 3 call sites
      (`retryBtn`/`sideRerunBtn`/`topRerunBtn`) that passed the click
      `Event` object as `resume` by referencing `startRun` directly as the
      handler — harmless before (any truthy value), but would have silently
      broken now that `resume` is serialized into the request body. 3 new
      tests (`has_checkpoint` true/false, `resume: false` reaches
      `pipeline_run`) — 380 passed. Live-verified `/status`+the idle
      screen's button state against a real server with no checkpoint
      present; **the "Empezar de nuevo" / has-checkpoint-true path itself
      still needs Kevin's own live click to confirm.**
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
