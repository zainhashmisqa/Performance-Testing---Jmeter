# Distributed Load Testing — Runbook
### Concept 7 (Quick Guide) / Concept 12 (deck)

Verified working: a controller driving **2 worker nodes**, with properties
propagating correctly and both workers generating equal load.

---

## Verified evidence

Run on loopback with two real JMeter server nodes (ports 1099 and 1100) using
`tests/probe_distributed.jmx`, a plan with **no HTTP samplers** — it exercises
the distribution plumbing only, so it can be re-run any time without touching a
target application.

```
Configuring remote engine: 127.0.0.1:1099
Configuring remote engine: 127.0.0.1:1100
Starting distributed test with remote engines: [127.0.0.1:1100, 127.0.0.1:1099]
summary =    200 in 00:00:01 =  219.8/s  Err: 0 (0.00%)

Total samples: 200          (5 threads x 20 loops x 2 workers)
  127.0.0.1:1099-probe   100 samples
  127.0.0.1:1100-probe   100 samples
  G-OK worker=w1         100 samples     <- -G property arrived
  G-OK worker=w2         100 samples     <- -G property arrived
  Errors: 0
```

The probe sampler **fails deliberately** unless the controller's `-G` property is
present on the worker, so `Err: 0` is positive proof of propagation rather than
an absence of evidence. The distinct `worker=w1` / `worker=w2` values
simultaneously prove that per-worker *local* properties survive alongside the
broadcast ones — which is what makes per-worker CSV slicing possible.

Reproduce:
```powershell
# two workers
.\run\worker-start.ps1 -WorkerIndex 1 -HostIp <ip1>
.\run\worker-start.ps1 -WorkerIndex 2 -HostIp <ip2>
# controller
.\run\distributed.ps1 -Workers <ip1>,<ip2> -Threads 100
```

---

## The four traps, and how this repo handles each

### 1. `-J` does not reach the workers
`-J` sets a property in the **controller's** JVM only. Workers never see it and
silently fall back to their own defaults — you believe you ran 200 VUs against
staging and actually ran 50 against localhost. Nothing warns you.

**Handled:** `run/distributed.ps1` sends everything the workers need with `-G`,
reading values from `config/user.properties` so there is still one source of
truth. `scripts/validate_repo.py` fails the build if a `-J` flag reappears there.

### 2. RMI SSL is on by default, and `-D` does not turn it off
`server.rmi.ssl.disable` is a **JMeter** property, not a JVM system property.
Passing `-Dserver.rmi.ssl.disable=true` does nothing at all; the worker exports
its RMI stub with an SSL socket factory and the controller dies with:

```
java.io.FileNotFoundException: rmi_keystore.jks (The system cannot find the file specified)
```

This cost real debugging time and the error message points nowhere useful.

**Handled:** `config/rmi-nossl.properties` is loaded with `-q` on **both** the
controller and every worker. Both launcher scripts do this automatically.

> Alternative for a security-sensitive network: keep SSL on and generate the
> keystore with `<jmeter>/bin/create-rmi-keystore.bat`, then distribute
> `rmi_keystore.jks` to every node. Disabling SSL is appropriate on an isolated
> test subnet, which is the assumption here.

### 3. Total load = threads x workers
`-Threads` is the **per-worker** count. `-Threads 100` across 2 workers is
**200 VUs**, not 100. Getting this wrong means reporting the wrong load level
against the SLA table.

**Handled:** `distributed.ps1` prints the real total prominently and warns when
it is neither 50 (baseline) nor 200 (peak), suggesting the correct per-worker
figure.

### 4. CSV data is not split across workers
JMeter does **not** partition a CSV Data Set. Every worker opens its own copy at
row 1, so with `shareMode=All threads` both workers hand out `azm_test_001`
first. The same account logs in concurrently on every node, producing session
collisions and row contention that look like an application bottleneck but are
a test-data defect.

**Handled:** `scripts/partition_csv.py` splits the accounts into disjoint
per-worker slices and asserts zero overlap:

```
python scripts\partition_csv.py --workers 2
  worker 1: data/logins_w1.csv  (60 accounts)
  worker 2: data/logins_w2.csv  (60 accounts)
  OK - 120 unique accounts, no overlap between workers.
```

Because `-G` broadcasts **one** value to **all** workers, the slice cannot come
from the controller. Each worker loads its own via `-Jcsvfile=...` locally —
which is exactly what `run/worker-start.ps1 -WorkerIndex N` does.

---

## Worker prerequisites

Each worker must have all of these, or the run fails in ways that are hard to
diagnose mid-test:

| Requirement | Why |
|---|---|
| **Identical JMeter version** (5.6.3) | RMI serialisation is version-sensitive |
| Same Java major version | avoids serialisation mismatches |
| The repo at the same relative layout | JSR223 `filename` references and the CSV resolve against the worker's own working directory |
| JDBC driver jar in `<jmeter>/lib/` | Concept 11 runs on the worker, not the controller |
| Its own CSV slice | see trap 4 |
| RMI port open (1099 + the server port) | controller-to-worker and callback traffic |
| Same subnet as the controller | per the brief |

`run/worker-start.ps1` checks the repo layout, the CSV slice and the JDBC driver
before starting, and refuses with a clear message rather than starting a node
that will fail later.

---

## What the controller does with the results

JMeter streams every worker's samples back and merges them into the single `-l`
file, so **one HTML report already covers the whole run** — there is no manual
`.jtl` merge step. `distributed.ps1` additionally prints a per-worker sample
count from `threadName`, which is how you prove every worker actually
participated rather than one node quietly doing all the work.

Self-healing evidence stays traceable too: each worker writes
`results/self-heal-<workerId>.log` on its own disk, and every line carries
`[workerId@hostname]`.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `FileNotFoundException: rmi_keystore.jks` | RMI SSL still enabled — load `config/rmi-nossl.properties` with `-q` on **both** sides |
| `Following remote engines could not be configured` | worker not running, port blocked, or the SSL mismatch above |
| Worker connects then no samples arrive | `-Djava.rmi.server.hostname` not set to the worker's own reachable IP |
| Half the expected load | `-Threads` is per worker; check the printed total |
| Duplicate-login errors under load | CSV not partitioned — run `scripts/partition_csv.py` |
| `ClassNotFoundException` on a worker | JMeter version mismatch, or a plugin present on the controller but not the worker |
| Properties ignored on workers | they were passed with `-J` instead of `-G` |
