# Paper Gate State Validation Implementation Note

This note ties the hardening pass to the binding contract in
`docs/paper-trading-refinement-contract.md`.

The pure gate model is still the same layer introduced by PR #22. The only
change is that every evaluator checks the shape of the provided
`PaperGateState` before applying the simulated delta.

## Public evaluator behavior

The following functions now fail closed with `PaperGateError` when the incoming
state is malformed:

- `evaluate_session_gate(...)`
- `evaluate_daily_gate(...)`
- `evaluate_weekly_gate(...)`
- `evaluate_all_gates(...)`

Malformed means one of:

- the object is not `PaperGateState`
- session/day/week keys are empty or not strings
- realized counters are negative or not integers
- boolean values are passed as integer counters
- `contract_count` is not the fixed contract count
- halt flags are not booleans

This keeps later local harness work from treating corrupted state as valid
input.
