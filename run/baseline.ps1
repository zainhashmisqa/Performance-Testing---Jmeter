# LEVEL 1 (BASELINE) — 30 GET VUs / 1 login / 60s ramp / 10 min hold
# Login: 1 thread, 1 iteration (single account, token pooled to all VUs)
# GET calls: 30 VUs hitting my-courses, certificates, profile
param([string]$BaseUrl = "", [string]$CsvFile = "data/real_logins.csv")
. "$PSScriptRoot\_common.ps1"
Invoke-JmeterRun -Level baseline -Threads 30 -LoginThreads 1 -RampUp 60 -Duration 600 -CsvFile $CsvFile -BaseUrl $BaseUrl
