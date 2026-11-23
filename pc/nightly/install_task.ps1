# Registers (or replaces) the Windows task NocturnoRove for the current user (EATP-037).
# No administrator rights needed. Run from PowerShell:  .\install_task.ps1
# Remove it with:  Unregister-ScheduledTask -TaskName NocturnoRove -Confirm:$false
$xml = (Get-Content -Raw (Join-Path $PSScriptRoot 'NocturnoRove.task.xml')) -replace '__USUARIO__', "$env:USERDOMAIN\$env:USERNAME"
Register-ScheduledTask -TaskName 'NocturnoRove' -Xml $xml -Force | Out-Null
$t = Get-ScheduledTask -TaskName 'NocturnoRove'
$i = Get-ScheduledTaskInfo -TaskName 'NocturnoRove'
"estado=$($t.State) WakeToRun=$($t.Settings.WakeToRun) proxima=$($i.NextRunTime.ToString('yyyy-MM-dd HH:mm'))"
