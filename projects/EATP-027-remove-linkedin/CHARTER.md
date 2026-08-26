# EATP-027 — Remove LinkedIn as a source entirely

## Objective

Cut LinkedIn out of Rove completely: no collector, no config entry, no UI
affordance, no docs describing it as a live source. Not disabled, not kept as a
dormant option — gone, with the history staying in git. This is Kevin's own call
(2026-08-21 backlog, P0 in the original ChatGPT draft): the collector has been the
most fragile one in the whole system (CAPTCHA, login walls, geo/rate limits — see
EATP-005, 019, 020, 022 for the repeated fights) for a shrinking share of good
matches, and its upkeep cost stopped being worth it.

## Problems solved

- **P26** — LinkedIn collector fragile/high-maintenance for its yield (see ROADMAP.md).

## Context to load

Read only these — do not read the rest of the repo:

- `src/rove/collectors/__init__.py` — registry wiring + `BROWSER_SOURCES`.
- `src/rove/collectors/linkedin.py` — being deleted; skim to confirm nothing
  outside it depends on a helper defined here.
- `src/rove/collectors/linkedin_api.py` — being deleted; same check.
- `src/rove/collectors/browser.py` — shared with Indeed; only comments/
  docstrings mentioning LinkedIn get trimmed, the actual session/profile/kill logic
  stays untouched since Indeed depends on it.
- `src/rove/collectors/indeed.py` — has comments pointing at
  `linkedin.py` as "mirrors X" reference; these need rewording once that file is
  gone (don't point comments at a deleted file).
- `src/rove/collectors/occ.py` — same kind of dangling comment reference.
- `src/rove/pipeline.py` — one comment mentioning LinkedIn/Indeed as "the
  browser-driven ones"; reword to Indeed only.
- `src/rove/web/static/js/app.js` — has a `linkedin` entry in the source
  icon/color map (~line 72) and a comment about not blocking the UI on LinkedIn
  login (~line 5) that should generalize to "browser-driven collectors" (i.e. Indeed).
- `tests/test_collector_linkedin.py`, `tests/test_collector_linkedin_api.py` —
  delete outright.
- `tests/fixtures/linkedin_jobs.json` — delete outright.
- `tests/test_collector_framework.py`, `tests/test_dedup.py`, `tests/test_models.py`,
  `tests/test_pipeline.py`, `tests/fixtures/latest_jobs.json` — grep each for
  `linkedin` and remove only the LinkedIn-specific fixtures/assertions; leave
  everything else in these files alone.
- `README.md`, `docs/governance/ARCHITECTURE.md`, `docs/governance/AUTOMATION.md`,
  `docs/governance/DATA-CONTRACTS.md`, `docs/governance/DEPENDENCIES.md`,
  `docs/governance/SCRAPING-GOTCHAS.md`, `docs/governance/SEARCH-STRATEGY.md` — each
  lists LinkedIn as a live/active source somewhere; update so it no longer reads as
  currently active. Where a gotcha or lesson is general (not LinkedIn-specific,
  e.g. "browser collectors can hang on a dead Chrome process"), keep it and
  reattribute to Indeed/browser-driven collectors generally instead of deleting it.
- `CHANGELOG.md` — append a new entry at the top; never edit past entries.
- `pyproject.toml`, `requirements.txt` — **do not** remove `DrissionPage`; Indeed
  still depends on it. Confirm nothing else in these files is LinkedIn-specific
  before touching them (expect: nothing is).

**Explicitly do not touch:** `legacy/` (reference material, never edited — golden
rule 12), `projects/EATP-005-linkedin-collector/`, `projects/EATP-019` through
`EATP-024` and their charters/checklists (historical session records — they
document real work that happened; they don't get retroactively rewritten because
the feature was later removed), `docs/diagnosis/LEGACY-SYSTEM-REVIEW.md` (historical
audit of the pre-rebuild system).

## Dependencies

- **Projects:** EATP-026 (sequential convention only — no technical coupling).
- **Libraries:** none added or removed. `DrissionPage` stays (Indeed).

## Scope

**In:**
- Delete `linkedin.py`, `linkedin_api.py`, their tests, and their fixture.
- Remove `linkedin` from the collector registry and from `BROWSER_SOURCES`.
- Remove the UI's LinkedIn source entry and any LinkedIn-specific messaging
  (login/CAPTCHA/blocked states) from `app.js`.
- Fix every comment/doc that currently describes LinkedIn as a live source, or
  that points at `linkedin.py`/`linkedin_api.py` as a reference for a shared
  pattern (reword to describe the pattern locally or point at Indeed instead).
- Purge `data/raw/linkedin.jsonl` and any LinkedIn rows from the local signature
  cache / run history **without** deleting non-LinkedIn cache entries or tracked
  actions ("Apliqué" / "No me interesa") on jobs from other sources.
- One clean run of the full pipeline (`mode='thorough'`) with zero LinkedIn code
  loaded, config referenced, or UI element shown.

**Out (not this project):**
- Anything about new sources, English classification, or cache UI — those are
  EATP-028/029/030.
- Touching Greenhouse/Lever's watchlist model — explicitly staying as-is
  (Kevin's call, see the ROADMAP note above the project table).

## Deliverables

- LinkedIn fully absent from `src/`, `tests/`, active config, and the UI.
- Updated docs (README + the governance docs listed above) with no stale
  "LinkedIn is an active source" claims.
- `CHANGELOG.md` entry for EATP-027.
- `ROADMAP.md` EATP-027 row set to ✅ with completion date + time.

## Key design decisions & constraints

- **Comments pointing at a soon-deleted file are a real risk here**, not a
  nitpick: `indeed.py` and `occ.py` currently explain their own rate-limit/worker
  patterns by saying "mirrors linkedin.py" — once that file is gone those
  comments describe nothing. Reword them to state the pattern directly.
- **`browser.py` is shared, not LinkedIn's.** Do not gut its session-recovery /
  process-kill logic — Indeed depends on it and that logic was hard-won (see
  EATP-025's dead-browser-hang fix). Only the LinkedIn-specific mentions in its
  docstring/comments get trimmed.
- **Don't touch historical project folders.** EATP-005/019-024 stay as they are —
  they're a record of what was actually built and debugged, not living docs.
- **Cache/history purge must be surgical.** Filter by source, not a blanket wipe —
  Kevin's tracked "Apliqué"/"No me interesa" actions on non-LinkedIn jobs must
  survive.

## Definition of Done

Standard CLAUDE.md §9, plus:
- [ ] `grep -ri linkedin src/ tests/ docs/ README.md CHANGELOG.md` (excluding
      `legacy/` and the historical EATP-005/019-024 project folders) returns
      nothing that describes LinkedIn as active/present.
- [ ] Full pipeline run completes with no LinkedIn source in the output, no
      import errors, no dangling `BROWSER_SOURCES`/registry reference.
- [ ] `pytest` green with no LinkedIn tests remaining and no broken imports from
      the deleted files.

## Estimated time

~1–1.5h. Mechanical in most places (delete two files, drop registry entries,
prune UI map); the careful parts are the shared `browser.py`/`indeed.py`/`occ.py`
comment rewording and the surgical cache/history purge.

## Open questions for Kevin

None expected — this is fully a technical call. If something genuinely needs
Kevin's judgment (e.g. a doc claim that isn't obviously stale/current), it'll be
flagged in the session plan, not assumed.
