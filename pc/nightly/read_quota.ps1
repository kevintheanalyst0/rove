# Reads Claude usage the way Pulse does (EATP-037). Free: spends no tokens, never
# refreshes the login, never prints the token. Prints ONE line of JSON.
$ErrorActionPreference = 'Stop'
try {
  $cred  = Get-Content "$env:USERPROFILE\.claude\.credentials.json" -Raw | ConvertFrom-Json
  $token = $cred.claudeAiOauth.accessToken
  $r = Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 15
  @{ ok = $true
     session = [math]::Round([double]$r.five_hour.utilization, 1)
     weekly  = [math]::Round([double]$r.seven_day.utilization, 1)
     session_resets_at = [string]$r.five_hour.resets_at
     weekly_resets_at  = [string]$r.seven_day.resets_at } | ConvertTo-Json -Compress
} catch {
  $resp = $_.Exception.Response
  $status = 0; $retry = 0
  if ($resp) { $status = [int]$resp.StatusCode; [void][int]::TryParse([string]$resp.Headers["Retry-After"], [ref]$retry) }
  @{ ok = $false; error = $_.Exception.GetType().Name; status = $status; retry_after = $retry } | ConvertTo-Json -Compress
}
