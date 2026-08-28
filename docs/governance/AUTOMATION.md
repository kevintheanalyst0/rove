# Automation — daily scheduled run

On Kevin's own machine, Rove still runs on demand: he opens the web UI and clicks
"Iniciar". This file originally documented how to *add* a daily unattended run on top
of that — as of EATP-032 (2026-08-27) that's no longer hypothetical, it's live, just
not via the recipe below.

> **EATP-032 superseded this file's original plan.** A scheduled run now actually
> exists — a systemd timer on Kevin's always-on Oracle VM (`rove-daily-run.timer`,
> fires `POST /run` at 13:00 UTC = 7am Kevin's fixed UTC-6 time against the
> `rove-web.service` already running there), not the Windows Task Scheduler + WSL
> recipe below. That recipe is left as-is — still valid if Rove ever needs a scheduled
> run on a Windows box specifically — but it is not what actually runs today. See
> `projects/EATP-032-deploy-oracle-vm/` for the full setup.

## Why it's off by default (on Kevin's own machine — see the EATP-032 note above for the VM)

- **AI quota.** Every run spends part of the free daily AI quota (`docs/governance/AI-PROVIDERS.md`).
  An unattended daily run competes with any manual runs Kevin does the same day.

Given that constraint, an unattended daily run is safe to leave running
unsupervised in the sense that it won't crash or corrupt data (the
orchestrator is checkpointed/resumable, CLAUDE.md golden rule 3). Indeed used to be a
second constraint here (its captchas needed Kevin at the screen) — moot since EATP-033
removed it entirely.

## The recipe, if Kevin wants it

**1. A one-shot run script**, invoked headless (no browser UI shown to the scheduler
   itself):

```bash
# scripts/run_once.sh (would need to be added if this is activated)
#!/usr/bin/env bash
cd "$(dirname "$0")/.."
source .venv/bin/activate
python -c "from rove.pipeline import run; run(mode='thorough')"
```

**2. Windows Task Scheduler**, running that script inside WSL once a day:

- Program/script: `wsl.exe`
- Arguments: `-d Ubuntu -- bash -lc "/home/kevin/Projects/rove/scripts/run_once.sh >> /home/kevin/Projects/rove/data/cron.log 2>&1"`
- Trigger: daily, e.g. weekday mornings.
- "Run whether user is logged on or not" can stay checked — no browser-driven
  collector needs an active Windows session anymore (EATP-033).

**3. Checking results.** `data/results.json` and `data/status.json`
  (`rove.config.RESULTS_FILE` / `STATUS_FILE`) are updated in place by every
  run, scheduled or manual. Opening the web UI after a scheduled run shows it exactly
  like a manual one — no separate "scheduled results" view needed.

## Not built

- No notification when a scheduled run finds a new A-grade match — Kevin doesn't want
  this (decided 2026-08-12, EATP-018). If that changes later, `pipeline.run()`'s
  `RunResult` already has everything needed (`jobs`, graded) to add one without
  touching the pipeline itself.
- No `scripts/run_once.sh` file yet — the snippet above is the recipe; create it only
  when Kevin actually turns this on.
