#!/usr/bin/env python3
"""
demo_pipeline.py — VAEH Telemetry Emitter
STATUS: DESIGN_ONLY_NOT_EXECUTED

Purpose:
    Reads arrest events from runs/arrest_*.json, validates SHA-256
    integrity, and emits telemetry.jsonl with dpo_training_pair entries.

Contracts:
    process_arrest_files(runs_dir="runs", output_path="telemetry.jsonl") -> int
        >= 0: number of valid entries written
        -1:   runs_dir missing (ERROR stderr)
        tampered/unreadable files: skipped with WARNING stderr
        empty runs_dir: returns 0
        idempotent on re-run
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from typing import Any, Dict, List


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def validate_arrest_event(record: Dict[str, Any]) -> bool:
    expected_hash = record.get("sha256")
    if expected_hash is None:
        return False
    payload = {k: v for k, v in record.items() if k != "sha256"}
    computed_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return computed_hash == expected_hash


def arrest_to_training_pair(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_type": "dpo_training_pair",
        "task_id": event["task_id"],
        "task_kind": event["task_kind"],
        "config": event["config"],
        "label": event["label"],
        "rolled_back": event.get("rolled_back", False),
        "post_state": event.get("post_state", {}),
        "timestamp": event.get("ts"),
    }


def process_arrest_files(runs_dir: str = "runs", output_path: str = "telemetry.jsonl") -> int:
    if not os.path.isdir(runs_dir):
        print(f"ERROR: runs directory '{runs_dir}' not found", file=sys.stderr)
        return -1

    pattern = os.path.join(runs_dir, "arrest_*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"WARNING: No arrest files found in {runs_dir}", file=sys.stderr)
        with open(output_path, "w") as f:
            pass
        return 0

    valid_count = 0
    entries: List[Dict[str, Any]] = []

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                record = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Could not read {filepath}: {e}", file=sys.stderr)
            continue

        if not validate_arrest_event(record):
            print(f"WARNING: Hash mismatch in {filepath} — skipping (tamper detected)",
                  file=sys.stderr)
            continue

        pair = arrest_to_training_pair(record)
        entries.append(pair)
        valid_count += 1

    with open(output_path, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    return valid_count


if __name__ == "__main__":
    count = process_arrest_files()
    if count < 0:
        sys.exit(1)
    print(f"Emitted {count} training pairs to telemetry.jsonl")
    sys.exit(0)
