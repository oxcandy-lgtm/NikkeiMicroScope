#!/usr/bin/env python3
"""Composed MarketContext JSON export dry-run script.

Exercises ``write_market_context_json`` end-to-end with mocked
``http_get`` for all four FRED overlay adapters. No real network
access. No environment variable reads. No subprocess calls. No
raw FRED data committed in this script — the CSVs below are small
synthetic examples with low-magnitude placeholder values.

The dry-run:

1. Builds a synthetic composed adapter chain (same pattern as
   ``scripts/compose_market_context.py``).
2. Loads the final composed ``MarketContext`` for
   ``2026-06-24``.
3. Writes the final context to
   ``exports/dry-run/composed-market-context-2026-06-24.json``.
4. Refuses to overwrite an existing file unless
   ``--overwrite`` is passed.
5. Prints the output path and a short summary.
6. Exits nonzero on failure.

The exported JSON includes a top-level ``"synthetic"`` marker
and a ``"_dry_run_meta"`` block so it is never confused with
live data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.composition import (
    AdapterStage,
    compose_market_context_adapter,
)
from nms.data.export import (
    market_context_to_json_text,
    market_context_to_ordered_dict,
    write_market_context_json,
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


# Synthetic CSVs (placeholder values, not from a real FRED
# download). The Treasury CSV has both DGS2 and DGS10 columns.
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
    URL's ``?id=`` parameter to a synthetic CSV.
    """
    def _fake_http_get(url: str) -> str:
        if "id=" in url:
            series_id = url.split("id=", 1)[1].split("&", 1)[0]
            if series_id in csv_by_url_id:
                return csv_by_url_id[series_id]
        return ""
    return _fake_http_get


def _build_composed_context(session_date: str) -> object:
    """Build the synthetic composed adapter chain and return
    the final ``MarketContext`` for ``session_date``.
    """
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
    return adapter.load(session_date)


def _default_output_path(session_date: str) -> Path:
    return (
        REPO_ROOT
        / "exports"
        / "dry-run"
        / f"composed-market-context-{session_date}.json"
    )


def _add_synthetic_marker(payload: dict, session_date: str) -> dict:
    """Add a synthetic / dry-run marker block to the payload.

    The marker is added in-memory before serializing; it does
    not mutate the input MarketContext.
    """
    out = dict(payload)
    out["synthetic"] = True
    out["_dry_run_meta"] = {
        "source": "nms.data.export dry-run",
        "session_date": session_date,
        "data_origin": "synthetic CSV (placeholder values)",
        "live_fred_used": False,
    }
    return out


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Composed MarketContext JSON export dry-run. "
            "Writes a synthetic export to exports/dry-run/."
        )
    )
    parser.add_argument(
        "--session-date",
        default="2026-06-24",
        help="Session date to compose (default: 2026-06-24).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output JSON path. Default: "
            "exports/dry-run/composed-market-context-<session_date>.json"
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting an existing output file.",
    )
    args = parser.parse_args(argv)

    session_date = args.session_date
    output_path = (
        Path(args.output) if args.output else _default_output_path(session_date)
    )

    ctx = _build_composed_context(session_date)
    # Re-validate to confirm the composed context is valid.
    validate_market_context(market_context_to_ordered_dict(ctx))

    # Build the export payload, with a synthetic marker.
    payload = market_context_to_ordered_dict(ctx)
    payload = _add_synthetic_marker(payload, session_date)

    # Serialize the payload (with marker) to JSON text and
    # write it directly. We use Path.write_text rather than
    # write_market_context_json because the latter calls
    # market_context_to_json_text on the input context, which
    # does not include the synthetic marker.
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if not text.endswith("\n"):
        text += "\n"

    if output_path.exists() and not args.overwrite:
        print(
            f"[dry-run] ERROR: refusing to overwrite existing file: "
            f"{output_path}. Pass --overwrite to override."
        )
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)

    # Print a short summary.
    print(f"[dry-run] session_date     = {ctx.session_date}")
    print(f"[dry-run] timezone         = {ctx.timezone}")
    print(f"[dry-run] output_path      = {output_path}")
    print(
        f"[dry-run] us_yields.us10y  = "
        f"{ctx.us_yields.us10y}"
    )
    print(
        f"[dry-run] us_equities.sp500 = "
        f"{ctx.us_equities.sp500}"
    )
    print(
        f"[dry-run] fx.usdjpy        = "
        f"{ctx.fx.usdjpy}"
    )
    print(
        f"[dry-run] us_equities.nasdaq100 = "
        f"{ctx.us_equities.nasdaq100}"
    )
    print(
        f"[dry-run] semiconductor.sox = "
        f"{ctx.semiconductor.sox} (unchanged: not sourced by SOX adapter)"
    )

    # Sanity check: parse the written file and verify
    # expected keys and nonzero overlay fields.
    parsed = json.loads(output_path.read_text(encoding="utf-8"))
    for k in (
        "session_date",
        "us_yields",
        "us_equities",
        "fx",
        "semiconductor",
    ):
        if k not in parsed:
            print(f"[dry-run] ERROR: missing top-level key {k!r}")
            return 1
    for path, label in (
        ("us_yields.us2y", "us2y"),
        ("us_yields.us10y", "us10y"),
        ("us_yields.us10y_minus_us2y", "us10y_minus_us2y"),
        ("us_yields.us10y_change_bp", "us10y_change_bp"),
        ("us_equities.sp500", "sp500"),
        ("us_equities.sp500_change_pct", "sp500_change_pct"),
        ("fx.usdjpy", "usdjpy"),
        ("fx.usdjpy_change_pct", "usdjpy_change_pct"),
        ("us_equities.nasdaq100", "nasdaq100"),
        ("us_equities.nasdaq100_change_pct", "nasdaq100_change_pct"),
    ):
        section, key = path.split(".", 1)
        v = parsed[section][key]
        if v == 0 or v == 0.0:
            print(f"[dry-run] ERROR: {path} = 0 (overlay not applied?)")
            return 1
        _ = label  # quiet linter

    print("[dry-run] ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
