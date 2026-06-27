#!/usr/bin/env python3
"""FRED NASDAQ100 dry-run script.

Exercises the FRED public NASDAQ-100 adapter end-to-end with mocked
``http_get``. No real network access. No environment variable reads.
No subprocess calls. No raw FRED NASDAQ100 data is committed in
this script — the CSVs below are small synthetic examples.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.fred_nasdaq100 import (
    FredNASDAQ100AdapterError,
    FredNASDAQ100OverlayAdapter,
    FredNASDAQ100SourceConfig,
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


# Synthetic CSV (placeholder values, not from a real FRED download).
SAMPLE_NASDAQ100_CSV = """DATE,NASDAQ100
2026-06-23,20612.50
2026-06-22,20580.10
2026-06-19,20500.00
"""


def main() -> int:
    base_adapter = FixtureMarketContextAdapter(
        base_path=REPO_ROOT / "fixtures" / "market_context"
    )

    def fake_http_get(url: str) -> str:
        if "NASDAQ100" in url:
            return SAMPLE_NASDAQ100_CSV
        return ""

    adapter = FredNASDAQ100OverlayAdapter(
        base_adapter=base_adapter,
        http_get=fake_http_get,
    )

    ctx = adapter.load("2026-06-24")
    ctx2 = validate_market_context(asdict(ctx))
    print(
        f"[dry-run] session_date                 = {ctx2.session_date}"
    )
    print(f"[dry-run] timezone                     = {ctx2.timezone}")
    print(
        f"[dry-run] us_equities.nasdaq100        = "
        f"{ctx2.us_equities.nasdaq100}"
    )
    print(
        f"[dry-run] us_equities.nasdaq100_change = "
        f"{ctx2.us_equities.nasdaq100_change_pct}"
    )
    print(
        f"[dry-run] us_equities.sp500 (base)     = "
        f"{ctx2.us_equities.sp500}"
    )
    print(
        f"[dry-run] us_yields.us10y (base)       = "
        f"{ctx2.us_yields.us10y}"
    )

    # Negative test: missing previous NASDAQ100 should raise.
    SINGLE_NASDAQ100 = "DATE,NASDAQ100\n2026-06-23,20612.50\n"
    single_adapter = FredNASDAQ100OverlayAdapter(
        base_adapter=base_adapter,
        http_get=lambda url: SINGLE_NASDAQ100,
    )
    try:
        single_adapter.load("2026-06-24")
        print("[dry-run] ERROR: expected missing-previous-NASDAQ100 error")
        return 1
    except FredNASDAQ100AdapterError as e:
        print(
            f"[dry-run] correctly raised on missing previous NASDAQ100: "
            f"{type(e).__name__}"
        )

    # Negative test: non-positive previous NASDAQ100 should raise.
    NON_POSITIVE_NASDAQ100 = """DATE,NASDAQ100
2026-06-22,0.0
2026-06-23,20612.50
"""
    non_positive_adapter = FredNASDAQ100OverlayAdapter(
        base_adapter=base_adapter,
        http_get=lambda url: NON_POSITIVE_NASDAQ100,
    )
    try:
        non_positive_adapter.load("2026-06-24")
        print(
            "[dry-run] ERROR: expected non-positive-previous-NASDAQ100 "
            "error"
        )
        return 1
    except FredNASDAQ100AdapterError as e:
        print(
            f"[dry-run] correctly raised on non-positive previous "
            f"NASDAQ100: {type(e).__name__}"
        )

    print("[dry-run] ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
