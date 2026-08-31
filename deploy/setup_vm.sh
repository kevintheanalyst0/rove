#!/usr/bin/env bash
# EATP-032 — idempotent setup for Rove's always-on server mode on a fresh
# Ubuntu 22.04 VM (built against Oracle Cloud's Always Free A1.Flex shape,
# but nothing here is Oracle-specific). Turns what was originally ~1h of
# manual SSH commands into: run this script, then two steps that genuinely
# can't be scripted (see the end of this file).
#
# Prerequisites this script assumes are already done:
#   - This repo is cloned to ~/rove (this script lives at ~/rove/deploy/).
#   - `.env` has been copied into ~/rove/.env (has secrets — must come from
#     Kevin's own machine, never generated or stored here).
#   - EATP-034: `data/resume.pdf` has been copied into ~/rove/data/resume.pdf
#     (Kevin's real CV — same treatment as `.env`, never generated/stored
#     here, gitignored). Auto-apply's submit step silently can't fill the
#     resume field without it; nothing in this script depends on it though.
#
# Safe to re-run: apt/systemctl steps are idempotent, `uv sync` is a no-op
# if already synced, `ufw`/`fail2ban` rules just get reasserted.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "==> [1/7] Installing uv, syncing Python deps"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv sync --extra dev

echo "==> [2/7] Installing Playwright's Chromium (EATP-034 — headless
    apply-form automation; separate from the Python package above, which
    uv sync already installed). This is the ARM/aarch64 build, cached at
    ~/.cache/ms-playwright — a different path/arch than the Windows build
    DEPENDENCIES.md describes for Kevin's desktop copy."
uv run playwright install --with-deps chromium

echo "==> [3/7] Installing Tailscale (not started yet — see manual step below)"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

echo "==> [4/7] Installing fail2ban, ufw, stress-ng"
sudo apt-get update -qq
sudo apt-get install -y -qq fail2ban ufw stress-ng

echo "==> [5/7] Configuring fail2ban (sshd jail — SSH stays public, hardened
    instead of Tailscale-restricted, so this machine and future sessions
    keep direct access; see docs/adr and EATP-032's charter for why)"
sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[sshd]
enabled = true
port = 22
maxretry = 4
bantime = 1h
findtime = 10m
EOF
sudo systemctl enable --now fail2ban

echo "==> [6/7] Configuring ufw (SSH public; everything else Tailscale-only)"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH - public, key-only + fail2ban'
sudo ufw allow in on tailscale0 comment 'Tailscale tailnet - full access'
sudo ufw --force enable

echo "==> [7/7] Installing systemd units (rove-web, rove-daily-run, rove-keepalive)"
sudo cp "$REPO_DIR"/deploy/systemd/*.service "$REPO_DIR"/deploy/systemd/*.timer \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rove-daily-run.timer rove-keepalive.timer
# rove-web is enabled last, deliberately NOT started yet — it needs
# ROVE_EXTRA_ALLOWED_HOSTS filled in with this VM's real Tailscale address
# first (see manual step 2 below), or every request from Kevin's phone
# will 403 as cross-origin.
sudo systemctl enable rove-web

cat <<'EOF'

==> Scripted part done. Two steps only Kevin (or whoever owns the Tailscale
    account) can do, since they require opening a real login URL:

  1. sudo tailscale up --hostname=rove-vm --ssh
     -> open the auth URL it prints, log into the Tailscale account.

  2. Fill in this VM's real address, then start the web server:
     tailscale ip -4          # -> e.g. 100.x.x.x
     tailscale status --json | python3 -c \
       "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'])"
     sudo sed -i \
       -e "s/__TAILSCALE_IP__/<the IP above>/" \
       -e "s/__TAILSCALE_MAGICDNS_NAME__/<the DNSName above, no trailing dot>/" \
       /etc/systemd/system/rove-web.service
     sudo systemctl daemon-reload
     sudo systemctl start rove-web

  Then verify: curl http://<tailscale-ip>:8000/ from another machine on the
  same tailnet should return 200; from the VM's public IP it should time out.
EOF
