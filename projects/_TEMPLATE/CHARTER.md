# EATP-00X — <Project name>

> Charter template. Every project follows this shape. Claude Code reads it in full at
> the start of the session, then loads ONLY the "Context to load" files.

## Objective
<What this project builds and why, in 2–4 sentences.>

## Problems solved
<Traceability to Kevin's list: P#, R#.>

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `docs/governance/<file>.md` | <reason> |
| `legacy/<path>` | <reference, if any> |

## Dependencies
- **Projects:** <EATP-00X must be ✅ first, or "none">.
- **Libraries:** <from DEPENDENCIES.md>.

## Scope
**In:** <what to build now.>
**Out:** <what belongs to a later project — do NOT build.>

## Deliverables
- <concrete artifact 1>
- <concrete artifact 2>
- <tests>

## Key design decisions & constraints
- <site-specific gotchas, "do it this way", ADR references.>

## Definition of Done
- [ ] <deliverables exist & work>
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left
- [ ] Checklist ticked, time logged
- [ ] ROADMAP status → ✅
- [ ] Session notes written
- [ ] Committed to git (CLAUDE.md §10)

## Estimated time
<estimate>

## Open questions for Kevin
- <surface these in the plan; or "none">
