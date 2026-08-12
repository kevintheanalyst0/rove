# EATP-014 — Orchestrator & resumable/memory-safe run

**Complexity:** Medium

## Objective
Wire the whole pipeline into one resumable, crash/OOM-safe run that streams and checkpoints between heavy stages, emits progress events for the UI, wires in source-health, and exposes speed-vs-exhaustiveness knobs. Make a full run reliably fast.

## Problems solved
P13 (speed), P14 (knobs), R12 (fewer manual steps); enables R11 via events; wires P20 health.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules — esp. 3 memory/crash safety. |
| `docs/governance/ARCHITECTURE.md` | End-to-end data flow. |
| `src/career_radar/events.py` | Event bus (EATP-001). |
| `src/career_radar/quality/*` | gate + dedup + cache (009-010). |
| `src/career_radar/collectors/base.py` | registry of sources (003-008). |
| `src/career_radar/health/check.py` | source health (011). |
| `src/career_radar/scoring/*` | prefilter+evaluate+validate (013). |
| `legacy/jobmatch/pipeline/{process,state}.py` | Reference: resumable batches + pause-on-quota + status persistence. |

## Dependencies
- **Projects:** EATP-004..011, EATP-013.
- **Libraries:** (none new).

## Scope
**In:**
- pipeline.py: run() = collect -> gate -> dedup -> cache -> prefilter -> AI evaluate -> validate -> rank -> persist, STREAMING per source to JSONL and checkpointing between stages.
- Resume: a paused (AI quota) or crashed run continues from the last checkpoint instead of restarting (no re-scrape, no re-pay AI).
- Progress events at every stage/percent (Spanish phase text) to the event bus.
- Memory safety: one source in memory at a time; block-wise writes; never hold all raw HTML; explicit checkpoints (the Bramvel OOM lesson).
- Wire in source-health into the RunResult.
- Knobs: source set, AI cap, recency window, 'fast' (HTTP/JSON sources only) vs 'thorough' (all sources incl. browser).
- Tests: a full run over fixtures (mock AI) yields a valid RunResult; a simulated mid-run stop resumes correctly.

**Out:**
- Web server/frontend (015-016).
- Packaging/scheduling (018).

## Deliverables
- src/career_radar/pipeline.py
- data/{status,results}.json writers
- tests/test_pipeline.py

## Key design decisions & constraints
- One source in memory at a time; stream raw to JSONL; gate/dedup incrementally.
- Checkpoint after collect, after gate, after AI — resume never re-scrapes or re-pays AI.
- Default mode = thorough (best coverage); fast mode drops browser sources.
- Emit human Spanish phase text ('Buscando en Remotive...', 'Evaluando 24 vacantes...').

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2.5-3 h).

## Open questions for Kevin
- Default mode on the Run button: 'thorough' (best coverage, slower) or 'fast' (HTTP/JSON only, ~a couple minutes)? (Suggest thorough default + a fast toggle.)
