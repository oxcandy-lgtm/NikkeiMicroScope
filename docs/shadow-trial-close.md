# Shadow Trial Close

> Binding for any code path that records a shadow close
> ledger entry. Lower-priority instructions (chat, scripts,
> LLM completions) cannot override this document. If in
> conflict, this document wins.

This document defines the shadow-trial-close contract. It
specifies:

1. The purpose.
2. Why this is not paper trading.
3. Why this is not live trading.
4. Why this is not PnL.
5. Input requirements.
6. Source trial validation dependency.
7. Deterministic close ID.
8. Append-only close JSONL ledger.
9. ``executable=false`` invariant.
10. ``price_delta_points`` and ``directional_delta_points``
    definitions.
11. Non-claims.
12. Future path.

The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md)
§8.10.

## 1. Purpose

The shadow trial close is the **second step** toward no-cash
test trading. It records a separate, local-only close
record from:

* one existing shadow trial record (see PR #15 /
  [`docs/shadow-trial-ledger.md`](shadow-trial-ledger.md));
* an operator-provided ``close_price``;
* an operator-provided ``closed_at_utc``.

The close record is a **labeled measurement of price
movement** after a shadow trial intent. It is **not**:

* a paper execution;
* a live execution;
* a broker fill;
* a market fill;
* a position close;
* a realized gain/loss (gain/loss metric);
* a return calculation;
* a win-rate / risk-adjusted / forward-return metric.

## 2. Why this is not paper trading

Paper trading typically means a simulated order is placed
against a (possibly fake) book and the system tracks a
virtual position. The shadow close does **none** of these.
There is no order. There is no virtual position. There is
no gain/loss ledger. The close record is a labeled
measurement of price movement in the direction of the
planned side.

## 3. Why this is not live trading

Live trading typically means a real order is placed at a
real broker and real money is at risk. The shadow close
does **none** of these. There is no broker integration.
There is no real money. The record's :attr:`executable`
is always ``False`` in this PR.

## 4. Why this is not PnL

A realized gain/loss is a function of price movement AND
position size AND capital AND fees AND slippage. The
shadow close deliberately records only the raw arithmetic
price difference. There is no multiplier, no cash
conversion, no fees, no slippage, no position value, no
capital, no return percentage.

The shadow close is a labeled measurement of price
movement. It is not a PnL, not a return, not a win-rate,
not a risk-adjusted metric, not a forward-return metric.

## 5. Input requirements

A shadow close record is built from the following inputs:

* ``ledger_path``: a local JSONL file containing one or
  more :class:`nms.shadow.ledger.ShadowTrialRecord`
  payloads.
* ``trial_id``: the id of exactly one trial record in the
  ledger.
* ``close_price``: a positive number. Provided by the
  operator. The ledger does not fetch a live quote.
* ``closed_at_utc``: an ISO-8601 timestamp ending in ``"Z"``.
  Provided by the operator.

All inputs are validated by
:func:`nms.shadow.close.build_shadow_trial_close_record`.
Invalid inputs raise :class:`nms.shadow.close.ShadowTrialCloseError`.

## 6. Source trial validation dependency

The close depends on the
[`shadow trial ledger`](shadow-trial-ledger.md) introduced
in PR #15. The validator confirms the source trial satisfies:

* ``schema_version == "shadow-trial/1"``
* ``executable is False``
* ``blocked_reason == "shadow_trial_not_executable"``
* ``planned_side in {"buy", "sell", "none"}``
* ``reference_price > 0``
* ``trial_size > 0``
* ``created_at_utc`` ends with ``"Z"``

A source trial that fails any of these checks causes
:func:`build_shadow_trial_close_record` to raise
:class:`ShadowTrialCloseError`. The close never bypasses
this validation.

## 7. Deterministic close ID

Every record carries a deterministic ``close_id``. The id is
a SHA-256 hex digest over the tuple:

```yaml
canonical: "{source_ledger_sha256}|{trial_id}|{planned_side}|{reference_price:.6f}|{close_price:.6f}|{closed_at_utc}"
algorithm: SHA-256
```

The canonical string format is fixed so the close id is
byte-for-byte stable across runs. Two records with the
same input tuple produce the same ``close_id``. A change
in any component produces a different ``close_id``.

## 8. Append-only close JSONL ledger

The close ledger is a JSONL file (one compact JSON object
per line). Records are **appended**: the appender never
overwrites, deletes, or truncates existing records. The
appender creates the parent directory if needed.

The compact JSON form has no indentation. A trailing
newline is added by the appender so each line ends with
``\n``.

## 9. ``executable=false`` invariant

The record's :attr:`executable` is always ``False`` in this
PR. The record's :attr:`blocked_reason` is always the
constant :data:`nms.shadow.close.SHADOW_CLOSE_NOT_EXECUTABLE`.

The close ledger must never be wired into any code path
that places, routes, simulates, or transmits an order. A
future PR that wishes to relax this invariant must:

* be a separate PR;
* update this document and §8.10 of
  ``docs/data-adapter-contract.md``;
* cite the operator charter required by ``AGENTS.md §4``;
* be reviewed in a non-bootstrap PR.

## 10. ``price_delta_points`` and ``directional_delta_points`` definitions

```yaml
price_delta_points: close_price - reference_price
directional_delta_points:
  buy: close_price - reference_price
  sell: reference_price - close_price
  none: 0.0
```

These are **not** a gain/loss, not a return, not a
risk-adjusted metric, not a forward-return metric. They
are a labeled measurement of price movement. There is no
multiplier, no cash conversion, no fees, no slippage, no
position value, no capital, no return percentage.

The directional delta inverts for ``"sell"`` because the
direction the trade wanted to go is downward. For
``"none"`` (no planned trade), the directional delta is
always zero — the operator did not take a side, so price
movement is not a gain or a loss in any direction.

## 11. Non-claims

The shadow close is **not**:

* a new market data source;
* a SOX / semiconductor adapter;
* a broker / exchange / FIX / order-router adapter;
* a paper-trading executor;
* a live-trading system;
* a backtest or replay engine;
* a cash balance or virtual position state;
* a gain/loss / profit / loss / return / win-rate /
  risk-adjusted / forward-return / risk-adjusted ratio /
  expected-return engine;
* a signal or score;
* investment advice, a profit guarantee, or a
  recommendation.

The :data:`nms.shadow.close.SHADOW_CLOSE_NON_CLAIMS` tuple
on every record encodes these non-claims as
machine-readable strings. Operators and downstream tooling
can read this tuple to confirm the close is
observation-only.

## 12. Future path

The shadow close is the foundation for one operator-gated
future PR:

* **PR #17 (proposed; not in this PR)**: replay over
  historical artifacts. Only after operator review and a
  charter update per ``AGENTS.md §4``.

Any future live-trading or paper-execution work remains
charter-gated and out of scope for the shadow close layer.

## 13. Reviewer checklist

- [ ] ``nms/shadow/close.py`` does not import any of:
      ``requests``, ``httpx``, ``aiohttp``, ``dotenv``,
      ``subprocess``, ``os``, ``urllib``, ``urllib3``,
      ``yfinance``, ``pandas``, broker SDKs.
- [ ] ``tests/test_shadow_trial_close.py`` does not perform
      live network I/O, does not use ``subprocess``, and
      does not read environment credentials.
- [ ] The dry-run script uses local ledger input only. It
      does not hit live network.
- [ ] The record always has ``executable=False``.
- [ ] The record's ``blocked_reason`` is always
      ``shadow_close_not_executable``.
- [ ] The close ledger is append-only. Existing records
      are never overwritten, deleted, or truncated.
- [ ] ``close_id`` is deterministic.
- [ ] The close record has no PnL / profit / loss / return
      / win-rate / risk-adjusted / forward-return /
      risk-adjusted ratio / expected-return / position /
      cash_balance field.
- [ ] §8.10 of ``docs/data-adapter-contract.md`` is
      updated and links to this document.
- [ ] No new runtime dependency is added.
- [ ] No GitHub workflow file is changed.
