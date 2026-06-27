# MarketContext Artifact Validation Report

> Binding for any code path that reads an exported
> `MarketContext` JSON artifact and produces a validation
> report. Lower-priority instructions (chat, scripts, LLM
> completions) cannot override this document. If in
> conflict, this document wins.

This document defines the artifact-validation / report
contract. It specifies:

1. The report purpose.
2. The input artifact shape.
3. The allowed artifact metadata.
4. The validation steps.
5. The field-population report.
6. The SOX / unapproved source posture.
7. The synthetic dry-run behavior.
8. The CLI usage.
9. Non-claims.

The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md)
§8.8.

## 1. Purpose

PR #13 added deterministic JSON export for the composed
`MarketContext`. PR #14 adds a read-only validator/report
that reads an exported artifact and reports:

* whether the artifact is valid JSON;
* whether it conforms to `MarketContext`;
* whether expected overlay fields are populated;
* whether known intentionally-missing / unapproved fields
  remain missing or unchanged;
* whether dry-run synthetic metadata is present when
  expected;
* whether SOX is still not treated as an approved input.

The report is read-only. It does not score, signal, or
execute. It is not a backtest, not paper trading, and not
live trading.

## 2. Input artifact shape

The input is a local JSON file. The top level must be a JSON
object. The top-level keys must be either:

* a `MarketContext` schema key (see
  [`docs/data-adapter-contract.md`](data-adapter-contract.md)
  §1), or
* an allowed artifact-level metadata key (see §3).

The validator rejects artifacts with any top-level key that
is neither a `MarketContext` schema key nor an allowed
artifact metadata key.

## 3. Allowed artifact metadata

Two top-level keys are allowed as artifact-level metadata
but are not part of the `MarketContext` schema:

* `synthetic` (boolean): when `True`, indicates the
  artifact was produced by a synthetic dry-run pipeline,
  not from live data.
* `_dry_run_meta` (object): a small object with
  operator-side metadata. The validator looks at
  `_dry_run_meta.live_fred_used`: if the caller passes
  `expect_synthetic=True`, the validator requires
  `live_fred_used: false`.

The validator strips these two keys from the loaded payload
before calling
[`validate_market_context`](data-adapter-contract.md). The
underlying `MarketContext` schema is **not** widened; the
metadata lives at the artifact layer, not the model layer.

## 4. Validation steps

The validator performs these steps in order:

1. Load the JSON file. If the file is missing or the JSON is
   invalid, the report has `valid_json=False` and an error.
2. Detect the synthetic marker (`synthetic`,
   `_dry_run_meta`).
3. Strip allowed metadata before schema validation.
4. Flag unknown top-level metadata keys.
5. Validate the (stripped) payload as `MarketContext`.
6. Build the field-status list for the expected populated
   fields and the intentionally-missing / unapproved fields.
7. If `expect_synthetic=True`, require the synthetic marker
   and `live_fred_used: false` in `_dry_run_meta`.
8. For SOX (an unapproved source), require zero values in
   any synthetic approved dry-run artifact.

The validator does not mutate the loaded payload. The
stripping is a copy, not an in-place edit.

## 5. Field-population report

The report includes two lists:

* `populated_fields` — the fields the approved dry-run
  pipeline is expected to populate. Each entry has the
  field path, whether it is present, its value, and whether
  it is populated (nonzero). The expected populated fields
  are:

  * `us_yields.us2y`
  * `us_yields.us10y`
  * `us_yields.us10y_minus_us2y`
  * `us_yields.us10y_change_bp`
  * `us_equities.sp500`
  * `us_equities.sp500_change_pct`
  * `fx.usdjpy`
  * `fx.usdjpy_change_pct`
  * `us_equities.nasdaq100`
  * `us_equities.nasdaq100_change_pct`

* `intentionally_missing_or_unapproved_fields` — fields
  the approved dry-run pipeline does not source from an
  approved source. Each entry has the same shape as above.
  The intentionally missing / unapproved fields are:

  * `semiconductor.sox`
  * `semiconductor.sox_change_pct`
  * `nikkei_night_session.close`
  * `nikkei_night_session.percent_change`

`report.ok` is `True` only if every expected populated field
is present and populated. A missing or zero expected field
fails the report.

## 6. SOX / unapproved source posture

Per
[`docs/sox-source-selection.md`](sox-source-selection.md)
and §8.5 of `docs/data-adapter-contract.md`, no SOX /
semiconductor adapter is approved yet. The validator:

* Does **not** fail merely because `semiconductor.sox` is
  zero. SOX zero is the expected state for a synthetic
  approved dry-run artifact.
* **Does** fail if `semiconductor.sox` is nonzero **in a
  synthetic approved dry-run artifact** (i.e. one with
  `synthetic: true` and `_dry_run_meta.live_fred_used:
  false`). A nonzero SOX in a synthetic approved artifact
  would mean a SOX source snuck in past the §8.5 contract.
* Does **not** fail if `semiconductor.sox` is nonzero in a
  non-synthetic artifact (the report just records the
  value). The §8.5 rule applies to the approved dry-run
  pipeline, not to arbitrary artifacts.

The validator treats SOX the same way it treats other
unapproved sources: it is not a score or signal. The
"unapproved" status is a *contract* signal, not a market
signal.

## 7. Synthetic dry-run behavior

If the caller passes `expect_synthetic=True`, the validator
requires:

* `synthetic: true` at the top level.
* `_dry_run_meta` present at the top level.
* `_dry_run_meta.live_fred_used: false`.

If `expect_synthetic=False` (the default), the validator
does not require any of the above. A non-synthetic
artifact is allowed; the report just records the synthetic
status.

The dry-run script
(`scripts/validate_market_context_artifact_dry_run.sh`)
generates a synthetic artifact using
`scripts/export_composed_market_context.py` and validates it
with `--expect-synthetic`. The shell wrapper verifies
`valid_json: true`, `valid_market_context: true`,
`synthetic: true`, `dry_run_meta_present: true`, and
`ok: true` in the report.

## 8. CLI usage

The validator can be run as a CLI:

```bash
python3 scripts/validate_market_context_artifact.py \
    --input <path> \
    [--expect-synthetic] \
    [--report-output <path>]
```

Behavior:

* `--input <path>`: required. The path to the JSON artifact
  to validate.
* `--expect-synthetic`: if set, the validator requires the
  synthetic marker.
* `--report-output <path>`: optional. If set, the validator
  writes the deterministic JSON report to this path. The
  report is in deterministic JSON (`ensure_ascii=False`,
  `indent=2`, `sort_keys=True`, trailing newline). If the
  path exists, the script refuses to overwrite by default.
* The validator always prints the report to stdout.
* Exit code is `0` iff `report.ok` is `True`.

The script does not hit live network, does not use
subprocess, and does not read environment credentials.

## 9. Non-claims

The report layer explicitly does **not** claim:

* It is a new market data source. It is not.
* It performs live network I/O. It does not.
* It introduces a default live pipeline. It does not.
* It is a backtest, paper-trading, or live-trading system.
  It is not.
* It is investment advice, a profit guarantee, or a
  recommendation. It is not.
* It is a score or signal. It is not. The "unapproved
  field" status is a *contract* signal, not a market
  signal.
* It approves the SOX / semiconductor adapter. It does
  not. The validator just reports SOX as unapproved and
  flags nonzero SOX in synthetic approved artifacts.
* It approves broker / auth / cookie / paid source paths.
  It does not.
* It widens the `MarketContext` schema. It does not. The
  metadata is stripped before schema validation.
* It is appropriate for runtime production use without a
  separately reviewed live-pipeline PR. A future
  live-pipeline PR is required before this report layer is
  wired into any production entry point.

## 10. Reviewer checklist

- [ ] `nms/data/artifact_report.py` does not import any of:
      `requests`, `httpx`, `aiohttp`, `dotenv`, `subprocess`,
      `os`, `urllib`, `urllib3`, `yfinance`, `pandas`,
      broker SDKs.
- [ ] `tests/test_market_context_artifact_report.py` does
      not perform live network I/O, does not use
      `subprocess`, and does not read environment
      credentials.
- [ ] The dry-run script uses local file input only. It
      does not hit live network.
- [ ] The validator does not widen the `MarketContext`
      schema.
- [ ] The validator strips only the allowed metadata keys
      before schema validation.
- [ ] The validator reports nonzero SOX in a synthetic
      approved dry-run artifact as an error.
- [ ] §8.8 of `docs/data-adapter-contract.md` is updated and
      links to this document.
- [ ] `nms/data/__init__.py` re-exports the new symbols.
- [ ] No new runtime dependency is added.
- [ ] No GitHub workflow file is changed.
