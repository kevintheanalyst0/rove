# EATP-001 — Foundation & core contracts

**Complexity:** Medium

## Objective
Lay the base every other project stands on: package skeleton, a single config source of truth, typed data models (pydantic) including the content-signature helper and the ONE score->grade mapping, atomic + streaming storage, a progress event bus the web UI will subscribe to, and logging. No collectors, no AI yet.

## Problems solved
Enables all. Directly supports R12 (clean base) and the event bus behind R11.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `docs/governance/ARCHITECTURE.md` | Target layout; where the foundation sits. |
| `docs/governance/DATA-CONTRACTS.md` | Exact shapes: Job/ScoredJob/RunResult, signature, grade mapping. |
| `docs/governance/DEPENDENCIES.md` | Install/verify protocol. |
| `legacy/jobmatch/config.py` | Reference: what config already centralizes. |
| `legacy/jobmatch/storage.py` | Reference: atomic write pattern to keep. |
| `legacy/jobmatch/models.py` | Reference: old Job/AnalyzedJob shapes. |

## Dependencies
- **Projects:** none
- **Libraries:** python-dotenv, pydantic, orjson (+ pytest, ruff dev).

## Scope
**In:**
- Create venv; install core+dev deps; verify each import.
- config.py: env (.env), paths, search terms, tunables — single source of truth.
- models.py: pydantic Job/ScoredJob/RunResult; enums remote_status/fit/grade; content_signature(); grade_from_score() (the ONE mapping).
- storage.py: atomic JSON write (temp+replace) AND streaming JSONL read/write for big files.
- events.py: in-process progress event bus (phase/status/percent) for orchestrator + UI.
- logging config (structured, quiet by default).
- Tests: models (validation, signature stability, grade mapping) + storage (atomicity, JSONL roundtrip).

**Out:**
- Collectors (003-008).
- Quality gates/cache (009-010).
- AI (012).
- Web (015).

## Deliverables
- src/career_radar/{config,models,storage,events}.py
- tests/test_models.py, tests/test_storage.py
- Green pytest.

## Key design decisions & constraints
- pydantic v2; keep models import-light.
- content_signature() implements ADR-001 exactly (normalize + sha1 of company|title|desc[:400]).
- grade_from_score() is the ONLY place grades are computed.
- JSONL for large per-source data; pretty JSON only for small status/result files.
- Event bus must be trivially consumable from FastAPI later (thread-safe queue or async pub/sub).

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
- none — fully specified.
