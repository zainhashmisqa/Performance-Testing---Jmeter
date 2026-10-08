# Execution evidence

## What this is, and what it is not

Everything here comes from running the plan against the **local mock**
(`mock/mock_api.py`, bound to 127.0.0.1). It proves the framework executes:
correlation captures real values, those values drive later requests, assertions
fire on body content, retry recovers, self-healing rebinds a renamed field, and
the per-transaction breakdown is populated.

It is **not** a graded load result. No run against the SBA Academy sandbox is
included, because that needs an authorised load window from the team lead. The
baseline / peak / spike tables in `report/concept-mapping.md` stay empty until
then. Treating mock numbers as performance findings would be dishonest - the
mock's latencies are injected constants, not the application's behaviour.

## Run: framework verification

| | |
|---|---|
| Command | `jmeter -n -t tests/azm_sba_perf.jmx -Jbase_url=127.0.0.1 -Jport=8080 -Jprotocol=http -Jthreads=5 -Jrampup=5 -Jduration=90` |
| Target | local mock, loopback only |
| Samples | 312 |
| Errors | 8 (2.56%) |
| HTML report | [`mock-verification/index.html`](mock-verification/index.html) |

### Per-label results

| Label | Samples | Errors | Err % | Avg ms | p90 | p95 | p99 | Max |
|---|---|---|---|---|---|---|---|---|
| MON Server metrics | 17 | 0 | 0.00% | 5 | 9 | 15 | 15 | 15 |
| S00 Login (CSV credentials) | 1 | 0 | 0.00% | 86 | 86 | 86 | 86 | 86 |
| S00b Re-login (fallback) | 4 | 0 | 0.00% | 68 | 97 | 97 | 97 | 97 |
| S01a My Courses | 16 | 0 | 0.00% | 72 | 99 | 100 | 100 | 100 |
| S01b Certificates | 16 | 2 | 12.50% | 218 | 290 | 300 | 300 | 300 |
| S01c Categories | 9 | 0 | 0.00% | 39 | 55 | 55 | 55 | 55 |
| S01d Course Catalog (filtered by category) | 9 | 0 | 0.00% | 36 | 47 | 47 | 47 | 47 |
| S01e Course Detail (chained from catalog) | 9 | 0 | 0.00% | 35 | 44 | 44 | 44 | 44 |
| S02 User profile (chained) | 39 | 0 | 0.00% | 38 | 52 | 56 | 61 | 61 |
| S03a My Courses (explore) | 7 | 0 | 0.00% | 72 | 95 | 95 | 95 | 95 |
| S03b Certificates (explore) | 7 | 2 | 28.57% | 226 | 318 | 318 | 318 | 318 |
| S03c Categories (explore) | 5 | 0 | 0.00% | 39 | 48 | 48 | 48 | 48 |
| S03d Course Search (chained keyword) | 5 | 0 | 0.00% | 40 | 47 | 47 | 47 | 47 |
| S04 User profile (chained) | 24 | 0 | 0.00% | 39 | 50 | 54 | 59 | 59 |
| S05 My Courses (deep dive) | 16 | 0 | 0.00% | 77 | 97 | 109 | 109 | 109 |
| S06 User profile (deep dive, chained by userId) | 15 | 0 | 0.00% | 39 | 55 | 57 | 57 | 57 |
| S07 Certificates (signed, retryable, chained by course) | 15 | 0 | 0.00% | 240 | 302 | 366 | 366 | 366 |
| S08 Enrollment status (chained by course + cert) | 15 | 0 | 0.00% | 71 | 92 | 97 | 97 | 97 |
| TX-01 Browse | 42 | 2 | 4.76% | 382 | 332 | 338 | 4791 | 4791 |
| TX-02 Explore | 24 | 2 | 8.33% | 143 | 314 | 334 | 352 | 352 |
| TX-03 Deep Dive | 17 | 0 | 0.00% | 588 | 546 | 3614 | 3614 | 3614 |

### Why the 8 errors are the point, not a defect

All eight are `S01b` / `S03b Certificates` returning **HTTP 200 with
`{"status":"declined"}`**. The mock injects this on 12% of certificate calls on
purpose. A status-code check passes it; only the body assertion catches it, and
it did. That is the brief's "200 is not success" pitfall, demonstrated rather
than asserted.

The same endpoint inside `TX-03` (`S07`, wrapped in the retry loop) shows **0
errors across 15 samples** - the retry absorbed the same injected failures. The
two together show the retry is doing real work.

## Request chaining

The captured values now drive later requests. Verified from the JTL that the
journey runs in order on every thread:

```
S01c Categories          -> captures categorySlug
S01d Course Catalog      -> GET /api/catalog/courses/?category=${categorySlug}
                            captures catalogCourseSlug
S01e Course Detail       -> GET /api/catalog/courses/${catalogCourseSlug}/
                            asserts $.slug == the slug it asked for
```

Six samplers consume a value captured upstream:

| Sampler | Consumes |
|---|---|
| S01d Course Catalog | `categorySlug` |
| S01e Course Detail | `catalogCourseSlug` |
| S03d Course Search | `courseSlug` |
| S06 User profile | `userId` |
| S07 Certificates | `courseSlug` |
| S08 Enrollment status | `courseSlug`, `certId` |

The JDBC validation query also keys on `${enrollmentId}`.

The detail assertion is the one that makes this non-trivial: it compares the
response's `$.slug` against the slug the request was built from, so a chain that
silently returned the wrong record would fail rather than pass.

## Self-healing

Run with the token extractor deliberately pointed at a path that does not exist
(`-Jtoken_json_path=$.sessionToken_renamed_by_api`), simulating the API renaming
its token field:

```
.\run\proof-self-heal.ps1
```

Result - [`self-heal-summary.json`](self-heal-summary.json):

```json
{
  "total_heals": 3,
  "layers_hit": {
    "alias_map": 3,
    "circuit_breaker_field": "token",
    "last_response_structure": "email,id,status,token,user.email,user.id,user.username,username"
  },
  "verdict": "SELF-HEALING ACTIVE — 3 field(s) recovered"
}
```

The run completed at **0% errors** with the extractor broken: the alias map
recovered the token, the circuit breaker cached the working field name so later
iterations skip the scan, and the response fingerprint recorded the structure.
Per-event detail is in [`self-heal-events.txt`](self-heal-events.txt):

```
HEALED           layer=alias_map  field='token'  sampler='S00 Login (CSV credentials)'
HEALED           layer=alias_map  field='token'  sampler='S00b Re-login (fallback)'
CIRCUIT-BREAKER  cached_field='token'  after=3 heals
HEALED           layer=alias_map  field='token'  sampler='S00b Re-login (fallback)'
```

## Reproducing

```powershell
# 1. Confirm the mock still answers every path the plan calls
python scripts\check_mock_parity.py

# 2. Start the mock (loopback only)
python mock\mock_api.py --port 8080 --reset

# 3. Framework verification run
jmeter -n -t tests\azm_sba_perf.jmx -q config\user.properties `
  -l results\verify.jtl -e -o results\verify-html `
  -Jprotocol=http -Jbase_url=127.0.0.1 -Jport=8080 `
  -Jthreads=5 -Jrampup=5 -Jduration=90 `
  -Jinflux_enabled=false -Jjdbc_enabled=false

# 4. Self-healing proof
.\run\proof-self-heal.ps1
```

## Still outstanding

| Gap | Needs |
|---|---|
| Graded baseline / peak / spike results | Authorised load window against the sandbox |
| Distributed run across 2+ hosts | Two worker machines on the same subnet |
| CI pipeline execution | A manual `workflow_dispatch` trigger |
| JDBC against the real schema | Test DB credentials and written confirmation the data is synthetic |
