# EATP-005 — LinkedIn collector (refactor + harden)

**Complexity:** Medium

## Objective
Port LinkedIn onto the framework: the browser lists job ids, the public guest API fetches details (no login needed for details). Make listing gentle and login handling event-based (never a terminal prompt). Be account-safety aware.

## Problems solved
P1, P2 (LinkedIn coverage), P13 (gentler/faster), P23 (account-ban safety).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/SEARCH-STRATEGY.md` | Terms + tiers. |
| `docs/governance/DATA-CONTRACTS.md` | Job shape. |
| `docs/governance/SCRAPING-GOTCHAS.md` | LinkedIn's "recommended for you" cards, rate-limit tab coordination, duplicate-job pitfalls. |
| `src/career_radar/collectors/{base,browser,http}.py` | Framework (EATP-003). |
| `legacy/jobmatch/collectors/linkedin.py` | Reference: listing scroll, page health (429), pause coordination. |
| `legacy/jobmatch/collectors/linkedin_api.py` | Reference: guest job-detail endpoint. |
| `tests/fixtures/linkedin_jobs.json` | Real records for tests. |

## Dependencies
- **Projects:** EATP-003.
- **Libraries:** (from framework).

## Scope
**In:**
- Port LinkedIn listing (browser -> job ids) with gentle pacing + 429 backoff.
- Port guest-API detail fetch (HTTP, concurrent but polite).
- Login/authwall handling is EVENT-BASED (pause/resume via event bus), NEVER input().
- Account safety: keep detail fetching on the guest API (no login); if listing needs login, surface it and allow skipping LinkedIn for that run rather than risking his main account.
- Tests: listing parse + detail parse from fixtures (no live calls).

**Out:**
- Indeed (006).
- New sources (007-008).
- Gate/AI.

## Deliverables
- src/career_radar/collectors/linkedin.py (+ guest api helper)
- tests/test_collector_linkedin.py

## Key design decisions & constraints
- Details via guest API (no login) to minimize account risk (P23).
- No input() — login surfaced as an event; run can proceed without LinkedIn if login is refused.
- Gentle pacing to avoid 429; keep the legacy's health checks.
- ADR-009: LinkedIn's legacy filters.py title-only pre-filter must NOT be ported as-is — only the absolute exclusion categories may skip a detail fetch; ambiguous titles still get fetched and judged on full text downstream.

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
- Do you want LinkedIn to use your main logged-in Chrome profile, or run without login (details-only, less coverage but zero account risk)? (Default: details-only/no-login; listing best-effort.)
