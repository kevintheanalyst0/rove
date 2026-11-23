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
- [ ] Review lists: skipped vacancies, pending questions
- [ ] Kill switch + settings (enabled, skip_tonight, pause_until, weekly_cap_pct) in API and dashboard
- [ ] `data/applicant_answers.toml` loader (gitignored) + answer-a-question flow that requeues the vacancy
- [ ] Tests (fixtures, no live AI)

### Phase 2 — PC runner
- [ ] Wrapper: preflight (switch, quota), batches, per-vacancy progress, cleanup, summary, hibernate
- [ ] Playbook prompt (rules in the charter)
- [ ] Windows scheduled task (wake to run)
- [ ] Vigilante rule: hibernate instead of shutdown before a scheduled wake

### Phase 3 — Rollout
- [ ] Dry run (no submit)
- [x] Supervised real run with Kevin present (2026-11-22: 2 sent, 4 skipped; see CHARTER)
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

**Total project time:** _tbd_

## Session notes
2026-11-22: planning only. Charter written, three read-only spikes done (quota read,
powercfg, CV comparison). Nothing was submitted, installed or changed on the PC.
Later the same day Kevin approved his answers (`data/applicant_answers.toml`, created locally,
gitignored) and decided the Workday question: trial for a few days, then he creates accounts by
hand if there are many. Employment-status questions stay with Kevin, never answered by Claude.
