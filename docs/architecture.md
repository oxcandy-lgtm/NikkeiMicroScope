# Architecture — NikkeiMicroScope (NMS)

This document describes the **planned** code layout for NMS. The current
bootstrap PR contains only docs, configuration, and Satellite support
surfaces. No runtime code is shipped in this PR.

## High-Level Module Layout

```
.
|-- core/         # Pure scoring + classification (no I/O, no network)
|-- data/         # Adapters: read-only ingestion of public context signals
|-- markets/
|   `-- nikkei_micro/   # Nikkei 225 micro-futures specific logic
|-- reports/      # Human-readable report rendering
|-- exports/      # Advisory JSON outputs (regime, satellite plan, etc.)
|-- scripts/      # Operator-facing runnable entry points
`-- docs/         # Product, research, scoring, and risk documentation
```

### `core/`

- Pure functions for `direction_score`, `volatility_score`,
  `event_risk_score`, `no_trade_score` and `classify_session`.
- **No I/O.** Inputs are passed in as already-normalized data structures.
- **No network access.** No subprocess calls.
- The score formulas are the single source of code-level truth for the
  definitions in `docs/market-regime-score.md`.

### `data/`

- Adapters that fetch and normalize each input source listed in
  `docs/product-spec.md`.
- Adapters are **read-only**. They never write to any external system
  except local files under `exports/` and `reports/`.
- Adapters never receive, store, or accept credentials. If an upstream
  source requires auth, that source is out of scope.

### `markets/nikkei_micro/`

- Nikkei 225 micro-futures specific code: contract size, tick size,
  intraday session boundaries, night-session bridging, JST timezone
  helpers.
- Reachable-move evaluation: given observed context, estimate whether
  +50円 and +100円 moves were realistic from the open.

### `reports/`

- Renders `reports/session-YYYY-MM-DD.md` from the advisory JSON.
- Pure templating; no business logic.

### `exports/`

- Advisory JSON outputs only.
- `regime/`, `sessions/`, `backtest/`, `satellite-*.json` subtrees.
- Nothing in `exports/` is cited as canonical truth. See
  `AGENTS.md §7`.

### `scripts/`

- Operator entry points. Examples: `run-scoring.sh`, `run-backtest.sh`,
  `satellite-update-dry-run.sh`.
- Scripts call into the package; they do not duplicate business logic.

## Hard Architectural Rules

1. **No broker / execution layer in MVP.** No import of a broker SDK, no
   order-placement API, no exchange adapter that can place orders. The
   first PR that adds such a layer requires the operator charter
   described in `AGENTS.md §4`.

2. **Separation of signal generation and execution.** `core/` and `data/`
   produce signals. There is no consumer of those signals in this
   repository that can place orders. Paper-trading execution (future
   work) must be in a clearly marked `paper/` subtree and must not
   share code with any future live-execution layer.

3. **No secrets in code paths.** No environment-variable reads for
   credentials, no config files that contain credentials, no `.env`
   loading, no hard-coded tokens.

4. **Advisory outputs only.** Anything emitted to `exports/` is
   advisory. Downstream automation is forbidden from acting on it as if
   it were a signal to execute.

5. **No silent schema drift.** Score formula changes require updating
   `docs/market-regime-score.md` in the same PR.

## Runtime / Process

- MVP runs as a batch process (cron or manual invocation) producing one
  set of advisory outputs per session. There is no long-running server
  in MVP.
- All timestamps are JST unless explicitly stated.
- Logs go to stdout / stderr in JSONL. No log shipping, no third-party
  log services.

## Dependency Posture

- Prefer small, well-known, permissively-licensed dependencies.
- No closed-source, paid, or vendor-locked dependencies.
- All dependencies must be installable from public package indexes
  without credentials.
