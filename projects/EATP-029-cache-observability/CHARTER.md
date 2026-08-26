# EATP-029 — Cache observability

## Objective

Make the existing 30-day signature cache (ADR-001, `quality/cache.py`) inspectable
without changing its behavior: a "Ver cacheadas" view and a manual reset, plus the
funnel diagnostic (EATP-028) reporting how many jobs the cache hid this run,
separately from "the market just produced little." No change to the 30-day
window or to what gets suppressed.

## Problems solved

- **P29** — cache suppresses repeats but isn't inspectable or resettable.

## Context to load

- `src/rove/quality/cache.py` — `SignatureCache`, `SignatureRecord`;
  read/write path.
- `docs/adr/ADR-001-content-signature-cache.md` — the existing design rationale;
  this project must not contradict it, only add visibility.
- Wherever EATP-028's funnel diagnostic ends up living (pipeline/events) — the
  cache-hidden count plugs into the same diagnostic.
- `src/rove/web/` (backend routes) + `app.js` / templates — where a new
  read-only "Ver cacheadas" view and a manual-reset action need to live.
- `docs/governance/DATA-CONTRACTS.md` — if the cache-hidden count becomes part
  of a documented response shape.

## Dependencies

- **Projects:** EATP-028 (sequential + the funnel diagnostic it introduces).
- **Libraries:** none expected.

## Scope

**In:** read-only "Ver cacheadas" view, manual reset control, cache-hidden count
in the funnel diagnostic.

**Out:** changing the 30-day window, changing what gets suppressed, any
automatic re-surfacing logic.

## Deliverables

- A view listing currently-cached signatures (job title/company/source/first
  seen/last seen at minimum).
- A manual reset action, clearly separate from normal run behavior.
- Cache-hidden count reported per run.

## Key design decisions & constraints

- **The cache does not get weaker.** This project is pure observability —
  resolving Kevin's actual complaint ("is the market slow or did the cache just
  hide a bunch of stuff") without touching suppression logic itself.

## Definition of Done

Standard CLAUDE.md §9. No behavior change to what the cache suppresses,
verified by existing cache tests still passing unmodified.

## Estimated time

TBD — sized at session start.

## Open questions for Kevin

None expected yet.
