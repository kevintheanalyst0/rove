# EATP-032 — Checklist & time log

## Phases

- [x] **Phase 1 — Provisioning (2026-08-26, prior session).** Oracle signup
      with `mx-queretaro-1` as home region. IP-block spike from real Cloud
      Shell egress: OCC + Computrabajo both clean, no captcha markers.
      Always Free capacity exhausted on signup day (both `A1.Flex` and
      `E2.1.Micro` shapes, "Out of host capacity" every attempt). Built
      `.github/workflows/retry-oci-vm.yml` — idempotent, 15-min schedule,
      tries ARM then AMD, no-ops once `rove-vm` is RUNNING. OCI API creds as
      GitHub Actions secrets; durable local copies of the OCI key and the
      VM's SSH keypair on Kevin's Windows Downloads folder as a fallback.
      Networking (VCN, subnet, internet gateway, security list allowing
      inbound 22 from 0.0.0.0/0) provisioned ahead of the VM itself.
- [x] **Phase 2 — VM lands (2026-08-27, this session).** The retry workflow
      succeeded faster than the ~5-day estimate — `VM.Standard.A1.Flex`
      (1 OCPU/6GB, ARM). The workflow's
      `GITHUB_STEP_SUMMARY` output (where it normally reports the IP) isn't
      readable via `gh api`; patched the workflow to also echo the IP to
      plain stdout so a future session can pull it with
      `gh run view <id> --log | grep "IP pública"` instead of needing OCI
      CLI credentials locally (which aren't available outside the GitHub
      Actions secrets).
- [x] **Phase 3 — Install Rove on the VM.** `git` clone via a one-time
      `gh auth token`-authenticated URL, then reset to a plain https remote
      (no token persisted on the VM). Installed `uv`, ran `uv sync`, copied
      `.env` from the Windows machine. Full test suite green on the VM.
- [x] **Phase 4 — Tailscale.** Installed, `sudo tailscale up --hostname=rove-vm
      --ssh` — the auth URL it printed had to be opened by Kevin himself
      (account-owner action, not something this session could do). Landed on
      the tailnet with a working IP and MagicDNS name (not recorded here —
      see the VM itself via `tailscale status`).
- [x] **Phase 5 — Host hardening.** Confirmed password SSH auth already
      disabled (Ubuntu cloud image default) before deciding anything about
      the security list. Presented Kevin the real tradeoff — restrict SSH to
      Tailscale-only vs. keep it public — since restricting it would cut off
      this Claude Code sandbox's own access (not a tailnet member). Kevin:
      "busca la mejor solución." Landed on: `fail2ban` (sshd jail, 4 retries
      / 1h ban) instead of narrowing the security list, plus `ufw`
      default-deny-incoming with explicit allows for port 22 (public) and
      the `tailscale0` interface (full access) — so the *web app* is
      Tailscale-only even though SSH stays reachable from anywhere. Verified
      SSH still worked immediately after enabling `ufw` (didn't lock myself
      out).
- [x] **Phase 6 — `server.py` server-mode toggles.** Added
      `ROVE_EXTRA_ALLOWED_HOSTS` (extends ADR-010's origin/host allowlist
      past 127.0.0.1/localhost) and `ROVE_AUTO_SHUTDOWN=0` (disables
      EATP-023's tab-close self-kill). Both env-gated with the old desktop
      behavior as the untouched default. 360 tests passing locally; pushed,
      pulled onto the VM.
- [x] **Phase 7 — systemd units.** `rove-web.service` (uvicorn, binds
      `0.0.0.0:8000` — safe because `ufw` already restricts non-Tailscale
      ingress on that port — `Restart=always`). `rove-daily-run.timer` +
      `.service` (`OnCalendar=*-*-* 13:00:00 UTC`, i.e. 7am Kevin's fixed
      UTC-6 time; `curl -X POST http://127.0.0.1:8000/run` against the
      already-running server rather than invoking the pipeline as a second
      process). Confirmed VM system clock is UTC and NTP-synced, so the
      `OnCalendar` spec means what it says.
- [x] **Phase 8 — Verify & close.** Live-tested from outside the VM: the app
      returns 200 over the Tailscale IP, is completely unreachable over the
      public IP (connection refused/timeout), the origin/host allowlist
      correctly 403s a spoofed non-Tailscale `Host`/`Origin` and correctly
      accepts a Tailscale one. **Incident during this verification:** an
      allowlist test accidentally used a real `POST /run` instead of a safe
      read-only check, starting a genuine pipeline run; caught within
      seconds and cancelled via `POST /cancel {"discard": true}` — the run
      never reached the AI-evaluation stage (`counts: {}`), so quota impact
      was effectively zero, but it was still an unintended live action and
      is recorded here rather than glossed over. Confirmed all five services
      (`rove-web`, `rove-daily-run.timer`, `tailscaled`, `fail2ban`, `ufw`)
      are `enabled` — survive a reboot with no manual step. Full test suite
      on the VM: 359 passed, 1 failed
      (`test_collector_occ.py::test_absolute_excluded_company_is_filtered_out`)
      — reran in isolation and within just its own file, passed both times;
      this is the same class of pre-existing cross-test-pollution flake
      EATP-027 already documented in this file (different specific test,
      same file, same "passes alone, flakes in full-suite order" signature)
      — not introduced by this project, not chased down here.
- [x] **Phase 9 — Idle-reclaim keep-alive (2026-08-27, same day, Kevin's own
      concern after testing from his phone).** Verified against Oracle's own
      docs (not memory): an Always Free instance is reclaimed if, over a
      7-day window, the 95th percentile of CPU **and** network **and**
      (for A1 shapes) memory utilization all stay under 20% —
      `docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm`.
      Rove's real daily workload (~10-15 min/day) is under 1% of that
      7-day window — nowhere near enough to clear the ~5% mass the 95th
      percentile test actually needs, so the VM was a real reclaim
      candidate despite being genuinely in use. Installed `stress-ng`;
      `rove-keepalive.timer` (`OnUnitActiveSec=15min`) runs
      `rove-keepalive.service` (a 1-core `stress-ng --cpu 1 --timeout 180s`
      burn, ~20% duty cycle, plus a small `curl` against the Ubuntu
      archive mirror already trusted for `apt`) — clearing the CPU
      criterion alone is sufficient since Oracle's rule is an AND of all
      three, comfortable ~4x margin over the bare minimum duty cycle
      needed. Confirmed live: the timer's `OnBootSec` fired it
      immediately without manual intervention, `stress-ng` ran its full
      180s and exited cleanly, next fire scheduled 15 min later. Costs
      nothing (Always Free has no usage-based billing) and doesn't touch
      AI quota or compete with the daily run.

## Time log

| Date | Phase(s) | Time |
|------|----------|------|
| 2026-08-26 | 1 (provisioning, spike, retry workflow) | ~2h (prior session, approximate) |
| 2026-08-27 | 9 (idle-reclaim keep-alive, follow-up) | ~15 min |
| 2026-08-27 | 2-8 (VM lands through verify & close) | ~1h |

**Total: ~3h across two sessions** (approximate — Phase 1's time wasn't
tracked live at the time; backfilled from memory of that session).

## Session notes

Real remote access finally exists: Kevin can reach Rove from his phone via
Tailscale, the daily run fires on its own at 7am his time, and none of it
depends on his laptop being on. The SSH-hardening tradeoff (Phase 5) is the
one decision in this project genuinely worth re-reading before touching the
VM's network config again — it's an intentional choice to keep this session
type's own access working, not an oversight. `docs/governance/AUTOMATION.md`
still describes the old Windows-Task-Scheduler plan and was deliberately not
rewritten (flagged via a note instead) — pick that up as a small follow-up
whenever it's convenient, not urgent. `retry-oci-vm.yml` is now a permanent
harmless no-op (finds `rove-vm` RUNNING, exits) — fine to leave enabled
indefinitely, or Kevin can disable/delete it now that its job is done.
