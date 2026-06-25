"""Tests for the FRED public USDJPY adapter.

These tests enforce the public/no-auth FRED USDJPY adapter contract:

* The adapter uses only publicly available FRED CSV data.
* No secrets, no API key, no PAT, no auth header or cookie.
* No broker SDK, no order placement, no live trading.
* No subprocess, no environment variable credential reading.
* No new runtime dependencies; stdlib only.
* The injected ``http_get`` is the only network entry point.
* The base adapter is read first, then USDJPY fields are overlaid.
* The adapter returns a validated :class:`MarketContext`.
* Only the two ``fx`` fields are overlaid.
* Missing previous DEXJPUS raises (no silent fallback to zero).
* Non-positive previous DEXJPUS raises.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import unittest
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
from unittest import mock

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.fred_usdjpy import (
    FredUSDJPYAdapterError,
    FredUSDJPYObservation,
    FredUSDJPYOverlayAdapter,
    FredUSDJPYSourceConfig,
)
from nms.data.models import (
    Fx,
    MarketContext,
)
from nms.data.validate import (
    ValidationError,
    validate_market_context,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FIXTURE = (
    REPO_ROOT / "fixtures" / "market_context" / "sample-session-2026-06-24.json"
)


# --- Sample CSVs --------------------------------------------------------

SAMPLE_DEXJPUS_CSV = """DATE,DEXJPUS
2024-01-02,141.23
2024-01-03,141.50
2024-01-04,142.10
"""

# Sample with at least two observations so previous exists
SAMPLE_DEXJPUS_TWO_OBS = """DATE,DEXJPUS
2026-06-23,144.20
2026-06-22,143.85
"""


def _make_fake_http_get(
    dexjpus_text: str = SAMPLE_DEXJPUS_TWO_OBS,
) -> "callable":
    """Return a fake ``http_get`` that returns the given CSV."""

    def fake_http_get(url: str) -> str:
        return dexjpus_text

    return fake_http_get


def _baseline_adapter() -> FixtureMarketContextAdapter:
    return FixtureMarketContextAdapter(
        base_path=REPO_ROOT / "fixtures" / "market_context"
    )


def _make_stub_base_adapter() -> Any:
    """Return a stub base adapter that always returns a minimal
    :class:`MarketContext` regardless of the requested date.
    """
    from nms.data.models import (
        EconomicEventRisk,
        IntradayRange,
        MarketContext,
        NikkeiNightSession,
        PreviousDay,
        Semiconductor,
        UsEquities,
        UsYields,
        VolatilityContext,
    )

    def _stub_load(session_date: str) -> MarketContext:
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
                close=0.0,
                high=0.0,
                low=0.0,
                range=0.0,
                percent_change=0.0,
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

    return mock.MagicMock(load=mock.MagicMock(side_effect=_stub_load))


# --- Parser tests --------------------------------------------------------


class ParseDEXJPUSCsvTests(unittest.TestCase):
    def test_parse_normal_csv(self) -> None:
        from nms.data.fred_usdjpy import _parse_fred_csv_observations

        obs = _parse_fred_csv_observations(SAMPLE_DEXJPUS_CSV, "DEXJPUS")
        self.assertEqual(len(obs), 3)
        self.assertEqual(obs[0].date, date(2024, 1, 2))
        self.assertAlmostEqual(obs[0].value, 141.23)
        self.assertEqual(obs[2].date, date(2024, 1, 4))
        self.assertAlmostEqual(obs[2].value, 142.10)

    def test_ignore_missing_value_rows(self) -> None:
        from nms.data.fred_usdjpy import _parse_fred_csv_observations

        csv = """DATE,DEXJPUS
2024-01-02,141.23
2024-01-03,.
2024-01-04,142.10
"""
        obs = _parse_fred_csv_observations(csv, "DEXJPUS")
        self.assertEqual(len(obs), 2)
        self.assertEqual(obs[0].date, date(2024, 1, 2))
        self.assertEqual(obs[1].date, date(2024, 1, 4))

    def test_reject_malformed_date(self) -> None:
        from nms.data.fred_usdjpy import _parse_fred_csv_observations

        csv = "DATE,DEXJPUS\nnot-a-date,141.23\n"
        with self.assertRaises(FredUSDJPYAdapterError):
            _parse_fred_csv_observations(csv, "DEXJPUS")

    def test_reject_malformed_numeric(self) -> None:
        from nms.data.fred_usdjpy import _parse_fred_csv_observations

        csv = "DATE,DEXJPUS\n2024-01-02,not-a-number\n"
        with self.assertRaises(FredUSDJPYAdapterError):
            _parse_fred_csv_observations(csv, "DEXJPUS")

    def test_reject_missing_column(self) -> None:
        from nms.data.fred_usdjpy import _parse_fred_csv_observations

        csv = "DATE,OTHER\n2024-01-02,141.23\n"
        with self.assertRaises(FredUSDJPYAdapterError):
            _parse_fred_csv_observations(csv, "DEXJPUS")

    def test_reject_empty_csv(self) -> None:
        from nms.data.fred_usdjpy import _parse_fred_csv_observations

        csv = "DATE,DEXJPUS\n"
        with self.assertRaises(FredUSDJPYAdapterError):
            _parse_fred_csv_observations(csv, "DEXJPUS")


# --- Adapter tests --------------------------------------------------------


class FredUSDJPYOverlayAdapterTests(unittest.TestCase):
    def test_load_returns_validated_market_context(self) -> None:
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        ctx = adapter.load("2026-06-24")
        self.assertIsInstance(ctx, MarketContext)
        # The returned context must pass re-validation.
        ctx2 = validate_market_context(asdict(ctx))
        self.assertIsInstance(ctx2, MarketContext)

    def test_load_uses_injected_http_get(self) -> None:
        calls: list[str] = []

        def tracking_http_get(url: str) -> str:
            calls.append(url)
            return SAMPLE_DEXJPUS_TWO_OBS

        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=tracking_http_get,
        )
        adapter.load("2026-06-24")
        self.assertEqual(len(calls), 1)
        self.assertIn("DEXJPUS", calls[0])

    def test_load_overlays_only_usdjpy_and_usdjpy_change_pct(self) -> None:
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        base = _baseline_adapter().load("2026-06-24")
        ctx = adapter.load("2026-06-24")
        # Only usdjpy and usdjpy_change_pct should differ.
        self.assertNotEqual(ctx.fx.usdjpy, base.fx.usdjpy)
        self.assertNotEqual(
            ctx.fx.usdjpy_change_pct, base.fx.usdjpy_change_pct
        )
        # All other sections should be unchanged.
        self.assertEqual(ctx.us_equities, base.us_equities)
        self.assertEqual(ctx.semiconductor, base.semiconductor)
        self.assertEqual(ctx.us_yields, base.us_yields)
        self.assertEqual(ctx.nikkei_night_session, base.nikkei_night_session)
        self.assertEqual(ctx.previous_day, base.previous_day)
        self.assertEqual(ctx.economic_event_risk, base.economic_event_risk)
        self.assertEqual(ctx.intraday_range, base.intraday_range)
        self.assertEqual(ctx.volatility_context, base.volatility_context)

    def test_compute_usdjpy_change_pct(self) -> None:
        # 144.20 vs 143.85 -> (144.20 / 143.85 - 1) * 100 ≈ 0.243%
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        ctx = adapter.load("2026-06-24")
        self.assertAlmostEqual(ctx.fx.usdjpy, 144.20)
        expected_change = ((144.20 / 143.85) - 1.0) * 100.0
        self.assertAlmostEqual(
            ctx.fx.usdjpy_change_pct, expected_change, places=6
        )

    def test_load_does_not_mutate_baseline_context(self) -> None:
        base = _baseline_adapter()
        original = base.load("2026-06-24")
        original_usdjpy = original.fx.usdjpy
        original_change = original.fx.usdjpy_change_pct
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(),
        )
        _ = adapter.load("2026-06-24")
        re_read = base.load("2026-06-24")
        self.assertEqual(re_read.fx.usdjpy, original_usdjpy)
        self.assertEqual(
            re_read.fx.usdjpy_change_pct, original_change
        )

    def test_choose_latest_observation_at_or_before_session_date(self) -> None:
        csv = """DATE,DEXJPUS
2024-01-02,141.23
2024-01-03,141.50
2024-01-04,142.10
"""
        base = _make_stub_base_adapter()
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        ctx = adapter.load("2024-01-03")
        self.assertAlmostEqual(ctx.fx.usdjpy, 141.50)

    def test_choose_previous_observation_strictly_before_selected(self) -> None:
        csv = """DATE,DEXJPUS
2024-01-02,141.23
2024-01-03,141.50
2024-01-04,142.10
"""
        # Loading 2024-01-03: latest is 141.50 (2024-01-03),
        # previous is 141.23 (2024-01-02).
        # change_pct = (141.50 / 141.23 - 1) * 100
        base = _make_stub_base_adapter()
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        ctx = adapter.load("2024-01-03")
        expected = ((141.50 / 141.23) - 1.0) * 100.0
        self.assertAlmostEqual(
            ctx.fx.usdjpy_change_pct, expected, places=6
        )

    def test_raises_when_no_previous_dexjpus(self) -> None:
        # Only one DEXJPUS observation exists.
        single_csv = "DATE,DEXJPUS\n2024-01-03,141.50\n"
        base = _make_stub_base_adapter()
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(single_csv),
        )
        with self.assertRaises(FredUSDJPYAdapterError) as cm:
            adapter.load("2024-01-03")
        self.assertIn("previous DEXJPUS", str(cm.exception))

    def test_raises_when_previous_dexjpus_is_non_positive(self) -> None:
        csv = """DATE,DEXJPUS
2024-01-02,0.0
2024-01-03,141.50
"""
        base = _make_stub_base_adapter()
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        with self.assertRaises(FredUSDJPYAdapterError) as cm:
            adapter.load("2024-01-03")
        self.assertIn("non-positive", str(cm.exception))

    def test_raises_when_previous_dexjpus_is_negative(self) -> None:
        csv = """DATE,DEXJPUS
2024-01-02,-100.0
2024-01-03,141.50
"""
        base = _make_stub_base_adapter()
        adapter = FredUSDJPYOverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        with self.assertRaises(FredUSDJPYAdapterError):
            adapter.load("2024-01-03")


# --- Network safety tests ------------------------------------------------


class FredUSDJPYAdapterNetworkSafetyTests(unittest.TestCase):
    """Enforce that nms/data/fred_usdjpy.py does not perform network
    I/O, subprocess calls, or env-credential reads when an
    ``http_get`` is injected.
    """

    FRED_USDJPY_PATH = REPO_ROOT / "nms" / "data" / "fred_usdjpy.py"

    def test_no_socket_call_when_http_get_injected(self) -> None:
        with mock.patch("socket.socket") as mocked_socket, mock.patch(
            "socket.create_connection"
        ) as mocked_connect:
            adapter = FredUSDJPYOverlayAdapter(
                base_adapter=_baseline_adapter(),
                http_get=_make_fake_http_get(),
            )
            adapter.load("2026-06-24")
            mocked_socket.assert_not_called()
            mocked_connect.assert_not_called()

    def test_no_subprocess_call(self) -> None:
        with mock.patch("subprocess.Popen") as mocked_popen, mock.patch(
            "subprocess.run"
        ) as mocked_run, mock.patch("subprocess.call") as mocked_call:
            adapter = FredUSDJPYOverlayAdapter(
                base_adapter=_baseline_adapter(),
                http_get=_make_fake_http_get(),
            )
            adapter.load("2026-06-24")
            mocked_popen.assert_not_called()
            mocked_run.assert_not_called()
            mocked_call.assert_not_called()

    def test_no_env_credential_reads(self) -> None:
        with mock.patch("os.environ.get") as mocked_get, mock.patch(
            "os.getenv"
        ) as mocked_getenv:
            adapter = FredUSDJPYOverlayAdapter(
                base_adapter=_baseline_adapter(),
                http_get=_make_fake_http_get(),
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

    def test_no_forbidden_imports(self) -> None:
        forbidden = {
            "requests", "httpx", "aiohttp", "dotenv",
            "subprocess", "os", "shutil", "shelve", "pickle",
            "ib_insync", "ccxt", "alpaca_trade_api", "metatrader5",
        }
        imports = self._collect_imports(self.FRED_USDJPY_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"fred_usdjpy.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_broker_order_account_fields_introduced(self) -> None:
        # The adapter must not introduce any account / broker / order
        # / position field. The schema is fixed by validate_market_context.
        # If a new top-level field were added, validate_market_context
        # would raise ValidationError. We test that an extra
        # account-balance field is rejected.
        ctx = _baseline_adapter().load("2026-06-24")
        ctx_dict = asdict(ctx)
        ctx_dict["account_balance"] = 100000
        with self.assertRaises(ValidationError):
            validate_market_context(ctx_dict)


if __name__ == "__main__":
    unittest.main()
