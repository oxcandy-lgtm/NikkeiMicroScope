# Composed MarketContext JSON Export

> Binding for any code path that serializes a composed
> `MarketContext` to JSON. Lower-priority instructions (chat,
> scripts, LLM completions) cannot override this document. If in
> conflict, this document wins.

This document defines the composed-MarketContext JSON export
contract. It specifies:

1. The export purpose.
2. The deterministic JSON format.
3. The dry-run / synthetic posture.
4. The overwrite policy.
5. The output location policy.
6. The no live network / no broker posture.
7. Non-claims.

The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md) §8.7.

## 1. Purpose

PR #12 added adapter composition primitives and a synthetic
dry-run script. This PR adds a read-only export utility that
serializes the final composed `MarketContext` to a deterministic
JSON artifact. The export is a thin layer on top of
`MarketContext`:

* `market_context_to_ordered_dict(ctx)` — re-validate + plain
  dict.
* `market_context_to_json_text(ctx)` — deterministic UTF-8 JSON
  text.
* `write_market_context_json(ctx, output_path, *,
  allow_overwrite=False)` — write to a local path, refuse
  overwrite by default, return the path.

The export layer is intentionally minimal. It is **not** a new
market data source. It does **not** perform network I/O. It
does **not** read environment credentials. It does **not** use
subprocess. It does **not** import broker SDKs, exchange
clients, or paid data sources.

## 2. Deterministic JSON format

The JSON output is deterministic so that the same input
`MarketContext` always produces the same byte sequence. The
format is:

* UTF-8 encoded.
* `ensure_ascii=False` — non-ASCII characters are kept as-is
  rather than escaped to `\uXXXX`.
* `indent=2` — human-readable.
* `sort_keys=True` — keys are sorted alphabetically at every
  level.
* A final newline (`\n`) is appended.

The schema is the same as the documented
`MarketContext` schema in
[`docs/data-adapter-contract.md`](data-adapter-contract.md) §1.
No new fields are introduced. The export layer does not
widen the schema.

## 3. Dry-run / synthetic posture

The default dry-run output goes to:

```yaml
exports/dry-run/composed-market-context-<session_date>.json
```

A committed example JSON may live in this directory, but it
**must**:

* Be under `exports/dry-run/`.
* Contain a top-level `"synthetic"` (or `"_dry_run_meta"`)
  marker so it is never confused with live data.
* Be produced from the synthetic CSV fixture used by the
  dry-run script, not from a live FRED download.

The dry-run script (`scripts/export_composed_market_context.py`)
**does not** hit live FRED. It uses injected `http_get` that
returns synthetic CSV text. The committed example JSON, if any,
is synthetic.

## 4. Re-validation

Before serializing, the export layer re-validates the input
`MarketContext` through
`nms.data.validate.validate_market_context`. If the input
context fails validation, the export layer raises
`nms.data.ValidationError` and does not write anything.

This is in addition to the per-adapter validation that the FRED
overlay adapters already perform on their own output. The
re-validation is a defense-in-depth check that catches:

* A context that the composed adapters did not validate.
* A context that was mutated in transit.
* A context that was constructed by a future adapter that does
  not validate eagerly.

## 5. Overwrite policy

`write_market_context_json` refuses to overwrite an existing
file by default. If `output_path` already exists and
`allow_overwrite=False` (the default), the function raises
`FileExistsError`. Pass `allow_overwrite=True` to override.

This is a safety measure for operator-side scripts. The default
behavior matches "fail loudly if you are about to clobber a
file" rather than "silently overwrite".

## 6. Output location policy

The default output path is
`exports/dry-run/composed-market-context-<session_date>.json`.
This directory is intentionally separate from `fixtures/` (which
holds input fixtures) and `reports/` (which is reserved for
future analytics outputs).

The export layer writes only to the path it is given. It does
not write to arbitrary paths. The dry-run script writes only to
a path under `exports/dry-run/`. The shell wrapper writes to a
temporary path or to the default dry-run path; both are
under the repository root.

## 7. No live network / no broker posture

The export layer:

* Does not import or call any of: `requests`, `httpx`,
  `aiohttp`, `urllib.request`, `yfinance`, `pandas`,
  `pandas-datareader`.
* Does not read environment variables for credentials.
* Does not use subprocess or shell-out.
* Does not import broker SDKs, exchange clients, or FIX.
* Does not use `.env`, `dotenv`, or any credential file.
* Does not introduce a default live pipeline. A future PR may
  add a CLI flag for live network, but not this one.

Tests and the dry-run script are subject to the same posture
and use only synthetic CSV / injected `http_get` / a
fixture-backed base adapter.

## 8. SOX posture

Per
[`docs/sox-source-selection.md`](sox-source-selection.md) and
§8.5 of `docs/data-adapter-contract.md`, no SOX / semiconductor
adapter is approved yet. The export layer does not introduce
one. The `semiconductor` section in the exported JSON is
whatever the input `MarketContext` provided — it must not be
populated by a SOX source at any stage.

The export layer is **not** a place to relax the SOX contract.
A future SOX source-selection change must be reviewed in a
separate PR that updates `docs/sox-source-selection.md` and
§8.5 of `docs/data-adapter-contract.md` first.

## 9. Non-claims

The export layer explicitly does **not** claim:

* It is a new market data source. It is not.
* It performs live network I/O. It does not.
* It introduces a default live pipeline. It does not.
* It is a backtest, paper-trading, or live-trading system. It
  is not.
* It is investment advice, a profit guarantee, or a
  recommendation. It is not.
* It approves the SOX / semiconductor adapter. It does not.
* It approves broker / auth / cookie / paid source paths. It
  does not.
* It is appropriate for runtime production use without a
  separately reviewed live-pipeline PR. A future live-pipeline
  PR is required before this export layer is wired into any
  production entry point.

## 10. Reviewer checklist

- [ ] `nms/data/export.py` does not import any of:
      `requests`, `httpx`, `aiohttp`, `dotenv`, `subprocess`,
      `os`, `urllib`, `urllib3`, `yfinance`, `pandas`,
      broker SDKs.
- [ ] `tests/test_market_context_export.py` does not perform
      live network I/O, does not use `subprocess`, and does not
      read environment credentials.
- [ ] The dry-run script uses synthetic CSV and injected
      `http_get`. It does not hit live FRED.
- [ ] The export layer re-validates the input context before
      writing.
- [ ] The export layer refuses overwrite by default.
- [ ] No raw FRED CSV is committed to `exports/`, `fixtures/`,
      or `reports/`.
- [ ] If a committed example JSON exists, it is under
      `exports/dry-run/` and contains a synthetic marker.
- [ ] §8.7 of `docs/data-adapter-contract.md` is updated and
      links to this document.
- [ ] `nms/data/__init__.py` re-exports the new symbols.
- [ ] No new runtime dependency is added.
- [ ] No GitHub workflow file is changed.
