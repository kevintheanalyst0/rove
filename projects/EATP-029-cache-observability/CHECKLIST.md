# EATP-029 — Checklist & time log

## Phases

- [x] **Phase 1 — Read-only view.** `SignatureRecord` gains `title`/`company`/
      `source` (optional, backward-compatible with an old `signatures.jsonl`
      that lacks them). `SignatureCache.update()` accepts and stores them
      (a repost's reworded title refreshes the label; a missing value never
      blanks an existing one). New `records()` accessor, most-recently-seen
      first. `pipeline.py::_persist` passes them through from `scored.job`.
      Backend: `GET /cache`. Frontend: "Ver cacheadas" button in the sidebar,
      reusing the existing job-detail modal shell with different content.
- [x] **Phase 2 — Manual reset.** `SignatureCache.reset()` (in-memory only,
      caller calls `save()`) + `POST /cache/reset` — deliberately separate
      from `/reset` ("Limpiar caché" in the UI, which wipes far more:
      results/raw/history/health). Kevin's call (2026-08-21): keep the
      existing "Limpiar caché" button and its name exactly as it is; the new
      control lives on its own as "Ver cacheadas" with its own reset action
      inside that view, no renaming of the old one.
- [x] **Phase 3 — Diagnostic hookup.** Already free: EATP-028's
      `RunResult.funnel` tallies every gate-rejection reason by source,
      `cached_recently` included — no new code needed, just a new end-to-end
      test (`test_cache_hidden_job_is_tallied_in_the_funnel_by_source`)
      proving it.
- [x] **Phase 4 — Verify.** 30-day window and suppression logic
      (`seen_recently()`) completely untouched — every pre-existing
      `test_cache.py` test still passes unmodified, exactly as the charter's
      Definition of Done required. **395 tests passing** (385 baseline + 10
      net new: 5 cache, 4 server route, 1 pipeline funnel-integration).
- [x] **Phase 5 — Close.** Updated `ROADMAP.md`, `CHANGELOG.md`,
      `DATA-CONTRACTS.md` (cache file shape), `ADR-001` (additive-only update
      note). Committed.

## Time log

| Date | Phase(s) | Time |
|------|----------|------|
| 2026-08-21 | 1-5 (full project, single session) | ~40 min |

**Total: ~40 min**

## Session notes

Found mid-design that the existing "Limpiar caché" button (EATP-019) is
actually a full wipe (results/raw/history/health), not a signature-cache
reset — a real naming collision with what this project needed to build.
Asked Kevin directly rather than guessing; his call was to leave "Limpiar
caché" exactly as it is and add "Ver cacheadas" as its own separate control.
The funnel-diagnostic deliverable turned out to need zero new code — EATP-028
already tallies `cached_recently` by source, so this phase was purely a
verification test. 395 tests passing. All four Notion backlog projects
(EATP-027 through 030) are now done except **EATP-030** (new LatAm sources) —
next recommended.
