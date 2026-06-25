#!/usr/bin/env python3
"""FRED SP500 dry-run script.

Exercises the FRED public SP500 adapter end-to-end with mocked
``http_get``. No real network access. No environment variable reads.
No subprocess calls.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.fred_sp500 import (
    FredSP500AdapterError,
    FredSP500OverlayAdapter,
    FredSP500SourceConfig,
)
from nms.data.models import (
    EconomicEventRisk,
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
from nms.data.validate import validate_market_context


SAMPLE_SP500_CSV = """DATE,SP500
2026-06-23,5760.23
2026-06-22,5750.10
2026-06-19,5740.55
"""


def _make_stub_base(session_date: str) -> MarketContext:
    return MarketContext(
        session_date=session_date,
        timezone="Asia/Tokyo",
        us_equities=UsEquities(
            sp500=0.0,
            dow=0.0,
            nasdaq100=0.0,
            russell2000=0.0,
            sp500_change_pct=0.0,
            nasdaq100_change_pct=0.0,
        ),
        semiconductor=Semiconductor(sox=0.0, sox_change_pct=0.0),
        fx=Fx(usdjpy=0.0, usdjpy_change_pct=0.0),
        us_yields=UsYields(
            us2y=0.0,
            us10y=0.0,
            us10y_minus_us2y=0.0,
            us10y_change_bp=0.0,
        ),
        nikkei_night_session=NikkeiNightSession(
            close=0.0, high=0.0, low=0.0, range=0.0, percent_change=0.0
        ),
        previous_day=PreviousDay(
            high=0.0, low=0.0, close=0.0, range=0.0
        ),
        economic_event_risk=EconomicEventRisk(events=[]),
        intraday_range=IntradayRange(
            first_15m_high=0.0,
            first_15m_low=0.0,
            first_15m_range=0.0,
            atr_like_baseline=1.0,
        ),
        volatility_context=VolatilityContext(
            realized_vol=0.0,
            atr_like=1.0,
            compression_flag=False,
        ),
    )


class _StubBase:
    """Minimal base adapter for the dry-run."""

    def load(self, session_date: str) -> MarketContext:
        return _make_stub_base(session_date)


def main() -> int:
    base = _StubBase()

    def fake_http_get(url: str) -> str:
        if "SP500" in url:
            return SAMPLE_SP500_CSV
        return ""

    adapter = FredSP500OverlayAdapter(
        base_adapter=base,
        http_get=fake_http_get,
    )

    ctx = adapter.load("2026-06-24")
    # Re-validate to confirm the returned context passes validation.
    ctx2 = validate_market_context(asdict(ctx))
    print(f"[dry-run] session_date          = {ctx2.session_date}")
    print(f"[dry-run] timezone              = {ctx2.timezone}")
    print(f"[dry-run] us_equities.sp500    = {ctx2.us_equities.sp500}")
    print(
        f"[dry-run] us_equities.sp500_change_pct = "
        f"{ctx2.us_equities.sp500_change_pct}"
    )
    print(
        f"[dry-run] us_equities.dow (from base) = "
        f"{ctx2.us_equities.dow}"
    )
    print(
        f"[dry-run] us_equities.nasdaq100 (from base) = "
        f"{ctx2.us_equities.nasdaq100}"
    )
    print(
        f"[dry-run] us_yields.us10y (from base) = "
        f"{ctx2.us_yields.us10y}"
    )

    # Negative test: missing previous SP500 should raise.
    SINGLE_SP500 = "DATE,SP500\n2026-06-23,5760.23\n"  # no previous
    single_adapter = FredSP500OverlayAdapter(
        base_adapter=base,
        http_get=lambda url: SINGLE_SP500,
    )
    try:
        single_adapter.load("2026-06-24")
        print("[dry-run] ERROR: expected missing-previous-SP500 error")
        return 1
    except FredSP500AdapterError as e:
        print(
            f"[dry-run] correctly raised on missing previous SP500: "
            f"{type(e).__name__}"
        )

    # Negative test: non-positive previous SP500 should raise.
    NON_POSITIVE_SP500 = """DATE,SP500
2026-06-22,0.0
2026-06-23,5760.23
"""
    non_positive_adapter = FredSP500OverlayAdapter(
        base_adapter=base,
        http_get=lambda url: NON_POSITIVE_SP500,
    )
    try:
        non_positive_adapter.load("2026-06-24")
        print("[dry-run] ERROR: expected non-positive-previous-SP500 error")
        return 1
    except FredSP500AdapterError as e:
        print(
            f"[dry-run] correctly raised on non-positive previous SP500: "
            f"{type(e).__name__}"
        )

    print("[dry-run] ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
