@echo off
REM Career Radar — one-click launch on native Windows (EATP-025).
REM
REM Replaces scripts/run_web.sh, which drove uvicorn inside WSL and reached
REM Windows through interop. The project runs natively now, so this is a
REM plain Windows launcher: no wsl.exe, no interop, no WSLg.
REM
REM Started hidden by "Career Radar.vbs" (no console window). The server
REM shuts itself down once the browser tab closes (server.py's tab-close
REM watcher), so there is nothing here to close by hand.

cd /d "%~dp0.."

if "%CAREER_RADAR_PORT%"=="" set CAREER_RADAR_PORT=8000
set CR_URL=http://127.0.0.1:%CAREER_RADAR_PORT%/

REM Career Radar is installed as a PWA in Edge (edge://apps). Activating it
REM by its Shell app identity (AUMID) is what makes Windows give the window
REM Career Radar's own taskbar icon — plain `msedge --app=URL` does not, it
REM just opens a popup inside Edge's existing process and inherits Edge's
REM icon (confirmed live, EATP-023). Overridable via the environment in case
REM the app is ever reinstalled and Windows assigns a new AUMID.
if "%CAREER_RADAR_APP_AUMID%"=="" set CAREER_RADAR_APP_AUMID=127.0.0.1-4FF64651_pfncv7bjx4w4g!App

REM Wait for the server to actually accept connections before opening the
REM window — a fixed sleep would either race a slow start or waste time on a
REM fast one. Runs in the background so uvicorn itself can hold the
REM foreground and keep this script (and the hidden console) alive.
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -Uri '%CR_URL%' -UseBasicParsing -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }; Start-Process explorer.exe 'shell:AppsFolder\%CAREER_RADAR_APP_AUMID%'"

.venv\Scripts\python.exe -m uvicorn career_radar.web.server:app --host 127.0.0.1 --port %CAREER_RADAR_PORT% --log-level warning
