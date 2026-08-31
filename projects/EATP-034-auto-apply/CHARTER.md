# EATP-034 — Auto-apply draft engine (Greenhouse & Lever)

## Objective
Automatically fill and hold ready-to-send job applications for Greenhouse/Lever
vacantes graded A+/A/B/C, answering screening questions via AI from a lean
candidate profile (no fixed question bank) instead of Kevin filling each ATS
form by hand. Ships the draft engine, the dashboard review/manual-send flow,
and the pipeline hook that prepares drafts after each daily run. The fully
unattended auto-send-after-deadline behavior is EATP-035, once this project's
draft quality has been validated on real jobs.

## Problems solved
**P33** — vacantes se acumulan en el inbox sin que Kevin tenga tiempo de
aplicar; para cuando aplica, ya se llenaron de competidores (his own,
2026-08-30 — see ROADMAP.md).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `docs/governance/CANDIDATE-PROFILE.md` | Source of truth for who Kevin is; needs a new `[application]` section. |
| `docs/governance/DATA-CONTRACTS.md` | Data-model conventions to mirror for `applications.jsonl`. |
| `docs/governance/AI-PROVIDERS.md` | Provider fallback / quota discipline to reuse for question-answering. |
| `docs/governance/DEPENDENCIES.md` | Check playwright/chromium install state; note the VM-vs-Windows runtime gap. |
| `docs/governance/SCRAPING-GOTCHAS.md` | Any existing per-site gotchas relevant to Greenhouse/Lever. |
| `docs/adr/ADR-011-auto-apply-draft-and-sweep.md` | The design decisions this project implements. |
| `src/rove/collectors/greenhouse.py`, `lever.py` | Exact fields/URLs available per job. |
| `src/rove/models.py` | `Job`/`ScoredJob` shape. |
| `src/rove/inbox/store.py`, `tracking/store.py` | JSONL store pattern to mirror for `apply/store.py`. |
| `src/rove/pipeline.py` | Hook point right after `inbox_store.append_run`. |
| `src/rove/ai/router.py`, `ai/base.py`, `ai/prompts.py` | `AiRouter`/`Provider` reuse pattern. |
| `src/rove/profile.py`, `profile.toml` | `Profile` model + TOML source to extend. |
| `src/rove/web/server.py` | Endpoint conventions (`/track`, `/inbox`). |
| `src/rove/web/static/js/app.js` | `trackAction` pattern to mirror for the new review/send UI. |
| `src/rove/events.py` | `EventBus`, for progress publishing. |
| `legacy/jobmatch/collectors/browser.py` | Reference only — "needs a real browser session" shape; not reusable (its dependency, DrissionPage, was removed in EATP-033). |

## Dependencies
- **Projects:** EATP-032 ✅ (deploy — this runs primarily on `rove-vm`), EATP-033 ✅
  (Indeed/browser-driven collector removed — this reintroduces headless browser
  use for a different purpose: filling forms, not scraping listings).
- **Libraries:** `playwright` (already present, currently scoped to UI visual
  verification only — repurposed here). New: `psutil` (pre-launch memory check)
  — **not yet in `DEPENDENCIES.md`, needs Kevin's "sí" before installing**
  (CLAUDE.md §8).

## Scope
**In:**
- New `[application]` table in `profile.toml` + `Application` submodel on `Profile`.
- New `src/rove/apply/` package: `browser.py`, `questions.py`, `store.py`,
  `prepare.py`, `submit.py`.
- Pipeline hook: prepares drafts for every open-inbox Greenhouse/Lever job
  graded A+/A/B/C, sequential (one Chromium instance at a time), with a
  memory/AI-quota safety check before each launch.
- New endpoints: `GET /applications`, `POST /applications/<signature>/send`
  (manual send, triggered from the dashboard).
- Dashboard UI: a review card/modal + "Enviar" button, mirroring the existing
  `trackAction` pattern.
- Graceful `manual_required` fallback on captcha/login-wall/unrecognized form.
- Tests: store (mirrors `test_tracking.py`), questions (mocked AI, no live
  calls), browser (against recorded fixture HTML, no live network).

**Out (belongs to EATP-035, not this project):**
- The unattended pre-run submit sweep / new systemd timer.
- Auto-send without Kevin's click.
- OCC/Computrabajo or aggregator-redirect sources (only Greenhouse/Lever, per
  Kevin's v1 scope decision).
- Answer-editing UI before send — nice-to-have; build only if it falls out
  naturally, otherwise defer without ceremony.

## Key design decisions & constraints
- Headless Playwright over raw HTTP form replay — see ADR-011 §1: unknown
  per-company whether a Greenhouse board is static or JS-rendered; Playwright
  handles both.
- Strictly sequential — one Chromium instance at a time, never parallel
  (CLAUDE.md golden rule 2; see also [[feedback_no_subagents_eatp]]) — bounds
  peak memory on the VM's 1 OCPU/6GB.
- No fixed Q&A bank — Kevin's explicit call (bad experience with this pattern
  in the legacy Career Radar predecessor). The AI reads each job's real
  questions plus the lean profile, fresh every time.
- Captcha/unsupported form → `manual_required`, never fought unattended — same
  lesson as EATP-033's Indeed removal.
- EEO/demographic-disclosure questions always answered "prefer not to
  disclose" via a standing prompt instruction — my own technical default
  (ADR-011 §6), independent of Kevin's "trust the AI" instruction for
  everything else.
- `AUTO_APPLY_ENABLED` defaults to **off** in `config.py` — flip only after a
  manual smoke test against real inbox jobs on the actual VM confirms memory
  stays healthy.
- `DEPENDENCIES.md` doc gap (only documents the native-Windows runtime from
  EATP-025; this feature runs primarily on the Linux/ARM VM from EATP-032) —
  flag, don't fully rewrite this session (same treatment `AUTOMATION.md` got
  in EATP-033).

## Definition of Done
- [x] Every deliverable above exists and works.
- [x] `pytest` green (fixtures/mocks only, no live AI or network) — 416/416.
      A real live-AI smoke test also ran, separately, with Kevin's explicit
      per-session approval (CLAUDE.md §7), not as part of the automated suite.
- [x] No OOM/crash risk left unaddressed — `psutil` memory check verified
      against real VM behavior (392Mi→570Mi free across the live smoke test),
      not just reasoned about.
- [x] Checklist ticked, time logged (~5h55m total).
- [x] ROADMAP status → ✅.
- [x] Session notes written.
- [x] Committed to git (CLAUDE.md §10).
- [x] Nothing secret or heavy committed (CV/resume file stays out of git, same
      treatment as `.env`/`data/`).
- [x] Manual smoke test run on `rove-vm` against 3 real jobs (2 from Kevin's
      actual inbox, 1 a real live posting used specifically to exercise the
      full path); memory confirmed stable.
- [x] CV/resume file resolved with Kevin (English version, his call) and
      copied to `rove-vm:~/rove/data/resume.pdf`.

## Estimated time
Large for this repo's usual sizing — realistically 4-6h given it's a genuinely
new subsystem (browser automation + a new AI capability + a new store + new
UI), likely spread across more than one session. If it starts ballooning
mid-build, stop and split into 034a/034b rather than push through (CLAUDE.md §3).

## Open questions for Kevin
- Where does your current CV/resume PDF live, so it can be placed on the VM
  (e.g. `data/resume.pdf`)? Not blocking the build itself, only the final
  real-send validation.
