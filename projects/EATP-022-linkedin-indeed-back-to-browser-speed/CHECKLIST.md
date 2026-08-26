# EATP-022 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — LinkedIn: real-browser listing
- [x] Ported scrolling/card-extraction logic from `legacy/jobmatch/collectors/linkedin.py`
      (`_expand_results_panel`, `data-occludable-job-id` extraction), adapted
      to current conventions (no inline gating, event-based not blocking)
- [x] Multi-tab search across terms (`_SEARCH_WORKERS=4`, legacy's own proven
      count), worker-per-tab pulling terms off a shared queue
- [x] Non-blocking login-wall handling (`_LoginCoordination`, same shape as
      `indeed.py`'s `_CaptchaCoordination` — shared deadline, one event per
      episode, paired `intervention_resolved` on resolve)
- [x] Detail-fetch stays on the guest HTTP endpoint (`linkedin_api.py`, untouched)
- [x] `BROWSER_SOURCES` updated (`linkedin` back in, `fast` mode skips it again)
- [x] Full test rewrite (22 tests, scripted fake page/tabs, no live network) — 336 passed
- [x] Live-verified 3x (real network + browser): 61.1s/23 jobs (headless),
      65.8s/23 jobs (headful, matches production), 164.8s/69 jobs — all far
      under the old guest-endpoint's 534-580s. Geo accuracy: 6/69 (8.7%)
      U.S.-signal rate, better than legacy's own 14%, locations overwhelmingly
      real Mexican cities/regions.
- [x] One false alarm mid-testing: killed a headful run early on a false read
      of "the browser window closed" — turned out it had already finished
      successfully (65.8s) faster than I was watching for. Noted so it
      doesn't get mistaken for a real bug later.

### Phase 2 — Indeed: tab count + pacing
- [x] Parallelized search-id collection across 2 tabs (`_SEARCH_WORKERS=2`,
      legacy's own proven count) — `_collect_all_term_ids`, same
      worker-per-tab-pulling-a-shared-queue shape as `_fetch_details`
- [x] Tuned detail-page navigation pause 1.5-4.0s -> 0.3-0.8s
      (`_navigate`'s new `pause_range` param) — search pages kept the
      longer default since they have no dedicated content-ready wait the
      way `_wait_for_detail_content` already gives detail pages
- [x] Tests updated (none broke — existing tests already patch
      `browser.human_pause` to a no-op) — 336 passed throughout
- [x] Live-verified twice against real Indeed: 233.6s/29 jobs (search
      parallelism only) -> 102.9s/29 jobs (+ pacing change) — **same exact
      29 jobs both times** (identical titles/companies), zero evidence of
      under-collection, unlike EATP-021's LinkedIn concurrency attempt

### Phase 3 — Verify & close
- [x] `pytest` green (336 passed)
- [ ] Update ROADMAP status + total time
- [ ] Write session notes below
- [ ] Commit to git (CLAUDE.md §10)

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-15 | Phase 1 | ~50 min | LinkedIn back to real-browser listing (classic UI un-broke itself); 8-9x faster, better geo than legacy. |
| 2026-08-15 | Phase 2 | ~30 min | Indeed: 2 search tabs + tuned detail pacing; >2x faster, verified zero data loss. |
| 2026-08-15 | Phase 3 | ~10 min | Closed project. |

**Total project time:** ~1h30min

## Session notes
Kevin ran the original legacy project directly and proved LinkedIn's
real-browser scraping still worked (28 fresh jobs in ~5 min alongside 2
other sources), directly contradicting EATP-019's finding that LinkedIn's
UI redesign broke scraping — turns out that redesign got reverted (or was a
temporary A/B test) sometime after 2026-08-13, and nobody re-checked before
building EATP-019/020/021's whole guest-HTTP-endpoint workaround on top of
a stale finding. Live-confirmed with rove's own existing isolated
profile (no need for Kevin's personal Chrome, no new account risk) —
reverted LinkedIn's listing back to real-browser search, kept detail-fetch
on the safe anonymous guest endpoint. Result: 8-9x faster than the guest
endpoint (61-165s vs. 534-580s) and better geo accuracy than even legacy's
own numbers. Indeed got the same treatment more conservatively: 2 search
tabs (was 1) plus a tuned, evidence-verified pacing cut for detail pages
only (search pages kept the safer default) — 233.6s -> 102.9s, verified
with the exact same job set both times, not just a faster wall-clock. One
false alarm along the way: killed a headful LinkedIn test early on a
mistaken read that it had hung — it had actually already finished
successfully, just faster than expected. Lesson for next time: trust the
process-alive check over a visual "did the window close" read.
