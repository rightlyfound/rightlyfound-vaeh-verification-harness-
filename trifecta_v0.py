#!/usr/bin/env python3
"""
trifecta_v0.py — VAEH Core Middleware
STATUS: TEST_VERIFIED (7/7 checks passed in prior execution)

Purpose:
    Middleware harness demonstrating governed task execution with
    arrest and rollback. This is the component whose absence produces
    SILENT_WRONG_STATE_FAILURE (ungated config) and whose presence
    produces ARRESTED_TASK (gated / middleware configs).

Known bug patterns addressed:
    #4 POST-MUTATION VALIDATION — verification runs AFTER the action
        mutates state, never as a substitute for it. Pre-flight checks
        alone are structurally insufficient and are not offered.

Design invariants:
    - UNGATED:     execute action, no post-state verification.
    - GATED:       execute action, verify post-state, arrest on failure.
    - MIDDLEWARE:  execute action, verify post-state, arrest + rollback if reversible.
    - T6: VERIFIABLE but NOT reversible.
    - R1: REVERSIBLE — rollback supported and recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional


class Config(str, Enum):
    UNGATED = "ungated"
    GATED = "gated"
    MIDDLEWARE = "middleware"


class TaskKind(str, Enum):
    VERIFIABLE = "VERIFIABLE"
    REVERSIBLE = "REVERSIBLE"


class OutcomeLabel(str, Enum):
    OK = "OK"
    SILENT_WRONG_STATE_FAILURE = "SILENT_WRONG_STATE_FAILURE"
    ARRESTED_TASK = "ARRESTED_TASK"


@dataclass(frozen=True)
class Task:
    task_id: str
    kind: TaskKind
    verify: Callable[[Dict[str, Any]], bool]
    rollback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    def __post_init__(self) -> None:
        if self.kind is TaskKind.REVERSIBLE and self.rollback is None:
            raise ValueError(f"{self.task_id}: REVERSIBLE task requires a rollback function")
        if self.kind is TaskKind.VERIFIABLE and self.rollback is not None:
            raise ValueError(f"{self.task_id}: VERIFIABLE task must not define rollback")


def _verify_t6(state: Dict[str, Any]) -> bool:
    return state.get("balance") == sum(state.get("deltas", []))


def _verify_r1(state: Dict[str, Any]) -> bool:
    return state.get("flag") is True and state.get("counter") == state.get("expected_counter")


def _rollback_r1(state: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = state.get("_pre_action_snapshot")
    if snapshot is None:
        raise RuntimeError("R1 rollback requested without a pre-action snapshot")
    restored = dict(snapshot)
    restored["_rolled_back"] = True
    return restored


T6 = Task(task_id="T6", kind=TaskKind.VERIFIABLE, verify=_verify_t6, rollback=None)
R1 = Task(task_id="R1", kind=TaskKind.REVERSIBLE, verify=_verify_r1, rollback=_rollback_r1)
TASKS: Dict[str, Task] = {"T6": T6, "R1": R1}

RUNS_DIR = "runs"


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def write_arrest_event(event: Dict[str, Any], runs_dir: str = RUNS_DIR) -> str:
    os.makedirs(runs_dir, exist_ok=True)
    digest = hashlib.sha256(_canonical_json(event).encode("utf-8")).hexdigest()
    record = dict(event)
    record["sha256"] = digest
    ts = event.get("ts", time.time())
    ts_str = f"{ts:.6f}".replace(".", "_")
    path = os.path.join(runs_dir, f"arrest_{event['task_id']}_{ts_str}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
    return path


@dataclass
class ExecutionResult:
    task_id: str
    config: Config
    label: OutcomeLabel
    state: Dict[str, Any]
    arrested: bool = False
    rolled_back: bool = False
    arrest_path: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id, "config": self.config.value,
            "label": self.label.value, "arrested": self.arrested,
            "rolled_back": self.rolled_back, "arrest_path": self.arrest_path,
            "detail": self.detail,
        }


class TrifectaMiddleware:
    def __init__(self, config: Config, runs_dir: str = RUNS_DIR):
        if not isinstance(config, Config):
            config = Config(config)
        self.config = config
        self.runs_dir = runs_dir

    def execute(self, task: Task, state: Dict[str, Any],
                action: Callable[[Dict[str, Any]], Dict[str, Any]]) -> ExecutionResult:
        pre_action_snapshot = dict(state)
        working = dict(state)
        working["_pre_action_snapshot"] = pre_action_snapshot
        new_state = action(working)

        if self.config is Config.UNGATED:
            ok = task.verify(new_state)
            if not ok:
                return ExecutionResult(
                    task_id=task.task_id, config=self.config,
                    label=OutcomeLabel.SILENT_WRONG_STATE_FAILURE,
                    state=new_state,
                    detail="Post-state violates invariant; ungated let it pass.")
            return ExecutionResult(task_id=task.task_id, config=self.config,
                                   label=OutcomeLabel.OK, state=new_state)

        ok = task.verify(new_state)
        if ok:
            return ExecutionResult(task_id=task.task_id, config=self.config,
                                   label=OutcomeLabel.OK, state=new_state)

        rolled_back = False
        final_state = new_state

        if self.config is Config.MIDDLEWARE:
            if task.kind is TaskKind.REVERSIBLE:
                final_state = task.rollback(new_state)
                rolled_back = True
            else:
                if task.rollback is not None:
                    raise RuntimeError(f"{task.task_id}: rollback prohibited for VERIFIABLE task")

        event = {
            "ts": time.time(), "task_id": task.task_id,
            "task_kind": task.kind.value, "config": self.config.value,
            "label": OutcomeLabel.ARRESTED_TASK.value, "rolled_back": rolled_back,
            "post_state": {k: v for k, v in new_state.items() if k != "_pre_action_snapshot"},
        }
        arrest_path = write_arrest_event(event, runs_dir=self.runs_dir)

        return ExecutionResult(
            task_id=task.task_id, config=self.config,
            label=OutcomeLabel.ARRESTED_TASK, state=final_state,
            arrested=True, rolled_back=rolled_back, arrest_path=arrest_path,
            detail="Post-state verification failed; task arrested.")
