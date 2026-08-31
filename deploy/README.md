# deploy/ — Oracle VM setup (EATP-032)

What actually runs on `rove-vm` (Oracle Cloud, Always Free, `mx-queretaro-1`),
captured here so a lost VM doesn't mean redoing an hour of manual SSH
commands from scratch. See `projects/EATP-032-deploy-oracle-vm/` for the
full story and decisions behind this.

## Getting a VM in the first place

Not part of this script — Oracle's Always Free capacity in this region is
often exhausted. `.github/workflows/retry-oci-vm.yml` (currently disabled
once `rove-vm` was up; `gh workflow enable "Retry OCI VM launch"` to
reactivate) retries every 15 minutes until a slot opens, using OCI API
credentials stored as GitHub Actions secrets. A durable copy of the OCI API
key and the VM's SSH keypair lives on Kevin's Windows machine under
`Downloads/` (`OCI_PRIVATE_KEY.txt`, `rove_vm_ssh_private_key.txt` /
`_public_key.txt`) if local `oci` CLI access is ever needed again.

## Setting up a VM once it exists

1. Clone this repo to `~/rove` on the VM (SSH user `ubuntu` on the Ubuntu
   22.04 images this has been used with).
2. Copy `.env` into `~/rove/.env` from Kevin's own machine — never
   generated or committed here, it has real API keys. Same treatment for
   `data/resume.pdf` (EATP-034 — Kevin's real CV, used to fill the resume
   field on real applications; auto-apply degrades gracefully without it,
   just can't fill that one required field).
3. Run `~/rove/deploy/setup_vm.sh`. It installs `uv`, syncs dependencies,
   installs Playwright's Chromium (EATP-034 — separate download from the
   Python package, ARM/aarch64 build), installs Tailscale (without starting
   it), installs `fail2ban`/`ufw`/`stress-ng`, configures the firewall, and
   installs+enables the systemd units in `deploy/systemd/`.
4. The script prints two steps it cannot do itself — both require opening a
   real browser login, which only the Tailscale account owner can do:
   - `sudo tailscale up --hostname=rove-vm --ssh`, then open the URL it
     prints.
   - Fill `rove-web.service`'s `__TAILSCALE_IP__`/`__TAILSCALE_MAGICDNS_NAME__`
     placeholders with this VM's real Tailscale address (`tailscale ip -4`,
     `tailscale status --json`), then start `rove-web`.

## What's here

- `setup_vm.sh` — the script above.
- `systemd/rove-web.service` — the FastAPI app itself, `Restart=always`,
  `ROVE_AUTO_SHUTDOWN=0` (server mode never self-kills for lack of an open
  browser tab — see EATP-023/032), bound to `0.0.0.0:8000` (safe: `ufw`
  restricts anything but Tailscale from reaching that port at all).
- `systemd/rove-daily-run.{service,timer}` — fires `POST /run` against the
  already-running server at 13:00 UTC (7am Kevin's fixed UTC-6 time) daily.
- `systemd/rove-keepalive.{service,timer}` — a `stress-ng` CPU burn every 15
  minutes, ~20% duty cycle. Not about performance: Oracle reclaims an
  Always Free instance whose 7-day 95th-percentile CPU/network/memory
  utilization all stay under 20%, and Rove's real daily workload alone
  (~10-15 min/day) doesn't clear that bar. See
  `projects/EATP-032-deploy-oracle-vm/CHECKLIST.md` Phase 9 for the math.

## Why SSH stays public

`ufw` locks down everything except port 22 (public, hardened with
`fail2ban`) and the `tailscale0` interface (full access — this is how the
web app is actually reached). Restricting SSH to Tailscale-only was
considered and rejected: this Claude Code sandbox is not a member of
Kevin's tailnet and reaches the VM by its public IP, so that would cut off
direct VM access for this and every future session, for a marginal security
gain given key-only auth (already the default) already makes brute-force
attacks impractical. Kevin's own call when presented with the tradeoff.
