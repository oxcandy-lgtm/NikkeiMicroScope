"""Data layer for NikkeiMicroScope.

The data layer is read-only and local-first at MVP. It defines:

* the normalized :class:`MarketContext` schema (``models``);
* the :class:`MarketContextAdapter` protocol and the fixture-backed
  implementation (``adapters``);
* a JSON fixture loader (``fixture_loader``);
* a schema validator (``validate``).

No module in this package may import network libraries, broker SDKs,
``dotenv``, or read credentials from the environment. This constraint
is enforced socially and via unit tests; see
``tests/test_fixture_loader.py``.
"""

from __future__ import annotations

from nms.data.models import (
    EconomicEventRisk,
    EventItem,
    Fx,
    IntradayRange,
    MarketContext,
    NikkeiNightSession,
    PreviousDay,
    Semiconductor,
    UsEquities,
    UsYields,
    VolatilityContext,
)
from nms.data.adapters import (
    FixtureMarketContextAdapter,
    MarketContextAdapter,
)
from nms.data.fred_treasury import FredTreasuryOverlayAdapter
from nms.data.fred_sp500 import (
    FredSP500AdapterError,
    FredSP500OverlayAdapter,
    FredSP500SourceConfig,
)
from nms.data.fred_usdjpy import (
    FredUSDJPYAdapterError,
    FredUSDJPYOverlayAdapter,
    FredUSDJPYSourceConfig,
)
from nms.data.fred_nasdaq100 import (
    FredNASDAQ100AdapterError,
    FredNASDAQ100OverlayAdapter,
    FredNASDAQ100SourceConfig,
)
from nms.data.public_sources import (
    FredObservation,
    FredTreasuryAdapterError,
    FredTreasurySourceConfig,
    _parse_fred_csv,
    _parse_fred_csv_with_previous,
)
from nms.data.validate import ValidationError, validate_market_context

__all__ = [
    "EconomicEventRisk",
    "EventItem",
    "FixtureMarketContextAdapter",
    "FredObservation",
    "FredSP500AdapterError",
    "FredSP500OverlayAdapter",
    "FredSP500SourceConfig",
    "FredTreasuryAdapterError",
    "FredTreasuryOverlayAdapter",
    "FredTreasurySourceConfig",
    "FredUSDJPYAdapterError",
    "FredUSDJPYOverlayAdapter",
    "FredUSDJPYSourceConfig",
    "FredNASDAQ100AdapterError",
    "FredNASDAQ100OverlayAdapter",
    "FredNASDAQ100SourceConfig",
    "Fx",
    "IntradayRange",
    "MarketContext",
    "MarketContextAdapter",
    "NikkeiNightSession",
    "PreviousDay",
    "Semiconductor",
    "UsEquities",
    "UsYields",
    "ValidationError",
    "VolatilityContext",
    "_parse_fred_csv",
    "_parse_fred_csv_with_previous",
    "validate_market_context",
]
