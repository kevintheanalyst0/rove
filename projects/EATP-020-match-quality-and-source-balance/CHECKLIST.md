# EATP-020 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Launcher UX (no silent autostart)
- [x] Resolved with Kevin: one launcher, 3-button landing screen (Iniciar
      búsqueda / Limpiar caché / Ver dashboard de la última corrida)
- [x] `Career Radar.bat` (single file, replaces the two old ones + their
      `.ico`s, all removed); `run_web.sh` autostart branch deleted
- [x] `index.html`: added `viewLastBtn` (hidden by default) next to
      `startBtn`/`clearCacheBtn` on the idle screen
- [x] `app.js`: `init()` no longer auto-jumps into `results`/`error` — always
      lands on `idle` (except a genuinely in-progress run, still resumed into
      `working`); shows `viewLastBtn` only when a prior successful run exists;
      wired its click to the existing `revealResults()`
- [x] README updated (single launcher, no more per-icon instructions)
- [x] `pytest` green (326 passed, no test depended on the old behavior)
- [x] Verified live with Playwright/Chromium against the real server + real
      `data/results.json`: lands on idle, `viewLastBtn` visible (prior run
      exists), click reveals the real dashboard (43 jobs; only 4 shown by
      default because Kevin had already dismissed 39 of them from his actual
      run — confirms tracking/filters still work, not a bug), reload lands
      back on idle. Zero console/page errors.

### Phase 2 — LinkedIn geo targeting + listing speed (merged, Kevin's call 2026-08-14)
- [x] Live investigation: `location=México` (free text) confirmed silently
      ignored for `f_WT=2` results (returned Miami/Texas/DC jobs). Tested
      `geoId=103323778` — live-verified 15/15 sampled jobs are real Mexico
      locations. **Site-side fix worked — no downstream filter needed.**
- [x] Wired `geoId=103323778` into `linkedin.py::build_search_url()`
- [x] Parallelized `_collect_term_ids` across search terms
      (`_MAX_TERM_WORKERS=3`, mirrors `fetch_job_details`'s worker pool);
      merge stays deterministic (grouped by term, not completion order)
- [x] 2 new tests (`geoId` present/no free-text `location`, multi-term merge
      order under concurrency) — 328 passed
- [x] Live full-run verification (real network, all 9 search terms): 534.6s
      total vs. ~459s EATP-019 measured for just 3 terms sequentially
      (~23 min extrapolated to 9) — **>2x speedup**. 134 jobs (down from
      321 pre-fix on Kevin's real run), overwhelmingly real Mexico cities.

### Phase 3 — Source rebalance (lever, remoteok, weak sources)
- [x] Diagnosed live: `lever` — Palantir has 300+ open postings but zero in
      Data/BI/Business Analyst right now (genuinely empty for our terms, not
      blocked); Clari's board is empty. Probed ~20 other well-known
      companies for Lever boards, all 404 (moved off Lever) — confirms
      Lever's ecosystem has genuinely shrunk, not worth chasing further.
      `remoteok` — API responds fine (not blocked); its "~100 most recent"
      feed has drifted to mostly non-tech gig postings (sampled titles:
      "Gardener Handyman Driver", "Room Attendant") — zero matches is the
      client-side filter working correctly on low-relevance input, not a bug.
- [x] Grown: `config.ATS_COMPANIES["greenhouse"]` +7 companies (instacart,
      affirm, brex, lyft, doximity, chime, flexport) — each live-verified to
      currently have open Data/BI/Business Analyst titles on its public board.
- [x] Documented both dead ends with evidence in `lever.py`'s config comment
      and `remoteok.py`'s module docstring, for the next session.
- [x] `pytest` green (328 passed) after the config change

### Phase 3.5 — Dashboard cleanup (Kevin's mid-session feedback, 2026-08-14)
- [x] Removed "Solo remoto" checkbox — confirmed dead code: every job that
      reaches the dashboard already passed the remote hard-gate
      (`quality/filters.py`), so `remote_status` is always `"remote"` and
      the toggle could never filter anything out.
- [x] Kept "Ocultar descartadas" — confirmed it works correctly (live-tested).
- [x] D-grade jobs now hidden by default in the results grid (still fully
      accessible — pick "D" from the grade dropdown to see them); by
      definition a "bad match" grade, not worth cluttering the default view.
- [x] `pytest` green (328 passed); live-verified with Playwright against
      real `data/results.json`: no D visible by default (with or without
      dismissed shown), all 33 D's appear when "D" is explicitly selected,
      zero console errors, `#remoteOnlyToggle` confirmed gone from the DOM.

### Phase 4 — Kevin's real verification run (2026-08-14/15, double-clicked `Career Radar.bat`)
Real run: 20.2 min total, 475 collected, 20 final. Greenhouse jumped 14→43
(the +7 companies worked). New findings from this run, triaged live:
- [x] **OCC 6 min vs. legacy's 1.5 min** — real bug, fixed (see Phase 5 below).
- [x] **Indeed captcha banner stuck on screen** — real bug, fixed (Phase 5).
- [x] **False captcha alarms** — same as legacy's own behavior (Kevin
      confirmed); root cause is likely `is_captcha_page`'s bare `"captcha"`
      substring match being too broad, but fixing detection blind (no live
      captcha sample to verify against) risks guessing wrong — deferred to
      EATP-021 with a live-verified diagnosis, same discipline as EATP-019
      Phase 6. The stuck-banner fix means a false alarm now self-clears
      within ~10s instead of staying stuck, which covers most of the pain.
- [x] **Tabs refreshing during captcha wait** — confirmed this is the
      intended passive poll (every 10s), not a bug — told Kevin.
- [x] **Solving the captcha in one tab was enough** — confirmed this is
      correct by design (Indeed's block is session/IP-wide, not per-tab).
- [x] **LinkedIn "still slow"** — the Phase 2 fix measured >2x faster in
      isolation; in the full pipeline it's competing with Indeed/captcha
      wait time for wall-clock attention. Deferred final re-measurement to
      Kevin's next full verification run (post-fixes).
- [ ] **Indeed's own base speed / tab-count tradeoff** — deliberate
      account-risk decision from EATP-006 (2 tabs, not legacy's 5) — out of
      this charter's scope, revisit in EATP-021 alongside the captcha fixes.

### Phase 5 — OCC speed + Indeed captcha-banner fix (Kevin's call, added mid-session)
- [x] `occ.py`: moved `gentle_pause()` into `_fetch_job` (per-request, kept),
      parallelized detail-fetch across `_DETAIL_WORKERS=5` (no login/session
      risk on OCC, safe to run more concurrent than Indeed's browser tabs)
- [x] Live-verified: 79.0s for 134 jobs (was ~6 min) — faster than legacy's
      own ~1.5 min benchmark
- [x] `browser.py`: new `clear_manual_intervention(source)` — publishes a
      paired `intervention_resolved` event on the same `collect:{source}`
      phase
- [x] `indeed.py`: calls it the moment `_wait_for_captcha_resolution` detects
      the block is actually gone (in addition to the existing `coord.resolved()`)
- [x] `app.js`: `handleEvent()` now clears that specific phase's notice on
      `intervention_resolved` instead of only at the next pipeline phase
- [x] Tests: `test_browser.py` (event shape), `test_collector_indeed.py`
      (resolved event follows needs_intervention) — 329 passed

### Phase 6 — Kevin's second real run + close
Second real run (2026-08-15, post OCC/captcha fixes), timed precisely via
`data/checkpoint.json` before it got cleared at persist: 19:05 total,
328 collected, 46 final. Per-collector: computrabajo 19s/9, greenhouse
39s/43, himalayas 8s/2, **indeed 265s/35**, lever 8s/0, **linkedin 294s/91**,
**occ 283s/134**, remoteok <1s/0, remotive 10s/13, wwr <1s/1.
- [x] Kevin's report on this run: OCC/LinkedIn/Indeed all still felt slow —
      re-ran OCC in isolation right after (72.7s, consistent with Phase 5's
      79.0s) — **the parallelization fix is real and still works standalone,
      but something inside the full pipeline run drags OCC back down to
      283s (3.9x slower than isolated).** Not a regression in this
      project's fixes — a new mystery, seeded as EATP-021 Phase 1
      (hypothesis: Indeed's browser leaves something running that starves
      later collectors of CPU — needs live process-level diagnosis to
      confirm, out of this charter's scope).
- [x] Investigated Kevin's direct ask — converting Indeed to HTTP-only like
      LinkedIn (EATP-019): **tested live, not viable.** Both the search page
      and a real job's detail page return `403 Forbidden` on a plain HTTP
      request (no browser) — unlike LinkedIn's genuinely-public guest
      endpoint, Indeed blocks at the fingerprint/TLS level regardless of
      URL. Getting past that needs TLS-fingerprint spoofing (e.g.
      `curl_cffi`), a materially bigger and riskier effort than this
      charter's scope — logged as a real (negative) finding for EATP-021,
      not re-attempted blind.
- [x] Captcha banner fix: no captcha occurred on this run to re-trigger it
      live: Kevin didn't report it sticking again, but that's the absence of
      a report, not a confirmed re-test — flagged for EATP-021 to verify
      live if a captcha comes up.
- [x] `pytest` green (329 passed, no changes since Phase 5)
- [x] ROADMAP status → ✅
- [x] Session notes written below
- [x] Committed to git (CLAUDE.md §10)

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-14 | Phase 1 | ~25 min | One launcher, 3-button landing screen, no auto-jump/autostart. |
| 2026-08-14 | Phase 2 | ~50 min | `geoId` fix (live-verified) + parallel listing; >2x faster, real Mexico jobs only. |
| 2026-08-14 | Phase 3 | ~25 min | Grew Greenhouse +7 companies (live-verified); documented lever/remoteok as genuinely low-yield. |
| 2026-08-14/15 | Phase 4 (Kevin's run + triage) | ~20 min | Real run surfaced OCC/captcha-banner bugs + confirmed 2 non-bugs; scoped fixes vs. EATP-021. |
| 2026-08-15 | Phase 5 | ~30 min | OCC parallelized (79s, was ~6min); captcha-resolved event fixes stuck banner. |
| 2026-08-15 | Phase 6 | ~25 min | Kevin's 2nd run timed exactly; found pipeline-only OCC slowdown; Indeed→HTTP tested live, not viable; closed project. |

**Total project time:** ~2h55min

## Session notes
Fixed what the real-run data actually showed: LinkedIn's geo targeting was
silently broken (fixed with the right `geoId`, not a new filter — Kevin's
call), LinkedIn+OCC were slow from unparalleled detail-fetching (fixed,
each verified >2-4x faster in isolation), Greenhouse grew from 12→19
companies (14→43 jobs live), and a real captcha-banner bug (never told the
UI when it actually resolved). Two dashboard dead-weight items also went:
"Solo remoto" (provably always-true, removed) and D-grade jobs now hidden
by default. The open thread for next time: OCC/LinkedIn are fast alone but
slow inside the full pipeline (283s vs 73s for OCC) — likely Indeed's
browser starving later collectors of resources, unconfirmed. Converting
Indeed to HTTP-only (Kevin's ask, to dodge this and the captcha entirely)
was tested live and isn't viable — Indeed 403s any non-browser request,
unlike LinkedIn's genuinely-public guest endpoint. Both seed EATP-021.
