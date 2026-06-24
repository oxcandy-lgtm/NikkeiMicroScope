"""Market regime scoring engine for NikkeiMicroScope.

This module is **pure**: it takes an already-validated
:class:`nms.data.models.MarketContext` and returns a
:class:`ScoreBreakdown`. It performs no I/O, no network access, no
subprocess, and no environment reads. See
``docs/core-scoring-contract.md`` for the normative formulas and
``tests/test_core_scoring.py`` for the purity audit.

All scores are dimensionless, bounded, and advisory. They are not
probabilities, predictions, or financial advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from nms.core.constants import (
    DIRECTION_WEIGHTS,
    EVENT_IMPACT_TABLE,
    EVENT_RISK_REASON_THRESHOLD,
    NO_TRADE_WEIGHT_ALIGNMENT,
    NO_TRADE_WEIGHT_EVENT_RISK,
    NO_TRADE_WEIGHT_VOLATILITY,
    PERCENT_CHANGE_SATURATION,
    VOLATILITY_BASELINE_GUARD,
    VOLATILITY_REASON_THRESHOLD,
    PlannedSide,
)
from nms.core.classification import classify
from nms.data.models import MarketContext


@dataclass(frozen=True)
class ScoreBreakdown:
    """The full advisory output for a single session.

    All numeric fields are dimensionless and bounded. ``classification``
    is one of ``"buy-only"``, ``"sell-only"``, ``"no-trade"``.
    ``no_trade_reasons`` is a tuple of human-readable strings naming
    the dominant contributors that pushed the session toward the
    ``no-trade`` classification. The tuple is empty when the
    classification is not ``no-trade``.
    """

    direction_score: float
    volatility_score: float
    event_risk_score: float
    alignment_penalty: float
    no_trade_score: float
    no_trade_reasons: Tuple[str, ...]
    classification: str


def _clamp(x: float, lo: float, hi: float) -> float:
    """Clamp ``x`` to the closed interval ``[lo, hi]``."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _normalize_percent_change(percent_change: float) -> float:
    """Map a percent-change value to a signal in ``[-1, +1]``.

    Saturation is at ``PERCENT_CHANGE_SATURATION`` (default: 2.0
    percent). A move of +/- 2% fully drives the signal.
    """
    return _clamp(percent_change / PERCENT_CHANGE_SATURATION, -1.0, 1.0)


def direction_score(context: MarketContext) -> float:
    """Compute the advisory direction score in ``[-1, +1]``.

    MVP normalization policy (see ``docs/core-scoring-contract.md``):

    * Only ``nikkei_night_session.percent_change`` is currently used.
      Its contribution is ``DIRECTION_WEIGHTS["nikkei_night"] * s``,
      where ``s`` is the bounded normalizer applied to the percent
      change.
    * The other five slots in ``DIRECTION_WEIGHTS`` contribute a
      neutral ``0.0`` at MVP because the corresponding daily-change
      fields are not yet part of the ``MarketContext`` schema. The
      weights are reserved for future use and the sum is unchanged.
    * Do not invent change values from absolute levels. The neutral
      contribution is the honest answer for MVP.

    The result is clamped to ``[-1, +1]`` as a defense in depth even
    though the bounded normalizer and the weights already guarantee
    the bound in practice.
    """
    nikkei_signal = _normalize_percent_change(
        context.nikkei_night_session.percent_change
    )
    raw = DIRECTION_WEIGHTS["nikkei_night"] * nikkei_signal
    return _clamp(raw, -1.0, 1.0)


def volatility_score(context: MarketContext) -> float:
    """Compute the advisory volatility score in ``[0, 1]``.

    MVP formula: ``clamp(1 - realized_vol / baseline_vol, 0, 1)``,
    where ``baseline_vol`` is
    ``context.volatility_context.atr_like``. If the baseline is at or
    below ``VOLATILITY_BASELINE_GUARD``, the function returns ``0.0``
    as a safe fallback to avoid division by zero. A warning string is
    not currently emitted (the package is pure and side-effect-free);
    callers can detect the safe fallback by checking
    ``context.volatility_context.atr_like <= 0``.
    """
    realized = context.volatility_context.realized_vol
    baseline = context.volatility_context.atr_like
    if baseline <= VOLATILITY_BASELINE_GUARD:
        return 0.0
    return _clamp(1.0 - realized / baseline, 0.0, 1.0)


def event_risk_score(context: MarketContext) -> float:
    """Compute the advisory event-risk score in ``[0, 1]``.

    MVP formula: the maximum impact score across all events in
    ``context.economic_event_risk.events``. Impact values are looked
    up in :data:`nms.core.constants.EVENT_IMPACT_TABLE` with a
    lowercased key. Unrecognized or empty impact strings map to 0.0.
    """
    events = context.economic_event_risk.events
    if not events:
        return 0.0
    impacts = [
        EVENT_IMPACT_TABLE.get(ev.impact.lower(), 0.0) for ev in events
    ]
    return max(impacts) if impacts else 0.0


def alignment_penalty(
    direction: float, planned_side: PlannedSide
) -> float:
    """Compute the alignment penalty in ``{0.0, 1.0}``.

    * ``"buy"`` planned side + negative direction -> ``1.0``.
    * ``"sell"`` planned side + positive direction -> ``1.0``.
    * Otherwise -> ``0.0`` (including the ``"none"`` planned side).
    """
    if planned_side == "buy" and direction < 0.0:
        return 1.0
    if planned_side == "sell" and direction > 0.0:
        return 1.0
    return 0.0


def no_trade_score(vol: float, event: float, penalty: float) -> float:
    """Compute the advisory no-trade score in ``[0, 1]``.

    MVP formula:
    ``clamp(NO_TRADE_WEIGHT_VOLATILITY * vol
          + NO_TRADE_WEIGHT_EVENT_RISK * event
          + NO_TRADE_WEIGHT_ALIGNMENT * penalty, 0, 1)``.
    """
    return _clamp(
        NO_TRADE_WEIGHT_VOLATILITY * vol
        + NO_TRADE_WEIGHT_EVENT_RISK * event
        + NO_TRADE_WEIGHT_ALIGNMENT * penalty,
        0.0,
        1.0,
    )


def _build_no_trade_reasons(
    event: float,
    vol: float,
    penalty: float,
    planned_side: PlannedSide,
    context: MarketContext,
) -> Tuple[str, ...]:
    """Build the human-readable reason list for a ``no-trade`` call."""
    reasons: list[str] = []
    if event >= EVENT_RISK_REASON_THRESHOLD:
        # Name the first event whose impact equals the max-impact
        # value used for the event_risk_score. This gives a
        # reproducible reason string.
        events = context.economic_event_risk.events
        max_impact = max(
            (EVENT_IMPACT_TABLE.get(ev.impact.lower(), 0.0) for ev in events),
            default=0.0,
        )
        for ev in events:
            if EVENT_IMPACT_TABLE.get(ev.impact.lower(), 0.0) == max_impact:
                reasons.append(f"event_risk:{ev.name}")
                break
    if vol >= VOLATILITY_REASON_THRESHOLD:
        reasons.append(f"volatility_compression:{vol:.3f}")
    if penalty > 0.0:
        reasons.append(f"alignment_penalty:{planned_side}_vs_direction")
    return tuple(reasons)


def score_context(
    context: MarketContext, planned_side: PlannedSide
) -> ScoreBreakdown:
    """Score a single :class:`MarketContext` and return a breakdown.

    This is the main entry point of the scoring engine. It composes
    the four component scores, the alignment penalty, the no-trade
    score, the reason list, and the classification into a single
    :class:`ScoreBreakdown`.

    The function does not mutate ``context``. It is pure and
    side-effect-free.
    """
    d = direction_score(context)
    v = volatility_score(context)
    e = event_risk_score(context)
    p = alignment_penalty(d, planned_side)
    nt = no_trade_score(v, e, p)
    reasons = _build_no_trade_reasons(e, v, p, planned_side, context)
    cls = classify(nt, d)
    return ScoreBreakdown(
        direction_score=d,
        volatility_score=v,
        event_risk_score=e,
        alignment_penalty=p,
        no_trade_score=nt,
        no_trade_reasons=reasons,
        classification=cls,
    )
