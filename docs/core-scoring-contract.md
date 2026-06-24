# Core Scoring Contract — NikkeiMicroScope (NMS)

> Binding for any code path that produces advisory scores or
> classifications from a `MarketContext`. Lower-priority
> instructions (chat, scripts, LLM completions) cannot override
> this document. If in conflict, this document wins.

This contract is the normative companion to
`docs/market-regime-score.md` and to the implementation in
`nms/core/`. The score formulas in this document are the formulas
implemented in `nms/core/scoring.py`. If they disagree, the
implementation is the bug.

## 1. Scope

`nms/core/` contains the **pure** scoring engine. It:

- Accepts an already-validated `nms.data.models.MarketContext`.
- Returns a `nms.core.ScoreBreakdown` containing component scores,
  the no-trade score, a list of human-readable no-trade reasons,
  and a classification.
- Performs **no I/O, no network access, no subprocess, no
  environment reads, and no broker / exchange / order code**.

The `nms/core/` package must not import any of the following
modules (enforced by `tests/test_core_scoring.py`):

- `json`, `pathlib`, `os`, `subprocess`, `socket`
- `urllib`, `urllib.request`, `urllib.error`, `urllib.parse`
- `http`, `http.client`, `requests`, `httpx`, `aiohttp`, `urllib3`
- `dotenv`
- `shutil`, `shelve`, `pickle`
- any broker / exchange SDK (e.g. `ib_insync`, `ccxt`,
  `alpaca_trade_api`, `metatrader5`)
- any FIX gateway

The only allowed imports in `nms/core/` are `__future__`,
`dataclasses`, `typing`, `math`, and `nms` (our own package).

## 2. Score Formulas (Implemented)

All scores are dimensionless and bounded. They are not
probabilities, predictions, or financial advice.

### 2.1 `direction_score` — range `[-1, +1]`

```
direction_score = clamp(DIRECTION_WEIGHTS["nikkei_night"] * s, -1, +1)
where s = clamp(nikkei_night_session.percent_change / PERCENT_CHANGE_SATURATION, -1, +1)
```

- `PERCENT_CHANGE_SATURATION = 2.0` (a 2% move saturates the
  normalizer at ±1.0).
- The other five slots in `DIRECTION_WEIGHTS` contribute `0.0`
  at MVP. See §3 for the rationale.

### 2.2 `volatility_score` — range `[0, 1]`

```
if volatility_context.atr_like <= VOLATILITY_BASELINE_GUARD:
    volatility_score = 0.0   # safe fallback
else:
    volatility_score = clamp(1 - realized_vol / atr_like, 0, 1)
```

- `VOLATILITY_BASELINE_GUARD = 1e-12` is a small positive constant
  used to detect non-positive baselines.

### 2.3 `event_risk_score` — range `[0, 1]`

```
event_risk_score = max(EVENT_IMPACT_TABLE[ev.impact.lower()] for ev in events)
                  if events else 0.0
```

- `EVENT_IMPACT_TABLE`:
  - `"high"`   → `1.0`
  - `"medium"` → `0.5`
  - `"low"`    → `0.25`
  - unrecognized / empty → `0.0`
- Event times are **not** parsed at MVP. The score is impact-only.
- The score is the **maximum** across all events, not a sum or an
  average. This is a conservative choice: a single high-impact
  event drives the score.

### 2.4 `alignment_penalty` — range `{0.0, 1.0}`

```
alignment_penalty = (
    1.0 if planned_side == "buy"  and direction_score < 0 else
    1.0 if planned_side == "sell" and direction_score > 0 else
    0.0
)
```

- `planned_side == "none"` always yields `0.0`.

### 2.5 `no_trade_score` — range `[0, 1]`

```
no_trade_score = clamp(
    0.40 * volatility_score
  + 0.40 * event_risk_score
  + 0.20 * alignment_penalty,
    0, 1
)
```

### 2.6 `classification` — one of three labels

```
if no_trade_score >= NO_TRADE_THRESHOLD:
    classification = "no-trade"
elif direction_score > 0:
    classification = "buy-only"
elif direction_score < 0:
    classification = "sell-only"
else:
    classification = "no-trade"   # direction == 0 exactly
```

- `NO_TRADE_THRESHOLD = 0.5`.

## 3. MVP Normalization Limitations

The `MarketContext` schema (defined in `docs/data-adapter-contract.md`
and `nms/data/models.py`) currently exposes daily percent changes
**only** for `nikkei_night_session.percent_change`. The other
fields carry absolute values (e.g. `us_equities.sp500`) that are
not directly comparable across sessions.

MVP normalization policy:

- `direction_score` uses only `nikkei_night_session.percent_change`
  via the bounded normalizer in §2.1.
- The other five slots in `DIRECTION_WEIGHTS` contribute `0.0`
  (neutral) at MVP. Their weights are reserved so that the sum
  remains `1.0` and so that future schema changes can activate
  them without changing the weight structure.
- We do **not** invent daily changes from absolute levels. Doing
  so would be a schema decision, not a scoring decision, and would
  require updating `docs/data-adapter-contract.md`,
  `nms/data/validate.py`, the fixture, and the tests in the same
  PR.

This means a typical MVP `direction_score` magnitude is small
(0.0–0.20) and is dominated by the overnight Nikkei move. This is
documented and accepted for the skeleton.

## 4. No-Trade Reasons

`ScoreBreakdown.no_trade_reasons` is a tuple of human-readable
strings. It is populated when the dominant contributors push the
session over `NO_TRADE_THRESHOLD`:

| Condition | Reason format |
| --- | --- |
| `event_risk_score >= EVENT_RISK_REASON_THRESHOLD` | `"event_risk:<name>"` where `<name>` is the first event with the max impact |
| `volatility_score >= VOLATILITY_REASON_THRESHOLD` | `"volatility_compression:<score>"` (3-decimal score) |
| `alignment_penalty > 0.0` | `"alignment_penalty:<planned_side>_vs_direction"` |

Both `EVENT_RISK_REASON_THRESHOLD` and `VOLATILITY_REASON_THRESHOLD`
are `0.5`, aligned with the classification threshold.

The reason list is **not** a probability, not a guarantee, and not
a prediction. It is an audit trail of the dominant contributors.

## 5. Non-Claims

- These scores do not predict the future.
- These scores are not probabilities.
- These scores are not a recommendation to take or avoid a trade.
- A high `no_trade_score` is **not** a guarantee that trading would
  have lost money, and a low `no_trade_score` is **not** a guarantee
  that trading would have made money.
- No PnL, Sharpe, win-rate, or expected-return claim is made or
  implied.

## 6. No I/O / No Network / No Broker Boundary

`nms/core/` is observation-only. It does not place orders, talk to
brokers, or write to any external system. Any future PR that
introduces an execution consumer of `ScoreBreakdown` requires:

- The operator charter in `AGENTS.md §4`.
- Updates to `docs/risk-policy.md`.
- A non-bootstrap review PR.

## 7. Relationship to `docs/market-regime-score.md`

`docs/market-regime-score.md` is the conceptual reference: it
explains what the scores mean and how they are used.

`docs/core-scoring-contract.md` (this document) is the
implementation reference: it pins down the exact formulas, the
exact constants, the MVP normalization limitations, and the
non-claims.

A short "Implementation note" section in
`docs/market-regime-score.md` points to this contract. The two
documents are kept in sync; if they disagree, this contract wins
and `docs/market-regime-score.md` is the bug.

## 8. Review Checklist for Scoring PRs

A reviewer of a new or modified scoring PR must confirm, at
minimum:

- [ ] `nms/core/` imports nothing outside the allowed set in §1.
- [ ] The AST and runtime purity tests in
      `tests/test_core_scoring.py` still pass.
- [ ] No score formula silently changes semantics; any change is
      documented here and in `docs/market-regime-score.md` in the
      same PR.
- [ ] No new runtime dependency is added.
- [ ] No PnL, Sharpe, win-rate, or expected-return claim appears
      in code, docs, or commit messages.
- [ ] The PR body lists the `must_not_do` set and the
      `no_trade_reasons` format.
