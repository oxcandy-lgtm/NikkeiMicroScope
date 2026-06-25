# FRED USDJPY Adapter Contract

> Binding for any code path that fetches or parses Japanese-yen-per-
> US-dollar daily observations from FRED. Lower-priority instructions
> (chat, scripts, LLM completions) cannot override this document. If
> in conflict, this document wins.

This document defines the FRED public USDJPY adapter contract. It
specifies:

1. What the adapter reads.
2. What the adapter does not read.
3. The mapping into `MarketContext.fx`.
4. Missing-value handling.
5. The date-selection rule.
6. The no-auth / no-secret posture.
7. The test strategy.
8. Non-claims.

## 1. Scope

The FRED USDJPY adapter is the **third approved public, no-auth
network adapter** in NikkeiMicroScope. It is implemented in
`nms/data/fred_usdjpy.py` and is documented in full by this
document. The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md) §8.3.

**What it reads:** only the FRED series below, public, no-auth, no
API key, downloaded as CSV over plain HTTPS.

| Series | Meaning | Unit |
| --- | --- | --- |
| DEXJPUS | Japanese Yen to U.S. Dollar Spot Exchange Rate | Japanese yen to one U.S. dollar |

URL: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXJPUS`

Higher value means weaker JPY / stronger USD versus JPY.

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
returns a new one with the two `fx` fields replaced.

## 2. What the Adapter Does Not Read

The adapter does **not** read:

* Any authenticated FRED API (the FRED API requires a key; this
  adapter does not use it).
* Nasdaq-100, SOX, SP500, or Nikkei data.
* Any environment variables for credentials.
* Any `.env` file.
* Any `os.environ.get` / `os.getenv` value.
* Any subprocess, shell, or external process output.
* Any broker / exchange / order / account information.

## 3. Mapping into `MarketContext.fx`

The adapter **overlays only** the following two fields on the
`fx` dataclass of the baseline `MarketContext`:

| Target field | Source |
| --- | --- |
| `usdjpy` | DEXJPUS value at the selected date |
| `usdjpy_change_pct` | `((DEXJPUS_today / DEXJPUS_yesterday) - 1.0) * 100.0` |

All other `MarketContext` sections come from the base adapter and
are left unchanged.

The resulting `MarketContext` is re-validated through
`validate_market_context` to enforce the schema and nested
strictness.

## 4. Date-Selection Rule

For a given `session_date`:

1. The latest DEXJPUS observation at or before `session_date` is
   selected. If none exists, `FredUSDJPYAdapterError` is raised.
2. The previous DEXJPUS observation (strictly before the selected
   date) is used to compute `usdjpy_change_pct`. **If none
   exists, `FredUSDJPYAdapterError` is raised.** A missing
   previous observation is never silently treated as a neutral
   contribution: that would corrupt downstream scoring by making
   "missing" indistinguishable from "zero change".
3. If the previous DEXJPUS value is non-positive (≤ 0),
   `FredUSDJPYAdapterError` is raised. A non-positive previous value
   would cause a division by zero or sign flip in the percent
   change calculation.

## 5. Missing-Value Handling

FRED rows with a missing value (`"."`) are ignored entirely — they
do not affect the date-selection logic. If the CSV contains no
usable rows (e.g. only the header, or only `""` / `"."` rows),
`FredUSDJPYAdapterError` is raised.

Rows with malformed dates or malformed numeric values cause
`FredUSDJPYAdapterError`.

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

## 7. Test Strategy

The adapter is exercised by:

* Parser unit tests (no HTTP, no subprocess, no env reads).
* Adapter unit tests with injected `http_get` and either a
  fixture-backed `MarketContextAdapter` or a stub base adapter.
* Negative tests for:
  * Missing previous DEXJPUS → `FredUSDJPYAdapterError`.
  * Non-positive previous DEXJPUS → `FredUSDJPYAdapterError`.
  * Malformed CSV (date, numeric, missing column, empty) →
    `FredUSDJPYAdapterError`.
* A test that only `fx.usdjpy` and `fx.usdjpy_change_pct` are
  overlaid (all other fields come from the base adapter
  unchanged).
* A test that the base adapter's context is not mutated.
* A schema-conformance test that the returned `MarketContext`
  passes `validate_market_context`.
* Network-safety tests that mock `socket.socket`,
  `subprocess.{Popen,run,call}`, and `os.environ.get` / `os.getenv`
  during a representative `load(...)` call.
* An AST-level check that the adapter does not import `requests`,
  `httpx`, `aiohttp`, `dotenv`, `subprocess`, or
  broker / exchange SDKs.
* A test that no broker / order / account field can be
  introduced (the validator rejects any extra top-level key).

## 8. Non-Claims

The adapter explicitly does **not** claim:

* Live data fetch is always available (FRED is a public service
  operated by the St. Louis Fed; availability is not guaranteed).
* Any form of trading or order placement.
* Any predictive accuracy of any score that consumes the overlaid
  fields.
* That the DEXJPUS endpoint is reachable at any particular moment.
  The dry-run uses mocked CSVs.
* That the adapter reads Nasdaq-100, SOX, SP500, or Nikkei data
  (those are out of scope for this PR).
* That missing data is silently treated as a neutral contribution.
  A missing required input (e.g. no previous DEXJPUS observation)
  causes `FredUSDJPYAdapterError` to be raised.

## 9. Review Checklist for Future Adapter PRs

A reviewer of a new or modified adapter PR must confirm, at minimum:

- [ ] The adapter class satisfies the `MarketContextAdapter` protocol.
- [ ] The new tests cover the AST and runtime checks from §7.
- [ ] No new runtime dependency is added.
- [ ] No environment-variable credential reads.
- [ ] No network access in tests (all HTTP is mocked).
- [ ] The PR body lists the new `must_not_do` set.
- [ ] A missing-data path (e.g. no previous observation) raises
      rather than silently returning a neutral value.
- [ ] `load()` is annotated as returning `MarketContext`.
