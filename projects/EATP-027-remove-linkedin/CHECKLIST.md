# EATP-027 — Checklist & time log

## Phases

- [x] **Phase 1 — Core removal.** Delete `linkedin.py`, `linkedin_api.py`, their
      tests, and their fixture. Remove `linkedin` from the collector registry and
      `BROWSER_SOURCES` in `collectors/__init__.py`.
- [x] **Phase 2 — Shared-file cleanup.** Reworded LinkedIn mentions in
      `browser.py` (7 spots), `indeed.py` (4 spots), `occ.py`, `pipeline.py`,
      `config.py` docstring example — logic untouched throughout.
- [x] **Phase 3 — UI.** Removed the `linkedin` entry from `app.js`'s source map
      and its unused `icons/linkedin.svg` asset; generalized the
      login-blocking comment to Indeed's captcha.
- [x] **Phase 4 — Tests.** Swapped the arbitrary `"linkedin"` source label to
      real remaining sources in `test_collector_framework.py`, `test_dedup.py`,
      `test_models.py` (these never functionally depended on the LinkedIn
      module — just used its name as a placeholder string). Simplified
      `test_pipeline.py`'s browser-sources test to just Indeed (the one
      remaining `BROWSER_SOURCES` entry). **Judgment call:** left
      `tests/fixtures/latest_jobs.json` and `test_filters.py` untouched —
      that fixture is 30 real historical postings used to test the quality
      gate's text-based classification end-to-end (ADR-002); it doesn't
      exercise the LinkedIn collector, "source" is just a data label on real
      jobs, and trimming/regenerating it would risk losing genuine edge
      cases it was curated for. Full `pytest`: **377 passed**.
- [x] **Phase 5 — Docs.** Updated README + all 6 governance docs (ARCHITECTURE,
      AUTOMATION, DATA-CONTRACTS, DEPENDENCIES, SCRAPING-GOTCHAS, SEARCH-STRATEGY)
      + ADR-001 + `pyproject.toml` comment so none describe LinkedIn as active.
      General lessons in SCRAPING-GOTCHAS.md (recommendation-card padding,
      rate-limit coordination, silent-profile-degradation, fraud/ghost companies)
      were kept and reattributed rather than deleted — still relevant to Indeed
      and future collectors (EATP-030). Appended `CHANGELOG.md` entry.
- [x] **Phase 6 — Data purge.** Checked the actual schemas before touching
      anything: `data/cache/signatures.jsonl` (the content-signature cache,
      ADR-001) and `data/tracking.jsonl` (Apliqué/No me interesa) have **no
      `source` field at all** — they're keyed purely by content signature,
      by design (cross-source dedup), so there is nothing to filter there;
      left both untouched. `data/history/*.jsonl` does have a `source` field
      but these are dated historical run records (what was actually shown to
      Kevin on 2026-08-18/20/21) — treated the same as CHANGELOG/ROADMAP
      history and left alone; `history/store.py`'s `source` field is a plain
      `str` with no validation, so old `"linkedin"` entries are inert, not a
      bug. Deleted `data/raw/linkedin.jsonl` (transient last-scrape output,
      the only piece that was actually dead weight).
- [x] **Phase 7 — Verify & close.** Skipped a live full-pipeline run (would
      spend real network/AI quota without Kevin's in-session go-ahead per
      CLAUDE.md §7) — verified instead via `build_registry()` (9 sources, no
      `linkedin`), `BROWSER_SOURCES == {"indeed"}`, and the full test suite:
      **377 passed**. `grep -ri linkedin` sweep clean outside `legacy/` and
      historical EATP project folders (only intentional historical
      annotations remain, e.g. "removed in EATP-027"). **Incidental finding,
      out of scope:** `tests/test_collector_occ.py::test_collect_stops_...`
      fails when run in isolation (`pytest path::test_name`) but passes
      reliably as part of its file or the full suite — a pre-existing
      test-isolation quirk (likely relies on ordering/an autouse fixture
      elsewhere in the file), unrelated to this project since neither
      `occ.py`'s logic nor this test file were touched here. Flagged to
      Kevin, not fixed in this session. Update `ROADMAP.md` to ✅. Commit.

## Time log

| Date | Phase(s) | Time |
|------|----------|------|
| 2026-08-21 | 1-3 (core removal, shared-file cleanup, UI) | ~20 min |
| 2026-08-21 | 4-7 (tests, docs, data purge, verify & close) | ~15 min |

**Total: ~35 min**

## Session notes

LinkedIn removed cleanly: 2 files + 2 tests + 1 fixture + 1 icon deleted, ~15
shared-file comments reworded across collectors/docs/tests, 1 stale raw-data
file purged. Judgment calls made and documented inline above: left
`tests/fixtures/latest_jobs.json`/`test_filters.py` untouched (real historical
gate-testing data, not LinkedIn-collector-specific); left the signature cache
and tracking data untouched (no `source` field to filter on — cross-source
dedup by design); kept general lessons in `SCRAPING-GOTCHAS.md` but
reattributed them instead of deleting. 377 tests passing. One pre-existing,
unrelated test-isolation quirk found incidentally in `test_collector_occ.py`
(passes in the full suite, fails run alone) — flagged to Kevin, not fixed here.
Next recommended project: **EATP-028** (English-requirement classification +
funnel diagnostic + expanded search terms).
