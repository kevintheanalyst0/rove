# EATP-002 — Candidate profile & evaluation criteria

**Complexity:** Light-medium

## Objective
Encode WHO Kevin is and WHAT a good job for him means, as versioned data both the rule pre-filter and the AI rubric read: profile.yaml (skills, target roles, priority) and criteria.yaml (dealbreakers, exclusion lists, English/remote signal words, matcher weights, score floors, on-site tolerance).

## Problems solved
P4, P6, P7 (right criteria); feeds P8 remote signals and P10 matcher.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/CANDIDATE-PROFILE.md` | Authoritative profile + priorities + dealbreakers. |
| `docs/governance/EVALUATION-RUBRIC.md` | How criteria are used across the layers. |
| `legacy/jobmatch/profile.py` | Reference: old profile dict. |
| `legacy/jobmatch/collectors/filters.py` | Reference: exclusion/English lists to port & expand. |
| `legacy/jobmatch/config.py` | Reference: ROLE_WEIGHTS/SKILL_WEIGHTS/search terms. |

## Dependencies
- **Projects:** EATP-001.
- **Libraries:** Prefer TOML/JSON (stdlib) to avoid a new dep; if pyyaml is wanted, ask Kevin first (CLAUDE.md 8).

## Scope
**In:**
- profile.(yaml|toml): target roles, skills, priority statement, English B2, one-line goal for prompts.
- criteria.(yaml|toml): exclusion title/company keywords (ported + EXPANDED: DBA/database admin, linux/sysadmin/infra, networking, cybersecurity, backend/frontend/devops, plus legacy set); conditional title rules; advanced-English phrases + regex; remote positive AND anti-remote signal words (ES+EN); matcher role/skill weights; score floors; recency window; on-site tolerance.
- profile.py / criteria.py: typed loaders validating against pydantic.
- Tests: loaders validate; known fixtures classify as expected (advanced-English flags true; hybrid phrase flags anti-remote).

**Out:**
- Applying filters in a pipeline (009).
- The AI prompt text (013).

## Deliverables
- profile + criteria data files
- src/career_radar/{profile,criteria}.py
- tests/test_criteria.py

## Key design decisions & constraints
- Anti-remote signals OVERRIDE remote signals (ADR-002) — encode both lists here.
- On-site tolerance is DATA, not hardcoded (default: up to ~1 day/month = remote-ok).
- Expand exclusions to cover Kevin's explicit dealbreakers (DBA/linux/infra/dev/finance/design...).
- Use TOML/JSON if avoiding pyyaml; note the choice.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~1.5-2 h).

## Open questions for Kevin
- Confirm on-site tolerance: is '~1 dia al mes' the max? (Default: up to ~1/month = remote-ok; more frequent = reject.)
