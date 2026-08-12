# EATP-014 — Orchestrator & resumable/memory-safe run — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Wire the flow
- [ ] streamed collect->gate->dedup->cache
- [ ] prefilter->AI->validate->rank
- [ ] persist status/results

### Phase 2 — Resume & memory safety
- [ ] checkpoints
- [ ] resume logic
- [ ] block-wise writes
- [ ] OOM review

### Phase 3 — Knobs, events & health
- [ ] fast/thorough modes
- [ ] progress events (ES)
- [ ] wire source-health

### Phase 4 — Close
- [ ] full-run + resume tests
- [ ] pytest
- [ ] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
|  |  |  |  |

**Total project time:** _tbd_

## Session notes
<3-6 lines: what was built, key decisions, anything the next project should know.>
