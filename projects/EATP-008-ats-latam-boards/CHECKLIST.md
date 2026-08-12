# EATP-008 — New sources — ATS + LatAm boards — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — ATS boards
- [x] Greenhouse
- [x] Lever
- [x] company list
- [x] tests

### Phase 2 — LatAm boards
- [x] Get on Board — investigated, not delivered (see session notes)
- [x] Torre — investigated, not delivered (see session notes)
- [x] tests (n/a — nothing shipped for this phase)

### Phase 3 — Close
- [x] register all
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | 1+2+3 (single session) | ~1 h | Live-verified all 4 candidate sources before coding; 2 of 4 turned out non-viable |

**Total project time:** ~1 h

## Session notes
Delivered **Greenhouse + Lever only** — LatAm boards (Get on Board, Torre) were
investigated live but not shipped, per the charter's explicit partial-delivery
allowance. Both are documented as pending, not silently dropped:

- **Get on Board**: no discoverable public API. It's a client-rendered SPA (Nuxt) with
  no JSON-LD, no RSS, no accessible `/api` route found after a reasonable search
  (checked `.json`/`.rss` suffixes, Accept-header negotiation, bundled JS for an
  Algolia-style key). Revisit only if a real endpoint surfaces later — not worth more
  guessing time now.
- **Torre**: has a real-looking endpoint (`search.torre.co/opportunities/_search`) but
  it **silently ignores every param sent** (`query`, `size`, `offset`) — confirmed by
  sending different values and getting byte-identical responses each time. It always
  returns the same static ~10-result "trending" snapshot. Building a collector on top
  of that would mean shipping a source that returns the same mostly-irrelevant jobs
  every run — directly against CLAUDE.md's quality-over-volume mandate — so it was
  deliberately not built rather than shipped as filler.
- **Greenhouse**: public per-company board API, `content=true` returns the full job
  body in one call. Gotcha found live: `content` is HTML-entity-escaped HTML (doubly
  encoded — `html.unescape()` before BeautifulSoup, or tags survive as visible text).
- **Lever**: public per-company postings API, ships `descriptionPlain` directly (no
  HTML stripping needed). Its curated company list is short (`palantir`, `clari`) —
  of ~20 well-known companies probed live, most no longer have an active Lever board.
- Both new collectors follow ADR-009 more deliberately than EATP-007's: since the full
  job body is already in the same response (no separate detail fetch to save), the
  keyword match runs against **title + description**, not title alone.
- `config.ATS_COMPANIES` added (dict of source -> curated company slugs); grow by hand,
  auto-discovery is backlog.
