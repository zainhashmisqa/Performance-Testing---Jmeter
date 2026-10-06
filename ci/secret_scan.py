#!/usr/bin/env python3
"""
Secret scanner — prevents accidental credential leaks before push.

Scans all tracked files for patterns that look like committed secrets:
API keys, tokens, passwords, connection strings with embedded credentials.

Exit 0 = clean, 1 = potential secrets found.
Usage:  python ci/secret_scan.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[A-Za-z0-9\-_]{20,}', "API key"),
    (r'(?i)(secret|password|passwd|pwd)\s*[=:]\s*["\']?[A-Za-z0-9\-_!@#$%^&*]{8,}', "Password/secret"),
    (r'(?i)bearer\s+[A-Za-z0-9\-_.]{20,}', "Bearer token"),
    (r'(?i)token\s*[=:]\s*["\']?[a-f0-9]{32,}', "Token hash"),
    (r'jdbc:[a-z]+://[^/]+/[^?]*\?.*password=[^&\s]+', "JDBC URL with password"),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*[A-Za-z0-9/+=]{30,}', "AWS secret"),
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', "Private key"),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub PAT"),
    (r'sk-[A-Za-z0-9]{32,}', "OpenAI/Stripe secret key"),
]

SAFE_PATTERNS = [
    r'FILL_ME_IN',
    r'azm-test-secret-not-a-real-key',
    r'\$\{',
    r'__P\(',
    r'example\.com',
    r'localhost',
    r'placeholder',
    r'changeme',
    r'your[-_]',
]

SKIP_DIRS = {'.git', 'node_modules', 'results', '__pycache__', '.venv', 'venv'}
SKIP_EXTS = {'.jar', '.class', '.exe', '.dll', '.png', '.jpg', '.gif', '.ico',
             '.zip', '.gz', '.jtl', '.csv', '.jks'}
BINARY_MARKER = {'.pdf', '.woff', '.woff2', '.ttf', '.eot'}

findings = []


def is_safe(line):
    return any(re.search(p, line) for p in SAFE_PATTERNS)


for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in filenames:
        ext = os.path.splitext(fn)[1].lower()
        if ext in SKIP_EXTS or ext in BINARY_MARKER:
            continue
        fpath = os.path.join(dirpath, fn)
        rel = os.path.relpath(fpath, ROOT)
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if is_safe(line):
                        continue
                    for pat, label in PATTERNS:
                        if re.search(pat, line):
                            snippet = line.strip()[:80]
                            findings.append((rel, lineno, label, snippet))
        except (OSError, UnicodeDecodeError):
            pass

print("=" * 60)
print("SECRET SCAN")
print("=" * 60)
print(f"  Scanned from: {ROOT}")
print()

if findings:
    print(f"  {len(findings)} potential secret(s) found:\n")
    for rel, lineno, label, snippet in findings:
        print(f"    {rel}:{lineno}")
        print(f"      Type: {label}")
        print(f"      Line: {snippet}")
        print()
    print("  Result: FAILED — review and remove or externalize these values")
    sys.exit(1)
else:
    print("  No committed secrets detected.")
    print("  Result: PASSED")
    sys.exit(0)


if __name__ == "__main__":
    pass
