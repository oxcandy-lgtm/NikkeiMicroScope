"""Tests for the FRED public treasury adapter.

These tests enforce the public/no-auth FRED adapter contract:

* The adapter uses only publicly available FRED CSV data.
* No secrets, no API key, no PAT, no auth header or cookie.
* No broker SDK, no order placement, no live trading.
* No subprocess, no environment variable credential reading.
* No new runtime dependencies; stdlib only.
* The injected ``http_get`` is the only network entry point.
* The base adapter is read first, then treasury fields are overlaid.
* The adapter returns a validated :class:`MarketContext`.
* Only the four ``us_yields`` fields are overlaid.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import unittest
from datetime import date
from pathlib import Path
from typing import Any
from unittest import mock

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.fred_treasury import FredTreasuryOverlayAdapter
from nms.data.models import (
    MarketContext,
    UsYields,
)
from nms.data.validate import (
    ValidationError,
    validate_market_context,
)
from nms.data.public_sources import (
    FredObservation,
    FredTreasuryAdapterError,
    FredTreasurySourceConfig,
    _parse_fred_csv,
    _parse_fred_csv_with_previous,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FIXTURE = (
    REPO_ROOT / "fixtures" / "market_context" / "sample-session-2026-06-24.json"
)


# --- Sample CSVs --------------------------------------------------------

SAMPLE_DGS2_CSV = """DATE,DGS2
2024-01-02,4.32
2024-01-03,4.28
2024-01-04,4.30
"""

SAMPLE_DGS10_CSV = """DATE,DGS10
2024-01-02,4.05
2024-01-03,4.02
2024-01-04,4.07
"""


def _make_fake_http_get(
    dgs2_text: str = SAMPLE_DGS2_CSV,
    dgs10_text: str = SAMPLE_DGS10_CSV,
) -> "callable":
    """Return a fake ``http_get`` that returns the given CSVs by URL."""

    def fake_http_get(url: str) -> str:
        if "DGS2" in url:
            return dgs2_text
        if "DGS10" in url:
            return dgs10_text
        return ""

    return fake_http_get


# --- Parser tests --------------------------------------------------------


class ParseFredCsvTests(unittest.TestCase):
    def test_returns_latest_at_or_before_date(self) -> None:
        obs = _parse_fred_csv(SAMPLE_DGS2_CSV, "DGS2", date(2024, 1, 3))
        self.assertEqual(obs.date, date(2024, 1, 3))
        self.assertEqual(obs.value, 4.28)

    def test_skips_missing_values(self) -> None:
        csv = """DATE,DGS2
2024-01-02,4.32
2024-01-03,.
2024-01-04,4.30
"""
        obs = _parse_fred_csv(csv, "DGS2", date(2024, 1, 4))
        self.assertEqual(obs.date, date(2024, 1, 4))
        self.assertEqual(obs.value, 4.30)

    def test_raises_when_no_observation_at_or_before(self) -> None:
        with self.assertRaises(FredTreasuryAdapterError):
            _parse_fred_csv(SAMPLE_DGS2_CSV, "DGS2", date(2024, 1, 1))

    def test_raises_on_malformed_date(self) -> None:
        csv = "DATE,DGS2\nnot-a-date,4.32\n"
        with self.assertRaises(FredTreasuryAdapterError):
            _parse_fred_csv(csv, "DGS2", date(2024, 1, 4))

    def test_raises_on_malformed_numeric(self) -> None:
        csv = "DATE,DGS2\n2024-01-02,not-a-number\n"
        with self.assertRaises(FredTreasuryAdapterError):
            _parse_fred_csv(csv, "DGS2", date(2024, 1, 4))

    def test_raises_on_missing_column(self) -> None:
        csv = "DATE,OTHER\n2024-01-02,4.32\n"
        with self.assertRaises(FredTreasuryAdapterError):
            _parse_fred_csv(csv, "DGS2", date(2024, 1, 2))


class ParseFredCsvWithPreviousTests(unittest.TestCase):
    def test_returns_latest_and_previous(self) -> None:
        latest, previous = _parse_fred_csv_with_previous(
            SAMPLE_DGS2_CSV, "DGS2", date(2024, 1, 4)
        )
        self.assertEqual(latest.date, date(2024, 1, 4))
        self.assertEqual(latest.value, 4.30)
        self.assertIsNotNone(previous)
        self.assertEqual(previous.date, date(2024, 1, 3))
        self.assertEqual(previous.value, 4.28)

    def test_returns_none_previous_for_first_observation(self) -> None:
        csv = "DATE,DGS2\n2024-01-02,4.32\n"
        latest, previous = _parse_fred_csv_with_previous(
            csv, "DGS2", date(2024, 1, 2)
        )
        self.assertEqual(latest.date, date(2024, 1, 2))
        self.assertIsNone(previous)


# --- Adapter tests --------------------------------------------------------


def _baseline_adapter() -> FixtureMarketContextAdapter:
    return FixtureMarketContextAdapter(
        base_path=REPO_ROOT / "fixtures" / "market_context"
    )


class FredTreasuryOverlayAdapterTests(unittest.TestCase):
    def test_load_returns_validated_market_context(self) -> None:
        adapter = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        ctx = adapter.load("2026-06-24")
        self.assertIsInstance(ctx, MarketContext)

    def test_load_overlays_only_us_yields(self) -> None:
        # The sample fixture (us_yields 0.0 baseline) should be
        # overwritten by the FRED overlay.
        adapter = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        ctx = adapter.load("2026-06-24")
        # The selected date for the sample is 2026-06-24, which is
        # outside the sample CSV range. Use a date in range.
        # Instead, build a custom base with 2024-01-03.
        # We use the sample fixture but the sample is 2026-06-24 and
        # our fake CSVs only go up to 2024-01-04. So we expect a
        # FredTreasuryAdapterError. Use a fixture whose date is in
        # range instead.
        # For this test, we'll just verify the overlay by reading
        # the baseline first and checking the overlay changes those
        # fields.
        base = _baseline_adapter().load("2026-06-24")
        # Baseline us_yields are the sample's values.
        baseline_us_yields = base.us_yields
        # Pick a date in range for the CSV.
        dgs2_csv = "DATE,DGS2\n2026-06-23,4.10\n2026-06-22,4.08\n"
        dgs10_csv = "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
        adapter2 = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
        )
        ctx2 = adapter2.load("2026-06-24")
        # The overlay should have changed us_yields.
        self.assertNotEqual(
            (ctx2.us_yields.us2y, ctx2.us_yields.us10y),
            (baseline_us_yields.us2y, baseline_us_yields.us10y),
        )
        self.assertAlmostEqual(ctx2.us_yields.us2y, 4.10)
        self.assertAlmostEqual(ctx2.us_yields.us10y, 4.00)
        self.assertAlmostEqual(ctx2.us_yields.us10y_minus_us2y, -0.10)
        # 4.00 vs 3.98 = +0.02% = +2.0 bp
        self.assertAlmostEqual(ctx2.us_yields.us10y_change_bp, 2.0)

    def test_load_uses_injected_http_get(self) -> None:
        calls: list[str] = []

        def tracking_http_get(url: str) -> str:
            calls.append(url)
            if "DGS2" in url:
                return "DATE,DGS2\n2026-06-23,4.10\n"
            if "DGS10" in url:
                return "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
            return ""

        adapter = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=tracking_http_get,
        )
        adapter.load("2026-06-24")
        # The injected http_get was called twice (DGS2 and DGS10).
        self.assertEqual(len(calls), 2)
        for url in calls:
            self.assertIn("DGS", url)

    def test_load_raises_on_dgs2_dgs10_date_mismatch(self) -> None:
        dgs2_csv = "DATE,DGS2\n2024-01-03,4.28\n"
        dgs10_csv = "DATE,DGS10\n2024-01-02,4.05\n"  # different date
        adapter = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
        )
        with self.assertRaises(FredTreasuryAdapterError):
            adapter.load("2026-06-24")

    def test_load_raises_when_no_previous_dgs10(self) -> None:
        # Only one DGS10 observation exists, so there is no
        # "previous" observation for us10y_change_bp. The adapter
        # must raise FredTreasuryAdapterError rather than silently
        # treating the missing previous as a neutral contribution.
        single_dgs10_csv = "DATE,DGS10\n2024-01-03,4.02\n"
        single_dgs2_csv = "DATE,DGS2\n2024-01-02,4.28\n2024-01-03,4.30\n"
        adapter = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(single_dgs2_csv, single_dgs10_csv),
        )
        with self.assertRaises(FredTreasuryAdapterError) as cm:
            adapter.load("2026-06-24")
        self.assertIn("previous DGS10", str(cm.exception))

    def test_load_does_not_mutate_baseline_context(self) -> None:
        # The adapter should produce a new MarketContext, not mutate
        # the one from the base adapter.
        base = _baseline_adapter()
        original_ctx = base.load("2026-06-24")
        original_yields = original_ctx.us_yields
        # Use CSVs in range to trigger an actual overlay.
        dgs2_csv = "DATE,DGS2\n2026-06-23,4.10\n"
        dgs10_csv = "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
        adapter = FredTreasuryOverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
        )
        _ = adapter.load("2026-06-24")
        # Re-read from the base; the base should be unchanged.
        re_read = base.load("2026-06-24")
        self.assertEqual(re_read.us_yields, original_yields)


class FredTreasuryOverlayAdapterNetworkSafetyTests(unittest.TestCase):
    """Enforce that nms/data/fred_treasury.py does not perform network
    I/O, subprocess calls, or env-credential reads when an
    ``http_get`` is injected.
    """

    FRED_TREASURY_PATH = (
        REPO_ROOT / "nms" / "data" / "fred_treasury.py"
    )

    def test_no_socket_call_when_http_get_injected(self) -> None:
        dgs2_csv = "DATE,DGS2\n2026-06-23,4.10\n"
        dgs10_csv = "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
        with mock.patch("socket.socket") as mocked_socket, mock.patch(
            "socket.create_connection"
        ) as mocked_connect:
            adapter = FredTreasuryOverlayAdapter(
                base_adapter=_baseline_adapter(),
                http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
            )
            adapter.load("2026-06-24")
            mocked_socket.assert_not_called()
            mocked_connect.assert_not_called()

    def test_no_subprocess_call(self) -> None:
        dgs2_csv = "DATE,DGS2\n2026-06-23,4.10\n"
        dgs10_csv = "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
        with mock.patch("subprocess.Popen") as mocked_popen, mock.patch(
            "subprocess.run"
        ) as mocked_run, mock.patch("subprocess.call") as mocked_call:
            adapter = FredTreasuryOverlayAdapter(
                base_adapter=_baseline_adapter(),
                http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
            )
            adapter.load("2026-06-24")
            mocked_popen.assert_not_called()
            mocked_run.assert_not_called()
            mocked_call.assert_not_called()

    def test_no_env_credential_reads(self) -> None:
        dgs2_csv = "DATE,DGS2\n2026-06-23,4.10\n"
        dgs10_csv = "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
        with mock.patch("os.environ.get") as mocked_get, mock.patch(
            "os.getenv"
        ) as mocked_getenv:
            adapter = FredTreasuryOverlayAdapter(
                base_adapter=_baseline_adapter(),
                http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
            )
            adapter.load("2026-06-24")
            mocked_get.assert_not_called()
            mocked_getenv.assert_not_called()

    def _collect_imports(self, py_path: Path) -> set[str]:
        with py_path.open("r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=str(py_path))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                names.add(node.module.split(".")[0])
        return names

    def test_no_requests_httpx_aiohttp_dotenv_imports(self) -> None:
        forbidden = {
            "requests", "httpx", "aiohttp", "dotenv",
            "subprocess", "os", "shutil", "shelve", "pickle",
            "ib_insync", "ccxt", "alpaca_trade_api", "metatrader5",
        }
        imports = self._collect_imports(self.FRED_TREASURY_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"fred_treasury.py imports forbidden modules: {sorted(bad)}",
        )


class FredTreasuryAdapterSchemaTests(unittest.TestCase):
    """The adapter returns a fully validated MarketContext."""

    def test_returned_context_passes_validate_market_context(self) -> None:
        dgs2_csv = "DATE,DGS2\n2026-06-23,4.10\n"
        dgs10_csv = "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
        adapter = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
        )
        ctx = adapter.load("2026-06-24")
        # Re-validate: it should pass without raising.
        from dataclasses import asdict

        ctx2 = validate_market_context(asdict(ctx))
        self.assertIsInstance(ctx2, MarketContext)

    def test_only_us_yields_overlaid(self) -> None:
        # All other fields should come from the base adapter unchanged.
        dgs2_csv = "DATE,DGS2\n2026-06-23,4.10\n"
        dgs10_csv = "DATE,DGS10\n2026-06-23,4.00\n2026-06-22,3.98\n"
        adapter = FredTreasuryOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(dgs2_csv, dgs10_csv),
        )
        base = _baseline_adapter().load("2026-06-24")
        ctx = adapter.load("2026-06-24")
        self.assertEqual(ctx.session_date, base.session_date)
        self.assertEqual(ctx.timezone, base.timezone)
        self.assertEqual(ctx.us_equities, base.us_equities)
        self.assertEqual(ctx.semiconductor, base.semiconductor)
        self.assertEqual(ctx.fx, base.fx)
        self.assertEqual(ctx.nikkei_night_session, base.nikkei_night_session)
        self.assertEqual(ctx.previous_day, base.previous_day)
        self.assertEqual(ctx.economic_event_risk, base.economic_event_risk)
        self.assertEqual(ctx.intraday_range, base.intraday_range)
        self.assertEqual(ctx.volatility_context, base.volatility_context)
        # Only us_yields should differ.
        self.assertNotEqual(ctx.us_yields, base.us_yields)


if __name__ == "__main__":
    unittest.main()
