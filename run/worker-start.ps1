# CONCEPT 7 (deck 12) - Distributed Load: WORKER node launcher.
#
# Run this on EACH worker machine, from the repo root, before starting the
# controller. Every worker must have:
#   - the same JMeter version as the controller (RMI is version-sensitive)
#   - the same Java major version
#   - a copy of this repo at the same relative layout (scripts/groovy, data/)
#   - the JDBC driver jar in <jmeter>/lib/ (if Concept 11 is enabled)
#
# PRO-LEVEL FEATURES:
#   - JVM heap tuning (-Xms/-Xmx) for high-thread stability
#   - Fixed RMI ports (no dynamic ephemeral ports = deterministic firewalls)
#   - NTP clock sync verification (timestamps must be comparable across nodes)
#   - Worker resource baseline capture (CPU/RAM before test starts)
#   - CSV data isolation (disjoint slices, no data collision)
#
# WHY -Jcsvfile IS SET HERE AND NOT ON THE CONTROLLER:
# The controller's -G flag broadcasts ONE value to ALL workers, so it cannot
# give each worker a different CSV slice. Test-data partitioning must therefore
# be a local property on each worker. Run scripts/partition_csv.py first and
# give each worker its own -WorkerIndex.
#
# Usage on worker 1:   .\run\worker-start.ps1 -WorkerIndex 1 -HostIp 10.0.0.11
# Usage on worker 2:   .\run\worker-start.ps1 -WorkerIndex 2 -HostIp 10.0.0.12

param(
    [Parameter(Mandatory)] [int]    $WorkerIndex,
    [Parameter(Mandatory)] [string] $HostIp,
    [int]    $RmiPort   = 1099,
    [string] $HeapSize  = "1g",
    [switch] $SkipChecks
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  JMeter Worker $WorkerIndex — $HostIp :$RmiPort" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# PRE-FLIGHT CHECKS: the things that silently ruin a distributed run
# ---------------------------------------------------------------------------
if (-not $SkipChecks) {

    # 1. JMeter binary
    $jm = Get-Command jmeter-server -ErrorAction SilentlyContinue
    if (-not $jm) {
        Write-Host "FAIL: jmeter-server is not on PATH." -ForegroundColor Red
        exit 1
    }
    $jmeterVersion = & jmeter --version 2>&1 | Select-String -Pattern "\d+\.\d+\.\d+" | ForEach-Object { $_.Matches[0].Value }
    Write-Host "  JMeter version : $jmeterVersion"

    # 2. Java version
    $javaVer = & java -version 2>&1 | Select-String -Pattern "\d+\.\d+" | ForEach-Object { $_.Matches[0].Value }
    Write-Host "  Java version   : $javaVer"

    # 3. CSV data slice (disjoint accounts)
    $csv = "data\logins_w$WorkerIndex.csv"
    if (-not (Test-Path $csv)) {
        Write-Host "FAIL: Missing $csv" -ForegroundColor Red
        Write-Host "Run on the controller, then copy the repo to this worker:" -ForegroundColor Yellow
        Write-Host "    python scripts\partition_csv.py --workers <N>"
        exit 1
    }
    $accounts = (Get-Content $csv).Count - 1
    Write-Host "  Data slice     : $csv ($accounts accounts, disjoint from other workers)"

    # 4. Groovy scripts present (JSR223 file refs resolve locally on each worker)
    $missing = @()
    foreach ($g in @("self_heal_token","signature_preprocessor","retry_postprocessor",
                     "retry_reset_preprocessor","jdbc_assertion",
                     "token_pool_publish","token_pool_bind",
                     "server_metrics","teardown_cleanup")) {
        if (-not (Test-Path "scripts\groovy\$g.groovy")) { $missing += $g }
    }
    if ($missing.Count -gt 0) {
        Write-Host "FAIL: Missing Groovy scripts: $($missing -join ', ')" -ForegroundColor Red
        Write-Host "Copy the whole repo to each worker." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  Groovy scripts : all present"

    # 5. JDBC driver (optional)
    if ($env:JMETER_HOME) {
        $drivers = Get-ChildItem "$env:JMETER_HOME\lib\*.jar" -ErrorAction SilentlyContinue |
                   Where-Object { $_.Name -match 'mysql|mssql|postgres' }
        if ($drivers) {
            Write-Host "  JDBC driver    : $($drivers[0].Name)"
        } else {
            Write-Host "  JDBC driver    : not found (Concept 11 will be skipped)" -ForegroundColor Yellow
        }
    }

    # 6. NTP / Clock sync check — timestamps must be comparable across nodes
    Write-Host ""
    Write-Host "  Clock sync check..." -NoNewline
    try {
        $w32time = Get-Service w32time -ErrorAction SilentlyContinue
        if ($w32time -and $w32time.Status -eq "Running") {
            Write-Host " NTP service running" -ForegroundColor Green
        } else {
            Write-Host " WARNING: Windows Time service not running" -ForegroundColor Yellow
            Write-Host "  Timestamps in the merged JTL may be offset from other workers." -ForegroundColor Yellow
            Write-Host "  Fix: net start w32time && w32tm /resync" -ForegroundColor Yellow
        }
    } catch {
        Write-Host " could not check (non-fatal)" -ForegroundColor Yellow
    }

    # 7. Worker resource baseline — capture before test so we know headroom
    Write-Host ""
    Write-Host "--- Worker Resource Baseline ---" -ForegroundColor Cyan
    $cpuCores = (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors
    $totalRamGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    $freeRamGB  = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
    Write-Host "  CPU cores      : $cpuCores"
    Write-Host "  Total RAM      : ${totalRamGB} GB"
    Write-Host "  Free RAM       : ${freeRamGB} GB"
    Write-Host "  JVM Heap       : $HeapSize (override with -HeapSize 2g)"

    if ($freeRamGB -lt 2) {
        Write-Host "  WARNING: Less than 2 GB free. Worker may OOM under 100+ threads." -ForegroundColor Yellow
    }

    # 8. Port availability
    $portInUse = Get-NetTCPConnection -LocalPort $RmiPort -ErrorAction SilentlyContinue
    if ($portInUse) {
        Write-Host "  FAIL: Port $RmiPort already in use!" -ForegroundColor Red
        Write-Host "  Kill the existing process or use -RmiPort <other>" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  RMI port       : $RmiPort (available)"
}

Write-Host ""
Write-Host "Starting jmeter-server. Leave this window open." -ForegroundColor Green
Write-Host "Start the controller next with:" -ForegroundColor Green
Write-Host "  .\run\distributed.ps1 -Workers ${HostIp}:${RmiPort},<other-worker>" -ForegroundColor White
Write-Host ""

# --- JVM TUNING (PRO) -------------------------------------------------------
# -Xms/-Xmx: fixed heap avoids GC pauses from dynamic resizing under load.
# -XX:+UseG1GC: low-pause GC, better than CMS for high-thread JMeter.
# -XX:MaxMetaspaceSize: Groovy compiles classes at runtime; cap prevents leak.
# -Djava.net.preferIPv4Stack: RMI on dual-stack hosts sometimes binds to IPv6
#   and the controller can't reach it. Force IPv4.
$env:JVM_ARGS = "-Xms$HeapSize -Xmx$HeapSize -XX:+UseG1GC -XX:MaxMetaspaceSize=256m -Djava.net.preferIPv4Stack=true"

# VERIFIED THE HARD WAY: -Dserver.rmi.ssl.disable=true does NOT work. JMeter
# reads this as a JMeter property, not a JVM system property, so the worker
# still exports its RMI stub with an SSL socket factory and the controller dies
# with "FileNotFoundException: rmi_keystore.jks". Loading it as a properties
# overlay with -q is what actually works.
& jmeter-server `
    -q config/rmi-nossl.properties `
    -Dserver_port=$RmiPort `
    -Djava.rmi.server.hostname=$HostIp `
    -Jcsvfile="data/logins_w$WorkerIndex.csv" `
    -Jworker_id="w$WorkerIndex"
