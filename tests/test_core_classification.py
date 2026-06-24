"""Tests for the session classifier in ``nms/core/classification.py``.

These tests are focused on the three-way mapping from
``(no_trade_score, direction_score)`` to one of ``"buy-only"``,
``"sell-only"``, ``"no-trade"``. The composition with the scoring
engine is covered in ``test_core_scoring.py``.
"""

from __future__ import annotations

import unittest

from nms.core import NO_TRADE_THRESHOLD, classify


class ClassifyThresholdTests(unittest.TestCase):
    def test_no_trade_above_threshold(self) -> None:
        self.assertEqual(classify(NO_TRADE_THRESHOLD + 0.01, 0.5), "no-trade")

    def test_no_trade_at_threshold(self) -> None:
        # The spec says ``no_trade_score >= NO_TRADE_THRESHOLD`` is
        # no-trade. The boundary belongs to no-trade.
        self.assertEqual(classify(NO_TRADE_THRESHOLD, 0.5), "no-trade")

    def test_buy_only_below_threshold(self) -> None:
        self.assertEqual(
            classify(NO_TRADE_THRESHOLD - 0.01, 0.1), "buy-only"
        )

    def test_sell_only_below_threshold(self) -> None:
        self.assertEqual(
            classify(NO_TRADE_THRESHOLD - 0.01, -0.1), "sell-only"
        )

    def test_zero_direction_below_threshold_is_no_trade(self) -> None:
        # When the direction is exactly zero and we are below the
        # no-trade threshold, the spec says no-trade.
        self.assertEqual(classify(0.0, 0.0), "no-trade")


class ClassifyDirectionTests(unittest.TestCase):
    """Direction only matters when no_trade_score is below threshold."""

    def test_positive_direction_yields_buy_only(self) -> None:
        for d in [0.01, 0.1, 0.5, 1.0]:
            with self.subTest(d=d):
                self.assertEqual(classify(0.0, d), "buy-only")

    def test_negative_direction_yields_sell_only(self) -> None:
        for d in [-0.01, -0.1, -0.5, -1.0]:
            with self.subTest(d=d):
                self.assertEqual(classify(0.0, d), "sell-only")


class ClassifyStabilityTests(unittest.TestCase):
    def test_classify_is_deterministic(self) -> None:
        for _ in range(5):
            self.assertEqual(classify(0.3, 0.2), "buy-only")
            self.assertEqual(classify(0.3, -0.2), "sell-only")
            self.assertEqual(classify(0.7, 0.2), "no-trade")
            self.assertEqual(classify(0.7, -0.2), "no-trade")
            self.assertEqual(classify(0.3, 0.0), "no-trade")

    def test_classify_does_not_touch_globals(self) -> None:
        # Smoke check: classify is a pure function of its arguments.
        # The output is the same regardless of call order.
        a = classify(0.6, 0.1)
        b = classify(0.4, 0.1)
        c = classify(0.6, 0.1)
        self.assertEqual(a, c)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
