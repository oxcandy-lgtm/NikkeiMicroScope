# Shadow Trial Ledger

> Binding for any code path that records a shadow trial
> ledger entry. Lower-priority instructions (chat, scripts,
> LLM completions) cannot override this document. If in
> conflict, this document wins.

This document defines the shadow-trial-ledger contract. It
specifies:

1. The purpose.
2. Why this is not paper trading.
3. Why this is not live trading.
4. Input requirements.
5. Artifact validation dependency.
6. Scoring dependency.
7. Deterministic trial ID.
8. Append-only JSONL ledger.
9. ``executable=false`` invariant.
10. Non-claims.
11. Future path.

The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md)
§8.9.

## 1. Purpose

The shadow trial ledger is the **first step** toward no-cash
test trading. It records a deterministic local ledger entry
saying:

> Given this validated MarketContext artifact, this planned
> side, this reference price, and this timestamp, NMS would
> have recorded a shadow trial intent with this score /
> classification context.

The ledger is an **observation artifact** only. It does not
place orders, route orders, simulate fills, connect to a
broker, or transmit any side-effect to the real world. There
is no real cash, no real broker, no real execution.

## 2. Why this is not paper trading yet

Paper trading typically means:

* A simulated order is placed against a (possibly fake) book.
* The system tracks a virtual position.
* The system computes PnL on close.

The shadow trial ledger does **none** of these. There is no
order. There is no virtual position. There is no PnL. The
ledger is a recorded intent: "given this validated context
and this planned side, NMS would have observed this score
context result".

A future PR (see §11) may add a virtual fill model and a
virtual PnL ledger, but only after operator review.

## 3. Why this is not live trading

Live trading typically means:

* A real order is placed at a real broker.
* Real money is at risk.
* PnL is realized.

The shadow trial ledger does **none** of these. There is no
broker integration. There is no real money. There is no
realized PnL. The record's :attr:`executable` is always
``False`` in this PR.

## 4. Input requirements

A shadow trial record is built from the following inputs:

* ``artifact_path``: a local JSON file containing a
  :class:`MarketContext` payload (see PR #13 / §8.7).
* ``planned_side``: one of ``"buy"``, ``"sell"``, ``"none"``.
  Provided by the operator. The ledger does not auto-select a
  side.
* ``reference_price``: a positive number. Provided by the
  operator. The ledger does not fetch a live quote.
* ``trial_size``: a positive integer. Provided by the
  operator.
* ``created_at_utc``: an ISO-8601 timestamp ending in ``"Z"``.
  Provided by the operator.
* ``expect_synthetic``: optional. If ``True``, the artifact
  must declare ``synthetic: true`` and ``_dry_run_meta`` with
  ``live_fred_used: false``.

All inputs are validated by
:func:`nms.shadow.ledger.build_shadow_trial_record`. Invalid
inputs raise :class:`nms.shadow.ledger.ShadowTrialLedgerError`.

## 5. Artifact validation dependency

The ledger depends on the
[`MarketContext` artifact validator](market-context-artifact-report.md)
introduced in PR #14 / §8.8. The validator is called with
``expect_synthetic=...``. If the report is not ``ok``, the
ledger raises :class:`ShadowTrialLedgerError`. The ledger
never bypasses the validator.

## 6. Scoring dependency

The ledger depends on the existing pure scoring engine in
`nms.core.scoring` (see
[`docs/core-scoring-contract.md`](core-scoring-contract.md) and
[`docs/market-regime-score.md`](market-regime-score.md)). The
engine is **unchanged** by this PR. The ledger uses the
existing :func:`nms.core.scoring.score_context` function and
snapshots the result into a
:class:`ShadowTrialScoreSnapshot` so the ledger does not
need to keep a reference to the live engine.

## 7. Deterministic trial ID

Every record carries a deterministic ``trial_id``. The id is
a SHA-256 hex digest over the tuple:

```yaml
canonical: "{artifact_sha256}|{session_date}|{planned_side}|{reference_price:.6f}|{trial_size}|{created_at_utc}"
algorithm: SHA-256
```

The canonical string format is fixed so the trial id is
byte-for-byte stable across runs. Two records with the same
input tuple produce the same ``trial_id``. A change in any
component produces a different ``trial_id``.

## 8. Append-only JSONL ledger

The ledger is a JSONL file (one compact JSON object per
line). Records are **appended**: the appender never
overwrites, deletes, or truncates existing records. The
appender creates the parent directory if needed.

The compact JSON form has no indentation. A trailing newline
is added by the appender so each line ends with ``\n``.

## 9. ``executable=false`` invariant

The record's :attr:`executable` is always ``False`` in this
PR. The record's :attr:`blocked_reason` is always the
constant :data:`nms.shadow.ledger.SHADOW_TRIAL_NOT_EXECUTABLE`.

The ledger must never be wired into any code path that
places, routes, simulates, or transmits an order. A future
PR that wishes to relax this invariant must:

* be a separate PR;
* update this document and §8.9 of
  ``docs/data-adapter-contract.md``;
* cite the operator charter required by ``AGENTS.md §4``;
* be reviewed in a non-bootstrap PR.

## 10. Non-claims

The shadow trial ledger is **not**:

* a new market data source;
* a SOX / semiconductor adapter;
* a broker / exchange / FIX / order-router adapter;
* a paper-trading executor;
* a live-trading system;
* a backtest or replay engine;
* a PnL / win-rate / risk-adjusted / forward-return engine;
* a signal or score;
* investment advice, a profit guarantee, or a
  recommendation.

The :data:`nms.shadow.ledger.SHADOW_TRIAL_NON_CLAIMS` tuple
on every record encodes these non-claims as machine-readable
strings. Operators and downstream tooling can read this
tuple to confirm the ledger is observation-only.

## 11. Future path

The shadow trial ledger is the foundation for two
operator-gated future PRs:

* **PR #16 (proposed; not in this PR)**: explicit close-price
  shadow fill and a virtual PnL ledger. Only after operator
  review and a charter update per ``AGENTS.md §4``.
* **PR #17 (proposed; not in this PR)**: replay over
  historical artifacts. Only after operator review and a
  charter update per ``AGENTS.md §4``.

Until those PRs land, the ledger remains an observation
artifact. There is no virtual fill and no PnL.

## 12. Reviewer checklist

- [ ] ``nms/shadow/ledger.py`` does not import any of:
      ``requests``, ``httpx``, ``aiohttp``, ``dotenv``,
      ``subprocess``, ``os``, ``urllib``, ``urllib3``,
      ``yfinance``, ``pandas``, broker SDKs.
- [ ] ``tests/test_shadow_trial_ledger.py`` does not perform
      live network I/O, does not use ``subprocess``, and
      does not read environment credentials.
- [ ] The dry-run script uses local artifact input only. It
      does not hit live network.
- [ ] The record always has ``executable=False``.
- [ ] The record's ``blocked_reason`` is always
      ``shadow_trial_not_executable``.
- [ ] The JSONL ledger is append-only. Existing records are
      never overwritten, deleted, or truncated.
- [ ] ``trial_id`` is deterministic.
- [ ] §8.9 of ``docs/data-adapter-contract.md`` is updated
      and links to this document.
- [ ] No new runtime dependency is added.
- [ ] No GitHub workflow file is changed.
