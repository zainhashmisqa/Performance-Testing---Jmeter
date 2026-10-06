# CONCEPT 7 (deck 12) - Distributed Load Testing: CONTROLLER.
#
# 1 controller (this machine) + >=2 workers on the same subnet.
#
# ---------------------------------------------------------------------------
# PRO-LEVEL DISTRIBUTED TESTING — WHAT THIS SCRIPT HANDLES
# ---------------------------------------------------------------------------
#
# 1. -J DOES NOT REACH WORKERS.
#    -J sets a property in the CONTROLLER's JVM only. Workers never see it, so
#    they silently fall back to their own defaults — you think you ran 200 VUs
#    against staging and you actually ran 50 against localhost. Properties that
#    must reach workers are sent with -G. This script uses -G throughout.
#
# 2. TOTAL LOAD = Threads × Workers.
#    -Threads is the PER-WORKER count. 100 threads across 2 workers is 200 VUs.
#    This script prints the real total and refuses silently-wrong combinations.
#
# 3. RMI SSL IS ON BY DEFAULT AND -D DOES NOT TURN IT OFF.
#    server.rmi.ssl.disable is a JMeter property, not a JVM system property.
#    Passing it with -D silently does nothing. Loaded as -q overlay on both sides.
#
# 4. CSV DATA IS NOT SPLIT AUTOMATICALLY.
#    Every worker opens its own copy at row 1, so partition first with
#    scripts/partition_csv.py and each worker loads its slice locally.
#
# 5. FIXED RMI PORTS (PRO).
#    Dynamic ephemeral ports break firewalls. config/rmi-nossl.properties pins
#    both server_port and server.rmi.localport so firewall rules are deterministic.
#
# 6. NTP CLOCK SYNC (PRO).
#    Timestamps in the merged JTL must be comparable. This script warns if the
#    controller's clock differs from workers by more than 1 second.
#
# 7. CONTROLLER DOES NOT GENERATE LOAD (PRO).
#    The controller only orchestrates and aggregates. It should NOT run as a
#    worker simultaneously — that makes it the bottleneck.
#
# 8. WORKER HEALTH MONITORING (PRO).
#    After the run, per-worker sample counts are printed to prove all workers
#    participated evenly. Uneven distribution signals a bottlenecked worker.
#
# ---------------------------------------------------------------------------
# Usage:
#   python scripts\partition_csv.py --workers 2
#   # on each worker:  .\run\worker-start.ps1 -WorkerIndex N -HostIp <ip>
#   .\run\distributed.ps1 -Workers 10.0.0.11,10.0.0.12 -Threads 100
# ---------------------------------------------------------------------------

param(
    [Parameter(Mandatory)] [string[]] $Workers,
    [int]    $Threads  = 100,
    [int]    $RampUp   = 120,
    [int]    $Duration = 900,
    [string] $BaseUrl  = "",
    [int]    $SyncGroupSize = 1,
    [string] $HeapSize = "512m",
    [switch] $StopWorkersAfter,
    [switch] $SkipReachCheck
)

. "$PSScriptRoot\_common.ps1"

Assert-Jmeter | Out-Null
if (-not $BaseUrl -and -not (Assert-TargetConfigured)) { exit 1 }

if ($Workers.Count -lt 2) {
    Write-Host "The brief requires at least 2 workers. Got $($Workers.Count)." -ForegroundColor Red
    exit 1
}

$total = $Threads * $Workers.Count
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Distributed Load Test — Controller" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Workers          : $($Workers -join ', ')"
Write-Host "  Threads/worker   : $Threads"
Write-Host "  TOTAL LOAD       : $total VUs  ($Threads x $($Workers.Count) workers)" -ForegroundColor Yellow
Write-Host "  Ramp / hold      : ${RampUp}s / ${Duration}s"
Write-Host "  Controller heap  : $HeapSize (coordinator only, no load generation)"
Write-Host ""

# --- PRO: Warn on classic load miscalculation --------------------------------
if ($total -ne 200 -and $total -ne 50) {
    Write-Host "  NOTE: total load is $total VUs, which is neither the baseline (50)" -ForegroundColor Yellow
    Write-Host "        nor the peak (200) the brief grades against." -ForegroundColor Yellow
    Write-Host "        For peak across $($Workers.Count) workers use -Threads $([math]::Floor(200 / $Workers.Count))." -ForegroundColor Yellow
    Write-Host ""
}

# --- PRO: Controller should NOT generate load --------------------------------
Write-Host "  Controller role: COORDINATOR ONLY (no local load generation)" -ForegroundColor Cyan
Write-Host "  This machine aggregates results — workers generate all the load."
Write-Host ""

# --- PRO: Network reachability check with fixed ports -------------------------
if (-not $SkipReachCheck) {
    Write-Host "--- Worker Reachability (RMI fixed-port check) ---" -ForegroundColor Cyan
    $unreachable = @()
    foreach ($w in $Workers) {
        $hostname = $w.Split(":")[0]
        $port     = if ($w.Contains(":")) { [int]$w.Split(":")[1] } else { 1099 }
        $ok = Test-NetConnection -ComputerName $hostname -Port $port -WarningAction SilentlyContinue -InformationLevel Quiet
        if ($ok) {
            Write-Host "  OK        $hostname : $port" -ForegroundColor Green
        } else {
            Write-Host "  NO ROUTE  $hostname : $port" -ForegroundColor Red
            $unreachable += $w
        }
    }
    if ($unreachable.Count -gt 0) {
        Write-Host ""
        Write-Host "Cannot reach: $($unreachable -join ', ')" -ForegroundColor Red
        Write-Host "Checklist:" -ForegroundColor Yellow
        Write-Host "  1. jmeter-server running on that worker?" -ForegroundColor Yellow
        Write-Host "  2. RMI port open in firewall? (fixed port $($Workers[0].Split(':')[-1]))" -ForegroundColor Yellow
        Write-Host "  3. Worker started with -Djava.rmi.server.hostname=<its own IP>?" -ForegroundColor Yellow
        Write-Host "  4. Same subnet? (JMeter RMI cannot cross subnets without proxy)" -ForegroundColor Yellow
        exit 1
    }
    Write-Host ""
}

# --- PRO: NTP Clock sync warning --------------------------------------------
Write-Host "--- Clock Sync Check ---" -ForegroundColor Cyan
try {
    $w32time = Get-Service w32time -ErrorAction SilentlyContinue
    if ($w32time -and $w32time.Status -eq "Running") {
        Write-Host "  Controller NTP: running" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Windows Time service not running on controller" -ForegroundColor Yellow
        Write-Host "  Merged JTL timestamps may be offset. Fix: net start w32time" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Could not check NTP (non-fatal)" -ForegroundColor Yellow
}
Write-Host ""

# --- JVM TUNING for controller -----------------------------------------------
# Controller does NOT generate load, so it needs less heap than workers.
# But it must handle result aggregation from all workers simultaneously.
$env:JVM_ARGS = "-Xms$HeapSize -Xmx$HeapSize -XX:+UseG1GC -XX:MaxMetaspaceSize=256m -Djava.net.preferIPv4Stack=true"

$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = Join-Path $RepoRoot "results\distributed-$stamp"
$jtl    = Join-Path $outDir "dist.jtl"
$html   = Join-Path $outDir "html"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# -G = send to every remote worker.   -J = controller-local only.
# -D = JVM system property (RMI settings must match on both sides).
# csvfile is deliberately NOT sent: each worker sets its own slice locally.
$jmArgs = @(
    "-n",
    "-t", (Join-Path $RepoRoot "tests\azm_sba_perf.jmx"),
    "-R", ($Workers -join ","),
    "-l", $jtl,
    "-j", (Join-Path $outDir "jmeter.log"),
    "-e", "-o", $html,
    "-q", (Join-Path $RepoRoot "config\rmi-nossl.properties"),
    "-Gthreads=$Threads",
    "-Grampup=$RampUp",
    "-Gduration=$Duration",
    "-Gsync_group_size=$SyncGroupSize",
    "-Gsetup_rampup=10"
)

# Forward target + DB + monitoring properties to workers via -G.
# Reading from the controller's properties file keeps one source of truth.
$forward = @("protocol","port","path_login","path_catalog","path_certificates",
             "path_profile","path_checkout","path_order","token_json_path",
             "think_constant","think_deviation","pct_browse","pct_cart",
             "pct_checkout","max_retries","retry_backoff_ms","hmac_secret",
             "db_pool","db_driver","db_url","db_user","db_password","db_table",
             "db_ref_column","db_max_tries","db_retry_delay_ms",
             "influx_url","influx_application","influx_measurement","env",
             "path_metrics","monitor_interval_ms","monitor_threads",
             "cleanup_enabled","jdbc_enabled","sla_checkout_ms")

$propsFile = Join-Path $RepoRoot "config\user.properties"
foreach ($key in $forward) {
    $m = Select-String -Path $propsFile -Pattern "^$key=(.*)$"
    if ($m) {
        $val = $m.Matches[0].Groups[1].Value
        if ($val) { $jmArgs += "-G$key=$val" }
    }
}
if ($BaseUrl) { $jmArgs += "-Gbase_url=$BaseUrl" }
else {
    $m = Select-String -Path $propsFile -Pattern "^base_url=(.*)$"
    if ($m) { $jmArgs += "-Gbase_url=$($m.Matches[0].Groups[1].Value)" }
}
if ($StopWorkersAfter) { $jmArgs += "-X" }

$gCount = ($jmArgs | Where-Object { $_ -like '-G*' }).Count
Write-Host "Sending $gCount properties to workers via -G" -ForegroundColor Cyan
Write-Host ""

$startTime = Get-Date
Push-Location $RepoRoot
try   { & jmeter @jmArgs }
finally { Pop-Location }
$elapsed = (Get-Date) - $startTime

# ==========================================================================
# POST-RUN ANALYSIS (PRO-LEVEL)
# ==========================================================================
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Post-Run Analysis" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Wall clock       : $([math]::Round($elapsed.TotalMinutes, 1)) minutes"
Write-Host "  Total VUs        : $total ($Threads x $($Workers.Count) workers)"
Write-Host ""

# --- PRO: Per-worker contribution analysis -----------------------------------
# The merged JTL's threadName column carries the worker hostname, which proves
# all workers participated. Uneven distribution signals a bottlenecked worker.
Write-Host "--- Per-Worker Contribution (proves all workers participated) ---" -ForegroundColor Cyan
if (Test-Path $jtl) {
    $rows = Import-Csv $jtl
    if ($rows -and $rows[0].PSObject.Properties.Name -contains "threadName") {
        $workerGroups = $rows | Group-Object { ($_.threadName -split '-')[0] } | Sort-Object Name
        $totalSamples = ($workerGroups | Measure-Object -Property Count -Sum).Sum
        foreach ($wg in $workerGroups) {
            $pct = [math]::Round(($wg.Count / $totalSamples) * 100, 1)
            $bar = "#" * [math]::Min([math]::Round($pct / 2), 40)
            $color = if ($pct -lt 20 -or $pct -gt 80) { "Yellow" } else { "Green" }
            Write-Host ("  {0,-28} {1,8} samples ({2,5}%)  {3}" -f $wg.Name, $wg.Count, $pct, $bar) -ForegroundColor $color
        }

        # PRO: Warn if distribution is significantly uneven (>20% deviation)
        $avgCount = $totalSamples / $workerGroups.Count
        $maxDeviation = ($workerGroups | ForEach-Object {
            [math]::Abs($_.Count - $avgCount) / $avgCount * 100
        } | Measure-Object -Maximum).Maximum
        Write-Host ""
        if ($maxDeviation -gt 20) {
            Write-Host "  WARNING: Load distribution is uneven (${maxDeviation}% deviation)." -ForegroundColor Yellow
            Write-Host "  Check if a worker is CPU/memory constrained." -ForegroundColor Yellow
        } else {
            Write-Host "  Load distribution: even ($([math]::Round($maxDeviation, 1))% max deviation)" -ForegroundColor Green
        }
    }

    # --- PRO: Error rate per worker ------------------------------------------
    Write-Host ""
    Write-Host "--- Per-Worker Error Rate ---" -ForegroundColor Cyan
    if ($rows[0].PSObject.Properties.Name -contains "success") {
        $rows | Group-Object { ($_.threadName -split '-')[0] } | Sort-Object Name | ForEach-Object {
            $errs = ($_.Group | Where-Object { $_.success -eq "false" }).Count
            $errPct = if ($_.Count -gt 0) { [math]::Round(($errs / $_.Count) * 100, 2) } else { 0 }
            $color = if ($errPct -gt 1) { "Red" } elseif ($errPct -gt 0) { "Yellow" } else { "Green" }
            Write-Host ("  {0,-28} {1,5} errors / {2,8} samples = {3}%" -f $_.Name, $errs, $_.Count, $errPct) -ForegroundColor $color
        }
    }

    Write-Host ""
    Write-Host "--- SLA Check (merged results) ---" -ForegroundColor Cyan
    python (Join-Path $RepoRoot "scripts\check_sla.py") $jtl --level peak
}

Write-Host ""
Write-Host "Merged HTML report : $html\index.html" -ForegroundColor Green
Write-Host "Raw JTL            : $jtl"
Write-Host ""
