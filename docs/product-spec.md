# Product Spec — NikkeiMicroScope (NMS)

## Problem

Retail and semi-pro traders of Nikkei 225 micro futures routinely enter
sessions that have no realistic chance of producing the +50円 / +100円
moves they need to justify a position. The reasons are usually structural
(context mismatch) and observable in advance:

- US session risk-on / risk-off flow is misaligned with the planned side.
- USDJPY, US yields, or Nasdaq / SOX context contradicts the planned
  direction.
- Economic event risk is elevated (CPI, FOMC, BoJ, US NFP, etc.).
- Intraday 15-minute range is too compressed for the planned stop.
- Volatility / ATR-like context does not support the planned move.
- The previous-day high / low sits in the way of the planned target.

Today, most of this is judged manually and inconsistently. NMS makes the
context check **explicit, logged, and reproducible**.

## Target User

- Independent retail / semi-pro Nikkei 225 micro futures traders.
- Researchers studying Nikkei 225 micro futures intraday structure.
- Paper-trading hobbyists who want a consistent, observable regime log.

NMS is **not** aimed at:

- Institutional desks (latency, order routing, and compliance needs are
  out of scope).
- Beginners with no futures market background (assumes basic
  understanding of margin, leverage, and intraday risk).

## MVP Scope

The MVP is **observation only**. It must:

1. Collect and normalize the **initial monitored context** below.
2. Compute advisory `direction_score`, `volatility_score`,
   `event_risk_score`, `no_trade_score` per session.
3. Classify each session as `buy-only` / `sell-only` / `no-trade`.
4. Log no-trade reasons and false-positive conditions explicitly.
5. Evaluate whether a +50円 or +100円 move was realistically reachable
   from the open, given observed context.
6. Support backtesting on historical sessions.
7. Support paper trading with hard simulated-loss gates.

The MVP must **not**:

- Place orders.
- Connect to any broker, exchange, or order-routing API.
- Hold credentials, secrets, or `.env` files.
- Make financial-advice claims or profit guarantees.

## Inputs (Initial Monitored Context)

| Group                | Signal                                                            |
| -------------------- | ----------------------------------------------------------------- |
| US equities          | S&P 500, Dow, Nasdaq-100, Russell 2000 — close, % change.         |
| Semiconductor        | SOX / Philadelphia Semiconductor Index — close, % change.        |
| FX                   | USDJPY — close, intraday range, % change.                         |
| US yields            | 2Y, 10Y, 10Y-2Y spread — change.                                  |
| Nikkei night session | Nikkei 225 night-session close, high, low, range.                 |
| Previous day         | Nikkei 225 previous-day high, low, close, range.                  |
| Economic event risk  | Calendar of scheduled high-impact events (CPI, FOMC, BoJ, NFP).   |
| Intraday range       | First 15 minutes of cash session range vs. ATR-like baseline.     |
| Volatility context   | Realized vol, ATR-like measure, intraday compression flag.        |

All inputs must be **publicly available** at MVP. No paid feeds, no
authenticated data sources, no broker data.

## Outputs (Advisory)

- `regime.json` per session:
  - `direction_score`, `volatility_score`, `event_risk_score`,
    `no_trade_score`.
  - `classification`: `buy-only` | `sell-only` | `no-trade`.
  - `no_trade_reasons[]`, `false_positive_flags[]`.
  - `reachable_moves`: `{ "p50": bool, "p100": bool, "reason": "..." }`.
- `reports/session-YYYY-MM-DD.md` — human-readable session summary.
- `exports/satellite-update-plan.json` — advisory update plan (dry run).

## Non-Goals (Hard)

- Live trading, order placement, broker integration.
- Holding or accepting any credential, token, or `.env` file.
- Financial advice or profit guarantees.
- Predictive accuracy claims ("we predict X with Y% accuracy").
- Auto-tuning against user account balance or position size.

## Risk Posture

- All outputs are advisory. Final decisions remain with the human.
- See `docs/risk-policy.md` for hard loss gates, anti-martingale, and
  no-leverage-escalation rules.
- See `README.md` for the standing disclaimer.
