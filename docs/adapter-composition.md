# Adapter Composition

> Binding for any code path that wires a sequence of
> `MarketContextAdapter` instances into a single final
> `MarketContext`. Lower-priority instructions (chat, scripts, LLM
> completions) cannot override this document. If in conflict, this
> document wins.

This document defines the adapter-composition contract. It specifies:

1. The purpose of the composition layer.
2. The approved inputs.
3. The explicit non-approved input (SOX adapter).
4. Stage ordering and execution semantics.
5. No live network in tests / dry-runs.
6. No default live production pipeline.
7. Failure and validation semantics.
8. Non-claims.

The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md) §8.6.

## 1. Purpose

NikkeiMicroScope now has several read-only `MarketContextAdapter`
implementations:

* `FixtureMarketContextAdapter` (local file I/O, no network)
* `FredTreasuryOverlayAdapter` (public FRED DGS2 / DGS10)
* `FredSP500OverlayAdapter` (public FRED SP500)
* `FredUSDJPYOverlayAdapter` (public FRED DEXJPUS)
* `FredNASDAQ100OverlayAdapter` (public FRED NASDAQ100)

The composition layer is a small, deterministic orchestration
layer that wires a base adapter and a sequence of named overlay
stages into a single final validated `MarketContext`. It is
**not** a new market data source. It does not perform network I/O
itself. It is pure orchestration.

The composition primitives live in
`nms/data/composition.py`:

* `AdapterStage` — a `(name, factory)` pair. The factory takes a
  baseline `MarketContextAdapter` and returns a new
  `MarketContextAdapter` that uses the input as its baseline.
* `AdapterCompositionError` — narrow exception wrapping
  construction-time and load-time failures.
* `ComposedMarketContextAdapter` — the composed adapter.
* `compose_market_context_adapter(base_adapter, stages)` —
  convenience helper that returns a
  `ComposedMarketContextAdapter`.

## 2. Approved inputs

The composition layer may only compose already-approved
`MarketContextAdapter` implementations. At this writing, the
approved list is:

| Stage name | Adapter class | Source |
| --- | --- | --- |
| `treasury` | `FredTreasuryOverlayAdapter` | FRED DGS2 / DGS10 |
| `sp500` | `FredSP500OverlayAdapter` | FRED SP500 |
| `usdjpy` | `FredUSDJPYOverlayAdapter` | FRED DEXJPUS |
| `nasdaq100` | `FredNASDAQ100OverlayAdapter` | FRED NASDAQ100 |
| (base) | `FixtureMarketContextAdapter` | Local fixture JSON |

A new entry in this table requires a new PR that updates both
this document and §8 of `docs/data-adapter-contract.md`. The
composition code itself must not silently accept a new adapter
class without that contract update.

## 3. Explicit non-approved input

Per
[`docs/sox-source-selection.md`](sox-source-selection.md) and
§8.5 of `docs/data-adapter-contract.md`, **no SOX / semiconductor
adapter is approved yet**. Therefore, the composition layer must
not include a SOX stage, must not import or instantiate any SOX
adapter, and must not write `semiconductor.sox` /
`semiconductor.sox_change_pct`. A SOX stage is added only after
the source-selection contract is updated to a `preferred` or
`acceptable` outcome.

## 4. Stage ordering

The composition layer accepts a sequence of `AdapterStage`s. The
sequence is the order in which stages are applied. The factories
themselves are invoked at `load()` time, in the listed order.
After all factories are applied, the resulting final adapter is
called with `load(session_date)` to produce the final
`MarketContext`. The final context is re-validated through
`nms.data.validate.validate_market_context`.

The composition layer does not introspect the internals of any
overlay adapter. The overlay adapters continue to take their
baseline adapter in the constructor (matching the existing FRED
adapter pattern) and call it lazily on `load()`. The composition
layer is intentionally thin: factory chain + final validation.

## 5. No live network in tests or dry-runs

This module does not perform network I/O. The injected
`http_get` of each FRED overlay adapter is the only network entry
point. Tests inject a fake `http_get` callable and prove that no
socket, subprocess, or env-credential read is performed. The
dry-run script uses synthetic CSV text and an injected
`http_get`. **No live FRED endpoint is hit by tests or the
dry-run.**

## 6. No default live production pipeline

This PR does **not** add a default live production pipeline. The
composition layer is a primitive: it composes already-constructed
adapter instances. The dry-run and tests only use synthetic data.

A future PR may add an operator-run CLI with an explicit
`--live-network-ok` flag, but not this one. Any such future PR
must:

* Be a separate PR.
* Be reviewed per
  [`docs/data-adapter-contract.md`](data-adapter-contract.md).
* Cite the operator charter required by `AGENTS.md §4`.
* Keep the no-broker / no-auth / no-cookie posture.

## 7. Failure semantics

Construction-time and load-time failures are wrapped in
`AdapterCompositionError`. The original exception is preserved as
`__cause__` for debugging.

* **Construction-time failure**: if a stage factory raises
  (e.g. the FRED adapter's constructor argument validation
  fails), the wrapped error message includes the failing stage's
  `name`. The original exception is preserved.
* **Load-time failure**: if the final composed adapter's
  `load(session_date)` raises, the wrapped error message
  includes the session date. The original exception is
  preserved.

The composition layer stops at the first failure. It does not
attempt to "neutralize" or "skip" a stage on failure.

## 8. Validation semantics

The composition layer re-validates the final
`MarketContext` returned by the chain. This is in addition to the
per-adapter validation that each FRED overlay already performs
on its own output. The validator
(`nms.data.validate.validate_market_context`) rejects:

* Unknown top-level keys.
* Unknown nested keys (e.g. an extra `us_equities` field).
* Wrong types (e.g. `bool` for a numeric field).
* Missing required keys.

If a future change widens the schema, that change must be
reviewed in the same PR as the schema change. The composition
layer does not relax any of these checks.

## 9. Non-claims

The composition layer explicitly does **not** claim:

* It is a new market data source. It is not.
* It performs live network I/O. It does not.
* It introduces a default live production pipeline. It does
  not.
* It approves the SOX / semiconductor adapter. It does not.
* It approves broker / auth / cookie / paid source paths. It
  does not.
* It changes the `MarketContext` schema. It does not.
* It changes any scoring weights. It does not.
* It performs paper trading, backtesting, or live trading. It
  does not.
* It is appropriate for runtime production use without a
  separately reviewed live-pipeline PR. A future live-pipeline
  PR is required before this composition layer is wired into
  any production entry point.

## 10. Reviewer checklist

- [ ] `nms/data/composition.py` does not import any of:
      `requests`, `httpx`, `aiohttp`, `dotenv`, `subprocess`,
      `urllib`, `urllib3`, `yfinance`, `pandas`, broker SDKs.
- [ ] `tests/test_adapter_composition.py` does not perform
      live network I/O, does not use `subprocess`, and does not
      read environment credentials.
- [ ] The dry-run script uses synthetic CSV and injected
      `http_get`. It does not hit live FRED.
- [ ] The composition layer does not include a SOX stage.
- [ ] The composition layer does not introduce a default live
      production pipeline.
- [ ] §8.6 of `docs/data-adapter-contract.md` is updated and
      links to this document.
- [ ] `nms/data/__init__.py` re-exports the new symbols.
- [ ] No new runtime dependency is added.
- [ ] No GitHub workflow file is changed.
