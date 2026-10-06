#!/usr/bin/env python3
"""
GitHub Actions step summary generator for JMeter results.

Reads a JTL file and an optional SLA JSON (from sla_gate.py --json) and writes
a rich Markdown summary to stdout. Pipe into $GITHUB_STEP_SUMMARY in CI.

Produces:
  - Overview stats table (samples, errors, p95, p99)
  - Per-request breakdown with color-coded error rates
  - Bottleneck identification
  - SLA verdict badge
  - Self-healing events (if log exists)

Usage:
  python ci/generate_summary.py results/ci.jtl baseline [results/sla.json] >> $GITHUB_STEP_SUMMARY
"""
import csv
import json
import os
import sys
from collections import defaultdict


def percentile(sorted_data, pct):
    if not sorted_data:
        return 0
    idx = int(len(sorted_data) * pct / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


def fmt_ms(ms):
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms}ms"


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <jtl> <level> [sla.json]", file=sys.stderr)
        sys.exit(2)

    jtl_path = sys.argv[1]
    level = sys.argv[2]
    sla_json = sys.argv[3] if len(sys.argv) > 3 else None

    if not os.path.isfile(jtl_path):
        print(f"ERROR: {jtl_path} not found", file=sys.stderr)
        sys.exit(2)

    by_label = defaultdict(lambda: {"elapsed": [], "errors": 0, "total": 0})
    totals = {"elapsed": [], "errors": 0, "total": 0}

    with open(jtl_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            label = row.get("label", "?")
            elapsed = int(row.get("elapsed", 0))
            ok = row.get("success", "true").lower() == "true"
            by_label[label]["elapsed"].append(elapsed)
            by_label[label]["total"] += 1
            if not ok:
                by_label[label]["errors"] += 1
            totals["elapsed"].append(elapsed)
            totals["total"] += 1
            if not ok:
                totals["errors"] += 1

    if totals["total"] == 0:
        print("No samples in JTL.", file=sys.stderr)
        sys.exit(2)

    all_sorted = sorted(totals["elapsed"])
    error_pct = totals["errors"] / totals["total"] * 100
    p90 = percentile(all_sorted, 90)
    p95 = percentile(all_sorted, 95)
    p99 = percentile(all_sorted, 99)

    sla_data = None
    if sla_json and os.path.isfile(sla_json):
        with open(sla_json) as f:
            sla_data = json.load(f)

    sla_pass = sla_data["sla_pass"] if sla_data else None
    badge = "PASS" if sla_pass else ("FAIL" if sla_pass is False else "N/A")
    badge_icon = "✅" if sla_pass else ("❌" if sla_pass is False else "ℹ️")

    out = []
    out.append(f"## {badge_icon} Performance Test — {level.upper()}\n")

    out.append("### Overview\n")
    out.append("| Metric | Value |")
    out.append("|--------|-------|")
    out.append(f"| **Level** | `{level}` |")
    out.append(f"| **Total Samples** | {totals['total']:,} |")
    out.append(f"| **Errors** | {totals['errors']:,} ({error_pct:.2f}%) |")
    out.append(f"| **p90** | {fmt_ms(p90)} |")
    out.append(f"| **p95** | {fmt_ms(p95)} |")
    out.append(f"| **p99** | {fmt_ms(p99)} |")
    out.append(f"| **Max** | {fmt_ms(max(all_sorted))} |")
    out.append(f"| **SLA** | **{badge}** |")
    out.append("")

    if sla_data and sla_data.get("breaches"):
        out.append("### SLA Breaches\n")
        for b in sla_data["breaches"]:
            out.append(f"- :x: {b}")
        out.append("")

    out.append("### Per-Request Breakdown\n")
    out.append("| Request | Samples | Errors | Error% | p90 | p95 | p99 | Max |")
    out.append("|---------|--------:|-------:|-------:|----:|----:|----:|----:|")

    for label in sorted(by_label.keys()):
        d = by_label[label]
        s = sorted(d["elapsed"])
        ep = d["errors"] / d["total"] * 100 if d["total"] else 0
        lp90 = percentile(s, 90)
        lp95 = percentile(s, 95)
        lp99 = percentile(s, 99)
        mx = max(s) if s else 0
        err_marker = " :warning:" if ep > 5 else (" :x:" if ep > 20 else "")
        out.append(f"| {label} | {d['total']} | {d['errors']} | {ep:.1f}%{err_marker} "
                   f"| {fmt_ms(lp90)} | {fmt_ms(lp95)} | {fmt_ms(lp99)} | {fmt_ms(mx)} |")
    out.append("")

    tx = {k: sorted(v["elapsed"]) for k, v in by_label.items() if k.startswith("TX-")}
    if tx:
        worst = max(tx, key=lambda k: percentile(tx[k], 95))
        wp95 = percentile(tx[worst], 95)
        out.append(f"### Bottleneck\n")
        out.append(f"Slowest transaction by p95: **{worst}** ({fmt_ms(wp95)})")
        out.append(f"Cross-check against the Grafana response-time-over-time panel.\n")

    heal_log = os.path.join(os.path.dirname(jtl_path), "..", "self-heal.log")
    if not os.path.isfile(heal_log):
        heal_log = os.path.join(os.path.dirname(jtl_path), "self-heal.log")
    if os.path.isfile(heal_log):
        with open(heal_log) as f:
            events = f.read().strip()
        if events:
            out.append("### Self-Healing Events\n")
            out.append("```")
            out.append(events)
            out.append("```\n")

    print("\n".join(out))


if __name__ == "__main__":
    main()
