# Changelog — Rove

All notable changes to this project, grouped by build session (`EATP-00X`). Dates are
the day the work was done; see `ROADMAP.md` for status/complexity/time per project.

## EATP-035 — Unattended pre-run submit sweep (2026-09-01)
- `src/rove/apply/sweep.py`: `sweep_pending_applications()` sends every
  still-pending `draft_ready` application, sequentially, reusing
  `apply.submit.submit_application` from EATP-034 as-is — no new fill/submit
  logic, just the daily orchestration. New `rove-presubmit-sweep.timer`
  (`12:30 UTC`, 30 min ahead of `rove-daily-run.timer`'s `13:00 UTC`) +
  `.service`, installed via `deploy/setup_vm.sh`.
- Kevin's own call to build this immediately rather than wait for real
  `draft_ready` output to validate first (EATP-034's original staging
  rationale): with only 2 of his 51 real accumulated jobs eligible for
  auto-apply at all, and both blocked by reCAPTCHA, there was nothing real
  to review yet — "cómo lo voy a probar si no hay ninguna vacante que se
  pueda." The sweep only ever acts on entries already `draft_ready`, so it's
  safe regardless of how often that actually happens.
- Same session: live-verified why OCC (Kevin's own question, prompted by
  this low real yield) isn't in scope — a plain page load against a real
  OCC posting returned `HTTP 403 "scraping abuse"` from headless Chromium,
  a harder and earlier-triggering block than Greenhouse's reCAPTCHA or
  Coinbase's Cloudflare wall. Not pursued further, same precedent as
  Indeed/EATP-033 and Glassdoor/EATP-030.
- 5 new tests (`test_apply_sweep.py`), full suite 421/421.
- Real-world timing validation (sweep finishes before the daily run over
  2+ actual days) is necessarily still pending — needs real calendar time
  to observe, not something a single session can confirm.

## EATP-034 — Auto-apply draft engine for Greenhouse & Lever (2026-08-30/31)
- New `[application]` table in `profile.toml` + `Application` submodel on
  `Profile` — the lean facts (contact, availability, work authorization,
  relocation, and a deliberate salary-placeholder policy) needed to answer
  real screening questions, never read by scoring.
- New `src/rove/apply/` package: `browser.py` (headless Playwright reads,
  classifies, and fills a real Greenhouse/Lever apply form — including full
  parsing of Lever's `[baseTemplate]` custom-question JSON, and a Cloudflare
  bot-challenge detector), `questions.py` (AI answers screening questions
  from the candidate profile, matched back by stable id — ADR-006's
  discipline, never a fixed Q&A bank per Kevin's explicit call),
  `store.py`/`prepare.py`/`submit.py` (draft state machine, orchestration,
  real send). `Provider.answer_questions` added across the whole AI layer,
  reusing `AiRouter`'s existing fallback/quota machinery.
- New pipeline stage (`pipeline._prepare_applications`, off by default via
  `AUTO_APPLY_ENABLED`): after every run, prepares a draft for every
  still-open Greenhouse/Lever job graded A+/A/B/C across the *whole*
  accumulated inbox — no per-run cap (Kevin's call), sequential, memory- and
  cancellation-aware.
- New dashboard surface: `GET /applications`, `POST
  /applications/<signature>/send`, a card badge, and a modal review/send
  block in `app.js`.
- Real-world DOM shape for every piece above was live-probed against actual
  Greenhouse (GitLab, Coinbase) and Lever (Palantir) boards before being
  coded, then validated end-to-end on `rove-vm` with 3 real jobs and a tiny,
  Kevin-approved live AI call — never sending a real application anywhere
  (`prepare_application` only, `submit_application` never invoked in
  testing). Two real findings logged for Kevin, not silently resolved:
  Greenhouse's real captcha rate may make it near-unusable for this feature
  as currently curated (Lever looks like the real carrier); one live AI
  answer to a US work-authorization question was ambiguous enough to warrant
  refining `profile.toml`'s wording afterward.
- `ADR-011` records the design (headless browser over raw HTTP replay,
  sweep-based deadline deferred to EATP-035, `manual_required` graceful
  degradation matching the Indeed/EATP-033 precedent). `EATP-035` (the
  unattended pre-run submit sweep) is scoped but deliberately not started —
  waits on Kevin watching real draft quality first.
- 416 tests passing (73 new: `test_apply_store.py`,
  `test_apply_browser.py`, `test_apply_questions.py`,
  `test_apply_prepare.py`, `test_apply_submit.py`,
  `test_pipeline_apply_prep.py`, plus dashboard/AI-router additions) — none
  of them spend live AI quota or touch the real network; the live smoke
  test was a separate, explicitly-approved, one-off run.

## EATP-033 — Remove Indeed as a source entirely (2026-08-27)
- Cut Indeed out of Rove completely: deleted `collectors/indeed.py` and
  `collectors/browser.py` (the DrissionPage/Chromium base — Indeed was its
  only remaining consumer after EATP-027 removed LinkedIn, the other one),
  their tests (`test_collector_indeed.py`, `test_browser.py` and the
  browser-specific tail of `test_collector_framework.py`), the `indeed_jobs.json`
  fixture, and the unused UI icon asset. Dropped `indeed` from the collector
  registry; `BROWSER_SOURCES` is now empty (kept as a mechanism, not deleted,
  for whichever future source needs it — 'fast' and 'thorough' modes run
  the same sources until then).
- Removed the now-fully-unused `DrissionPage` dependency and the
  `CHROME_BROWSER_PATH`/`CHROME_USER_DATA_DIR` config; `playwright` stays
  (used separately for UI visual verification, per `pyproject.toml`).
- Reworded every comment/docstring in `pipeline.py`, `server.py`, `app.js`,
  and the governance docs that described Indeed as active or pointed at the
  now-deleted files; marked `ADR-005` (the "keep & optimize Indeed" decision)
  Superseded by this project rather than rewriting its history.
- Kevin's own call (2026-08-27), made while working through EATP-032's
  headless-server deploy: Indeed's captcha volume is something he's always
  solved by hand, watching the screen — not viable unattended on a VM with
  no one looking, and not worth building around. He'll keep using Indeed
  manually outside Rove; the real browser profile with his login session
  (`data/browser_profile`) was deliberately left on disk for that, not
  purged.
- 360 tests passing (was 377 pre-EATP-027-era count minus the browser/indeed
  suites removed here); `ruff check` clean (4 pre-existing, unrelated
  findings in `parsing.py`/`weremoto.py`/`server.py` left untouched).

## EATP-032 — Deploy to an always-on Oracle Cloud VM (2026-08-26/27)
*(Backfilled 2026-08-27 — built across two sessions without a charter/checklist
at the time; see `projects/EATP-032-deploy-oracle-vm/` for the full record.)*
- The actual reason Rove forked off Career Radar (P32): run unattended, no
  laptop required, reachable from Kevin's phone. A GitHub Actions workflow
  (`.github/workflows/retry-oci-vm.yml`, `*/15 * * * *`, idempotent) retried
  Oracle's Always Free capacity in `mx-queretaro-1` until a slot opened —
  landed a `VM.Standard.A1.Flex` (1 OCPU/6GB, ARM) named `rove-vm`, faster
  than the ~5-day estimate.
- Installed Rove on the VM (`uv sync`, `.env` copied), full test suite
  verified green there too.
- **Tailscale** installed for private remote access — this is how Kevin's
  phone reaches the server, not the public IP.
- Hardened the VM without sacrificing direct SSH access for future sessions
  (key-only auth was already the default; added `fail2ban` for the sshd jail
  instead of restricting the security list, since the latter would have cut
  off SSH from anywhere outside the tailnet, including this repo's own
  Claude Code sessions). `ufw` default-denies everything except port 22
  (public) and the `tailscale0` interface (full access) — the web app itself
  is reachable **only** over Tailscale, confirmed live: 200 via the Tailscale
  IP, unreachable via the public IP.
- `server.py` gained two env-driven toggles for server mode (desktop
  launchers unaffected, defaults unchanged): `ROVE_AUTO_SHUTDOWN=0` disables
  EATP-023's tab-close self-kill (Kevin checks in from his phone with long
  gaps between visits — the server must survive that), and
  `ROVE_EXTRA_ALLOWED_HOSTS` extends ADR-010's same-origin/host allowlist
  past `127.0.0.1`/`localhost` so Tailscale-origin requests aren't rejected
  as cross-origin.
- Three systemd units on the VM: `rove-web.service` (the FastAPI app,
  `Restart=always`, survives reboot), `rove-daily-run.timer` +
  `rove-daily-run.service` (`OnCalendar=*-*-* 13:00:00 UTC` = 7am Kevin's
  fixed UTC-6 time, triggers `POST /run` against the already-running
  server rather than invoking the pipeline as a separate process). All
  five services (`rove-web`, the timer, `tailscaled`, `fail2ban`, `ufw`)
  confirmed `enabled` — a VM reboot (Oracle maintenance, etc.) restores full
  function with no manual step.
- **Not fixed here, flagged only:** `docs/governance/AUTOMATION.md` still
  describes the original Windows-Task-Scheduler recipe, not this VM-based
  approach — a note was added pointing at this project instead of rewriting
  it (separate scope).
- Also mid-session: EATP-033 removed Indeed entirely (see above) — surfaced
  by this same deploy work (no headless display for its browser automation)
  but Kevin's own call for a different reason (captcha volume, not the
  display issue, which Xvfb would have solved).

## EATP-031 — Accumulated inbox (2026-08-25/26)
*(Backfilled 2026-08-27 alongside EATP-032/033 — see the note above.)*
- Jobs now persist across runs in `data/inbox.jsonl` until Kevin applies or
  dismisses them, fixing `results.json` being overwritten every run — which
  used to silently lose anything from a day he didn't check (the concrete
  case P32 above is about).
- New `GET /inbox`, bucketed **Hoy / Ayer / Esta semana / Más viejo** in
  Kevin's real timezone (`config.KEVIN_TIMEZONE`, fixed UTC-6).

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
