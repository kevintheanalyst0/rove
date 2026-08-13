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
      He logged in successfully.
- [x] **Extra, Kevin's own report mid-phase**: stray tabs (e.g. a leftover LinkedIn
      tab) staying open during a later collector's run, across runs too. Root-caused:
      `data/browser_profile/Default/Preferences` was stuck at `exit_type: "Crashed"`
      because `ChromiumPage.quit()` force-kills the process right after asking it to
      close, racing Chrome's own "clean exit" write — so Chrome's crash-recovery
      restores old tabs on every subsequent launch. Fix: `browser.py` now deletes
      `Default/Sessions/*` (the tab-restore snapshot only — cookies/login data
      untouched) before every profile-based launch. 3 new unit tests
      (`tests/test_browser.py`, no real Chromium needed).

### Phase 5 — Indeed: multiple captchas per run
- [x] Fix `_CaptchaCoordination`: added `resolved()`, called once a captcha clears,
      resetting `_deadline` to `None` so the next occurrence gets its own fresh
      `_CAPTCHA_WAIT_SECONDS` window + its own notification instead of silently
      reusing the first captcha's already-spent deadline
- [x] Test: `test_collect_notifies_separately_for_a_second_captcha_later_in_the_run` —
      two captcha episodes across two search terms, asserts exactly 2 "resuélvela"
      notifications (not 1) and both jobs still collected. Verified the test actually
      catches the bug: reverted the fix locally, test failed (1 == 2), restored, green.

### Phase 6 — LinkedIn returning zero
- [x] Reviewed `legacy/jobmatch/collectors/linkedin.py` per Kevin's own recollection:
      4 parallel tabs + global-pause coordination on rate-limit (kept OUT — the
      current single-tab design is a deliberate account-safety improvement, not a
      regression, per EATP-005's own docstring) + retry-once patterns worth keeping:
      missing results panel got one retry after 10s, a 429/health-error got the
      whole fleet paused ~40s then retried once.
- [x] Ported the retry-once *behavior* (not the 4-tab machinery) into the current
      single-sequential-tab `linkedin.py`: missing results panel now retries once
      after 10s; an unhealthy/rate-limited page now retries once after 40s before
      giving up and notifying Kevin. 2 new tests, both verified to fail without the
      fix (reverted locally, confirmed red, restored, confirmed green).
- [x] Root-caused via a live, AI-quota-free smoke test (real browser, Kevin's
      profile): LinkedIn now redirects `/jobs/search/` → `/jobs/search-results/`,
      **silently drops** our `f_WT=2`/`f_JT=F` (remote/full-time) query params and
      substitutes unrelated ones, and renders results through a new "AI job search"
      UI (LinkedIn's own banner: "Ahora usas la búsqueda de empleo con IA... algunos
      filtros ya no estén disponibles"). The page genuinely has real results (saw
      "99 resultados", real Data Analyst/BI listings, all México/remote) — this is
      **not** a block, not a captcha, not genuinely-zero. It's that the new UI has
      no stable scraping hooks left: no `data-occludable-job-id`, no `jobs/view`
      hrefs, only build-hashed CSS classes (`_796307fd` etc.) that change per
      deployment. DOM scraping this new UI reliably is a real rewrite, not a
      selector tweak — confirmed DrissionPage has a `page.listen` network-
      interception API that could grab the underlying API response instead of
      scraping the DOM, but that's a different, bigger architecture than what this
      phase scoped. **Stopped here to ask Kevin how he wants to prioritize this**
      rather than silently starting a large rewrite.
- [x] **Kevin's call: fix it properly, now.** Tried network-interception of the new
      "AI search" UI's React-Server-Components action first (`page.listen` on
      `jobSearchUpdateRequestAction`) — the endpoint exists but streams a response
      DrissionPage couldn't reliably capture a body for; treated as a dead end rather
      than sinking more time into it.
      Found a much better path instead: LinkedIn's public **guest** search endpoint
      (`jobs-guest/jobs/api/seeMoreJobPostings/search`) — the same stable, logged-out
      surface `linkedin_api.py` already uses for job *details* — still serves classic
      server-rendered HTML with `data-entity-urn="urn:li:jobPosting:<id>"` on every
      card, completely unaffected by the new UI. Verified live: `f_TPR`/`f_WT`/`f_JT`/
      `location`/`start` all still work as real filters, pagination has no overlap
      between pages, page size is 10 (not the old UI's 25).
      **Rewrote `linkedin.py` to be HTTP-only** (no browser at all): listing now uses
      this guest endpoint via `collectors/http.py`'s shared client/retry/pacing
      (same pattern as OCC/Computrabajo/Lever), detail-fetch unchanged
      (`linkedin_api.py` was never broken). Removed from `BROWSER_SOURCES` — LinkedIn
      no longer carries any account-ban/login-wall/captcha risk at all, and now
      qualifies for `mode='fast'` too. Fully rewrote `tests/test_collector_linkedin.py`
      (mocked httpx transport, same pattern as `test_collector_computrabajo.py`) and
      fixed `test_pipeline.py::test_fast_mode_never_touches_browser_sources` (now
      exercises `indeed`, the only remaining browser source; asserts LinkedIn *is*
      included in fast mode). `pytest`: 326 passed.
- [x] **Live end-to-end verification (real network, no AI, no browser)**: 3 real
      search terms -> **138 real jobs** collected (vs. 0 before), full titles/
      companies/real descriptions (1.4k-10.7k chars each). ~459s total for 3 terms +
      full detail fetch of 138 jobs — detail-fetch pacing unchanged from before, not
      a regression.

### Phase 7 — Verify & close
- [x] `pytest` green (326 passed)
- [x] Update ROADMAP status + total time
- [x] Write session notes below
- [x] Commit to git (CLAUDE.md §10)

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-13 | Phase 1 | ~10 min | Chrome maximized on every headful launch. |
| 2026-08-13 | Phase 2 | ~20 min | Two `.bat` launchers (Kevin's feedback: split into two, mirroring legacy). |
| 2026-08-13 | Phase 3 | ~35 min | `/reset` + "Limpiar caché" button, keeps browser session/tracking/eval. |
| 2026-08-13 | Phase 4 | ~15 min | Indeed session persistence confirmed (no code change); Kevin logged in. |
| 2026-08-13 | Phase 4 extra | ~20 min | Stray-tabs-across-runs bug found by Kevin; fixed (clear Sessions/ snapshot). |
| 2026-08-13 | Phase 5 | ~30 min | Indeed multi-captcha bug fixed + regression test. |
| 2026-08-13 | Phase 6 (diagnose) | ~45 min | Legacy review + retry-once port + live root-cause of LinkedIn's zero. |
| 2026-08-13 | Phase 6 (fix) | ~75 min | RSC interception dead-end, guest-endpoint discovery, full HTTP-only rewrite, live verification (138 jobs). |

**Total project time:** ~4h10min

## Session notes
Six fixes/features Kevin asked for after using the published product for the first
time, done easiest-to-hardest as he requested. Two were real bugs (Indeed's captcha
coordinator only ever notified once per run; Chrome's crash-recovery was restoring
stale tabs across every collector run because `quit()` races Chrome's own clean-exit
write). One was pure usability (maximized Chrome, two single-purpose `.bat`
launchers, a cache-reset button that deliberately leaves login/tracking/eval data
alone). The big one: LinkedIn was returning zero because the site shipped a new
authenticated "AI job search" UI with no stable scraping hooks — diagnosed live
(not a captcha/block/genuine-zero), then fixed by moving the whole collector onto
LinkedIn's public guest search endpoint (same stable surface `linkedin_api.py`
already used for details), which also means LinkedIn no longer touches a browser at
all — no more login wall, captcha, or account-ban risk on that source, and it now
qualifies for `mode='fast'`. Live-verified: 138 real jobs vs. 0 before.
