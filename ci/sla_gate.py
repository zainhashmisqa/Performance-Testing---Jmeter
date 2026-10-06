#!/usr/bin/env python3
"""
SLA Gate — fail the CI build if performance thresholds are breached.

Reads a JMeter JTL (CSV) and enforces per-level SLA targets:

    smoke      p95 any   · err < 5%
    baseline   p95 ≤ 2s  · p99 ≤ 4s   · err ≤ 1%
    peak       p95 ≤ 3s  · p99 ≤ 5s   · err < 2%
    max        p95 ≤ 4s  · p99 ≤ 8s   · err < 3%
    spike      p95 ≤ 4s  · p99 ≤ 8s   · err < 5%

Reports p90/p95/p99 per request label — never averages, which is the first
pitfall the brief calls out.  Exits non-zero on a breach so CI fails loudly
instead of publishing a report nobody reads.

Output:  structured table + bottleneck call-out + JSON summary (for CI parsing)
Exit:    0 = pass, 1 = breach, 2 = usage/file error

Usage:
  python ci/sla_gate.py results/baseline.jtl baseline
  python ci/sla_gate.py results/peak.jtl peak
  python ci/sla_gate.py results/ci.jtl baseline --ci --json results/sla.json
"""
import csv
import json
import sys
import os
from collections import defaultdict

SLAS = {
    "smoke": {
        "max_error_pct": 5.0,
        "p95_ms": None,
        "p99_ms": None,
    },
    "baseline": {
        "max_error_pct": 1.0,
        "p95_ms": 2000,
        "p99_ms": 4000,
    },
    "peak": {
        "max_error_pct": 2.0,
        "p95_ms": 3000,
        "p99_ms": 5000,
    },
    "max": {
        "max_error_pct": 3.0,
        "p95_ms": 4000,
        "p99_ms": 8000,
    },
    "spike": {
        "max_error_pct": 5.0,
        "p95_ms": 4000,
        "p99_ms": 8000,
    },
}


def percentile(sorted_data, pct):
    if not sorted_data:
        return 0
    idx = int(len(sorted_data) * pct / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


def main():
    ci_mode = "--ci" in sys.argv
    json_out = None
    args = [a for a in sys.argv[1:] if a != "--ci"]

    if "--json" in args:
        ji = args.index("--json")
        if ji + 1 < len(args):
            json_out = args[ji + 1]
            args = args[:ji] + args[ji + 2:]

    if len(args) < 2:
        print(f"Usage: {sys.argv[0]} <jtl-file> <level> [--ci] [--json <path>]")
        print(f"  Levels: {', '.join(SLAS.keys())}")
        sys.exit(2)

    jtl_path = args[0]
    level = args[1].lower()

    if level not in SLAS:
        print(f"ERROR: unknown level '{level}'. Valid: {', '.join(SLAS.keys())}")
        sys.exit(2)

    if not os.path.isfile(jtl_path):
        print(f"ERROR: JTL file not found: {jtl_path}")
        sys.exit(2)

    sla = SLAS[level]

    by_label = defaultdict(lambda: {"elapsed": [], "errors": 0, "total": 0})
    totals = {"elapsed": [], "errors": 0, "total": 0}
    codes = defaultdict(lambda: defaultdict(int))

    with open(jtl_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row.get("label", "unknown")
            elapsed = int(row.get("elapsed", 0))
            success = row.get("success", "true").lower() == "true"

            by_label[label]["elapsed"].append(elapsed)
            by_label[label]["total"] += 1
            if not success:
                by_label[label]["errors"] += 1
                codes[label][row.get("responseCode", "?")] += 1

            totals["elapsed"].append(elapsed)
            totals["total"] += 1
            if not success:
                totals["errors"] += 1

    if totals["total"] == 0:
        print("ERROR: JTL file is empty")
        sys.exit(2)

    breaches = []

    error_pct = (totals["errors"] / totals["total"]) * 100
    if sla["max_error_pct"] is not None and error_pct > sla["max_error_pct"]:
        breaches.append(
            f"Error rate {error_pct:.2f}% exceeds {level} SLA of {sla['max_error_pct']}%"
        )

    all_sorted = sorted(totals["elapsed"])
    overall_p90 = percentile(all_sorted, 90)
    overall_p95 = percentile(all_sorted, 95)
    overall_p99 = percentile(all_sorted, 99)

    if sla["p95_ms"] and overall_p95 > sla["p95_ms"]:
        breaches.append(
            f"Overall p95 {overall_p95}ms exceeds {level} SLA of {sla['p95_ms']}ms"
        )
    if sla["p99_ms"] and overall_p99 > sla["p99_ms"]:
        breaches.append(
            f"Overall p99 {overall_p99}ms exceeds {level} SLA of {sla['p99_ms']}ms"
        )

    # ── Report ────────────────────────────────────────────────────────
    w = 96
    print("=" * w)
    print(f"SLA GATE — Level: {level.upper()}    File: {jtl_path}")
    print("=" * w)
    print(f"  Total samples : {totals['total']}")
    print(f"  Error rate    : {error_pct:.2f}%"
          f" (SLA: <= {sla['max_error_pct']}%)" if sla["max_error_pct"] is not None
          else f"  Error rate    : {error_pct:.2f}%")
    print(f"  Overall p90   : {overall_p90}ms")
    print(f"  Overall p95   : {overall_p95}ms"
          f" (SLA: <= {sla['p95_ms']}ms)" if sla["p95_ms"]
          else f"  Overall p95   : {overall_p95}ms")
    print(f"  Overall p99   : {overall_p99}ms"
          f" (SLA: <= {sla['p99_ms']}ms)" if sla["p99_ms"]
          else f"  Overall p99   : {overall_p99}ms")
    print()

    # Per-request breakdown
    print(f"  {'Label':<40s} {'n':>6} {'p90':>7} {'p95':>7} {'p99':>7} {'max':>7} {'err%':>7}")
    print(f"  {'-'*40} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    per_label = {}
    for label in sorted(by_label.keys()):
        d = by_label[label]
        s = sorted(d["elapsed"])
        ep = (d["errors"] / d["total"]) * 100 if d["total"] else 0
        p90 = percentile(s, 90)
        p95 = percentile(s, 95)
        p99 = percentile(s, 99)
        mx = max(s) if s else 0
        flag = ""
        if sla["p95_ms"] and p95 > sla["p95_ms"]:
            flag = " <<"
            breaches.append(f"{label} p95 {p95}ms > {sla['p95_ms']}ms")
        if sla["max_error_pct"] is not None and ep > sla["max_error_pct"] * 2:
            flag = " <<"
        print(f"  {label:<40s} {d['total']:>6} {p90:>6}ms {p95:>6}ms {p99:>6}ms {mx:>6}ms {ep:>6.1f}%{flag}")
        per_label[label] = {
            "samples": d["total"], "errors": d["errors"], "error_pct": round(ep, 2),
            "p90": p90, "p95": p95, "p99": p99, "max": mx,
        }

    # Error breakdown
    if any(codes.values()):
        print()
        print("  Error breakdown:")
        for label in sorted(codes.keys()):
            detail = ", ".join(f"{c}x{k}" for k, c in
                               sorted(codes[label].items(), key=lambda x: -x[1])[:4])
            print(f"    {label:<40s} [{detail}]")

    # Bottleneck call-out
    tx = {k: sorted(v["elapsed"]) for k, v in by_label.items() if k.startswith("TX-")}
    bottleneck = None
    if tx:
        worst = max(tx, key=lambda k: percentile(tx[k], 95))
        bottleneck = {"label": worst, "p95": percentile(tx[worst], 95)}
        print()
        print(f"  Bottleneck: {worst} (p95 = {bottleneck['p95']}ms)")
        print(f"  Cross-check against the Grafana response-time-over-time panel.")

    print()
    if breaches:
        print("  BREACHES:")
        for b in breaches:
            prefix = "::error::" if ci_mode else "  FAIL  "
            print(f"    {prefix}{b}")
        print(f"\n  Result: FAILED ({len(breaches)} breach(es))")
    else:
        print("  Result: PASSED — all SLAs met")

    # ── JSON output (for CI parsing / trend tracking) ─────────────────
    if json_out:
        summary = {
            "level": level,
            "total_samples": totals["total"],
            "total_errors": totals["errors"],
            "error_pct": round(error_pct, 2),
            "p90": overall_p90,
            "p95": overall_p95,
            "p99": overall_p99,
            "sla_pass": len(breaches) == 0,
            "breaches": breaches,
            "bottleneck": bottleneck,
            "per_label": per_label,
        }
        os.makedirs(os.path.dirname(json_out) or ".", exist_ok=True)
        with open(json_out, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\n  JSON summary: {json_out}")

    sys.exit(1 if breaches else 0)


if __name__ == "__main__":
    main()
