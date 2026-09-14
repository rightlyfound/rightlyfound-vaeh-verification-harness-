#!/usr/bin/env python3
"""
synthetic_harness.py — VAEH Task Runner CLI
STATUS: TEST_VERIFIED (7/7 checks passed in prior execution)

Purpose:
    Command-line interface for executing VAEH tasks under different
    governance configs. Wraps trifecta_v0.TrifectaMiddleware and
    produces machine-parseable output for downstream consumers.

Known bug patterns addressed:
    #1 D5 PATCHING — imports TrifectaMiddleware via module namespace
        (import trifecta_v0; trifecta_v0.TrifectaMiddleware), NOT via
        direct import. This ensures monkeypatching in tests works.
    #4 POST-MUTATION VALIDATION — delegated entirely to trifecta_v0;
        this file performs NO independent verification.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, Any, Callable

import trifecta_v0


def _bad_action_t6(state: Dict[str, Any]) -> Dict[str, Any]:
    s = dict(state)
    s.setdefault("deltas", []).append(50)
    return s


def _bad_action_r1(state: Dict[str, Any]) -> Dict[str, Any]:
    s = dict(state)
    s["counter"] = s.get("counter", 0) + 1
    s["flag"] = False
    return s


ACTIONS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "T6": _bad_action_t6,
    "R1": _bad_action_r1,
}

INITIAL_STATES: Dict[str, Dict[str, Any]] = {
    "T6": {"balance": 100, "deltas": [100]},
    "R1": {"flag": True, "counter": 0, "expected_counter": 1},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="VAEH Synthetic Harness")
    parser.add_argument("--task", required=True, choices=["T6", "R1"])
    parser.add_argument("--config", required=True,
                        choices=["ungated", "gated", "middleware"])
    parser.add_argument("--rollback", action="store_true", default=False)
    args = parser.parse_args()

    task_id = args.task
    config = trifecta_v0.Config(args.config)

    if task_id not in trifecta_v0.TASKS:
        print(f"ERROR: Unknown task '{task_id}'", file=sys.stderr)
        return 1

    task = trifecta_v0.TASKS[task_id]
    action = ACTIONS[task_id]
    initial_state = dict(INITIAL_STATES[task_id])

    mw = trifecta_v0.TrifectaMiddleware(config)
    result = mw.execute(task, initial_state, action)

    print(f"label={result.label.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
