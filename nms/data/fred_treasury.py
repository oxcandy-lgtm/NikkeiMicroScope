"""FRED public treasury adapter for NikkeiMicroScope.

This module is the FRED public treasury adapter. It:

* Accepts an already-validated :class:`MarketContext` from a base adapter
  (any object satisfying the :class:`MarketContextAdapter` protocol).
* Fetches or parses FRED DGS2 and DGS10 daily treasury yield observations.
* Overlays only the ``us_yields`` fields on the ``MarketContext``.
* Returns a new frozen, validated :class:`MarketContext`.

The adapter is public/no-auth: it uses only publicly available FRED CSV
data and requires no API key, no auth header, no cookie.

Hard constraints (enforced socially and via unit tests):

* No secrets, no API key, no PAT, no auth header or cookie.
* No broker SDK, no order placement, no live trading.
* No subprocess, no environment variable credential reading.
* No new runtime dependencies; stdlib only.
* The ``http_get`` parameter is the only network entry point.
* Tests must inject a fake ``http_get`` and prove no socket/subprocess
  is used.

The adapter returns a fully validated :class:`MarketContext` whose
``us_yields`` fields (``us2y``, ``us10y``, ``us10y_minus_us2y``,
``us10y_change_bp``) are taken from FRED. All other fields come from
the base adapter.
"""

from __future__ import annotations

import urllib.request
from dataclasses import asdict, replace
from datetime import date, datetime
from typing import Any, Callable, Mapping, Optional, Protocol


class MarketContextAdapter(Protocol):
    """Read-only adapter that produces a :class:`MarketContext` for a date.

    Implemented by :class:`nms.data.adapters.FixtureMarketContextAdapter`
    and any future adapter.
    """

    def load(self, session_date: str) -> Any:
        ...


from nms.data.models import MarketContext, UsYields
from nms.data.public_sources import (
    FredObservation,
    FredTreasuryAdapterError,
    FredTreasurySourceConfig,
    _parse_fred_csv,
    _parse_fred_csv_with_previous,
)
from nms.data.validate import validate_market_context


#: Type alias for the injected HTTP GET function. The default
#: implementation uses ``urllib.request``; tests inject a fake.
HttpGet = Callable[[str], str]


class FredTreasuryOverlayAdapter:
    """FRED public treasury adapter that overlays only ``us_yields`` on a
    :class:`MarketContext`.

    Behavior:

    1. Load a baseline :class:`MarketContext` from ``base_adapter``.
    2. Fetch DGS2 and DGS10 from FRED (public, no-auth CSV).
    3. Choose the latest available observation at or before
       ``session_date``.
    4. Overlay only the four ``us_yields`` fields:

       * ``us2y`` from DGS2
       * ``us10y`` from DGS10
       * ``us10y_minus_us2y`` = ``us10y - us2y``
       * ``us10y_change_bp`` = (today DGS10 - previous DGS10) * 100

    5. Return a new frozen, validated :class:`MarketContext``.
    """

    def __init__(
        self,
        base_adapter: MarketContextAdapter,
        http_get: Optional[HttpGet] = None,
        source_config: Optional[FredTreasurySourceConfig] = None,
    ) -> None:
        self._base_adapter = base_adapter
        self._http_get: HttpGet = http_get or self._default_http_get
        self._source_config = source_config or FredTreasurySourceConfig()

    @staticmethod
    def _default_http_get(url: str) -> str:
        """Default HTTP GET using stdlib ``urllib.request``. No auth, no headers.

        The default fetcher is intentionally minimal: no headers, no
        cookies, no auth. The FRED CSVs are publicly downloadable
        without authentication.
        """
        with urllib.request.urlopen(url, timeout=10.0) as response:
            return response.read().decode("utf-8")

    def load(self, session_date: str) -> MarketContext:
        """Load a :class:`MarketContext` with FRED treasury yields overlaid.

        Steps:

        1. Load a baseline :class:`MarketContext` from the base adapter.
        2. Fetch DGS2 and DGS10 from FRED.
        3. Choose the latest observation at or before ``session_date``.
        4. Overlay only the ``us_yields`` fields.
        5. Return a new frozen, validated :class:`MarketContext``.

        Returns:
            A fully validated :class:`MarketContext` whose ``us_yields``
            fields are sourced from FRED and whose other fields come
            from the base adapter.

        Raises:
            FredTreasuryAdapterError: If the FRED data is missing,
                malformed, or if the selected dates for DGS2 and DGS10
                do not match.
        """
        # 1. Load baseline
        baseline = self._base_adapter.load(session_date)
        if not isinstance(baseline, MarketContext):
            raise FredTreasuryAdapterError(
                "base adapter did not return a MarketContext: "
                f"got {type(baseline).__name__}"
            )

        # Parse session_date to a date object
        target_date = _parse_session_date(baseline.session_date)

        # 2. Fetch DGS2 and DGS10
        dgs2_text = self._http_get(self._source_config.dgs2_url)
        dgs10_text = self._http_get(self._source_config.dgs10_url)

        # 3. Choose latest observation
        dgs2_obs, _ = _parse_fred_csv_with_previous(
            dgs2_text, "DGS2", target_date
        )
        dgs10_obs, dgs10_prev = _parse_fred_csv_with_previous(
            dgs10_text, "DGS10", target_date
        )

        if dgs2_obs.date != dgs10_obs.date:
            raise FredTreasuryAdapterError(
                f"DGS2 and DGS10 dates mismatch: "
                f"DGS2={dgs2_obs.date.isoformat()}, "
                f"DGS10={dgs10_obs.date.isoformat()}"
            )

        # 4. Compute the four us_yields fields
        us2y = dgs2_obs.value
        us10y = dgs10_obs.value
        us10y_minus_us2y = us10y - us2y
        if dgs10_prev is not None:
            us10y_change_bp = (dgs10_obs.value - dgs10_prev.value) * 100.0
        else:
            us10y_change_bp = 0.0

        # 5. Overlay only us_yields via dataclasses.replace
        new_ctx = replace(
            baseline,
            us_yields=UsYields(
                us2y=us2y,
                us10y=us10y,
                us10y_minus_us2y=us10y_minus_us2y,
                us10y_change_bp=us10y_change_bp,
            ),
        )

        # 6. Re-validate via validate_market_context to enforce the
        #    schema and nested strictness.
        return validate_market_context(asdict(new_ctx))


def _parse_session_date(session_date: str) -> date:
    """Parse a session_date string (ISO YYYY-MM-DD) to a date object."""
    return datetime.strptime(session_date, "%Y-%m-%d").date()
