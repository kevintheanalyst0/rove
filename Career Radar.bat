@echo off
title Career Radar
echo Arrancando Career Radar...
echo Se va a abrir tu navegador con la pantalla de inicio: iniciar busqueda,
echo limpiar cache o ver el dashboard de la ultima corrida.
echo.
echo Para APAGAR el servidor, cerra esta ventana (o Ctrl+C aca adentro).
echo.
wsl.exe -d Ubuntu-24.04 -- bash -lc "/home/kevin/Projects/career-radar/scripts/run_web.sh"
echo.
echo El servidor se detuvo.
pause
