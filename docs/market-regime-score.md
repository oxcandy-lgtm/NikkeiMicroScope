# Market Regime Score — NikkeiMicroScope (NMS)

This document defines the **advisory** market-regime scores used by NMS.
The formulas here are normative for the code in `core/`. Any change to a
score must be made in the same PR that updates this document.

> **Scoring is advisory, not canonical truth.** No score in this
> document constitutes investment advice, a prediction, or a
> profit guarantee.

## Score Families

| Score               | Range    | Higher means…                                     |
| ------------------- | -------- | ------------------------------------------------- |
| `direction_score`   | `-1..+1` | stronger **bullish** bias (positive) / **bearish** bias (negative). |
| `volatility_score`  | `0..1`   | stronger compression relative to recent history.  |
| `event_risk_score`  | `0..1`   | higher scheduled-event risk in or near the window.|
| `no_trade_score`    | `0..1`   | stronger structural reason **not to take a trade**. |

All four scores are dimensionless and intentionally bounded. They are
not probabilities in the statistical sense and must not be cited as
such.

## `direction_score`

A weighted sum of normalized, sign-aligned context signals:

```
direction_score = clamp(sum_i w_i * s_i, -1, +1)
```

Where each `s_i` is a context signal normalized to `[-1, +1]`
(positive = bullish for Nikkei, negative = bearish). Suggested
signal weights at MVP:

| Signal                                | `w_i` |
| ------------------------------------- | ----- |
| Nasdaq-100 daily % change             |  0.20 |
| SOX daily % change                    |  0.20 |
| S&P 500 daily % change                |  0.10 |
| USDJPY daily % change (JPY weaker = +) |  0.20 |
| US 10Y daily change (bp, sign-flipped) |  0.10 |
| Nikkei night-session % change         |  0.20 |

Weights are MVP defaults and are documented here so the code in
`core/` can import them. Tuning weights requires a research PR that
also updates the backtest metrics in `docs/research-plan.md`.

## `volatility_score`

A compression indicator relative to recent history:

- Compute realized vol and an ATR-like measure on a rolling window.
- `volatility_score` is the normalized inverse: it is **high** when
  current vol is *below* the rolling baseline (compression), and
  **low** when current vol is *above* baseline (expansion).
- Bounded to `0..1`. A simple MVP form is acceptable, e.g.
  `clamp(1 - realized_vol / baseline_vol, 0, 1)`.

## `event_risk_score`

A scheduled-event proximity / impact score:

- `0` when no high-impact event is scheduled in the next N hours.
- Approaches `1` when a high-impact event (CPI, FOMC, BoJ, NFP, etc.)
  is scheduled within the session window.
- MVP uses a fixed list of event names and a static impact table.
  Changes to the event list require updating this document in the
  same PR.

## `no_trade_score`

A composite that flags structural reasons **not** to take a trade:

```
no_trade_score = clamp(
    w_v * volatility_score
  + w_e * event_risk_score
  + w_a * alignment_penalty,
    0, 1
)
```

Where `alignment_penalty` rises when the planned side disagrees with
`direction_score`. Default weights at MVP:

| Component            | Weight |
| -------------------- | ------ |
| `volatility_score`   |  0.40  |
| `event_risk_score`   |  0.40  |
| `alignment_penalty`  |  0.20  |

`classification` is derived as:

- `no-trade` if `no_trade_score >= no_trade_threshold`.
- Otherwise: `buy-only` if `direction_score > 0`, `sell-only` if
  `direction_score < 0`, `no-trade` if `direction_score == 0`.

The `no_trade_threshold` is a documented constant (suggested MVP
value: `0.5`).

## Implementation Note (PR #4 skeleton)

The MVP implementation in `nms/core/` follows the formulas above
with two clarifications:

1. **`direction_score` is currently driven by the overnight Nikkei
   move only.** The `MarketContext` schema (see
   `docs/data-adapter-contract.md`) exposes daily percent change
   only for `nikkei_night_session.percent_change`. The other five
   context groups (Nasdaq-100, SOX, S&P 500, USDJPY, US 10Y) carry
   absolute values, not daily changes. The implementation
   therefore contributes a neutral `0.0` from those five slots at
   MVP rather than inventing changes from absolute levels.
   Activating them requires a schema PR that adds change fields,
   not a scoring PR.

2. **The bounded normalizer for `percent_change` saturates at
   ±2%.** A 2% move fully drives the signal; larger moves are
   clamped. This is a documented constant
   (`PERCENT_CHANGE_SATURATION = 2.0`) in `nms/core/constants.py`.

The exact formulas, constants, MVP limitations, and non-claims are
normatively defined in `docs/core-scoring-contract.md`. If this
section and the contract disagree, the contract wins and this
section is the bug.

## Logging No-Trade Reasons and False Positives

Each session must record, in `regime.json`:

- `no_trade_reasons[]` — human-readable strings naming the dominant
  contributors to `no_trade_score` (e.g. `"event_risk: FOMC in
  window"`, `"volatility_compression: 0.82"`).
- `false_positive_flags[]` — populated only on sessions that were
  classified as `buy-only` / `sell-only` but did not reach the
  planned move. Each entry references the score that misled the
  classification and the actual reachable-move result.

## Non-Claims

- These scores do not predict the future.
- These scores are not probabilities.
- These scores are not a recommendation to take or avoid a trade.
- A high `no_trade_score` is **not** a guarantee that trading would
  have lost money, and a low `no_trade_score` is **not** a guarantee
  that trading would have made money.
