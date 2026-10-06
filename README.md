# AZM QA — JMeter Performance Testing (Milestone 3)

**Engineer:** Zain Hashmi  
**Tool:** Apache JMeter 5.6.3  
**Target:** SBA Academy sandbox (Open edX — sitech-cloud)  
**Script:** [`tests/azm_sba_perf.jmx`](tests/azm_sba_perf.jmx) — single file, all 17 concepts

---

## Quick Start

```powershell
# Prerequisites: JMeter 5.6.3 on PATH, Java 17+, Python 3, Docker

# 1. Start monitoring stack
cd monitoring; docker compose up -d; cd ..

# 2. Run tests
.\run\smoke.ps1       # 1 VU    — validates setup
.\run\baseline.ps1    # 30 VUs  — 10 min
.\run\peak.ps1        # 40 VUs  — 15 min
.\run\spike.ps1       # 50 VUs  — 15 min

# 3. Proof runs
.\run\proof-self-heal.ps1    # Self-healing evidence
.\run\proof-jdbc.ps1         # DB validation evidence

# 4. Validation
python scripts\validate_repo.py
python ci\secret_scan.py
```

Results go to `results/<level>-<timestamp>/` with `.jtl`, HTML report, and SLA verdict.

---

## Project Structure

```
├── tests/
│   └── azm_sba_perf.jmx                  # Single JMX — all 17 concepts
├── config/
│   ├── user.properties                    # 49 externalized properties (base_url, threads, rampup, etc.)
│   ├── staging.properties                 # Staging environment overlay
│   ├── local.properties                   # Local dev overlay
│   ├── rmi-nossl.properties               # RMI config for distributed testing
│   └── endpoints.md                       # API endpoint mapping
├── data/
│   └── logins.csv                         # 120 synthetic test accounts
├── scripts/
│   ├── groovy/                            # 12 Groovy scripts (all cacheKey=true)
│   │   ├── self_heal_token.groovy         # 4-layer self-healing agent
│   │   ├── correlation_guardian.groovy    # Multi-field correlation healer
│   │   ├── self_heal_stats.groovy         # Healing statistics reporter
│   │   ├── signature_preprocessor.groovy  # HMAC-SHA256 request signing
│   │   ├── retry_postprocessor.groovy     # Retry logic with backoff
│   │   ├── retry_reset_preprocessor.groovy# Retry state reset
│   │   ├── jdbc_assertion.groovy          # DB row validation
│   │   ├── jdbc_seed_h2.groovy            # H2 embedded DB setup for CI
│   │   ├── token_pool_publish.groovy      # Inter-thread token sharing
│   │   ├── token_pool_bind.groovy         # Token binding per thread
│   │   ├── server_metrics.groovy          # Server-side metric collection
│   │   └── teardown_cleanup.groovy        # Post-run cleanup
│   ├── validate_repo.py                   # 15-check static validator
│   ├── check_sla.py                       # SLA checker with bottleneck ID
│   ├── compare_runs.py                    # Run-over-run regression detector
│   └── partition_csv.py                   # CSV splitter for distributed workers
├── ci/
│   ├── secret_scan.py                     # Credential leak prevention
│   ├── sla_gate.py                        # CI SLA gate with JSON output
│   └── generate_summary.py               # GitHub Step Summary generator
├── .github/workflows/
│   ├── perf.yml                           # Full pipeline: validate → test → analyze → publish
│   ├── validate.yml                       # Static validation gate
│   └── proof-tests.yml                    # Evidence collector (self-heal/JDBC/retry)
├── run/
│   ├── smoke.ps1                          # 1 VU smoke test
│   ├── baseline.ps1                       # 30 VU baseline
│   ├── peak.ps1                           # 40 VU peak load
│   ├── spike.ps1                          # 50 VU spike burst
│   ├── distributed.ps1                    # Distributed controller script
│   ├── worker-start.ps1                   # Worker node launcher
│   ├── proof-self-heal.ps1                # Self-healing evidence run
│   └── proof-jdbc.ps1                     # JDBC validation evidence run
├── monitoring/
│   ├── docker-compose.yml                 # InfluxDB 1.8 + Grafana 10.4.2
│   └── provisioning/                      # Auto-provisioned datasource + dashboard
├── mock/
│   └── mock_api.py                        # Local mock server for offline testing
├── report/
│   └── concept-mapping.md                 # Full submission report
└── docs/
    └── screenshots/                       # Grafana dashboard screenshots
```

---

## The 17 Concepts

| # | Concept | Description |
|---|---|---|
| 1 | Weighted Mix | Three Throughput Controllers split traffic 50% browse / 30% cart / 20% checkout — percentages driven by `${__P()}` properties so the ratio changes without editing the script |
| 2 | Correlation | 16 JSON Extractors capture dynamic values (`authToken`, `userId`, `courseSlug`, `enrollmentId`, `certId`, `orderId`, etc.) from one response and feed them into the next request |
| 3 | Parameterization | CSV Data Set Config loads 120 synthetic test accounts from `data/logins.csv` with `shareMode=All` so each virtual user gets a unique login |
| 4 | Request Chaining | 16 correlated variables flow across 18 HTTP samplers — login token used in headers, course slug in URLs, order ID in checkout, enrollment ID in verification |
| 5 | Profiling & Analysis | Transaction Controllers wrap each business step so the HTML report breaks down p90/p95/p99 per transaction — identifies which step is the bottleneck |
| 6 | JSR223 Scripting | Groovy PreProcessor computes HMAC-SHA256 signature over a canonical request fingerprint (method + path + userId + nonce + timestamp) for every checkout request |
| 7 | Distributed Load | Controller + worker architecture using `-G` property forwarding (not `-J`), per-worker CSV partitioning, fixed RMI ports, NTP sync check, and post-run worker contribution analysis |
| 8 | Monitoring & Reporting | Backend Listener streams live metrics to InfluxDB → Grafana dashboard with 38 panels across 7 sections (see dashboard details below) + server-side metric polling |
| 9 | Order Controllers | Random Controller randomizes browse path selection, Interleave Controller alternates cart entries — prevents all virtual users from hitting the same endpoint in lockstep |
| 10 | Dynamic Auth Headers | HTTP Header Manager injects `Authorization: Bearer ${authToken}` into every request — token extracted once during setUp and shared via inter-thread property |
| 11 | JDBC Validation | After checkout, a JDBC Request queries the enrollment table to confirm the row was actually persisted — handles async writes with configurable retry (up to `db_max_tries`) |
| 12 | Assertions | 54 assertions validate response body content (not just HTTP 200): JSONPath checks on `$.status`, Response assertions on business fields, Duration assertion on checkout SLA, JSR223 assertion on DB result |
| 13 | Custom Timers | Gaussian Random Timer (2000ms ± 1000ms) simulates human think time, Synchronizing Timer creates coordinated spike bursts, Constant Timer controls pacing |
| 14 | Config Management | Every operational value externalized via `${__P(name,default)}` — 49 distinct properties across target URL, load profile, thresholds, DB config, monitoring. Environment switching via `-q config/staging.properties` overlays |
| 15 | Error Handling & Retry | While Controller + Groovy PostProcessor retries failed requests up to 3 times with linear backoff (500ms, 1000ms, 1500ms) — checks body content, not just status code. Provable with `-Jforce_fail=true` |
| 16 | CI/CD Integration | 3 GitHub Actions workflows (all `workflow_dispatch` only): validation gate, full performance pipeline with SLA gate + regression detection, and evidence collector. Publishes results to GitHub Pages |
| 17 | AI Self-Healing | 4-layer agent: deterministic alias map (16 field names) → JWT structure detection → heuristic pattern matching → optional LLM fallback. Includes circuit breaker, correlation guardian for all 7 extracted variables, and response fingerprinting |

---

## Monitoring Stack — InfluxDB + Grafana

The monitoring stack runs via Docker Compose (`monitoring/docker-compose.yml`):

- **InfluxDB 1.8** — time-series database receiving live JMeter metrics via Backend Listener
- **Grafana 10.4.2** — auto-provisioned dashboard, no manual import needed

```powershell
cd monitoring; docker compose up -d; cd ..
# Grafana: http://localhost:3000 (admin / admin)
```

### Dashboard — 38 Panels, 7 Sections

The custom dashboard (`monitoring/provisioning/dashboards/azm-sba-perf.json`) provides real-time visibility during test execution:

| Section | Panels | What It Shows |
|---|---|---|
| **Overview** | Virtual Users · Requests/s · Errors/s · Checks/s | Live load shape — how many VUs are active, request throughput, and error rate trending over time |
| **Response Time** | Avg · Max · Min · p90 · p95 · p99 · Time Series · Per Transaction | Full latency breakdown — stat panels show current percentiles, time-series chart shows how response times change under load, per-transaction view isolates slow endpoints |
| **Test Results** | Total Samples · Passed · Failed · Error Rate · Peak VUs · Data Sent · Data Received · Avg Response | Summary counters — at a glance: how many requests ran, pass/fail ratio, error rate gauge, and data transfer volume |
| **Weighted Mix** | Mix Breakdown · Pass vs Fail per Request · Request Detail | Validates the 50/30/20 traffic split is working correctly and shows which specific requests are failing |
| **Throughput** | Per-Transaction Throughput · Data Transfer (bytes/s) | Stacked throughput chart per transaction type and network bandwidth consumption |
| **Per Transaction** | Response Time per Sampler | Isolates each HTTP sampler's response time — the chart that answers "which API call is the bottleneck?" |
| **Distributed** | Total Samples · Workers · Errors · Avg Response · p90 · p99 · Throughput Comparison · Response Time Comparison | Worker-level breakdown — proves all workers participated evenly, compares throughput and latency across nodes |

### Dashboard Screenshots

<p align="center">
  <img src="docs/screenshots/grafana-overview.png" width="800" alt="Overview + Response Time sections"/>
</p>

<p align="center">
  <img src="docs/screenshots/grafana-results.png" width="800" alt="Test Results + Weighted Mix + Throughput sections"/>
</p>

<p align="center">
  <img src="docs/screenshots/grafana-distributed.png" width="800" alt="Distributed Load Testing section"/>
</p>

### InfluxDB Data Flow

```
JMeter Backend Listener
    ↓  (HTTP POST every 15s)
InfluxDB 1.8 (database: jmeter, measurement: jmeter)
    ↓  (InfluxQL queries)
Grafana Dashboard (38 panels, auto-refresh 5s)
```

Metrics stored in InfluxDB: `hit` (request count), `avg`/`min`/`max`/`pct90`/`pct95`/`pct99` (response times), `countError` (errors), `maxAT`/`meanAT`/`minAT` (active threads), `sentBytes`/`receivedBytes` (data transfer).

---

## CI/CD

Three workflows, all **manual trigger only** (`workflow_dispatch`):

| Workflow | Jobs | Purpose |
|---|---|---|
| `perf.yml` | validate → test → analyze → publish | Full pipeline with SLA gate, regression detection, and GitHub Pages dashboard |
| `validate.yml` | validate | Static checks: secret scan, Groovy syntax, YAML lint |
| `proof-tests.yml` | proof | Evidence collection for self-heal, JDBC, retry — uploads artifacts |

---

## Security

- Synthetic test accounts only (`.invalid` domain) — never production credentials
- All secrets supplied at runtime via `-J` flags / GitHub Secrets — nothing committed
- `ci/secret_scan.py` scans for API keys, tokens, passwords before every pipeline
- `results/`, `*.log`, `rmi_keystore.jks` excluded via `.gitignore`
- JDBC gated behind `jdbc_enabled` property — degrades cleanly without the driver
