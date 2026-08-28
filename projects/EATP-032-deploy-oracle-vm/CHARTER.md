# EATP-032 — Deploy to an always-on Oracle Cloud VM

> **Backfilled 2026-08-27.** This project was built across two sessions
> (2026-08-26 provisioning, 2026-08-27 configuration) without the usual
> charter-before-building ceremony — it grew organically out of "let's
> finally deploy this thing" rather than a planned session. This charter
> documents the decision as made, not as originally proposed; the
> CHECKLIST.md carries the real phase-by-phase record.

## Objective

Get Rove running unattended, 24/7, without Kevin's laptop, reachable from
his phone to review/apply/dismiss jobs — the actual reason this repo forked
off Career Radar in the first place (see `ROADMAP.md` P32), not just the
rename. Concretely: a real remote machine running the daily pipeline on its
own schedule, serving the same web UI Kevin already uses locally, private
(not exposed to the open internet), and resilient to a reboot.

## Problems solved

- **P32** — Rove needs to run unattended, reachable from Kevin's phone, with
  nothing lost if he doesn't check in for days.

## Key decisions

- **Provider: Oracle Cloud, Always Free tier, `mx-queretaro-1` (Mexico
  Central) as home region.** Chosen after a real IP-block risk spike:
  curled OCC's and Computrabajo's actual search URLs from a genuine
  Querétaro egress IP (via OCI Cloud Shell) and got clean, full HTML with no
  captcha/challenge markers — the two biggest collectors are confirmed safe
  from that IP. Free-tier capacity in that region's one availability domain
  was exhausted at signup time; solved with an idempotent GitHub Actions
  workflow (`retry-oci-vm.yml`, `*/15 * * * *`, checks for a RUNNING
  `rove-vm` first and no-ops if found) that retried until a slot opened —
  landed one faster than the ~5-day estimate Kevin had accepted.
- **Access: Tailscale, not a public port.** The web app (job data, "Apliqué"/
  "No me interesa" actions) is reachable only over Kevin's own tailnet — his
  phone needs the Tailscale app installed and logged into the same account.
  The VM's public IP exists only for SSH and the OCI networking layer
  itself; nothing job-related is ever exposed to the open internet.
- **SSH: kept public, hardened instead of restricted.** The alternative —
  locking port 22 to Tailscale-sourced traffic only — was rejected because
  this Claude Code sandbox is not a member of Kevin's tailnet and reaches
  the VM by its public IP; restricting SSH would have cut off direct VM
  access for this and every future session, in exchange for a marginal gain
  given key-only auth (already the default, password auth confirmed
  disabled) already makes brute-force attacks impractical. Kevin's own call
  when presented with the tradeoff ("busca la mejor solución"): `fail2ban`
  on the sshd jail instead, `ufw` restricting everything *else* to the
  `tailscale0` interface.
- **Daily run: a systemd timer hitting the running server's own `/run`
  endpoint**, not a separate cron invoking the pipeline as its own process.
  Keeps exactly one code path for "start a run" (the same one the UI uses),
  so there's no risk of the timer and a phone-initiated manual run
  overlapping in ways the app's own `running` lock doesn't already handle.
- **`server.py` needed two behavior changes for server mode, both env-gated
  so desktop launchers are untouched:** EATP-023's tab-close auto-shutdown
  assumes a desktop session with one browser tab; an always-on server with
  a phone checking in sporadically must never self-kill for looking
  tab-less. ADR-010's same-origin/host allowlist hardcoded
  127.0.0.1/localhost, which would 403 every legitimate Tailscale-origin
  request.

## Scope

**In:** VM provisioning (already running by the time this charter was
written), Rove installed + tested on it, Tailscale, host hardening
(fail2ban + ufw), `server.py`'s two server-mode toggles, `rove-web` and
`rove-daily-run` systemd units, reboot-survival verification.

**Out (flagged, not this project):**
- Rewriting `docs/governance/AUTOMATION.md` for this VM-based approach — it
  still describes the original Windows-Task-Scheduler plan; a note points
  here instead.
- Retiring `retry-oci-vm.yml` now that its job is done (it's a harmless
  no-op every 15 min going forward) — Kevin's call, not made yet.
- Anything about Indeed — that became its own project (EATP-033) once
  Kevin decided mid-session, surfaced by this deploy work but solved for a
  different reason than the display/headless issue that first came up.

## Definition of Done

Standard CLAUDE.md §9, plus everything in CHECKLIST.md's Phase 8 verify step.
