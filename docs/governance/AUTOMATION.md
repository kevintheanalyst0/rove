# Automation — daily scheduled run (documented, not activated)

Rove runs on demand: Kevin opens the web UI and clicks "Iniciar". This file
documents how to add a **daily unattended run** on top of that, for if/when Kevin wants
it. **It is not wired up.** Nothing in this repo runs on a schedule today.

## Why it's off by default

- **AI quota.** Every run spends part of the free daily AI quota (`docs/governance/AI-PROVIDERS.md`).
  An unattended daily run competes with any manual runs Kevin does the same day.
- **Manual captcha/login.** Indeed can ask for human verification
  mid-run (`collectors/browser.py: request_manual_intervention`). A run started by
  Windows Task Scheduler with nobody watching can't solve that — it just waits up to
  5 minutes and skips that source (see EATP-006 checklist notes).

Given those two constraints, an unattended daily run is safe to leave running
unsupervised **only** in the sense that it won't crash or corrupt data (the
orchestrator is checkpointed/resumable, CLAUDE.md golden rule 3) — but some days it
will silently under-collect from Indeed if a captcha comes up while Kevin's
away. That trade-off is his call, which is why this stays opt-in.

## The recipe, if Kevin wants it

**1. A one-shot run script**, invoked headless (no browser UI shown to the scheduler
   itself — the browser-driven collectors still open their own Chromium window under
   WSLg for the manual-intervention case):

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
- Trigger: daily, at a time Kevin is likely to be at his computer (so he can solve a
  captcha if one comes up) — e.g. weekday mornings.
- "Run whether user is logged on or not" should stay **unchecked**: WSLg needs an
  active Windows session to show the Chromium window for captcha/login prompts.

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
