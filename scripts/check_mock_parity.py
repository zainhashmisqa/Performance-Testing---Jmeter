#!/usr/bin/env python3
"""
Verify the local mock serves every path the test plan actually calls.

WHY THIS EXISTS
---------------
The mock and the .jmx drifted apart once: the plan was moved to the SBA
/api/catalog/... contract while the mock still served an older Open edX shape.
Every request 404'd, the run reported a ~90% error rate, and the numbers that
came out of it were meaningless - but nothing in the pipeline said so, because
a 404 is a perfectly valid HTTP response and the run "completed".

This check makes that failure mode loud and cheap to catch. It is static: no
server is started and no request is sent.

Exit code 0 = parity holds, 1 = a path the script calls has no route.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JMX = ROOT / "tests" / "azm_sba_perf.jmx"
PROPS = ROOT / "config" / "user.properties"
MOCK = ROOT / "mock" / "mock_api.py"


def load_properties():
    props = {}
    for line in PROPS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        props[k.strip()] = v.strip()
    return props


def resolve(path_expr, props):
    """Turn ${__P(name,default)} and ${var} into a concrete path to compare."""
    # ${__P(name,default)} -> the value from user.properties, else the default
    def _p(m):
        name, default = m.group(1), m.group(2) or ""
        return props.get(name, default)

    out = re.sub(r"\$\{__P\(([^,)]+),?([^)]*)\)\}", _p, path_expr)
    # Runtime variables stand in for a value we cannot know statically.
    out = re.sub(r"\$\{[^}]+\}", "VAR", out)
    out = out.replace("&amp;", "&")
    return out.split("?")[0]


def main():
    props = load_properties()
    jmx = JMX.read_text(encoding="utf-8")
    mock = MOCK.read_text(encoding="utf-8")

    raw_paths = re.findall(r'name="HTTPSampler\.path">([^<]*)</stringProp>', jmx)
    paths = sorted({resolve(p, props) for p in raw_paths if p.strip()})

    # Routes the mock declares, as literal strings in its source.
    routes = re.findall(r'["\'](/[A-Za-z0-9_\-/]*)["\']', mock)
    routes = sorted({r.rstrip("/") for r in routes if r.startswith("/")})

    print("=" * 72)
    print("MOCK PARITY - does the mock answer every path the plan calls?")
    print("=" * 72)

    missing = []
    for p in paths:
        probe = p.rstrip("/")
        # A path ending in a variable segment is a detail call; its parent route
        # is what the mock has to recognise.
        if probe.endswith("/VAR"):
            probe = probe[: -len("/VAR")]
        hit = any(probe == r or probe.startswith(r + "/") or r.startswith(probe)
                  for r in routes)
        print(("  ok   " if hit else "  FAIL ") + p)
        if not hit:
            missing.append(p)

    print()
    if missing:
        print("%d path(s) have no route in the mock:" % len(missing))
        for m in missing:
            print("   ", m)
        print()
        print("A local run against this mock would 404 on those calls and the")
        print("resulting error rate would be an artefact of the mock, not of the")
        print("script. Add the route to mock/mock_api.py before trusting a run.")
        return 1

    print("Parity holds: every sampler path has a matching route in the mock.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
