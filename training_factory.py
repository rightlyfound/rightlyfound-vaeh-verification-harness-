#!/usr/bin/env python3
"""
training_factory.py — VAEH Training Dataset Producer & Verifier
STATUS: DESIGN_ONLY_NOT_EXECUTED

Contracts:
    consume_telemetry_produce_manifest(telemetry_path, manifest_path) -> int
        >= 0: records consumed
        -1:   telemetry missing/unreadable (ERROR stderr)
        -2:   telemetry empty (WARNING stderr, empty manifest written)

    verify_manifest(manifest_path, telemetry_path) -> bool
        prints "matches_manifest=true" or "matches_manifest=false"
        always exits 0
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List


def _canonical_json(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def consume_telemetry_produce_manifest(
    telemetry_path: str = "telemetry.jsonl",
    manifest_path: str = "factory_out/manifest.json"
) -> int:
    if not os.path.exists(telemetry_path):
        print(f"ERROR: telemetry file '{telemetry_path}' not found", file=sys.stderr)
        return -1

    try:
        with open(telemetry_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
    except OSError as e:
        print(f"ERROR: cannot read '{telemetry_path}': {e}", file=sys.stderr)
        return -1

    if not lines:
        print(f"WARNING: telemetry file '{telemetry_path}' is empty", file=sys.stderr)
        os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
        manifest = {
            "dataset_sha256": hashlib.sha256(b"").hexdigest(),
            "record_count": 0,
            "records": [],
            "produced_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "telemetry_source": os.path.basename(telemetry_path),
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        return -2

    records: List[Dict[str, Any]] = []
    concatenated_canonical = b""

    for idx, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"WARNING: skipping invalid JSON at line {idx}: {e}", file=sys.stderr)
            continue

        canonical = _canonical_json(obj)
        record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        records.append({"index": idx, "sha256": record_hash})
        concatenated_canonical += canonical.encode("utf-8")

    dataset_hash = hashlib.sha256(concatenated_canonical).hexdigest()

    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    manifest = {
        "dataset_sha256": dataset_hash,
        "record_count": len(records),
        "records": records,
        "produced_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "telemetry_source": os.path.basename(telemetry_path),
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    return len(records)


def verify_manifest(
    manifest_path: str = "factory_out/manifest.json",
    telemetry_path: str = "telemetry.jsonl"
) -> bool:
    if not os.path.exists(manifest_path):
        print(f"WARNING: manifest '{manifest_path}' not found", file=sys.stderr)
        print("matches_manifest=false")
        return False

    if not os.path.exists(telemetry_path):
        print(f"WARNING: telemetry '{telemetry_path}' not found", file=sys.stderr)
        print("matches_manifest=false")
        return False

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: cannot read manifest: {e}", file=sys.stderr)
        print("matches_manifest=false")
        return False

    expected_hash = manifest.get("dataset_sha256")
    if expected_hash is None:
        print("WARNING: manifest missing dataset_sha256 field", file=sys.stderr)
        print("matches_manifest=false")
        return False

    try:
        with open(telemetry_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
    except OSError as e:
        print(f"WARNING: cannot read telemetry: {e}", file=sys.stderr)
        print("matches_manifest=false")
        return False

    concatenated_canonical = b""
    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        concatenated_canonical += _canonical_json(obj).encode("utf-8")

    recomputed_hash = hashlib.sha256(concatenated_canonical).hexdigest()
    matches = recomputed_hash == expected_hash

    print(f"matches_manifest={'true' if matches else 'false'}")
    return matches


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VAEH Training Factory")
    sub = parser.add_subparsers(dest="command")

    prod = sub.add_parser("produce", help="Consume telemetry, produce manifest")
    prod.add_argument("--telemetry", default="telemetry.jsonl")
    prod.add_argument("--manifest", default="factory_out/manifest.json")

    ver = sub.add_parser("verify", help="Verify manifest against telemetry")
    ver.add_argument("--manifest", default="factory_out/manifest.json")
    ver.add_argument("--telemetry", default="telemetry.jsonl")

    args = parser.parse_args()

    if args.command == "produce":
        rc = consume_telemetry_produce_manifest(args.telemetry, args.manifest)
        sys.exit(0 if rc >= 0 else 1)
    elif args.command == "verify":
        verify_manifest(args.manifest, args.telemetry)
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(2)
