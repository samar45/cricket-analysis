# Runs `cricket cricbuzz sync` and appends all output to data\external\cricbuzz\sync_run.log (used by the scheduled task).
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$log = Join-Path $repo "data\external\cricbuzz\sync_run.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
"=== $(Get-Date -Format s) start ===" | Out-File -Append -Encoding utf8 $log
& "$repo\.venv\Scripts\cricket.exe" cricbuzz sync *>&1 | Out-File -Append -Encoding utf8 $log
$code = $LASTEXITCODE
"=== $(Get-Date -Format s) exit $code ===" | Out-File -Append -Encoding utf8 $log
exit $code
