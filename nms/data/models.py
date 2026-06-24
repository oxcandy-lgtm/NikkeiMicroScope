"""Normalized :class:`MarketContext` data model for NikkeiMicroScope.

This module is stdlib-only. It uses :mod:`dataclasses` to define the
shape of a single trading session's market context, matching the input
groups enumerated in ``docs/product-spec.md`` and ``docs/architecture.md``.

The schema is intentionally observation-only. It contains no fields
for account state, position size, broker endpoints, order placement,
or credentials. Any such field is out of scope and will be rejected
by the validator in :mod:`nms.data.validate`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

#: Canonical MVP timezone. All fixtures and validation enforce this.
MVP_TIMEZONE = "Asia/Tokyo"


@dataclass(frozen=True)
class UsEquities:
    """US equity index closes / change values for the session."""

    sp500: float
    dow: float
    nasdaq100: float
    russell2000: float


@dataclass(frozen=True)
class Semiconductor:
    """Semiconductor index context (SOX / Philadelphia Semiconductor Index)."""

    sox: float


@dataclass(frozen=True)
class Fx:
    """FX context. ``usdjpy`` is JPY per 1 USD."""

    usdjpy: float


@dataclass(frozen=True)
class UsYields:
    """US Treasury yield context (in percent)."""

    us2y: float
    us10y: float
    us10y_minus_us2y: float


@dataclass(frozen=True)
class NikkeiNightSession:
    """Nikkei 225 night-session summary."""

    close: float
    high: float
    low: float
    range: float
    percent_change: float


@dataclass(frozen=True)
class PreviousDay:
    """Nikkei 225 previous-day summary (cash session)."""

    high: float
    low: float
    close: float
    range: float


@dataclass(frozen=True)
class EventItem:
    """A single scheduled economic event.

    MVP fields are intentionally minimal. ``name`` is required;
    ``time_jst`` and ``impact`` are optional but recommended.
    """

    name: str
    time_jst: str = ""
    impact: str = ""


@dataclass(frozen=True)
class EconomicEventRisk:
    """Economic event risk for the session window."""

    events: List[EventItem] = field(default_factory=list)


@dataclass(frozen=True)
class IntradayRange:
    """First 15 minutes of the cash session, plus an ATR-like baseline."""

    first_15m_high: float
    first_15m_low: float
    first_15m_range: float
    atr_like_baseline: float


@dataclass(frozen=True)
class VolatilityContext:
    """Realized vol, ATR-like measure, and a compression flag."""

    realized_vol: float
    atr_like: float
    compression_flag: bool


@dataclass(frozen=True)
class MarketContext:
    """The normalized market context for a single trading session.

    This is the canonical shape that downstream scoring and reporting
    code (future PRs) will consume. The schema is locked by
    ``docs/data-adapter-contract.md``.
    """

    session_date: str
    timezone: str
    us_equities: UsEquities
    semiconductor: Semiconductor
    fx: Fx
    us_yields: UsYields
    nikkei_night_session: NikkeiNightSession
    previous_day: PreviousDay
    economic_event_risk: EconomicEventRisk
    intraday_range: IntradayRange
    volatility_context: VolatilityContext
