# EATP-033 — Checklist & time log

## Phases

- [x] **Phase 1 — Core removal.** Deleted `indeed.py`, `browser.py` (confirmed
      via grep it had exactly two consumers left — `indeed.py` and
      `server.py`'s `kill_all_browsers()` call — both removed here, so no
      shared logic was orphaned). Removed `indeed` from the collector
      registry; `BROWSER_SOURCES` is now `set()`, kept as a mechanism with an
      updated docstring rather than deleted.
- [x] **Phase 2 — Shared-file cleanup.** Reworded Indeed mentions in
      `pipeline.py` (2 spots: `run()`'s mode docstring, `reset_all_run_data()`'s
      now-stale `CHROME_USER_DATA_DIR` bullet — removed since the config var
      is gone too; also reworded a `browser.kill_all_browsers()` doc reference
      in `_evaluate_batch_cancellable` to a generic OS-kill analogy),
      `server.py` (dropped the `browser` import and the `/cancel` endpoint's
      hard-kill call + its now-obsolete CDP-blocking justification, kept the
      cooperative-cancellation explanation), `app.js` (dropped the `indeed`
      source-icon entry, reworded the `needs_intervention` docstring example
      to be generic — the mechanism itself has no caller left but isn't
      Indeed-specific code, so it stays), `occ.py` (2 comments comparing
      itself to "Indeed" reworded to "a browser-driven collector" so they
      don't name a deleted file), `config.py` (removed
      `CHROME_BROWSER_PATH`/`CHROME_USER_DATA_DIR` entirely — confirmed via
      grep these had no other consumer).
- [x] **Phase 3 — Standalone scripts.** Deleted `scripts/test_indeed_live.py`
      (imported `indeed.py` directly) and `scripts/smoke_browser.py` (imported
      `browser.py` for a live Chrome launch/teardown check with nothing left
      to smoke-test). Updated `README.md`'s Development section to drop the
      `smoke_browser.py` run line and its explanatory paragraph, and
      relabeled the `playwright install chromium` line's comment from
      "browser collectors" to "UI visual verification" (its actual remaining
      purpose, per `pyproject.toml`).
- [x] **Phase 4 — Tests.** Deleted `test_collector_indeed.py`, `test_browser.py`,
      `tests/fixtures/indeed_jobs.json`. Removed `test_collector_framework.py`'s
      browser-specific tail (path resolution, `build_options`,
      `request_manual_intervention` — 6 tests) and its now-unused
      `browser_mod`/`EventBus` imports; the registry/HTTP tests earlier in the
      same file were untouched. Deleted `conftest.py`'s
      `_no_real_windows_foreground_calls` autouse fixture (monkeypatched
      `browser._force_windows_foreground`, which no longer exists) and its
      now-unused `browser` import. Swapped the arbitrary `"indeed"` source
      label to `"greenhouse"` in `test_dedup.py`, `test_models.py`,
      `test_source_health.py`, `test_web_server.py` (checked each test's own
      context first — `greenhouse` didn't collide with any source already
      used in the same test). **Judgment call:** deleted
      `test_fast_mode_never_touches_browser_sources` outright rather than
      "simplifying" it the way EATP-027 simplified it to Indeed-only — with
      `BROWSER_SOURCES` now empty there's no browser source left for 'fast'
      mode to skip, so the test's premise doesn't exist anymore. Replaced it
      with `test_fast_mode_runs_every_source_while_browser_sources_is_empty`,
      asserting fast and thorough behave identically until a future
      browser-driven source exists. Full `pytest`: **360 passed** (down from
      377 pre-EATP-027-era baseline — accounts for the ~17 deleted
      browser/indeed tests).
- [x] **Phase 5 — Dependencies.** Removed `DrissionPage` from `pyproject.toml`
      and `requirements.txt` (confirmed via grep: zero remaining imports
      anywhere in `src/`/`tests/` after Phase 1-4's deletions — unlike
      EATP-027, which had to keep it since Indeed still needed it then).
      `playwright` stays untouched (separate purpose: UI visual verification).
- [x] **Phase 6 — Docs.** Updated `README.md` (dropped the 3-step
      "Chrome corre minimizado.../resuélvela ahí" usage instructions and the
      captcha caveat on the automation section), all 6 governance docs
      (`ARCHITECTURE`, `AUTOMATION`, `DATA-CONTRACTS`, `DEPENDENCIES`,
      `SCRAPING-GOTCHAS`, `SEARCH-STRATEGY`) so none describe Indeed as
      active, `ADR-001` and `ADR-008` (Indeed mentioned only as illustrative
      example text — reworded to a still-active source or folded into a
      "both historically removed" phrasing alongside LinkedIn), and marked
      `ADR-005` **Superseded by EATP-033** with a short note rather than
      rewriting its body — it's a historical record of a decision that was
      later reversed for a different reason than the alternative it
      originally rejected. `AUTOMATION.md` also got a note flagging that its
      whole Windows-Task-Scheduler recipe predates EATP-032's Oracle-VM
      approach — not rewritten (out of scope here), just flagged so it's not
      mistaken for the current plan. General lessons in `SCRAPING-GOTCHAS.md`
      (rate-limit coordination across browser tabs, the persistent-profile
      cold-start gotcha, the loop-detection pagination pattern) were kept and
      marked historical rather than deleted — still relevant to whichever
      future source drives a real browser. Appended `CHANGELOG.md` entry;
      updated `ROADMAP.md` (new EATP-033 row, Block B description, the
      dependency-graph line, P5's mapping, and a new **P31** in the
      traceability table for "Indeed's captcha volume makes it unworkable for
      an unattended server").
- [x] **Phase 7 — Data purge.** Deleted `data/raw/indeed.jsonl` (transient
      last-scrape output, dead weight). **Left `data/browser_profile`
      (~300MB) untouched** — attempted an initial `rm -rf` on it by habit
      before catching the actual reasoning: Kevin explicitly said he'll keep
      using Indeed manually outside Rove, so his real logged-in session in
      that profile is still useful to him; purging it would only cost a
      re-login for zero benefit to this project's goal. `data/cache` and
      `data/history` were checked (same schema audit EATP-027 did) — no
      `source` field to filter on in the signature cache, and history
      records are dated historical run records treated like CHANGELOG
      entries; nothing purged there.
- [x] **Phase 8 — Verify & close.** `pytest`: 360 passed. `ruff check src/
      tests/`: 4 findings, all pre-existing and in files this project never
      touched (`parsing.py`'s `re.S`, `weremoto.py`'s timezone replacement,
      `server.py`'s unrelated `noqa`/`B008` — confirmed via git diff these
      predate this session). `grep -ri indeed` sweep clean outside `legacy/`
      and historical completed-project folders. Committed and pushed to
      `main`. Deployed the resulting code to the EATP-032 Oracle VM (`git
      pull`, `uv sync` — DrissionPage no longer installs there either) in the
      same session, since the VM had already been provisioned with the
      pre-removal code moments before Kevin made this call.

## Time log

| Date | Phase(s) | Time |
|------|----------|------|
| 2026-08-27 | 1-8 (full project, one session) | ~1h |

**Total: ~1h**

## Session notes

Indeed removed cleanly: 4 files + 2 standalone scripts + 2 test files + 1
fixture deleted, ~20 shared-file comments reworded across
collectors/pipeline/server/UI/docs/tests, 1 stale raw-data file purged, 1
dependency dropped. Judgment calls made and documented inline above: deleted
(not simplified) the `BROWSER_SOURCES`-skip test since its premise no longer
exists with an empty set; kept `BROWSER_SOURCES` itself as a live but empty
mechanism rather than removing the fast/thorough distinction Kevin didn't ask
to remove; deliberately did NOT purge `data/browser_profile` (Kevin's real
login session, still useful to him for manual Indeed use); flagged
`AUTOMATION.md`'s staleness relative to the actual EATP-032 VM plan without
rewriting it (separate scope). 360 tests passing, zero new lint findings. This
also happens to remove the single biggest technical blocker to EATP-032's
unattended-server goal — Indeed's captcha handling required a human at a
screen, which a headless VM will never have.
