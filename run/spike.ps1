# LEVEL 3 (SPIKE) — 50 VUs released as a coordinated burst
#
# CONCEPT 13 — this is the run that makes the Synchronizing Timer do real work.
# The timer is enabled in the plan but its groupSize is property-driven, so it is
# a no-op at the default of 1. Here we set it to the full thread count: every VU
# blocks at the timer until all 50 have arrived, then they are released in the
# same instant. That is a true spike — a step function in arrival rate — rather
# than a fast ramp, which is what a plain short ramp-up actually produces.
#
# RampUp is deliberately short (10s) so the threads reach the barrier together.
# sync_timeout is the safety valve: if fewer than groupSize threads ever arrive
# (a worker died, a login failed) the waiting threads are released after the
# timeout instead of hanging the run.

param(
    [string]$BaseUrl  = "",
    [string]$CsvFile  = "data/real_logins.csv",
    [int]   $Threads  = 50,
    [int]   $RampUp   = 10,
    [int]   $Duration = 900
)
. "$PSScriptRoot\_common.ps1"

Write-Host ""
Write-Host "  SPIKE PROFILE" -ForegroundColor Cyan
Write-Host "  Threads        : $Threads"
Write-Host "  Ramp           : ${RampUp}s (short, so threads reach the barrier together)"
Write-Host "  Sync group     : $Threads  (all VUs released in one burst)"
Write-Host "  Sync timeout   : 10000ms (safety valve, prevents a deadlock)"
Write-Host ""

Invoke-JmeterRun -Level max -Threads $Threads -LoginThreads 1 -RampUp $RampUp `
    -Duration $Duration -CsvFile $CsvFile -BaseUrl $BaseUrl `
    -Extra @("-Jsync_group_size=$Threads", "-Jsync_timeout=10000")
