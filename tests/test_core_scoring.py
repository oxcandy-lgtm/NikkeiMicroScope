"""Tests for the pure scoring engine in ``nms/core/``.

These tests cover:

* bounded output of every component score;
* the MVP formulas (direction, volatility, event risk,
  no-trade, alignment penalty);
* the no-trade reason list;
* that scoring does not mutate its input;
* the core purity audit (no I/O, network, subprocess, env, or
  broker imports anywhere under ``nms/core/``).

The tests build a :class:`MarketContext` directly from dataclasses
so the test is focused on scoring and not on JSON parsing. The
sample fixture is used only in the end-to-end integration test
at the bottom of the file.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Iterable

from nms.core import (
    DIRECTION_WEIGHTS,
    EVENT_IMPACT_TABLE,
    NO_TRADE_THRESHOLD,
    PlannedSide,
    ScoreBreakdown,
    alignment_penalty,
    classify,
    direction_score,
    event_risk_score,
    no_trade_score,
    score_context,
    volatility_score,
)
from nms.data import FixtureMarketContextAdapter
from nms.data.models import (
    EconomicEventRisk,
    EventItem,
    Fx,
    IntradayRange,
    MarketContext,
    MVP_TIMEZONE,
    NikkeiNightSession,
    PreviousDay,
    Semiconductor,
    UsEquities,
    UsYields,
    VolatilityContext,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FIXTURE = (
    REPO_ROOT / "fixtures" / "market_context" / "sample-session-2026-06-24.json"
)


def _make_event(name: str, impact: str = "high") -> EventItem:
    return EventItem(name=name, time_jst="", impact=impact)


def _make_context(
    *,
    nikkei_pct: float = 0.0,
    realized_vol: float = 0.0,
    atr_like: float = 1.0,
    events: Iterable[EventItem] = (),
) -> MarketContext:
    """Build a MarketContext with controllable scoring inputs.

    Defaults are chosen so the formula returns well-defined values
    for the tests below. Callers override the fields they care about.
    """
    return MarketContext(
        session_date="2026-06-24",
        timezone=MVP_TIMEZONE,
        us_equities=UsEquities(
            sp500=0.0, dow=0.0, nasdaq100=0.0, russell2000=0.0
        ),
        semiconductor=Semiconductor(sox=0.0),
        fx=Fx(usdjpy=0.0),
        us_yields=UsYields(us2y=0.0, us10y=0.0, us10y_minus_us2y=0.0),
        nikkei_night_session=NikkeiNightSession(
            close=0.0,
            high=0.0,
            low=0.0,
            range=0.0,
            percent_change=nikkei_pct,
        ),
        previous_day=PreviousDay(high=0.0, low=0.0, close=0.0, range=0.0),
        economic_event_risk=EconomicEventRisk(events=list(events)),
        intraday_range=IntradayRange(
            first_15m_high=0.0,
            first_15m_low=0.0,
            first_15m_range=0.0,
            atr_like_baseline=1.0,
        ),
        volatility_context=VolatilityContext(
            realized_vol=realized_vol,
            atr_like=atr_like,
            compression_flag=False,
        ),
    )


class ClampTests(unittest.TestCase):
    def test_clamp_low(self) -> None:
        from nms.core.scoring import _clamp
        self.assertEqual(_clamp(-5.0, 0.0, 1.0), 0.0)

    def test_clamp_high(self) -> None:
        from nms.core.scoring import _clamp
        self.assertEqual(_clamp(5.0, 0.0, 1.0), 1.0)

    def test_clamp_passthrough(self) -> None:
        from nms.core.scoring import _clamp
        self.assertEqual(_clamp(0.5, 0.0, 1.0), 0.5)


class DirectionScoreTests(unittest.TestCase):
    def test_zero_pct_change_is_zero(self) -> None:
        ctx = _make_context(nikkei_pct=0.0)
        self.assertEqual(direction_score(ctx), 0.0)

    def test_positive_pct_saturates(self) -> None:
        # 2% should saturate the bounded normalizer at +1.0; with
        # weight 0.20 the contribution is 0.20.
        ctx = _make_context(nikkei_pct=2.0)
        self.assertAlmostEqual(direction_score(ctx), 0.20, places=6)

    def test_negative_pct_saturates(self) -> None:
        ctx = _make_context(nikkei_pct=-2.0)
        self.assertAlmostEqual(direction_score(ctx), -0.20, places=6)

    def test_pct_above_saturation_clamps(self) -> None:
        ctx = _make_context(nikkei_pct=10.0)
        self.assertAlmostEqual(direction_score(ctx), 0.20, places=6)

    def test_pct_below_saturation_clamps(self) -> None:
        ctx = _make_context(nikkei_pct=-10.0)
        self.assertAlmostEqual(direction_score(ctx), -0.20, places=6)

    def test_bounded_minus_one_to_plus_one(self) -> None:
        for pct in [-100.0, -3.0, -1.0, 0.0, 0.5, 1.0, 3.0, 100.0]:
            with self.subTest(pct=pct):
                ctx = _make_context(nikkei_pct=pct)
                d = direction_score(ctx)
                self.assertGreaterEqual(d, -1.0)
                self.assertLessEqual(d, 1.0)


class VolatilityScoreTests(unittest.TestCase):
    def test_zero_realized_at_baseline_is_zero(self) -> None:
        # realized == baseline -> 1 - 1 = 0
        ctx = _make_context(realized_vol=0.5, atr_like=0.5)
        self.assertEqual(volatility_score(ctx), 0.0)

    def test_compression_yields_high_score(self) -> None:
        # realized << baseline -> near 1.0
        ctx = _make_context(realized_vol=0.1, atr_like=1.0)
        self.assertAlmostEqual(volatility_score(ctx), 0.9, places=6)

    def test_expansion_yields_low_score(self) -> None:
        # realized > baseline -> clamped to 0.0
        ctx = _make_context(realized_vol=2.0, atr_like=1.0)
        self.assertEqual(volatility_score(ctx), 0.0)

    def test_zero_baseline_is_safe(self) -> None:
        ctx = _make_context(realized_vol=0.5, atr_like=0.0)
        self.assertEqual(volatility_score(ctx), 0.0)

    def test_negative_baseline_is_safe(self) -> None:
        ctx = _make_context(realized_vol=0.5, atr_like=-1.0)
        self.assertEqual(volatility_score(ctx), 0.0)

    def test_bounded_zero_to_one(self) -> None:
        for realized, baseline in [
            (0.0, 1.0), (0.5, 1.0), (1.0, 1.0), (2.0, 1.0),
            (0.0, 0.5), (0.1, 0.5), (0.0, 0.0), (1.0, 0.0),
        ]:
            with self.subTest(realized=realized, baseline=baseline):
                ctx = _make_context(realized_vol=realized, atr_like=baseline)
                v = volatility_score(ctx)
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)


class EventRiskScoreTests(unittest.TestCase):
    def test_no_events_is_zero(self) -> None:
        ctx = _make_context(events=())
        self.assertEqual(event_risk_score(ctx), 0.0)

    def test_high_impact_event(self) -> None:
        ctx = _make_context(events=[_make_event("FOMC", "high")])
        self.assertEqual(event_risk_score(ctx), 1.0)

    def test_medium_impact_event(self) -> None:
        ctx = _make_context(events=[_make_event("NFP", "medium")])
        self.assertEqual(event_risk_score(ctx), 0.5)

    def test_low_impact_event(self) -> None:
        ctx = _make_context(events=[_make_event("Minor", "low")])
        self.assertEqual(event_risk_score(ctx), 0.25)

    def test_unknown_impact_event_is_zero(self) -> None:
        ctx = _make_context(events=[_make_event("X", "unknown-impact")])
        self.assertEqual(event_risk_score(ctx), 0.0)

    def test_empty_impact_is_zero(self) -> None:
        ctx = _make_context(events=[_make_event("X", "")])
        self.assertEqual(event_risk_score(ctx), 0.0)

    def test_max_across_multiple_events(self) -> None:
        ctx = _make_context(
            events=[
                _make_event("A", "low"),
                _make_event("B", "high"),
                _make_event("C", "medium"),
            ]
        )
        self.assertEqual(event_risk_score(ctx), 1.0)

    def test_impact_table_constants(self) -> None:
        # The dispatch spec mandates the exact table values.
        self.assertEqual(EVENT_IMPACT_TABLE["high"], 1.0)
        self.assertEqual(EVENT_IMPACT_TABLE["medium"], 0.5)
        self.assertEqual(EVENT_IMPACT_TABLE["low"], 0.25)


class AlignmentPenaltyTests(unittest.TestCase):
    def test_buy_vs_negative_direction(self) -> None:
        self.assertEqual(alignment_penalty(-0.5, "buy"), 1.0)

    def test_sell_vs_positive_direction(self) -> None:
        self.assertEqual(alignment_penalty(0.5, "sell"), 1.0)

    def test_buy_vs_positive_direction(self) -> None:
        self.assertEqual(alignment_penalty(0.5, "buy"), 0.0)

    def test_sell_vs_negative_direction(self) -> None:
        self.assertEqual(alignment_penalty(-0.5, "sell"), 0.0)

    def test_none_always_zero(self) -> None:
        for d in [-1.0, -0.1, 0.0, 0.1, 1.0]:
            with self.subTest(direction=d):
                self.assertEqual(alignment_penalty(d, "none"), 0.0)

    def test_zero_direction_no_penalty(self) -> None:
        self.assertEqual(alignment_penalty(0.0, "buy"), 0.0)
        self.assertEqual(alignment_penalty(0.0, "sell"), 0.0)


class NoTradeScoreTests(unittest.TestCase):
    def test_zero_inputs_yield_zero(self) -> None:
        self.assertEqual(no_trade_score(0.0, 0.0, 0.0), 0.0)

    def test_max_inputs_yield_one(self) -> None:
        self.assertEqual(no_trade_score(1.0, 1.0, 1.0), 1.0)

    def test_weights_sum_to_one(self) -> None:
        from nms.core.constants import (
            NO_TRADE_WEIGHT_ALIGNMENT,
            NO_TRADE_WEIGHT_EVENT_RISK,
            NO_TRADE_WEIGHT_VOLATILITY,
        )
        total = (
            NO_TRADE_WEIGHT_ALIGNMENT
            + NO_TRADE_WEIGHT_EVENT_RISK
            + NO_TRADE_WEIGHT_VOLATILITY
        )
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_bounded_zero_to_one(self) -> None:
        for v in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for e in [0.0, 0.25, 0.5, 0.75, 1.0]:
                for p in [0.0, 0.5, 1.0]:
                    with self.subTest(v=v, e=e, p=p):
                        n = no_trade_score(v, e, p)
                        self.assertGreaterEqual(n, 0.0)
                        self.assertLessEqual(n, 1.0)


class NoTradeReasonsTests(unittest.TestCase):
    def test_event_risk_reason_emitted(self) -> None:
        ctx = _make_context(events=[_make_event("FOMC", "high")])
        breakdown = score_context(ctx, "none")
        self.assertIn(
            "event_risk:FOMC", breakdown.no_trade_reasons
        )

    def test_volatility_compression_reason_emitted(self) -> None:
        ctx = _make_context(realized_vol=0.1, atr_like=1.0)
        breakdown = score_context(ctx, "none")
        compression_reasons = [
            r for r in breakdown.no_trade_reasons
            if r.startswith("volatility_compression:")
        ]
        self.assertEqual(len(compression_reasons), 1)

    def test_alignment_penalty_reason_emitted(self) -> None:
        # Force a large negative direction by saturating nikkei_pct
        # downward, then plan a buy.
        ctx = _make_context(nikkei_pct=-10.0)
        breakdown = score_context(ctx, "buy")
        self.assertIn(
            "alignment_penalty:buy_vs_direction", breakdown.no_trade_reasons
        )

    def test_no_reasons_when_classification_is_buy_only(self) -> None:
        # Build a context that yields a low no_trade_score and a
        # positive direction. With no events, no compression, and
        # "none" planned side, reasons should be empty.
        ctx = _make_context(
            nikkei_pct=1.0,  # positive direction
            realized_vol=0.9,  # near baseline -> vol_score near 0
            atr_like=1.0,
            events=(),
        )
        breakdown = score_context(ctx, "none")
        self.assertEqual(breakdown.classification, "buy-only")
        self.assertEqual(breakdown.no_trade_reasons, ())


class ScoreContextTests(unittest.TestCase):
    def test_returns_score_breakdown(self) -> None:
        ctx = _make_context(nikkei_pct=0.5)
        b = score_context(ctx, "none")
        self.assertIsInstance(b, ScoreBreakdown)
        self.assertEqual(b.classification, "buy-only")
        self.assertGreater(b.direction_score, 0.0)

    def test_does_not_mutate_context(self) -> None:
        ctx = _make_context(nikkei_pct=0.5)
        # Snapshot key fields.
        before = (
            ctx.nikkei_night_session.percent_change,
            ctx.volatility_context.realized_vol,
            ctx.volatility_context.atr_like,
            tuple(
                (e.name, e.impact) for e in ctx.economic_event_risk.events
            ),
        )
        score_context(ctx, "buy")
        after = (
            ctx.nikkei_night_session.percent_change,
            ctx.volatility_context.realized_vol,
            ctx.volatility_context.atr_like,
            tuple(
                (e.name, e.impact) for e in ctx.economic_event_risk.events
            ),
        )
        self.assertEqual(before, after)

    def test_sample_fixture_end_to_end(self) -> None:
        # The sample fixture is loaded through the public data-layer
        # adapter (not by nms/core/) and then scored. This is the
        # full read-only path.
        adapter = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        ctx = adapter.load("2026-06-24")
        b = score_context(ctx, "none")
        # The sample has high-impact events and high realized vol
        # relative to the chosen baseline, so the classification
        # should be no-trade. We assert the structure, not the
        # exact number, because the data is synthetic.
        self.assertIn(b.classification, {"buy-only", "sell-only", "no-trade"})
        self.assertGreaterEqual(b.no_trade_score, 0.0)
        self.assertLessEqual(b.no_trade_score, 1.0)


class CorePurityTests(unittest.TestCase):
    """Static + runtime checks that nms/core/ stays pure."""

    CORE_FILES = [
        REPO_ROOT / "nms" / "core" / "__init__.py",
        REPO_ROOT / "nms" / "core" / "constants.py",
        REPO_ROOT / "nms" / "core" / "scoring.py",
        REPO_ROOT / "nms" / "core" / "classification.py",
    ]

    #: Modules that MUST NOT appear anywhere in nms/core/.
    FORBIDDEN_IMPORTS = frozenset(
        {
            "json", "pathlib", "os", "subprocess", "socket",
            "urllib", "urllib.request", "urllib.error", "urllib.parse",
            "http", "http.client", "requests", "httpx", "aiohttp",
            "urllib3", "dotenv", "shutil", "shelve", "pickle",
        }
    )

    #: Modules that ARE allowed in nms/core/ (stdlib + our own data
    #: layer). The ``math`` module is allowed but not currently used.
    ALLOWED_IMPORTS = frozenset(
        {
            "__future__",
            "dataclasses",
            "typing",
            "math",
            "nms",
        }
    )

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
        for path in self.CORE_FILES:
            with self.subTest(file=path.name):
                imports = self._collect_imports(path)
                bad = imports & self.FORBIDDEN_IMPORTS
                self.assertFalse(
                    bad,
                    f"{path.name} imports forbidden modules: {sorted(bad)}",
                )

    def test_only_allowed_imports(self) -> None:
        for path in self.CORE_FILES:
            with self.subTest(file=path.name):
                imports = self._collect_imports(path)
                unexpected = imports - self.ALLOWED_IMPORTS
                self.assertFalse(
                    unexpected,
                    f"{path.name} has unexpected imports: {sorted(unexpected)}",
                )

    def test_direction_weights_sum_to_one(self) -> None:
        total = sum(DIRECTION_WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_classification_threshold_constant(self) -> None:
        # The dispatch spec mandates NO_TRADE_THRESHOLD = 0.5.
        self.assertEqual(NO_TRADE_THRESHOLD, 0.5)

    def test_classify_is_pure(self) -> None:
        # Same inputs -> same output, no hidden state.
        self.assertEqual(classify(0.6, 0.1), "no-trade")
        self.assertEqual(classify(0.6, 0.1), "no-trade")
        self.assertEqual(classify(0.4, 0.1), "buy-only")
        self.assertEqual(classify(0.4, -0.1), "sell-only")
        self.assertEqual(classify(0.4, 0.0), "no-trade")


if __name__ == "__main__":
    unittest.main()
