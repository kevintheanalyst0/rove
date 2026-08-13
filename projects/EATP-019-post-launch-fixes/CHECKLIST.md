# EATP-019 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Chrome full-screen for manual intervention
- [x] `browser.py`: launch maximized instead of a small randomized viewport
- [x] Verify: launched a real (headful) page, confirmed `window_state == "maximized"`

### Phase 2 — Self-serve launcher (no Claude Code needed)
- [ ] Windows-side double-click script (calls into WSL, starts the server, opens the browser)
- [ ] Short doc note in README

### Phase 3 — "Limpiar caché" button
- [ ] `POST /reset` endpoint (refuses while a run is active)
- [ ] UI button next to "Iniciar búsqueda"
- [ ] Tests

### Phase 4 — Indeed session persistence
- [ ] Confirm shared browser profile covers Indeed the same way it does LinkedIn
- [ ] Tell Kevin what (if anything) he needs to do manually

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
