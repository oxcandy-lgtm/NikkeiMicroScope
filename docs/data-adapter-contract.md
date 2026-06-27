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
match the schema is rejected with `nms.data.ValidationError`. The
enforcement is **strict at every level**: unexpected keys are rejected
at the top level, at every nested object (`us_equities`, `fx`,
`volatility_context`, etc.), and at every item in
`economic_event_risk.events`. This is a defense-in-depth posture
that prevents the schema from silently growing to include account,
broker, order, or credential fields at any depth.

## 1. Schema (Canonical)

The top-level `MarketContext` is a single trading session's snapshot.
The validator rejects any top-level key outside the documented set —
this is a defense-in-depth check that prevents account / broker /
order fields from creeping in.

| Field | Type | Notes |
| --- | --- | --- |
| `session_date` | string | ISO-8601 calendar date, e.g. `"2026-06-24"`. |
| `timezone` | string | Must be `"Asia/Tokyo"` at MVP. |
| `us_equities` | object | Absolute levels (`sp500`, `dow`, `nasdaq100`, `russell2000`) and daily percent changes (`sp500_change_pct`, `nasdaq100_change_pct`). All numeric. |
| `semiconductor` | object | Absolute level (`sox`) and daily percent change (`sox_change_pct`). Both numeric. |
| `fx` | object | Absolute level (`usdjpy`, JPY per 1 USD) and daily percent change (`usdjpy_change_pct`). Both numeric. |
| `us_yields` | object | Absolute yields in percent (`us2y`, `us10y`), the 10y-2y spread (`us10y_minus_us2y`), and the daily change of the 10y yield in basis points (`us10y_change_bp`). All numeric. |
| `nikkei_night_session` | object | `close`, `high`, `low`, `range`, `percent_change`. |
| `previous_day` | object | `high`, `low`, `close`, `range`. |
| `economic_event_risk` | object | `events: [...]` (list of `{name, time_jst?, impact?}`). |
| `intraday_range` | object | `first_15m_high`, `first_15m_low`, `first_15m_range`, `atr_like_baseline`. |
| `volatility_context` | object | `realized_vol`, `atr_like`, `compression_flag` (bool). |

Numeric fields accept `int` or `float`. `bool` is **rejected** for
numeric fields (it is technically `int` in Python but is almost always
a schema bug).

**Absolute vs change fields.** Some context groups carry both an
absolute level and a daily change:

- `us_equities` carries the index level (`sp500`, etc.) and the
  daily percent change (`sp500_change_pct`, `nasdaq100_change_pct`).
- `semiconductor` carries the SOX level (`sox`) and the daily
  percent change (`sox_change_pct`).
- `fx` carries the USDJPY level (`usdjpy`) and the daily percent
  change (`usdjpy_change_pct`).
- `us_yields` carries the absolute yields in percent (`us2y`,
  `us10y`), the spread (`us10y_minus_us2y`), and the daily change
  of the 10y yield in **basis points** (`us10y_change_bp`). The
  bp unit is intentional: it is the unit the change is reported
  in by the upstream data source and the unit the scoring engine
  uses.

The change fields are the inputs to `direction_score` in
`nms/core/scoring.py`. The absolute fields are kept because
downstream reporting needs the absolute level for context even
though scoring uses the change.

**Nested strictness:** every nested object and every event item has
its own fixed key set, and the validator rejects any key outside that
set with `nms.data.ValidationError`. The allowed key sets are:

| Path | Allowed keys |
| --- | --- |
| `us_equities` | `sp500`, `dow`, `nasdaq100`, `russell2000`, `sp500_change_pct`, `nasdaq100_change_pct` |
| `semiconductor` | `sox`, `sox_change_pct` |
| `fx` | `usdjpy`, `usdjpy_change_pct` |
| `us_yields` | `us2y`, `us10y`, `us10y_minus_us2y`, `us10y_change_bp` |
| `nikkei_night_session` | `close`, `high`, `low`, `range`, `percent_change` |
| `previous_day` | `high`, `low`, `close`, `range` |
| `economic_event_risk` | `events` |
| `economic_event_risk.events[i]` | `name`, `time_jst`, `impact` |
| `intraday_range` | `first_15m_high`, `first_15m_low`, `first_15m_range`, `atr_like_baseline` |
| `volatility_context` | `realized_vol`, `atr_like`, `compression_flag` |

The set of allowed top-level keys is defined as
`_ALLOWED_TOP_KEYS` in `nms/data/validate.py`. The allowed key sets
for every nested object and for `EventItem` are defined as
`_ALLOWED_*_KEYS` constants in the same file. All are enforced by
`_reject_extra_keys`, which is called at the start of every
`_build_*` helper and at the start of each iteration of the events
loop.

Adding a new field at **any** level (top-level, nested, or inside an
event item) requires updating this document and the validator in
the same PR. The whitelist rules in `nms/data/validate.py` and the
table in this section are normative; if they disagree, the validator
wins and this document is the bug.

### 1.1 Fixture values are synthetic

The sample fixture at
`fixtures/market_context/sample-session-2026-06-24.json` is
**synthetic**. The numeric values are plausible shapes chosen to
exercise the schema and the scoring formulas; they are **not**
real historical data and must not be cited as such. Adapters that
read real data must override the sample values; the fixture is
the test input, not a market record.

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

## 8. Approved Network Adapters

The data layer is local-first at MVP. Network adapters must be
approved per the rules in this section before they can be merged.

### 8.1 `FredTreasuryOverlayAdapter` (first approved public no-auth network adapter)

`FredTreasuryOverlayAdapter` is the **first approved public, no-auth
network adapter** in NikkeiMicroScope. It is implemented in
`nms/data/fred_treasury.py` and is documented in full by
[`docs/fred-treasury-adapter.md`](fred-treasury-adapter.md). The
summary below is the contract view; the linked document is
authoritative for the implementation.

**What it reads:** only the two FRED series below, both public,
no-auth, no API key, downloaded as CSV over plain HTTPS.

| Series | Meaning | Unit |
| --- | --- | --- |
| DGS2 | U.S. Treasury 2-Year Constant Maturity | percent |
| DGS10 | U.S. Treasury 10-Year Constant Maturity | percent |

**What it overlays on the baseline `MarketContext`:** only the
four `us_yields` fields:

| Target field | Source |
| --- | --- |
| `us2y` | DGS2 value at the selected date |
| `us10y` | DGS10 value at the selected date |
| `us10y_minus_us2y` | `us10y - us2y` |
| `us10y_change_bp` | `(DGS10_today - DGS10_yesterday) * 100` |

**What it returns:** a new frozen, fully validated `MarketContext`.
The returned context is re-validated through
`validate_market_context` to enforce the schema and nested
strictness. The adapter does not mutate the base context; it
returns a new one with `us_yields` replaced.

**What it does NOT do:**

* No API key, no auth header, no cookie.
* No `.env`, no `os.environ.get` / `os.getenv` for credentials.
* No broker SDK, no order placement, no live trading.
* No subprocess, no shell-out.
* No new runtime dependency (stdlib only).
* No widening of the `MarketContext` schema.
* No silent fallback for missing data. If the previous DGS10
  observation needed to compute `us10y_change_bp` is missing,
  `FredTreasuryAdapterError` is raised. The adapter does not
  silently treat "missing" as "neutral".

**Required future-adapter pattern:** any future public network
adapter (equities, FX, SOX, Nikkei) must:

1. Implement the `MarketContextAdapter` protocol.
2. Update this section (`§8`) of this document with the new
   adapter's contract.
3. Link to a dedicated adapter doc (e.g.
   `docs/fred-treasury-adapter.md`) that is the authoritative
   reference for that adapter.
4. Add AST-level and runtime tests that mirror §3 and §4 of this
   contract.
5. Add a network-safety test that mocks `socket.socket`,
   `subprocess.*`, and `os.environ.get` during a representative
   `load(...)` call.
6. Never silently fall back to a neutral value on missing data.
   A missing input is a `FredTreasuryAdapterError` (or
   equivalent), not a "neutral contribution".

## 8.2 `FredSP500OverlayAdapter` (second approved public no-auth network adapter)

`FredSP500OverlayAdapter` is the **second approved public, no-auth
network adapter** in NikkeiMicroScope. It is implemented in
`nms/data/fred_sp500.py` and is documented in full by
[`docs/fred-sp500-adapter.md`](fred-sp500-adapter.md). The summary
below is the contract view; the linked document is authoritative
for the implementation.

**What it reads:** only the FRED series below, public, no-auth, no
API key, downloaded as CSV over plain HTTPS.

| Series | Meaning | Unit |
| --- | --- | --- |
| SP500 | S&P 500 Index | index level |

**What it overlays on the baseline `MarketContext`:** only the
two `us_equities` fields:

| Target field | Source |
| --- | --- |
| `us_equities.sp500` | SP500 value at the selected date |
| `us_equities.sp500_change_pct` | `((SP500_today / SP500_yesterday) - 1) * 100` |

All other `us_equities` fields (`dow`, `nasdaq100`, `russell2000`,
`nasdaq100_change_pct`) and all other `MarketContext` sections
come from the base adapter and are left unchanged.

**What it returns:** a new frozen, fully validated `MarketContext`.
The returned context is re-validated through
`validate_market_context` to enforce the schema and nested
strictness. The adapter does not mutate the base context; it
returns a new one with the two `us_equities` fields replaced.

**What it does NOT do:**

* No API key, no auth header, no cookie.
* No `.env`, no `os.environ.get` / `os.getenv` for credentials.
* No broker SDK, no order placement, no live trading.
* No subprocess, no shell-out.
* No new runtime dependency (stdlib only).
* No widening of the `MarketContext` schema.
* No silent fallback for missing data. If the previous SP500
  observation needed to compute `sp500_change_pct` is missing,
  `FredSP500AdapterError` is raised. If the previous SP500 value
  is non-positive, `FredSP500AdapterError` is raised. The adapter
  does not silently treat "missing" or "non-positive" as a neutral
  contribution.

## 8.3 `FredUSDJPYOverlayAdapter` (third approved public no-auth network adapter)

`FredUSDJPYOverlayAdapter` is the **third approved public, no-auth
network adapter** in NikkeiMicroScope. It is implemented in
`nms/data/fred_usdjpy.py` and is documented in full by
[`docs/fred-usdjpy-adapter.md`](fred-usdjpy-adapter.md). The
summary below is the contract view; the linked document is
authoritative for the implementation.

**What it reads:** only the FRED series below, public, no-auth, no
API key, downloaded as CSV over plain HTTPS.

| Series | Meaning | Unit |
| --- | --- | --- |
| DEXJPUS | Japanese Yen to U.S. Dollar Spot Exchange Rate | Japanese yen to one U.S. dollar |

**What it overlays on the baseline `MarketContext`:** only the
two `fx` fields:

| Target field | Source |
| --- | --- |
| `fx.usdjpy` | DEXJPUS value at the selected date |
| `fx.usdjpy_change_pct` | `((DEXJPUS_today / DEXJPUS_yesterday) - 1) * 100` |

All other `MarketContext` sections come from the base adapter and
are left unchanged.

**What it returns:** a new frozen, fully validated `MarketContext`.
The returned context is re-validated through
`validate_market_context` to enforce the schema and nested
strictness. The adapter does not mutate the base context; it
returns a new one with the two `fx` fields replaced. The `load()`
method is annotated as returning `MarketContext`.

**What it does NOT do:**

* No API key, no auth header, no cookie.
* No `.env`, no `os.environ.get` / `os.getenv` for credentials.
* No broker SDK, no order placement, no live trading.
* No subprocess, no shell-out.
* No new runtime dependency (stdlib only).
* No widening of the `MarketContext` schema.
* No silent fallback for missing data. If the previous DEXJPUS
  observation needed to compute `usdjpy_change_pct` is missing,
  `FredUSDJPYAdapterError` is raised. If the previous DEXJPUS
  value is non-positive, `FredUSDJPYAdapterError` is raised. The
  adapter does not silently treat "missing" or "non-positive" as
  a neutral contribution.

## 8.4 `FredNASDAQ100OverlayAdapter` (fourth approved public no-auth network adapter)

`FredNASDAQ100OverlayAdapter` is the **fourth approved public,
no-auth network adapter** in NikkeiMicroScope. It is implemented in
`nms/data/fred_nasdaq100.py` and is documented in full by
[`docs/fred-nasdaq100-adapter.md`](fred-nasdaq100-adapter.md). The
summary below is the contract view; the linked document is
authoritative for the implementation.

**What it reads:** only the FRED series below, public, no-auth, no
API key, downloaded as CSV over plain HTTPS.

| Series | Meaning | Unit | Frequency |
| --- | --- | --- | --- |
| NASDAQ100 | NASDAQ-100 Index | Index | Daily, Close |

> **This is NASDAQ-100, not Nasdaq Composite.** The FRED series id
> is exactly `NASDAQ100`.

**What it overlays on the baseline `MarketContext`:** only the
two `us_equities` fields:

| Target field | Source |
| --- | --- |
| `us_equities.nasdaq100` | NASDAQ100 value at the selected date |
| `us_equities.nasdaq100_change_pct` | `((NASDAQ100_today / NASDAQ100_yesterday) - 1) * 100` |

All other `MarketContext` sections come from the base adapter and
are left unchanged.

**What it returns:** a new frozen, fully validated `MarketContext`.
The returned context is re-validated through
`validate_market_context` to enforce the schema and nested
strictness. The adapter does not mutate the base context; it
returns a new one with the two `us_equities` fields replaced. The
`load()` method is annotated as returning `MarketContext`.

**What it does NOT do:**

* No API key, no auth header, no cookie.
* No `.env`, no `os.environ.get` / `os.getenv` for credentials.
* No broker SDK, no order placement, no live trading.
* No subprocess, no shell-out.
* No new runtime dependency (stdlib only).
* No widening of the `MarketContext` schema.
* No silent fallback for missing data. If the previous NASDAQ100
  observation needed to compute `nasdaq100_change_pct` is missing,
  `FredNASDAQ100AdapterError` is raised. If the previous NASDAQ100
  value is non-positive, `FredNASDAQ100AdapterError` is raised. The
  adapter does not silently treat "missing" or "non-positive" as a
  neutral contribution.
* **No raw NASDAQ100 data is committed as a fixture or exported.**
  The FRED `NASDAQ100` series is sourced from Nasdaq, Inc. and is
  subject to the standard FRED citation / pre-approval policy.
  The adapter is for operator-side observation only; downstream
  redistribution of raw NASDAQ100 observations is out of scope
  and requires operator/legal review.

## 8.5 Future SOX / semiconductor source selection

No SOX adapter is approved yet.

The source-selection contract lives in
[`docs/sox-source-selection.md`](sox-source-selection.md). The
contract evaluates at least one exact-index candidate and the two
obvious ETF proxies (`SOXX`, `SMH`), and records the current
decision. The current decision is
`defer_adapter` — no reviewed public no-auth exact SOX source has
been confirmed yet.

Until a future PR updates §8.5 and the source-selection document
to a `preferred` or `acceptable` outcome:

- no adapter may write `semiconductor.sox`
- no adapter may write `semiconductor.sox_change_pct`
- no ETF proxy may be labeled as exact SOX
- no raw index data may be committed or exported
- no broker, auth, cookie, or paid source may be introduced
  as a SOX / semiconductor source

## 8.6 Adapter composition

`ComposedMarketContextAdapter` composes approved
`MarketContextAdapter` instances into one final validated
`MarketContext`. The composition layer is documented in full by
[`docs/adapter-composition.md`](adapter-composition.md). The
summary below is the contract view; the linked document is
authoritative.

This composition layer:

- does not approve new sources
- does not perform network I/O by itself
- may only compose already-approved adapters
- must not include a SOX adapter until §8.5 is updated
- must not introduce broker / auth / cookie / paid source paths
- must re-validate the final `MarketContext`
- must not add a default live production pipeline
- must stop at the first failure, wrapping the original
  exception in `AdapterCompositionError` with stage-name
  (construction failure) or session-date (load failure) metadata

## 8.7 Composed MarketContext JSON export

`nms.data.export` may serialize a validated `MarketContext`
into deterministic JSON. The export layer is documented in
full by [`docs/market-context-export.md`](market-context-export.md).
The summary below is the contract view; the linked document
is authoritative.

This export layer:

- does not approve new sources
- does not perform network I/O
- must re-validate before writing
- must write deterministic UTF-8 JSON
  (`ensure_ascii=False`, `indent=2`, `sort_keys=True`,
  trailing newline)
- must refuse overwrite by default
- must not include a SOX adapter until §8.5 is updated
- must not introduce broker / auth / cookie / paid source
  paths
- must not be treated as backtest, paper trading, or live
  trading
- must not add a default live pipeline
- must not commit raw FRED CSV to `exports/`, `fixtures/`,
  or `reports/`

## 8.8 MarketContext artifact validation report

`nms.data.artifact_report` may read an exported
`MarketContext` JSON artifact and produce a deterministic
read-only validation report. The report layer is documented
in full by
[`docs/market-context-artifact-report.md`](market-context-artifact-report.md).
The summary below is the contract view; the linked document
is authoritative.

This report layer:

- does not approve new sources
- does not perform network I/O
- must not widen the `MarketContext` schema
- may strip allowed artifact metadata
  (`synthetic`, `_dry_run_meta`) before schema validation
- must report populated approved fields
- must report SOX / unapproved fields as unapproved, not
  missing bugs
- must not include broker / auth / cookie / paid source
  paths
- must not be treated as score, signal, backtest, paper
  trading, or live trading
- must not add a default live pipeline
- must not commit raw FRED CSV to `exports/`, `fixtures/`,
  or `reports/`
