"""Tests for the MarketContext data model and schema validator.

These tests cover the schema rules documented in
``docs/data-adapter-contract.md``:

* the sample fixture loads successfully and round-trips through the
  validator into a populated :class:`MarketContext`;
* a missing required field is rejected with :class:`ValidationError`;
* a non-numeric value in a numeric field is rejected;
* a list-typed field (``events``) is rejected when given a non-list;
* the validator rejects payloads that contain extra top-level keys
  (defense in depth against account / broker fields creeping in);
* the MVP timezone constraint is enforced.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from nms.data import (
    EconomicEventRisk,
    FixtureMarketContextAdapter,
    Fx,
    IntradayRange,
    MarketContext,
    NikkeiNightSession,
    PreviousDay,
    Semiconductor,
    UsEquities,
    UsYields,
    ValidationError,
    VolatilityContext,
    validate_market_context,
)
from nms.data.models import MVP_TIMEZONE


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FIXTURE = (
    REPO_ROOT
    / "fixtures"
    / "market_context"
    / "sample-session-2026-06-24.json"
)


def _minimal_valid_payload() -> dict:
    """Build a minimal valid payload for negative tests."""
    return {
        "session_date": "2026-06-24",
        "timezone": MVP_TIMEZONE,
        "us_equities": {
            "sp500": 1.0,
            "dow": 1.0,
            "nasdaq100": 1.0,
            "russell2000": 1.0,
        },
        "semiconductor": {"sox": 1.0},
        "fx": {"usdjpy": 1.0},
        "us_yields": {"us2y": 1.0, "us10y": 1.0, "us10y_minus_us2y": 0.0},
        "nikkei_night_session": {
            "close": 1.0,
            "high": 1.0,
            "low": 1.0,
            "range": 0.0,
            "percent_change": 0.0,
        },
        "previous_day": {
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "range": 0.0,
        },
        "economic_event_risk": {"events": []},
        "intraday_range": {
            "first_15m_high": 1.0,
            "first_15m_low": 1.0,
            "first_15m_range": 0.0,
            "atr_like_baseline": 1.0,
        },
        "volatility_context": {
            "realized_vol": 0.0,
            "atr_like": 1.0,
            "compression_flag": False,
        },
    }


class SampleFixtureTests(unittest.TestCase):
    def test_sample_fixture_file_exists(self) -> None:
        self.assertTrue(
            SAMPLE_FIXTURE.is_file(),
            f"sample fixture missing: {SAMPLE_FIXTURE}",
        )

    def test_sample_fixture_is_valid_json(self) -> None:
        with SAMPLE_FIXTURE.open("r", encoding="utf-8") as fh:
            json.load(fh)  # raises if invalid

    def test_sample_fixture_validates(self) -> None:
        with SAMPLE_FIXTURE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        ctx = validate_market_context(data)
        self.assertIsInstance(ctx, MarketContext)
        self.assertEqual(ctx.session_date, "2026-06-24")
        self.assertEqual(ctx.timezone, MVP_TIMEZONE)
        self.assertIsInstance(ctx.us_equities, UsEquities)
        self.assertIsInstance(ctx.semiconductor, Semiconductor)
        self.assertIsInstance(ctx.fx, Fx)
        self.assertIsInstance(ctx.us_yields, UsYields)
        self.assertIsInstance(ctx.nikkei_night_session, NikkeiNightSession)
        self.assertIsInstance(ctx.previous_day, PreviousDay)
        self.assertIsInstance(ctx.economic_event_risk, EconomicEventRisk)
        self.assertIsInstance(ctx.intraday_range, IntradayRange)
        self.assertIsInstance(ctx.volatility_context, VolatilityContext)
        self.assertEqual(len(ctx.economic_event_risk.events), 2)

    def test_fixture_adapter_loads_sample(self) -> None:
        adapter = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        ctx = adapter.load("2026-06-24")
        self.assertEqual(ctx.session_date, "2026-06-24")

    def test_fixture_adapter_missing_file_raises(self) -> None:
        adapter = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        with self.assertRaises(FileNotFoundError):
            adapter.load("1999-01-01")


class SchemaNegativeTests(unittest.TestCase):
    def test_missing_top_level_field_rejected(self) -> None:
        payload = _minimal_valid_payload()
        del payload["us_equities"]
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_missing_nested_field_rejected(self) -> None:
        payload = _minimal_valid_payload()
        del payload["us_equities"]["sp500"]
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_non_numeric_rejected(self) -> None:
        payload = _minimal_valid_payload()
        payload["us_equities"]["sp500"] = "not-a-number"
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_bool_rejected_for_numeric_field(self) -> None:
        # ``True`` is technically ``int`` in Python, but is almost
        # always a schema bug. The validator rejects it explicitly.
        payload = _minimal_valid_payload()
        payload["us_equities"]["sp500"] = True
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_events_must_be_list(self) -> None:
        payload = _minimal_valid_payload()
        payload["economic_event_risk"]["events"] = {"name": "FOMC"}
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_event_item_must_have_name_string(self) -> None:
        payload = _minimal_valid_payload()
        payload["economic_event_risk"]["events"] = [{"name": 42}]
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_extra_top_level_field_rejected(self) -> None:
        # Defense in depth: account / broker / order fields must not
        # silently appear in the schema.
        payload = _minimal_valid_payload()
        payload["account_balance"] = 100000
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_extra_broker_field_rejected(self) -> None:
        payload = _minimal_valid_payload()
        payload["broker_endpoint"] = "https://broker.example.com"
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_extra_nested_us_equities_field_rejected(self) -> None:
        # Defense in depth: account / broker / order fields must not
        # be silently added at any nesting level. ``us_equities`` only
        # allows the four documented indices.
        payload = _minimal_valid_payload()
        payload["us_equities"]["secret_account_id"] = "ACC-12345"
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_extra_nested_fx_field_rejected(self) -> None:
        # ``fx`` only allows ``usdjpy``. Any extra key (e.g. a hidden
        # ``api_key`` or ``broker_token``) is rejected.
        payload = _minimal_valid_payload()
        payload["fx"]["api_key"] = "sk-live-pretend"
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_extra_event_item_field_rejected(self) -> None:
        # ``economic_event_risk.events[i]`` only allows
        # ``name``, ``time_jst``, ``impact``. Any extra key (e.g. a
        # ``broker_order_ref`` or an ``account_id``) is rejected.
        payload = _minimal_valid_payload()
        payload["economic_event_risk"]["events"] = [
            {
                "name": "FOMC",
                "time_jst": "2026-06-24T21:00:00+09:00",
                "impact": "high",
                "broker_order_ref": "ORD-9999",
            }
        ]
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_timezone_must_be_mvp_canonical(self) -> None:
        payload = _minimal_valid_payload()
        payload["timezone"] = "UTC"
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_compression_flag_must_be_bool(self) -> None:
        payload = _minimal_valid_payload()
        payload["volatility_context"]["compression_flag"] = 1
        with self.assertRaises(ValidationError):
            validate_market_context(payload)

    def test_top_level_must_be_mapping(self) -> None:
        with self.assertRaises(ValidationError):
            validate_market_context(["not", "a", "mapping"])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
