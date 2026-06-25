#!/usr/bin/env python3
"""FRED USDJPY dry-run script.

Exercises the FRED public USDJPY adapter end-to-end with mocked
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
from nms.data.fred_usdjpy import (
    FredUSDJPYAdapterError,
    FredUSDJPYOverlayAdapter,
    FredUSDJPYSourceConfig,
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


SAMPLE_DEXJPUS_CSV = """DATE,DEXJPUS
2026-06-23,144.20
2026-06-22,143.85
2026-06-19,143.50
"""


class _StubBase:
    """Minimal base adapter for the dry-run."""

    def load(self, session_date: str) -> MarketContext:
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


def main() -> int:
    base = _StubBase()

    def fake_http_get(url: str) -> str:
        if "DEXJPUS" in url:
            return SAMPLE_DEXJPUS_CSV
        return ""

    adapter = FredUSDJPYOverlayAdapter(
        base_adapter=base,
        http_get=fake_http_get,
    )

    ctx = adapter.load("2026-06-24")
    # Re-validate to confirm the returned context passes validation.
    ctx2 = validate_market_context(asdict(ctx))
    print(f"[dry-run] session_date            = {ctx2.session_date}")
    print(f"[dry-run] timezone                = {ctx2.timezone}")
    print(f"[dry-run] fx.usdjpy               = {ctx2.fx.usdjpy}")
    print(
        f"[dry-run] fx.usdjpy_change_pct    = "
        f"{ctx2.fx.usdjpy_change_pct}"
    )
    print(
        f"[dry-run] us_equities.sp500 (from base) = "
        f"{ctx2.us_equities.sp500}"
    )
    print(
        f"[dry-run] us_yields.us10y (from base)   = "
        f"{ctx2.us_yields.us10y}"
    )

    # Negative test: missing previous DEXJPUS should raise.
    SINGLE_DEXJPUS = "DATE,DEXJPUS\n2026-06-23,144.20\n"  # no previous
    single_adapter = FredUSDJPYOverlayAdapter(
        base_adapter=base,
        http_get=lambda url: SINGLE_DEXJPUS,
    )
    try:
        single_adapter.load("2026-06-24")
        print("[dry-run] ERROR: expected missing-previous-DEXJPUS error")
        return 1
    except FredUSDJPYAdapterError as e:
        print(
            f"[dry-run] correctly raised on missing previous DEXJPUS: "
            f"{type(e).__name__}"
        )

    # Negative test: non-positive previous DEXJPUS should raise.
    NON_POSITIVE_DEXJPUS = """DATE,DEXJPUS
2026-06-22,0.0
2026-06-23,144.20
"""
    non_positive_adapter = FredUSDJPYOverlayAdapter(
        base_adapter=base,
        http_get=lambda url: NON_POSITIVE_DEXJPUS,
    )
    try:
        non_positive_adapter.load("2026-06-24")
        print("[dry-run] ERROR: expected non-positive-previous-DEXJPUS error")
        return 1
    except FredUSDJPYAdapterError as e:
        print(
            f"[dry-run] correctly raised on non-positive previous DEXJPUS: "
            f"{type(e).__name__}"
        )

    print("[dry-run] ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
