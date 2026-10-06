# SMOKE — 1 VU / 30s. Validate correlation and chaining before any real load.
# Uses real_logins.csv by default. Not a graded level.
param([string]$BaseUrl = "", [string]$CsvFile = "data/real_logins.csv")
. "$PSScriptRoot\_common.ps1"
Invoke-JmeterRun -Level smoke -Threads 1 -LoginThreads 1 -RampUp 1 -Duration 30 -CsvFile $CsvFile -BaseUrl $BaseUrl
