# Search Strategy

How Career Radar finds *more* jobs **and** *better* jobs (Kevin's P2/P3/P4/P15). The
guiding idea: **spend effort where the signal is high and the competition is low.**

## Search terms (Spanish-first)

Kept in `config.py`'s `SEARCH_TERMS` (Spanish) / `ENGLISH_SEARCH_TERMS` (English) —
this doc doesn't duplicate the live list (EATP-028 expanded both; check `config.py`
for the current set rather than trusting a copy pasted here). Rules:
- Run Spanish terms on Spanish/LatAm sources; English terms on remote-first/global
  boards.
- Keep terms in `config` (single source), not per-collector.
- Do **not** add senior/lead/architect variants — they pull the wrong roles.

## Source tiers (by signal quality)

**Tier 1 — High signal, API-friendly, low competition (prioritize).**
- **ATS boards** with public JSON, curated per-company watchlist (`config.ATS_COMPANIES`,
  EATP-007/008): **Greenhouse**, **Lever**. Many remote-friendly companies expose clean
  job JSON with no captcha. Enterprise/whitelist-only ATS platforms beyond these two
  (Ashby, Workable, Recruitee, SmartRecruiters, Workday, ...) were deliberately cut from
  scope in the 2026-08-21 backlog design (EATP-027 ROADMAP note) — a hand-maintained
  company list per platform, forever, wasn't worth it for platforms Kevin isn't already
  invested in.
- **Remote-first boards:** **Remotive**, **We Work Remotely**, **RemoteOK**,
  **Himalayas** — several have JSON/RSS feeds; strong remote guarantee.
- **LatAm job boards, sitemap/category-discovered + JSON-LD detail** (EATP-030):
  **Hireline**, **WeRemoto**, **RemotoJob** — no company watchlist needed, real
  market-wide postings. ~~Get on Board~~, ~~Torre~~ (EATP-008), ~~LaPieza~~ (EATP-030)
  investigated and dropped: all three are client-rendered SPAs with no discoverable
  API/sitemap/JSON-LD — see ROADMAP.md Backlog before re-attempting any of them.

**Tier 2 — Useful but crowded (keep, refactor in EATP-004/005).**
- **OCC**, **Computrabajo** — HTTP/JSON, fast, Spanish market. Keep.
- ~~**LinkedIn**~~ — huge coverage but crowded and application-tracking is weak for
  Kevin, plus the most fragile/high-maintenance collector in the whole system
  (CAPTCHA, login walls, geo/rate limits). Removed entirely in EATP-027 — the
  maintenance cost stopped being worth its yield (ROADMAP.md P26).

**Tier 3 — Keep and optimize (captcha-heavy).**
- **Indeed** — valuable listings but aggressive bot detection (P5). **Kept as a
  first-class source and optimized** in EATP-006 (stealthier browser, human pacing,
  event-based captcha handling); a run never *fails* because of an Indeed captcha, but
  Indeed is not dropped.

> Strategic point (ADR-005): we optimize Indeed AND add Tier-1 sources. The clean
> Tier-1 feeds ease three problems at once — less pressure on captcha-heavy Indeed (P5),
> higher quality (P4/P6), and the "missing good jobs" feeling (P15) — without giving up
> Indeed's coverage.

## How much to pull

- Breadth: run all Tier-1 + Tier-2 sources every run; Indeed only if enabled.
- Depth per source: enough pages to catch fresh postings (last ~14 days), not so many
  that pagination trips bot detection. Prefer *recent* over *deep*.
- **Recency window:** default 14 days; configurable.

## Quality bar (before AI even sees a job)

A job must pass ALL of these to reach the AI (details in EVALUATION-RUBRIC.md + EATP-009/010):
1. Title/company not on the exclusion lists; conditional title rules satisfied.
2. Not advanced-English-required.
3. **Remote confirmed** (hard-gate; hybrid/onsite rejected).
4. Not a near-duplicate of a job already in this run.
5. Not seen-and-scored recently (content-signature cache).
6. Survives the matcher pre-filter (clearly-off roles rejected).

This is what turns "search more" into "search more, and better".

## Anti-competition note (historical — Kevin's original LinkedIn concern)

This was the original reasoning for prioritizing Tier-1 over LinkedIn even while
LinkedIn was still a source: LinkedIn rarely surfaced Kevin's applications, partly
because those postings get hundreds of applicants fast. Tier-1 ATS/remote boards
typically have far fewer applicants per posting, so the *same effort* yields better
odds. LinkedIn was removed entirely in EATP-027, so this is no longer a live
trade-off — kept here as the historical rationale for why Tier-1 is the default
habit.
