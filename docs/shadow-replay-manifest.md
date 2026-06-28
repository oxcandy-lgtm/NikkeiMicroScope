# Shadow Replay Manifest

> Binding for any code path that runs a shadow replay.
> Lower-priority instructions (chat, scripts, LLM
> completions) cannot override this document. If in
> conflict, this document wins.

This document defines the shadow-replay-manifest contract.
It specifies:

1. The purpose.
2. Why this is not backtest.
3. Why this is not paper trading.
4. Why this is not live trading.
5. Input manifest shape.
6. Output manifest shape.
7. Append-only behavior.
8. Row-level error behavior.
9. Non-claims.
10. Future path.

The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md)
§8.11.

## 1. Purpose

The shadow replay manifest is the **third step** toward
no-cash test trading. It runs a local append-only replay
over a manifest of ``MarketContext`` artifacts and
operator-provided inputs. For each row, the replay
creates a :class:`nms.shadow.ledger.ShadowTrialRecord` and
(optionally) a
:class:`nms.shadow.close.ShadowTrialCloseRecord`.

The replay records only counts and per-row statuses. It
does **not** compute or report aggregate money deltas,
performance ratios, win rates, returns, or any other
performance metric. It is not a backtest.

## 2. Why this is not backtest

A backtest typically runs a strategy over historical
data and reports aggregate performance metrics (PnL,
return, win rate, Sharpe, etc.). The shadow replay manifest
does **none** of these. It records only counts and
per-row statuses. It is a deterministic observation of
"what the shadow trial pipeline produced for each row".

## 3. Why this is not paper trading

Paper trading typically means a simulated order is
placed against a (possibly fake) book and the system
tracks a virtual position. The shadow replay does
**none** of these. There is no order. There is no
virtual position. The replay only records what the
shadow trial pipeline produced.

## 4. Why this is not live trading

Live trading typically means a real order is placed at
a real venue and real money is at risk. The shadow replay
does **none** of these. There is no venue integration.
There is no real money.

## 5. Input manifest shape

The input manifest is a local JSON file with schema
version :data:`nms.shadow.replay.SHADOW_REPLAY_INPUT_SCHEMA_VERSION`.

```yaml
schema_version: shadow-replay-input/1
rows:
  - row_id: str (unique)
    artifact_path: str (local JSON file path)
    planned_side: "buy" | "sell" | "none"
    reference_price: float (> 0)
    trial_size: int (> 0)
    trial_created_at_utc: str (ends with "Z")
    close_price: float (> 0) (optional)
    closed_at_utc: str (ends with "Z") (optional)
    expect_synthetic: bool
```

If both ``close_price`` and ``closed_at_utc`` are present,
the row creates both a trial record and a close record.
If both are absent, the row creates only a trial record.
One present and the other absent is rejected at load
time.

## 6. Output manifest shape

The output manifest is a deterministic JSON file with
schema version
:data:`nms.shadow.replay.SHADOW_REPLAY_RESULT_SCHEMA_VERSION`.

```yaml
schema_version: shadow-replay-result/1
input_manifest_sha256: str (hex SHA-256)
created_at_utc: str (ends with "Z")
requested_rows: int
valid_rows: int
trial_records_created: int
close_records_created: int
rows:
  - row_id: str
    status: "close_created" | "trial_created" | "row_error"
    trial_id: str | null
    close_id: str | null
    error: str | null
non_claims: list[str]
```

The output manifest deliberately does **not** include:

* aggregate directional delta;
* average delta;
* total delta;
* score distribution;
* win/loss count;
* return;
* PnL;
* performance metric;
* equity curve;
* portfolio balance.

## 7. Append-only behavior

The replay is **append-only**: existing trial and close
records in the destination ledgers are never overwritten,
deleted, or truncated. The replay always appends new
records. The result manifest itself refuses to overwrite
an existing file unless ``allow_overwrite=True``.

## 8. Row-level error behavior

Row-level errors are captured and the replay continues.
There is no rollback. The replay is not a transaction
system. If a row's close fails after the trial append,
the trial append is preserved and the row is marked as
``row_error`` with the close error. This is a
deliberate design choice: the trial ledger is the source
of truth for what was attempted, and the result manifest
is the source of truth for what succeeded.

## 9. Non-claims

The shadow replay manifest is **not**:

* a new market data source;
* a SOX / semiconductor adapter;
* a venue / exchange / FIX / order-router adapter;
* a paper-trading executor;
* a live-trading system;
* a backtest or replay engine for strategy performance;
* a capital account or virtual exposure state;
* a money-delta / ratio / risk-adjusted / forward-return /
  expected-return / win-count / equity-curve / portfolio /
  strategy-performance engine;
* a signal or score;
* investment advice, a profit guarantee, or a
  recommendation.

The :data:`nms.shadow.replay.SHADOW_REPLAY_NON_CLAIMS` tuple
on every result manifest encodes these non-claims as
machine-readable strings. Operators and downstream
tooling can read this tuple to confirm the replay is
observation-only.

## 10. Future path

The shadow replay manifest is the foundation for one
operator-gated future direction:

* A separate operator-chartered PR may add report
  summaries that aggregate per-row results. That work is
  charter-gated and out of scope for this PR.

Any future backtest / paper-trading / live-trading work
remains charter-gated and out of scope for the shadow
replay layer.

## 11. Reviewer checklist

- [ ] ``nms/shadow/replay.py`` does not import any of:
      ``requests``, ``httpx``, ``aiohttp``, ``dotenv``,
      ``subprocess``, ``os``, ``urllib``, ``urllib3``,
      ``yfinance``, ``pandas``, venue SDKs.
- [ ] ``tests/test_shadow_replay_manifest.py`` does not
      perform live network I/O, does not use ``subprocess``,
      and does not read environment credentials.
- [ ] The dry-run script uses local files only. It does
      not hit live network.
- [ ] The result manifest contains only counts and
      per-row statuses. It does not contain aggregate
      delta / average delta / total delta / score
      distribution / win-loss count / return / PnL /
      performance metric / equity curve / portfolio
      fields.
- [ ] §8.11 of ``docs/data-adapter-contract.md`` is
      updated and links to this document.
- [ ] No new runtime dependency is added.
- [ ] No GitHub workflow file is changed.
