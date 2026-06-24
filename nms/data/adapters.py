"""Market context adapter interface and the fixture-backed implementation.

The interface is a :class:`Protocol` so any future adapter (network,
database, mock) can satisfy it without subclassing. The MVP ships
only the :class:`FixtureMarketContextAdapter`, which reads local JSON
fixtures from a configurable directory.

Hard constraints (enforced socially and via tests):

* No network access. See ``tests/test_fixture_loader.py``.
* No environment-variable credential reading. See the same test file.
* No subprocess / shell-out. The adapter is pure local file I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nms.data.fixture_loader import load_fixture_file
from nms.data.models import MarketContext


class MarketContextAdapter(Protocol):
    """Read-only adapter that produces a :class:`MarketContext` for a date."""

    def load(self, session_date: str) -> MarketContext:
        """Load the market context for the given ``session_date``.

        ``session_date`` is an ISO-8601 calendar date string (e.g.
        ``"2026-06-24"``).
        """
        ...


#: Default filename template for fixture-backed adapters.
#: ``{session_date}`` is substituted at call time.
DEFAULT_FIXTURE_TEMPLATE = "sample-session-{session_date}.json"


class FixtureMarketContextAdapter:
    """An adapter that reads local JSON fixtures.

    The adapter looks for files named
    ``sample-session-{session_date}.json`` under ``base_path``. This
    explicit ``sample-session-`` prefix is intentional: the adapter
    is for fixture / sample data only. Real data must come from a
    different adapter that is reviewed per
    ``docs/data-adapter-contract.md``.
    """

    def __init__(
        self,
        base_path: str | Path = "fixtures/market_context",
        filename_template: str = DEFAULT_FIXTURE_TEMPLATE,
    ) -> None:
        self._base_path = Path(base_path)
        self._filename_template = filename_template

    @property
    def base_path(self) -> Path:
        return self._base_path

    def load(self, session_date: str) -> MarketContext:
        filename = self._filename_template.format(session_date=session_date)
        path = self._base_path / filename
        return load_fixture_file(path)
