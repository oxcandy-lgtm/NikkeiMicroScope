"""Tests for the FRED public S&P 500 adapter.

These tests enforce the public/no-auth FRED SP500 adapter contract:

* The adapter uses only publicly available FRED CSV data.
* No secrets, no API key, no PAT, no auth header or cookie.
* No broker SDK, no order placement, no live trading.
* No subprocess, no environment variable credential reading.
* No new runtime dependencies; stdlib only.
* The injected ``http_get`` is the only network entry point.
* The base adapter is read first, then SP500 fields are overlaid.
* The adapter returns a validated :class:`MarketContext`.
* Only the two ``us_equities`` fields are overlaid.
* Missing previous SP500 raises (no silent fallback to zero).
* Non-positive previous SP500 raises.
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
from nms.data.fred_sp500 import (
    FredSP500AdapterError,
    FredSP500Observation,
    FredSP500OverlayAdapter,
    FredSP500SourceConfig,
)
from nms.data.models import (
    MarketContext,
    UsEquities,
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

SAMPLE_SP500_CSV = """DATE,SP500
2024-01-02,4760.23
2024-01-03,4775.10
2024-01-04,4800.50
"""

# Sample with at least two observations so previous exists
SAMPLE_SP500_TWO_OBS = """DATE,SP500
2026-06-23,5760.23
2026-06-22,5750.10
"""


def _make_fake_http_get(
    sp500_text: str = SAMPLE_SP500_TWO_OBS,
) -> "callable":
    """Return a fake ``http_get`` that returns the given CSV."""

    def fake_http_get(url: str) -> str:
        return sp500_text

    return fake_http_get


def _baseline_adapter() -> FixtureMarketContextAdapter:
    return FixtureMarketContextAdapter(
        base_path=REPO_ROOT / "fixtures" / "market_context"
    )


def _make_stub_base_adapter() -> Any:
    """Return a stub base adapter that always returns a minimal
    :class:`MarketContext` regardless of the requested date.

    Used by tests that need to exercise the SP500 adapter with
    arbitrary session dates (the real fixture adapter only knows
    the sample date).
    """
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


class ParseSP500CsvTests(unittest.TestCase):
    def test_parse_normal_csv(self) -> None:
        from nms.data.fred_sp500 import _parse_fred_csv_observations

        obs = _parse_fred_csv_observations(SAMPLE_SP500_CSV, "SP500")
        self.assertEqual(len(obs), 3)
        self.assertEqual(obs[0].date, date(2024, 1, 2))
        self.assertAlmostEqual(obs[0].value, 4760.23)
        self.assertEqual(obs[2].date, date(2024, 1, 4))
        self.assertAlmostEqual(obs[2].value, 4800.50)

    def test_ignore_missing_value_rows(self) -> None:
        from nms.data.fred_sp500 import _parse_fred_csv_observations

        csv = """DATE,SP500
2024-01-02,4760.23
2024-01-03,.
2024-01-04,4800.50
"""
        obs = _parse_fred_csv_observations(csv, "SP500")
        self.assertEqual(len(obs), 2)
        self.assertEqual(obs[0].date, date(2024, 1, 2))
        self.assertEqual(obs[1].date, date(2024, 1, 4))

    def test_reject_malformed_date(self) -> None:
        from nms.data.fred_sp500 import _parse_fred_csv_observations

        csv = "DATE,SP500\nnot-a-date,4760.23\n"
        with self.assertRaises(FredSP500AdapterError):
            _parse_fred_csv_observations(csv, "SP500")

    def test_reject_malformed_numeric(self) -> None:
        from nms.data.fred_sp500 import _parse_fred_csv_observations

        csv = "DATE,SP500\n2024-01-02,not-a-number\n"
        with self.assertRaises(FredSP500AdapterError):
            _parse_fred_csv_observations(csv, "SP500")

    def test_reject_missing_column(self) -> None:
        from nms.data.fred_sp500 import _parse_fred_csv_observations

        csv = "DATE,OTHER\n2024-01-02,4760.23\n"
        with self.assertRaises(FredSP500AdapterError):
            _parse_fred_csv_observations(csv, "SP500")

    def test_reject_empty_csv(self) -> None:
        from nms.data.fred_sp500 import _parse_fred_csv_observations

        csv = "DATE,SP500\n"
        with self.assertRaises(FredSP500AdapterError):
            _parse_fred_csv_observations(csv, "SP500")


# --- Adapter tests --------------------------------------------------------


class FredSP500OverlayAdapterTests(unittest.TestCase):
    def test_load_returns_validated_market_context(self) -> None:
        adapter = FredSP500OverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        ctx = adapter.load("2026-06-24")
        self.assertIsInstance(ctx, MarketContext)
        # The returned context must pass re-validation.
        ctx2 = validate_market_context(
            {
                "session_date": ctx.session_date,
                "timezone": ctx.timezone,
                "us_equities": ctx.us_equities.__dict__,
                "semiconductor": ctx.semiconductor.__dict__,
                "fx": ctx.fx.__dict__,
                "us_yields": ctx.us_yields.__dict__,
                "nikkei_night_session": ctx.nikkei_night_session.__dict__,
                "previous_day": ctx.previous_day.__dict__,
                "economic_event_risk": {
                    "events": [
                        e.__dict__ for e in ctx.economic_event_risk.events
                    ]
                },
                "intraday_range": ctx.intraday_range.__dict__,
                "volatility_context": ctx.volatility_context.__dict__,
            }
        )
        self.assertIsInstance(ctx2, MarketContext)

    def test_load_uses_injected_http_get(self) -> None:
        calls: list[str] = []

        def tracking_http_get(url: str) -> str:
            calls.append(url)
            return SAMPLE_SP500_TWO_OBS

        adapter = FredSP500OverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=tracking_http_get,
        )
        adapter.load("2026-06-24")
        self.assertEqual(len(calls), 1)
        self.assertIn("SP500", calls[0])

    def test_load_overlays_only_sp500_and_sp500_change_pct(self) -> None:
        adapter = FredSP500OverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        base = _baseline_adapter().load("2026-06-24")
        ctx = adapter.load("2026-06-24")
        # Only sp500 and sp500_change_pct should differ.
        self.assertNotEqual(ctx.us_equities.sp500, base.us_equities.sp500)
        self.assertNotEqual(
            ctx.us_equities.sp500_change_pct, base.us_equities.sp500_change_pct
        )
        # All other us_equities fields should be unchanged.
        self.assertEqual(ctx.us_equities.dow, base.us_equities.dow)
        self.assertEqual(ctx.us_equities.nasdaq100, base.us_equities.nasdaq100)
        self.assertEqual(
            ctx.us_equities.russell2000, base.us_equities.russell2000
        )
        self.assertEqual(
            ctx.us_equities.nasdaq100_change_pct,
            base.us_equities.nasdaq100_change_pct,
        )
        # All other sections should be unchanged.
        self.assertEqual(ctx.semiconductor, base.semiconductor)
        self.assertEqual(ctx.fx, base.fx)
        self.assertEqual(ctx.us_yields, base.us_yields)
        self.assertEqual(
            ctx.nikkei_night_session, base.nikkei_night_session
        )
        self.assertEqual(ctx.previous_day, base.previous_day)
        self.assertEqual(ctx.economic_event_risk, base.economic_event_risk)
        self.assertEqual(ctx.intraday_range, base.intraday_range)
        self.assertEqual(ctx.volatility_context, base.volatility_context)

    def test_compute_sp500_change_pct(self) -> None:
        # 5760.23 vs 5750.10 -> (5760.23 / 5750.10 - 1) * 100 ≈ 0.1758%
        adapter = FredSP500OverlayAdapter(
            base_adapter=_baseline_adapter(),
            http_get=_make_fake_http_get(),
        )
        ctx = adapter.load("2026-06-24")
        self.assertAlmostEqual(ctx.us_equities.sp500, 5760.23)
        expected_change = ((5760.23 / 5750.10) - 1.0) * 100.0
        self.assertAlmostEqual(
            ctx.us_equities.sp500_change_pct, expected_change, places=6
        )

    def test_load_does_not_mutate_baseline_context(self) -> None:
        base = _baseline_adapter()
        original = base.load("2026-06-24")
        original_sp500 = original.us_equities.sp500
        original_change = original.us_equities.sp500_change_pct
        adapter = FredSP500OverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(),
        )
        _ = adapter.load("2026-06-24")
        re_read = base.load("2026-06-24")
        self.assertEqual(re_read.us_equities.sp500, original_sp500)
        self.assertEqual(
            re_read.us_equities.sp500_change_pct, original_change
        )

    def test_choose_latest_observation_at_or_before_session_date(self) -> None:
        csv = """DATE,SP500
2024-01-02,4760.23
2024-01-03,4775.10
2024-01-04,4800.50
"""
        # Use a stub base adapter that always returns a minimal
        # MarketContext, so we can test with arbitrary session dates.
        base = _make_stub_base_adapter()
        adapter = FredSP500OverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        ctx = adapter.load("2024-01-03")
        self.assertAlmostEqual(ctx.us_equities.sp500, 4775.10)

    def test_choose_previous_observation_strictly_before_selected(self) -> None:
        csv = """DATE,SP500
2024-01-02,4760.23
2024-01-03,4775.10
2024-01-04,4800.50
"""
        # Loading 2024-01-03: latest is 4775.10 (2024-01-03),
        # previous is 4760.23 (2024-01-02).
        # change_pct = (4775.10 / 4760.23 - 1) * 100
        base = _make_stub_base_adapter()
        adapter = FredSP500OverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        ctx = adapter.load("2024-01-03")
        expected = ((4775.10 / 4760.23) - 1.0) * 100.0
        self.assertAlmostEqual(
            ctx.us_equities.sp500_change_pct, expected, places=6
        )

    def test_raises_when_no_previous_sp500(self) -> None:
        # Only one SP500 observation exists.
        single_csv = "DATE,SP500\n2024-01-03,4775.10\n"
        base = _make_stub_base_adapter()
        adapter = FredSP500OverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(single_csv),
        )
        with self.assertRaises(FredSP500AdapterError) as cm:
            adapter.load("2024-01-03")
        self.assertIn("previous SP500", str(cm.exception))

    def test_raises_when_previous_sp500_is_non_positive(self) -> None:
        # Previous SP500 is 0.0 (should be impossible in reality, but
        # the adapter must reject it rather than divide by zero).
        csv = """DATE,SP500
2024-01-02,0.0
2024-01-03,4775.10
"""
        base = _make_stub_base_adapter()
        adapter = FredSP500OverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        with self.assertRaises(FredSP500AdapterError) as cm:
            adapter.load("2024-01-03")
        self.assertIn("non-positive", str(cm.exception))

    def test_raises_when_previous_sp500_is_negative(self) -> None:
        csv = """DATE,SP500
2024-01-02,-100.0
2024-01-03,4775.10
"""
        base = _make_stub_base_adapter()
        adapter = FredSP500OverlayAdapter(
            base_adapter=base,
            http_get=_make_fake_http_get(csv),
        )
        with self.assertRaises(FredSP500AdapterError):
            adapter.load("2024-01-03")


# --- Network safety tests ------------------------------------------------


class FredSP500AdapterNetworkSafetyTests(unittest.TestCase):
    """Enforce that nms/data/fred_sp500.py does not perform network
    I/O, subprocess calls, or env-credential reads when an
    ``http_get`` is injected.
    """

    FRED_SP500_PATH = REPO_ROOT / "nms" / "data" / "fred_sp500.py"

    def test_no_socket_call_when_http_get_injected(self) -> None:
        with mock.patch("socket.socket") as mocked_socket, mock.patch(
            "socket.create_connection"
        ) as mocked_connect:
            adapter = FredSP500OverlayAdapter(
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
            adapter = FredSP500OverlayAdapter(
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
            adapter = FredSP500OverlayAdapter(
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
        imports = self._collect_imports(self.FRED_SP500_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"fred_sp500.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_broker_order_account_fields_introduced(self) -> None:
        # The adapter must not introduce any account / broker / order
        # / position field. The schema is fixed by validate_market_context.
        # If a new top-level field were added, validate_market_context
        # would raise ValidationError. We test that an extra
        # account-balance field is rejected.
        ctx = _baseline_adapter().load("2026-06-24")
        from dataclasses import asdict

        ctx_dict = asdict(ctx)
        ctx_dict["account_balance"] = 100000
        with self.assertRaises(ValidationError):
            validate_market_context(ctx_dict)


if __name__ == "__main__":
    unittest.main()
