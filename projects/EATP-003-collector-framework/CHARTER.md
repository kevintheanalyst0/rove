# EATP-003 — Collector framework & shared plumbing

**Complexity:** Medium

## Objective
Give collectors a common contract and shared, well-behaved plumbing so every source is consistent, testable, and safe: a Collector protocol + registry, a shared httpx layer (session/pacing/retry), and a stealthier browser base with the WSL Chromium path resolved. No site-specific collectors yet — just the infra they all plug into. Critically: manual interventions (captcha/login) are NEVER a blocking terminal prompt; they are surfaced as events for pause/resume.

## Problems solved
P1 (methodology/efficiency); sets up P5 (Indeed) and R11/R12 (no terminal input()).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/ARCHITECTURE.md` | Where collectors sit; base/registry idea. |
| `docs/governance/SEARCH-STRATEGY.md` | Terms, tiers, recency, gentle pacing. |
| `docs/governance/DATA-CONTRACTS.md` | Job shape every collector emits. |
| `docs/adr/ADR-009-title-is-a-signal-not-a-verdict.md` | Any request-saving pre-filter before fetching detail may only use the absolute exclusion list — never skip a job on an ambiguous title. |
| `legacy/jobmatch/collectors/browser.py` | Reference: persistent-profile browser helper + alert_manual_intervention (which uses input() — replace). |
| `legacy/jobmatch/collectors/utils.py` | Reference: shared HTTP session, clean_text, date parsing. |

## Dependencies
- **Projects:** EATP-001.
- **Libraries:** httpx, tenacity, DrissionPage, beautifulsoup4, lxml.

## Scope
**In:**
- collectors/base.py: Collector protocol (collect() -> Iterator[Job]) + a registry (enable/disable per source).
- collectors/http.py: shared httpx session, headers, gentle randomized pacing, retry (tenacity).
- collectors/browser.py: stealthier Chromium base (realistic fingerprint/viewport, human pacing, session reuse); RESOLVE the WSL Chromium/Chrome path here.
- A manual-intervention mechanism that is EVENT-BASED (emit to the event bus + pause/resume), NEVER input()/terminal blocking.
- A per-source result envelope carrying yield count + health (feeds EATP-011).
- Tests: registry works; http pacing/retry behaves; a fake collector integrates.

**Out:**
- Actual site collectors (004-008).
- The gate/cache (009-010).
- AI (012).

## Deliverables
- src/career_radar/collectors/{base,http,browser}.py
- tests/test_collector_framework.py

## Key design decisions & constraints
- No blocking terminal prompts anywhere in collectors — manual steps are surfaced as events (this is what makes R11/R12 possible).
- Collectors emit RAW Jobs; gating/dedup/cache happen later in the pipeline (keep collectors dumb + testable).
- In WSL, ensure a Chromium binary is reachable; document the one-time setup simply if needed (do not block on it — HTTP collectors don't need it).
- **ADR-009: title is a signal, never a verdict.** If a site-specific collector (004-008) pre-filters by title before fetching a job's full detail to save requests, it may ONLY skip on the absolute `excluded_title_keywords` categories (designer, sales, recruiting, legal, health, education, …) — never on an ambiguous word. When unsure, fetch the description; a real good job ("Analista administrativo") was buried by exactly this kind of title-only shortcut in the legacy system.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2-3 h). WSL browser setup may add time.

## Open questions for Kevin
- none critical. If WSL Chromium proves painful, we can point browser collectors at Windows Chrome; decide in-session.
