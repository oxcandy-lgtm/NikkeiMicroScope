# Paper Gate State Validation Hardening

## Purpose

This document records the state-validation hardening layer for
`nms.paper.gates`.

PR #22 introduced the pure paper gate model. This hardening pass keeps that
model pure and deterministic while making every public evaluator reject malformed
`PaperGateState` values before applying a simulated delta.

## Why this exists

`PaperGateState` is a frozen dataclass, but Python callers can still construct
one directly with invalid field values. A future local paper refinement harness
must not accidentally accept corrupted state as valid input.

The correct behavior is fail-closed at evaluator entry.

## Validation added

Every public evaluator now validates the full state before evaluation:

- `evaluate_session_gate(...)`
- `evaluate_daily_gate(...)`
- `evaluate_weekly_gate(...)`
- `evaluate_all_gates(...)`

The state must satisfy:

- `state` is a `PaperGateState`
- `session_id`, `day_key`, and `week_key` are non-empty strings
- `session_realized_jpy`, `day_realized_jpy`, and `week_realized_jpy` are
  non-negative integers
- boolean values are not accepted as integer counters
- `contract_count` is an integer and equals `FIXED_CONTRACT_COUNT`
- `session_halted`, `day_halted`, and `week_halted` are booleans

`format_halt_reason(...)` also rejects negative or boolean `limit_jpy` /
`observed_jpy` values.

## Scope

This is a local validation hardening change only.

It does not add:

- a paper refinement harness
- a replay loop
- an optimizer
- a report writer
- a command-line trading surface
- a network adapter
- a broker or venue adapter
- a scheduled workflow
- a scoring or signal layer

## CI proof

The read-only `ccl-lite` workflow now runs the paper gate tests directly:

```bash
python3 -m unittest tests.test_paper_trading_gates tests.test_paper_gate_state_validation
```

The workflow still uses repository read-only permissions.

## Non-claims

This hardening pass is not a backtest, not paper execution, not live trading,
not a broker integration, not an order path, not a strategy optimizer, and not a
performance or result-summary layer.
