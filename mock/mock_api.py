#!/usr/bin/env python3
"""
Local mock of the SBA Academy API. LOOPBACK ONLY.

WHY THIS EXISTS
---------------
A performance script that has never executed is a design document. This mock
implements the same contract the real app is expected to expose, so the whole
plan - correlation, chaining, assertions, retry, pacing, teardown, monitoring -
can be proven to work before anyone points it at a shared environment. It binds
to 127.0.0.1 only and talks to nothing.

CONTRACT PARITY
---------------
The routes below mirror the paths in config/user.properties exactly. If a path
property changes, the matching route here must change with it, otherwise a local
run reports failures that are an artefact of the mock rather than of the script.
Run scripts/check_mock_parity.py to verify the two sides still agree.

It deliberately misbehaves in controlled ways so the framework's defences can be
demonstrated rather than asserted:
  * CHECKOUT_FAIL_RATE   -> transient failures, so the retry loop has real work
  * CHECKOUT_LATENCY_MS  -> the signed certificate call is the slowest step, so
                            profiling finds a genuine bottleneck instead of noise
  * ORDER_COMMIT_LAG_MS  -> enrollments commit asynchronously, so the async-safe
                            DB verification is exercised
  * TOKEN_FIELD          -> rename the token field to prove self-healing

Run:  python mock/mock_api.py --port 8080
"""
import argparse
import json
import os
import random
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CFG = {
    "token_field":        os.getenv("TOKEN_FIELD", "token"),
    "checkout_fail_rate": float(os.getenv("CHECKOUT_FAIL_RATE", "0.12")),
    "checkout_latency":   int(os.getenv("CHECKOUT_LATENCY_MS", "220")),
    "browse_latency":     int(os.getenv("BROWSE_LATENCY_MS", "35")),
    "cart_latency":       int(os.getenv("CART_LATENCY_MS", "70")),
    "commit_lag":         int(os.getenv("ORDER_COMMIT_LAG_MS", "150")),
}

DB_PATH = os.getenv("MOCK_DB", "mock/mock.db")
_lock = threading.Lock()
_stats = {"requests": 0, "checkouts": 0, "failures": 0, "active": 0}

# The assertions pin currency and tax_percent, so these must match the defaults
# in user.properties (expected_currency=SAR, expected_tax_percent=15).
CURRENCY = "SAR"
TAX_PERCENT = 15

# "General" is the expected_category the categories assertion looks for.
CATEGORIES = [
    {"id": 1, "name": "General",     "slug": "general",     "course_count": 14},
    {"id": 2, "name": "Engineering", "slug": "engineering", "course_count": 11},
    {"id": 3, "name": "Business",    "slug": "business",    "course_count": 9},
    {"id": 4, "name": "Design",      "slug": "design",      "course_count": 6},
]

COURSES = []
for i in range(1, 41):
    cat = CATEGORIES[i % len(CATEGORIES)]
    COURSES.append({
        "id": i,
        "slug": "sba-course-%03d" % i,
        "title": "SBA Course %03d" % i,
        "price": 49 + (i % 7) * 10,
        "currency": CURRENCY,
        "tax_percent": TAX_PERCENT,
        "course_type": "self_paced" if i % 2 else "instructor_led",
        "category": cat["slug"],
        "availability": "open",
        "language": "en",
        "difficulty": ["beginner", "intermediate", "advanced"][i % 3],
    })


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS student_courseenrollment ("
                  "id TEXT PRIMARY KEY, username TEXT, course_id TEXT, "
                  "status TEXT, created_at REAL)")
        c.commit()


def seed_enrollments(n=25):
    """The read flows assert on an existing enrollment, so the table cannot start
    empty or every first iteration fails for a reason the script is not at fault
    for."""
    with db() as c:
        for i in range(1, n + 1):
            course = COURSES[i % len(COURSES)]
            c.execute("INSERT OR REPLACE INTO student_courseenrollment VALUES (?,?,?,?,?)",
                      ("ENR-%06d" % i, "azm_test_%03d" % i, course["slug"],
                       "confirmed", time.time()))
        c.commit()


def commit_enrollment_async(enroll_id, username, course_slug, lag_ms):
    """Write the enrollment row AFTER a delay - the real-world async commit that
    makes a naive immediate DB assertion report a false failure."""
    def _w():
        time.sleep(lag_ms / 1000.0)
        try:
            with db() as c:
                c.execute("INSERT OR REPLACE INTO student_courseenrollment VALUES (?,?,?,?,?)",
                          (enroll_id, username, course_slug, "confirmed", time.time()))
                c.commit()
        except Exception:
            pass
    threading.Thread(target=_w, daemon=True).start()


def enrollment_rows(limit=20):
    with db() as c:
        rows = c.execute(
            "SELECT id, username, course_id, status FROM student_courseenrollment "
            "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        slug = r[2]
        course = next((x for x in COURSES if x["slug"] == slug), None)
        out.append({
            "id": r[0],
            "enrollment_id": r[0],
            "username": r[1],
            "course_slug": slug,
            "course_title": course["title"] if course else slug,
            "status": r[3],
        })
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass  # keep the console clean under load

    def _send(self, code, payload, delay_ms=0):
        if delay_ms:
            time.sleep(delay_ms / 1000.0)
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def _jitter(self, base):
        return max(1, int(random.gauss(base, base * 0.25)))

    def _count(self, key):
        with _lock:
            _stats[key] = _stats.get(key, 0) + 1

    # ---------------------------------------------------------------- GET ----
    def do_GET(self):
        self._count("requests")
        with _lock:
            _stats["active"] += 1
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            # --- server-side metrics for the monitor thread group -------------
            if path in ("/heartbeat/", "/heartbeat", "/internal/metrics"):
                with _lock:
                    s = dict(_stats)
                try:
                    with db() as c:
                        rows = c.execute(
                            "SELECT COUNT(*) FROM student_courseenrollment").fetchone()[0]
                except Exception:
                    rows = -1
                return self._send(200, {
                    "cpu_percent": round(min(99.0, 12 + s["active"] * 2.4), 2),
                    "memory_mb": round(320 + s["requests"] * 0.004, 1),
                    "active_requests": s["active"],
                    "total_requests": s["requests"],
                    "checkouts": s["checkouts"],
                    "failures": s["failures"],
                    "enrollment_rows": rows,
                    "status": "ok",
                })

            if path == "/internal/orders/count":
                with db() as c:
                    n = c.execute(
                        "SELECT COUNT(*) FROM student_courseenrollment").fetchone()[0]
                return self._send(200, {"count": n, "status": "ok"})

            # --- categories ---------------------------------------------------
            if path.rstrip("/") == "/api/catalog/categories":
                return self._send(200, CATEGORIES, self._jitter(CFG["browse_latency"]))

            # --- course catalog: list (filtered) and detail --------------------
            if path.startswith("/api/catalog/courses"):
                tail = path[len("/api/catalog/courses"):].strip("/")

                # Detail: /api/catalog/courses/<slug>/
                if tail:
                    match = next((c for c in COURSES if c["slug"] == tail), None)
                    if not match:
                        return self._send(404, {"status": "error",
                                                "detail": "no such course"})
                    out = dict(match)
                    out["status"] = "ok"
                    out["description"] = "Full description for %s" % match["title"]
                    return self._send(200, out, self._jitter(CFG["browse_latency"]))

                # List, honouring the filters the script actually sends so the
                # chained category/search values visibly change the result set.
                results = COURSES
                cat = (qs.get("category") or [""])[0]
                if cat and not cat.startswith("NO_"):
                    narrowed = [c for c in results if c["category"] == cat]
                    # An unknown slug must not empty the page, or the downstream
                    # detail call has nothing to chain from.
                    results = narrowed or results
                search = (qs.get("search") or [""])[0]
                if search and not search.startswith("NO_"):
                    narrowed = [c for c in results
                                if search.lower() in c["slug"].lower()
                                or search.lower() in c["title"].lower()]
                    results = narrowed or results

                page = results[:10]
                return self._send(200, {"count": len(results), "results": page,
                                        "status": "ok"},
                                  self._jitter(CFG["browse_latency"]))

            # --- enrollments ("my courses") -----------------------------------
            if path.rstrip("/") == "/api/enrollment/my-courses":
                rows = enrollment_rows()
                if not rows:
                    seed_enrollments()
                    rows = enrollment_rows()
                course = (qs.get("course") or [""])[0]
                if course and not course.startswith("NO_"):
                    narrowed = [r for r in rows if r["course_slug"] == course]
                    rows = narrowed or rows
                return self._send(200, rows, self._jitter(CFG["cart_latency"]))

            # --- certificates (the signed, retryable, slowest step) -----------
            if path.rstrip("/") == "/api/certificates":
                self._count("checkouts")

                # Concept 15 proof hook: the preprocessor rewrites the path to
                # .../FORCED_FAILURE/ for the first attempts.
                if "FORCED_FAILURE" in self.path:
                    self._count("failures")
                    return self._send(500, {"status": "error",
                                            "detail": "forced failure"})

                if random.random() < CFG["checkout_fail_rate"]:
                    self._count("failures")
                    # A 200 carrying an error body - passes a naive status-code
                    # check and is caught only by a body assertion.
                    return self._send(200, {"status": "declined",
                                            "detail": "certificate service timeout"},
                                      self._jitter(CFG["checkout_latency"]))

                course = (qs.get("course") or [""])[0]
                if not course or course.startswith("NO_"):
                    course = random.choice(COURSES)["slug"]
                title = next((c["title"] for c in COURSES if c["slug"] == course), course)

                enroll_id = "ENR-%06d" % random.randint(1, 999999)
                commit_enrollment_async(enroll_id, "azm_test", course, CFG["commit_lag"])

                return self._send(200, [{
                    "id": enroll_id,
                    "course_slug": course,
                    "course_title": title,
                    "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "status": "confirmed",
                }], self._jitter(CFG["checkout_latency"]))

            # --- profile -------------------------------------------------------
            if path.rstrip("/") == "/api/accounts/me":
                return self._send(200, {
                    "id": 1001,
                    "username": "azm_test_001",
                    "email": "azm_test_001@azm-perf.invalid",
                    "full_name": "AZM Test User",
                    "status": "active",
                }, self._jitter(CFG["browse_latency"]))

            return self._send(404, {"status": "error", "detail": "not found"})
        finally:
            with _lock:
                _stats["active"] -= 1

    # --------------------------------------------------------------- POST ----
    def do_POST(self):
        self._count("requests")
        with _lock:
            _stats["active"] += 1
        try:
            path = urlparse(self.path).path
            body = self._body()

            if path.rstrip("/") == "/api/accounts/login":
                user = body.get("username") or body.get("email") or "anonymous"
                alphabet = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                            "abcdefghijklmnopqrstuvwxyz0123456789")
                token = "eyJ" + "".join(random.choices(alphabet, k=40))
                # The field NAME is configurable - rename it to prove self-healing.
                return self._send(200, {
                    CFG["token_field"]: token,
                    "user": {"id": 1001, "username": user,
                             "email": "%s@azm-perf.invalid" % user},
                    "status": "ok",
                }, self._jitter(60))

            return self._send(404, {"status": "error", "detail": "not found"})
        finally:
            with _lock:
                _stats["active"] -= 1

    # ------------------------------------------------------------- DELETE ----
    def do_DELETE(self):
        """Used by the tearDown Thread Group to remove rows this run created,
        so repeated runs do not grow the table and fake a regression."""
        self._count("requests")
        if urlparse(self.path).path.rstrip("/") == "/internal/orders":
            with db() as c:
                n = c.execute(
                    "SELECT COUNT(*) FROM student_courseenrollment").fetchone()[0]
                c.execute("DELETE FROM student_courseenrollment")
                c.commit()
            return self._send(200, {"deleted": n, "status": "ok"})
        return self._send(404, {"status": "error"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--reset", action="store_true", help="drop existing rows on start")
    args = ap.parse_args()

    init_db()
    if args.reset:
        with db() as c:
            c.execute("DELETE FROM student_courseenrollment")
            c.commit()
    seed_enrollments()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True
    print("Mock SBA Academy API on http://127.0.0.1:%d  (loopback only)" % args.port)
    print("  token field       : %s" % CFG["token_field"])
    print("  checkout fail rate: %s" % CFG["checkout_fail_rate"])
    print("  checkout latency  : %dms" % CFG["checkout_latency"])
    print("  commit lag        : %dms" % CFG["commit_lag"])
    srv.serve_forever()


if __name__ == "__main__":
    main()
