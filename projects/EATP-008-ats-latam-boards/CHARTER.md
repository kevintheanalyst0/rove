# EATP-008 — New sources — ATS + LatAm boards

**Complexity:** Medium

## Objective
Add ATS board feeds (Greenhouse/Lever/Ashby/Workable public JSON for a curated set of remote-friendly companies) and LatAm boards (Get on Board, Torre). ATS feeds are clean, captcha-free, and often list the best remote roles directly from the company.

## Problems solved
P2, P3, P4, P6, P15.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/SEARCH-STRATEGY.md` | Source tiers + companies rationale. |
| `docs/adr/ADR-005-source-strategy.md` | Why these sources. |
| `docs/governance/SCRAPING-GOTCHAS.md` | Recommended-jobs cards, pagination end-signals, site filter params, duplicate-job pitfalls — check every new source for these even without legacy precedent. |
| `docs/governance/DATA-CONTRACTS.md` | Job shape. |
| `src/rove/collectors/{base,http}.py` | Framework (EATP-003). |

## Dependencies
- **Projects:** EATP-003.
- **Libraries:** httpx.

## Scope
**In:**
- ATS collectors: Greenhouse + Lever (public board JSON) first; Ashby/Workable if time allows. Query a curated 'ats_companies' list (in config) for matching titles.
- LatAm boards: Get on Board (getonbrd public API) + Torre (public search API) for Spanish-market remote roles.
- A curated ats_companies list seeded with sensible defaults (remote-friendly companies hiring analysts).
- Tests: each parses a saved payload into valid Jobs (no live calls).

**Out:**
- Automatic ATS company discovery (backlog).
- Gate/AI/UI.

## Deliverables
- src/rove/collectors/{greenhouse,lever,getonbrd,torre}.py (+ ashby/workable if time)
- ats_companies list in config
- tests/test_collectors_ats_latam.py

## Key design decisions & constraints
- Curated company list is the pragmatic v1; auto-discovery is backlog.
- Greenhouse/Lever have stable public JSON — highest ROI; do them first.
- Partial delivery acceptable — note pending boards.
- ADR-009: don't filter out a company's posting on an ambiguous title before parsing its full JSON body — only the absolute exclusion categories justify that.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2-3 h).

## Open questions for Kevin
- Any companies you already like/watch? Their Greenhouse/Lever boards are easy high-signal adds. (Optional; I'll seed a default list.)
