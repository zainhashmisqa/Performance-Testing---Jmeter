# LEVEL 3 (MAX) — 50 GET VUs / 1 login / 120s ramp / 15 min hold
# Login: 1 thread, 1 iteration (single account, token pooled to all VUs)
# GET calls: 50 VUs hitting my-courses, certificates, profile
param([string]$BaseUrl = "", [string]$CsvFile = "data/real_logins.csv")
. "$PSScriptRoot\_common.ps1"
Invoke-JmeterRun -Level max -Threads 50 -LoginThreads 1 -RampUp 120 -Duration 900 -CsvFile $CsvFile -BaseUrl $BaseUrl
