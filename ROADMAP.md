# ROADMAP — Career Radar

Career Radar is the rebuild of **JobMatchEngine**: a remote-first job-discovery engine
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
  (incl. Indeed, kept & optimized), plus the gates/dedup/cache/history/health that turn
  raw scrapes into a clean, remote-only, de-duplicated, non-repeating list. *When this
  block is done, "the scraping is solved."*
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
| **EATP-021** | Collector speed in the full pipeline + Indeed captcha/tab tradeoff | — | ⬜ | 020 | Medium | — |

> Fill **Status** and **Total time** as each project completes. The **Complexity** column
> exists so no project balloons: they're all sized Medium-ish, with a couple intentionally
> Light (011, 017) — quick sessions. If any project starts feeling like a 300k-token
> monster mid-build, STOP and split it (CLAUDE.md §3).

## Dependency graph (build order)

```
A: 001 -> 002
B: 001 -> 003 -> 004
                 |-> 005
                 |-> 006   (Indeed: kept + optimized)
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
| P5  | Indeed captchas | **EATP-006 (kept & optimized)** |
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

---

## Backlog (not scheduled)

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
