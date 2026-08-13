# EATP-019 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Chrome full-screen for manual intervention
- [x] `browser.py`: launch maximized instead of a small randomized viewport
- [x] Verify: launched a real (headful) page, confirmed `window_state == "maximized"`

### Phase 2 — Self-serve launcher (no Claude Code needed)
- [x] Windows-side double-click scripts — **two**, mirroring legacy (Kevin's feedback):
      `Career Radar - Ejecutar busqueda.bat` (auto-starts a full run) and
      `Career Radar - Ver resultados.bat` (opens the dashboard only, no new run).
      Both reuse `scripts/run_web.sh` from EATP-015; added `CAREER_RADAR_AUTOSTART=1`
      env var to it that POSTs `/run` once the server's up, before opening the browser.
- [x] Short doc note in README (both `.bat`s as the primary path, manual steps kept as fallback)
- [x] Verified: autostart POST confirmed via `/status` (`running: true`); noticed
      `run_web.sh`'s trap doesn't always kill uvicorn promptly if a browser tab is still
      holding an open `/events` SSE connection when the window closes — pre-existing
      EATP-015 behavior, not introduced here, not fixed (Kevin didn't ask for it and it's
      not silent data loss, just a slower-than-instant shutdown in that specific case) —
      noted here for later if it becomes an actual complaint.

### Phase 3 — "Limpiar caché" button
- [x] `pipeline.reset_all_run_data()` — wipes checkpoint/gated/AI-checkpoint/raw/
      results/status/signature-cache/history/health; leaves tracking.jsonl,
      eval/, and the browser profile alone (Kevin's call: keep Chrome session)
- [x] `POST /reset` endpoint (409 while a run is active, mirrors `/run`'s guard)
- [x] UI: small "Limpiar caché" link — one next to "Iniciar búsqueda" (idle state),
      one in the sidebar under "Buscar de nuevo" (results state) since idle is only
      ever shown before the very first run
- [x] Tests: `pipeline.reset_all_run_data` (real files, tmp-path isolated) +
      `/reset` route (injected fake, both the ok and 409-while-running paths)
- [x] Verified live: confirm() dialog text correct, dismissed without wiping real data

### Phase 4 — Indeed session persistence
- [x] Confirmed shared browser profile covers Indeed the same way it does LinkedIn:
      inspected `data/browser_profile/Default/Cookies` directly — 16+ cookies already
      persisted on `.indeed.com` across runs, same mechanism as LinkedIn's 19 on
      `.linkedin.com`. No code change needed; `use_profile=True` already does this
      for both collectors.
- [x] Told Kevin: unlike LinkedIn, Indeed's collector never requires login to work
      (browses public search results) — being signed in is optional/best-effort on
      his end, not something the code can do for him (needs his credentials). Offered
      to open the (now-maximized) browser window so he can log in whenever he wants.

### Phase 5 — Indeed: multiple captchas per run
- [ ] Fix `_CaptchaCoordination` to reset after each resolved captcha
- [ ] Test: two captchas in one `collect()` call both get their own wait+notification

### Phase 6 — LinkedIn returning zero
- [ ] Add diagnostics distinguishing block/DOM-drift from genuine zero-results
- [ ] Root-cause (may need a live supervised run)
- [ ] Fix

### Phase 7 — Verify & close
- [ ] `pytest` green
- [ ] Update ROADMAP status + total time
- [ ] Write session notes below
- [ ] Commit to git (CLAUDE.md §10)

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
|  |  |  |  |

**Total project time:** _tbd_

## Session notes
<3–6 lines: what was built, key decisions, anything the next project should know.>
