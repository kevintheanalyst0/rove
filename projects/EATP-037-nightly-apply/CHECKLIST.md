# EATP-037 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases
### Phase 0 — Spikes (no submissions, nothing sent)
- [x] Read Claude quota from WSL the way Pulse does (2026-11-22: session 45 %, weekly 45 %)
- [x] Check hibernation / wake-timer support with `powercfg` (2026-11-22: hibernation disabled, S0 only)
- [x] Compare Kevin's CVs on `D:` with the ones in Notion (identical, SHA-256)
- [x] `claude -p --chrome` drives Chrome from WSL on a sample page (2026-11-22, Haiku, 9 turns, no denials)
- [x] Same on a real OCC vacancy, no submit (2026-11-22: opened, clicked Postularme, listed 9 questions, closed, nothing sent)
- [ ] Same with the screen locked after a timed wake, then a multi-vacancy batch that fills a form
- [x] Chrome behaviour with the screen locked after waking (2026-11-22 short test: usable)
- [x] Enable hibernation (2026-11-22, Kevin approved the admin prompt; Fast Startup off)
- [x] Timed wake from hibernation, short test (2026-11-22, 87 s, worked)
- [x] Verify a keep-awake request stops Windows re-sleeping after a timed wake (2026-11-22: re-hibernated after ~2 min without it; with it, 6 min clean)
- [ ] Overnight multi-hour timed wake (Vigilante repo)
- [ ] OCC / Computrabajo apply flows: captcha? account?

### Phase 1 — Rove side
- [x] Review lists: skipped vacancies, pending questions (2026-11-22)
- [x] Kill switch + settings (enabled, skip_next_run, pause_until, weekly_cap_pct) in API and dashboard (2026-11-22)
- [~] Answer-a-question flow done (`learned_answers.jsonl`, `vacancies_to_retry`); the `applicant_answers.toml` loader belongs to the runner (Phase 2)
- [x] Tests (fixtures, no live AI): 72 new, suite 493 green

### Phase 2 — PC runner
- [x] Wrapper: preflight (switch, quota), batches, per-vacancy progress, summary, hibernate (code + tests with fakes, 2026-11-22; `--dry-run` checked live)
- [~] Playbook prompt written (`prompt.py`, 11 rules + JSON contract); not yet run live: that is the supervised batch
- [ ] Windows scheduled task (wake to run)
- [ ] Vigilante rule: hibernate instead of shutdown before a scheduled wake

### Phase 3 — Rollout
- [x] Dry run (no submit): `--dry-run` against the real Rove (2026-11-22)
- [x] Supervised real run with Kevin present (2026-11-22: 2 sent, 4 skipped; see CHARTER)
- [x] First supervised runner batch, 3 vacancies (2026-11-22): 0 sent, 2 dismissed, 1 question; ~4 min; window 42 -> 43 %. The `applied` path is not yet proven live.
- [ ] First unattended night; read the summary together

### Phase 4 — Verify & close
- [ ] `pytest` green
- [ ] Update ROADMAP status + total time
- [ ] Sync Notion (Rove page, Vigilante page) and the Vigilante repo docs
- [ ] Write session notes below
- [ ] Commit to git (CLAUDE.md §10) — one commit, clear message

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-11-22 | Planning + read-only spikes | tbd | Plan agreed with Kevin; nothing built |
| 2026-11-22 | Phase 2 A+B — runner code (night) | ~1 h 30 min (estimate, not timed live) | selector, outcomes, quota, prompt, runner, pc ports, 59 tests; live dry run OK |
| 2026-11-22 | Phase 1 — Rove side (evening) | ~1 h 15 min (estimate, not timed live) | stores, routes, dashboard panel, 72 tests; not deployed |

**Total project time:** _tbd_

## Session notes
2026-11-22: planning only. Charter written, three read-only spikes done (quota read,
powercfg, CV comparison). Nothing was submitted, installed or changed on the PC.
Later the same day Kevin approved his answers (`data/applicant_answers.toml`, created locally,
gitignored) and decided the Workday question: trial for a few days, then he creates accounts by
hand if there are many. Employment-status questions stay with Kevin, never answered by Claude.

2026-11-22 (night): Phase 1 built (stores, routes, dashboard panel, 72 tests) and deployed to the VM with
Kevin's go; verified over Tailscale. Next: Phase 2, the PC-side runner.
