# Research Plan — NikkeiMicroScope (NMS)

## Hypotheses

1. **Context-aligned entries outperform context-misaligned entries.**
   Sessions whose `direction_score` agrees with the planned side have
   higher reachability of +50円 / +100円 moves than misaligned ones.

2. **High `event_risk_score` reduces reachable-move probability.**
   Sessions flagged for scheduled high-impact events are more likely
   to fail the reachable-move evaluation, regardless of direction.

3. **Low-volatility sessions are a structural `no-trade` class.**
   When realized vol and ATR-like context are compressed relative to
   recent history, +100円 moves are typically not reachable from the
   open in the cash session.

4. **Previous-day high / low act as a magnet and a wall.**
   Sessions whose open sits within a narrow band of the prior day's
   high / low have a higher no-trade rate than sessions opening far
   from prior levels.

These hypotheses are **advisory research questions**, not claims of
predictive accuracy. The MVP exists to test them honestly.

## Minimum Data Requirements

- At least **250 trading sessions** of Nikkei 225 micro futures
  history (cash session + night session bridging).
- Corresponding daily context: US equities, Nasdaq-100, SOX, USDJPY,
  US 2Y / 10Y, scheduled economic event calendar, prior-day
  Nikkei high / low.
- 15-minute intraday range for each cash session.
- ATR-like measure computed on the daily series.

All data must be public, no-auth sources. If a required source is
not available without credentials, that input is dropped and the
gap is recorded in `docs/architecture.md` and the relevant
implementation report.

## Backtest Metrics

For each backtest run, compute and report:

- **Reach rate** of +50円 and +100円 moves from the open, conditioned
  on `classification` (`buy-only` / `sell-only` / `no-trade`).
- **No-trade rate** per regime (high-vol, low-vol, event-risk,
  aligned, misaligned).
- **False-positive rate**: sessions classified as `buy-only` /
  `sell-only` that did *not* reach the planned move.
- **Distribution** of `direction_score`, `volatility_score`,
  `event_risk_score`, `no_trade_score`.
- **Coverage**: share of sessions that fall into each `classification`.

No PnL claim, no Sharpe, no "we beat buy-and-hold" claim. The MVP
intentionally avoids PnL reporting because the backtest is on
advisory classification, not on a trading strategy.

## Walk-Forward Validation

- Use rolling **walk-forward** windows, not a single in-sample /
  out-of-sample split.
- Window length: at least 125 sessions.
- Step: 25 sessions.
- For each window, the score formulas in `docs/market-regime-score.md`
  are **frozen** to the values defined in this repository at the
  start of the window. No peeking, no re-fitting inside the window.
- Report metrics per window and aggregated, with the aggregation
  rule documented in the implementation report.

## Paper-Trade Acceptance Gate

Paper trading is the only allowed pre-live step. The paper-trade
phase may begin only when all of the following are true:

1. Backtest metrics on walk-forward windows have been recorded in
   `docs/research-plan.md` or a follow-up research doc.
2. A hard simulated loss gate is defined in `docs/risk-policy.md`
   and enforced by the paper-trading code.
3. The dry-run Satellite update is green and current.
4. An implementation report for the paper-trading layer is
   attached to the relevant PR, including a safety / privacy
   audit (no secrets, no PAT, no live-trading code path).
5. An explicit operator instruction authorizes opening the
   paper-trading phase.

The paper-trading code path must be in a `paper/` subtree and must
not share code with any future live-execution layer.

## Out of Scope for Research

- Predictive accuracy claims expressed as a single number.
- Profit guarantees.
- Comparison against specific commercial signal services.
- Auto-optimization of score weights against user outcomes.
