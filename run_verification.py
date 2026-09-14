#!/usr/bin/env python3
"""
run_verification.py — Execute a verification bundle and update the status ledger.

Usage:
  python3 run_verification.py <bundle.py> [--source path] [--ledger verification_status.json]

Exit codes: 0=TEST_VERIFIED, 1=VERIFICATION_FAILED, 2=missing bundle
"""

import json, os, subprocess, sys, time, hashlib

def env_hash():
    h = hashlib.sha256()
    for k in ("PYTHON_VERSION", "GITHUB_SHA", "USER"):
        h.update(f"{k}={os.environ.get(k, '')}".encode())
    return h.hexdigest()[:12]

def parse_output(stdout, stderr):
    checks = []
    for line in stdout.splitlines():
        line_s = line.strip()
        if line_s.startswith("[PASS]"):
            checks.append({"name": line_s[6:].strip(), "passed": True})
        elif line_s.startswith("[FAIL]"):
            checks.append({"name": line_s[6:].strip(), "passed": False})
    result = {"passed": None, "total": None}
    for line in stdout.splitlines():
        if "RESULT:" in line:
            try:
                body = line.split("RESULT:")[1].strip()
                nums, _ = body.split(" ", 1)
                p, t = nums.split("/")
                result = {"passed": int(p), "total": int(t)}
            except (ValueError, IndexError):
                pass
    return {"checks": checks, "result": result,
            "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:]}

def main():
    if len(sys.argv) < 2:
        print("Usage: run_verification.py <bundle.py> [--source P] [--ledger F]")
        return 2
    bundle = sys.argv[1]
    source = None
    ledger_path = "verification_status.json"
    if "--source" in sys.argv:
        source = sys.argv[sys.argv.index("--source") + 1]
    if "--ledger" in sys.argv:
        ledger_path = sys.argv[sys.argv.index("--ledger") + 1]

    if not os.path.exists(bundle):
        print(f"NO_BUNDLE {bundle}")
        return 2

    proc = subprocess.run([sys.executable, bundle],
                          capture_output=True, text=True, timeout=600)
    parsed = parse_output(proc.stdout, proc.stderr)

    n, t = parsed["result"]["passed"], parsed["result"]["total"]
    checks_ok = all(c["passed"] for c in parsed["checks"])
    verified = (proc.returncode == 0) and (n is not None and n == t) and checks_ok
    status = "TEST_VERIFIED" if verified else "VERIFICATION_FAILED"

    ledger = {}
    if os.path.exists(ledger_path):
        try:
            ledger = json.load(open(ledger_path))
        except json.JSONDecodeError:
            ledger = {}
    entry = {
        "artifact": os.path.basename(source or bundle),
        "bundle": os.path.basename(bundle),
        "status": status,
        "exit_code": proc.returncode,
        "checks_passed": n, "checks_total": t,
        "failed_checks": [c["name"] for c in parsed["checks"] if not c["passed"]],
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env_hash": env_hash(),
    }
    ledger.setdefault("runs", []).append(entry)
    ledger["latest"] = entry
    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2)

    print(f"STATUS: {status}  ({n}/{t} checks, exit {proc.returncode})")
    if not verified and parsed["failed_checks"]:
        print("FAILED:", ", ".join(parsed["failed_checks"]))
    print("Ledger updated:", ledger_path)
    return 0 if verified else 1

if __name__ == "__main__":
    sys.exit(main())
