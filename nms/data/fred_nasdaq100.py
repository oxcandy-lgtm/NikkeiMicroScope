"""FRED public NASDAQ-100 adapter for NikkeiMicroScope.

This module is the FRED public NASDAQ-100 adapter. It:

* Accepts an already-validated :class:`MarketContext` from a base
  adapter (any object satisfying the :class:`MarketContextAdapter`
  protocol).
* Fetches or parses FRED ``NASDAQ100`` daily index-level
  observations.
* Overlays only the ``us_equities.nasdaq100`` and
  ``us_equities.nasdaq100_change_pct`` fields on the
  ``MarketContext``.
* Returns a new frozen, validated :class:`MarketContext``.

The adapter is public/no-auth: it uses only publicly available FRED
CSV data and requires no API key, no auth header, no cookie.

Hard constraints (enforced socially and via unit tests):

* No secrets, no API key, no PAT, no auth header or cookie.
* No broker SDK, no order placement, no live trading.
* No subprocess, no environment variable credential reading.
* No new runtime dependencies; stdlib only.
* The ``http_get`` parameter is the only network entry point.
* Tests must inject a fake ``http_get`` and prove no
  socket/subprocess is used.

Copyright / redistribution guard:

The FRED ``NASDAQ100`` series is sourced from Nasdaq, Inc. and is
subject to the standard FRED citation / pre-approval policy. This
adapter is for **operator-side observation only**. Raw downloaded
``NASDAQ100`` observations must not be committed as fixtures or
redistributed via exports. Tests and dry-runs use small synthetic
mocked CSVs only.

The adapter returns a fully validated :class:`MarketContext` whose
``us_equities.nasdaq100`` and ``us_equities.nasdaq100_change_pct``
fields are taken from FRED. All other fields come from the base
adapter.
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
class FredNASDAQ100SourceConfig:
    """Configuration for the FRED NASDAQ100 data source.

    Attributes:
        nasdaq100_url: URL of the FRED NASDAQ100 CSV.
        timeout_seconds: HTTP timeout in seconds for the default
            :func:`FredNASDAQ100OverlayAdapter._default_http_get`.
    """

    nasdaq100_url: str = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQ100"
    )
    timeout_seconds: float = 10.0


class FredNASDAQ100AdapterError(ValueError):
    """Raised when FRED NASDAQ100 data is missing or malformed.

    Raised for:

    * Empty CSV.
    * Missing ``NASDAQ100`` column.
    * No usable observations.
    * No observation at or before ``session_date``.
    * No previous NASDAQ100 observation for change calculation.
    * Malformed date.
    * Malformed numeric value.
    * Non-positive previous NASDAQ100 value.
    """


def _parse_fred_csv_observations(
    text: str, series_id: str
) -> List["FredNASDAQ100Observation"]:
    """Parse FRED CSV text and return all valid observations sorted by date.

    FRED CSV format::

        DATE,NASDAQ100
        2024-01-02,16826.12
        2024-01-03,.

    Missing values are represented as ``.``.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or series_id not in reader.fieldnames:
        raise FredNASDAQ100AdapterError(
            f"FRED CSV missing expected column {series_id!r}"
        )

    observations: List[FredNASDAQ100Observation] = []
    for row in reader:
        date_str = (row.get("DATE") or "").strip()
        value_str = (row.get(series_id) or "").strip()
        if not date_str or not value_str or value_str == ".":
            continue
        try:
            obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            obs_value = float(value_str)
        except ValueError as e:
            raise FredNASDAQ100AdapterError(
                f"Malformed FRED row: {row!r}: {e}"
            ) from e
        observations.append(
            FredNASDAQ100Observation(date=obs_date, value=obs_value)
        )

    if not observations:
        raise FredNASDAQ100AdapterError(
            f"FRED CSV contains no usable {series_id} observations"
        )

    observations.sort(key=lambda o: o.date)
    return observations


def _parse_fred_csv_with_previous(
    text: str, series_id: str, on_date: date
) -> tuple["FredNASDAQ100Observation", Optional["FredNASDAQ100Observation"]]:
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
        raise FredNASDAQ100AdapterError(
            f"No FRED {series_id} observation at or before "
            f"{on_date.isoformat()}"
        )

    latest = observations[latest_idx]
    previous = observations[latest_idx - 1] if latest_idx > 0 else None
    return latest, previous


@dataclass(frozen=True)
class FredNASDAQ100Observation:
    """A single FRED daily NASDAQ100 observation."""

    date: date
    value: float


@dataclass(frozen=True)
class FredNASDAQ100Snapshot:
    """A snapshot of the latest NASDAQ100 value plus its daily change."""

    date: date
    nasdaq100: float
    nasdaq100_change_pct: float


class FredNASDAQ100OverlayAdapter:
    """FRED public NASDAQ-100 adapter that overlays only
    ``nasdaq100`` and ``nasdaq100_change_pct`` on the ``us_equities``
    of a :class:`MarketContext`.

    Behavior:

    1. Load a baseline :class:`MarketContext` from ``base_adapter``.
    2. Fetch NASDAQ100 from FRED (public, no-auth CSV).
    3. Choose the latest available observation at or before
       ``session_date``.
    4. Choose the previous available observation strictly before the
       selected date.
    5. Compute:

       * ``nasdaq100 = current_nasdaq100``
       * ``nasdaq100_change_pct =
         ((current_nasdaq100 / previous_nasdaq100) - 1.0) * 100.0``

    6. Replace only the two ``us_equities`` fields via
       :func:`dataclasses.replace`.
    7. Re-validate the final context through
       :func:`validate_market_context`.
    """

    def __init__(
        self,
        base_adapter: MarketContextAdapter,
        http_get: Optional[HttpGet] = None,
        source_config: Optional[FredNASDAQ100SourceConfig] = None,
    ) -> None:
        self._base_adapter = base_adapter
        self._http_get: HttpGet = http_get or self._default_http_get
        self._source_config = source_config or FredNASDAQ100SourceConfig()

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
        """Load a :class:`MarketContext` with FRED NASDAQ100 overlaid.

        Steps:

        1. Load a baseline :class:`MarketContext` from the base adapter.
        2. Fetch NASDAQ100 from FRED.
        3. Choose the latest observation at or before ``session_date``.
        4. Choose the previous observation strictly before the latest.
        5. Compute ``nasdaq100`` and ``nasdaq100_change_pct``.
        6. Replace only the two ``us_equities`` fields.
        7. Re-validate the result through
           :func:`validate_market_context`.

        Returns:
            A new frozen, validated :class:`MarketContext` whose
            ``us_equities.nasdaq100`` and
            ``us_equities.nasdaq100_change_pct`` are sourced from
            FRED and whose other fields come from the base adapter.

        Raises:
            FredNASDAQ100AdapterError: If the FRED data is missing,
                malformed, if no previous NASDAQ100 observation is
                available, or if the previous NASDAQ100 value is
                non-positive.
        """
        # 1. Load baseline
        baseline = self._base_adapter.load(session_date)

        if not isinstance(baseline, MarketContext):
            raise FredNASDAQ100AdapterError(
                "base adapter did not return a MarketContext: "
                f"got {type(baseline).__name__}"
            )

        # Parse session_date to a date object
        target_date = datetime.strptime(session_date, "%Y-%m-%d").date()

        # 2. Fetch NASDAQ100
        nasdaq100_text = self._http_get(self._source_config.nasdaq100_url)

        # 3 + 4. Choose latest and previous observations
        nasdaq100_obs, nasdaq100_prev = _parse_fred_csv_with_previous(
            nasdaq100_text, "NASDAQ100", target_date
        )

        # 5. Compute nasdaq100 and nasdaq100_change_pct
        nasdaq100 = nasdaq100_obs.value
        if nasdaq100_prev is None:
            raise FredNASDAQ100AdapterError(
                "No previous NASDAQ100 observation available "
                f"before {nasdaq100_obs.date.isoformat()} for "
                "nasdaq100_change_pct"
            )
        if nasdaq100_prev.value <= 0.0:
            raise FredNASDAQ100AdapterError(
                f"Previous NASDAQ100 value is non-positive: "
                f"{nasdaq100_prev.value} on "
                f"{nasdaq100_prev.date.isoformat()}"
            )
        nasdaq100_change_pct = (
            (nasdaq100 / nasdaq100_prev.value) - 1.0
        ) * 100.0

        # 6. Overlay only us_equities.nasdaq100 and
        #    us_equities.nasdaq100_change_pct
        new_us_equities = replace(
            baseline.us_equities,
            nasdaq100=nasdaq100,
            nasdaq100_change_pct=nasdaq100_change_pct,
        )
        new_ctx = replace(baseline, us_equities=new_us_equities)

        # 7. Re-validate
        return validate_market_context(asdict(new_ctx))
