#!/usr/bin/env python3
"""
VERIFICATION BUNDLE FOR training_factory.py (v1 - contract-pinned)
STATUS: DESIGN_ONLY_NOT_EXECUTED

CONTRACTS:
  A. consume_telemetry_produce_manifest(telemetry_path, manifest_path) -> int
       >= 0: records consumed; -1: missing; -2: empty
  B. verify_manifest(manifest_path, telemetry_path) -> bool
       prints matches_manifest=true/false; always exits 0

CANONICALIZATION: json.dumps(obj, sort_keys=True, separators=(",",":"))
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REQUIRED_FILES = ["training_factory.py"]
for f in REQUIRED_FILES:
    if not os.path.exists(f):
        print(f"FATAL: Missing '{f}'")
        sys.exit(1)
print("✓ ENVIRONMENT CHECK PASSED")

checks = []
def check(name, condition, diag=""):
    status = "PASS" if condition else "FAIL"
    checks.append((name, condition))
    print(f"  [{status}] {name}" + (f"  {diag}" if diag else ""))

tmp = tempfile.mkdtemp(prefix="vaeh_tf_")
telem = os.path.join(tmp, "telemetry.jsonl")
manifest = os.path.join(tmp, "manifest.json")
missing_telem = os.path.join(tmp, "NOPE.jsonl")
empty_telem = os.path.join(tmp, "empty.jsonl")
open(empty_telem, "w").close()

try:
    records = [
        {"event_type": "dpo_training_pair", "task_id": "T6", "label": "ARRESTED_TASK"},
        {"event_type": "dpo_training_pair", "task_id": "R1", "label": "ARRESTED_TASK"},
        {"event_type": "dpo_training_pair", "task_id": "T6", "label": "OK"},
    ]
    with open(telem, "w") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"✓ Fixtures: {len(records)} records")

    r1 = subprocess.run([sys.executable, "training_factory.py", "produce",
                         "--telemetry", telem, "--manifest", manifest],
                        capture_output=True, text=True)
    check("produce exits 0", r1.returncode == 0, r1.stderr[:200])

    if os.path.exists(manifest):
        m = json.load(open(manifest))
        required_keys = {"dataset_sha256", "record_count", "records", "produced_at_utc", "telemetry_source"}
        check("manifest has required keys", required_keys.issubset(m.keys()))
        check(f"record_count == {len(records)}", m.get("record_count") == len(records))
    else:
        check("manifest exists", False)
        check("record_count correct", False)

    r2 = subprocess.run([sys.executable, "training_factory.py", "verify",
                         "--manifest", manifest, "--telemetry", telem],
                        capture_output=True, text=True)
    check("verify prints matches_manifest=true", "matches_manifest=true" in r2.stdout)
    check("verify exits 0", r2.returncode == 0)

    m1 = json.load(open(manifest))
    subprocess.run([sys.executable, "training_factory.py", "produce",
                    "--telemetry", telem, "--manifest", manifest],
                   capture_output=True)
    m2 = json.load(open(manifest))
    check("idempotent (dataset_sha256 unchanged)", m1["dataset_sha256"] == m2["dataset_sha256"])

    r3 = subprocess.run([sys.executable, "-c",
                         f"import training_factory; print(training_factory.consume_telemetry_produce_manifest('{missing_telem}', '{os.path.join(tmp, 'm2.json')}'))"],
                        capture_output=True, text=True)
    try:
        rc = int(r3.stdout.strip())
    except ValueError:
        rc = None
    check("missing telemetry → returns -1", rc == -1, f"got {rc!r}")
    check("missing telemetry → ERROR on stderr", "error" in r3.stderr.lower())

    empty_man = os.path.join(tmp, "empty_manifest.json")
    r4 = subprocess.run([sys.executable, "-c",
                         f"import training_factory; print(training_factory.consume_telemetry_produce_manifest('{empty_telem}', '{empty_man}'))"],
                        capture_output=True, text=True)
    try:
        rc_empty = int(r4.stdout.strip())
    except ValueError:
        rc_empty = None
    check("empty telemetry → returns -2", rc_empty == -2, f"got {rc_empty!r}")
    check("empty telemetry → manifest still written", os.path.exists(empty_man))

    with open(telem, "a") as f:
        f.write('{"tampered": true}\n')
    r5 = subprocess.run([sys.executable, "training_factory.py", "verify",
                         "--manifest", manifest, "--telemetry", telem],
                        capture_output=True, text=True)
    check("tampered telemetry → matches_manifest=false", "matches_manifest=false" in r5.stdout)

finally:
    shutil.rmtree(tmp, ignore_errors=True)
    print("✓ Cleanup complete")

passed = sum(1 for _, c in checks if c)
total = len(checks)
print(f"\n{'='*60}")
print(f"RESULT: {passed}/{total} checks passed")
print(f"{'='*60}")

if passed == total:
    print("\nCLASSIFICATION PROMPT:")
    print("  training_factory.py → TEST_VERIFIED (bundle executed locally)")
    sys.exit(0)
else:
    print(f"\nFAILED: {[n for n,c in checks if not c]}")
    sys.exit(1)
