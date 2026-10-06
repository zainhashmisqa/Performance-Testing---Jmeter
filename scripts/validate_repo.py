#!/usr/bin/env python3
"""
Static validator for the AZM JMeter assignment repo.

Checks the things a grader (and the brief's five pitfalls) care about, WITHOUT
running anything: JMX structure, concept coverage, hardcoded values, GUI
listeners, CSV test data, and that no real credentials are committed.

READ-ONLY. No network, no subprocess, no server contact. Parses files only.

Usage:  python scripts/validate_repo.py
Exit:   0 = clean, 1 = at least one error
"""
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET

# Repo root = parent of scripts/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JMX = os.path.join(ROOT, "tests", "azm_sba_perf.jmx")
PROPS = os.path.join(ROOT, "config", "user.properties")

errors, warnings, notes = [], [], []


def err(m): errors.append(m)
def warn(m): warnings.append(m)
def note(m): notes.append(m)


# --------------------------------------------------------------- 1. XML parse
try:
    tree = ET.parse(JMX)
    root = tree.getroot()
    note(f"JMX parses. Root <{root.tag}> jmeter={root.get('jmeter')}")
except ET.ParseError as e:
    err(f"JMX is not well-formed XML: {e}")
    print("FATAL"); sys.exit(1)

# ------------------------------------------- 2. hashTree pairing (JMeter rule)
# Inside a <hashTree>, every test element MUST be followed by its own <hashTree>.
# A missed pair is the #1 reason a hand-edited .jmx loads with a mangled tree.
def check_pairs(ht, path="root"):
    kids = list(ht)
    i = 0
    while i < len(kids):
        node = kids[i]
        if node.tag == "hashTree":
            err(f"Orphan <hashTree> with no preceding element at {path}[{i}]")
            i += 1
            continue
        nxt = kids[i + 1] if i + 1 < len(kids) else None
        if nxt is None or nxt.tag != "hashTree":
            name = node.get("testname", node.tag)
            err(f"Element not followed by <hashTree>: '{name}' ({node.tag}) at {path}")
            i += 1
            continue
        check_pairs(nxt, f"{path}/{node.get('testname', node.tag)}")
        i += 2

for ht in root.findall("hashTree"):
    check_pairs(ht)

# ------------------------------------------------- 3. element inventory / tiers
elements = [e for e in root.iter() if e.get("testclass")]
by_class = {}
for e in elements:
    by_class.setdefault(e.get("testclass"), []).append(e.get("testname", ""))

required = {
    "CSVDataSet": "3 Parameterization",
    "JSONPostProcessor": "2 Correlation",
    "HeaderManager": "10 Dynamic Auth Headers",
    "GaussianRandomTimer": "13 Custom Timers (think time)",
    "SyncTimer": "13 Custom Timers (spike)",
    "RandomController": "9 Order Controllers",
    "InterleaveControl": "9 Order Controllers",
    "ThroughputController": "1 Weighted Mix",
    "JSR223PreProcessor": "6 JSR223 Scripting",
    "JSR223PostProcessor": "15 Retry / 17 Self-heal",
    "WhileController": "15 Error Handling & Retry",
    "JDBCDataSource": "11 JDBC Validation (pool)",
    "JDBCSampler": "11 JDBC Validation (query)",
    "JSR223Assertion": "11 JDBC assertion",
    "BackendListener": "8 Monitoring",
    "TransactionController": "5 Profiling",
    "SetupThreadGroup": "setUp login",
    "ThreadGroup": "main load",
}
for cls, concept in required.items():
    if cls not in by_class:
        err(f"MISSING element {cls}  (concept {concept})")

# assertions: must assert on body, not only response code
assertion_classes = ["JSONPathAssertion", "ResponseAssertion", "JSR223Assertion"]
n_assert = sum(len(by_class.get(c, [])) for c in assertion_classes)
if n_assert < 4:
    warn(f"Only {n_assert} assertions found — brief expects body assertions on every business step")

# --------------------------------------------- 4. weighted mix totals to 100
pcts = []
for e in elements:
    if e.get("testclass") == "ThroughputController":
        for sp in e.findall("stringProp"):
            if sp.get("name") == "ThroughputController.percentThroughput":
                m = re.search(r",(\d+)\)", sp.text or "")
                if m:
                    pcts.append(int(m.group(1)))
        for ip in e.findall("intProp"):
            if ip.get("name") == "ThroughputController.style" and ip.text != "1":
                err(f"ThroughputController '{e.get('testname')}' is not in Percent Executions mode (style={ip.text})")
if pcts:
    if sum(pcts) != 100:
        err(f"Weighted mix defaults total {sum(pcts)}%, expected 100% (got {pcts})")
    else:
        note(f"Weighted mix defaults total 100% {pcts}")

# ------------------------------------------ 5. JSR223 external script files
missing_scripts = []
for e in elements:
    if e.get("testclass", "").startswith("JSR223"):
        fn = None
        cache = None
        lang = None
        for sp in e.findall("stringProp"):
            if sp.get("name") == "filename":
                fn = (sp.text or "").strip()
            if sp.get("name") == "cacheKey":
                cache = (sp.text or "").strip()
            if sp.get("name") == "scriptLanguage":
                lang = (sp.text or "").strip()
        if lang != "groovy":
            err(f"JSR223 '{e.get('testname')}' language is '{lang}', must be groovy")
        if cache != "true":
            warn(f"JSR223 '{e.get('testname')}' has cacheKey != true — slow at 200 VUs")
        if fn:
            full = os.path.join(ROOT, fn.replace("/", os.sep))
            if not os.path.isfile(full):
                missing_scripts.append(fn)
for m in missing_scripts:
    err(f"JSR223 references missing script file: {m}")

# --------------------------------------------- 6. hardcoding / property audit
raw = open(JMX, encoding="utf-8").read()

# every __P(...) reference should have a default AND a documented property
refs = re.findall(r"__P\(([A-Za-z0-9_]+)\s*(,([^)]*))?\)", raw)
prop_names = set()
for line in open(PROPS, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        prop_names.add(line.split("=", 1)[0].strip())

seen = set()
for name, has_default, _dv in refs:
    if name in seen:
        continue
    seen.add(name)
    if not has_default:
        err(f"__P({name}) has no default value — run breaks if the property is absent")
    if name not in prop_names:
        warn(f"__P({name}) is not documented in config/user.properties")
note(f"{len(seen)} distinct properties referenced by the JMX; {len(prop_names)} defined in user.properties")

# hardcoded hosts / tokens
for pat, msg in [
    (r"https?://(?!localhost|influxdb|archive\.apache)", "hardcoded absolute URL"),
    (r"Bearer [A-Za-z0-9\-_.]{12,}", "hardcoded bearer token"),
]:
    for m in re.finditer(pat, raw):
        line = raw[:m.start()].count("\n") + 1
        snippet = raw[m.start():m.start() + 60].replace("\n", " ")
        err(f"Possible {msg} at JMX line {line}: {snippet}")

# --------------------------------------------------------- 7. GUI listeners off
for e in elements:
    if e.get("testclass") == "ResultCollector" and e.get("enabled") == "true":
        err(f"GUI listener '{e.get('testname')}' is ENABLED — cripples throughput (brief pitfall)")
note("GUI listeners: " + ", ".join(
    f"{e.get('testname')}={e.get('enabled')}"
    for e in elements if e.get("testclass") == "ResultCollector") or "none")

# ---------------------------------------------- 8. spike timer safety default
for e in elements:
    if e.get("testclass") == "SyncTimer":
        for sp in e.findall("stringProp"):
            if sp.get("name") == "groupSize":
                m = re.search(r",(\d+)\)", sp.text or "")
                if m and int(m.group(1)) > 1:
                    err("SyncTimer default groupSize > 1 — baseline/peak runs would deadlock")
sync_default = None
for line in open(PROPS, encoding="utf-8"):
    if line.strip().startswith("sync_group_size="):
        sync_default = line.strip().split("=", 1)[1]
if sync_default != "1":
    err(f"user.properties sync_group_size={sync_default}, must be 1 for non-spike runs")
else:
    note("SyncTimer is a no-op by default (sync_group_size=1) — correct")

# ------------------------------------------------------------- 9. CSV test data
csv_path = os.path.join(ROOT, "data", "logins.csv")
with open(csv_path, encoding="utf-8-sig") as f:
    rows = list(csv.reader(f))
header, data = rows[0], rows[1:]
if header != ["username", "password"]:
    err(f"logins.csv header is {header}, JMX expects username,password")
if len(data) < 100:
    err(f"logins.csv has {len(data)} rows — brief requires >= 100")
else:
    note(f"logins.csv: {len(data)} rows, header {header}")
real_looking = [r[0] for r in data if not r[0].endswith((".invalid", ".example", ".test"))]
if real_looking:
    err(f"logins.csv contains {len(real_looking)} non-reserved-domain accounts "
        f"(e.g. {real_looking[0]}) — confirm these are synthetic staging accounts")
else:
    note("logins.csv uses only reserved .invalid domains — no real credentials present")

# --------------------------------------------- 10. CSV config sanity in the JMX
for e in elements:
    if e.get("testclass") == "CSVDataSet":
        vals = {sp.get("name"): (sp.text or "") for sp in e.findall("stringProp")}
        bools = {bp.get("name"): (bp.text or "") for bp in e.findall("boolProp")}
        if vals.get("variableNames", "") == "" and bools.get("ignoreFirstLine") == "true":
            err("CSV: variableNames empty AND ignoreFirstLine=true — header row would be skipped and unnamed")
        if vals.get("shareMode") != "shareMode.all":
            warn(f"CSV shareMode is {vals.get('shareMode')} — brief expects All threads")
        if bools.get("recycle") != "true" or bools.get("stopThread") != "false":
            warn("CSV recycle/stopThread not set to true/false — threads may die at EOF")

# ------------------------------------------------------- 11. groovy referenced files
gdir = os.path.join(ROOT, "scripts", "groovy")
for fn in sorted(os.listdir(gdir)):
    src = open(os.path.join(gdir, fn), encoding="utf-8").read()
    if src.count("{") != src.count("}"):
        err(f"{fn}: unbalanced braces ({src.count('{')} open, {src.count('}')} close)")
    if src.count("(") != src.count(")"):
        warn(f"{fn}: unbalanced parens — check manually")
    # no secrets committed
    if re.search(r"(api[_-]?key|password|secret)\s*=\s*[\"'][A-Za-z0-9]{20,}", src, re.I):
        err(f"{fn}: looks like a committed secret")
note(f"groovy scripts checked: {len(os.listdir(gdir))}")

# ---------------------------------------------------------- 12. YAML / compose
try:
    import yaml
    for rel in ["monitoring/docker-compose.yml",
                "monitoring/provisioning/datasources/influxdb.yml",
                ".github/workflows/perf.yml"]:
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        with open(p, encoding="utf-8") as f:
            yaml.safe_load(f)
        note(f"YAML OK: {rel}")
except ImportError:
    warn("pyyaml not installed — YAML files not parsed")
except Exception as e:
    err(f"YAML parse failure: {e}")

# ------------------------------------------- 13. all 17 concepts accounted for
# The Quick Guide and the teaching deck number the same 17 concepts differently.
# Node labels carry BOTH so the plan reads correctly against either document.
CONCEPTS = {
    1:  ("Weighted Mix / Workload Modeling", 1),
    2:  ("Correlation",                      2),
    3:  ("Parameterization",                 3),
    4:  ("Request Chaining",                 4),
    5:  ("Profiling & Analysis",             5),
    6:  ("JSR223 Scripting",                 6),
    7:  ("Distributed Load",                12),
    8:  ("Monitoring & Reporting",          13),
    9:  ("Order Controllers",               14),
    10: ("Dynamic Auth Headers",             7),
    11: ("JDBC Validation",                  8),
    12: ("Assertions",                       9),
    13: ("Custom Timers",                   10),
    14: ("Config Management",               15),
    15: ("Error Handling & Retry",          11),
    16: ("CI/CD Integration",               16),
    17: ("AI Self-Healing",                 17),
}
# 7 and 16 live outside the .jmx by nature (worker topology / pipeline).
EXTERNAL = {
    7:  os.path.join(ROOT, "run", "distributed.ps1"),
    16: os.path.join(ROOT, ".github", "workflows", "perf.yml"),
}
labelled = set(int(m) for m in re.findall(r"CONCEPT (\d+) \(deck", raw))
for n, (name, deck) in sorted(CONCEPTS.items()):
    if n in labelled:
        continue
    path = EXTERNAL.get(n)
    if path and os.path.isfile(path):
        note(f"concept {n} (deck {deck}) {name}: implemented outside the .jmx -> "
             f"{os.path.relpath(path, ROOT)}")
    else:
        err(f"concept {n} (deck {deck}) '{name}' is not labelled anywhere")
note(f"concepts labelled inside the .jmx: {len(labelled)}/17 "
     f"(+{len(EXTERNAL)} implemented outside it)")

# also check the dual numbering is actually correct where it appears
for m in re.finditer(r"CONCEPT (\d+) \(deck (\d+)\)", raw):
    guide, deck = int(m.group(1)), int(m.group(2))
    if guide not in CONCEPTS:
        err(f"unknown concept number {guide}")
    elif CONCEPTS[guide][1] != deck:
        err(f"concept {guide} labelled 'deck {deck}' but the deck numbers it "
            f"{CONCEPTS[guide][1]}")

# ------------------------------------------------ 14. distributed readiness
dist = os.path.join(ROOT, "run", "distributed.ps1")
if os.path.isfile(dist):
    d = open(dist, encoding="utf-8").read()
    # -J does NOT reach remote workers; only -G does. This is the single most
    # common distributed defect and it fails silently.
    local_only = re.findall(r'"-J([a-z_]+)=', d)
    if local_only:
        err(f"distributed.ps1 passes {local_only} with -J — these will NOT reach "
            f"the workers. Use -G for anything the workers must see.")
    if "-G" not in d:
        err("distributed.ps1 sends no -G properties — workers will use their own defaults")
    else:
        note("distributed.ps1 propagates properties with -G (reaches workers)")
    if "server.rmi.ssl.disable" not in d:
        warn("distributed.ps1 does not set server.rmi.ssl.disable — RMI handshake may fail")
    if "csvfile" in d and "-Gcsvfile" in d:
        err("distributed.ps1 broadcasts csvfile with -G — every worker would get the "
            "SAME slice. Set it locally per worker instead.")

part = os.path.join(ROOT, "scripts", "partition_csv.py")
if os.path.isfile(part):
    note("CSV partitioner present (workers get disjoint accounts)")
else:
    err("no scripts/partition_csv.py — workers would replay identical logins")

wstart = os.path.join(ROOT, "run", "worker-start.ps1")
if os.path.isfile(wstart):
    note("worker launcher present with parity checks")
else:
    err("no run/worker-start.ps1 — worker setup is undocumented and error-prone")

# ---------------------------------------- 15. bugs found by executing the plan
# Each check below corresponds to a defect that static inspection missed and
# only a real run exposed. They are guards against regression, not theory.

# (a) A comma inside a JMeter function tears the inner script in half, because
#     JMeter splits function ARGUMENTS on commas before Groovy ever sees them.
#     props.getProperty("max_retries","3") silently broke both retry caps.
for m in re.finditer(r"\$\{__groovy\((.*?)\)\}", raw, re.S):
    body = m.group(1)
    # strip bracketed groups, then look for a bare comma at argument level
    depth, bare = 0, False
    for ch in body:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            bare = True
    if bare or re.search(r'getProperty\([^)]*,', body):
        err("__groovy() contains a comma inside its argument - JMeter splits "
            "function args on commas and the script will not compile. "
            "Use (props.get(\"x\") ?: \"default\") instead of getProperty(\"x\",\"default\")")

# (b) A variable in a SAMPLER NAME fragments the results: every runtime value
#     becomes its own row in the statistics table and its own Grafana series,
#     making per-request percentiles meaningless.
for m in re.finditer(r'<(HTTPSamplerProxy|JDBCSampler|JSR223Sampler)[^>]*testname="([^"]*)"', raw):
    name = m.group(2)
    if "${" in name and "__P(" not in name:
        err(f"sampler name '{name}' contains a runtime variable - this fragments "
            f"the results table and Grafana series. Remove it from the label.")

# (c) Response Assertion test_type: 2=Contains(regex), 16=Substring(literal).
#     Substring is case-sensitive, so a renamed field defeats the assertion even
#     when self-healing recovered the value.
for m in re.finditer(r'<ResponseAssertion.*?</ResponseAssertion>', raw, re.S):
    blk = m.group(0)
    tt = re.search(r'name="Assertion.test_type">(\d+)<', blk)
    if tt and tt.group(1) == "16":
        warn("Response Assertion uses test_type 16 (literal, case-sensitive "
             "Substring). Prefer 2 (Contains, regex) so a field rename does not "
             "defeat the assertion.")

# (d) ConstantThroughputTimer throughput must not be a doubleProp holding a
#     ${__P()} expression - the plan becomes unloadable.
if re.search(r"<doubleProp>\s*<name>throughput</name>\s*<value>\$\{", raw):
    err("ConstantThroughputTimer throughput is a doubleProp containing a "
        "property expression - JMeter parses it as a literal Double at load "
        "time and the .jmx will not open. Use a stringProp.")

# (e) Test data lifecycle: a suite that creates rows must clean them up.
if "PostThreadGroup" not in raw:
    err("no tearDown Thread Group - data created by each run is never cleaned "
        "up, so repeated peak runs grow the table and fake a regression")
else:
    note("tearDown Thread Group present (test data lifecycle)")

# (f) Server-side observability
if "path_metrics" in raw:
    note("server-side metrics polling present (bottleneck analysis has CPU/mem)")
else:
    warn("no server-side metrics - bottleneck analysis will be client-side only")

# ------------------------------------------------------------------- report
print("=" * 72)
print("STATIC VALIDATION — no network, no execution")
print("=" * 72)
for n in notes:
    print(f"  ok   {n}")
print()
for w in warnings:
    print(f"  WARN {w}")
print()
for e_ in errors:
    print(f"  FAIL {e_}")
print()
print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
sys.exit(1 if errors else 0)
