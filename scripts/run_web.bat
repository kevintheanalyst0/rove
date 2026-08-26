@echo off
REM Rove — one-click launch on native Windows (EATP-025).
REM
REM Replaces scripts/run_web.sh, which drove uvicorn inside WSL and reached
REM Windows through interop. The project runs natively now, so this is a
REM plain Windows launcher: no wsl.exe, no interop, no WSLg.
REM
REM Started hidden by "Rove.vbs" (no console window). The server
REM shuts itself down once the browser tab closes (server.py's tab-close
REM watcher), so there is nothing here to close by hand.

cd /d "%~dp0.."

if "%ROVE_PORT%"=="" set ROVE_PORT=8000
set CR_URL=http://127.0.0.1:%ROVE_PORT%/

REM Rove is installed as a PWA in Edge (edge://apps). Activating it
REM by its Shell app identity (AUMID) is what makes Windows give the window
REM Rove's own taskbar icon — plain `msedge --app=URL` does not, it
REM just opens a popup inside Edge's existing process and inherits Edge's
REM icon (confirmed live, EATP-023). Overridable via the environment in case
REM the app is ever reinstalled and Windows assigns a new AUMID.
REM
REM No hardcoded default (unlike the old Career Radar launcher this was
REM forked from): that AUMID belonged to Career Radar's own Shell identity,
REM not Rove's. Until Rove is reinstalled as its own PWA and ROVE_APP_AUMID
REM is set to its real AUMID, fall back to a plain msedge window — works,
REM just without the dedicated taskbar icon.
REM Wait for the server to actually accept connections before opening the
REM window — a fixed sleep would either race a slow start or waste time on a
REM fast one. Runs in the background so uvicorn itself can hold the
REM foreground and keep this script (and the hidden console) alive.
if "%ROVE_APP_AUMID%"=="" (
  start "" /b powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
    "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -Uri '%CR_URL%' -UseBasicParsing -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }; Start-Process msedge.exe ('--app=' + '%CR_URL%')"
) else (
  start "" /b powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
    "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -Uri '%CR_URL%' -UseBasicParsing -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }; Start-Process explorer.exe 'shell:AppsFolder\%ROVE_APP_AUMID%'"
)

.venv\Scripts\python.exe -m uvicorn rove.web.server:app --host 127.0.0.1 --port %ROVE_PORT% --log-level warning
