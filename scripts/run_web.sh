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

# Two launchers, one script (Kevin's call, EATP-019 — mirrors legacy's two
# separate .bat files): CAREER_RADAR_AUTOSTART=1 kicks off a full pipeline
# run before opening the browser, so the page loads straight into the
# spinner instead of Kevin having to click "Iniciar búsqueda" himself. Unset
# (the default) just opens whatever's already there — the last results if
# any, otherwise the idle "Iniciar búsqueda" screen — no run is started.
if [ "${CAREER_RADAR_AUTOSTART:-0}" = "1" ]; then
  curl -s -X POST "${URL}run" -H "Content-Type: application/json" -d '{}' >/dev/null || true
fi

open_browser() {
  if grep -qi microsoft /proc/version 2>/dev/null; then
    # WSL: no GUI browser on the Linux side — hand the URL to Windows.
    explorer.exe "$URL" >/dev/null 2>&1 && return 0
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

echo "Career Radar corriendo en $URL — cierra esta ventana para detenerlo."
wait "$SERVER_PID"
