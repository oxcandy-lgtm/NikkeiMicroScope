"""Core scoring engine for NikkeiMicroScope.

This package is **pure**: it takes an already-validated
:class:`nms.data.models.MarketContext` and returns advisory scores
and a classification. It performs no I/O, no network access, no
subprocess, and no environment reads. See
``docs/core-scoring-contract.md`` for the normative formulas and
``tests/test_core_scoring.py`` for the purity audit.

Hard constraints (enforced socially and via unit tests):

* No import of network libraries (``urllib``, ``http``, ``socket``,
  ``requests``, ``httpx``, ``aiohttp``).
* No import of broker / exchange / FIX SDKs.
* No import of ``dotenv``, ``os.environ``, or any credential reader.
* No import of ``subprocess``, ``shutil``, or shell-out modules.
* No import of ``json`` or ``pathlib`` — ``nms/core/`` does not read
  files. File I/O is the data layer's responsibility.
"""

from __future__ import annotations

from nms.core.classification import classify
from nms.core.constants import (
    DIRECTION_WEIGHTS,
    EVENT_IMPACT_TABLE,
    NO_TRADE_THRESHOLD,
    PERCENT_CHANGE_SATURATION,
    PlannedSide,
)
from nms.core.scoring import (
    ScoreBreakdown,
    alignment_penalty,
    direction_score,
    event_risk_score,
    no_trade_score,
    score_context,
    volatility_score,
)

__all__ = [
    "DIRECTION_WEIGHTS",
    "EVENT_IMPACT_TABLE",
    "NO_TRADE_THRESHOLD",
    "PERCENT_CHANGE_SATURATION",
    "PlannedSide",
    "ScoreBreakdown",
    "alignment_penalty",
    "classify",
    "direction_score",
    "event_risk_score",
    "no_trade_score",
    "score_context",
    "volatility_score",
]
