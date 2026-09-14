---
name: validate-execution
description: Executes a verification bundle for a pending artifact and advances
  its status from DESIGN_ONLY to TEST_VERIFIED only on real evidence.
---

# Validate Execution

## Overview
Runs the verification bundle for a target artifact in the real environment,
captures complete terminal evidence, updates a status ledger, and classifies
the artifact honestly.

## When to Use
- An artifact claims TEST_VERIFIED without a bundle run
- A user asks "is it verified?" and the ledger shows DESIGN_ONLY
- A source file changed and prior verification is stale

## Core Process
1. LOCATE the bundle: look for `verify_<artifact>.py` beside the source.
   If absent, STOP: do not fabricate a run.
2. RUN it: `python3 verify_<artifact>.py` — capture stdout, stderr, exit code.
3. PARSE the bundle's RESULT line (`RESULT: N/M checks passed`).
4. UPDATE the ledger (`verification_status.json`) with full evidence.
5. CLASSIFY: exit 0 AND N==M → TEST_VERIFIED. Otherwise VERIFICATION_FAILED.
6. REPORT the evidence block verbatim. Never summarize away a failure.

## Red Flags
- Classifying TEST_VERIFIED without an exit code in the ledger
- Logging a rerun as fresh evidence when source changed between runs
- Truncating stderr before the failing check is visible
