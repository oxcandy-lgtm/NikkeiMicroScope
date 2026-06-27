#!/usr/bin/env python3
"""Adapter composition dry-run script.

Exercises ``ComposedMarketContextAdapter`` end-to-end with mocked
``http_get`` for all four FRED overlay adapters. No real network
access. No environment variable reads. No subprocess calls. No
raw FRED data committed in this script — the CSVs below are small
synthetic examples with low-magnitude placeholder values.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.composition import (
    AdapterStage,
    ComposedMarketContextAdapter,
    compose_market_context_adapter,
)
from nms.data.fred_nasdaq100 import (
    FredNASDAQ100OverlayAdapter,
    FredNASDAQ100SourceConfig,
)
from nms.data.fred_sp500 import (
    FredSP500OverlayAdapter,
    FredSP500SourceConfig,
)
from nms.data.fred_treasury import (
    FredTreasuryOverlayAdapter,
    FredTreasurySourceConfig,
)
from nms.data.fred_usdjpy import (
    FredUSDJPYOverlayAdapter,
    FredUSDJPYSourceConfig,
)
from nms.data.validate import validate_market_context


# Synthetic CSVs (placeholder values, not from a real FRED download).
SYN_TREASURY_CSV = """DATE,DGS2,DGS10
2026-06-23,4.20,4.30
2026-06-22,4.18,4.27
2026-06-19,4.16,4.25
"""

SYN_SP500_CSV = """DATE,SP500
2026-06-23,5480.00
2026-06-22,5460.00
2026-06-19,5440.00
"""

SYN_USDJPY_CSV = """DATE,DEXJPUS
2026-06-23,159.70
2026-06-22,159.30
2026-06-19,158.90
"""

SYN_NASDAQ100_CSV = """DATE,NASDAQ100
2026-06-23,19800.00
2026-06-22,19750.00
2026-06-19,19700.00
"""


def _http_get_factory(csv_by_url_id: dict):
    """Return a fake ``http_get`` that dispatches on the FRED
    URL's ``?id=`` parameter to a synthetic CSV. The dispatch
    uses the FRED series id, not a substring of the URL, so
    that ``?id=DGS2`` and ``?id=DGS10`` both map to the
    Treasury CSV.
    """
    def _fake_http_get(url: str) -> str:
        if "id=" in url:
            series_id = url.split("id=", 1)[1].split("&", 1)[0]
            if series_id in csv_by_url_id:
                return csv_by_url_id[series_id]
        return ""
    return _fake_http_get


def main() -> int:
    base = FixtureMarketContextAdapter(
        base_path=REPO_ROOT / "fixtures" / "market_context"
    )

    csv_by_url_id = {
        "DGS2": SYN_TREASURY_CSV,
        "DGS10": SYN_TREASURY_CSV,
        "SP500": SYN_SP500_CSV,
        "DEXJPUS": SYN_USDJPY_CSV,
        "NASDAQ100": SYN_NASDAQ100_CSV,
    }
    http_get = _http_get_factory(csv_by_url_id)

    def make_treasury(b):
        return FredTreasuryOverlayAdapter(
            base_adapter=b,
            http_get=http_get,
            source_config=FredTreasurySourceConfig(),
        )

    def make_sp500(b):
        return FredSP500OverlayAdapter(
            base_adapter=b,
            http_get=http_get,
            source_config=FredSP500SourceConfig(),
        )

    def make_usdjpy(b):
        return FredUSDJPYOverlayAdapter(
            base_adapter=b,
            http_get=http_get,
            source_config=FredUSDJPYSourceConfig(),
        )

    def make_nasdaq100(b):
        return FredNASDAQ100OverlayAdapter(
            base_adapter=b,
            http_get=http_get,
            source_config=FredNASDAQ100SourceConfig(),
        )

    adapter = compose_market_context_adapter(
        base_adapter=base,
        stages=[
            AdapterStage(name="treasury", factory=make_treasury),
            AdapterStage(name="sp500", factory=make_sp500),
            AdapterStage(name="usdjpy", factory=make_usdjpy),
            AdapterStage(name="nasdaq100", factory=make_nasdaq100),
        ],
    )

    ctx = adapter.load("2026-06-24")
    ctx2 = validate_market_context(asdict(ctx))
    print(
        f"[dry-run] session_date                 = {ctx2.session_date}"
    )
    print(f"[dry-run] timezone                     = {ctx2.timezone}")

    # Treasury
    print(
        f"[dry-run] us_yields.us2y               = "
        f"{ctx2.us_yields.us2y}"
    )
    print(
        f"[dry-run] us_yields.us10y              = "
        f"{ctx2.us_yields.us10y}"
    )
    print(
        f"[dry-run] us_yields.us10y_minus_us2y   = "
        f"{ctx2.us_yields.us10y_minus_us2y}"
    )
    print(
        f"[dry-run] us_yields.us10y_change_bp    = "
        f"{ctx2.us_yields.us10y_change_bp}"
    )

    # SP500
    print(
        f"[dry-run] us_equities.sp500            = "
        f"{ctx2.us_equities.sp500}"
    )
    print(
        f"[dry-run] us_equities.sp500_change_pct = "
        f"{ctx2.us_equities.sp500_change_pct}"
    )

    # USDJPY
    print(
        f"[dry-run] fx.usdjpy                    = "
        f"{ctx2.fx.usdjpy}"
    )
    print(
        f"[dry-run] fx.usdjpy_change_pct         = "
        f"{ctx2.fx.usdjpy_change_pct}"
    )

    # NASDAQ100
    print(
        f"[dry-run] us_equities.nasdaq100        = "
        f"{ctx2.us_equities.nasdaq100}"
    )
    print(
        f"[dry-run] us_equities.nasdaq100_change = "
        f"{ctx2.us_equities.nasdaq100_change_pct}"
    )

    # Verify all four overlays were applied.
    expected_nonzero = {
        "us_yields.us2y": ctx2.us_yields.us2y,
        "us_yields.us10y": ctx2.us_yields.us10y,
        "us_yields.us10y_minus_us2y": ctx2.us_yields.us10y_minus_us2y,
        "us_yields.us10y_change_bp": ctx2.us_yields.us10y_change_bp,
        "us_equities.sp500": ctx2.us_equities.sp500,
        "us_equities.sp500_change_pct": ctx2.us_equities.sp500_change_pct,
        "fx.usdjpy": ctx2.fx.usdjpy,
        "fx.usdjpy_change_pct": ctx2.fx.usdjpy_change_pct,
        "us_equities.nasdaq100": ctx2.us_equities.nasdaq100,
        "us_equities.nasdaq100_change_pct": (
            ctx2.us_equities.nasdaq100_change_pct
        ),
    }
    for k, v in expected_nonzero.items():
        if v == 0.0:
            print(f"[dry-run] ERROR: {k} = 0.0 (overlay not applied?)")
            return 1

    print("[dry-run] all four overlays applied ok")
    print("[dry-run] ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
