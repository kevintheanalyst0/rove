' Rove — launches the server with no visible console window
' (EATP-023, Kevin's call: feel like a real product, not a local script).
' The server shuts itself down on its own once you close the browser tab
' (see server.py's tab-close watcher) — there's no window to close anymore.
'
' EATP-025: the project runs natively on Windows now. This used to hand off
' to `wsl.exe -d Ubuntu-24.04 -- bash -lc .../run_web.sh`; the WSL copy is
' kept only as a backup and is no longer what this launches. The path is
' derived from this file's own location, so moving the folder doesn't break it.
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.Run """" & scriptDir & "\scripts\run_web.bat""", 0, False
