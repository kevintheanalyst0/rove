' Career Radar — launches the server with no visible console window
' (EATP-023, Kevin's call: feel like a real product, not a local script).
' The server shuts itself down on its own once you close the browser tab
' (see server.py's tab-close watcher) — there's no window to close anymore.
Set objShell = CreateObject("WScript.Shell")
objShell.Run "wsl.exe -d Ubuntu-24.04 -- bash -lc ""/home/kevin/Projects/career-radar/scripts/run_web.sh""", 0, False
