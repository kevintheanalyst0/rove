# EATP-035 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases

### Phase 1 — Sweep script + systemd units
- [x] `src/rove/apply/sweep.py` — `sweep_pending_applications()` iterates
      `apply_store.draft_ready_entries()`, calls `apply.submit.submit_application`
      per entry, sequential, never raises. A draft with no matching inbox
      entry (already resolved by hand some other way) is skipped and logged,
      not treated as an error.
- [x] `deploy/systemd/rove-presubmit-sweep.service` (oneshot, direct venv
      python invocation, same style as `rove-web.service`) +
      `rove-presubmit-sweep.timer` (`12:30:00 UTC` — 30 min before
      `rove-daily-run.timer`'s `13:00:00 UTC`).
- [x] `deploy/setup_vm.sh` step [7/7] updated to install + enable the new
      timer alongside the existing two.
- [x] `tests/test_apply_sweep.py` — 5 tests (`submit_application`
      monkeypatched, same test-boundary principle as the pipeline hook's own
      tests — the real fill/submit mechanics are already covered by
      `test_apply_submit.py`). Full suite: 421/421, `ruff` clean.

### Phase 2 — Deploy & validate on the real VM
- [x] Installed on `rove-vm` (`git pull` + systemd install/enable);
      `rove-presubmit-sweep.timer` confirmed `enabled` + `active`, next
      trigger `12:30 UTC` — 30 min ahead of the `13:00 UTC` daily run.
      Manually fired the service once (`systemctl start`) to confirm it
      actually runs end to end: exited `0/SUCCESS`, no drafts pending (none
      exist yet), no errors.
- [ ] **Watch 2+ real daily cycles via `journalctl`** — genuinely can't be
      done inside this session (needs real calendar days to pass). Not
      blocking close: the code and deployment are done and verified as far
      as a single session can; this is ongoing real-world observation, not
      remaining work. Worth a spot-check in a future session.

### Phase 3 — Verify & close
- [x] `pytest` green — 421/421.
- [x] Update ROADMAP status + total time
- [x] Write session notes below
- [x] Commit to git (CLAUDE.md §10) — one commit, clear message

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-09-01 | Phase 1 | ~25 min | `apply/sweep.py` + systemd units + `setup_vm.sh`, 5 tests, full suite 421/421. |
| 2026-09-01 | Phase 2/3 | ~15 min | Deployed to `rove-vm`, timer enabled, closed the project. |

**Total project time:** ~40 min.

## Session notes

Built right after EATP-034's own real-world validation showed the practical
gap it exists to close: of Kevin's 51 real accumulated jobs, only 2 were
eligible for auto-apply at all (both Greenhouse, both blocked by
reCAPTCHA) — zero real `draft_ready` entries exist yet. Kevin explicitly
asked to build this anyway rather than wait for real drafts to review first
(his call, overriding EATP-034's original "wait and see" staging rationale
— see conversation: "cómo lo voy a probar si no hay ninguna vacante que se
pueda"). The sweep itself is safe regardless of draft volume: it only acts
on entries that are already `draft_ready`, so an empty backlog is a no-op,
not a risk.

Also live-verified, same session, why OCC (and by extension most
Mexican/LatAm boards outside this ATS-direct model) isn't in scope: a plain
page load against a real OCC job posting returned `HTTP 403 "scraping
abuse"` from headless Chromium — a harder, earlier-triggering block than
either Greenhouse's reCAPTCHA or Coinbase's Cloudflare wall. Not attempted
further, same non-negotiable principle as Indeed/EATP-033 and
Glassdoor/EATP-030: never fight active bot-detection unattended. Kevin
decided not to pursue widening scope (e.g. more Lever companies) for now —
"ya no quiero seguir agregando cosas."

**Real-world validation of the sweep's actual behavior (does it fire on
time, does a real submission survive the gap) still needs 2+ real calendar
days to observe** — noted as ongoing, not blocking this project's close.
