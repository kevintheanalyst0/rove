# EATP-034 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases

### Phase 1 — Profile & data contracts
- [x] Add `[application]` table to `profile.toml` (salary placeholder policy,
      availability, work authorization, relocation, phone, email, linkedin,
      portfolio, github).
- [x] Add `Application` submodel to `src/rove/profile.py` `Profile`.
- [x] Update `docs/governance/CANDIDATE-PROFILE.md`.
- [ ] Update `DATA-CONTRACTS.md` with the `applications.jsonl` schema — deferred
      to Phase 2, once `ApplicationEntry` actually exists (doc should describe
      reality, not a plan).
- [x] Full `pytest` suite green (359/360 — the 1 failure, an SSE timing test,
      passed in isolation; unrelated to this phase's changes).

### Phase 2 — `apply/store.py`
- [x] `ApplicationEntry` model + JSONL store, mirroring `inbox/store.py` /
      `tracking/store.py` (`already_prepared_signatures()` skips
      `draft_ready`/`manual_required`/`submitted` but retries `failed`;
      `draft_ready_entries()` feeds the dashboard + EATP-035's future sweep).
- [x] `config.APPLICATIONS_FILE`.
- [x] `tests/test_apply_store.py` — 7 tests, green.
- [x] `docs/governance/DATA-CONTRACTS.md` updated with the real
      `ApplicationEntry` schema (deferred from Phase 1 on purpose).

### Phase 3 — `apply/browser.py`
- [x] Captured real Greenhouse (GitLab) and Lever (Palantir) apply pages live
      via headless Chromium — confirmed real field ids/names, confirmed
      GitLab's board has a reCAPTCHA, confirmed Lever's form lives at
      `<hostedUrl>/apply` (not the listing page), confirmed the EEO fields'
      exact React-Select decline-option wording by live-clicking them.
      Trimmed, faithful fixtures written to `tests/fixtures/` (not raw SPA
      dumps).
- [x] `read_form`/`fill_form`/`submit_form`/`resolve_apply_url` in
      `apply/browser.py`.
- [x] Captcha detection → `has_captcha`; no-form-found → empty `fields`; both
      read by `prepare.py` (Phase 5) as `manual_required` triggers.
- [x] **Investigated both flagged gaps for real instead of leaving them
      documented (Kevin's explicit ask, 2026-08-31):**
      - Greenhouse custom-domain embeds (Coinbase, live-checked): it's a
        Cloudflare bot-challenge page ("Just a moment..."), the same class
        of block that got Indeed removed in EATP-033 and Glassdoor never
        attempted in EATP-030 — not a code gap, a deliberate boundary.
        `read_form` now detects it explicitly (`blocked_reason`) so the
        resulting `manual_required` entry says *why* instead of looking
        like a silent failure.
      - Lever's custom "additional info cards" — **fully solved**, not left
        unsupported. Each card's hidden `[baseTemplate]` input holds a full
        JSON spec (question text, type, required, options); `text`/
        `textarea`/`multiple-choice`(radio)/`multiple-select`(checkbox)/
        `dropdown`(select) are all read, AI-answered, and filled correctly,
        live-verified against Palantir's real board including a 3301-option
        university dropdown. Only a choice-field with more than
        `MAX_CHOICE_OPTIONS` (100) options stays `unsupported` — a
        deliberate AI-quota-budget cap (CLAUDE.md §7), not an unresolved gap.
- [x] `tests/test_apply_browser.py` — 12 tests against the fixtures
      (including the Cloudflare-detection and Lever-card cases above), no
      live network, green.

### Phase 4 — `apply/questions.py` + AI plumbing
- [x] New `_APPLICATION_TEMPLATE`/`build_application_prompt` in
      `ai/prompts.py` — candidate profile (incl. the `[application]` table)
      + job context + questions (with OPTIONS when constrained-choice) →
      structured JSON answer. EEO "prefer not to disclose" is handled at the
      browser layer (Phase 3), not here — those fields never reach the AI.
- [x] `Provider.answer_questions(prompt) -> str` added to the ABC + all three
      provider families (`_openai_compatible.py` covers Groq/OpenRouter,
      `gemini.py` its own), reusing the exact same retry/quota-classification
      helpers as `evaluate_batch`. `AiRouter.answer_questions` mirrors
      `evaluate_batch`'s fallback loop over the same `AI_PROVIDER_ORDER` and
      `UsageTracker` — **shares the same daily budget as scoring**, flagged
      in `AI-PROVIDERS.md` as an accepted risk given Kevin's no-cap decision.
- [x] `apply/questions.py`: `answer_form_questions` (only answers `CUSTOM`
      fields) + `parse_answers_response` (ADR-006-style match-by-id, drops
      invented/duplicate ids rather than guessing).
- [x] Fixed 5 pre-existing test-double `Provider` subclasses (across
      `test_ai_router.py`/`test_scoring.py`/`test_pipeline.py`) that needed a
      stub `answer_questions` once it became a required abstract method.
- [x] `tests/test_apply_questions.py` — 12 tests, mocked provider, no live AI
      calls. Full suite: 389/389.

### Phase 5 — `apply/prepare.py` + `apply/submit.py`
- [x] `prepare_application(job, profile, router)` — eligibility check
      (`is_eligible`), browser read, AI answer, **and a real dry-fill**
      (never submit) to validate everything actually works before promising
      `draft_ready` — a deliberate refinement over the original charter
      wording (which had prepare only reading), documented in the module
      docstring with the reasoning.
- [x] `submit_application(job, profile, entry)` — re-drives a fresh browser
      session to fill (reusing the entry's stored `answers`, never re-asking
      the AI) and actually submit.
- [x] Both accept an optional injected `BrowserContext`, so tests exercise
      the real Playwright interaction end-to-end via `context.route(...)`
      fixture responses — zero live network calls, real headless-browser
      behavior (CLAUDE.md §7 extended to browser automation, same as Phase 3).
- [x] `tests/test_apply_prepare.py` (9 tests) + `tests/test_apply_submit.py`
      (5 tests) — captcha/no-form/Cloudflare/success/AI-silent/nav-error
      paths, all green. Full suite: 403/403.
- [x] **Honest, documented limit:** the "did the submission actually
      succeed?" detection (`browser.submit_form` — URL change to
      thanks/confirm, or a "thank you"/"successfully submitted" text) is
      only verified against synthetic test fixtures. Confirming it against a
      real company's real post-submit page would mean actually sending a
      real, irreversible test application — deliberately not done. Revisit
      once Phase 8's manual VM smoke test has a plan for this (see that
      phase's own notes).

### Phase 6 — Pipeline hook
- [x] `pipeline._prepare_applications()`, called right after `_persist()`
      inside `run()`'s existing try block — off by default
      (`config.AUTO_APPLY_ENABLED`). Iterates the FULL open inbox (via
      `inbox_store.open_entries()` + `tracking_store.latest_actions()`, same
      as the dashboard's own inbox view), filters through
      `apply.prepare.is_eligible` and `apply_store.already_prepared_signatures`
      (skips `draft_ready`/`manual_required`/`submitted`, retries `failed`).
- [x] Strictly sequential (CLAUDE.md golden rule 2), `psutil`-based
      `_has_memory_headroom()` checked before each job — bails gracefully
      (not a crash) when under ~1GB free, logged and published as an event;
      remaining jobs retried automatically next run.
- [x] `cancellation.check()` each iteration — Kevin's Pausar/Cancelar reaches
      this stage too, same mechanism as the AI-scoring loop.
- [x] `EventBus` progress publishing (`phase="apply_prep"`) — picked up by
      the existing SSE pipe/dashboard for free, no new transport.
- [x] `docs/governance/ARCHITECTURE.md` updated with the new stage (also
      backfilled the EATP-031 inbox-accumulation step it was missing).
- [x] `tests/test_pipeline_apply_prep.py` — 7 tests (disabled-by-default,
      eligibility filtering, dismissed/applied skip, already-prepared skip
      vs. failed retry, memory bail-out, cancellation), `prepare_application`
      monkeypatched — a different test boundary than Phase 5's real-browser
      tests, same principle `test_pipeline.py` already uses for the AI layer.
      Full suite: 410/410.

### Phase 7 — Web + dashboard
- [x] `GET /applications` — signature-keyed state, mirrors `/eval/labels`'s
      shape exactly (merged client-side onto `/inbox` entries, no server-side
      job re-lookup needed).
- [x] `POST /applications/<signature>/send` — 404 if no draft, 409 if not
      `draft_ready`, 404 if the job fell out of the inbox; runs synchronously
      (single job, a few seconds) rather than via the SSE/background-thread
      machinery built for whole pipeline runs. `submit_application` is
      dependency-injectable on `create_app()`, same pattern as `pipeline_run`
      — route tests never launch a real browser.
- [x] `app.js`: `/applications` merged into `allJobs` the same way
      `/eval/labels` already is. Card badge ("Aplicación lista" /
      "Aplica manual"). Modal section: answers list + real "Enviar
      aplicación" button for `draft_ready`; a clear note for
      `manual_required`. `sendApplication()` mirrors `trackAction`'s
      optimistic-removal pattern on success (server already marks it
      "applied" via `tracking_store`, so `/inbox` naturally drops it).
- [x] CSS additions matching the existing badge/notice/summary-box language.
- [x] Tests: 6 new in `test_web_dashboard.py` (empty/populated `/applications`,
      send success + 404/409/404-job-missing paths). Full suite: 416/416.
- [x] Manual smoke check: real `uvicorn` process, real HTTP — `/` (200),
      `/applications` (200, `{}`), `/static/js/app.js` (200), plus
      `node --check` on the JS for syntax. **Honest limit:** no visual
      browser check — this sandbox has no display; the actual look (badge
      placement, modal layout) hasn't been eyeballed in a real browser yet.

### Phase 8 — Deploy prep
- [x] Kevin's sign-off on `psutil` (given in Phase 1) — in `pyproject.toml`
      + `DEPENDENCIES.md` already.
- [x] `deploy/setup_vm.sh`: added `uv run playwright install --with-deps
      chromium` as its own idempotent step (renumbered 6→7 steps);
      `deploy/README.md` updated to match.
- [x] Kevin's CV resolved: English version
      (`D:\Descargas\CV´s\CV_Kevin_Castillo_EN.pdf`, his call — Greenhouse/
      Lever skew US/global, matches the real forms already seen), copied to
      `rove-vm:~/rove/data/resume.pdf`.
- [x] **Real live smoke test on `rove-vm`** (Kevin's explicit approval for a
      tiny live-AI spend), staged at `~/rove_staging` first (`.env`/`data`
      symlinked from the live `~/rove`, never touched the production
      checkout) — `uv sync`, Chromium install, full non-browser test suite
      (389/390, 1 pre-existing test-order flake unrelated to this project,
      confirmed by re-running it alone). Then `prepare_application` against
      3 REAL jobs:
      - GitLab (from Kevin's actual inbox) → `manual_required`, reCAPTCHA —
        correctly detected, zero AI calls spent (short-circuits before the
        AI step).
      - Coinbase (from Kevin's actual inbox) → `manual_required`, Cloudflare
        challenge — correctly detected, zero AI calls spent.
      - Palantir/Lever (a real live posting, not currently in Kevin's own
        matches — used specifically to exercise the full live path,
        **`prepare_application` only, never `submit_application` — no real
        application was ever sent anywhere**) → real Gemini 503 → real Groq
        fallback → real, coherent, profile-grounded answers for 6 real
        questions (multi-select language pick, work-auth, visa sponsorship,
        a genuine paragraph about a real Bramvel/Factory-Costs project).
        The one required field with 600+ options (a real 3301-option
        university dropdown) correctly landed `unsupported` →
        `manual_required` overall, exactly as designed — no false
        `draft_ready`.
      - Memory: 392Mi→570Mi free, 4.8GB available throughout. Healthy.
- [x] **Real finding worth Kevin's attention, not a bug:** every standard
      `job-boards.greenhouse.io` company sampled (8/8 — GitLab, Figma,
      Discord, Webflow, Mixpanel, Amplitude, Vercel, Airtable) has a
      reCAPTCHA; every custom-domain Greenhouse embed sampled (4/4 —
      Coinbase, Stripe, Elastic, Asana, Instacart) didn't render a form in
      time (Cloudflare-style or similar). **Lever (Palantir) had neither.**
      Net: Greenhouse's real-world `draft_ready` rate for this company list
      may be at or near zero; Lever looks genuinely automatable. Worth
      revisiting whether the curated Greenhouse company list, or the
      captcha-fighting boundary itself, needs a product decision — Kevin's
      call, not something to silently work around.
- [x] **Real finding worth Kevin's attention, a content-accuracy concern:**
      the AI answered "Yes" to Palantir's "Are you legally authorized to
      work in the country for which you are applying?" — his profile only
      states Mexico work authorization, not explicit US authorization;
      "the country for which you are applying" is ambiguous (the employer's
      country vs. where he'd physically work remotely from). Not a code bug
      — a real instance of exactly the kind of answer Kevin said he'd trust
      the AI on, but worth him seeing concretely before this goes live for
      real US-based companies.

### Phase 9 — Verify & close
- [x] `pytest` green — 416/416, full suite, after every phase's changes
      including the post-smoke-test profile refinement.
- [x] Update ROADMAP status + total time
- [x] Write session notes below
- [x] Commit to git (CLAUDE.md §10) — one commit, clear message

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-30 | Phase 1 | ~35 min | Profile intake (CV read + Kevin interview), `psutil` installed, Notion updated (LinkedIn + portfolio live URL), `[application]` table + `Application` submodel shipped, docs updated. |
| 2026-08-30 | Phase 2 | ~15 min | `apply/store.py` (`ApplicationEntry`/`ApplicationStatus`, mirrors `inbox`/`tracking`), 7 tests green, `DATA-CONTRACTS.md` schema added. |
| 2026-08-30 | Phase 3 | ~50 min | Live-probed real Greenhouse (GitLab) + Lever (Palantir) apply forms with headless Chromium to ground the design in real DOM shape (found the reCAPTCHA, the Lever `/apply` URL pattern, the EEO React-Select decline options). Built `apply/browser.py` + fixtures + 9 tests, all green. Full suite: 376/376. |
| 2026-08-31 | Phase 3 (follow-up) | ~40 min | Kevin pushed back on leaving gaps merely "documented" — investigated both for real. Confirmed Coinbase's embed is a genuine Cloudflare bot-challenge (not fixable, added explicit detection instead). Fully implemented Lever's custom-card question types (text/radio/checkbox/select) by parsing the real `[baseTemplate]` JSON spec, live-verified against Palantir's board. 12 tests green, full suite 379/379. |
| 2026-08-31 | Phase 4 | ~45 min | `Provider.answer_questions` across the whole AI layer, `AiRouter.answer_questions`, application prompt template, `apply/questions.py`. 12 new tests + 5 pre-existing test-double fixes. Full suite: 389/389. |
| 2026-08-31 | Phase 5 | ~55 min | `apply/prepare.py` + `apply/submit.py`, both dependency-injectable with a `BrowserContext` for real-Playwright, zero-live-network testing via `context.route(...)`. 14 new tests covering captcha/no-form/Cloudflare/success/AI-silent/nav-error/failed-fill paths. Full suite: 403/403. |
| 2026-08-31 | Phase 6 | ~30 min | `pipeline._prepare_applications()` wired into `run()`, memory-bounded + cancellation-aware + EventBus-published. `ARCHITECTURE.md` updated. 7 new tests. Full suite: 410/410. |
| 2026-08-31 | Phase 7 | ~35 min | `/applications` GET + `/applications/<sig>/send` POST, `app.js` card badge + modal review/send UI, CSS. 6 new tests + a real (non-visual) `uvicorn` smoke check. Full suite: 416/416. |
| 2026-08-31 | Phase 8 | ~50 min | `setup_vm.sh`/`README.md` updated; real CV copied to the VM; real live smoke test against 3 real jobs (GitLab, Coinbase, Palantir) via a staged, non-production checkout — real captcha/Cloudflare detection confirmed, real AI answers confirmed, real 3301-option dropdown correctly capped, memory stayed healthy. Two real findings surfaced for Kevin (Greenhouse's real-world captcha rate; one ambiguous work-authorization answer). |
| 2026-08-31 | Phase 9 | ~15 min | Refined `profile.toml`'s `work_authorization` from the smoke test's real finding; logged the Greenhouse captcha-rate finding to `ROADMAP.md` Backlog + ADR-011 (Kevin's call, not resolved here); cleaned up the VM's temporary staging checkout; full suite re-verified (416/416); closed the project. |

**Total project time:** ~5h55m across one 2026-08-30/31 session (Phases 1-9).

## Session notes

Built the full auto-apply draft engine for Greenhouse/Lever: a new
`profile.toml` `[application]` table, `src/rove/apply/` (browser
read/fill/submit, AI question-answering, JSONL store, prepare/submit
orchestration), a pipeline hook (off by default via `AUTO_APPLY_ENABLED`),
and dashboard review/send UI. Every phase's real-world DOM shape was
live-probed against actual Greenhouse/Lever boards before being coded —
found and handled a real reCAPTCHA, a real Cloudflare embed, the real Lever
custom-question JSON schema, and validated the whole path end-to-end with
real (tiny, Kevin-approved) AI calls against a real live posting, never
sending an actual application anywhere.

Two real, live-verified findings are **not** resolved by this project,
logged for Kevin instead: (1) Greenhouse's real captcha rate among the
curated company list may make it near-unusable for full auto-submission —
Lever looks like the source that actually carries this feature's value;
(2) the AI's first real answer to a US company's "work authorization"
question was ambiguous/risky given Kevin only holds Mexico work
authorization — the profile's `work_authorization` text was refined with an
explicit disambiguation rule as a result, but the underlying ambiguity in
how such questions get asked is inherent, not something a prompt tweak
fully eliminates.

**Not started this session, by design:** EATP-035 (the unattended pre-run
submit sweep) — depends on Kevin watching real `draft_ready` output for a
few days first, per the whole point of splitting these two projects apart
(ADR-011 §7). `AUTO_APPLY_ENABLED` is still `0`; nothing changes in Rove's
actual daily behavior until Kevin explicitly flips it. Code is committed
locally but **not pushed to GitHub and not deployed to the live `rove-vm`
checkout** — both require Kevin's separate explicit go-ahead per CLAUDE.md
§10, asked for at the end of this session rather than assumed.
