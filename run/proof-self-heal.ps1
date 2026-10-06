# CONCEPT 17 — proof run.
#
# Simulates the API renaming its token field by pointing the JSON Extractor at a
# path that does not exist. The extractor returns NOT_FOUND, the self-healing
# JSR223 PostProcessor kicks in, finds the real token under a known alias, and
# the run continues green.
#
# This produces results/self-heal.log — the evidence to screenshot for the report.
#
# Run the normal smoke FIRST so you have a passing baseline to compare against.

param([string]$BaseUrl = "")
. "$PSScriptRoot\_common.ps1"

$healLog = Join-Path $RepoRoot "results\self-heal.log"
if (Test-Path $healLog) {
    Move-Item $healLog "$healLog.bak" -Force
    Write-Host "Archived previous self-heal log to self-heal.log.bak"
}

Write-Host ""
Write-Host "Simulating field rename: token_json_path = `$.sessionToken_renamed_by_api" -ForegroundColor Yellow
Write-Host "Expect: extractor returns NOT_FOUND -> self-heal recovers the token -> run passes." -ForegroundColor Yellow

Invoke-JmeterRun -Level smoke -Threads 1 -RampUp 1 -Duration 60 -BaseUrl $BaseUrl `
    -Extra @('-Jtoken_json_path=$.sessionToken_renamed_by_api')

# Invoke-JmeterRun exits, so the summary below is printed by the wrapper in
# README instructions instead. To inspect manually:
#   Get-Content results\self-heal.log
