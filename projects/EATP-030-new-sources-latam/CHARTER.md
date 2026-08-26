# EATP-030 — New sources: LaPieza, Hireline, WeRemoto, RemotoJOB (+ Glassdoor spike)

## Objective

Add real keyword/filter-search job boards focused on the Mexican/LatAm market:
LaPieza, Hireline, WeRemoto, RemotoJOB. Unlike Greenhouse/Lever/Ashby-style ATS
platforms, these are expected to be market-wide search boards (any company,
searchable by term) — no company watchlist needed, if a real public
search/listing endpoint exists.

**Hard rule carried over from EATP-008's Get on Board / Torre failure (see
ROADMAP.md Backlog):** spike each source's endpoint viability *before* writing a
full collector. Get on Board turned out to be a client-rendered SPA with no
JSON-LD/RSS; Torre's search endpoint ignores query params and always returns the
same static snapshot. Don't re-attempt guessing against a source that has no
real API — confirm one exists first, in an hour or less per source, or drop it
and move on.

## Problems solved

- **P30** — source coverage still thin outside the current 10 collectors.

## Context to load

- `src/rove/collectors/base.py`, `http.py` — the collector protocol
  new HTTP-only sources plug into (same shape as `remotive.py`/`wwr.py`/
  `remoteok.py` — simplest reference examples, not Greenhouse/Lever which are
  the watchlist-per-company shape this project explicitly avoids).
- `src/rove/collectors/remotive.py` or `wwr.py` — pick whichever is the
  cleanest structural template for a market-search HTTP collector.
- `src/rove/collectors/__init__.py` — registry wiring for whatever ships.
- `ROADMAP.md` Backlog section — the Get on Board / Torre dead-end note; read
  before spiking anything.
- `criteria.toml` — how existing collectors' results feed into filtering
  (should need zero changes if these behave like existing HTTP sources).
- `tests/fixtures/` — pattern for recorded fixtures per source (no live calls
  in tests, per CLAUDE.md §7/§8 spirit — same discipline applies to job-board
  HTTP calls, not just paid AI calls: don't hit live endpoints in the test
  suite).

## Dependencies

- **Projects:** EATP-029 (sequential convention).
- **Libraries:** none expected beyond what's already in use (`httpx`,
  `BeautifulSoup` if a source is HTML-only rather than JSON).

## Scope

**In:** viability spike for each of LaPieza, Hireline, WeRemoto, RemotoJOB, and
Glassdoor; full collector build only for the ones that pass the spike.

**Out:** any ATS/enterprise-watchlist platform (explicitly cut from this backlog
— see the ROADMAP note above the project table); Greenhouse/Lever changes.

## Deliverables

- A short written verdict per source (viable / not viable + why), so a future
  session never re-guesses a source already ruled out here — same courtesy
  EATP-008 left for Get on Board/Torre.
- A working, registered, tested collector for each source that passed its spike.
- Glassdoor gets the spike only; if no real endpoint turns up within the
  time-box, it's documented as a dead end in the Backlog section, same as Get on
  Board/Torre, and dropped — not force-built with browser automation (that would
  reintroduce exactly the fragility LinkedIn was removed for in EATP-027).

## Key design decisions & constraints

- **Spike first, build second, per source, in that order** — this is the whole
  point of this charter existing separately from "just add the sources."
- **If a source needs browser automation to work at all** (like Glassdoor
  plausibly does), that's a strong signal against building it — weigh it against
  the exact reasoning that killed LinkedIn (EATP-027), don't quietly reintroduce
  the same fragility under a new name.

## Definition of Done

Standard CLAUDE.md §9, plus: written viability verdict for all five candidate
sources exists in this project's checklist or the ROADMAP Backlog section,
regardless of how many actually shipped.

## Estimated time

TBD — genuinely uncertain until the spikes run; could be light (all viable,
simple JSON APIs) or could shrink to nothing shipped (all dead ends, same as
Get on Board/Torre). Size honestly at session start after the spikes, not before.

## Open questions for Kevin

None expected before the spikes run. If 3+ of the 5 turn out to be dead ends,
that's worth flagging back to Kevin before building the survivors — worth
checking whether the remaining 1-2 are still worth a full collector for the
yield they'd add.
