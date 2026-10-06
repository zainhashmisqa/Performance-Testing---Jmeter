# Shared helper for all run scripts.
# Dot-sourced by baseline.ps1 / peak.ps1 / spike.ps1 / smoke.ps1 / distributed.ps1
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 files as
# ANSI unless they carry a UTF-8 BOM, and non-ASCII punctuation silently breaks
# string parsing.

$ErrorActionPreference = "Stop"

# Repo root = parent of run/
$script:RepoRoot = Split-Path -Parent $PSScriptRoot

function Assert-Jmeter {
    $cmd = Get-Command jmeter -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "jmeter is not on PATH." -ForegroundColor Red
        Write-Host "Install Apache JMeter 5.6.3, add its bin folder to PATH, then re-run."
        exit 1
    }
    return $cmd.Source
}

function Assert-TargetConfigured {
    $props = Join-Path $RepoRoot "config\user.properties"
    $match = Select-String -Path $props -Pattern '^base_url=(.*)$'
    $base  = if ($match) { $match.Matches[0].Groups[1].Value } else { "" }

    if ($base -match 'fill-me-in|FILL_ME_IN|example') {
        Write-Host ""
        Write-Host "  STOP - base_url is still a placeholder ($base)." -ForegroundColor Yellow
        Write-Host "  Work through config\endpoints.md with your lead first:" -ForegroundColor Yellow
        Write-Host "    - confirmed sandbox base URL and endpoint paths"
        Write-Host "    - real staging test accounts in data\logins.csv"
        Write-Host "    - written confirmation the test DB holds synthetic data"
        Write-Host "    - authorization to run this load level against the sandbox"
        Write-Host ""
        Write-Host "  Override for a one-off with the -BaseUrl parameter." -ForegroundColor Yellow
        return $false
    }
    return $true
}

function Invoke-JmeterRun {
    param(
        [Parameter(Mandatory)] [string]   $Level,
        [Parameter(Mandatory)] [int]      $Threads,
        [Parameter(Mandatory)] [int]      $RampUp,
        [Parameter(Mandatory)] [int]      $Duration,
        [int]      $LoginThreads  = 1,
        [int]      $SyncGroupSize = 1,
        [string]   $CsvFile = "",
        [string]   $BaseUrl = "",
        [string[]] $Extra = @()
    )

    Assert-Jmeter | Out-Null
    if (-not $BaseUrl) {
        if (-not (Assert-TargetConfigured)) { exit 1 }
    }

    $stamp   = Get-Date -Format "yyyyMMdd-HHmmss"
    $outDir  = Join-Path $RepoRoot "results\$Level-$stamp"
    $jtl     = Join-Path $outDir "$Level.jtl"
    $html    = Join-Path $outDir "html"
    $logFile = Join-Path $outDir "jmeter.log"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    # Do not name this $args - that is a reserved automatic variable.
    $jmArgs = @(
        "-n",
        "-t", (Join-Path $RepoRoot "tests\azm_sba_perf.jmx"),
        "-q", (Join-Path $RepoRoot "config\user.properties"),
        "-l", $jtl,
        "-j", $logFile,
        "-e", "-o", $html,
        "-Jthreads=$Threads",
        "-Jlogin_threads=$LoginThreads",
        "-Jrampup=$RampUp",
        "-Jduration=$Duration",
        "-Jsync_group_size=$SyncGroupSize"
    )
    if ($CsvFile) { $jmArgs += "-Jcsvfile=$CsvFile" }
    if ($BaseUrl) { $jmArgs += "-Jbase_url=$BaseUrl" }
    $jmArgs += $Extra

    Write-Host ""
    Write-Host "=== $Level : $Threads VUs / $RampUp s ramp / $Duration s hold ===" -ForegroundColor Cyan
    Write-Host "Output: $outDir"
    Write-Host ""

    # Run from the repo root so the relative paths inside the .jmx
    # (data/logins.csv, scripts/groovy/*.groovy) resolve correctly.
    Push-Location $RepoRoot
    try   { & jmeter @jmArgs }
    finally { Pop-Location }

    Write-Host ""
    Write-Host "--- SLA check ---" -ForegroundColor Cyan
    python (Join-Path $RepoRoot "scripts\check_sla.py") $jtl --level $Level
    $slaExit = $LASTEXITCODE

    Write-Host ""
    Write-Host "HTML report: $html\index.html"
    $healLog = Join-Path $RepoRoot "results\self-heal.log"
    if (Test-Path $healLog) {
        Write-Host "Self-heal events logged: $healLog" -ForegroundColor Yellow
    }
    exit $slaExit
}
