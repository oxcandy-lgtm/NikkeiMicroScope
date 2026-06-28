# Shadow Replay Integrity CI Proof

## Purpose

This document records the CI proof lane for the shadow replay integrity checker.
The lane exists because local execution output must not be fabricated when the
operator cannot actually run the repository locally.

## CI lane

The `ccl-lite` workflow now keeps its original Satellite artifact validation and
adds three read-only proof steps:

1. `python3 -m compileall -q nms scripts tests`
2. `python3 -m unittest tests.test_shadow_replay_integrity`
3. `bash scripts/run_shadow_replay_integrity_dry_run.sh`

These steps run on GitHub Actions for pull requests and for `codex/**` branch
pushes.

## What this proves

The CI lane proves that, in the checked-out repository state:

- Python files under `nms`, `scripts`, and `tests` compile.
- `tests.test_shadow_replay_integrity` passes.
- The integrity dry-run can generate synthetic local replay artifacts,
  run the replay, run the checker, and verify an `ok:true` report.

## What this does not prove

The CI lane does not prove market quality, score quality, strategy quality,
future outcome, or execution readiness.

The dry-run uses temporary files and synthetic placeholder data only. It does
not fetch market data, does not use credentials, and does not write committed
runtime artifacts.

## Boundaries

This proof lane must remain:

- read-only at the repository permission level
- local-file-only during execution
- dependency-free beyond Python stdlib and GitHub-hosted runner defaults
- free of any order, venue, or account path
- limited to compile/unit/dry-run proof

It must not become a live pipeline, source acquisition job, scheduled data run,
or summary-performance workflow.
