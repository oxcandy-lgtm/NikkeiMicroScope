"""Constants for the market regime scoring engine.

This module is pure data. It depends only on :mod:`typing` (for
``Literal``) and is part of the ``nms/core/`` package, which is
forbidden from importing network, subprocess, env-reading, or
broker modules. See ``docs/core-scoring-contract.md`` for the
normative definitions and ``tests/test_core_scoring.py`` for the
purity audit.
"""

from __future__ import annotations

from typing import Literal


#: The planned side for a session. Used by the alignment penalty.
#: ``"none"`` means "no planned trade" and forces the alignment
#: penalty to 0.0.
PlannedSide = Literal["buy", "sell", "none"]


#: Direction-score weights. The sum is 1.0. These are the MVP weights
#: documented in ``docs/market-regime-score.md``. Only the
#: ``nikkei_night`` slot is currently exercised by the implementation
#: because the other slots require a daily-change field that the MVP
#: ``MarketContext`` schema does not yet provide. The other slots
#: contribute a neutral 0.0 at MVP. See
#: ``docs/core-scoring-contract.md`` for the normalization policy.
DIRECTION_WEIGHTS: dict[str, float] = {
    "nasdaq100": 0.20,
    "sox": 0.20,
    "sp500": 0.10,
    "usdjpy": 0.20,
    "us10y": 0.10,  # sign-flipped at consumption time
    "nikkei_night": 0.20,
}


#: A percent change of this magnitude saturates the bounded normalizer
#: at +/- 1.0. The default ``2.0`` means a 2% move fully drives the
#: signal. This is a documented MVP constant; tuning it requires a
#: research PR per ``AGENTS.md``.
PERCENT_CHANGE_SATURATION: float = 2.0


#: Guard against division by zero in the volatility-score formula.
#: If ``baseline_vol`` is at or below this threshold, the volatility
#: score is defined as 0.0 (safe fallback).
VOLATILITY_BASELINE_GUARD: float = 1e-12


#: Static event-impact table. Unknown / empty / unrecognized impact
#: strings map to 0.0. Keys are lowercased at lookup time.
EVENT_IMPACT_TABLE: dict[str, float] = {
    "high": 1.0,
    "medium": 0.5,
    "low": 0.25,
}


#: No-trade score weights. Sum to 1.0. Same as the MVP weights in
#: ``docs/market-regime-score.md``.
NO_TRADE_WEIGHT_VOLATILITY: float = 0.40
NO_TRADE_WEIGHT_EVENT_RISK: float = 0.40
NO_TRADE_WEIGHT_ALIGNMENT: float = 0.20


#: Classification threshold. ``no_trade_score >= NO_TRADE_THRESHOLD``
#: forces the ``no-trade`` classification.
NO_TRADE_THRESHOLD: float = 0.5


#: Thresholds for emitting a no-trade reason string. These are
#: separate from the classification threshold and are intentionally
#: aligned with it (``0.5``) so that the dominant contributors that
#: push a session over the threshold are named in the reason list.
EVENT_RISK_REASON_THRESHOLD: float = 0.5
VOLATILITY_REASON_THRESHOLD: float = 0.5
