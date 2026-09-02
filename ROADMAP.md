# ROADMAP — Rove

Rove is the rebuild of **JobMatchEngine**: a remote-first job-discovery engine
for Kevin. The build is split into sequential projects (`EATP-001` … `EATP-018` were the
original launch scope; `EATP-019+` are post-launch work opened after Kevin started using
the product),
grouped into logical blocks. **Claude Code works one project per session.**

---

## Cómo usar este repo (para Kevin)

1. Abre Claude Code en Ubuntu, dentro de esta carpeta.
2. Escribe: **"Trabajemos en EATP-001"** (siempre en orden, empezando por el 001).
3. Claude lee el roadmap y el charter, revisa dependencias y te devuelve un
   **plan + tiempo estimado + lo que necesita de ti**. No construye todavía.
4. Cuando estés de acuerdo, responde **"sigue"** y construye por fases, confirmando
   contigo entre cada una.
5. Al terminar, el proyecto queda ✅ y pasas al siguiente.

Reglas completas del comportamiento de Claude: ver `CLAUDE.md`.

---

## Logical blocks (this is the order, and why)

Two hard rules drive the order (Kevin's): **all scraping is solved before any AI**, and
**all AI is solved before the app**.

- **Block A — Base (001–002):** structure, contracts, and Kevin's criteria. No scraping/AI.
- **Block B — Scraping & data quality (003–011):** the framework, every collector
  (Indeed was kept & optimized here, then removed entirely in EATP-033 — see that
  project), plus the gates/dedup/cache/history/health that turn raw scrapes into a
  clean, remote-only, de-duplicated, non-repeating list. *When this block is done,
  "the scraping is solved."*
- **Block C — AI (012–013):** the multi-provider AI layer and the scoring pipeline.
  *Starts only after Block B.*
- **Block D — Orchestration (014):** wire it all into one resumable, memory-safe run.
- **Block E — App (015–016):** the web UI (runner spinner, then dashboard + tracking).
  *Starts only after AI is solved.*
- **Block F — Verify & ship (017–018):** prove match quality improved, harden, publish.

## Status legend
⬜ Not started · 🚧 In progress · ✅ Done · ⛔ Blocked

## Project sequence

| ID | Project | Block | Status | Depends on | Complexity | Total time |
|----|---------|-------|--------|-----------|-----------|------------|
| **EATP-001** | Foundation & core contracts | A | ✅ | — | Medium | ~25 min (2026-08-12) |
| **EATP-002** | Candidate profile & criteria | A | ✅ | 001 | Light-med | ~6 min (2026-08-12) |
| **EATP-003** | Collector framework & plumbing | B | ✅ | 001 | Medium | ~40 min (2026-08-12) |
| **EATP-004** | HTTP collectors — OCC & Computrabajo | B | ✅ | 003 | Light-med | ~1 h (2026-08-12) |
| **EATP-005** | LinkedIn collector (refactor + harden) | B | ✅ | 003 | Medium | ~2.5 h (2026-08-12) |
| **EATP-006** | Indeed collector — optimize & de-captcha | B | ✅ | 003 | Medium | ~1.8 h (2026-08-12) |
| **EATP-007** | New sources — remote-first boards | B | ✅ | 003 | Light-med | ~45 min (2026-08-12) |
| **EATP-008** | New sources — ATS + LatAm boards | B | ✅ | 003 | Medium | ~1 h (2026-08-12) |
| **EATP-009** | Quality gates — filters + remote hard-gate | B | ✅ | 002 | Medium | ~40 min (2026-08-12) |
| **EATP-010** | Dedup, content-signature cache & run history | B | ✅ | 001, 009 | Medium | ~45 min (2026-08-12) |
| **EATP-011** | Source health & self-check | B | ✅ | 003–008, 010 | Light | ~35 min (2026-08-12) |
| **EATP-012** | Multi-provider AI layer | C | ✅ | 001, 002 | Medium | ~45 min (2026-08-12) |
| **EATP-013** | Scoring & evaluation pipeline | C | ✅ | 002, 009, 012 | Medium | ~25 min (2026-08-12) |
| **EATP-014** | Orchestrator & resumable/memory-safe run | D | ✅ | 004–011, 013 | Medium | ~9 min (2026-08-12) |
| **EATP-015** | Web UI — backend + runner spinner | E | ✅ | 014 | Medium | ~45 min (2026-08-12) |
| **EATP-016** | Web UI — results dashboard + job tracking | E | ✅ | 010, 014, 015 | Medium | ~13 min (2026-08-12) |
| **EATP-017** | Match-quality evaluation harness | F | ✅ | 013, 014 | Light-med | ~35 min (2026-08-12) |
| **EATP-018** | QA, hardening, automation & GitHub publish | F | ✅ | all | Medium | ~1h10 (2026-08-12) |
| **EATP-019** | Post-launch fixes: captcha/browser UX, self-serve launcher, cache reset, source reliability | — | ✅ | 018 | Medium-High | ~4h10 (2026-08-13) |
| **EATP-020** | Match quality & source balance: launcher UX, LinkedIn geo/eligibility gate, source rebalance, LinkedIn speed | — | ✅ | 019 | Medium-High | ~2h55 (2026-08-15) |
| **EATP-021** | Collector speed in the full pipeline + Indeed captcha/tab tradeoff | — | ✅ | 020 | Medium | ~1h05 (2026-08-15) |
| **EATP-022** | LinkedIn & Indeed: close the speed gap with legacy (real-browser listing back for LinkedIn, tab/pacing tuning for Indeed) | — | ✅ | 021 | Medium-High | ~1h30 (2026-08-15) |
| **EATP-023** | Final polish: window focus, no visible terminal, auto-shutdown on tab close | — | ✅ | 022 | Medium | ~1h55 (2026-08-15) |
| **EATP-024** | Pausar/Cancelar reliability + Indeed browser visibility | — | ✅ | 023 | Medium | ~1h25 (2026-08-16) |
| **EATP-025** | Dead-browser hang fix + migration out of WSL to native Windows | — | ✅ | 024 | High | ~2h30 (2026-08-17/18) |
| **EATP-026** | API surface hardening + adversarial input tests (Security Hardening initiative) | — | ✅ | — | Light-Medium | ~1h20 (2026-08-19) |
| **EATP-027** | Remove LinkedIn as a source entirely | — | ✅ | 026 | Medium | ~35 min (2026-08-21) |
| **EATP-028** | English-requirement classification (reject/compatible/indeterminate) + per-run funnel diagnostic + expanded search terms | — | ✅ | 027 | Medium | ~30 min (2026-08-21) |
| **EATP-029** | Cache observability — "Ver cacheadas" view + manual reset | — | ✅ | 028 | Light-med | ~40 min (2026-08-21) |
| **EATP-030** | New sources — Hireline, WeRemoto, RemotoJob shipped; LaPieza + Glassdoor spiked and dropped (see Backlog) | — | ✅ | 029 | Medium-High | ~1h40 (2026-08-21) |
| **EATP-031** | Accumulated inbox — jobs persist across runs until applied/dismissed | — | ✅ | 030 | Medium | (2026-08-25/26) |
| **EATP-032** | Deploy to an always-on Oracle Cloud VM (Querétaro), reachable from Kevin's phone | — | ✅ | 031 | High | ~3h across two sessions (2026-08-26/27) |
| **EATP-033** | Remove Indeed as a source entirely | — | ✅ | 032 | Medium | ~1h (2026-08-27) |
| **EATP-034** | Auto-apply draft engine (Greenhouse & Lever) — headless-browser fill, AI-answered screening questions, dashboard review/manual-send | — | ✅ | 032, 033 | High | ~5h55m (2026-08-30/31) |
| **EATP-035** | Unattended pre-run submit sweep — sends pending drafts before the next day's run | — | ✅ | 034 | Light-med | ~40 min (2026-09-01) |

> **EATP-027 through 030** come from a job-search improvement backlog Kevin had
> drafted with ChatGPT and pasted into Notion (Rove page, 2026-08-21),
> then designed down to size in a Claude Code conversation before any charter was
> written. Two things were cut from ChatGPT's original version during that design
> pass: (1) all whitelist-based enterprise ATS platforms (Ashby, SmartRecruiters,
> Recruitee, Teamtailor, Breezy HR, BambooHR, Workday, Eightfold, iCIMS, Jobvite,
> Oracle/Taleo, SAP SuccessFactors, Dayforce, ADP) — same operating model as
> Greenhouse/Lever (`config.ATS_COMPANIES`), which means a hand-maintained company
> watchlist per platform forever; Kevin decided that's not worth it for platforms
> he isn't already invested in, while Greenhouse/Lever stay exactly as they are
> since they're sunk cost and already working; (2) Get on Board was in ChatGPT's
> list too, but it's already a documented dead end from EATP-008 (see Backlog
> below) — no discoverable public API. **EATP-030 must spike each new source's
> real endpoint viability before writing a full collector, same lesson.**
>
> **Rove closed out 2026-08-15** (EATP-023), reopened for EATP-024
> (2026-08-16) and again for EATP-025 (2026-08-17/18).

> **EATP-025** started as "LinkedIn hangs the run" and ended as a platform move.
> Root cause of the hang: `page.quit()` issues the same timeout-less `Browser.close`
> CDP call as everything else, so against an already-dead Chrome it blocked forever —
> and it sat in a `finally`, outside every bound added for the collecting work.
> Fixed with `browser.close_page()` (bounded quit, then force-kill regardless).
>
> What kept killing Chrome in the first place was WSLg's virtualized GPU. Kevin
> then pointed out the fact that reframed everything: **legacy ran natively on
> Windows, never under WSL** — so its stability never validated any of these
> settings here. The project moved to `D:\Development\Rove` on native
> Windows (Python 3.12 via `uv`). The WSL copy stays as a backup.
>
> The move immediately surfaced two real Windows bugs the WSL-only test runs could
> never have caught: `signal.SIGKILL` doesn't exist on Windows (it would have
> crashed the "Cancelar" button), and `Path.read_text()` without an explicit
> encoding reads cp1252 there, which breaks on any accented Spanish text.
>
> **Update, 2026-08-19:** the WSL copy (`~/Projects/rove`) was deleted.
> During EATP-026 planning it caused a real mix-up — a design/build session targeted
> it by mistake, unaware of this migration, since it looked current. Kevin decided
> the confusion risk outweighed keeping it as a backup; this native-Windows repo
> (`D:\Development\Rove`) is now the only copy. Before deleting, `.env` was
> confirmed identical and `data/` confirmed to have nothing the Windows copy didn't
> already have (Windows had strictly more: real run history, results, cache).
>
> **This repo's `origin` was pointing at that now-deleted WSL path** (that's how it
> got cloned during the EATP-025 migration) — fetching from it started failing
> immediately after the deletion. Repointed `origin` straight to GitHub
> (`git@github.com:kevintheanalyst0/rove.git`) instead. Local is currently
> **4 commits ahead of GitHub** (a3b0b38, 29bcd25, 333a871, a4f7fe4) — not pushed
> automatically; push only with Kevin's explicit go-ahead, per CLAUDE.md §10.

> **EATP-026** opened 2026-08-19 as part of the cross-repo "Security Hardening —
> Portfolio, Rove y Snippets" initiative (tracked in Notion; Portfolio and
> Snippets have their own equivalent projects in their own repos). Independent of
> 001-025 — no dependency either way. Built and verified in this native-Windows repo.
> See `docs/adr/ADR-010-origin-host-validation-strategy.md` and the SEC-#
> traceability note below.

> Fill **Status** and **Total time** as each project completes. The **Complexity** column
> exists so no project balloons: they're all sized Medium-ish, with a couple intentionally
> Light (011, 017) — quick sessions. If any project starts feeling like a 300k-token
> monster mid-build, STOP and split it (CLAUDE.md §3).

## Dependency graph (build order)

```
A: 001 -> 002
B: 001 -> 003 -> 004
                 |-> 005
                 |-> 006   (Indeed: kept + optimized, then removed in EATP-033)
                 |-> 007
                 |-> 008
   002 -> 009 -> 010 -> 011   (011 also needs 003-008)
C: {001,002} -> 012 ;  {002,009,012} -> 013
D: {004-011, 013} -> 014
E: 014 -> 015 -> 016   (016 also needs 010)
F: {013,014} -> 017 ;  all -> 018
```

Plain order: **001 -> 002 -> 003 -> 004 -> 005 -> 006 -> 007 -> 008 -> 009 -> 010 -> 011
-> 012 -> 013 -> 014 -> 015 -> 016 -> 017 -> 018.**

---

## Traceability — problems -> projects

Kevin's stated problems are **P1-P16 / R11-R12**. Problems surfaced by our own audit
(things Kevin didn't list) are **P17-P23** — see `docs/diagnosis/LEGACY-SYSTEM-REVIEW.md`.

| # | Problem / request (short) | Solved in |
|---|---------------------------|-----------|
| P1  | Collector methodology/efficiency unclear | EATP-003, 004-008 |
| P2  | Only 4 platforms; LinkedIn low visibility; competition | EATP-005, 007, 008 |
| P3  | Want broader search across more platforms | EATP-007, 008 |
| P4  | Not just "more" — much higher **quality** | EATP-009, 013 (+017 verifies) |
| P5  | Indeed captchas | EATP-006 (kept & optimized), then **EATP-033 (removed entirely)** |
| P6  | Junk / off-role vacancies | EATP-009, 013 |
| P7  | Gemini criteria wrong ("B" with "No cons") | EATP-002, 013 |
| P8  | Filter lets non-remote (hybrid/onsite) through | EATP-009 (ADR-002) |
| P9  | Daily-reposted jobs reappear | EATP-010 (ADR-001) |
| P10 | "Matcher" has no purpose | EATP-013 (pre-filter with reject+cap) |
| P11 | Gemini returns malformed JSON | EATP-012 |
| P12 | Gemini free tier tiny; 503 charged; want free cloud alt | EATP-012 (ADR-003) |
| P13 | Run takes ~11-12 min; want faster | EATP-014 |
| P14 | Quality > speed, but cap excessive runtime | EATP-013, 014 |
| P15 | Feels like good jobs are missed | EATP-007, 008, 013 (+017 verifies) |
| P16 | Not in GitHub; build in Ubuntu, publish at end | EATP-018 |
| R11 | No terminal -> web page with spinner + status | EATP-015 (ADR-004) |
| R12 | Minimize manual actions | EATP-014, 015, 018 |
| **P17** | *AI mapping is positional -> mis-attributed analyses* | EATP-012, 013 (ADR-006) |
| **P18** | *No run history / no "new since last run"* | EATP-010, 016 (ADR-007) |
| **P19** | *No applied/dismissed tracking* | EATP-016 (ADR-007) |
| **P20** | *No source-health detection (silent scraper failure)* | EATP-011 (ADR-008) |
| **P21** | *Description quality varies by source* | EATP-004, 013 |
| **P22** | *No way to measure if quality improved* | EATP-017 |
| **P23** | *Scraping ToS / account-ban risk* | EATP-003, 005, 006 |
| **P24** | *Title-only judgment buries good jobs / waves through bad ones (ADR-009)* | EATP-002 (done), 003-008, 009, 013 |
| P25 | Fraudulent/ghost companies mass-posting to harvest data (esp. LinkedIn) | EATP-002 (blocklist, done), 009, 013 |
| P26 | LinkedIn collector is fragile and high-maintenance (CAPTCHA, login walls, geo/rate limits) for the yield it produces | EATP-027 |
| P27 | Ambiguous English-requirement phrasing ("professional English", "English required", "fluent") gets hard-rejected today with no distinction from genuinely explicit C1/C2/native requirements | EATP-028 |
| P28 | No per-run funnel diagnostic (collected/duplicate/stale/non-remote/English-rejected/cache-hidden/prefiltered/sent-to-Gemini by source) | EATP-028 |
| P29 | 30-day signature cache suppresses repeats but isn't inspectable or manually resettable | EATP-029 |
| P30 | Source coverage still thin outside the current 10 collectors; untested LatAm-market boards | EATP-030 |
| P31 | Indeed's captcha volume makes it unworkable for an unattended server (EATP-032's whole point) — Kevin used to solve them by hand, no one's watching the screen on a headless VM | EATP-033 |
| P32 | Rove needs to run unattended (e.g. 7am daily) without Kevin's laptop, reachable from his phone to apply/dismiss, with nothing lost if he doesn't check in for days — the actual reason this repo forked off Career Radar in the first place, not just the rename | EATP-031, 032 |
| P33 | Vacantes se acumulan en el inbox sin que Kevin tenga tiempo de aplicar; para cuando aplica, ya se llenaron de competidores — quiere aplicación automática a Greenhouse/Lever, sin banco de preguntas fijo, sin obligar revisión manual, pero sin dejar nada pendiente después de la siguiente corrida diaria | EATP-034, 035 |

> P26-P30 are from the 2026-08-21 job-search backlog (Kevin + ChatGPT, trimmed in a
> Claude Code design conversation — see the note above the project table). P31/P32 are
> Kevin's own, from the fork's founding motivation and a decision made mid-EATP-032 —
> documented here after the fact along with EATP-031-033 themselves (built in earlier
> sessions without the usual charter/checklist/ROADMAP ceremony; backfilled 2026-08-27).
>
> Bold = problems we surfaced that Kevin didn't list. P25 isn't bold — it's Kevin's own,
> just recalled later than the original P1-P16 pass.
>
> **P24 detail:** Kevin caught this directly — a legacy vacancy titled "Analista
> administrativo" was genuinely excellent but got buried because the title alone looked
> unremarkable (he only found it by manually checking the cache in VS Code); the mirror
> risk is a friendly title ("Data Analyst") hiding an off-field job. See
> `docs/adr/ADR-009-title-is-a-signal-not-a-verdict.md` — every project that touches
> title-based filtering (collectors 003-008, quality gates 009, matcher/AI 013) must
> respect it: only a short absolute keyword list may hard-reject on title alone;
> everything else is judged on the full job text.
>
> **P25 detail:** see `docs/governance/SCRAPING-GOTCHAS.md` §6-7 — the blocklist
> mechanism already exists (`criteria.excluded_companies`, currently just BairesDev +
> Indi Staffing Services) but is almost certainly incomplete; grow it as Kevin names
> more, and keep the door open for a behavioral heuristic in EATP-009/013 rather than
> relying on the static list alone.

### Security Hardening initiative (separate id space: SEC-#)

Not part of the P#/R# job-search backlog above — tracked separately because it's a
cross-repo initiative (Notion: "Security Hardening — Portfolio, Rove y
Snippets", 2026-08-19) that also touches the `portfolio` and `snippets` repos, each
with its own equivalent project. Only the Rove items are listed here.

| # | Item | Origin | Solved in |
|---|------|--------|-----------|
| SEC-12 | API keys of AI providers only in `.env`, never committed | Kevin | Already true (verified — `.env` never tracked, only `os.getenv` in source) |
| SEC-13 | GitHub Secret Scanning + Push Protection active | Kevin | Already true (confirmed enabled) |
| SEC-14 | Audit git history for leaked keys | Kevin | Already true (full-history audit found no real keys) |
| SEC-3 | Validate Host/Origin on the local server | Kevin | EATP-026 |
| SEC-4 | Harden `/run`, `/reset`, `/cancel` | Kevin | EATP-026 |
| SEC-5 | Tests against prompt injection via malicious job descriptions | Kevin | EATP-026 |
| **SEC-15** | *Host/Origin gap is CSRF/DNS-rebinding-class against routes with destructive side effects (not just generic hardening); `/track` and `/eval/label` belong in the same fix* | **AI** | EATP-026 |

> Bold/italic = surfaced by the AI during the 2026-08-19 audit, not on Kevin's original
> Notion checklist. Numbering continues the same SEC-# scheme used in the Portfolio and
> Snippets repos' own charters, for cross-repo reference back to the original Notion
> page and the design conversation — the ids are not otherwise meaningful inside this
> repo alone.

---

## Backlog (not scheduled)

- **Auto-apply (EATP-034): Greenhouse's real-world captcha rate may make it
  near-unusable for full auto-submission.** Live-verified 2026-08-31 (that
  project's Phase 8 smoke test): every standard `job-boards.greenhouse.io`
  company sampled (8/8 — GitLab, Figma, Discord, Webflow, Mixpanel,
  Amplitude, Vercel, Airtable) has a reCAPTCHA on submit; every custom-domain
  Greenhouse embed sampled (4/4 — Coinbase, Stripe, Elastic, Asana) didn't
  render a form within the automation's wait window (Cloudflare-style or
  similar). Lever (Palantir), by contrast, had neither and fully worked live.
  Not fixed by EATP-034 — fighting either kind of bot-protection unattended
  is explicitly against this repo's own precedent (Indeed/EATP-033,
  Glassdoor/EATP-030). Worth a future call, Kevin's: whether `config.
  ATS_COMPANIES["greenhouse"]` should be re-curated toward captcha-free
  boards specifically for this use case, or whether Greenhouse stays mostly
  a "surfaces the job, Kevin applies by hand" source while Lever carries the
  real auto-apply weight.
- **CV tailoring / cover letters** — legacy `jobmatch/cv/` is Windows/Word-COM only; not
  urgent. Revisit post-018, redesigned cross-platform.
- **Automatic ATS company discovery** (beyond the curated list in EATP-008).
- **Richer notifications** (Kevin declined the simple A-grade alert planned for
  EATP-018, 2026-08-12 — no notification channel exists; revisit only if he asks).
- **"Hide all from this company"** tracking option (beyond per-posting dismiss).
- **Get on Board / Torre as real sources** (EATP-008 investigated, didn't ship): Get on
  Board has no discoverable public API (client-rendered SPA, no JSON-LD/RSS found);
  Torre's search endpoint ignores every query/pagination param sent and always returns
  the same static ~10-result snapshot. Revisit only if a real endpoint is found —
  don't re-attempt the same guesses.
- **LaPieza / Glassdoor as real sources** (EATP-030 spiked live, 2026-08-21, didn't
  ship): LaPieza is a client-rendered Next.js app — no `__NEXT_DATA__`, no JSON-LD job
  data, no sitemap; same dead end as Get on Board. Glassdoor returned a 403 anti-bot
  wall on the very first request, no different from LinkedIn's fragility (the exact
  reason LinkedIn was removed in EATP-027) — never attempted with browser automation,
  on purpose. Revisit only if a real endpoint surfaces; don't re-attempt the same
  guesses, and don't reach for a headless browser to force either one.
