@echo off
title Career Radar - Probar Indeed
echo Corriendo solo el collector de Indeed (sin IA, sin las demas fuentes).
echo Esto no gasta cuota de IA y no corre el pipeline completo.
echo.
wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /home/kevin/Projects/career-radar && .venv/bin/python scripts/test_indeed_live.py"
echo.
pause
