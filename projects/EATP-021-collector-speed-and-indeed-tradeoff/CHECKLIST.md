# EATP-021 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Persist collector timing past the run
- [x] `health/check.py`: `_YieldEntry` + `record_yields()` now carry
      `duration_seconds` (already computed by `CollectorResult`, just wasn't
      persisted) — `data/health/yields.jsonl` survives a completed run,
      unlike `checkpoint.json`
- [x] Test: `test_record_yields_persists_duration_seconds`
- [x] Verified live: real run's `yields.jsonl` rows do carry real durations

### Phase 2 — Live diagnosis: pipeline-only OCC/LinkedIn slowdown
- [x] Ran a real full pipeline live (real AI eval), sampling processes/load
      every 5s throughout via a background script
- [x] Confirmed a zombie Chrome process from Indeed does linger after
      `page.quit()` — but it's defunct (near-zero resources); system load
      stayed at 0.03-0.24 the entire run
- [x] **OCC did NOT reproduce the slowdown this run**: 85.1s running right
      after Indeed inside the full pipeline — matches isolated benchmarks
      (72-79s). Kevin's original ~283s observation didn't recur under the
      same architecture — most likely OCC's own site having a slow moment
      that one time, not a systemic bug in this codebase. **Root cause: not
      confirmed as a real, reproducible issue — didn't force a fix onto
      something I couldn't reproduce.**
- [x] What IS consistently real: LinkedIn (~5-9 min) and Indeed (~4-6.5 min,
      more with a captcha) are the two genuine time sinks, together ~80-85%
      of total pipeline wall-clock time across both live runs measured.

### Phase 3 — (folded into Phase 2's conclusion — no separate fix needed)
- [x] No confirmed, reproducible cause to fix for OCC/LinkedIn pipeline
      slowdown beyond normal site-side variance — closing this phase as
      "investigated, not reproduced" rather than guessing a patch.

### Phase 4 — Concurrency bump (Kevin's call: "sube ambos")
- [x] LinkedIn: tried `_MAX_TERM_WORKERS`/`linkedin_api._MAX_WORKERS` 3->5.
      **Live A/B, same moment**: workers=5 → 92.2s but only **14 jobs**;
      workers=3 → 316.5s but **42 jobs**. More concurrent search-term
      requests trigger LinkedIn's rate limiting, and `_collect_term_ids`
      can't distinguish "genuinely out of results" from "this request got
      rate-limited" — both stop the term silently. **Reverted to 3/3** —
      confirmed silent data loss, not worth the speed.
- [x] Indeed: `_DETAIL_WORKERS` 2->3 — matches legacy's own proven tab count
      exactly (not beyond it). Captcha exposure doesn't scale with tab count
      (block is session/IP-wide, confirmed in EATP-019/020). Not live-load-
      tested at the same rigor as LinkedIn (real logged-in browser session,
      didn't want to spend more live captcha exposure just to benchmark) —
      **verify on Kevin's next real run.**
- [x] `pytest` green (330 passed) after both changes

### Phase 5 — Captcha follow-ups
- [x] Live-reverified the EATP-020 stuck-banner fix: a real captcha hit
      during Phase 2's live run, resolved itself, and the `intervention_resolved`
      event fired correctly (twice) — banner did not stay stuck. Confirmed
      working, not just unit-tested.
- [ ] `is_captcha_page` false-alarm tightening — no false-alarm sample
      surfaced this session to test against; left open for next time one
      occurs.

### Phase 6 — Verify & close
- [x] `pytest` green
- [ ] Update ROADMAP status + total time
- [ ] Write session notes below
- [ ] Commit to git (CLAUDE.md §10)

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-15 | Phase 1 | ~15 min | Timing now persisted in `yields.jsonl`, survives past checkpoint clearing. |
| 2026-08-15 | Phase 2 | ~20 min | Live-monitored a real run; OCC's slowdown didn't reproduce; LinkedIn+Indeed confirmed the real time sinks. |
| 2026-08-15 | Phase 4 | ~20 min | LinkedIn concurrency bump live-A/B'd and reverted (silent data loss); Indeed bumped to legacy's own tab count. |
| 2026-08-15 | Phase 5 + 6 | ~10 min | Captcha-banner fix confirmed live; closed project. |

**Total project time:** ~1h05min

## Session notes
Persisted per-collector timing so it survives a completed run (was only ever
in `checkpoint.json`, deleted on success). Live-diagnosed the OCC "slow
inside the pipeline" complaint with real process/load monitoring during a
full run — it didn't reproduce (85s, same as isolated), and a lingering
Chrome zombie from Indeed turned out to be resource-free, so no fix was
forced onto an unconfirmed cause. What IS real: LinkedIn and Indeed together
eat ~80%+ of total run time. Tried raising LinkedIn's concurrency 3->5 per
Kevin's request — live A/B proved it silently drops ~66% of real vacancies
(rate-limiting mistaken for "no more results"), so reverted. Indeed's detail
tabs went 2->3, matching legacy's own proven count exactly — not live-load-
tested as hard (real logged-in session) so it's flagged for Kevin's next
real run to confirm. Bonus: the EATP-020 captcha-banner fix got a real live
test (an actual captcha hit mid-run) and worked correctly. Open for next
time: `is_captcha_page`'s false-alarm tightening still has no real sample to
test against — don't guess-patch it, wait for one.
