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

## Key Numbers

| Metric | Value |
|---|---|
| Concepts | **17 / 17** (Tier A: 14 · Tier B: 3) |
| Properties | **49** externalized — zero hardcoded values |
| Assertions | **54** (JSONPath + Response + Duration + JSR223) |
| HTTP Samplers | 18 |
| JSON Extractors | 16 |
| Groovy Scripts | 12 |
| Thread Groups | 4 |
| CI/CD Workflows | 3 (`workflow_dispatch` only) |

---

## Grafana Dashboard

Auto-provisioned via Docker Compose — 7 sections covering response times, throughput, error rates, weighted mix, and distributed worker comparison.

<p align="center">
  <img src="docs/screenshots/grafana-overview.png" width="800" alt="Grafana Overview"/>
</p>

<p align="center">
  <img src="docs/screenshots/grafana-results.png" width="800" alt="Grafana Results"/>
</p>

<p align="center">
  <img src="docs/screenshots/grafana-distributed.png" width="800" alt="Grafana Distributed"/>
</p>

---

## The 17 Concepts

| # | Concept | Tier | Implementation |
|---|---|---|---|
| 1 | Weighted Mix | A | 3 Throughput Controllers: 50/30/20 split |
| 2 | Correlation | A | 16 JSON Extractors chained across samplers |
| 3 | Parameterization | A | CSV Data Set — 120 synthetic accounts |
| 4 | Request Chaining | A | 16 variables passed across 18 samplers |
| 5 | Profiling & Analysis | A | Transaction Controllers → per-label p90/p95/p99 |
| 6 | JSR223 Scripting | A | HMAC-SHA256 signature with nonce |
| 8 | Monitoring | A | InfluxDB + Grafana + server-side metrics |
| 9 | Order Controllers | A | Random + Interleave Controllers |
| 10 | Dynamic Auth | A | Header Manager with Bearer token |
| 11 | JDBC Validation | A | DB row check with async retry |
| 12 | Assertions | A | 54 assertions on body content |
| 13 | Custom Timers | A | Gaussian + Synchronizing + Constant |
| 14 | Config Management | A | 49 properties with env overlays |
| 15 | Error Handling | A | While Controller retry with backoff |
| 7 | Distributed Load | B | `-G` forwarding, CSV partitioning, worker analysis |
| 16 | CI/CD Integration | B | 3 workflows with SLA gate + GitHub Pages |
| 17 | AI Self-Healing | B | 4-layer agent with circuit breaker and correlation guardian |

---

## CI/CD

Three workflows, all **manual trigger only** (`workflow_dispatch`):

| Workflow | Purpose |
|---|---|
| `perf.yml` | Full pipeline: validate → test → analyze → publish to GitHub Pages |
| `validate.yml` | Static checks: secret scan, Groovy syntax, YAML lint |
| `proof-tests.yml` | Evidence collection for self-heal, JDBC, retry |

---

## Distributed Testing

```powershell
python scripts\partition_csv.py --workers 2
.\run\worker-start.ps1 -WorkerIndex 1 -HostIp 10.0.0.11
.\run\distributed.ps1 -Workers 10.0.0.11,10.0.0.12 -Threads 100
```

Uses `-G` forwarding (not `-J`), per-worker CSV partitioning, fixed RMI ports, and post-run contribution analysis.

---

## Security

- Synthetic test accounts only — never production credentials
- All secrets via `-J` flags / GitHub Secrets — nothing committed
- `ci/secret_scan.py` runs before every pipeline
- `results/`, `*.log`, `rmi_keystore.jks` in `.gitignore`

---

## Repository Layout

```
tests/azm_sba_perf.jmx           # Single JMX — all 17 concepts
config/                           # Properties + env overlays
data/logins.csv                   # 120 synthetic test accounts
scripts/groovy/                   # 12 Groovy scripts
scripts/*.py                      # Validators, SLA checker, CSV splitter
ci/                               # Secret scan, SLA gate, summary generator
.github/workflows/                # 3 CI/CD workflows
run/                              # PowerShell runners + proof scripts
monitoring/                       # Docker Compose (InfluxDB + Grafana)
mock/mock_api.py                  # Local mock for offline testing
report/concept-mapping.md         # Full submission report
docs/screenshots/                 # Grafana dashboard screenshots
```
