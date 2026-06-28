# Code Agent Brief — Paper-Trading Program Refinement

## Purpose

This is an implementation brief for a future code agent. It defines how to
refine NikkeiMicroScope through paper-trading style feedback without crossing
into live trading, broker integration, or unreviewed strategy-performance
claims.

The goal is program refinement, not trading automation.

## Current boundary reading

`AGENTS.md` forbids live trading, broker integration, order placement,
auto-execution, broker SDKs, secrets, PATs, and GitHub Issues.

`docs/risk-policy.md` already defines constraints for paper-trading and
backtest code:

- no martingale
- no leverage escalation
- flat fixed contract count
- max simulated loss gates
- machine-readable logs
- gate outcomes visible in reports
- no profit guarantee
- no advice claim

Therefore paper-trading refinement is possible only as a local simulation and
measurement lane. It must not become a live execution lane.

## Allowed objective

Build a local, deterministic paper-trading refinement harness that helps answer:

> Did a proposed scoring/rule/program change make the replayed decision process
> more internally consistent under the reviewed constraints?

The harness may compare local candidate programs against local historical or
synthetic replay inputs, but it must report bounded diagnostic metrics only.

## Required architecture

Use a four-layer split.

### 1. Input layer

Allowed:

- local replay manifests
- local MarketContext artifacts
- local operator-provided close prices
- future reviewed local historical artifacts

Forbidden:

- broker feeds
- authenticated feeds
- cookies
- paid sources
- environment credentials
- network fetch inside the harness

### 2. Program layer

Allowed:

- pure deterministic rule objects
- explicit program version ids
- immutable config snapshots
- fixed contract count constant
- reviewed constants for gates

Forbidden:

- dynamic leverage
- martingale sizing
- hidden state that changes risk exposure
- environment-dependent behavior
- current-time-dependent behavior except explicit report timestamp

### 3. Simulation layer

Allowed:

- local-only simulated entry / close event construction
- per-session gate checks
- daily / weekly simulated loss gates
- deterministic halt recording
- append-only machine-readable logs

Forbidden:

- order placement
- broker SDK import
- exchange API import
- venue adapter
- account model that could be confused with real funds
- any write to an external system

### 4. Report layer

Allowed:

- count metrics
- gate-trip counts
- halt counts
- coverage counts
- consistency checks
- diagnostic deltas between two local program versions

Forbidden by default:

- profit guarantee
- financial advice
- expected return claim
- win-rate claim
- Sharpe or risk-adjusted return claim
- equity curve claim
- live-readiness claim
- production execution recommendation

If money-denominated simulated P/L is needed to enforce loss gates, it must be
framed as gate accounting, not as performance marketing.

## First implementation PR shape

The first code PR should be small and non-executing by default.

Suggested PR title:

```text
Add paper-trading refinement contract and pure gate model
```

Suggested scope:

- `docs/paper-trading-refinement-contract.md`
- `nms/paper/gates.py`
- `tests/test_paper_trading_gates.py`

Allowed first code:

- constants:
  - `FIXED_CONTRACT_COUNT`
  - `MAX_SESSION_LOSS_JPY`
  - `MAX_DAILY_LOSS_JPY`
  - `MAX_WEEKLY_LOSS_JPY`
- pure functions:
  - session gate evaluation
  - daily gate evaluation
  - weekly gate evaluation
  - halt reason formatting
- dataclasses:
  - `PaperGateDecision`
  - `PaperGateState`

Forbidden first code:

- replay loop
- strategy optimizer
- execution adapter
- file-writing run report
- network adapter
- CLI that looks like a trading command

Reason: prove the risk gates first before adding a harness that depends on them.

## Second implementation PR shape

After the pure gates pass review, a second PR may add a local-only harness.

Suggested PR title:

```text
Add local paper refinement dry-run harness
```

Suggested scope:

- `nms/paper/harness.py`
- `scripts/run_paper_refinement_dry_run.py`
- `docs/paper-refinement-dry-run.md`
- `tests/test_paper_refinement_harness.py`

Allowed:

- local temp files in tests
- deterministic JSON reports
- synthetic fixture input
- no default committed result artifacts

Forbidden:

- cron
- scheduled workflow
- live market source
- account credential
- broker import
- auto-generated recommendation text

## Required tests

Every PR in this lane must include tests for:

- no forbidden imports:
  - broker SDKs
  - exchange clients
  - network clients unless separately approved
- no environment credential reads:
  - `os.environ.get`
  - `os.getenv`
  - dotenv loading
- no subprocess use for data acquisition
- fixed sizing only
- gate trip at session threshold
- gate trip at daily threshold
- gate trip at weekly threshold
- no martingale / no leverage escalation by construction
- deterministic JSON serialization if a report writer is introduced

## Implementation report requirements

The code agent must report:

- exact files touched
- validation commands and results
- whether any metric can be interpreted as strategy performance
- why the PR does not alter live/broker boundaries
- whether future PRs are needed before any broader harness exists

## Review gates

A PR is not ready if any of the following are true:

- imports a broker, exchange, or venue SDK
- reads credentials
- introduces an order-like external mutation
- weakens fixed sizing
- weakens max simulated loss gates
- uses a scheduled workflow
- presents simulated results as trading advice
- claims production readiness
- stores raw external market data as a committed artifact

## Safe next action for code agent

Start with the pure gate model only.

Do not build the full paper-trading harness until the gate model has its own
reviewed PR and tests.
