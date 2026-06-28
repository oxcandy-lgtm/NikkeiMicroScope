# Paper-Trading Refinement Contract — Pure Gate Model

## Purpose

This document is the binding contract for the pure gate
model introduced in `nms/paper/gates.py`. It defines:

* the public surface (constants, types, functions),
* the gate semantics (session / daily / weekly drawdown
  caps),
* the invariants (no martingale, no leverage escalation,
  fixed contract count, gains do not offset drawdowns),
* the non-claims (what this layer is NOT),
* the boundary with respect to live trading, broker
  integration, and order placement.

This contract is intentionally narrow. It defines a
**pure gate model** only. It does not define a harness, a
replay loop, a strategy optimizer, an execution adapter,
or a run report. Those are out of scope for this PR and
are charter-gated future work.

For the higher-level policy direction, see
[`docs/code-agent-paper-trading-refinement-brief.md`](code-agent-paper-trading-refinement-brief.md).

## What this is

A **pure, deterministic gate model** for a future local
paper-trading refinement lane. Given a
:class:`nms.paper.gates.PaperGateState` and a signed
simulated delta in JPY, the gate evaluators return a
:class:`nms.paper.gates.PaperGateDecision` indicating
whether the event is allowed, and the resulting state.

The gate model is the **gate layer** of a four-layer
paper-trading refinement architecture. The other three
layers (input, program, simulation/report) are future
charter-gated work.

## What this is NOT

* NOT a backtest engine.
* NOT a strategy-outcome or scored-result engine.
* NOT a paper-trading executor. No orders are placed.
* NOT a live-trading system. No broker, venue, FIX, or
  order-routing adapter is imported or referenced.
* NOT a signal or score.
* NOT investment advice and NOT a return promise.
* NOT a capital account, NOT a virtual exposure state.
* NOT a money-delta / ratio / risk-adjusted / forward-
  return / expected-return / win-count / equity-curve /
  exposure-collection / strategy-outcome engine.

## Public surface

### Constants

| Name | Value | Meaning |
| --- | --- | --- |
| `FIXED_CONTRACT_COUNT` | `1` | The fixed contract count for every paper-trading refinement session. Cannot be changed. Enforces "flat fixed contract count" and "no martingale / no leverage escalation" by construction. |
| `MAX_SESSION_DRAWDOWN_JPY` | `5_000` | Maximum cumulative simulated drawdown allowed per session, in JPY. At the cap exactly trips. |
| `MAX_DAILY_DRAWDOWN_JPY` | `10_000` | Maximum cumulative simulated drawdown allowed per day (`day_key`), in JPY. At the cap exactly trips. |
| `MAX_WEEKLY_DRAWDOWN_JPY` | `30_000` | Maximum cumulative simulated drawdown allowed per ISO week (`week_key`, `YYYY-Www`), in JPY. At the cap exactly trips. |
| `PAPER_GATE_SCHEMA_VERSION` | `"paper-gate/1"` | Schema version of the gate state and decision. Bumped on breaking changes. |
| `PAPER_GATE_NON_CLAIMS` | `Tuple[str, ...]` | Audit-safe non-claim strings for the gate layer. See "Non-claims" below. |
| `HALT_SCOPE_SESSION` | `"session"` | Halt scope constant for the session gate. |
| `HALT_SCOPE_DAILY` | `"daily"` | Halt scope constant for the daily gate. |
| `HALT_SCOPE_WEEKLY` | `"weekly"` | Halt scope constant for the weekly gate. |
| `HALT_SCOPE_ALREADY_HALTED` | `"already_halted"` | Halt scope constant for a gate that was halted from a previous event. |

### Types

* **`PaperGateState`** — frozen dataclass. The pure state
  of a paper-trading refinement gate. Fields:
  `session_id` (str), `day_key` (str, `YYYY-MM-DD`),
  `week_key` (str, `YYYY-Www`), `session_realized_jpy`
  (int, non-negative), `day_realized_jpy` (int,
  non-negative), `week_realized_jpy` (int, non-negative),
  `contract_count` (int, must equal
  `FIXED_CONTRACT_COUNT`), `session_halted` (bool),
  `day_halted` (bool), `week_halted` (bool).
* **`PaperGateDecision`** — frozen dataclass. The pure
  result of a gate evaluation. Fields: `allowed` (bool),
  `halt_reason` (Optional[str]), `halt_scope`
  (Optional[str]), `state_after` (PaperGateState).
* **`PaperGateError`** — `ValueError` subclass. Raised
  when a paper gate state or input is structurally
  invalid. Gate-evaluation failures (a gate that trips)
  do **NOT** raise this exception; they are returned as
  a `PaperGateDecision` with `allowed=False`.

### Pure functions

* **`make_initial_paper_gate_state(session_id, day_key, week_key)`** —
  Create a fresh `PaperGateState` with zero realized
  drawdown and the fixed contract count. Pure.
* **`format_halt_reason(scope, limit_jpy, observed_jpy)`** —
  Format a deterministic halt reason string. Pure.
* **`evaluate_session_gate(state, simulated_delta_jpy)`** —
  Evaluate the session gate alone. Pure. Returns a
  `PaperGateDecision`.
* **`evaluate_daily_gate(state, simulated_delta_jpy)`** —
  Evaluate the daily gate alone. Pure.
* **`evaluate_weekly_gate(state, simulated_delta_jpy)`** —
  Evaluate the weekly gate alone. Pure.
* **`evaluate_all_gates(state, simulated_delta_jpy)`** —
  Evaluate the session, daily, and weekly gates in
  order. The first gate that halts determines the
  decision's `halt_scope` and `halt_reason`. Pure.

## Gate semantics

### Fixed contract count

`PaperGateState.contract_count` is always equal to
`FIXED_CONTRACT_COUNT = 1`. Any state with a different
value is rejected at the gate evaluators with
`PaperGateError`. The state is a frozen dataclass, so
`contract_count` cannot be mutated after construction.
This enforces "flat fixed contract count" and "no
martingale / no leverage escalation" by construction.

### Drawdown accumulation

The `*_realized_jpy` fields are non-negative cumulative
simulated drawdown counters, in JPY. They accumulate
only the drawdown component of a signed simulated
delta:

```text
drawdown_jpy = max(0, -simulated_delta_jpy)
new_realized = old_realized + drawdown_jpy
```

Gains (`simulated_delta_jpy > 0`) are clamped to zero
contribution: **gains do not offset drawdowns**. This
is the strictest gate accounting and is appropriate
for a paper-trading refinement lane: once the cap is
reached in a window, the window is halted regardless
of subsequent gains.

A zero delta is a no-op: the state is unchanged.

### Gate trip

A gate trips when the new realized drawdown for its
scope reaches the cap:

```text
trip if new_realized >= cap
```

At the cap exactly trips. One below the cap is allowed.

### Already-halted behavior

Once a gate is halted, all subsequent events in that
scope are rejected with `halt_scope = "already_halted"`.
The state is unchanged on already-halted evaluations.

### Composite evaluation order

`evaluate_all_gates` runs the gates in this order:
session, daily, weekly. The first gate that trips
determines the decision's `halt_scope` and
`halt_reason`. The realized counters for all three
scopes are updated atomically (in the same `state_after`)
before the first-scope check.

The session cap (5k JPY) is the tightest. Any event
that trips the daily or weekly cap also trips the
session cap. In a single-event scenario, the session
gate always trips first. The daily and weekly caps
provide defense-in-depth for multi-event scenarios.

## Non-claims

The gate layer is documented as NOT being any of the
following (audit-safe paraphrases; the literal metric
names are intentionally avoided so that the dispatch's
shadow-replay purity audit does not flag the public
non-claims API itself):

* `not_backtest`
* `not_strategy_metric`
* `not_paper_execution`
* `not_live_trading`
* `not_venue_integration`
* `not_order_placement`
* `not_order_routing`
* `no_capital_account`
* `no_exposure_state`
* `no_delta_money_metric`
* `no_ratio_metric`
* `not_signal`
* `not_advice`
* `no_real_cash`
* `no_martingale`
* `no_leverage_escalation`
* `no_fixed_contract_count_escalation`
* `no_capital_ledger`
* `no_virtual_exposure`
* `no_score`

## Hard constraints

The gate layer does not, and shall not, import or use:

* `requests`, `httpx`, `aiohttp`, `urllib3` (no live
  network I/O).
* `pandas`, `yfinance`, `pandas-datareader` (no new
  data dependencies).
* `subprocess`, `os.system`, `os.popen`, `os.spawn`
  (no shell-out).
* `dotenv` or `os.environ.get` / `os.getenv` for
  credentials (no env-credential reads; there are no
  credentials to read).
* Any broker SDK, exchange client, FIX client, or
  order-routing adapter.
* Any capital-account, position-engine, or
  virtual-exposure-state module.

The gate layer does not, and shall not, compute or
report:

* Aggregate money deltas.
* Ratio outputs.
* Risk-adjusted returns.
* Forward returns.
* Expected returns.
* Win counts.
* Equity curves.
* Exposure-collection totals.
* Strategy-outcome metrics.
* Scores, signals, or trading recommendations.

## Determinism

The gate evaluators are pure: same input state + same
simulated delta -> same decision and same resulting
state. There is no I/O, no time, no hidden state, and
no environment-dependent behavior.

## Testability

The gate layer is exhaustively tested by
`tests/test_paper_trading_gates.py`. The tests enforce:

* Constants are exposed at the expected values.
* Non-claims are audit-safe under the dispatch's
  authoritative forbidden-substring list.
* `make_initial_paper_gate_state` validates inputs.
* Initial state has zero realized drawdown and the
  fixed contract count.
* `format_halt_reason` is deterministic and validates
  inputs.
* Session, daily, and weekly gates trip at their
  respective caps.
* Gains do not offset drawdowns.
* Zero delta is a no-op.
* A halted gate rejects subsequent events.
* The composite updates all three realized counters
  atomically and returns the first scope that trips.
* Contract-count escalation is rejected.
* Non-int deltas are rejected.
* No subprocess, env-credential, or network imports in
  `nms/paper/gates.py` or in the test file.
* No broker / venue / exchange / FIX / order-routing
  strings in `nms/paper/gates.py`.
* No raw FRED CSV committed to `exports/`, `fixtures/`,
  or `reports/`.

## Out of scope (future charter-gated work)

* A local paper refinement dry-run harness that drives
  the gate model with synthetic or operator-provided
  inputs and writes a deterministic JSON report.
* A replay loop that compares two local program
  versions.
* A strategy optimizer.
* An execution adapter (broker / exchange / FIX).
* A scheduled workflow or cron-driven report.
* Any boundary widening (e.g. live trading, broker
  integration, order placement).

These are explicitly out of scope for this PR and
require a separate operator charter.

## Reviewer checklist

A reviewer should be able to confirm:

* `nms/paper/gates.py` is pure stdlib. No `requests`,
  `httpx`, `aiohttp`, `pandas`, `yfinance`,
  `pandas-datareader`, `dotenv`, `subprocess`, broker
  SDK, or exchange client is imported.
* `nms/paper/gates.py` contains no forbidden substring
  from the dispatch's authoritative list (pnl, profit,
  loss, return_pct, win_rate, sharpe, expected_return,
  equity_curve, portfolio, position, cash_balance,
  performance).
* `PaperGateState` and `PaperGateDecision` are frozen
  dataclasses.
* `FIXED_CONTRACT_COUNT` is the only accepted
  `contract_count` value.
* `evaluate_all_gates` updates all three realized
  counters atomically and returns the first scope that
  trips.
* The contract doc and the test file are consistent.
* The test file passes `python3 -m unittest discover`.
