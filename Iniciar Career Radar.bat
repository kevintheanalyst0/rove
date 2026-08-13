@echo off
title Career Radar
echo Iniciando Career Radar...
echo Se va a abrir tu navegador en unos segundos.
echo.
echo Para APAGAR el servidor, cerra esta ventana (o Ctrl+C aca adentro).
echo.
wsl.exe -d Ubuntu-24.04 -- bash -lc "/home/kevin/Projects/career-radar/scripts/run_web.sh"
echo.
echo El servidor se detuvo.
pause
