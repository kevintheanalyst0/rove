@echo off
title Career Radar - Ejecutar busqueda
echo Arrancando una corrida completa de Career Radar...
echo Se va a abrir tu navegador mostrando el progreso en vivo.
echo.
echo Para APAGAR el servidor, cerra esta ventana (o Ctrl+C aca adentro).
echo.
wsl.exe -d Ubuntu-24.04 -- bash -lc "CAREER_RADAR_AUTOSTART=1 /home/kevin/Projects/career-radar/scripts/run_web.sh"
echo.
echo El servidor se detuvo.
pause
