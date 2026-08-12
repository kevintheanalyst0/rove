# Legacy System Review — JobMatchEngine

A full read-through of the current system (in `legacy/`), what it does well, and where
each of Kevin's 16 problems actually comes from in the code. This is the evidence base
for the rebuild. Read it once; then let the charters drive the work.

## What the legacy system is

A single Python package `jobmatch/` plus a Streamlit `app.py`. Flow:

```
collectors (linkedin, indeed, occ, computrabajo) → per-source JSON
        → merge.py (dedup) → jobs.json
        → process.py: matcher (rule score) → top-N → Gemini (parallel batches)
        → latest_jobs.json → Streamlit app renders results
```

**It is not badly built.** A prior refactor already did good things we keep as ideas:
centralized `config.py`, a single `models.py` schema, atomic `storage.py`, shared
`filters.py`, resumable batches, and adaptive rate-limiting for Gemini. The rebuild is
**not** because the code is a mess — it's to fix **quality, source coverage, remote
correctness, cache correctness, AI robustness, and the terminal-only UX**, and to put
it under a clean, session-based governance model.

## Strengths worth carrying forward

- **Single config source of truth** (`config.py`) — keep this idea.
- **Atomic writes** (`storage.py`, temp-file + `os.replace`) — keep.
- **Search terms in Spanish** — correct instinct for the local market; keep + expand.
- **HTTP-only collectors for OCC/Computrabajo** — fast, no browser; keep the pattern.
- **LinkedIn guest detail API** — clever; browser only lists IDs, details via HTTP.
- **Resumable Gemini batches + daily-quota pause** — good; generalize it.
- **Early title/company rejection before fetching detail** — saves requests; keep.

## Problem-by-problem root cause

### P1 — Collector methodology/efficiency
Collectors each re-implement their own loop, threading, and pagination. They work but
share no common contract, so quality rules and pacing drift per source. **Fix:** a base
`Collector` interface + shared browser/HTTP/pacing helpers (EATP-003).

### P2 / P3 / P15 — Only 4 platforms; missing good jobs; high competition
Sources are the 4 most crowded consumer boards. The best remote roles for Kevin's
profile often live on **ATS boards (Greenhouse / Lever / Ashby / Workday)** and
**remote-first boards (Remotive, We Work Remotely, RemoteOK, Himalayas)** and LatAm
tech boards (**Get on Board / Torre**), which the system never touches. These have
**clean public JSON**, little/no captcha, and far less competition. **Fix:** EATP-007/008
+ ADR-005 add high-signal, API-friendly sources (while Indeed is optimized, not dropped).

### P4 / P6 — Volume without quality; junk & off-role results
Two causes:
1. The quality gate is thin. `filters.py` blocks some titles and "advanced English",
   but "analista de datos" search strings on crowded boards still return graphic-design
   and senior-architect roles that slip past keyword filters.
2. The rule matcher only *scores*; it never *rejects*. Everything reaches Gemini, and
   Gemini's criteria (see P7) then over-score off-role jobs.
**Fix:** stronger multi-layer gates (EATP-009/010) + a matcher repurposed as a real
pre-filter with reject power (EATP-013) + a fixed AI rubric (EATP-002/013).

### P5 — Indeed captchas
`indeed.py` drives a real Chromium with a persistent profile and threads several tabs
navigating fast. That pattern trips Indeed's bot detection quickly, hence frequent
captchas that need manual solving. **Fix:** Indeed is **kept and optimized** (EATP-006) — gentler human-like pacing,
stealthier browser, and event-based captcha handling so a captcha never fails the run —
**and** we add API-friendly Tier-1 sources (ADR-005) so Indeed isn't the only path.
Indeed stays a first-class source; it's made robust, not dropped.

### P7 — Gemini criteria wrong ("B" grade with "No cons")
Root cause is a **grade/score mismatch**, not (only) the prompt. `matcher.py._grade()`
maps a score to A/B/C on the **matcher** score, while the app shows a grade derived
elsewhere; and the AI prompt tells the model to return an **empty** contras array when
there are no real cons ("If there are no meaningful disadvantages, return an empty
array"). So a high-scoring job legitimately has empty contras — but the displayed
letter grade comes from a different scale, producing the "B with No cons" nonsense.
Separately, off-role jobs (finance intern, process-engineering *subdirector*) scored 90
in the real data because the rubric rewards responsibility overlap too loosely. **Fix:**
one canonical score→grade mapping used everywhere, a rubric that hard-caps off-role and
non-remote jobs, and post-validation that repairs contradictory outputs (EATP-002/013).

### P8 — Non-remote jobs leak through with `remote:false`
`detect_remote()` is keyword-only and runs on title+description; OCC/Computrabajo
**hardcode `remote=True`** regardless. There is **no final remote gate**: `process.py`
sends everything to the app, and 57 of 123 jobs in the last real run had
`remote:false` yet were shown. Hybrid roles ("2 días en oficina") pass because nothing
checks for *anti-remote* signals. **Fix:** a strict remote hard-gate with positive
signals AND absence of hybrid/onsite signals; ambiguous → "remoto: incierto", and the
default output shows only confirmed-remote (EATP-009, ADR-002).

### P9 — Daily-reposted jobs keep reappearing (Capgemini "FBS Analyst")
The permanent cache (`analyzed_jobs.json`, 913 records) is keyed on the **per-site
job_id**. LinkedIn/Indeed mint a **new id every day** for the same reposted vacancy, so
the cache never recognizes it and it reappears forever. **Fix:** a **content-signature**
cache keyed on normalized (company + title + description head), with a first-seen date,
so the same posting is recognized regardless of its volatile id (EATP-010, ADR-001).

### P10 — Matcher has no purpose
It computes a score that only *ranks* which jobs go to the AI first — and since
`AI_TOP_JOBS=500` exceeds the ~177 jobs ever collected, effectively **everything** goes
to the AI, so the ranking changes nothing. **Fix:** repurpose the matcher as a genuine
**cheap pre-filter that rejects** clearly-bad jobs and *caps* how many reach the AI, so
AI budget goes only to plausible matches (EATP-013).

### P11 — Gemini returns malformed JSON sometimes
`ai.extract_json()` does a best-effort brace/bracket scan. It usually works but has no
schema enforcement and no repair path; a truncated or fenced response can still throw.
**Fix:** provider-native structured output (JSON schema / `response_format`) where
available, plus a tolerant parse-and-repair fallback and per-item validation
(EATP-012).

### P12 — Gemini free tier tiny; 503 still charged; want a free cloud alternative
Confirmed externally: Google cut **Gemini 2.5 Flash** free tier to ~20 requests/day in
late 2025. A `503` still consumes a call. **Fix:** a **multi-provider AI layer**
(EATP-012, ADR-003) that prefers **Groq** (free, fast, ~1,000 req/day, OpenAI-compatible)
and **Gemini 2.5 Flash-Lite** (~1,000–1,500 req/day, huge TPM), with automatic fallback.
All cloud-hosted; nothing runs on Kevin's machine.

### P13 / P14 — ~11–12 min per run; want faster, but quality first
Most time is browser scraping (LinkedIn/Indeed) + sequential-ish detail fetches. **Fix:**
lean on fast HTTP/JSON sources (EATP-007/008), tighten concurrency safely, and give the
orchestrator explicit speed-vs-exhaustiveness knobs (EATP-014), defaulting to quality.

### P16 / R11 / R12 — Not in GitHub; terminal-only; too many manual steps
The system lives in a PC folder, runs via `.bat` files and a terminal, and needs manual
captcha/login. **Fix:** build in Ubuntu under Git, publish to GitHub at the end
(EATP-018); replace the terminal with a **local web page** showing a Windows-style dots
spinner + live status (EATP-015, ADR-004); minimize manual steps across EATP-014/015/018.

## Things we deliberately drop or defer

- **CV tailoring (`jobmatch/cv/`)** — Windows/Word-COM only; not relevant to the urgent
  goal. Moved to backlog (redesign cross-platform later).
- **Ollama / local models** — already removed by Kevin; stays removed (AI is cloud-only).
- **Streamlit** — replaced by a FastAPI + static web page so there's no terminal window
  in the user's face (ADR-004).

---

## Problems Kevin did NOT list, that we also fix (proactive)

Kevin flagged the problems he could see; a deeper code audit surfaced these, which are
relevant and now have their own scope. Each is an ADR + a project.

### P17 — AI mapping is positional, not id-based (silent correctness bug)
`pipeline/ai.py` + `process.py` label jobs `VACANTE_1…N` and match the AI's results back
**by order**. If the model reorders/drops/duplicates an item (LLMs do this), the wrong
analysis attaches to the wrong job — and Kevin can't tell. A job could show pros/contras
from a different posting. **Fix:** stable-id round-trip (ADR-006), enforced in EATP-012/013.

### P18 — No run history / no "new since last run"
Output is overwritten each run; there's no memory of past runs. Kevin re-sees the same
jobs every time and can't tell what's actually new. This partly explains the "nothing
good ever shows" feeling (P15): it's often the *same* jobs re-shown. **Fix:** run-history
store (ADR-007), EATP-010; a NEW badge in the UI (EATP-016).

### P19 — No applied/dismissed tracking
No way to mark a job "applied" or "not interested", so good jobs get lost in the noise
and rejected ones keep reappearing. For a multi-week hunt this is a real gap. **Fix:**
tracking (ADR-007), EATP-016 — dismissed jobs are hidden from future runs.

### P20 — No source-health detection (silent scraper failure)
If a scraper breaks (layout change, IP block, captcha wall), it just yields nothing and
the run still looks "successful". Nobody notices a whole source went dark — dangerous for
unattended runs. **Fix:** per-source health vs. a rolling baseline (ADR-008), EATP-011.

### P21 — Description quality varies by source
The AI judges on `description`, but some sources return short/truncated text
(LinkedIn guest API, some Computrabajo cards). Poor descriptions → poor AI judgments,
both false positives and false negatives (feeds P15). **Fix:** a description-quality flag
so scoring can down-weight/skip thin postings (EATP-004, used in EATP-013).

### P22 — No way to measure if match quality actually improved
Nothing verifies the rebuild surfaces *better* jobs rather than just *different* ones.
**Fix:** a lightweight match-quality harness (Kevin labels a handful good/bad → precision
report) so P4/P15 are validated with evidence, not vibes (EATP-017).

### P23 — Scraping ToS / account-ban risk & fingerprint fragility
Driving Kevin's logged-in LinkedIn/Indeed hard risks bans and burns his real accounts.
**Fix:** fetch LinkedIn details via the no-login guest API; keep browser pacing gentle;
make login/captcha event-based and skippable so the system never hammers his main account
(EATP-005/006, plus the no-`input()` rule in the collector framework EATP-003).
