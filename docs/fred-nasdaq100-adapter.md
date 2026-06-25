# FRED NASDAQ100 Adapter Contract

> Binding for any code path that fetches or parses NASDAQ-100 daily
> observations from FRED. Lower-priority instructions (chat, scripts,
> LLM completions) cannot override this document. If in conflict,
> this document wins.

This document defines the FRED public NASDAQ-100 adapter contract.
It specifies:

1. What the adapter reads.
2. What the adapter does not read.
3. The mapping into `MarketContext.us_equities`.
4. Missing-value handling.
5. The date-selection rule.
6. The no-auth / no-secret posture.
7. The copyright / redistribution guard.
8. The test strategy.
9. Non-claims.

## 1. Scope

The FRED NASDAQ-100 adapter is the **fourth approved public, no-auth
network adapter** in NikkeiMicroScope. It is implemented in
`nms/data/fred_nasdaq100.py` and is documented in full by this
document. The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md) §8.4.

**What it reads:** only the FRED series below, public, no-auth, no
API key, downloaded as CSV over plain HTTPS.

| Series | Meaning | Unit | Frequency |
| --- | --- | --- | --- |
| NASDAQ100 | NASDAQ-100 Index | Index | Daily, Close |

URL: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQ100`

Source: Nasdaq, Inc. (release: Nasdaq Daily Index Data).

Higher value means stronger NASDAQ-100 (risk-on).

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
returns a new one with the two `us_equities` fields replaced.

## 2. What the Adapter Does Not Read

The adapter does **not** read:

* Any authenticated FRED API (the FRED API requires a key; this
  adapter does not use it).
* S&P 500, SOX, Nikkei, or USDJPY data.
* Any environment variables for credentials.
* Any `.env` file.
* Any `os.environ.get` / `os.getenv` value.
* Any subprocess, shell, or external process output.
* Any broker / exchange / order / account information.

## 3. Mapping into `MarketContext.us_equities`

The adapter **overlays only** the following two fields on the
`us_equities` dataclass of the baseline `MarketContext`:

| Target field | Source |
| --- | --- |
| `nasdaq100` | NASDAQ100 value at the selected date |
| `nasdaq100_change_pct` | `((NASDAQ100_today / NASDAQ100_yesterday) - 1.0) * 100.0` |

All other `us_equities` fields are preserved unchanged:

| Field | Source |
| --- | --- |
| `sp500` | base adapter |
| `dow` | base adapter |
| `russell2000` | base adapter |
| `sp500_change_pct` | base adapter |

All other `MarketContext` sections come from the base adapter and
are left unchanged:

* `semiconductor`
* `fx`
* `us_yields`
* `nikkei_night_session`
* `previous_day`
* `economic_event_risk`
* `intraday_range`
* `volatility_context`

The resulting `MarketContext` is re-validated through
`validate_market_context` to enforce the schema and nested
strictness.

## 4. Date-Selection Rule

For a given `session_date`:

1. The latest NASDAQ100 observation at or before `session_date` is
   selected. If none exists, `FredNASDAQ100AdapterError` is raised.
2. The previous NASDAQ100 observation (strictly before the
   selected date) is used to compute `nasdaq100_change_pct`. **If
   none exists, `FredNASDAQ100AdapterError` is raised.** A missing
   previous observation is never silently treated as a neutral
   contribution: that would corrupt downstream scoring by making
   "missing" indistinguishable from "zero change".
3. If the previous NASDAQ100 value is non-positive (≤ 0),
   `FredNASDAQ100AdapterError` is raised. A non-positive previous
   value would cause a division by zero or sign flip in the percent
   change calculation.

## 5. Missing-Value Handling

FRED rows with a missing value (`"."`) are ignored entirely — they
do not affect the date-selection logic. If the CSV contains no
usable rows (e.g. only the header, or only `""` / `"."` rows),
`FredNASDAQ100AdapterError` is raised.

Rows with malformed dates or malformed numeric values cause
`FredNASDAQ100AdapterError`.

## 6. No-Auth / No-Secret Posture

The adapter is public/no-auth:

* No API key.
* No auth header.
* No cookie.
* No `.env` file.
* No environment variable credential reading.
* No subprocess / shell-out.

The default HTTP GET uses `urllib.request` with no headers. Tests
inject a fake `http_get` callable and prove that no socket,
subprocess, or environment-variable access is performed.

## 7. Copyright / Redistribution Guard

The FRED `NASDAQ100` series is sourced from **Nasdaq, Inc.** and is
subject to the standard FRED citation / pre-approval policy. To
stay within the bounds of that policy, this PR is intentionally
conservative:

* **No raw downloaded NASDAQ100 data is committed as a fixture.**
  All test CSVs and the dry-run CSV are small synthetic examples
  with low-magnitude placeholder values. They are not from a real
  FRED download.
* **No raw NASDAQ100 export is produced by this PR.** No export
  path is created or modified; the existing `exports/` directory
  contains only `satellite-health.json` and
  `satellite-update-plan.json` and remains unchanged.
* The adapter is for **operator-side observation only.** Operators
  may use it at runtime to overlay the two `us_equities` fields
  for downstream scoring, but downstream redistribution of raw
  NASDAQ100 observations is out of scope and requires
  operator/legal review.
* The dry-run script uses synthetic CSV text and an injected
  `http_get`. It does not perform any network I/O.

## 8. Test Strategy

The adapter is exercised by:

* Parser unit tests (no HTTP, no subprocess, no env reads).
* Adapter unit tests with injected `http_get` and either a
  fixture-backed `MarketContextAdapter` or a stub base adapter.
* Negative tests for:
  * Missing previous NASDAQ100 → `FredNASDAQ100AdapterError`.
  * Non-positive previous NASDAQ100 → `FredNASDAQ100AdapterError`.
  * Malformed CSV (date, numeric, missing column, empty) →
    `FredNASDAQ100AdapterError`.
* A test that only `us_equities.nasdaq100` and
  `us_equities.nasdaq100_change_pct` are overlaid (all other
  fields come from the base adapter unchanged).
* A test that the base adapter's context is not mutated.
* A schema-conformance test that the returned `MarketContext`
  passes `validate_market_context`.
* Network-safety tests that mock `socket.socket`,
  `subprocess.{Popen,run,call}`, and `os.environ.get` /
  `os.getenv` during a representative `load(...)` call.
* An AST-level check that the adapter does not import `requests`,
  `httpx`, `aiohttp`, `dotenv`, `subprocess`, or
  broker / exchange SDKs.
* A test that no broker / order / account field can be
  introduced (the validator rejects any extra top-level key).
* Copyright / redistribution guard tests that no raw NASDAQ100
  data is committed under `fixtures/`, `exports/`, or
  `reports/`.

## 9. Non-Claims

The adapter explicitly does **not** claim:

* Live data fetch is always available (FRED is a public service
  operated by the St. Louis Fed; availability is not guaranteed).
* Any form of trading or order placement.
* Any predictive accuracy of any score that consumes the overlaid
  fields.
* That the NASDAQ100 endpoint is reachable at any particular
  moment. The dry-run uses mocked CSVs.
* That the adapter reads S&P 500, SOX, Nikkei, or USDJPY data
  (those are out of scope for this PR).
* That missing data is silently treated as a neutral contribution.
  A missing required input (e.g. no previous NASDAQ100
  observation) causes `FredNASDAQ100AdapterError` to be raised.
* Right or permission to redistribute raw NASDAQ100 observations
  downstream. Operators using this adapter are responsible for
  their own compliance with the FRED / Nasdaq citation and
  pre-approval policy.

## 10. Review Checklist for Future Adapter PRs

A reviewer of a new or modified adapter PR must confirm, at minimum:

- [ ] The adapter class satisfies the `MarketContextAdapter` protocol.
- [ ] The new tests cover the AST and runtime checks from §8.
- [ ] No new runtime dependency is added.
- [ ] No environment-variable credential reads.
- [ ] No network access in tests (all HTTP is mocked).
- [ ] The PR body lists the new `must_not_do` set.
- [ ] A missing-data path (e.g. no previous observation) raises
      rather than silently returning a neutral value.
- [ ] `load()` is annotated as returning `MarketContext`.
- [ ] If the source is a third-party index with copyright /
      redistribution constraints, the PR includes a §7-style
      copyright / redistribution guard.
