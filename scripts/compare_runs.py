#!/usr/bin/env python3
"""
Compare two runs and flag regressions. Pure file parsing, no network.

WHY A SINGLE RUN IS NOT ENOUGH
------------------------------
"p95 was 1.8s" means nothing on its own. The question a reviewer actually asks
is "is that better or worse than last time, and by how much?" A single-run SLA
gate catches a breach; only a comparison catches the slow drift that turns into
a breach three sprints from now, and only a comparison lets you prove a tuning
change worked.

Usage:
    python scripts/compare_runs.py results/baseline-old.jtl results/baseline-new.jtl
    python scripts/compare_runs.py old.jtl new.jtl --threshold 15 --ci
"""
import argparse
import collections
import csv
import sys


def percentile(sorted_values, pct):
    if not sorted_values:
        return 0
    k = max(1, int(round(pct / 100.0 * len(sorted_values) + 0.5)) - 1)
    return sorted_values[min(k, len(sorted_values) - 1)]


def load(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"ERROR: {path} not found")
        sys.exit(1)
    times = collections.defaultdict(list)
    fails = collections.Counter()
    for r in rows:
        try:
            times[r["label"]].append(int(r["elapsed"]))
        except (KeyError, ValueError):
            continue
        if str(r.get("success", "")).lower() != "true":
            fails[r["label"]] += 1
    return times, fails, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--threshold", type=float, default=10.0,
                    help="percent p95 increase that counts as a regression")
    ap.add_argument("--ci", action="store_true", help="emit ::error:: annotations")
    args = ap.parse_args()

    old_t, old_f, old_n = load(args.baseline)
    new_t, new_f, new_n = load(args.candidate)

    print("=" * 94)
    print(f"RUN COMPARISON   baseline={args.baseline} ({old_n} samples)")
    print(f"                 candidate={args.candidate} ({new_n} samples)")
    print(f"                 regression threshold: +{args.threshold}% on p95")
    print("=" * 94)
    print(f"{'Label':<40}{'p95 base':>10}{'p95 new':>10}{'delta':>10}{'err base':>10}{'err new':>10}")
    print("-" * 94)

    regressions, improvements = [], []
    # Only labels present in BOTH runs are comparable; the rest are reported
    # separately rather than silently dropped, because a disappearing
    # transaction is itself a finding.
    for label in sorted(set(old_t) | set(new_t)):
        if label not in old_t:
            print(f"{label:<40}{'-':>10}{percentile(sorted(new_t[label]),95):>10}{'NEW':>10}")
            continue
        if label not in new_t:
            print(f"{label:<40}{percentile(sorted(old_t[label]),95):>10}{'-':>10}{'GONE':>10}")
            regressions.append(f"{label} disappeared from the candidate run")
            continue

        o, n = sorted(old_t[label]), sorted(new_t[label])
        po, pn = percentile(o, 95), percentile(n, 95)
        delta = ((pn - po) / po * 100) if po else 0.0
        eo = old_f[label] / len(o) * 100
        en = new_f[label] / len(n) * 100
        mark = ""
        if delta > args.threshold:
            mark = "  REGRESSION"
            regressions.append(f"{label} p95 {po}ms -> {pn}ms ({delta:+.1f}%)")
        elif delta < -args.threshold:
            mark = "  improved"
            improvements.append(f"{label} p95 {po}ms -> {pn}ms ({delta:+.1f}%)")
        if en > eo + 1.0:
            regressions.append(f"{label} error rate {eo:.2f}% -> {en:.2f}%")
        print(f"{label:<40}{po:>10}{pn:>10}{delta:>9.1f}%{eo:>9.2f}%{en:>9.2f}%{mark}")

    print("-" * 94)
    if improvements:
        print("\nImprovements:")
        for i in improvements:
            print(f"  {i}")
    if regressions:
        print("\nRegressions:")
        for r in regressions:
            print(f"{'::error::' if args.ci else '  '}{r}")
        print(f"\nRESULT: FAIL - {len(regressions)} regression(s)")
        return 1
    print("\nRESULT: PASS - no regression beyond the threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
