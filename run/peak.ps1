# LEVEL 2 (PEAK) — 40 GET VUs / 1 login / 90s ramp / 15 min hold
# Login: 1 thread, 1 iteration (single account, token pooled to all VUs)
# GET calls: 40 VUs hitting my-courses, certificates, profile
param([string]$BaseUrl = "", [string]$CsvFile = "data/real_logins.csv")
. "$PSScriptRoot\_common.ps1"
Invoke-JmeterRun -Level peak -Threads 40 -LoginThreads 1 -RampUp 90 -Duration 900 -CsvFile $CsvFile -BaseUrl $BaseUrl
