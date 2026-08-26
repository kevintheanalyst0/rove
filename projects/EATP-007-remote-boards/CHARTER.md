# EATP-007 — New sources — remote-first boards

**Complexity:** Light-medium

## Objective
Add high-signal, low-competition remote-first sources with clean JSON/RSS feeds: Remotive, RemoteOK, We Work Remotely, Himalayas. These are where good remote roles Kevin is missing often live, and they have little/no captcha.

## Problems solved
P2, P3, P4, P6, P15 (broader AND better; less competition).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/SEARCH-STRATEGY.md` | Source tiers + rationale. |
| `docs/adr/ADR-005-source-strategy.md` | Keep Indeed; ADD these high-signal sources. |
| `docs/governance/SCRAPING-GOTCHAS.md` | Recommended-jobs cards, pagination end-signals, site filter params, duplicate-job pitfalls — check every new source for these even without legacy precedent. |
| `docs/governance/DATA-CONTRACTS.md` | Job shape. |
| `src/rove/collectors/{base,http}.py` | Framework (EATP-003). |

## Dependencies
- **Projects:** EATP-003.
- **Libraries:** httpx (+ feedparser only if RSS is used; ask before adding).

## Scope
**In:**
- Remotive (public API), RemoteOK (public JSON), We Work Remotely (RSS), Himalayas (API) — filter to data/BI/analyst + remote.
- Each emits the standard Job shape; runs fast (HTTP/JSON).
- Tests: each parses a saved sample payload into valid Jobs (no live calls).

**Out:**
- ATS + LatAm boards (008).
- Gate/AI/UI.

## Deliverables
- src/rove/collectors/{remotive,remoteok,wwr,himalayas}.py
- tests/test_collectors_remote_boards.py

## Key design decisions & constraints
- Start with the easiest/highest-yield (Remotive, RemoteOK); add the rest as time allows — partial delivery is fine, note what's pending.
- These are English-market friendly; use the English search terms here (SEARCH-STRATEGY).
- Respect each API's terms + rate limits; gentle pacing.
- ADR-009: these APIs return full postings in one call, so this mostly doesn't apply — but if any board needs a second detail call, don't skip it on an ambiguous title.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~1.5-2.5 h).

## Open questions for Kevin
- none.
