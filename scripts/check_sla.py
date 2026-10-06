#!/usr/bin/env python3
"""
SLA gate for the AZM JMeter assignment.

Reads a JMeter .jtl (CSV format) and grades it against the brief's numbers:

    Baseline   50 VUs    p95 <= 2000 ms  ·  p99 <= 4000 ms
    Peak      200 VUs    error rate < 1% ·  assertions 100%
    Spike     200 in 1s  checkout p95 <= 3000 ms

Reports p90/p95/p99 per request label — never averages, which is the first
pitfall the brief calls out. Exits non-zero on a breach so CI fails loudly
instead of publishing a report nobody reads.

Pure file parsing. No network.

Usage:
    python scripts/check_sla.py results/baseline.jtl --level baseline
    python scripts/check_sla.py results/peak.jtl     --level peak
    python scripts/check_sla.py results/spike.jtl    --level spike
    python scripts/check_sla.py results/run.jtl      --level none   # report only
"""
import argparse
import collections
import csv
import sys

LEVELS = {
    "baseline": {"p95": 2000, "p99": 4000, "err": None, "label_prefix": "TX-"},
    "peak":     {"p95": None, "p99": None, "err": 1.0,  "label_prefix": "TX-"},
    "spike":    {"p95": 3000, "p99": None, "err": None, "label_prefix": "TX-03"},
    "smoke":    {"p95": None, "p99": None, "err": 5.0,  "label_prefix": "TX-"},
    "none":     {"p95": None, "p99": None, "err": None, "label_prefix": "TX-"},
}


def percentile(sorted_values, pct):
    """Nearest-rank percentile — same convention as JMeter's HTML report."""
    if not sorted_values:
        return 0
    k = max(1, int(round(pct / 100.0 * len(sorted_values) + 0.5)) - 1)
    return sorted_values[min(k, len(sorted_values) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jtl")
    ap.add_argument("--level", default="none", choices=sorted(LEVELS))
    ap.add_argument("--ci", action="store_true", help="emit ::error:: annotations")
    args = ap.parse_args()
    sla = LEVELS[args.level]

    try:
        with open(args.jtl, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"ERROR: {args.jtl} not found")
        return 1

    if not rows:
        print("ERROR: no samples recorded — the run produced nothing")
        return 1

    if "elapsed" not in rows[0]:
        print("ERROR: .jtl has no 'elapsed' column. Was it saved in CSV format "
              "with field names? Check jmeter.save.saveservice.output_format=csv")
        return 1

    times = collections.defaultdict(list)
    failures = collections.Counter()
    codes = collections.defaultdict(collections.Counter)
    total_fail = 0
    assertion_fail = 0

    for r in rows:
        label = r.get("label", "?")
        try:
            times[label].append(int(r["elapsed"]))
        except (ValueError, TypeError):
            continue
        ok = str(r.get("success", "")).lower() == "true"
        if not ok:
            total_fail += 1
            failures[label] += 1
            codes[label][r.get("responseCode", "?")] += 1
            msg = r.get("failureMessage", "") or ""
            if msg:
                assertion_fail += 1

    total = sum(len(v) for v in times.values())
    err_rate = total_fail / total * 100 if total else 0.0

    print("=" * 96)
    print(f"SLA REPORT — {args.jtl}   level={args.level}   samples={total}")
    print("=" * 96)
    print(f"{'Label':<44}{'n':>7}{'p90':>8}{'p95':>8}{'p99':>8}{'max':>8}{'err%':>8}")
    print("-" * 96)

    breaches = []
    for label in sorted(times):
        v = sorted(times[label])
        p90, p95, p99 = percentile(v, 90), percentile(v, 95), percentile(v, 99)
        lerr = failures[label] / len(v) * 100
        print(f"{label:<44}{len(v):>7}{p90:>8}{p95:>8}{p99:>8}{max(v):>8}{lerr:>7.2f}%")

        if not label.startswith(sla["label_prefix"]):
            continue
        if sla["p95"] and p95 > sla["p95"]:
            breaches.append(f"{label} p95 {p95}ms > {sla['p95']}ms")
        if sla["p99"] and p99 > sla["p99"]:
            breaches.append(f"{label} p99 {p99}ms > {sla['p99']}ms")

    print("-" * 96)
    print(f"Overall error rate: {err_rate:.2f}%   failed samples: {total_fail}"
          f"   with assertion messages: {assertion_fail}")

    if failures:
        print("\nError breakdown by request:")
        for label, n in failures.most_common():
            detail = ", ".join(f"{c}x{k}" for k, c in codes[label].most_common(4))
            print(f"  {label:<44}{n:>6}  [{detail}]")

    if sla["err"] is not None and err_rate >= sla["err"]:
        breaches.append(f"error rate {err_rate:.2f}% >= {sla['err']}%")
    if args.level == "peak" and assertion_fail > 0:
        breaches.append(f"{assertion_fail} assertion failures (peak requires 100% passing)")

    # Bottleneck call-out — the analysis the brief grades on.
    tx = {k: sorted(v) for k, v in times.items() if k.startswith("TX-")}
    if tx:
        worst = max(tx, key=lambda k: percentile(tx[k], 95))
        print(f"\nSlowest transaction by p95: {worst} "
              f"({percentile(tx[worst], 95)}ms) — name this as the bottleneck "
              f"and cross-check it against the Grafana response-time-over-time panel.")

    print()
    if breaches:
        for b in breaches:
            print(f"{'::error::' if args.ci else 'SLA BREACH — '}{b}")
        print(f"\nRESULT: FAIL ({len(breaches)} breach(es))")
        return 1

    print("RESULT: PASS — all SLAs met." if args.level != "none"
          else "RESULT: report only, no SLA applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
