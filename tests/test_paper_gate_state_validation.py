"""State validation tests for the paper gate model."""

from __future__ import annotations

import unittest
from dataclasses import replace

from nms.paper.gates import (
    FIXED_CONTRACT_COUNT,
    PaperGateError,
    PaperGateState,
    evaluate_all_gates,
    evaluate_daily_gate,
    evaluate_session_gate,
    evaluate_weekly_gate,
    format_halt_reason,
    make_initial_paper_gate_state,
)


def _state() -> PaperGateState:
    return make_initial_paper_gate_state(
        "session-1", "2026-06-29", "2026-W27"
    )


class PaperGateStateValidationTests(unittest.TestCase):
    def _assert_rejected_by_all(self, state: object) -> None:
        for fn in (
            evaluate_session_gate,
            evaluate_daily_gate,
            evaluate_weekly_gate,
            evaluate_all_gates,
        ):
            with self.subTest(fn=fn.__name__):
                with self.assertRaises(PaperGateError):
                    fn(state, -1)  # type: ignore[arg-type]

    def test_rejects_non_state_object(self) -> None:
        self._assert_rejected_by_all({"not": "a state"})

    def test_rejects_empty_session_id(self) -> None:
        self._assert_rejected_by_all(replace(_state(), session_id=""))

    def test_rejects_empty_day_key(self) -> None:
        self._assert_rejected_by_all(replace(_state(), day_key=""))

    def test_rejects_empty_week_key(self) -> None:
        self._assert_rejected_by_all(replace(_state(), week_key=""))

    def test_rejects_negative_session_realized(self) -> None:
        self._assert_rejected_by_all(
            replace(_state(), session_realized_jpy=-1)
        )

    def test_rejects_negative_day_realized(self) -> None:
        self._assert_rejected_by_all(replace(_state(), day_realized_jpy=-1))

    def test_rejects_negative_week_realized(self) -> None:
        self._assert_rejected_by_all(replace(_state(), week_realized_jpy=-1))

    def test_rejects_bool_session_realized(self) -> None:
        self._assert_rejected_by_all(
            replace(_state(), session_realized_jpy=True)
        )

    def test_rejects_bool_day_realized(self) -> None:
        self._assert_rejected_by_all(replace(_state(), day_realized_jpy=False))

    def test_rejects_bool_week_realized(self) -> None:
        self._assert_rejected_by_all(replace(_state(), week_realized_jpy=True))

    def test_rejects_non_bool_session_halted(self) -> None:
        self._assert_rejected_by_all(
            replace(_state(), session_halted=1)  # type: ignore[arg-type]
        )

    def test_rejects_non_bool_day_halted(self) -> None:
        self._assert_rejected_by_all(
            replace(_state(), day_halted=0)  # type: ignore[arg-type]
        )

    def test_rejects_non_bool_week_halted(self) -> None:
        self._assert_rejected_by_all(
            replace(_state(), week_halted="false")  # type: ignore[arg-type]
        )

    def test_rejects_bool_contract_count(self) -> None:
        self._assert_rejected_by_all(
            replace(_state(), contract_count=True)  # type: ignore[arg-type]
        )

    def test_rejects_wrong_contract_count(self) -> None:
        self._assert_rejected_by_all(
            replace(_state(), contract_count=FIXED_CONTRACT_COUNT + 1)
        )

    def test_valid_state_still_passes_below_cap(self) -> None:
        decision = evaluate_all_gates(_state(), -1)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.state_after.session_realized_jpy, 1)
        self.assertEqual(decision.state_after.day_realized_jpy, 1)
        self.assertEqual(decision.state_after.week_realized_jpy, 1)


class PaperGateFormatValidationTests(unittest.TestCase):
    def test_format_halt_reason_rejects_negative_limit(self) -> None:
        with self.assertRaises(PaperGateError):
            format_halt_reason("session", -1, 0)

    def test_format_halt_reason_rejects_negative_observed(self) -> None:
        with self.assertRaises(PaperGateError):
            format_halt_reason("session", 1, -1)

    def test_format_halt_reason_rejects_bool_limit(self) -> None:
        with self.assertRaises(PaperGateError):
            format_halt_reason("session", True, 1)  # type: ignore[arg-type]

    def test_format_halt_reason_rejects_bool_observed(self) -> None:
        with self.assertRaises(PaperGateError):
            format_halt_reason("session", 1, False)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
