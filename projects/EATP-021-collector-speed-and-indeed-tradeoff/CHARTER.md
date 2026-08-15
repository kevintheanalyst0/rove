# EATP-021 — Collector speed in the full pipeline + Indeed's captcha/tab tradeoff

## Objective
EATP-020 fixed LinkedIn's geo targeting and parallelized LinkedIn/OCC detail-fetching —
each verified 2-4x faster **in isolation**. But Kevin's second real run (2026-08-15,
19:05 min total) showed OCC still taking 283s inside the full pipeline vs. 72.7s
standalone, run back-to-back on the same machine right after. Something specific to
running *inside the real orchestrated pipeline* — not the fixes themselves — is eating
the improvement. This project finds and fixes that, and separately revisits the
Indeed captcha/tab-count tradeoff now that HTTP conversion (Kevin's ask, tested live in
EATP-020) is confirmed not viable (Indeed 403s any non-browser request, even a single
job detail page — unlike LinkedIn's genuinely-public guest endpoint).

## Problems solved
New, seeded directly by EATP-020's closing findings (2026-08-15) — not on the original
P1-P25 list. Extends P13 (run takes too long) and the EATP-006 Indeed speed/risk
tradeoff.

## Diagnosis so far (from EATP-020, don't re-derive — build on this)
- Real numbers from `data/checkpoint.json` (captured live before it cleared at
  persist): `computrabajo 19s/9, greenhouse 39s/43, himalayas 8s/2, indeed 265s/35,
  lever 8s/0, linkedin 294s/91, occ 283s/134, remoteok <1s/0, remotive 10s/13, wwr <1s/1`.
- Collectors run strictly sequentially, one at a time, in `pipeline.py::_collect_stage`
  — never concurrently with each other. So OCC's 283s-vs-73s gap isn't contention
  *during* OCC's own run; something from an *earlier* collector (Indeed runs before
  LinkedIn/OCC in the alphabetical `sorted(requested)` order — confirm this) leaves
  the process/machine in a worse state for everything after it.
- Leading hypothesis (unconfirmed — this project's job to verify or rule out):
  Indeed's DrissionPage/Chromium browser (`collectors/browser.py`) doesn't fully
  release resources after `page.quit()`. EATP-019 already found one instance of
  imperfect Chrome cleanup (`quit()` races Chrome's own clean-exit write, leaving
  stale session-restore files) — plausible there's a live process/thread/CPU leak too,
  not just a file artifact. Needs live process-level observation during a real run to
  confirm (e.g. `ps aux` / thread counts sampled while the pipeline runs), not another
  guess-and-patch.
- Indeed → HTTP-only: **ruled out**, don't re-attempt without new evidence. Both
  `indeed.com/jobs` (search) and `mx.indeed.com/viewjob` (detail, real job id) return
  `403 Forbidden` on a plain `httpx` request with normal browser-like headers — this is
  fingerprint/TLS-level blocking, not a header/cookie gap. Getting past it needs
  TLS-impersonation tooling (`curl_cffi` or similar), a materially bigger and riskier
  scope than this charter — flag to Kevin if he wants to pursue that specifically, don't
  build it speculatively.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `projects/EATP-020-match-quality-and-source-balance/CHECKLIST.md` | Full diagnosis + numbers this charter builds on — read Phase 4-6. |
| `src/career_radar/pipeline.py` | `_collect_stage` — confirms collector run order, where to instrument timing/process checks. |
| `src/career_radar/collectors/browser.py` | Chrome launch/`quit()` — prime suspect for the leak. |
| `src/career_radar/collectors/indeed.py` | Detail-tab pool (`_DETAIL_WORKERS=2`), captcha coordination, `is_captcha_page` markers. |
| `docs/adr/ADR-008-source-health.md` | If timing/health data needs a new field to persist past checkpoint clearing. |

## Dependencies
- **Projects:** EATP-020 (done — this is a direct continuation of its closing findings).
- **Libraries:** none new expected — plan is `ps`/shell process inspection during a
  live-monitored run, not a new profiling dependency. If that proves insufficient and
  `psutil` would genuinely help, ask Kevin first (CLAUDE.md §8) before installing.

## Scope
**In (ordered easiest → hardest, per Kevin's usual preference):**
1. **Persist collector timing past the run** — `checkpoint.json` (which has
   `duration_seconds` per source) gets deleted once a run completes successfully, so
   there's no lasting record to compare runs against. Add per-collector durations to
   `data/health/yields.jsonl` (already persisted, already has a row per source per run)
   or `results.json` so "was this run faster than last time" is answerable without
   catching the checkpoint file mid-run.
2. **Live diagnosis: what's dragging OCC/LinkedIn down inside the full pipeline.**
   Instrument or observe a real run (process list, thread counts, maybe explicit
   before/after timing markers around Indeed specifically) to confirm or rule out the
   Chrome-leftover-resources hypothesis. This is the "flag to Kevin, don't guess-patch"
   phase — needs a real run to watch, same discipline as EATP-019 Phase 6.
3. **Fix whatever's confirmed** (likely: make sure Indeed's Chromium process is fully
   gone before the pipeline moves to the next collector — a stronger wait/verify after
   `page.quit()`, not just calling it and moving on).
4. **Revisit Indeed's tab-count/speed tradeoff** — now that HTTP is off the table,
   is 2 tabs (vs. legacy's 5) still the right call, or does the account-risk math
   change now that Indeed's captcha UX (EATP-020's stuck-banner fix) is better? This is
   a product/risk call — surface it to Kevin, don't just change it.
5. **Live-reverify the captcha-banner fix** — EATP-020 fixed it but no captcha occurred
   in Kevin's second run to confirm live. Confirm the next time one comes up.
6. **`is_captcha_page` false-alarm tightening** — the bare `"captcha"` substring match
   is suspiciously broad (could match an unrelated script/analytics reference on a
   normal page); needs a live false-alarm sample to fix safely, not a blind guess.

**Out:** Indeed → HTTP-only (ruled out this session, would need `curl_cffi`-class
tooling — only revisit if Kevin explicitly wants to fund that risk/effort); anything
already in `ROADMAP.md`'s Backlog.

## Deliverables
- Collector timing persisted somewhere that survives a completed run.
- A confirmed (not guessed) root cause for the pipeline-only OCC/LinkedIn slowdown,
  plus a fix if one exists.
- A decision with Kevin on Indeed's tab count.
- `is_captcha_page` tightened, if a real false-alarm sample becomes available to test
  against; otherwise documented as still open with why.

## Key design decisions & constraints
- Don't patch `is_captcha_page` or the Chrome-cleanup theory without live evidence —
  both are exactly the kind of "confirmed live, not guessed" fix this codebase's own
  history (EATP-019 Phase 6, EATP-020 Phase 2) has repeatedly shown pays off.
- Collectors must stay sequential (`pipeline.py`'s own design, CLAUDE.md golden rule 3
  — memory-safe, resumable) — this project diagnoses inter-collector interference, it
  doesn't propose running collectors concurrently with each other.

## Definition of Done
- [ ] Deliverables above exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left
- [ ] Checklist ticked, time logged
- [ ] ROADMAP status → ✅
- [ ] Session notes written
- [ ] Committed to git (CLAUDE.md §10)

## Estimated time
~1.5-3h — wide range because Phase 2 (live diagnosis) is open-ended until root-caused,
same shape as EATP-019 Phase 6 and EATP-020 Phase 2.

## Open questions for Kevin
- Indeed tab count: once we know what's actually slowing things down, do you want to
  revisit the 2-tab limit, or leave that account-risk call as it is?
