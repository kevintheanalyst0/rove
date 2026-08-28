# EATP-033 — Remove Indeed as a source entirely

## Objective

Cut Indeed out of Rove completely: no collector, no config entry, no UI
affordance, no docs describing it as a live source. Not disabled, not kept as a
dormant option — gone, with the history staying in git. Kevin's own call
(2026-08-27, mid-EATP-032 deploy session): Indeed's captcha volume was always
something he solved by hand, watching the screen for a window to jump to the
front. EATP-032's whole point is an unattended VM with nobody watching —
Indeed's captcha handling (EATP-006, kept alive through EATP-021/022/024)
cannot survive that, and he decided it isn't worth building around. He'll
keep using Indeed manually, outside Rove.

## Problems solved

- **P31** — Indeed's captcha volume makes it unworkable for an unattended
  server (see ROADMAP.md).

## Context to load

Read only these — do not read the rest of the repo:

- `src/rove/collectors/__init__.py` — registry wiring + `BROWSER_SOURCES`.
- `src/rove/collectors/indeed.py` — being deleted.
- `src/rove/collectors/browser.py` — being deleted; its only consumers were
  `indeed.py` and `server.py`'s `kill_all_browsers()` call (confirm nothing
  else imports it before deleting — EATP-027 left it alive because Indeed
  still needed it then).
- `src/rove/collectors/occ.py` — has comments comparing itself to Indeed
  (login/session risk, concurrency headroom); reword to describe the
  contrast generically ("a browser-driven collector") rather than naming a
  file about to not exist.
- `src/rove/pipeline.py` — `BROWSER_SOURCES` import/usage in
  `_requested_sources` and the `run()` docstring describing 'thorough' mode;
  `reset_all_run_data()`'s docstring lists `config.CHROME_USER_DATA_DIR` as
  deliberately untouched — that config var is also being removed.
- `src/rove/config.py` — `CHROME_BROWSER_PATH`/`CHROME_USER_DATA_DIR`, only
  used by `browser.py`/`pipeline.py`; remove once both are updated.
- `src/rove/web/server.py` — imports `browser` for `kill_all_browsers()` in
  the `/cancel` endpoint; that was EATP-024's hard-kill safety net for a
  collector stuck inside a blocking CDP call, moot with no browser-driven
  collector left.
- `src/rove/web/static/js/app.js` — a `indeed` entry in the source
  icon/color map (~line 75) and a docstring comment naming "Indeed's
  captcha" as the `needs_intervention` example (~line 5); the
  `needs_intervention` event-handling mechanism itself is generic and stays
  (no current caller, but it's not Indeed-specific code).
- `scripts/test_indeed_live.py`, `scripts/smoke_browser.py` — delete
  outright; both import the modules being deleted (`indeed.py` directly, or
  `browser.py` for a live Chrome launch/teardown smoke test that has nothing
  left to smoke-test once no collector drives a browser).
- `tests/conftest.py` — the autouse `_no_real_windows_foreground_calls`
  fixture monkeypatches `browser._force_windows_foreground`; delete the
  fixture and the now-unused import along with it.
- `tests/test_collector_indeed.py`, `tests/test_browser.py` — delete
  outright.
- `tests/fixtures/indeed_jobs.json` — delete outright.
- `tests/test_collector_framework.py` — its tail section (path resolution +
  `build_options` + `request_manual_intervention` tests) exercises
  `browser.py` directly; delete that section and the now-unused
  `browser_mod`/`EventBus` imports. The registry/HTTP tests earlier in the
  same file are unrelated — leave them.
- `tests/test_pipeline.py` — `test_fast_mode_never_touches_browser_sources`
  assumed Indeed was the one remaining `BROWSER_SOURCES` entry; with the set
  now empty there's nothing left to skip. Judgment call needed here, not a
  mechanical edit.
- `tests/test_dedup.py`, `tests/test_models.py`, `tests/test_source_health.py`,
  `tests/test_web_server.py` — grep each for `indeed`; it's used purely as an
  arbitrary source-name placeholder in all four (no functional dependency on
  the Indeed collector) — swap to a real remaining source, checking each
  test's own context for name collisions first.
- `README.md`, `docs/adr/ADR-001-content-signature-cache.md`,
  `docs/adr/ADR-005-source-strategy.md`, `docs/adr/ADR-008-source-health.md`,
  `docs/governance/ARCHITECTURE.md`, `docs/governance/AUTOMATION.md`,
  `docs/governance/DATA-CONTRACTS.md`, `docs/governance/DEPENDENCIES.md`,
  `docs/governance/SCRAPING-GOTCHAS.md`, `docs/governance/SEARCH-STRATEGY.md`
  — each lists Indeed as a live/active source somewhere, or points at a file
  being deleted. `ADR-005` is entirely about the "keep & optimize Indeed"
  decision — mark it Superseded rather than rewriting its body (ADRs are a
  historical record; EATP-027 set the "Superseded" status precedent for
  exactly this situation, though it wasn't needed there since LinkedIn never
  had its own dedicated ADR).
- `pyproject.toml`, `requirements.txt` — **do** remove `DrissionPage` this
  time (unlike EATP-027, which explicitly kept it because Indeed still
  needed it) — confirm first that nothing else imports it.
- `CHANGELOG.md` — append a new entry at the top; never edit past entries.
- `data/raw/indeed.jsonl` — delete (transient last-scrape output, dead
  weight). **Do NOT delete `data/browser_profile`** — it holds Kevin's real
  logged-in Indeed session, which he still needs for manual use outside
  Rove; purging it would only cost him a re-login for no benefit to this
  project's goal.

**Explicitly do not touch:** `legacy/` (reference material, never edited —
golden rule 12), `projects/EATP-006-indeed-collector/` and every other
historical completed-project folder (`003, 005, 007, 011, 014-024, 027-030`)
— they're records of real work that happened, not living docs, and stay as
written even where they describe Indeed as active at the time.
`docs/diagnosis/LEGACY-SYSTEM-REVIEW.md` (historical audit of the
pre-rebuild system). `tests/fixtures/latest_jobs.json` (real historical
postings used for the quality-gate's text classification, EATP-027's own
precedent for leaving this alone — "source" is just a data label on real
jobs, not a functional dependency on the collector).

## Dependencies

- **Projects:** EATP-032 (sequential convention only — this surfaced mid-deploy
  session, no technical coupling either direction).
- **Libraries:** removes `DrissionPage`. `playwright` stays (separate use:
  visual verification of the web UI, per `pyproject.toml`'s own comment).

## Scope

**In:**
- Delete `indeed.py`, `browser.py`, their tests/fixture, and the two
  standalone scripts that only existed to exercise them live.
- Remove `indeed` from the collector registry; `BROWSER_SOURCES` becomes an
  empty set (kept as a live mechanism for a future browser-driven source,
  not deleted — 'fast'/'thorough' just run the same sources until then).
- Remove the UI's `indeed` source-icon entry and the stale "Indeed's
  captcha" example in `app.js`'s docstring.
- Remove `CHROME_BROWSER_PATH`/`CHROME_USER_DATA_DIR` config and the
  `DrissionPage` dependency.
- Fix every comment/doc that currently describes Indeed as a live source, or
  that points at a file being deleted.
- Purge `data/raw/indeed.jsonl`. Leave `data/browser_profile` alone.
- Full test suite green with zero Indeed/browser.py code loaded or
  referenced.

**Out (not this project):**
- Anything about the actual EATP-032 VM deploy itself (SSH setup, Tailscale,
  the daily cron) — that continues separately once this lands.
- Rewriting `docs/governance/AUTOMATION.md`'s Windows-Task-Scheduler recipe
  for the new Oracle-VM-based automation — flagged as stale via a note, not
  rewritten; that's EATP-032's documentation debt, not this project's.
- Backfilling ROADMAP.md/CHANGELOG.md entries for EATP-031/032 themselves
  (accumulated inbox, VM deploy) — those were built in a prior session
  without the usual charter/checklist/changelog ceremony; a real gap, but a
  separate cleanup from removing Indeed.

## Key design decisions & constraints

- **`browser.py` is not shared with anything anymore.** EATP-027 kept it
  alive because Indeed still needed it; this project is the one that
  actually gets to delete it. Confirm via grep before deleting — don't
  assume this charter's own claim is still true by the time you build.
- **`BROWSER_SOURCES` stays as a mechanism, empty, not removed.** Kevin
  didn't ask to remove the fast/thorough mode distinction — only to remove
  Indeed. Ripping out the mode toggle because its one browser-driven member
  is gone would be unrequested scope; leave it there for whatever source
  earns it back in.
- **The real browser profile (`data/browser_profile`, ~300MB) is Kevin's,
  not Rove's dead weight.** He's keeping Indeed as a manual tool outside
  this app — deleting his saved login session would actively make that
  harder, not clean anything up.
- **Comments pointing at a soon-deleted file are a real risk**, same lesson
  as EATP-027: reword them to state the pattern directly rather than
  reference a file that's about to describe nothing.

## Definition of Done

Standard CLAUDE.md §9, plus:
- [ ] `grep -ri indeed src/ tests/ docs/ scripts/ README.md CHANGELOG.md
      pyproject.toml requirements.txt` (excluding `legacy/` and historical
      completed-project folders under `projects/`) returns nothing that
      describes Indeed as active/present or points at a deleted file.
- [ ] No import errors; `pytest` green with no Indeed/browser tests
      remaining.
- [ ] `ruff check` introduces no new findings versus pre-project baseline.

## Estimated time

~1h. Mechanical in most places (delete files, drop registry entries, prune
UI map, swap placeholder test source names); the careful parts are the
`occ.py`/`pipeline.py`/`server.py` comment rewording, the ADR-005
supersession note, and deciding what to do with
`test_fast_mode_never_touches_browser_sources` now that `BROWSER_SOURCES` has
no members left to test against.

## Open questions for Kevin

None expected — Kevin made this call explicitly and unprompted mid-session.
If a doc claim turns out ambiguous (current vs. historical), default to
marking it historical rather than deleting real narrative.
