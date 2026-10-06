#!/usr/bin/env python3
"""
Local mock of the AZM/SBA course-commerce API. LOOPBACK ONLY.

WHY THIS EXISTS
---------------
A performance script that has never executed is a design document. This mock
implements the same contract the real app is expected to expose, so the whole
plan - correlation, chaining, assertions, retry, pacing, teardown, monitoring -
can be proven to work before anyone points it at a shared environment. It binds
to 127.0.0.1 only and talks to nothing.

It deliberately misbehaves in controlled ways so the framework's defences can be
demonstrated rather than asserted:
  * CHECKOUT_FAIL_RATE   -> transient failures, so the retry loop has real work
  * CHECKOUT_LATENCY_MS  -> checkout is the slowest step, so profiling finds a
                            genuine bottleneck instead of noise
  * ORDER_COMMIT_LAG_MS  -> orders commit asynchronously, so the async-safe DB
                            verification is exercised
  * TOKEN_FIELD          -> rename the token field to prove self-healing

Run:  python mock/mock_api.py --port 8080
"""
import argparse
import json
import os
import random
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

COURSES = [{"id": "course-v1:AZM+SBA%03d+2026" % i, "name": "Course %03d" % i,
            "price": 49 + (i % 7) * 10} for i in range(1, 41)]


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


def commit_order_async(order_id, username, course_id, lag_ms):
    """Write the enrollment row AFTER a delay - the real-world async commit that
    makes a naive immediate DB assertion report a false failure."""
    def _w():
        time.sleep(lag_ms / 1000.0)
        try:
            with db() as c:
                c.execute("INSERT OR REPLACE INTO student_courseenrollment VALUES (?,?,?,?,?)",
                          (order_id, username, course_id, "confirmed", time.time()))
                c.commit()
        except Exception:
            pass
    threading.Thread(target=_w, daemon=True).start()


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

    def do_GET(self):
        self._count("requests")
        path = self.path.split("?")[0]

        if path == "/internal/metrics":
            # Stands in for server-side APM (CPU/memory/queue depth). The real
            # target exposes something equivalent; the monitoring thread group
            # polls whatever path is configured.
            with _lock:
                s = dict(_stats)
            try:
                with db() as c:
                    rows = c.execute("SELECT COUNT(*) FROM student_courseenrollment").fetchone()[0]
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
                n = c.execute("SELECT COUNT(*) FROM student_courseenrollment").fetchone()[0]
            return self._send(200, {"count": n, "status": "ok"})

        if path.startswith("/api/courses/v1/courses/"):
            cid = path[len("/api/courses/v1/courses/"):].strip("/")
            if cid:
                match = None
                for c in COURSES:
                    if c["id"] == cid:
                        match = c
                        break
                if not match:
                    return self._send(404, {"status": "error", "detail": "no such course"})
                out = dict(match)
                out["status"] = "ok"
                return self._send(200, out, self._jitter(CFG["browse_latency"]))
            page = random.sample(COURSES, 10)
            return self._send(200, {"results": page, "count": len(COURSES), "status": "ok"},
                              self._jitter(CFG["browse_latency"]))

        if re.match(r"^/api/commerce/v1/orders/", path):
            oid = path.rstrip("/").split("/")[-1]
            with db() as c:
                row = c.execute("SELECT status FROM student_courseenrollment WHERE id=?",
                                (oid,)).fetchone()
            # Reports confirmed immediately even if the row has not committed -
            # exactly the API-says-yes / DB-says-nothing case Concept 11 catches.
            return self._send(200, {"order_number": oid,
                                    "status": row[0] if row else "confirmed"},
                              self._jitter(40))

        return self._send(404, {"status": "error", "detail": "not found"})

    def do_POST(self):
        self._count("requests")
        with _lock:
            _stats["active"] += 1
        try:
            path = self.path.split("?")[0]
            body = self._body()

            if path == "/api/user/v1/account/login_session/":
                user = body.get("email") or "anonymous"
                alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                token = "eyJ" + "".join(random.choices(alphabet, k=40))
                # The field NAME is configurable - rename it to prove self-healing.
                return self._send(200, {CFG["token_field"]: token,
                                        "user": user, "status": "ok"},
                                  self._jitter(60))

            if path == "/api/commerce/v1/baskets/":
                if not body.get("course_id"):
                    return self._send(400, {"status": "error", "detail": "course_id required"})
                return self._send(200, {"id": "basket-%d" % random.randint(100000, 999999),
                                        "course_id": body["course_id"], "status": "ok"},
                                  self._jitter(CFG["cart_latency"]))

            if path == "/api/commerce/v1/checkout/":
                self._count("checkouts")
                basket = body.get("basket_id", "")
                if basket == "FORCED_FAILURE_CART":
                    self._count("failures")
                    return self._send(500, {"status": "error", "detail": "forced failure"})
                if random.random() < CFG["checkout_fail_rate"]:
                    self._count("failures")
                    # A 200 carrying an error body - passes a naive status-code
                    # check and is caught only by a body assertion.
                    return self._send(200, {"status": "declined",
                                            "detail": "payment gateway timeout"},
                                      self._jitter(CFG["checkout_latency"]))
                oid = "ORD-%d" % random.randint(10**9, 10**10 - 1)
                commit_order_async(oid, body.get("user", "unknown"),
                                   body.get("course_id", "unknown"), CFG["commit_lag"])
                return self._send(200, {"order_number": oid, "status": "confirmed",
                                        "basket_id": basket},
                                  self._jitter(CFG["checkout_latency"]))

            return self._send(404, {"status": "error", "detail": "not found"})
        finally:
            with _lock:
                _stats["active"] -= 1

    def do_DELETE(self):
        """Used by the tearDown Thread Group to remove rows this run created,
        so repeated runs do not grow the table and fake a checkout regression."""
        self._count("requests")
        if self.path.split("?")[0] == "/internal/orders":
            with db() as c:
                n = c.execute("SELECT COUNT(*) FROM student_courseenrollment").fetchone()[0]
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

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True
    print("Mock AZM/SBA API on http://127.0.0.1:%d  (loopback only)" % args.port)
    print("  token field       : %s" % CFG["token_field"])
    print("  checkout fail rate: %s" % CFG["checkout_fail_rate"])
    print("  checkout latency  : %dms" % CFG["checkout_latency"])
    print("  order commit lag  : %dms" % CFG["commit_lag"])
    srv.serve_forever()


if __name__ == "__main__":
    main()
