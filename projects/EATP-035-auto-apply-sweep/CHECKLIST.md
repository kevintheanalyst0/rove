# EATP-035 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases

### Phase 1 — Sweep script + systemd units
- [ ] Sweep logic: iterate `draft_ready` entries, call `apply.submit`.
- [ ] `deploy/systemd/rove-presubmit-sweep.service` + `.timer`.
- [ ] Add install steps to `deploy/setup_vm.sh` (idempotent).

### Phase 2 — Deploy & validate on the real VM
- [ ] Install on `rove-vm`, confirm `enabled` + survives reboot.
- [ ] Watch 2+ real daily cycles via `journalctl` — sweep finishes before
      `rove-daily-run.timer` fires; drafts actually get sent.

### Phase 3 — Verify & close
- [ ] `pytest` green
- [ ] Update ROADMAP status + total time
- [ ] Write session notes below
- [ ] Commit to git (CLAUDE.md §10) — one commit, clear message

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
|  |  |  |  |

**Total project time:** _tbd_

## Session notes
<3–6 lines: what was built, key decisions, anything the next project should know.>
