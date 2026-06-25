"""FRED public S&P 500 adapter for NikkeiMicroScope.

This module is the FRED public S&P 500 adapter. It:

* Accepts an already-validated :class:`MarketContext` from a base adapter
  (any object satisfying the :class:`MarketContextAdapter` protocol).
* Fetches or parses FRED SP500 daily index-level observations.
* Overlays only the ``us_equities.sp500`` and
  ``us_equities.sp500_change_pct`` fields on the ``MarketContext``.
* Returns a new frozen, validated :class:`MarketContext``.

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
``us_equities.sp500`` and ``us_equities.sp500_change_pct`` fields are
taken from FRED. All other fields come from the base adapter.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from typing import Callable, List, Optional, Protocol

from nms.data.models import MarketContext, UsEquities
from nms.data.validate import validate_market_context


class MarketContextAdapter(Protocol):
    """Read-only adapter that produces a :class:`MarketContext` for a date."""

    def load(self, session_date: str) -> MarketContext:
        ...


#: Type alias for the injected HTTP GET function. The default
#: implementation uses ``urllib.request``; tests inject a fake.
HttpGet = Callable[[str], str]


@dataclass(frozen=True)
class FredSP500SourceConfig:
    """Configuration for the FRED SP500 data source.

    Attributes:
        sp500_url: URL of the FRED SP500 CSV.
        timeout_seconds: HTTP timeout in seconds for the default
            :func:`FredSP500OverlayAdapter._default_http_get`.
    """

    sp500_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500"
    timeout_seconds: float = 10.0


class FredSP500AdapterError(ValueError):
    """Raised when FRED SP500 data is missing or malformed.

    Raised for:

    * Empty CSV.
    * Missing ``SP500`` column.
    * No usable observations.
    * No observation at or before ``session_date``.
    * No previous SP500 observation for change calculation.
    * Malformed date.
    * Malformed numeric value.
    * Non-positive previous SP500 value.
    """


def _parse_fred_csv_observations(
    text: str, series_id: str
) -> List["FredSP500Observation"]:
    """Parse FRED CSV text and return all valid observations sorted by date.

    FRED CSV format::

        DATE,SP500
        2024-01-02,4760.23
        2024-01-03,.

    Missing values are represented as ``.``.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or series_id not in reader.fieldnames:
        raise FredSP500AdapterError(
            f"FRED CSV missing expected column {series_id!r}"
        )

    observations: List[FredSP500Observation] = []
    for row in reader:
        date_str = (row.get("DATE") or "").strip()
        value_str = (row.get(series_id) or "").strip()
        if not date_str or not value_str or value_str == ".":
            continue
        try:
            obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            obs_value = float(value_str)
        except ValueError as e:
            raise FredSP500AdapterError(
                f"Malformed FRED row: {row!r}: {e}"
            ) from e
        observations.append(FredSP500Observation(date=obs_date, value=obs_value))

    if not observations:
        raise FredSP500AdapterError(
            f"FRED CSV contains no usable {series_id} observations"
        )

    observations.sort(key=lambda o: o.date)
    return observations


def _parse_fred_csv_with_previous(
    text: str, series_id: str, on_date: date
) -> tuple["FredSP500Observation", Optional["FredSP500Observation"]]:
    """Parse FRED CSV and return the latest observation at or before
    ``on_date``, plus the previous observation (the one immediately
    before the latest).
    """
    observations = _parse_fred_csv_observations(text, series_id)

    latest_idx = -1
    for i, obs in enumerate(observations):
        if obs.date <= on_date:
            latest_idx = i
        else:
            break

    if latest_idx == -1:
        raise FredSP500AdapterError(
            f"No FRED {series_id} observation at or before {on_date.isoformat()}"
        )

    latest = observations[latest_idx]
    previous = observations[latest_idx - 1] if latest_idx > 0 else None
    return latest, previous


@dataclass(frozen=True)
class FredSP500Observation:
    """A single FRED daily SP500 observation."""

    date: date
    value: float


class FredSP500OverlayAdapter:
    """FRED public S&P 500 adapter that overlays only ``sp500`` and
    ``sp500_change_pct`` on the ``us_equities`` of a
    :class:`MarketContext`.

    Behavior:

    1. Load a baseline :class:`MarketContext` from ``base_adapter``.
    2. Fetch SP500 from FRED (public, no-auth CSV).
    3. Choose the latest available observation at or before
       ``session_date``.
    4. Choose the previous available observation strictly before the
       selected date.
    5. Compute:

       * ``sp500 = current_sp500``
       * ``sp500_change_pct = ((current / previous) - 1.0) * 100.0``

    6. Replace only the two ``us_equities`` fields via
       :func:`dataclasses.replace`.
    7. Re-validate the final context through
       :func:`validate_market_context`.
    """

    def __init__(
        self,
        base_adapter: MarketContextAdapter,
        http_get: Optional[HttpGet] = None,
        source_config: Optional[FredSP500SourceConfig] = None,
    ) -> None:
        self._base_adapter = base_adapter
        self._http_get: HttpGet = http_get or self._default_http_get
        self._source_config = source_config or FredSP500SourceConfig()

    def _default_http_get(self, url: str) -> str:
        """Default HTTP GET using stdlib ``urllib.request``. No auth, no headers.

        The default fetcher is intentionally minimal: no headers, no
        cookies, no auth. The FRED CSVs are publicly downloadable
        without authentication. The timeout is taken from
        ``self._source_config.timeout_seconds`` rather than being
        hardcoded, so tests and operators can tune it.
        """
        with urllib.request.urlopen(
            url, timeout=self._source_config.timeout_seconds
        ) as response:
            return response.read().decode("utf-8")

    def load(self, session_date: str) -> MarketContext:
        """Load a :class:`MarketContext` with FRED SP500 overlaid.

        Steps:

        1. Load a baseline :class:`MarketContext` from the base adapter.
        2. Fetch SP500 from FRED.
        3. Choose the latest observation at or before ``session_date``.
        4. Choose the previous observation strictly before the latest.
        5. Compute ``sp500`` and ``sp500_change_pct``.
        6. Replace only the two ``us_equities`` fields.
        7. Re-validate the result through
           :func:`validate_market_context`.

        Returns:
            A new frozen, validated :class:`MarketContext` whose
            ``us_equities.sp500`` and ``us_equities.sp500_change_pct``
            are sourced from FRED and whose other fields come from
            the base adapter.

        Raises:
            FredSP500AdapterError: If the FRED data is missing,
                malformed, if no previous SP500 observation is
                available, or if the previous SP500 value is
                non-positive.
        """
        # 1. Load baseline
        baseline = self._base_adapter.load(session_date)

        if not isinstance(baseline, MarketContext):
            raise FredSP500AdapterError(
                "base adapter did not return a MarketContext: "
                f"got {type(baseline).__name__}"
            )

        # Parse session_date to a date object
        target_date = datetime.strptime(session_date, "%Y-%m-%d").date()

        # 2. Fetch SP500
        sp500_text = self._http_get(self._source_config.sp500_url)

        # 3 + 4. Choose latest and previous observations
        sp500_obs, sp500_prev = _parse_fred_csv_with_previous(
            sp500_text, "SP500", target_date
        )

        # 5. Compute sp500 and sp500_change_pct
        sp500 = sp500_obs.value
        if sp500_prev is None:
            raise FredSP500AdapterError(
                "No previous SP500 observation available "
                f"before {sp500_obs.date.isoformat()} for "
                "sp500_change_pct"
            )
        if sp500_prev.value <= 0.0:
            raise FredSP500AdapterError(
                f"Previous SP500 value is non-positive: {sp500_prev.value} "
                f"on {sp500_prev.date.isoformat()}"
            )
        sp500_change_pct = ((sp500 / sp500_prev.value) - 1.0) * 100.0

        # 6. Overlay only us_equities.sp500 and us_equities.sp500_change_pct
        new_us_equities = replace(
            baseline.us_equities,
            sp500=sp500,
            sp500_change_pct=sp500_change_pct,
        )
        new_ctx = replace(baseline, us_equities=new_us_equities)

        # 7. Re-validate
        return validate_market_context(asdict(new_ctx))
