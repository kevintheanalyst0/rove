#!/usr/bin/env bash
# One-click launch (EATP-015 / ADR-004): start the web UI and open it in the
# browser — no terminal interaction required from Kevin beyond running this.
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

HOST="127.0.0.1"
PORT="${CAREER_RADAR_PORT:-8000}"
URL="http://${HOST}:${PORT}/"

"$BASE_DIR/.venv/bin/python" -m uvicorn career_radar.web.server:app \
  --host "$HOST" --port "$PORT" --log-level warning &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

# Wait for the server to actually accept connections instead of guessing
# with a fixed sleep — a slow box shouldn't open the browser too early.
for _ in $(seq 1 50); do
  if curl -s -o /dev/null "$URL"; then
    break
  fi
  sleep 0.2
done

# Career Radar is installed as a PWA in Kevin's Edge (edge://apps). Its Shell
# app identity (AUMID) — found via `(New-Object -ComObject Shell.Application
# ).NameSpace('shell:AppsFolder').Items()` — activates it exactly the way
# Windows does when Kevin opens it from Start or a pinned taskbar icon.
#
# This matters because raw `msedge --app=URL` / `--app-id=X` (tried first,
# 2026-08-15/16) never show Career Radar's own taskbar icon, even with the
# PWA genuinely installed: Edge is already running in the background
# (`--no-startup-window`), so both of those just forward the request via
# Chromium's single-instance IPC into a new popup *inside that same existing
# process* — which only ever carries Edge's own generic icon. Only a real
# Shell activation (this one) makes Windows assign the window its own
# AppUserModelID/icon, confirmed by Kevin live (2026-08-16): a window opened
# this way showed the correct icon; `--app=`/`--app-id=` windows moments
# before did not.
#
# `explorer.exe`'s own exit code is unreliable here (nonzero even on a
# successful activation) — don't chain it to a fallback with `&&`, that
# would silently open a second, redundant window every single launch.
# Overridable (edge://apps → app → Detalles) in case Kevin ever reinstalls
# the app and Windows assigns a new AUMID.
APP_AUMID="${CAREER_RADAR_APP_AUMID:-127.0.0.1-4FF64651_pfncv7bjx4w4g!App}"

open_browser() {
  if grep -qi microsoft /proc/version 2>/dev/null; then
    # WSL: no GUI browser on the Linux side — hand the URL to Windows.
    if [ -n "$APP_AUMID" ]; then
      # `|| true`, not just "don't chain a fallback": `set -e` (top of this
      # script) kills the WHOLE script on any nonzero exit, not only ones
      # you explicitly check — explorer.exe's unreliable exit code took the
      # server down with it seconds after opening the window (2026-08-16,
      # Kevin's live test: correct icon, but "127.0.0.1 rechazó la
      # conexión" — the script's own EXIT trap had already killed uvicorn).
      explorer.exe "shell:AppsFolder\\${APP_AUMID}" >/dev/null 2>&1 || true
      return 0
    fi
    cmd.exe /c start "" msedge --app="$URL" >/dev/null 2>&1 && return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 && return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 && return 0
  fi
  "$BASE_DIR/.venv/bin/python" -m webbrowser "$URL" >/dev/null 2>&1 && return 0
  echo "Career Radar está corriendo en $URL — ábrelo manualmente en tu navegador."
}

open_browser

# EATP-023: no visible console to close anymore (the .vbs launcher hides
# it) — the server watches its own SSE subscriber count and shuts itself
# down once Kevin closes the browser tab (see server.py's tab-close
# watcher). This echo only matters if someone's running the script directly
# in a real terminal for debugging.
echo "Career Radar corriendo en $URL — se apaga solo al cerrar la pestaña del navegador."
wait "$SERVER_PID"