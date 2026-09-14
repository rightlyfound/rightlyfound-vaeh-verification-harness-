#!/usr/bin/env python3
"""
VERIFICATION BUNDLE FOR demo_pipeline.py (contract-pinned)
STATUS: DESIGN_ONLY_NOT_EXECUTED

CONTRACTS:
  process_arrest_files(runs_dir, output_path) -> int
       >= 0: number of valid entries written
       -1:   runs_dir missing (ERROR stderr)
       tampered/unreadable files: skipped with WARNING stderr
       empty runs_dir: returns 0, output file written (empty)
       idempotent on re-run
  Each emitted line is a dpo_training_pair carrying task_id, task_kind,
  config, label, rolled_back, post_state, timestamp.

CANONICALIZATION: json.dumps(obj, sort_keys=True, separators=(",",":"))
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REQUIRED_FILES = ["demo_pipeline.py"]
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


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _write_arrest(runs_dir, name, event, tamper=False):
    record = dict(event)
    record["sha256"] = hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()
    if tamper:
        record["label"] = "OK"
    with open(os.path.join(runs_dir, name), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)


def _call(runs_dir, output_path):
    code = (
        "import demo_pipeline, sys; "
        f"print(demo_pipeline.process_arrest_files({runs_dir!r}, {output_path!r}))"
    )
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def _rc(proc):
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


tmp = tempfile.mkdtemp(prefix="vaeh_dp_")
runs = os.path.join(tmp, "runs")
empty_runs = os.path.join(tmp, "empty_runs")
missing_runs = os.path.join(tmp, "NOPE")
os.makedirs(runs)
os.makedirs(empty_runs)
out = os.path.join(tmp, "telemetry.jsonl")
out_empty = os.path.join(tmp, "telemetry_empty.jsonl")
out_missing = os.path.join(tmp, "telemetry_missing.jsonl")

try:
    valid_events = [
        {"ts": 1.0, "task_id": "T6", "task_kind": "VERIFIABLE", "config": "gated",
         "label": "ARRESTED_TASK", "rolled_back": False,
         "post_state": {"balance": 100, "deltas": [100, 50]}},
        {"ts": 2.0, "task_id": "R1", "task_kind": "REVERSIBLE", "config": "middleware",
         "label": "ARRESTED_TASK", "rolled_back": True,
         "post_state": {"flag": False, "counter": 1, "expected_counter": 1}},
    ]
    _write_arrest(runs, "arrest_T6_1_000000.json", valid_events[0])
    _write_arrest(runs, "arrest_R1_2_000000.json", valid_events[1])
    _write_arrest(runs, "arrest_T6_3_000000.json", dict(valid_events[0], ts=3.0), tamper=True)
    with open(os.path.join(runs, "arrest_R1_4_000000.json"), "w") as fh:
        fh.write("{not json")
    with open(os.path.join(runs, "unrelated.json"), "w") as fh:
        fh.write("{}")
    print("✓ Fixtures: 2 valid, 1 tampered, 1 unreadable, 1 non-arrest")

    r1 = _call(runs, out)
    check("valid run exits 0", r1.returncode == 0, r1.stderr[:200])
    check("returns 2 (valid entries only)", _rc(r1) == 2, f"got {_rc(r1)!r}")
    check("tampered file → WARNING on stderr", "warning" in r1.stderr.lower()
          and "tamper" in r1.stderr.lower())
    check("unreadable file → WARNING on stderr", "could not read" in r1.stderr.lower())

    lines = []
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()]
    check("telemetry has 2 lines", len(lines) == 2, f"got {len(lines)}")

    entries = []
    for l in lines:
        try:
            entries.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    check("all lines are valid JSON", len(entries) == len(lines) == 2)
    check("all entries are dpo_training_pair",
          all(e.get("event_type") == "dpo_training_pair" for e in entries))
    required = {"task_id", "task_kind", "config", "label", "rolled_back", "post_state", "timestamp"}
    check("entries carry required fields",
          all(required.issubset(e.keys()) for e in entries))
    check("entries preserve source fields",
          {e.get("task_id") for e in entries} == {"T6", "R1"}
          and any(e.get("rolled_back") is True for e in entries)
          and {e.get("timestamp") for e in entries} == {1.0, 2.0})

    first = open(out, encoding="utf-8").read() if os.path.exists(out) else None
    r1b = _call(runs, out)
    second = open(out, encoding="utf-8").read() if os.path.exists(out) else None
    check("idempotent (identical output, same count)",
          first is not None and first == second and _rc(r1b) == 2)

    r2 = _call(empty_runs, out_empty)
    check("empty runs_dir → returns 0", _rc(r2) == 0, f"got {_rc(r2)!r}")
    check("empty runs_dir → empty output written",
          os.path.exists(out_empty) and os.path.getsize(out_empty) == 0)

    r3 = _call(missing_runs, out_missing)
    check("missing runs_dir → returns -1", _rc(r3) == -1, f"got {_rc(r3)!r}")
    check("missing runs_dir → ERROR on stderr", "error" in r3.stderr.lower())
    check("missing runs_dir → no output written", not os.path.exists(out_missing))

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
    print("  demo_pipeline.py → TEST_VERIFIED (bundle executed locally)")
    sys.exit(0)
else:
    print(f"\nFAILED: {[n for n,c in checks if not c]}")
    sys.exit(1)
