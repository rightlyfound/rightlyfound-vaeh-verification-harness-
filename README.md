# VAEH Verification Harness

Execution-bound verification system for AI safety artifacts.

## Rule
No artifact is TEST_VERIFIED unless its verification bundle runs and exits with all checks passing.

## Files
- `trifecta_v0.py` — middleware with arrest/rollback
- `synthetic_harness.py` — CLI task runner
- `demo_pipeline.py` — arrest events → telemetry pairs
- `training_factory.py` — telemetry → attested manifest
- `verify_*.py` — contract-pinned verification bundles
- `run_verification.py` — executes bundles, updates ledger
- `.github/workflows/verify.yml` — CI verification on push

## Local Run
python3 run_verification.py verify_demo_pipeline.py --source demo_pipeline.py
python3 run_verification.py verify_training_factory.py --source training_factory.py

## Classification
- DESIGN_ONLY_NOT_EXECUTED: bundle not yet passed
- TEST_VERIFIED: bundle exited 0, all checks passed
- VERIFICATION_FAILED: bundle ran but failed
