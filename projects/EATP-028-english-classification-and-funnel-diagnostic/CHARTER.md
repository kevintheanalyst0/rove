# EATP-028 — English-requirement classification + funnel diagnostic + expanded search terms

## Objective

Replace the binary `requires_advanced_english()` reject gate with a three-tier
classification — **reject** (explicit C1/C2/native/bilingual), **compatible**
(explicit B2/intermediate), **indeterminate** (ambiguous phrasing like
"professional English" or "fluent") — so ambiguous listings surface as
**Confirmar inglés** instead of being silently dropped, while explicit C1/C2
still hard-rejects exactly as today. Kevin's B2 ceiling does not move; only the
interpretation of ambiguous phrasing changes. Alongside it, add a per-run funnel
diagnostic (collected/duplicate/stale/non-remote/English-rejected/cache-hidden/
prefiltered/sent-to-Gemini, by source) and expand the search-term list.

## Problems solved

- **P27** — ambiguous English phrasing hard-rejected with no distinction from
  genuinely explicit requirements.
- **P28** — no per-run funnel diagnostic.
- Expanded search terms (Power BI Developer, BI Developer, Data Visualization
  Analyst, Insights Analyst, Operations Data Analyst, Supply Chain Data Analyst,
  Business Systems Analyst, SAP Data Analyst, Automation Analyst, Analista de
  inteligencia comercial, Reporting Analyst, People Analytics) — not a numbered
  P#, folded in here since it's a small `criteria.toml` addition touching the
  same file this project already opens.

## Context to load

- `src/rove/criteria.py` — `requires_advanced_english()` (~line 146) and
  the `AdvancedEnglish` model (~line 72); this is what becomes 3-way.
- `criteria.toml` — the `[advanced_english]` table (~lines 94-112): today's
  `phrases`/`regex` lists conflate explicit (C1/C2/native/bilingual) with
  ambiguous ("professional english", "english required", "fluent", "strong
  communication skills") — these need to split into two tiers. Also where the
  new search terms get added.
- `src/rove/quality/filters.py` (~line 54-56) — where the reject fires
  today; needs a third path for "indeterminate" that keeps the job visible with
  a tag instead of dropping it.
- `src/rove/scoring/validate.py` (~line 77) — other caller of
  `requires_advanced_english()`.
- `src/rove/scoring/prefilter.py` — check whether it also needs to know
  about the indeterminate tier or only the hard filter does.
- `src/rove/pipeline.py` — where per-source/per-stage counts already
  exist (if any) for the funnel diagnostic; check `RunResult`/`events.py` for
  the right place to accumulate and expose these counts.
- `src/rove/web/static/js/app.js` + whatever template renders results —
  where the "Confirmar inglés" tag and the exact matched phrase need to show.
- `docs/governance/DATA-CONTRACTS.md` — update if the job/result shape gains a
  field (e.g. `english_requirement: reject | compatible | indeterminate` +
  `matched_phrase`).

## Dependencies

- **Projects:** EATP-027 (sequential convention).
- **Libraries:** none expected.

## Scope

**In:** the 3-way classification, the matched-phrase surfacing, the
"Confirmar inglés" UI tag, the per-run funnel diagnostic, the expanded term list.

**Out:** relaxing the B2 ceiling itself (never in scope, ever); cache changes
(EATP-029); new sources (EATP-030).

## Deliverables

- `criteria.toml` `[advanced_english]` split into an explicit-reject tier and an
  indeterminate tier, with tests for the previously-misclassified example
  phrases ("professional English", "English required", "fluent").
- Result objects carry the classification + the exact matched text.
- A funnel diagnostic surfaced per run (counts by stage and by source).
- Expanded search-term list live in `criteria.toml`.

## Key design decisions & constraints

- **B2 stays a hard filter.** This project changes interpretation of ambiguous
  text, not the cap itself.
- **Always show the triggering phrase**, reject or indeterminate alike — Kevin
  needs to audit misclassifications, per his own P24/ADR-009 pattern of title-
  only judgment burying good jobs.

## Definition of Done

Standard CLAUDE.md §9, plus: test cases for at least the three phrases named in
Kevin's original note ("professional English", "English required", "strong
communication skills") land in `indeterminate`, not `reject`; explicit C1/C2/
native/bilingual still lands in `reject`.

## Estimated time

TBD — will be sized properly at session start once EATP-027 is done and this
charter is re-read against the then-current code.

## Open questions for Kevin

None expected yet — will surface at session start if anything about the
indeterminate-tag UX needs his call (e.g. whether "Confirmar inglés" jobs should
sort separately from confirmed-compatible ones).
