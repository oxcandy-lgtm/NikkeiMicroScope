# Shadow Replay Integrity Checker

## Purpose

`nms.shadow.integrity` checks one shadow replay result manifest against the
local trial ledger and local close ledger produced by the replay lane.

This is a counts/status/reference integrity layer only. It exists before any
future summary layer so NMS can prove that the result manifest and ledgers agree
at the identifier and count level.

## Scope

The checker reads three local files:

- replay result manifest JSON
- shadow trial ledger JSONL
- shadow close ledger JSONL

It emits one deterministic JSON integrity report.

## What it checks

The checker verifies:

- replay result schema version is `shadow-replay-result/1`
- result rows are well-formed JSON objects
- row statuses are one of:
  - `close_created`
  - `trial_created`
  - `row_error`
- result counts match the row statuses and ids:
  - `requested_rows`
  - `valid_rows`
  - `trial_records_created`
  - `close_records_created`
- trial ledger lines are JSON objects
- close ledger lines are JSON objects
- trial ids are unique in the trial ledger
- close ids are unique in the close ledger
- result-referenced trial ids exist in the trial ledger
- result-referenced close ids exist in the close ledger
- close ledger records point to existing trial ids
- referenced close records point to the same trial id as the result row
- trial and close records keep their shadow-only invariants:
  - `schema_version`
  - `executable=false`
  - fixed `blocked_reason`

Extra ledger records are allowed because ledgers are append-only and may contain
records from earlier local runs. The checker requires that every result
reference exists; it does not require the ledger to contain only that result's
records.

## Output report

The report schema version is:

```text
shadow-replay-integrity-report/1
```

The report includes only:

- `ok`
- paths
- row/reference counts
- ledger record counts
- issue list
- non-claims

It does not include price movement summaries or score-quality claims.

## CLI

```bash
python3 scripts/check_shadow_replay_integrity.py \
  --result-manifest /path/to/shadow-replay-result.json \
  --trial-ledger /path/to/shadow-trial-ledger.jsonl \
  --close-ledger /path/to/shadow-close-ledger.jsonl \
  --report-output /path/to/shadow-replay-integrity-report.json
```

Exit codes:

- `0` when the report is `ok:true`
- `1` when the report is `ok:false` or the output file would be overwritten

## Dry run

```bash
bash scripts/run_shadow_replay_integrity_dry_run.sh
```

The dry-run uses temporary files only. It generates synthetic artifacts, runs the
shadow replay, runs the integrity checker, verifies the report, and deletes temp
files on exit.

## Boundaries

This checker does not:

- approve a new market data source
- perform network I/O
- fetch or infer close prices
- create shadow trial records
- create shadow close records
- mutate ledgers
- place, route, simulate, or transmit orders
- connect to a broker or venue
- read credentials
- maintain capital account or exposure state
- compute scored-result metrics
- claim summary quality
- act as backtest, paper execution, or live trading
- add a default live pipeline
