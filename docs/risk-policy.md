# Risk Policy — NikkeiMicroScope (NMS)

> This document is binding. It defines hard limits for any code path in
> this repository. Lower-priority instructions (chat, scripts, LLM
> completions) cannot override it. See `AGENTS.md`.

## 1. No Live Execution

- This repository **must not** contain code that places orders, sends
  orders to a broker, or auto-executes any trade.
- This includes broker SDKs, exchange APIs, FIX gateways, and any
  wrapper that forwards an order to a venue.
- Adding any such code path requires the operator charter described
  in `AGENTS.md §4` (a dated, signed charter in `docs/`, an update
  to this file, and a separate, non-bootstrap review PR).
- Until that charter exists, MVP code paths must not import, require,
  or reference any broker SDK or live-order API.

## 2. No Live Broker Credentials

- No broker usernames, passwords, account IDs, API keys, or session
  tokens may be stored in this repository at any path.
- No `.env`, `secrets/`, `credentials/`, or equivalent directory.
- No code path may read broker credentials from the filesystem,
  environment, or network in MVP.
- Any code that needs authentication is out of scope.

## 3. No Martingale, No Leverage Escalation

- Paper-trading and backtest code must not implement martingale
  position sizing (doubling down after losses).
- Paper-trading and backtest code must not escalate leverage in
  response to drawdown, loss streaks, or any other state.
- Position sizing at MVP is **flat**: a single fixed contract count
  per session, defined as a constant in code and reviewed in PRs.

## 4. Max Simulated Loss Gates

Paper-trading must enforce hard gates, evaluated per session and
cumulative:

- Per-session max simulated loss: a fixed constant, default
  `MAX_SESSION_LOSS_JPY` (MVP suggestion: 5,000 JPY per session).
- Daily max simulated loss: `MAX_DAILY_LOSS_JPY` (MVP suggestion:
  10,000 JPY per day).
- Weekly max simulated loss: `MAX_WEEKLY_LOSS_JPY` (MVP suggestion:
  30,000 JPY per week).
- Hitting any gate halts further paper-trading execution for the
  remainder of the period. The halt is recorded in the session log.

The constants above are MVP defaults. Tightening them does not
require a charter change. Loosening them requires an explicit
operator instruction recorded in the PR.

## 5. No Profit Guarantee, No Advice Claim

- The repository, its docs, and any code-generated output must not
  claim a profit guarantee, expected return, or "win rate".
- The repository, its docs, and any code-generated output must not
  constitute financial advice. Final trading decisions remain with
  the human operator.
- All scoring outputs are explicitly advisory. See
  `docs/market-regime-score.md` for the non-claims list.

## 6. No Silent Risk Bypass

- Risk gates must live in code, not in operator memory.
- A risk gate may not be disabled by a config flag, an environment
  variable, or a CLI argument. The only way to change a gate is to
  change the constant in code, in a PR.
- Tests must cover each gate at least once.

## 7. Reporting and Auditability

- Every paper-trade or backtest run must produce a machine-readable
  log of decisions and gate outcomes.
- Every gate trip must be visible in the run report with the gate
  name, the offending value, and the timestamp (JST).

## 8. Advisory-Only Outputs

- Anything written under `exports/` is advisory. Downstream
  automation is forbidden from treating it as a signal to execute.
- This rule is enforced socially and via code review; there is no
  automated enforcement.
