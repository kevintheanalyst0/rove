# Changelog — Rove

All notable changes to this project, grouped by build session (`EATP-00X`). Dates are
the day the work was done; see `ROADMAP.md` for status/complexity/time per project.

## EATP-030 — New sources: Hireline, WeRemoto, RemotoJob (2026-08-21)
- Added three HTTP-only collectors sharing one shape new to this repo: no
  search API, but every posting discoverable via a sitemap or category page,
  with a standard schema.org `JobPosting` JSON-LD block on each detail page.
  No company watchlist needed (unlike Greenhouse/Lever) — real market-wide
  postings.
- New shared helpers in `collectors/parsing.py`: `extract_job_posting_ld_json`
  (picks the right block out of several unrelated JSON-LD types per page,
  tolerant of a raw-newline gotcha confirmed live on RemotoJob) and
  `slug_to_text` (prefilters a sitemap-discovered URL by its slug before
  spending a detail request on it).
- Live-verified against the real sites (not just against fixtures): Hireline
  and WeRemoto both returned real, current, on-profile postings.
- LaPieza and Glassdoor were spiked and dropped: LaPieza is a client-rendered
  SPA with no discoverable API (same dead end as Get on Board, EATP-008);
  Glassdoor returned a 403 anti-bot wall immediately (same fragility class as
  LinkedIn — not force-built with browser automation, on purpose). Recorded
  in `ROADMAP.md`'s Backlog so a future session doesn't re-attempt either.
- Fixed stale claims in `SEARCH-STRATEGY.md` (Ashby/Workable/Get on
  Board/Torre were still listed as current sources despite being cut/dead-
  ended earlier) and pointed its search-terms section at `config.py` instead
  of a copy that will drift again.
- 408 tests passing (13 net new).

## EATP-029 — Cache observability: "Ver cacheadas" + manual reset (2026-08-21)
- `SignatureRecord` gains `title`/`company`/`source` (display-only; suppression
  still keys on `signature` alone) so the cache is finally human-readable.
- New `GET /cache` (read-only list, most-recently-seen first) and
  `POST /cache/reset` (clears only the signature cache — deliberately
  separate from the existing "Limpiar caché" button, which wipes far more:
  results/raw/history/health). Kevin's call: keep "Limpiar caché" exactly as
  it is, add this as its own distinct control.
- The funnel diagnostic's `cached_recently` count (EATP-028) already covered
  "how many did the cache hide this run" — verified end to end, no new
  tracking needed.
- 395 tests passing (10 net new). No change to the 30-day suppression window
  or what gets suppressed — every pre-existing cache test still passes
  unmodified.

## EATP-028 — English-requirement classification + funnel diagnostic + search terms (2026-08-21)
- Replaced the bare `english_required: bool` hard-reject with a three-tier
  `EnglishRequirement` classification (`compatible`/`indeterminate`/`reject`) —
  same shape as the existing `remote_status`/`remote_evidence` pattern. Only
  `reject` (explicit C1/C2/native/bilingual) still hard-gates; `indeterminate`
  (ambiguous phrasing like "English required", "professional English",
  "fluent" — none of which specify a level) is kept visible with a
  `confirm_english` flag and the exact matched phrase instead of being
  silently dropped (P27, Kevin's 2026-08-21 backlog).
- Added `RunResult.funnel`: a per-source breakdown of every gate-rejection
  reason, so a quiet run can be told apart from a stage/source quietly
  filtering a lot (P28) — reuses `quality/filters.py`'s existing reason
  strings, no new tracking mechanism.
- Expanded `config.py`'s search-term lists with 10 new titles (Power BI
  Developer, Insights Analyst, SAP Data Analyst, People Analytics, etc.) plus
  "analista de inteligencia comercial".
- UI: "Confirmar inglés" badge on the job card + matched-phrase notice in the
  detail modal.
- 385 tests passing (8 net new, covering both classification tiers and the
  three previously-misclassified example phrases).

## EATP-027 — Remove LinkedIn as a source entirely (2026-08-21)
- Deleted `collectors/linkedin.py`, `collectors/linkedin_api.py`, their tests, their
  fixture, and the unused UI icon asset. Dropped `linkedin` from the collector
  registry and from `BROWSER_SOURCES` (Indeed is now the only browser-driven source).
- Reworded every comment/docstring in `browser.py`, `indeed.py`, `occ.py`,
  `pipeline.py`, `config.py`, and the governance docs (`ARCHITECTURE.md`,
  `AUTOMATION.md`, `DATA-CONTRACTS.md`, `DEPENDENCIES.md`, `SCRAPING-GOTCHAS.md`,
  `SEARCH-STRATEGY.md`) that described LinkedIn as active or pointed at the now-deleted
  files — `browser.py`'s actual session/profile/kill logic (shared with Indeed) was
  left untouched.
- Decision (P26, Kevin's 2026-08-21 job-search backlog): the collector had been the
  most fragile in the system (CAPTCHA, login walls, geo/rate limits — see EATP-005,
  019, 020, 022) for a shrinking share of good matches; not worth the upkeep any
  longer. Full history stays in git; nothing kept as a dormant option.
- 377 tests passing after removal; no behavior change to any other collector.

## [Unreleased] — EATP-018 — QA, hardening, automation & GitHub publish (2026-08-12)
- End-to-end verification via the real web UI: 232 collected -> 48 gated -> 48
  AI-evaluated -> 48 final. Indeed's captcha resolved manually with the Chrome window
  visible under WSLg (a prior session had this fail; restarting Ubuntu fixed it).
- Playwright visual verification: spinner state (dots + live status text, via a
  fake-pipeline instance so no extra live calls were spent) and the results dashboard
  (real data) both render correctly, no layout regressions.
- Confirmed LinkedIn/Lever/RemoteOK returning zero results that run were real "nothing
  matched" outcomes (verified their APIs directly), not breakage.
- Documented (not activated) a Windows Task Scheduler + `wsl.exe` daily-run recipe —
  `docs/governance/AUTOMATION.md`.
- Match-notification hook: **not built** — Kevin doesn't want it (decided 2026-08-12).
- Finalized `README.md` and this `CHANGELOG.md`.
- Secret/`.gitignore` audit and GitHub publish: pending.

## EATP-017 — Match-quality evaluation harness (2026-08-12)
- Kevin can label shown jobs "good"/"bad" (with a reason) from the dashboard.
- A precision report compares those labels against the AI's own grading, to answer
  "did quality actually improve" (P22) instead of guessing.

## EATP-016 — Web UI: results dashboard + job tracking (2026-08-12)
- Results dashboard: grade, score, pros/cons, summary per job; NEW badge for postings
  unseen in prior runs (ADR-007).
- **Apliqué** / **No me interesa** tracking per posting; dismissed jobs are hidden from
  future runs.
- Visual redesign to a light "Apple + Aero" glass look (v3), with responsive-layout
  fixes for the sidebar/card breakpoints.

## EATP-015 — Web UI: backend + runner spinner (2026-08-12)
- FastAPI backend + single-page frontend. `POST /run` starts the pipeline in a
  background thread; Server-Sent Events stream live phase/status to the page.
- Working-spinner + status text instead of a terminal (ADR-004) — Kevin starts a run
  with one click ("Iniciar búsqueda") and never sees a console.

## EATP-014 — Orchestrator (2026-08-12)
- One resumable, checkpointed pipeline run wiring collect → gate → matcher pre-filter
  → AI evaluation → persist. A crash or interruption resumes from the last checkpoint
  instead of restarting (golden rule 3: never lose progress to an OOM/crash).

## EATP-013 — Scoring & evaluation pipeline (2026-08-12)
- Matcher pre-filter rejects clearly-bad jobs and caps how many reach the AI, to protect
  the free AI quota and focus it on plausible matches (P10).
- AI deep-evaluation is **id-based, not positional** (ADR-006) — fixes P17, where the
  legacy system could mis-attribute one job's analysis to another.
- Post-validation guards strip contradictory AI output (e.g. a "pro" that restates a
  hard exclusion).

## EATP-012 — Multi-provider AI layer (2026-08-12)
- Groq / Gemini Flash-Lite / OpenRouter with fallback order and quota tracking
  (ADR-003), so a single provider's tiny free tier never stalls a run.
- Structured-output enforcement + repair for malformed AI JSON (P11).
- Fixed a stale Gemini model id and corrected the free-tier quota numbers Kevin had
  observed in practice, both found via a single approved live smoke test.

## EATP-011 — Source health & self-check (2026-08-12)
- Detects a source going silently empty/broken (P20) instead of it just quietly
  yielding nothing forever.

## EATP-010 — Dedup, content-signature cache & run history (2026-08-12)
- Cross-source fuzzy dedup within a run.
- Content-signature cache (ADR-001) so daily-reposted jobs don't reappear (P9) — cache
  keys are content signatures, never volatile site ids.

## EATP-009 — Quality gates (2026-08-12)
- `filters.py`: title/english/junk gates + the remote hard-gate (ADR-002) — hybrid and
  onsite jobs are rejected outright, never shown with a "kind of remote" flag (P8).

## EATP-008 — ATS boards: Greenhouse + Lever (2026-08-12)
- Investigated Get on Board and Torre as sources; neither has a usable public
  endpoint (documented in `ROADMAP.md` backlog so it isn't re-attempted blind).

## EATP-007 — Remote-first boards (2026-08-12)
- Remotive, RemoteOK, WWR, Himalayas — broadens sourcing beyond the original 4
  platforms (P2, P3).

## EATP-006 — Indeed collector (2026-08-12)
- Rebuilt from scratch, not ported from legacy (P5). Iterated live: fixed a wrong date
  field (`datePosted`), parallelized detail-page fetches across 2 tabs, and — after
  Kevin's explicit preference — switched from auto-skipping captchas to waiting for
  Kevin to resolve them manually, since he'd rather solve it himself than have the run
  silently under-collect.

## EATP-005 — LinkedIn collector (2026-08-12)
- Rebuilt from scratch, not ported from legacy.

## EATP-004 — HTTP collectors: OCC & Computrabajo (2026-08-12)
- Rebuilt from scratch, not ported from legacy.

## EATP-003 — Collector framework (2026-08-12)
- Shared plumbing (base contract, browser/http helpers, pacing) every collector builds
  on.

## EATP-001 / EATP-002 — Foundation & criteria (2026-08-12)
- Config, data models, storage, event bus, candidate profile, hard filters, fit rubric.
- Fraud-company blocklist (P25) and the legacy-evaluation rule that later became
  CLAUDE.md golden rule 12 (judge legacy code on its merits, never port by habit).
