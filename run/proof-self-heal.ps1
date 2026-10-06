# CONCEPT 17 — proof run: Multi-Layer Self-Healing Agent
#
# Simulates the API renaming its token field by pointing the JSON Extractor at a
# path that does not exist. The extractor returns NOT_FOUND, the self-healing
# agent kicks in with its 4-layer strategy:
#
#   Layer 1 — Alias map (11+ known field names)
#   Layer 2 — JWT structure detection (header.payload.signature)
#   Layer 3 — Heuristic (token-ish keys with long values)
#   Layer 4 — Optional LLM fallback
#
# AGENT FEATURES DEMONSTRATED:
#   - Circuit breaker: after 3 consecutive heals, caches the field mapping
#   - Correlation guardian: heals ALL extractors, not just authToken
#   - Healing statistics: aggregated summary at run end
#   - Response fingerprinting: detects API structure changes
#
# Evidence produced:
#   results/self-heal-local.log          — per-event healing log
#   results/correlation-guardian-local.jsonl — structured correlation heals
#   results/self-heal-summary.json       — aggregated statistics
#
# Run the normal smoke FIRST so you have a passing baseline to compare against.

param([string]$BaseUrl = "")
. "$PSScriptRoot\_common.ps1"

# Archive previous logs
@("self-heal-local.log", "correlation-guardian-local.jsonl", "self-heal-summary.json") | ForEach-Object {
    $f = Join-Path $RepoRoot "results\$_"
    if (Test-Path $f) {
        Move-Item $f "$f.bak" -Force
        Write-Host "Archived previous $_ to $_.bak"
    }
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Self-Healing Agent — Proof Run" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Simulating: token_json_path = `$.sessionToken_renamed_by_api" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Expected behavior:" -ForegroundColor Yellow
Write-Host "    1. JSON Extractor returns NOT_FOUND" -ForegroundColor Yellow
Write-Host "    2. Self-heal agent Layer 1 scans aliases" -ForegroundColor Yellow
Write-Host "    3. If alias misses, Layer 2 detects JWT structure" -ForegroundColor Yellow
Write-Host "    4. Circuit breaker caches the mapping after 3 heals" -ForegroundColor Yellow
Write-Host "    5. Correlation guardian monitors all other variables" -ForegroundColor Yellow
Write-Host "    6. Statistics reporter summarizes at teardown" -ForegroundColor Yellow
Write-Host ""

Invoke-JmeterRun -Level smoke -Threads 1 -RampUp 1 -Duration 60 -BaseUrl $BaseUrl `
    -Extra @('-Jtoken_json_path=$.sessionToken_renamed_by_api')

# Post-run: display healing evidence
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Self-Healing Evidence" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

$healLog = Join-Path $RepoRoot "results\self-heal-local.log"
if (Test-Path $healLog) {
    Write-Host ""
    Write-Host "--- Healing Log ---" -ForegroundColor Green
    Get-Content $healLog | ForEach-Object { Write-Host "  $_" }
}

$guardianLog = Join-Path $RepoRoot "results\correlation-guardian-local.jsonl"
if (Test-Path $guardianLog) {
    Write-Host ""
    Write-Host "--- Correlation Guardian Log ---" -ForegroundColor Green
    Get-Content $guardianLog | ForEach-Object { Write-Host "  $_" }
}

$summaryFile = Join-Path $RepoRoot "results\self-heal-summary.json"
if (Test-Path $summaryFile) {
    Write-Host ""
    Write-Host "--- Aggregated Summary ---" -ForegroundColor Green
    Get-Content $summaryFile | ForEach-Object { Write-Host "  $_" }
}

Write-Host ""
