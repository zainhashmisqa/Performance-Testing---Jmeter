# Monitoring Stack (Concept 8)

## Start
```bash
cd monitoring
docker compose up -d
```
- **Grafana** → http://localhost:3000 (admin / admin)
- **InfluxDB** → http://localhost:8086, database `jmeter`

Both the InfluxDB datasource and the custom k6-style dashboard are
**auto-provisioned** — no manual import needed.

## Dashboard

The provisioned dashboard (`provisioning/dashboards/azm-sba-perf.json`) includes:

| Section | Panels |
|---|---|
| Overview | Virtual Users, Requests/s, Errors/s, Checks/s |
| Response Time | Mean, Max, Min, p90, p95, p99 stats + time-series |
| Test Results | Total, Passed, Failed, Error Rate gauge, Peak VUs, Data Sent/Received |
| Weighted Mix | Donut chart, Pass vs Fail bar, Request Detail table |
| Throughput & Bandwidth | Per-transaction throughput, Data Transfer (sent/received) |
| Distributed (Concept 7) | Samples, Workers, Errors, Avg Response, p90, p99 + comparison charts |

Template variables: `application` (default `azm_sba`) and `transaction` (default All).

## Verify data is arriving
```bash
curl -G http://localhost:8086/query \
  --data-urlencode "db=jmeter" \
  --data-urlencode "q=SHOW MEASUREMENTS"
```

## Reload after JSON changes
Grafana caches provisioned dashboards in its internal DB. To reload:
```bash
docker compose stop grafana
docker compose rm -f grafana
docker volume rm monitoring_grafana-data
docker compose up -d grafana
```

## Stop / reset
```bash
docker compose down        # keep data
docker compose down -v     # wipe InfluxDB + Grafana state
```
