# NikkeiMicroScope (NMS)

> Market regime observation and no-trade decision support for Nikkei 225 micro futures research.

NikkeiMicroScope (short name: **NMS**) is a research and observation system for
Nikkei 225 micro futures regime analysis. It collects and normalizes market
context signals, computes advisory market-regime scores, classifies each
session as `buy-only` / `sell-only` / `no-trade`, and evaluates whether
+50円 / +100円 price moves were realistically reachable given the observed
context. All outputs are advisory.

## Status

- **Stage:** bootstrap (docs-only)
- **CCL Tier:** 2 (Satellite-first Project Repo)
- **Repo mode:** `dry_run`
- **Live trading:** disabled
- **Broker integration:** disabled
- **Source of truth for generated exports:** false (advisory only)

## Scope

This repository owns:

- Project identity, product spec, architecture, and research plan.
- Advisory scoring formulas (regime score, no-trade score).
- Backtesting and paper-trading scaffolding.
- Satellite pack, agent state, and advisory export surfaces.

This repository does **not** contain:

- A full parent CCL tree copy.
- A live broker / order-placement layer.
- Secrets, `.env` files, API keys, or tokens.
- Financial advice claims or profit guarantees.
- GitHub Issues usage.
- Direct-to-`main` commits or pushes.

## Non-Goals (Hard)

- No live trading, no auto order placement.
- No broker / exchange credential handling.
- No PAT, no service account token, no `.env` secrets.
- No financial advice; no profit guarantees.
- No GitHub Issues; no canonical wiki auto-writes.
- No direct push to `main`.
- No copying the full parent CCL template into this repo.

## Initial Roadmap

1. **Docs-only bootstrap** — this PR.
2. **Data adapters** — read-only ingestion of public context signals.
3. **Scoring** — implement `direction_score`, `volatility_score`,
   `event_risk_score`, `no_trade_score` from `docs/market-regime-score.md`.
4. **Backtest** — walk-forward validation against historical sessions.
5. **Paper trading** — simulated execution only, with hard loss gates.

Future work items must be opened as pull requests, not issues, and must not
modify the hard non-goals above.

## CCL Tier 2 (Satellite-first) Note

NMS uses **CCL Tier 2 — Satellite-first Project Repo**. It is a project-owned
repo, not a full CCL template instance. The parent CCL tree is **not** copied
in. Only the following Satellite surfaces are present here:

- `satellite-pack.json`
- `.agent/state.json`
- `scripts/satellite-update-dry-run.sh`
- `exports/satellite-health.json`
- `exports/satellite-update-plan.json`

All Satellite updates are advisory. `repo_mode` is `dry_run` and
`source_of_truth` is `false` for generated exports. There is no auto-apply
and no recurring sync pressure beyond explicit workflow / manual runs.

## Repository Layout

```
.
|-- AGENTS.md                         # Operator / agent rules
|-- GITHUB_*.md                       # GitHub stewardship root docs
|-- HUMAN_PLATFORM_COVENANT.md        # Human / platform covenant
|-- README.md                         # This file
|-- satellite-pack.json               # CCL Satellite pack manifest
|-- .agent/state.json                 # CCL Satellite agent state
|-- docs/
|   |-- product-spec.md
|   |-- architecture.md
|   |-- research-plan.md
|   |-- market-regime-score.md
|   `-- risk-policy.md
|-- exports/
|   |-- satellite-health.json
|   `-- satellite-update-plan.json
|-- scripts/
|   `-- satellite-update-dry-run.sh
`-- .github/workflows/                # Optional, read-only CI only
```

## Disclaimer

This is a **research and paper-trading observation tool**. It is not
investment advice, not a recommendation, and not a live trading system. All
signals, scores, and classifications are advisory and may be wrong. The
operator of this repository and the authors of any derived content accept
no liability for losses arising from use of this material. Do not risk money
you cannot afford to lose.
