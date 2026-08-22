# EATP-030 — Checklist & time log

## Phases

- [x] **Phase 1 — Spikes.** Live viability check (real `curl`/Python requests
      against each site, not just reading about them) for all five candidates:
  - **LaPieza — dead end.** Client-rendered Next.js app-router SPA; no
    `__NEXT_DATA__`, no JSON-LD job data, no `/api/` hints, no sitemap
    (404). Same dead end as Get on Board (EATP-008).
  - **Hireline — viable.** `robots.txt` disallows only the query-string
    search (`/empleos?k=*`); `/mx/sitemap_ofertas.xml` lists every current
    MX posting (227 URLs, `lastmod` same day as the spike). Each posting
    embeds a clean schema.org `JobPosting` JSON-LD block.
  - **WeRemoto — viable.** `sitemap.xml` only covers blog/events (a red
    herring, not a dead end) — postings are server-rendered HTML behind
    `/categoria-de-trabajo/<slug>` category pages (`analista-de-datos`
    confirmed live), each with its own `JobPosting` JSON-LD block.
  - **RemotoJob — viable.** WordPress board, `rj-job-sitemap{N}.xml` files
    (~200 URLs each, N=1 confirmed as the most-recently-updated batch).
    `JobPosting` JSON-LD present, with one gotcha: a raw unescaped newline
    inside the description breaks strict JSON (`strict=False` fixes it).
  - **Glassdoor — dead end.** 403 "Security" anti-bot page on the very
    first request. Same fragility class as LinkedIn; not attempted with
    browser automation, on purpose (would reintroduce exactly what
    EATP-027 removed).
  - Only 2 of 5 dead-ended (below the charter's own "3+ dead ends ->
    check back with Kevin" threshold) — proceeded straight to building
    the 3 survivors.
- [x] **Phase 2 — Shared helper.** `collectors/parsing.py` gains
      `extract_job_posting_ld_json()` (picks the right block out of several
      unrelated JSON-LD types on the same page, `strict=False` for the
      RemotoJob gotcha) and `slug_to_text()` (for prefiltering a
      sitemap-discovered URL before spending a detail request on it).
- [x] **Phase 3 — Three collectors.** `hireline.py` (sitemap + slug
      prefilter), `weremoto.py` (3 hand-curated category pages, dedup across
      categories), `remotojob.py` (sitemap batch 1 + slug prefilter). All
      HTTP-only, no browser, no company watchlist.
- [x] **Phase 4 — Register & test.** Wired into `collectors/__init__.py`'s
      registry. 13 new tests in `tests/test_collectors_latam_boards.py`
      (shared-helper unit tests + per-collector parse/prefilter/cancellation/
      dedup/registration coverage), all against a mocked transport built from
      real page structure — no live calls in the suite. **408 tests passing.**
- [x] **Phase 5 — Live verification.** Ran all three collectors for real
      (not mocked) against the live sites: Hireline returned 7 real postings,
      WeRemoto 2, RemotoJob 0 that hour (its current sitemap batch happened to
      be dominated by engineering/design titles, not analyst ones — expected
      day-to-day variance for a general board, not a bug; confirmed by
      inspecting the actual 200 slugs directly). Also chased down what looked
      like a mojibake encoding bug in one live result ("Biling�e") — traced
      it to the Windows-native venv's own console/stdout re-encoding when
      piped through WSL, not the collector: writing the same string to a file
      and reading it back confirmed clean UTF-8 ("Bilingüe") the whole way
      through. No code bug; noted here so a future session doesn't re-chase it.
- [x] **Phase 6 — Close.** Recorded the LaPieza/Glassdoor dead-end verdicts in
      `ROADMAP.md`'s Backlog (same style as Get on Board/Torre). Updated
      `SEARCH-STRATEGY.md`'s Tier-1 list (also fixed a pre-existing staleness
      there: Ashby/Workable/Recruitee/Get on Board/Torre were still listed as
      current despite EATP-008/the 2026-08-21 backlog design already ruling
      most of them out) and pointed its search-terms section at `config.py`
      instead of duplicating a list that will drift again. Added
      `SCRAPING-GOTCHAS.md` §8 (the sitemap/JSON-LD collector shape, for the
      next time a board like this comes up). Updated `ARCHITECTURE.md`'s repo
      map. `ROADMAP.md`/`CHANGELOG.md` updated. Committed.

## Time log

| Date | Phase(s) | Time |
|------|----------|------|
| 2026-08-21 | 1-6 (full project, single session) | ~1h40 |

**Total: ~1h40**

## Session notes

All four Notion-backlog projects (EATP-027 through 030) are now done. The
spike-first discipline paid off twice: LaPieza looked like a reasonable ask
in the original ChatGPT backlog but turned out to be a flat dead end (same
shape as Get on Board), and Glassdoor's risk was exactly as predicted during
planning. The three survivors share one collector shape (sitemap/category
discovery + JSON-LD `JobPosting` detail) documented in SCRAPING-GOTCHAS.md §8
for reuse if another LatAm board comes up later. No open questions for Kevin.
