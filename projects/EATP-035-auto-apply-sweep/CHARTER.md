# EATP-035 — Unattended pre-run submit sweep

## Objective
Add the fully unattended half of auto-apply: a daily sweep that sends every
still-pending `draft_ready` application (from EATP-034's engine) automatically,
timed to finish before the next day's 7am collection run — so each new run
starts with only D-grade jobs and genuinely `manual_required` jobs left open.
Ships once EATP-034's draft quality has been validated on real jobs for a few
days; not meant to start the same session EATP-034 finishes.

## Problems solved
**P33** (continued from EATP-034) — the "must not linger past the next run"
half of Kevin's requirement.

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `docs/adr/ADR-011-auto-apply-draft-and-sweep.md` | The sweep design this project implements. |
| `src/rove/apply/store.py`, `submit.py` | Built in EATP-034 — reused as-is. |
| `deploy/systemd/rove-daily-run.timer`, `rove-keepalive.timer` | Pattern to mirror for the new timer/service pair. |
| `deploy/setup_vm.sh` | Where the new timer gets installed idempotently. |

## Dependencies
- **Projects:** EATP-034 must be ✅ first, and its draft output should have
  been eyeballed by Kevin on real jobs for a few days before this ships — not
  a hard technical dependency, but the whole point of splitting these two
  projects apart.
- **Libraries:** none new.

## Scope
**In:**
- `rove-presubmit-sweep.timer` + `.service`, firing shortly before 13:00 UTC
  (e.g. 12:30 UTC / 6:30am MX).
- Sweep logic: every `draft_ready` `ApplicationEntry` not yet sent →
  `apply.submit`.
- Add to `deploy/setup_vm.sh` (idempotent, like the existing units).

**Out:**
- Any change to EATP-034's draft-preparation logic itself.
- Per-job timers or configurable deadlines — the sweep IS the deadline
  mechanism (ADR-011 §5).

## Key design decisions & constraints
- One daily sweep, not a per-job 24h timer — see ADR-011 §5 for why.
- Must reliably finish before `rove-daily-run.timer` fires — verify over a
  couple of real days via `journalctl` timestamps before trusting it
  unattended, per EATP-034's Definition of Done precedent.

## Definition of Done
- [x] Deliverables exist and work.
- [x] `pytest` green — 421/421.
- [x] No OOM/crash risk left (same sequential/memory-aware discipline as EATP-034).
- [x] Checklist ticked, time logged.
- [x] ROADMAP status → ✅.
- [x] Session notes written.
- [x] Committed to git (CLAUDE.md §10) and deployed to `rove-vm`.
- [ ] **Not yet observable this session:** verified over 2+ real days that the
      sweep completes before the daily run and drafts actually get sent —
      needs real calendar time; the code/deploy side is done and correct as
      far as one session can confirm.

## Estimated time
Light-medium — ~1-1.5h. Mostly deploy plumbing; the hard part (submit logic)
already exists from EATP-034.

## Open questions for Kevin
- None expected — timing/design already decided in the EATP-034 planning
  conversation (2026-08-30). Confirm he's actually seen and is happy with a
  few days of EATP-034's real drafts before starting this project.
