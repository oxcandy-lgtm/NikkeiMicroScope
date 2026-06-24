"""Session classification for NikkeiMicroScope.

The classifier maps a ``no_trade_score`` and a ``direction_score``
to one of three advisory labels:

* ``"no-trade"``: structural reason not to take a trade.
* ``"buy-only"``: positive directional bias.
* ``"sell-only"``: negative directional bias.

The classification is purely advisory. It is not a prediction, a
recommendation, or a financial-advice claim.
"""

from __future__ import annotations

from nms.core.constants import NO_TRADE_THRESHOLD


def classify(no_trade_score: float, direction_score: float) -> str:
    """Return the advisory classification for a session.

    Rules (from ``docs/market-regime-score.md``):

    1. ``no_trade_score >= NO_TRADE_THRESHOLD`` -> ``"no-trade"``.
    2. Otherwise, positive ``direction_score`` -> ``"buy-only"``.
    3. Otherwise, negative ``direction_score`` -> ``"sell-only"``.
    4. Otherwise (``direction_score == 0`` exactly) -> ``"no-trade"``.
    """
    if no_trade_score >= NO_TRADE_THRESHOLD:
        return "no-trade"
    if direction_score > 0.0:
        return "buy-only"
    if direction_score < 0.0:
        return "sell-only"
    return "no-trade"
