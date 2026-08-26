# EATP-020 — Match quality & source balance (first real-run findings)

## Objective
Kevin ran the finished product manually for the first time (2026-08-14, real run
`data/results.json`, 25 min, 43 final jobs) and found four issues. This project fixes
all four, using that actual run's data as evidence rather than guessing:

1. The "Ejecutar búsqueda" launcher silently auto-starts the pipeline — Kevin never
   sees the idle screen with "Iniciar búsqueda" / "Limpiar caché".
2. LinkedIn is ~3x slower than legacy.
3. LinkedIn returns mostly U.S.-only postings (visa/citizenship/state-residency
   required) that Kevin can never actually take, even though nothing says "advanced
   English" outright — same blind spot as the language case, just geographic.
4. LinkedIn dominates the final list so heavily that other sources barely register,
   and the grade distribution is bimodal (mostly D, almost no B/C) with very few A+.

## Problems solved
New, raised directly by Kevin after his first real end-to-end run post-EATP-019
(2026-08-14). Extends P2/P15 (source balance, missing matches), P20 (source health —
lever/remoteok silently yielding 0), and the ADR-002/P8 remote-eligibility logic
(geographic eligibility is the same shape as the advanced-English hard gate, just
never built).

## Diagnosis (from the real run — `data/results.json`, started 2026-08-14T00:16Z)
- **Launcher**: `Rove - Ejecutar busqueda.bat` sets
  `ROVE_AUTOSTART=1`, which makes `scripts/run_web.sh` POST `/run` before
  opening the browser at all (see the script's own comment block). This was a
  deliberate EATP-019 design choice to save Kevin a click — but in practice it means
  he never sees the idle screen or the cache-reset button, which is worse. Confirmed
  in code, not a bug — a UX call that needs revisiting.
- **Source imbalance**: raw collected 532 jobs total. `source_health` shows LinkedIn
  alone yielded 321 (60% of everything collected) vs. occ 139, indeed 32, greenhouse
  14, remotive 13, computrabajo 11, himalayas 1, wwr 1 — and **lever and remoteok
  both yielded 0**, flagged `"posible bloqueo"` by the health check. Of the 43 jobs
  that survived gating and AI scoring, 32 (74%) are LinkedIn, 8 occ, 2 indeed, 1
  remotive. LinkedIn isn't just "popular", two other sources are silently dead.
- **U.S.-only jobs slipping through**: of the 32 kept LinkedIn jobs, 14 explicitly
  mention visa/citizenship/"United States"/work-authorization/state-residency in the
  description (grep-verified), despite `f_WT=2` (remote) + `location=México` in the
  search URL. LinkedIn's guest endpoint clearly doesn't actually restrict results to
  Mexico-eligible remote roles — `location` there acts more like a hint than a hard
  filter. `quality/filters.py`'s `gate()` has no geographic/work-authorization check
  at all today — only title exclusions, advanced-English, remote/hybrid, staleness,
  and dedup. `linkedin.py` already captures `location_raw` per job (`_build_job`,
  from the detail page's `.topcard__flavor--bullet`) but nothing downstream reads it.
- **The AI is already correctly catching these when it sees them** — this is the key
  finding for issue #4. Inspected the D-graded jobs directly: e.g. "Senior Power BI
  Developer" (ai_score 20, summary: *"La vacante está restringida a residentes de
  Estados Unidos"*), "Data Analyst- Remote from AZ/ NC" (ai_score 25, *"restricción
  obligatoria de residencia en estados específicos de EE. UU."*), "Senior Data
  Analyst - Investment Insight" (ai_score 40, *"Rol atado a la estructura corporativa
  de RBC en EE. UU."*). The scoring rubric (EATP-013) is doing its job — it's just
  being asked to judge (and burn AI quota on) jobs that should never have reached it.
  **Conclusion: the bimodal grade distribution is a downstream symptom of the missing
  geo/eligibility gate, not a scoring-rubric bug.** No changes planned to
  `scoring/evaluate.py` or the rubric itself — fixing the gate should be verified to
  fix the distribution as a side effect, not treated as a separate problem to solve
  by tuning AI weights.
- **LinkedIn speed**: `linkedin.py`'s listing phase (`_collect_term_ids`) is fully
  sequential — one `Client`, one page at a time across up to 9 search terms x 10
  pages, `gentle_pause(0.8, 2.2)` between every page. Detail-fetch already uses a
  3-worker `ThreadPoolExecutor` (`linkedin_api.fetch_job_details`). Since EATP-019
  moved LinkedIn fully onto the public guest endpoint (no login, no browser, no
  account-ban risk — see that charter's Phase 6), the account-safety reason for
  staying sequential no longer applies to listing the way it did when this was a
  real logged-in browser session; there's room to parallelize per-term listing the
  same way details already are.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `scripts/run_web.sh` | Autostart behavior (Phase 1). |
| `Rove - Ejecutar busqueda.bat`, `Rove - Ver resultados.bat` | The two launchers (Phase 1). |
| `src/rove/web/static/index.html` + `web/static/js/` | Idle screen / buttons (Phase 1, if the fix needs UI changes). |
| `criteria.toml` | Where `advanced_english`-style phrase lists live — geo/eligibility list goes here too (Phase 2). |
| `src/rove/quality/filters.py` | `gate()` — where the new eligibility check plugs in (Phase 2). |
| `src/rove/collectors/linkedin.py` | `location_raw` capture, listing loop to parallelize (Phase 2 & 4). |
| `src/rove/collectors/linkedin_api.py` | Existing `ThreadPoolExecutor` pattern to mirror for listing (Phase 4). |
| `src/rove/collectors/lever.py`, `collectors/remoteok.py` | Diagnose the two zero-yield sources (Phase 3). |
| `src/rove/config.py` | `ATS_COMPANIES`, `SEARCH_TERMS` — grow curated lists (Phase 3). |
| `docs/governance/EVALUATION-RUBRIC.md`, `docs/adr/ADR-002-remote-hard-gate.md` | Pattern to mirror for the new hard gate (Phase 2). |
| `docs/governance/SCRAPING-GOTCHAS.md` | Known per-source quirks, before touching any collector. |
| `data/results.json` (already inspected this session) | The evidence base for this whole charter. |

## Dependencies
- **Projects:** EATP-019 (done — this only makes sense against the shipped,
  HTTP-only LinkedIn collector and the launcher/cache-reset it built).
- **Libraries:** none new expected (parallelism uses stdlib
  `concurrent.futures`, already used in `linkedin_api.py`).

## Scope
**In (ordered easiest → hardest, per Kevin's usual preference):**
1. **Launcher UX (Kevin's call, confirmed)** — collapse the two `.bat` files into
   **one** launcher that always opens a landing screen with **three** explicit
   buttons: "Iniciar búsqueda", "Limpiar caché", "Ver dashboard de la última
   corrida". No auto-run, no auto-jump straight to old results — Kevin picks every
   time. `index.html` already has `startBtn` + `clearCacheBtn` on its idle state;
   needs a third action plus whatever state-routing changes make the landing screen
   show up every launch instead of only when there's no prior run.
2. **Fix LinkedIn's geo targeting AND listing speed together (merged Kevin's
   call, 2026-08-14 — was two separate phases, combined because both touch
   `linkedin.py`'s listing loop and are verified by the same live run)**:
   - *Geo*: `location=México` is already sent on every search, so the fix is not
     "add more filters downstream", it's making the site itself respect it.
     **Investigate live first**: confirm whether the guest search endpoint has a
     real, working geo parameter for remote jobs (LinkedIn's normal UI uses a
     `geoId` for the search region, not a free-text `location` string — the
     guest endpoint may respect `geoId` where it ignores `location` for `f_WT=2`
     results). This is also the mechanism the old legacy browser collector
     implicitly relied on (its `/jobs/search/` UI resolved `location=México`
     server-side into a real geoId before filtering) — legacy's filtering
     "just worked" for this same underlying reason, not because it used a
     browser. Only if a working geo param turns out to be a dead end does a
     minimal downstream check become the fallback (absolute-list discipline,
     same as `advanced_english` — never a blanket "reject non-Mexico").
   - *Speed*: parallelize `_collect_term_ids` across search terms (mirroring
     `fetch_job_details`'s worker-pool pattern) — this is the current
     architecture's version of what legacy's 4 parallel browser tabs did for
     speed, minus the browser/login overhead entirely.
   - **Note for Kevin**: legacy's exact browser-based collector (real login,
     `/jobs/search/` UI) can't just be restored — that's the same page EATP-019
     Phase 6 already confirmed is unscrapeable today (LinkedIn's 2026 redesign
     removed every stable selector; network-interception was tried and hit a
     dead end). The current HTTP-only guest-endpoint collector is the only
     viable base — this phase's job is to make it match what legacy achieved
     (real geo filtering, comparable speed) without reviving dead code.
3. **Source rebalance** — diagnose why `lever` and `remoteok` yielded 0 this run
   (dead API vs. genuinely-empty curated list vs. filter too strict) and fix or
   grow what's fixable (e.g. more Lever/Greenhouse companies in `ATS_COMPANIES`).
   Goal: other sources contribute enough that LinkedIn isn't 60-74% of everything by
   default — not by capping LinkedIn, but by growing the rest.
4. **Verification** — after phases 2-3, do a real live run and confirm: source
   distribution is less LinkedIn-dominated, the U.S.-only jobs are gone from the
   final list, LinkedIn is measurably faster, and the grade distribution has more
   B/C (not just A+/D) as a result — without touching the AI rubric itself.

5. **OCC speed regression (Kevin's report, 2026-08-14, after Phase 4's first
   verification run)** — ~6 min vs. legacy's ~1.5 min, despite both being
   plain sequential HTTP. Root cause: `gentle_pause()` before every single
   detail fetch, one at a time (absent in legacy). Fixed the same way as
   LinkedIn — kept the pause, parallelized detail-fetch across a worker pool.
6. **Indeed captcha banner stuck on screen (Kevin's report, same run)** —
   confirmed real bug: the collector never told the frontend when a captcha
   actually cleared, only the *next pipeline phase* (gate/prefilter/ai) wiped
   the notice, which could be minutes away or not visibly happen at all.
   Added a paired "resolved" event.

**Out:** changing `scoring/evaluate.py` or the AI rubric/weights (diagnosis says
that's not where the bug is); notifications; CV tailoring; Indeed's tab-count/
speed tradeoff (deliberate account-risk decision from EATP-006, revisit in
EATP-021); tightening `is_captcha_page`'s false-alarm detection (needs live
evidence to fix safely, EATP-021); anything else already in `ROADMAP.md`'s
Backlog section.

## Deliverables
- One launcher `.bat` (the other retired) opening a 3-button landing screen:
  Iniciar búsqueda / Limpiar caché / Ver dashboard de la última corrida.
- `linkedin.py`: fixed geo targeting (real `geoId`/working param) if the live
  investigation finds one — or, only if not, a minimal `criteria.toml` fallback
  list + `quality/filters.py` gate check, with a note on why the source-side fix
  wasn't possible.
- `lever.py`/`remoteok.py`: fix or documented root cause; `config.py` ATS list grown
  if that's the fix.
- `linkedin.py`: parallel listing phase + tests; before/after timing note.
- A short "before vs. after" note (counts + grade distribution) from a real
  verification run.

- **Kevin's explicit instruction**: don't reach for a new filter as the default
  answer to a geo problem — try to make the site's own location targeting work
  first. A downstream filter is the fallback, not the plan.

## Key design decisions & constraints
- **Site-side fix first.** Live-test LinkedIn's guest endpoint with a real `geoId`
  for México before touching `criteria.toml`/`gate()` at all.
- If a downstream fallback ends up necessary, it follows the exact same "absolute
  list only, never ambiguous, never a standalone title verdict" discipline as
  ADR-009 and the existing `advanced_english` list — ambiguous cases (e.g. "must
  overlap with U.S. business hours") stay out of a hard reject; only unambiguous
  disqualifiers (citizenship/visa/named-state residency) would count.
- Don't rebalance sources by throttling LinkedIn — grow the weak sources instead
  (matches CLAUDE.md's "quality over volume" but volume-of-*sources* is legitimately
  useful when the top source is this concentrated).
- Live network/browser diagnosis (Phase 3) burns real time against real sites —
  same discipline as EATP-019 Phase 6, confirm live behavior before assuming a fix.

## Definition of Done
- [ ] All 4 phases built, confirmed with Kevin between each
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left
- [ ] Checklist ticked, time logged
- [ ] ROADMAP status → ✅
- [ ] Session notes written
- [ ] Committed to git (CLAUDE.md §10)

## Estimated time
~2.5–4 h total across all 5 phases (Phase 3's live diagnosis of lever/remoteok is
the widest part of that range, same shape as EATP-019 Phase 6).

## Open questions for Kevin
- **Launcher UX**: ✅ resuelto — un solo `.bat`, pantalla con 3 botones (Iniciar
  búsqueda / Limpiar caché / Ver dashboard de la última corrida).
- **Geo targeting**: ✅ resuelto — primero investigar en vivo si LinkedIn tiene un
  parámetro que sí funcione (`geoId`); un filtro propio es solo el último recurso,
  no el plan por defecto.
