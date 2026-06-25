"""Public, no-auth FRED data sources for NikkeiMicroScope.

This module provides public, no-auth FRED data sources for NikkeiMicroScope.
It currently ships:

* :class:`FredObservation` — a single FRED daily treasury observation.
* :class:`FredTreasurySourceConfig` — FRED source URLs and timeout.
* :class:`FredTreasuryAdapterError` — narrow exception for FRED adapter errors.
* :func:`_parse_fred_csv` — parse FRED CSV and return the latest observation
  at or before a date.
* :func:`_parse_fred_csv_with_previous` — also return the previous observation
  immediately before the latest.

These are public/no-auth sources: they require no API key, no auth header,
no cookie.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class FredObservation:
    """A single FRED daily treasury observation.

    Attributes:
        date: the observation date.
        value: the observed value in the documented FRED unit
            (e.g. percent for DGS2 / DGS10).
    """

    date: date
    value: float


@dataclass(frozen=True)
class FredTreasurySourceConfig:
    """Configuration for the FRED treasury data source.

    Attributes:
        dgs2_url: URL of the FRED DGS2 CSV.
        dgs10_url: URL of the FRED DGS10 CSV.
        timeout_seconds: HTTP timeout in seconds for the default
            :func:`FredTreasuryOverlayAdapter._default_http_get`.
    """

    dgs2_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2"
    dgs10_url: str = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    timeout_seconds: float = 10.0


class FredTreasuryAdapterError(ValueError):
    """Raised when FRED treasury data is missing or malformed."""


def _parse_fred_csv_observations(
    text: str, series_id: str
) -> List[FredObservation]:
    """Parse FRED CSV text and return all valid observations sorted by date.

    FRED CSV format::

        DATE,SERIES_ID
        2024-01-02,4.32
        2024-01-03,4.28
        2024-01-04,.

    Missing values are represented as ``.``.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or series_id not in reader.fieldnames:
        raise FredTreasuryAdapterError(
            f"FRED CSV missing expected column {series_id!r}"
        )

    observations: List[FredObservation] = []
    for row in reader:
        date_str = (row.get("DATE") or "").strip()
        value_str = (row.get(series_id) or "").strip()
        if not date_str or not value_str or value_str == ".":
            continue
        try:
            obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            obs_value = float(value_str)
        except ValueError as e:
            raise FredTreasuryAdapterError(
                f"Malformed FRED row: {row!r}: {e}"
            ) from e
        observations.append(FredObservation(date=obs_date, value=obs_value))

    observations.sort(key=lambda o: o.date)
    return observations


def _parse_fred_csv(
    text: str, series_id: str, on_date: date
) -> FredObservation:
    """Parse FRED CSV and return the latest observation at or before ``on_date``.

    Raises:
        FredTreasuryAdapterError: If no observation is at or before
            ``on_date``, or if the CSV is malformed.
    """
    observations = _parse_fred_csv_observations(text, series_id)

    latest: Optional[FredObservation] = None
    for obs in observations:
        if obs.date <= on_date:
            latest = obs
        else:
            break

    if latest is None:
        raise FredTreasuryAdapterError(
            f"No FRED {series_id} observation at or before {on_date.isoformat()}"
        )
    return latest


def _parse_fred_csv_with_previous(
    text: str, series_id: str, on_date: date
) -> Tuple[FredObservation, Optional[FredObservation]]:
    """Parse FRED CSV and return the latest observation at or before ``on_date``,
    plus the previous observation (the one immediately before the latest).
    """
    observations = _parse_fred_csv_observations(text, series_id)

    latest_idx = -1
    for i, obs in enumerate(observations):
        if obs.date <= on_date:
            latest_idx = i
        else:
            break

    if latest_idx == -1:
        raise FredTreasuryAdapterError(
            f"No FRED {series_id} observation at or before {on_date.isoformat()}"
        )

    latest = observations[latest_idx]
    previous = observations[latest_idx - 1] if latest_idx > 0 else None
    return latest, previous
