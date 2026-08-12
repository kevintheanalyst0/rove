# Search Strategy

How Career Radar finds *more* jobs **and** *better* jobs (Kevin's P2/P3/P4/P15). The
guiding idea: **spend effort where the signal is high and the competition is low.**

## Search terms (Spanish-first)

Primary (Spanish, no accents so URLs stay clean):
```
analista de datos, analista de negocios, analista de inteligencia de negocios,
analista bi, analista power bi, analista de reportes, analista de informacion,
especialista en datos, analista funcional, analista de business intelligence
```
Secondary (English, for remote-LatAm boards that post in English):
```
data analyst, business intelligence analyst, reporting analyst, business analyst,
bi analyst, analytics analyst
```
Rules:
- Run Spanish terms on Spanish/LatAm sources; English terms on remote-first/global
  boards.
- Keep terms in `config` (single source), not per-collector.
- Do **not** add senior/lead/architect variants — they pull the wrong roles.

## Source tiers (by signal quality)

**Tier 1 — High signal, API-friendly, low competition (prioritize; new in EATP-007/008).**
- **ATS boards** with public JSON: **Greenhouse**, **Lever**, **Ashby**, **Workable**,
  **Recruitee**. Many remote-friendly companies expose clean job JSON with no captcha.
  These are where "the good jobs Kevin is missing" often live.
- **Remote-first boards:** **Remotive**, **We Work Remotely**, **RemoteOK**,
  **Himalayas** — several have JSON/RSS feeds; strong remote guarantee.
- **LatAm tech boards:** **Get on Board (getonbrd)**, **Torre** — remote-friendly,
  Spanish-market, lower competition than LinkedIn.

**Tier 2 — Useful but crowded (keep, refactor in EATP-004/005).**
- **OCC**, **Computrabajo** — HTTP/JSON, fast, Spanish market. Keep.
- **LinkedIn** — huge coverage but crowded and application-tracking is weak for Kevin.
  Keep as a source of *signal*, not the centerpiece.

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

## Anti-competition note (Kevin's LinkedIn concern)

LinkedIn rarely surfaces Kevin's applications partly because those postings get hundreds
of applicants fast. Tier-1 ATS/remote boards typically have far fewer applicants per
posting, so the *same effort* yields better odds. The system should make Tier-1 the
default habit, with LinkedIn as supplementary coverage.
