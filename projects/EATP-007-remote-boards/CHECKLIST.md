# EATP-007 — New sources — remote-first boards — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Feeds A
- [x] Remotive
- [x] RemoteOK
- [x] tests

### Phase 2 — Feeds B
- [x] We Work Remotely
- [x] Himalayas
- [x] tests

### Phase 3 — Close
- [x] register all
- [x] pytest
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | 1+2+3 (single session) | ~45 min | All 4 sources verified live before coding, then built + tested in one pass |

**Total project time:** ~45 min

## Session notes
Built all 4 Tier-1 remote boards in one session instead of the planned two phases — went
faster than estimated once the live API shapes were confirmed. Key findings from live
verification (documented in each collector's module docstring):
- **Remotive** has real server-side search (`?search=`) — only source here with one.
- **RemoteOK** and **Himalayas** silently ignore every search/filter query param tested
  (confirmed against real responses), so both fetch once/paginate and filter
  client-side via the new `parsing.matches_any_term()` helper against
  `config.ENGLISH_SEARCH_TERMS` (also new — English terms were missing from config,
  only Spanish `SEARCH_TERMS` existed).
- **We Work Remotely**'s old "remote-data-jobs"/"remote-business-jobs" category feeds
  now 301 (site restructured categories) — using the closest surviving one
  (`remote-management-and-finance-jobs`) plus client-side keyword filtering. Parsed with
  stdlib `xml.etree.ElementTree`, no new dependency (feedparser wasn't needed).
- Himalayas pagination has no natural end-signal (always returns a full page), so it's
  capped at `_MAX_PAGES = 5` as the loop-safety net from SCRAPING-GOTCHAS.md #2.
- All 4 respect ADR-009 (title pre-filter is absolute-list-only) and never set
  `remote_status`/hardcode remote — that's still EATP-009's job.
