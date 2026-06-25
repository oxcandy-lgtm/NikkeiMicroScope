#!/usr/bin/env python3
"""Fred treasury dry-run script.

Exercises the FRED public treasury adapter end-to-end with mocked
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
from nms.data.fred_treasury import FredTreasuryOverlayAdapter
from nms.data.validate import validate_market_context


SAMPLE_DGS2_CSV = """DATE,DGS2
2026-06-23,4.10
2026-06-22,4.08
2026-06-19,4.05
"""

SAMPLE_DGS10_CSV = """DATE,DGS10
2026-06-23,4.00
2026-06-22,3.98
2026-06-19,3.95
"""


def main() -> int:
    base_adapter = FixtureMarketContextAdapter(
        base_path=REPO_ROOT / "fixtures" / "market_context"
    )

    def fake_http_get(url: str) -> str:
        if "DGS2" in url:
            return SAMPLE_DGS2_CSV
        if "DGS10" in url:
            return SAMPLE_DGS10_CSV
        return ""

    adapter = FredTreasuryOverlayAdapter(
        base_adapter=base_adapter,
        http_get=fake_http_get,
    )

    ctx = adapter.load("2026-06-24")
    # Re-validate to confirm the returned context passes validation.
    ctx2 = validate_market_context(asdict(ctx))
    print(f"[dry-run] session_date      = {ctx2.session_date}")
    print(f"[dry-run] timezone          = {ctx2.timezone}")
    print(f"[dry-run] us_yields.us2y    = {ctx2.us_yields.us2y}")
    print(f"[dry-run] us_yields.us10y   = {ctx2.us_yields.us10y}")
    print(
        f"[dry-run] us_yields.us10y_minus_us2y = "
        f"{ctx2.us_yields.us10y_minus_us2y}"
    )
    print(
        f"[dry-run] us_yields.us10y_change_bp = "
        f"{ctx2.us_yields.us10y_change_bp}"
    )
    # All other fields should come from the base fixture.
    print(
        f"[dry-run] us_equities.sp500 = {ctx2.us_equities.sp500} (from base)"
    )
    print(
        f"[dry-run] nikkei_night.percent_change = "
        f"{ctx2.nikkei_night_session.percent_change} (from base)"
    )

    # Negative test: date mismatch should raise.
    MISMATCH_DGS10 = "DATE,DGS10\n2026-06-22,3.98\n"  # different from DGS2
    mismatch_adapter = FredTreasuryOverlayAdapter(
        base_adapter=base_adapter,
        http_get=lambda url: (
            SAMPLE_DGS2_CSV if "DGS2" in url else MISMATCH_DGS10
        ),
    )
    try:
        mismatch_adapter.load("2026-06-24")
        print("[dry-run] ERROR: expected date-mismatch error")
        return 1
    except Exception as e:
        print(f"[dry-run] correctly raised on date mismatch: {type(e).__name__}")

    # Negative test: missing previous DGS10 should raise.
    SINGLE_DGS10 = "DATE,DGS10\n2026-06-23,4.00\n"  # no previous obs
    single_dgs10_adapter = FredTreasuryOverlayAdapter(
        base_adapter=base_adapter,
        http_get=lambda url: (
            SAMPLE_DGS2_CSV if "DGS2" in url else SINGLE_DGS10
        ),
    )
    try:
        single_dgs10_adapter.load("2026-06-24")
        print("[dry-run] ERROR: expected missing-previous-DGS10 error")
        return 1
    except Exception as e:
        print(
            f"[dry-run] correctly raised on missing previous DGS10: "
            f"{type(e).__name__}"
        )

    print("[dry-run] ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
