# FRED Treasury Adapter Contract

> Binding for any code path that fetches or parses DGS2 / DGS10 daily
> U.S. Treasury yield observations from FRED. Lower-priority
> instructions (chat, scripts, LLM completions) cannot override this
> document. If in conflict, this document wins.

This document defines the FRED public treasury adapter contract. It
specifies:

1. What the adapter reads.
2. What the adapter does not read.
3. The mapping into ``MarketContext.us_yields``.
4. Missing-value handling.
5. The date-selection rule.
6. The no-auth / no-secret posture.
7. The test strategy.
8. Non-claims.

## 1. Scope

The FRED adapter is the **first approved public, no-auth network
adapter** in NikkeiMicroScope. It reads only the following two FRED
series, both public, no-auth, no API key:

| Series ID | Meaning | Unit | Frequency |
| --- | --- | --- | --- |
| DGS2 | U.S. Treasury 2-Year Constant Maturity | percent | daily |
| DGS10 | U.S. Treasury 10-Year Constant Maturity | percent | daily |

The adapter does **not** read equities, FX, SOX, or Nikkei data. Those
are out of scope for this PR and require their own adapters per the
``MarketContextAdapter`` protocol.

## 2. What the Adapter Reads

The adapter reads two FRED CSV endpoints:

```
https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2
https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10
```

Each endpoint returns a CSV with the format:

```
DATE,DGS2
2024-01-02,4.32
2024-01-03,4.28
2024-01-04,.
...
```

Missing values are represented as ``.`` and are ignored by the
parser.

## 3. What the Adapter Does Not Read

The adapter does **not** read:

* Any authenticated FRED API (the FRED API requires a key; this
  adapter does not use it).
* Any equities, FX, SOX, or Nikkei data.
* Any environment variables for credentials.
* Any ``.env`` file.
* Any ``os.environ.get`` / ``os.getenv`` value.
* Any subprocess, shell, or external process output.
* Any broker / exchange / order / account information.

## 4. Mapping into ``MarketContext.us_yields``

The adapter **overlays only** the following four fields on the
``us_yields`` dataclass of the baseline ``MarketContext``:

| Target field | Source |
| --- | --- |
| ``us2y`` | DGS2 value at the selected date |
| ``us10y`` | DGS10 value at the selected date |
| ``us10y_minus_us2y`` | ``us10y - us2y`` |
| ``us10y_change_bp`` | ``(DGS10_today - DGS10_yesterday) * 100`` |

All other ``MarketContext`` fields come from the base adapter and are
left unchanged.

The resulting ``MarketContext`` is re-validated through
``validate_market_context`` to enforce the schema and nested
strictness.

## 5. Date-Selection Rule

For a given ``session_date``:

1. The latest DGS2 observation at or before ``session_date`` is
   selected. If none exists, ``FredTreasuryAdapterError`` is raised.
2. The latest DGS10 observation at or before ``session_date`` is
   selected. If none exists, ``FredTreasuryAdapterError`` is raised.
3. The previous DGS10 observation (strictly before the selected
   date) is used to compute ``us10y_change_bp``. If none exists,
   ``us10y_change_bp`` is set to ``0.0``.
4. The selected DGS2 and DGS10 dates must match. If they differ,
   ``FredTreasuryAdapterError`` is raised.

## 6. Missing-Value Handling

FRED rows with a missing value (``"."``) are ignored entirely — they
do not affect the date-selection logic. Rows with malformed dates or
malformed numeric values cause ``FredTreasuryAdapterError``.

## 7. No-Auth / No-Secret Posture

The adapter is public/no-auth:

* No API key.
* No auth header.
* No cookie.
* No ``.env`` file.
* No environment variable credential reading.
* No subprocess / shell-out.

The default HTTP GET uses ``urllib.request`` with no headers. Tests
inject a fake ``http_get`` callable and prove that no socket,
subprocess, or environment-variable access is performed.

## 8. Test Strategy

The adapter is exercised by:

* Parser unit tests (no HTTP, no subprocess, no env reads).
* Adapter unit tests with injected ``http_get`` and a fixture-backed
  ``MarketContextAdapter``.
* Network-safety tests that mock ``socket.socket``,
  ``subprocess.{Popen,run,call}``, and ``os.environ.get`` / ``os.getenv``
  during a representative ``load(...)`` call.
* An AST-level check that the adapter does not import ``requests``,
  ``httpx``, ``aiohttp``, ``dotenv``, ``subprocess``, or
  broker / exchange SDKs.
* A schema-conformance test that the returned ``MarketContext`` passes
  ``validate_market_context``.

## 9. Non-Claims

The adapter explicitly does **not** claim:

* Live trading or order placement.
* Broker / exchange integration.
* Authentication or API key handling.
* Predictive accuracy of any score that consumes the overlaid fields.
* A guarantee that the DGS2 / DGS10 endpoints are reachable at any
  particular moment (FRED is a public service operated by the St.
  Louis Fed).

## 10. Review Checklist for Future Adapter PRs

A reviewer of a new or modified adapter PR must confirm, at minimum:

- [ ] The adapter class satisfies the ``MarketContextAdapter`` protocol.
- [ ] The new tests cover the AST and runtime checks from §8.
- [ ] No new runtime dependency is added.
- [ ] No environment-variable credential reads.
- [ ] No network access in tests (all HTTP is mocked).
- [ ] The PR body lists the new ``must_not_do`` set.
