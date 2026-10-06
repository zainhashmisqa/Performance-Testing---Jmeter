# CONCEPT 8 (deck 8) — JDBC Validation PROOF.
#
# Problem: we can't access SBA Academy's production database (and we shouldn't).
# Solution: H2 embedded database — pure Java, zero install, runs inside JMeter's
# JVM. Seeds it with realistic enrollment data, runs the test with jdbc_enabled=true,
# and the JDBC assertion either passes or fails on real SQL.
#
# This proves:
#   1. JDBCDataSource config works (pool creation, driver loading)
#   2. JDBCSampler executes a real SELECT COUNT(*) query
#   3. JSR223 assertion validates the result row exists
#   4. Async-safe retry loop handles eventual consistency
#
# Usage:
#   .\run\proof-jdbc.ps1
#
# Prerequisites:
#   - H2 JAR in <jmeter>/lib/  (this script downloads it if missing)

param(
    [string] $JmeterHome = ""
)

. "$PSScriptRoot\_common.ps1"

$jmeterBin = Assert-Jmeter
if (-not $JmeterHome) {
    $JmeterHome = Split-Path -Parent (Split-Path -Parent $jmeterBin)
}
$libDir = Join-Path $JmeterHome "lib"

# --- Step 1: Ensure H2 driver is in JMeter's lib/ ----------------------------
$h2Jar = Get-ChildItem "$libDir\h2-*.jar" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $h2Jar) {
    Write-Host "H2 driver not found in $libDir" -ForegroundColor Yellow
    Write-Host "Downloading H2 2.2.224 (1.8 MB)..." -ForegroundColor Cyan
    $h2Url = "https://repo1.maven.org/maven2/com/h2database/h2/2.2.224/h2-2.2.224.jar"
    $h2Dest = Join-Path $libDir "h2-2.2.224.jar"
    try {
        Invoke-WebRequest -Uri $h2Url -OutFile $h2Dest -UseBasicParsing
        Write-Host "  Downloaded: $h2Dest" -ForegroundColor Green
        Write-Host ""
        Write-Host "  IMPORTANT: Restart JMeter for the new JAR to load." -ForegroundColor Yellow
        Write-Host "  Then re-run this script." -ForegroundColor Yellow
        exit 0
    } catch {
        Write-Host "  Download failed: $_" -ForegroundColor Red
        Write-Host "  Manual download: $h2Url -> $libDir" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "H2 driver found: $($h2Jar.Name)" -ForegroundColor Green
}

# --- Step 2: Create + seed the H2 database -----------------------------------
# H2 in embedded mode creates the DB file automatically on first connect.
# We seed it via a Groovy setUp script that JMeter runs before the test.
$dbDir  = Join-Path $RepoRoot "results"
if (-not (Test-Path $dbDir)) { New-Item -ItemType Directory -Force $dbDir | Out-Null }
$dbPath = Join-Path $dbDir "proof-jdbc"

Write-Host ""
Write-Host "=== JDBC Validation Proof ===" -ForegroundColor Cyan
Write-Host "  H2 database    : $dbPath"
Write-Host "  JDBC URL       : jdbc:h2:file:$dbPath;AUTO_SERVER=TRUE"
Write-Host "  Table           : student_courseenrollment"
Write-Host ""

# Seed script: creates table + inserts realistic enrollment rows
$seedScript = @"
import groovy.sql.Sql

def url = 'jdbc:h2:file:${dbPath};AUTO_SERVER=TRUE'.replace('\\', '/')
def sql = Sql.newInstance(url, 'sa', '', 'org.h2.Driver')

sql.execute('''
    CREATE TABLE IF NOT EXISTS student_courseenrollment (
        id INT PRIMARY KEY,
        user_id INT,
        course_id INT,
        course_slug VARCHAR(100),
        status VARCHAR(20),
        enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

// Seed with realistic data matching the SBA API responses
def enrollments = [
    [63, 5, 76, 've', 'completed'],
    [62, 5, 75, 'test-course-01', 'completed'],
    [60, 5, 71, 'basel-iii', 'confirmed'],
    [59, 5, 69, 'compliance-basics', 'completed'],
    [58, 5, 68, 'risk-management', 'confirmed'],
    [55, 5, 56, 'aml-certification', 'completed'],
    [50, 5, 40, 'kyc-fundamentals', 'completed']
]

enrollments.each { e ->
    sql.execute('''
        MERGE INTO student_courseenrollment (id, user_id, course_id, course_slug, status)
        VALUES (?, ?, ?, ?, ?)
    ''', e)
}

log.info("JDBC PROOF: Seeded " + enrollments.size() + " enrollment rows into H2")
sql.close()
SampleResult.setIgnore()
"@

$seedFile = Join-Path $RepoRoot "scripts\groovy\jdbc_seed_h2.groovy"
Set-Content -Path $seedFile -Value $seedScript -Encoding utf8

# --- Step 3: Run the test with JDBC enabled against H2 -----------------------
$dbUrl = "jdbc:h2:file:${dbPath};AUTO_SERVER=TRUE".Replace('\', '/')

Write-Host "Running smoke test with JDBC validation enabled..." -ForegroundColor Cyan
Write-Host ""

Invoke-JmeterRun `
    -Level "proof-jdbc" `
    -Threads 1 `
    -LoginThreads 1 `
    -RampUp 1 `
    -Duration 30 `
    -CsvFile "data/real_logins.csv" `
    -Extra @(
        "-Jjdbc_enabled=true",
        "-Jdb_driver=org.h2.Driver",
        "-Jdb_url=$dbUrl",
        "-Jdb_user=sa",
        "-Jdb_password=",
        "-Jdb_table=student_courseenrollment",
        "-Jdb_ref_column=id",
        "-Jdb_validate_query=SELECT 1"
    )
