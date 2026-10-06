#!/usr/bin/env python3
"""
Partition the login CSV into one file per distributed worker.

WHY THIS IS NEEDED
------------------
JMeter does NOT split a CSV Data Set across remote workers. Every worker opens
its own copy of the file and starts at row 1. With 2 workers and shareMode=All
threads, both workers hand out azm_test_001 first -- so the same account logs in
twice concurrently. On a real app that causes session collisions, skewed cache
hit rates, and row-level contention that looks like an application bottleneck
but is actually a test-data defect. It is one of the most common ways a
distributed run produces numbers nobody can trust.

Splitting the file per worker gives every worker a disjoint account set.

USAGE
    python scripts/partition_csv.py --workers 2
    python scripts/partition_csv.py --workers 3 --input data/logins.csv

Produces data/logins_w1.csv, data/logins_w2.csv, ...
Each worker loads its own slice LOCALLY (not via -G from the controller --
-G broadcasts one value to every worker, so it cannot give each a different
file). run/worker-start.ps1 -WorkerIndex N does this for you.
"""
import argparse
import csv
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--input", default="data/logins.csv")
    ap.add_argument("--min-rows-per-worker", type=int, default=50,
                    help="warn if a slice is thinner than this")
    args = ap.parse_args()

    if args.workers < 1:
        print("ERROR: --workers must be >= 1")
        return 1

    if not os.path.isfile(args.input):
        print(f"ERROR: {args.input} not found")
        return 1

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    header, data = rows[0], [r for r in rows[1:] if r and any(c.strip() for c in r)]
    if not data:
        print("ERROR: no data rows")
        return 1

    base = os.path.splitext(args.input)[0]
    slices = [data[i::args.workers] for i in range(args.workers)]

    print(f"Input: {args.input}  ({len(data)} accounts, header {header})")
    print()
    thin = False
    for i, chunk in enumerate(slices, 1):
        out = f"{base}_w{i}.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(chunk)
        flag = ""
        if len(chunk) < args.min_rows_per_worker:
            flag = "  <-- THIN: recycling will reuse accounts heavily"
            thin = True
        print(f"  worker {i}: {out}  ({len(chunk)} accounts){flag}")

    # Disjointness is the whole point - assert it rather than assume it.
    seen = set()
    overlap = 0
    for chunk in slices:
        for r in chunk:
            key = r[0]
            if key in seen:
                overlap += 1
            seen.add(key)
    print()
    if overlap:
        print(f"ERROR: {overlap} account(s) appear in more than one slice")
        return 1
    print(f"OK - {len(seen)} unique accounts, no overlap between workers.")

    if thin:
        print()
        print("WARNING: at least one slice is thin. Either add more accounts to")
        print("data/logins.csv or reduce the worker count, otherwise workers will")
        print("recycle the same few logins and your cache behaviour is unrealistic.")

    print()
    print("Now copy the repo to each worker and start them with:")
    for i in range(1, args.workers + 1):
        print(f"  worker {i}:  ./run/worker-start.ps1 -WorkerIndex {i} -HostIp <ip{i}>")
    print()
    print("(worker-start.ps1 sets -Jcsvfile locally; the controller must NOT")
    print(" send csvfile with -G or every worker would get the same slice.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
