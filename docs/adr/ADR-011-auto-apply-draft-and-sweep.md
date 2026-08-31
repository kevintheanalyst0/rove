# ADR-011 — Auto-apply: headless-browser drafts, AI-only answers, sweep-based deadline

- **Status:** Accepted
- **Date:** 2026-08-30
- **Context:** Kevin lets Rove's inbox accumulate and doesn't have time to apply
  to every vacante by hand; the longer a good match sits, the more competing
  applicants it accumulates. He wants Greenhouse/Lever applications (Rove's two
  ATS-direct, login-free sources) filled and sent automatically, without a fixed
  Q&A bank (a similar approach in the legacy Career Radar predecessor "no quedó
  del todo bien"), and without a mandatory per-application review gate — but
  nothing should be lost, and nothing should linger past the next day's 7am run.
- **Decision:**
  1. Use headless Playwright (already a `pyproject.toml` dependency, currently
     scoped only to UI visual verification — repurposed here) to read and fill
     the *real* Greenhouse/Lever apply page, rather than replaying the form via
     raw HTTP POST. Neither collector's JSON API tells us whether a given
     company's board is static HTML or the JS-rendered "Job Board" embed;
     Playwright handles both without needing to know in advance.
  2. Screening questions are answered by AI, per application, from a new lean
     `[application]` profile table (salary, availability, work authorization,
     relocation, contact info) — never a fixed question→answer bank. Kevin's
     explicit call.
  3. No per-run cap on how many drafts get prepared — bounded only by actual
     memory/AI-quota headroom on the VM, checked before each sequential
     (never parallel) browser launch. Kevin's explicit call; if a job can't be
     prepared today, it's retried automatically on tomorrow's run.
  4. A captcha, login-wall, or unrecognized form shape gets the job marked
     `manual_required` and left alone — never fought unattended. Same lesson as
     EATP-033's Indeed removal.
  5. The "must send within ~24h, and before the next day's run" requirement is
     implemented as **one daily pre-run sweep** (EATP-035), not a per-job timer.
     Simpler, and it structurally guarantees "resolved before the next run"
     rather than relying on precise timestamp arithmetic.
  6. EEO/voluntary-disclosure-style questions always get a standing "prefer not
     to disclose" instruction in the AI prompt — independent of the
     review-trust decision above; this is the universally safe default for
     that question *type*, not a product choice Kevin needed to make.
  7. Delivered as two EATP projects: EATP-034 (draft engine + dashboard
     review/manual-send, usable and testable standalone) then EATP-035 (the
     unattended sweep, once 034's draft quality is validated on real jobs).
     Rollout staging only — by the time EATP-035 ships, behavior matches
     exactly what Kevin asked for (no mandatory review, auto-sent by deadline).
- **Consequences:**
  - Real, irreversible applications go out with AI-generated answers to
    consequential questions (salary, relocation) without Kevin seeing them
    first, once EATP-035 ships. Accepted risk, Kevin's explicit call — the
    `[application]` profile is the safety valve: garbage in the profile means
    garbage in every answer, so its accuracy matters far more here than for
    scoring.
  - Headless Chromium adds real memory pressure to a 1 OCPU/6GB ARM VM that
    also runs the always-on FastAPI server and the idle-reclaim keep-alive
    burn. Mitigated by strictly sequential processing and a pre-launch memory
    check; `AUTO_APPLY_ENABLED` defaults off until manually validated on the
    real VM.
  - AI question-answering shares the same daily per-provider quota counters as
    job scoring (`ai/usage.py` tracks by provider, not by feature) — a heavy
    apply day can eat into the budget scoring depends on. No separate
    safeguard beyond the existing quota-exhaustion fallback chain; revisit if
    this becomes a real problem in practice.
  - `docs/governance/DEPENDENCIES.md` still only documents the native-Windows
    runtime (EATP-025); this feature's browser automation runs primarily on
    the Oracle VM (Linux/ARM, EATP-032), a gap not fully closed by this ADR —
    flagged as documentation debt, same as `AUTOMATION.md` was in EATP-033.
  - **Live-verified 2026-08-31 (Phase 8 smoke test):** Greenhouse's real
    captcha rate among sampled companies is high enough (8/8 hosted boards,
    4/4 custom-domain embeds all blocked one way or another) that this
    source's real-world `draft_ready` rate may be near zero as currently
    curated; Lever worked cleanly live, no blocks. See the ROADMAP.md
    backlog entry — a product decision for Kevin, not resolved here.
- **Alternatives considered:**
  - Full-auto immediate send, no dashboard at all — rejected: Kevin wants the
    option to open the dashboard and review/edit/send early any time, even
    though nothing waits on him by default.
  - Fixed Q&A bank keyed by common question text — rejected, Kevin's explicit
    call based on a past bad experience with this approach in the legacy
    Career Radar predecessor.
  - Pure HTTP form replay (parse the static form, POST it directly, no
    browser) — deferred, not rejected outright: cheaper and simpler if every
    target company's board turns out to be static HTML, but unverified across
    the whole curated company list, and silently wrong for any JS-rendered
    board. Worth revisiting as an optimization once real-world data shows
    which boards are static.
  - Per-job 24h timer instead of a daily sweep — rejected as unnecessary
    complexity; a single daily sweep before the next run achieves the same
    guarantee with far simpler scheduling.
