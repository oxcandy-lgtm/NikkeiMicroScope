# Data Adapter Contract — NikkeiMicroScope (NMS)

> Binding for any code path that reads market context data into NMS.
> Lower-priority instructions (chat, scripts, LLM completions) cannot
> override this document. If in conflict, this document wins.

This contract defines:

1. The **normalized** `MarketContext` schema.
2. The **adapter interface** and the **fixture-backed implementation**.
3. The rules any **future adapter** (network, database, mock) must obey.
4. The **observation-only** posture that keeps NMS out of execution.

The corresponding schema is enforced at runtime by
`nms.data.validate.validate_market_context`. Any payload that does not
match the schema is rejected with `nms.data.ValidationError`.

## 1. Schema (Canonical)

The top-level `MarketContext` is a single trading session's snapshot.
The validator rejects any top-level key outside the documented set —
this is a defense-in-depth check that prevents account / broker /
order fields from creeping in.

| Field | Type | Notes |
| --- | --- | --- |
| `session_date` | string | ISO-8601 calendar date, e.g. `"2026-06-24"`. |
| `timezone` | string | Must be `"Asia/Tokyo"` at MVP. |
| `us_equities` | object | `sp500`, `dow`, `nasdaq100`, `russell2000` (all numeric). |
| `semiconductor` | object | `sox` (numeric). |
| `fx` | object | `usdjpy` (numeric, JPY per 1 USD). |
| `us_yields` | object | `us2y`, `us10y`, `us10y_minus_us2y` (numeric, percent). |
| `nikkei_night_session` | object | `close`, `high`, `low`, `range`, `percent_change`. |
| `previous_day` | object | `high`, `low`, `close`, `range`. |
| `economic_event_risk` | object | `events: [...]` (list of `{name, time_jst?, impact?}`). |
| `intraday_range` | object | `first_15m_high`, `first_15m_low`, `first_15m_range`, `atr_like_baseline`. |
| `volatility_context` | object | `realized_vol`, `atr_like`, `compression_flag` (bool). |

Numeric fields accept `int` or `float`. `bool` is **rejected** for
numeric fields (it is technically `int` in Python but is almost always
a schema bug).

The set of allowed top-level keys is defined as
`_ALLOWED_TOP_KEYS` in `nms/data/validate.py`. Adding a new top-level
key requires updating both this document and the validator in the
same PR.

## 2. Adapter Interface

```python
class MarketContextAdapter(Protocol):
    def load(self, session_date: str) -> MarketContext: ...
```

The MVP ships only `FixtureMarketContextAdapter`. It is the reference
implementation and the test target.

`FixtureMarketContextAdapter`:

- Constructor: `FixtureMarketContextAdapter(base_path, filename_template)`.
  - `base_path` defaults to `"fixtures/market_context"`.
  - `filename_template` defaults to `"sample-session-{session_date}.json"`.
- `load(session_date)` opens `<base_path>/<filename_template.format(session_date=...)>`,
  parses JSON, validates against the schema, and returns a
  `MarketContext`.
- The `sample-session-` filename prefix is intentional: the fixture
  adapter is for sample / development data only. A real data adapter
  must use a different class and pass review per §4.

## 3. Required Behavior (All Adapters)

Any class that satisfies `MarketContextAdapter` MUST:

- Be **read-only**: no writes to the network, no writes to any
  external system, no writes to disk outside the local test/cache
  paths.
- Perform **no network access** at MVP. A network adapter is a future
  change and requires a separate PR (see §4).
- Perform **no subprocess / shell-out** to fetch or compute data.
- Read **no environment-variable credentials**. Adapter code MUST NOT
  call `os.environ.get`, `os.getenv`, or load `.env` files.
- Import **no broker SDK**, exchange client, or FIX gateway. NMS is
  observation-only; the charter gate in `AGENTS.md §4` applies to any
  future change that would weaken this rule.
- Return a `MarketContext` that passes `validate_market_context`.
  Adapters may validate eagerly (recommended) or lazily, but the
  caller must never see an unvalidated object.

These rules are enforced by `tests/test_fixture_loader.py` for the
fixture adapter and must be re-enforced for any future adapter in the
same PR that introduces it.

## 4. Adding a Future Adapter

Adding a new adapter (e.g. a public-data HTTP fetcher, a CSV loader,
a database reader) requires:

1. A PR that updates this document with the new adapter's contract.
2. The new adapter MUST implement the `MarketContextAdapter` protocol.
3. The PR MUST add tests that mirror `tests/test_fixture_loader.py`:
   - AST check that the new adapter does not import any forbidden
     module.
   - Runtime mock of `socket.socket` and `subprocess.*` during a
     representative `load(...)` call.
   - Runtime mock of `os.environ.get` / `os.getenv` during the same
     call.
4. The PR MUST NOT widen the schema unless the schema change is
   reviewed in the same PR. Schema changes update both this document
   and `nms/data/validate.py` in the same PR.
5. If the adapter needs a new runtime dependency, the PR MUST justify
   it in the PR body and update `pyproject.toml`. NMS prefers no new
   runtime dependencies; stdlib-only is the default.

## 5. Public / No-Auth-Only MVP Posture

At MVP, all data sources must be:

- **Public**: no paywall, no login, no API key.
- **No-auth**: no authentication, no token, no cookie.
- **Reproducible**: the same input must produce the same
  `MarketContext` for the same `session_date`.

If a future data source requires auth, that is a future PR and must
not be merged before the operator charter in `AGENTS.md §4` is
extended to cover credentialed data sources.

## 6. No Broker / No Live Trading Boundary

This package is observation-only. The data layer produces a
`MarketContext`; nothing in this package consumes that context to
place orders, talk to a broker, or alter any external system state.

Any future PR that introduces an execution consumer of
`MarketContext` requires:

- The operator charter in `AGENTS.md §4`.
- Updates to `docs/risk-policy.md`.
- A non-bootstrap review PR.

Until those exist, the data layer's `load(...)` must not be called
from any code path that could place an order.

## 7. Review Checklist for Adapter PRs

A reviewer of a new or modified adapter PR must confirm, at minimum:

- [ ] The adapter class satisfies `MarketContextAdapter`.
- [ ] The new tests cover the AST and runtime checks from §3 and §4.
- [ ] No new top-level fields in `MarketContext` unless the schema
      change is reviewed in this PR.
- [ ] No new runtime dependency unless justified in the PR body.
- [ ] No environment-variable credential reads.
- [ ] No network access (or, for a future network adapter, the PR
      body justifies why this is the right time to introduce it and
      cites the operator charter).
- [ ] The PR body lists the new `must_not_do` set if any were relaxed.
