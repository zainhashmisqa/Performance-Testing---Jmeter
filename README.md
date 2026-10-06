# AZM QA — JMeter Performance Testing (Milestone 3)

**Engineer:** Zain Hashmi  
**Tool:** Apache JMeter 5.6.3  
**Target:** SBA Academy sandbox (Open edX — sitech-cloud)  
**Script:** [`tests/azm_sba_perf.jmx`](tests/azm_sba_perf.jmx) — single file, all 17 concepts

---

## Quick start

```powershell
# 0. Prerequisites: JMeter 5.6.3 on PATH, Java 17+, Python 3, Docker

# 1. Monitoring stack (InfluxDB + Grafana — auto-provisioned)
cd monitoring; docker compose up -d; cd ..
# Grafana: http://localhost:3000 (admin / admin)

# 2. Smoke test — 1 VU, validates correlation and chaining
.\run\smoke.ps1

# 3. Graded runs
.\run\baseline.ps1   # 30 VUs  / 60s ramp  / 10 min
.\run\peak.ps1       # 40 VUs  / 90s ramp  / 15 min
.\run\spike.ps1      # 50 VUs  / 120s ramp / 15 min

# 4. Tier B proofs
.\run\proof-self-heal.ps1    # Concept 17 — token field rename recovery
.\run\proof-jdbc.ps1         # Concept 11 — H2 embedded DB validation

# 5. Static validation (no network required)
python scripts\validate_repo.py
python ci\secret_scan.py
```

Each run creates `results/<level>-<timestamp>/` with the `.jtl`, HTML report, JMeter log, and SLA verdict.

---

## Key numbers

| Metric | Value |
|---|---|
| Concepts implemented | **17 / 17** (Tier A: 14, Tier B: 3) |
| Externalized properties | **49** via `${__P(name,default)}` — zero hardcoded values |
| Assertions | **54** (17 Response + 35 JSONPath + 1 Duration + 1 JSR223) |
| HTTP Samplers | 18 |
| JSON Extractors | 16 (correlation chain) |
| External Groovy Scripts | 12 (all `cacheKey=true`) |
| Thread Groups | 4 (setUp + Main + Monitor + tearDown) |
| CI/CD Workflows | 3 (validate + perf pipeline + proof-tests) |
| Grafana Dashboard | Custom k6-style, 7 sections, auto-provisioned |
| JMX Lines | 1,368 |

---

## Grafana dashboard (Concept 8)

Custom k6-inspired dashboard with 7 sections, auto-provisioned via Docker Compose — no manual import needed.

| Section | What it shows |
|---|---|
| Overview | Virtual Users, Requests/s, Errors/s, Checks/s |
| Response Time | p90, p95, p99 stat panels + time-series overlay |
| Test Results | Total Samples, Pass/Fail, Error Rate gauge, Peak VUs |
| Weighted Mix | Donut chart (50/30/20), Pass vs Fail by transaction |
| Throughput | Per-transaction throughput (stacked), Data Transfer |
| Per Transaction | Response time breakdown per sampler |
| Distributed | Worker samples, Avg Response, p90/p99, Throughput comparison |

### Dashboard screenshots

<p align="center">
  <img src="docs/screenshots/grafana-overview.png" width="800" alt="Grafana Overview + Response Time"/>
</p>

<p align="center">
  <img src="docs/screenshots/grafana-results.png" width="800" alt="Grafana Test Results + Weighted Mix"/>
</p>

<p align="center">
  <img src="docs/screenshots/grafana-distributed.png" width="800" alt="Grafana Distributed + Throughput"/>
</p>

> **To add screenshots:** Save your 3 Grafana screenshots as `docs/screenshots/grafana-overview.png`, `grafana-results.png`, and `grafana-distributed.png`.

---

## Repository layout

```
├── tests/
│   └── azm_sba_perf.jmx              # Single script — all 17 concepts
├── config/
│   ├── user.properties                # 49 externalized properties
│   ├── staging.properties             # Environment overlay
│   ├── local.properties               # Local dev overlay
│   ├── rmi-nossl.properties           # RMI config for distributed
│   └── endpoints.md                   # Endpoint map (verify with lead)
├── data/
│   └── logins.csv                     # 120 synthetic test accounts
├── scripts/
│   ├── groovy/                        # 10 external Groovy scripts
│   │   ├── self_heal_token.groovy     # Concept 17 — 4-layer healing agent
│   │   ├── correlation_guardian.groovy # Concept 17 — multi-field correlation healer
│   │   ├── self_heal_stats.groovy    # Concept 17 — teardown statistics
│   │   ├── signature_preprocessor.groovy  # Concept 6 — HMAC-SHA256
│   │   ├── retry_postprocessor.groovy # Concept 15 — retry with backoff
│   │   ├── jdbc_assertion.groovy      # Concept 11 — DB row validation
│   │   ├── token_pool_publish.groovy  # Concept 4 — inter-thread sharing
│   │   ├── server_metrics.groovy      # Concept 8 — server-side polling
│   │   └── ...
│   ├── validate_repo.py               # 15-check static validator
│   ├── check_sla.py                   # SLA checker with bottleneck ID
│   ├── compare_runs.py                # Run-over-run regression detector
│   └── partition_csv.py               # CSV splitter for distributed
├── ci/
│   ├── secret_scan.py                 # Credential leak prevention
│   ├── sla_gate.py                    # CI SLA gate + JSON output
│   └── generate_summary.py            # GitHub Step Summary generator
├── .github/workflows/
│   ├── perf.yml                       # 3-job pipeline: validate → test → analyze
│   ├── validate.yml                   # Static validation gate
│   └── proof-tests.yml                # Evidence collector (self-heal/JDBC/retry)
├── run/
│   ├── smoke.ps1, baseline.ps1, peak.ps1, spike.ps1
│   ├── distributed.ps1                # Controller with -G forwarding
│   ├── worker-start.ps1               # Worker launcher
│   ├── proof-self-heal.ps1            # Concept 17 evidence
│   └── proof-jdbc.ps1                 # Concept 11 evidence
├── monitoring/
│   ├── docker-compose.yml             # InfluxDB 1.8 + Grafana 10.4.2
│   └── provisioning/                  # Auto-provisioned dashboard + datasource
├── mock/
│   └── mock_api.py                    # Local mock for offline testing
├── report/
│   └── concept-mapping.md             # Full submission report
└── docs/
    ├── distributed-runbook.md         # Distributed testing guide
    └── screenshots/                   # Grafana dashboard screenshots
```

---

## The 17 concepts

| # | Concept | Tier | Where |
|---|---|---|---|
| 3 | Parameterization | A | CSV Data Set Config — 120 rows, `shareMode=All` |
| 12 | Assertions | A | 54 assertions: JSONPath, Response, Duration, JSR223 — body content, not just HTTP 200 |
| 2 | Correlation | A | 16 JSON Extractors -> `authToken`, `courseSlug`, `enrollmentId`, `orderId` etc. |
| 4 | Request Chaining | A | 16 chained variables across 18 samplers |
| 10 | Dynamic Auth Headers | A | HTTP Header Manager -> `Authorization: Bearer ${authToken}` |
| 13 | Custom Timers | A | Gaussian (2000 +/- 1000ms) + Synchronizing Timer + Constant Timer |
| 9 | Order Controllers | A | Random Controller (browse) + Interleave Controller (cart) |
| 1 | Weighted Mix | A | 3x Throughput Controller: 50/30/20 (property-driven) |
| 14 | Config Management | A | 49 `${__P()}` properties + env overlays — zero hardcoded values |
| 6 | JSR223 Scripting | A | HMAC-SHA256 signature + dynamic payload + nonce (`cacheKey=true`) |
| 15 | Error Handling & Retry | A | While Controller + Groovy PostProcessor, max 3 attempts, linear backoff |
| 11 | JDBC Validation | A | JDBC Connection Config + Request + JSR223 assertion (gated by `jdbc_enabled`) |
| 5 | Profiling & Analysis | A | Transaction Controllers per step -> per-label p90/p95/p99 |
| 8 | Monitoring & Reporting | A | InfluxDB + Grafana auto-provisioned + server-side metrics polling |
| 7 | Distributed Load | B | `-G` forwarding (not `-J`), CSV partitioning, post-run worker analysis |
| 16 | CI/CD Integration | B | 3 workflows: validation gate + perf pipeline + evidence collector |
| 17 | AI Self-Healing | B | 4-layer agent: alias map (16 names) + JWT detection + heuristic + LLM; circuit breaker, correlation guardian, response fingerprinting |

---

## CI/CD framework (Concept 16)

Three workflows, all **`workflow_dispatch` only** — no automatic triggers.

| Workflow | Jobs | Purpose |
|---|---|---|
| `perf.yml` | validate -> test -> analyze | Full performance pipeline with SLA gate + regression detection |
| `validate.yml` | validate | Fast read-only gate: secret scan, static checks, Groovy syntax, YAML lint |
| `proof-tests.yml` | proof | Evidence collector for self-heal, JDBC, retry — uploads artifacts |

All credentials from GitHub Secrets via `-J` flags. Secret scan runs first in every pipeline.

---

## Distributed testing (Concept 7)

```powershell
# Partition CSV for workers
python scripts\partition_csv.py --workers 2

# On each worker machine:
.\run\worker-start.ps1 -WorkerIndex 1 -HostIp 10.0.0.11

# On controller:
.\run\distributed.ps1 -Workers 10.0.0.11,10.0.0.12 -Threads 100
```

Key features: `-G` property forwarding (not `-J`), per-worker CSV partitioning, fixed RMI ports, NTP check, controller does NOT generate load, post-run per-worker contribution analysis.

---

## Environment switching (Concept 14)

No file edits — ever:

```powershell
# Different environment overlay
jmeter -n -t tests\azm_sba_perf.jmx -q config\user.properties -q config\staging.properties

# Override individual properties
jmeter -n -t tests\azm_sba_perf.jmx -q config\user.properties -Jbase_url=other-host -Jthreads=50
```

---

## Security

- `data/logins.csv` uses synthetic `.invalid` domain accounts — never production credentials
- All credentials supplied at runtime via `-J` flags / GitHub Secrets — none committed
- `ci/secret_scan.py` scans for API keys, tokens, passwords, JDBC URLs with embedded creds
- `results/`, `*.log`, `rmi_keystore.jks` excluded via `.gitignore`
- JDBC gated behind `jdbc_enabled` property — degrades cleanly without the driver
