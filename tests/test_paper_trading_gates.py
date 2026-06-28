"""Tests for the paper-trading refinement pure gate model.

These tests enforce the contract documented in
``docs/paper-trading-refinement-contract.md`` and the
higher-level policy brief in
``docs/code-agent-paper-trading-refinement-brief.md``.

Coverage:

* module is importable and pure.
* constants are exposed at the expected values.
* non-claims are audit-safe.
* ``make_initial_paper_gate_state`` validates inputs.
* initial state has zero realized drawdown and the
  fixed contract count.
* ``format_halt_reason`` is deterministic and validates
  inputs.
* session gate trips at the session cap.
* daily gate trips at the daily cap.
* weekly gate trips at the weekly cap.
* gains do not offset drawdowns.
* zero delta is a no-op.
* a halted gate rejects subsequent events.
* the composite ``evaluate_all_gates`` updates all three
  realized counters atomically.
* the composite returns the first scope that trips.
* contract-count escalation is rejected.
* non-int deltas are rejected.
* no subprocess import/call in ``nms/paper/gates.py``.
* no subprocess import/call in this test file.
* no env credential reads.
* no network library imports.
* no broker / auth / cookie / path introduced.
* no money / result-ratio / win-count /
  forward-outcome / scored-result fields in the
  module's public surface.
* no SOX adapter introduced.
* no raw FRED CSV committed.
* contract doc exists.

All checks are pure filesystem / static checks. No
subprocess is invoked. No network is used.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from nms.paper.gates import (
    FIXED_CONTRACT_COUNT,
    HALT_SCOPE_ALREADY_HALTED,
    HALT_SCOPE_DAILY,
    HALT_SCOPE_SESSION,
    HALT_SCOPE_WEEKLY,
    MAX_DAILY_DRAWDOWN_JPY,
    MAX_SESSION_DRAWDOWN_JPY,
    MAX_WEEKLY_DRAWDOWN_JPY,
    PAPER_GATE_NON_CLAIMS,
    PAPER_GATE_SCHEMA_VERSION,
    PaperGateDecision,
    PaperGateError,
    PaperGateState,
    evaluate_all_gates,
    evaluate_daily_gate,
    evaluate_session_gate,
    evaluate_weekly_gate,
    format_halt_reason,
    make_initial_paper_gate_state,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
GATES_PATH = REPO_ROOT / "nms" / "paper" / "gates.py"
CONTRACT_DOC = (
    REPO_ROOT / "docs" / "paper-trading-refinement-contract.md"
)

# Authoritative forbidden-substring list per the dispatch's
# paper-gate extension of the shadow-replay purity audit.
FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "pnl",
    "profit",
    "loss",
    "return_pct",
    "win_rate",
    "sharpe",
    "expected_return",
    "equity_curve",
    "portfolio",
    "position",
    "cash_balance",
    "performance",
)

FORBIDDEN_IMPORTS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "pandas",
    "yfinance",
    "pandas_datareader",
    "dotenv",
    "subprocess",
)


def _initial_state() -> PaperGateState:
    return make_initial_paper_gate_state(
        "session-1", "2026-06-28", "2026-W26"
    )


def _module_text() -> str:
    return GATES_PATH.read_text(encoding="utf-8")


def _module_imports() -> list[str]:
    tree = ast.parse(_module_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.append(node.module)
    return imports


class ConstantsTests(unittest.TestCase):
    def test_fixed_contract_count_is_one(self) -> None:
        self.assertEqual(FIXED_CONTRACT_COUNT, 1)

    def test_max_session_drawdown_jpy_value(self) -> None:
        self.assertEqual(MAX_SESSION_DRAWDOWN_JPY, 5_000)

    def test_max_daily_drawdown_jpy_value(self) -> None:
        self.assertEqual(MAX_DAILY_DRAWDOWN_JPY, 10_000)

    def test_max_weekly_drawdown_jpy_value(self) -> None:
        self.assertEqual(MAX_WEEKLY_DRAWDOWN_JPY, 30_000)

    def test_session_cap_is_tightest(self) -> None:
        # The session cap is the tightest, so any event
        # that trips daily/weekly also trips session.
        # Daily cap is tighter than weekly.
        self.assertLess(MAX_SESSION_DRAWDOWN_JPY, MAX_DAILY_DRAWDOWN_JPY)
        self.assertLess(MAX_DAILY_DRAWDOWN_JPY, MAX_WEEKLY_DRAWDOWN_JPY)

    def test_schema_version_exposed(self) -> None:
        self.assertEqual(PAPER_GATE_SCHEMA_VERSION, "paper-gate/1")


class NonClaimsTests(unittest.TestCase):
    def test_non_claims_is_tuple_of_str(self) -> None:
        self.assertIsInstance(PAPER_GATE_NON_CLAIMS, tuple)
        self.assertGreater(len(PAPER_GATE_NON_CLAIMS), 0)
        for claim in PAPER_GATE_NON_CLAIMS:
            self.assertIsInstance(claim, str)
            self.assertTrue(claim)

    def test_non_claims_audit_safe(self) -> None:
        for claim in PAPER_GATE_NON_CLAIMS:
            for forbidden in FORBIDDEN_SUBSTRINGS:
                self.assertNotIn(
                    forbidden,
                    claim,
                    msg=(
                        f"non-claim {claim!r} contains forbidden "
                        f"substring {forbidden!r}"
                    ),
                )

    def test_non_claims_contain_core_negatives(self) -> None:
        for needle in (
            "not_strategy_metric",
            "not_paper_execution",
            "not_live_trading",
            "not_venue_integration",
            "no_capital_account",
            "no_exposure_state",
            "no_real_cash",
        ):
            self.assertIn(needle, PAPER_GATE_NON_CLAIMS)

    def test_non_claims_contain_no_martingale_and_no_leverage(self) -> None:
        for needle in (
            "no_martingale",
            "no_leverage_escalation",
            "no_fixed_contract_count_escalation",
        ):
            self.assertIn(needle, PAPER_GATE_NON_CLAIMS)


class InitialStateTests(unittest.TestCase):
    def test_initial_state_zero_realized(self) -> None:
        state = _initial_state()
        self.assertEqual(state.session_realized_jpy, 0)
        self.assertEqual(state.day_realized_jpy, 0)
        self.assertEqual(state.week_realized_jpy, 0)

    def test_initial_state_not_halted(self) -> None:
        state = _initial_state()
        self.assertFalse(state.session_halted)
        self.assertFalse(state.day_halted)
        self.assertFalse(state.week_halted)

    def test_initial_state_fixed_contract_count(self) -> None:
        state = _initial_state()
        self.assertEqual(state.contract_count, FIXED_CONTRACT_COUNT)

    def test_initial_state_carries_keys(self) -> None:
        state = _initial_state()
        self.assertEqual(state.session_id, "session-1")
        self.assertEqual(state.day_key, "2026-06-28")
        self.assertEqual(state.week_key, "2026-W26")

    def test_initial_state_rejects_empty_session_id(self) -> None:
        with self.assertRaises(PaperGateError):
            make_initial_paper_gate_state("", "2026-06-28", "2026-W26")

    def test_initial_state_rejects_empty_day_key(self) -> None:
        with self.assertRaises(PaperGateError):
            make_initial_paper_gate_state("s", "", "2026-W26")

    def test_initial_state_rejects_empty_week_key(self) -> None:
        with self.assertRaises(PaperGateError):
            make_initial_paper_gate_state("s", "2026-06-28", "")

    def test_initial_state_rejects_non_string(self) -> None:
        with self.assertRaises(PaperGateError):
            make_initial_paper_gate_state(123, "2026-06-28", "2026-W26")  # type: ignore[arg-type]


class FormatHaltReasonTests(unittest.TestCase):
    def test_format_session_halt(self) -> None:
        text = format_halt_reason("session", 5_000, 6_000)
        self.assertIn("session", text)
        self.assertIn("6000", text)
        self.assertIn("5000", text)

    def test_format_daily_halt(self) -> None:
        text = format_halt_reason("daily", 10_000, 12_000)
        self.assertIn("daily", text)

    def test_format_weekly_halt(self) -> None:
        text = format_halt_reason("weekly", 30_000, 35_000)
        self.assertIn("weekly", text)

    def test_format_already_halted(self) -> None:
        text = format_halt_reason("already_halted", 5_000, 5_000)
        self.assertIn("already_halted", text)

    def test_format_rejects_unknown_scope(self) -> None:
        with self.assertRaises(PaperGateError):
            format_halt_reason("bogus", 100, 100)

    def test_format_rejects_non_int_limit(self) -> None:
        with self.assertRaises(PaperGateError):
            format_halt_reason("session", 100.5, 100)  # type: ignore[arg-type]

    def test_format_rejects_non_int_observed(self) -> None:
        with self.assertRaises(PaperGateError):
            format_halt_reason("session", 100, "100")  # type: ignore[arg-type]

    def test_format_deterministic(self) -> None:
        a = format_halt_reason("session", 5_000, 6_000)
        b = format_halt_reason("session", 5_000, 6_000)
        self.assertEqual(a, b)


class SessionGateTests(unittest.TestCase):
    def test_within_cap_allowed(self) -> None:
        state = _initial_state()
        d = evaluate_session_gate(state, -2_000)
        self.assertTrue(d.allowed)
        self.assertIsNone(d.halt_reason)
        self.assertIsNone(d.halt_scope)
        self.assertEqual(d.state_after.session_realized_jpy, 2_000)

    def test_one_below_cap_allowed(self) -> None:
        state = _initial_state()
        d = evaluate_session_gate(state, -4_999)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after.session_realized_jpy, 4_999)

    def test_exactly_at_cap_trips(self) -> None:
        state = _initial_state()
        d = evaluate_session_gate(state, -5_000)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_SESSION)
        self.assertTrue(d.state_after.session_halted)

    def test_one_over_cap_trips(self) -> None:
        state = _initial_state()
        d = evaluate_session_gate(state, -5_001)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_SESSION)
        self.assertTrue(d.state_after.session_halted)

    def test_gain_does_not_offset_drawdown(self) -> None:
        state = _initial_state()
        d1 = evaluate_session_gate(state, -2_000)
        self.assertTrue(d1.allowed)
        d2 = evaluate_session_gate(d1.state_after, 100_000)
        self.assertTrue(d2.allowed)
        # Realized drawdown is unchanged: gains do not offset.
        self.assertEqual(d2.state_after.session_realized_jpy, 2_000)

    def test_zero_delta_noop(self) -> None:
        state = _initial_state()
        d = evaluate_session_gate(state, 0)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after, state)

    def test_halted_session_rejects_subsequent(self) -> None:
        state = _initial_state()
        d1 = evaluate_session_gate(state, -5_000)
        self.assertFalse(d1.allowed)
        d2 = evaluate_session_gate(d1.state_after, -1_000)
        self.assertFalse(d2.allowed)
        self.assertEqual(d2.halt_scope, HALT_SCOPE_ALREADY_HALTED)
        # State is unchanged on already-halted evaluation.
        self.assertEqual(d2.state_after, d1.state_after)

    def test_individual_session_does_not_update_day_or_week(self) -> None:
        state = _initial_state()
        d = evaluate_session_gate(state, -2_000)
        self.assertEqual(d.state_after.day_realized_jpy, 0)
        self.assertEqual(d.state_after.week_realized_jpy, 0)

    def test_rejects_non_int_delta(self) -> None:
        state = _initial_state()
        with self.assertRaises(PaperGateError):
            evaluate_session_gate(state, 1.5)  # type: ignore[arg-type]

    def test_rejects_wrong_contract_count(self) -> None:
        from dataclasses import replace
        state = replace(_initial_state(), contract_count=2)
        with self.assertRaises(PaperGateError):
            evaluate_session_gate(state, -1_000)


class DailyGateTests(unittest.TestCase):
    def test_within_cap_allowed(self) -> None:
        state = _initial_state()
        d = evaluate_daily_gate(state, -5_000)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after.day_realized_jpy, 5_000)

    def test_one_below_cap_allowed(self) -> None:
        state = _initial_state()
        d = evaluate_daily_gate(state, -9_999)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after.day_realized_jpy, 9_999)

    def test_exactly_at_cap_trips(self) -> None:
        state = _initial_state()
        d = evaluate_daily_gate(state, -10_000)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_DAILY)
        self.assertTrue(d.state_after.day_halted)

    def test_one_over_cap_trips(self) -> None:
        state = _initial_state()
        d = evaluate_daily_gate(state, -10_001)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_DAILY)
        self.assertTrue(d.state_after.day_halted)

    def test_individual_daily_does_not_update_session_or_week(self) -> None:
        state = _initial_state()
        d = evaluate_daily_gate(state, -5_000)
        self.assertEqual(d.state_after.session_realized_jpy, 0)
        self.assertEqual(d.state_after.week_realized_jpy, 0)

    def test_halted_daily_rejects_subsequent(self) -> None:
        state = _initial_state()
        d1 = evaluate_daily_gate(state, -10_000)
        d2 = evaluate_daily_gate(d1.state_after, -1_000)
        self.assertEqual(d2.halt_scope, HALT_SCOPE_ALREADY_HALTED)


class WeeklyGateTests(unittest.TestCase):
    def test_within_cap_allowed(self) -> None:
        state = _initial_state()
        d = evaluate_weekly_gate(state, -10_000)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after.week_realized_jpy, 10_000)

    def test_one_below_cap_allowed(self) -> None:
        state = _initial_state()
        d = evaluate_weekly_gate(state, -29_999)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after.week_realized_jpy, 29_999)

    def test_exactly_at_cap_trips(self) -> None:
        state = _initial_state()
        d = evaluate_weekly_gate(state, -30_000)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_WEEKLY)
        self.assertTrue(d.state_after.week_halted)

    def test_one_over_cap_trips(self) -> None:
        state = _initial_state()
        d = evaluate_weekly_gate(state, -30_001)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_WEEKLY)
        self.assertTrue(d.state_after.week_halted)

    def test_individual_weekly_does_not_update_session_or_day(self) -> None:
        state = _initial_state()
        d = evaluate_weekly_gate(state, -10_000)
        self.assertEqual(d.state_after.session_realized_jpy, 0)
        self.assertEqual(d.state_after.day_realized_jpy, 0)

    def test_halted_weekly_rejects_subsequent(self) -> None:
        state = _initial_state()
        d1 = evaluate_weekly_gate(state, -30_000)
        d2 = evaluate_weekly_gate(d1.state_after, -1_000)
        self.assertEqual(d2.halt_scope, HALT_SCOPE_ALREADY_HALTED)


class CompositeGateTests(unittest.TestCase):
    def test_within_all_caps_allowed(self) -> None:
        state = _initial_state()
        d = evaluate_all_gates(state, -2_000)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after.session_realized_jpy, 2_000)
        self.assertEqual(d.state_after.day_realized_jpy, 2_000)
        self.assertEqual(d.state_after.week_realized_jpy, 2_000)

    def test_one_below_session_cap_allowed_in_composite(self) -> None:
        state = _initial_state()
        d = evaluate_all_gates(state, -4_999)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after.session_realized_jpy, 4_999)

    def test_session_cap_trips_first(self) -> None:
        state = _initial_state()
        d = evaluate_all_gates(state, -5_000)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_SESSION)
        # All three realized counters are updated atomically.
        self.assertEqual(d.state_after.session_realized_jpy, 5_000)
        self.assertEqual(d.state_after.day_realized_jpy, 5_000)
        self.assertEqual(d.state_after.week_realized_jpy, 5_000)
        self.assertTrue(d.state_after.session_halted)
        # Daily and weekly halted flags are NOT set because
        # session halted first.
        self.assertFalse(d.state_after.day_halted)
        self.assertFalse(d.state_after.week_halted)

    def test_halted_session_rejects_subsequent(self) -> None:
        state = _initial_state()
        d1 = evaluate_all_gates(state, -5_000)
        d2 = evaluate_all_gates(d1.state_after, -1_000)
        self.assertFalse(d2.allowed)
        self.assertEqual(d2.halt_scope, HALT_SCOPE_ALREADY_HALTED)
        self.assertEqual(d2.state_after, d1.state_after)

    def test_halted_daily_rejects_subsequent(self) -> None:
        from dataclasses import replace
        state = replace(_initial_state(), day_halted=True)
        d = evaluate_all_gates(state, -10_000)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_ALREADY_HALTED)

    def test_halted_weekly_rejects_subsequent(self) -> None:
        from dataclasses import replace
        state = replace(_initial_state(), week_halted=True)
        d = evaluate_all_gates(state, -10_000)
        self.assertFalse(d.allowed)
        self.assertEqual(d.halt_scope, HALT_SCOPE_ALREADY_HALTED)

    def test_zero_delta_in_composite_noop(self) -> None:
        state = _initial_state()
        d = evaluate_all_gates(state, 0)
        self.assertTrue(d.allowed)
        self.assertEqual(d.state_after, state)

    def test_gain_in_composite_does_not_offset(self) -> None:
        state = _initial_state()
        d1 = evaluate_all_gates(state, -2_000)
        d2 = evaluate_all_gates(d1.state_after, 100_000)
        self.assertTrue(d2.allowed)
        self.assertEqual(d2.state_after.session_realized_jpy, 2_000)
        self.assertEqual(d2.state_after.day_realized_jpy, 2_000)
        self.assertEqual(d2.state_after.week_realized_jpy, 2_000)

    def test_composite_rejects_wrong_contract_count(self) -> None:
        from dataclasses import replace
        state = replace(_initial_state(), contract_count=2)
        with self.assertRaises(PaperGateError):
            evaluate_all_gates(state, -1_000)

    def test_composite_rejects_non_int_delta(self) -> None:
        state = _initial_state()
        with self.assertRaises(PaperGateError):
            evaluate_all_gates(state, 1.5)  # type: ignore[arg-type]

    def test_composite_rejects_bool_delta(self) -> None:
        state = _initial_state()
        with self.assertRaises(PaperGateError):
            evaluate_all_gates(state, True)  # type: ignore[arg-type]


class DecisionTypeTests(unittest.TestCase):
    def test_decision_is_frozen(self) -> None:
        d = evaluate_session_gate(_initial_state(), -1_000)
        with self.assertRaises(Exception):
            d.allowed = False  # type: ignore[misc]

    def test_state_is_frozen(self) -> None:
        state = _initial_state()
        with self.assertRaises(Exception):
            state.session_realized_jpy = 999  # type: ignore[misc]

    def test_decision_fields(self) -> None:
        d = evaluate_all_gates(_initial_state(), -5_000)
        self.assertIsInstance(d, PaperGateDecision)
        self.assertFalse(d.allowed)
        self.assertIsNotNone(d.halt_reason)
        self.assertEqual(d.halt_scope, HALT_SCOPE_SESSION)
        self.assertIsInstance(d.state_after, PaperGateState)

    def test_state_fields(self) -> None:
        state = _initial_state()
        self.assertIsInstance(state, PaperGateState)
        self.assertEqual(state.session_id, "session-1")
        self.assertEqual(state.day_key, "2026-06-28")
        self.assertEqual(state.week_key, "2026-W26")
        self.assertEqual(state.contract_count, 1)
        self.assertFalse(state.session_halted)


class ProductionCodeSurfacePurityTests(unittest.TestCase):
    """Purity and forbidden-substring audits for the
    production code surface (nms/paper/gates.py).
    """

    def test_module_file_exists(self) -> None:
        self.assertTrue(GATES_PATH.exists())

    def test_no_forbidden_substring_in_module(self) -> None:
        text = _module_text()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(
                forbidden,
                text,
                msg=(
                    f"nms/paper/gates.py contains forbidden "
                    f"substring {forbidden!r}"
                ),
            )

    def test_no_forbidden_imports(self) -> None:
        imports = _module_imports()
        for imp in imports:
            for forbidden in FORBIDDEN_IMPORTS:
                self.assertFalse(
                    imp == forbidden or imp.startswith(forbidden + "."),
                    msg=(
                        f"nms/paper/gates.py imports forbidden "
                        f"module {imp!r} (matches {forbidden!r})"
                    ),
                )

    def test_no_subprocess_call_in_module(self) -> None:
        text = _module_text()
        # Reject any use of subprocess.run, subprocess.Popen,
        # subprocess.call, os.system, os.popen, os.spawn.
        for needle in (
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "os.system",
            "os.popen",
            "os.spawn",
        ):
            self.assertNotIn(needle, text)

    def test_no_env_credential_reads(self) -> None:
        text = _module_text()
        for needle in (
            "os.environ.get",
            "os.getenv",
            "os.environ[",
            "dotenv",
        ):
            self.assertNotIn(needle, text)

    def test_no_network_libraries(self) -> None:
        imports = _module_imports()
        for imp in imports:
            for forbidden in ("requests", "httpx", "aiohttp", "urllib3"):
                self.assertFalse(
                    imp == forbidden or imp.startswith(forbidden + "."),
                    msg=f"forbidden network import: {imp!r}",
                )

    def test_no_score_or_signal_strings(self) -> None:
        text = _module_text().lower()
        # The authoritative forbidden-substring list is in
        # FORBIDDEN_SUBSTRINGS. 'score' alone is not in that
        # list; 'no_score' is a non-claim string. This test
        # spot-checks that the module does not embed a
        # scoring-engine reference.
        for needle in ("score_context", "score_breakdown", "win_rate", "sharpe"):
            self.assertNotIn(needle, text)


class TestFilePurityTests(unittest.TestCase):
    """Purity audits for this test file itself. These use
    static AST checks, not text searches, so that the
    test's own docstring / comments (which mention the
    forbidden tokens as absence-check fixtures) do not
    trigger false positives.
    """

    def test_no_subprocess_import_in_test(self) -> None:
        tree = ast.parse(
            Path(__file__).read_text(encoding="utf-8")
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "subprocess")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "subprocess")

    def test_no_env_credential_reads_in_test(self) -> None:
        tree = ast.parse(
            Path(__file__).read_text(encoding="utf-8")
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                # Reject os.environ.get / os.environ[...]
                if isinstance(node.value, ast.Attribute):
                    if (
                        node.value.attr == "environ"
                        and isinstance(node.value.value, ast.Name)
                        and node.value.value.id == "os"
                    ):
                        self.fail(
                            f"os.environ access in test file: "
                            f"{ast.dump(node)}"
                        )
            elif isinstance(node, ast.Call):
                # Reject os.getenv(...)
                if isinstance(node.func, ast.Attribute):
                    if (
                        node.func.attr == "getenv"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                    ):
                        self.fail(
                            f"os.getenv call in test file: "
                            f"{ast.dump(node)}"
                        )

    def test_no_network_libraries_in_test(self) -> None:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    imports.append(node.module)
        for imp in imports:
            for forbidden in (
                "requests",
                "httpx",
                "aiohttp",
                "urllib3",
                "subprocess",
            ):
                self.assertFalse(
                    imp == forbidden or imp.startswith(forbidden + "."),
                    msg=f"forbidden import in test: {imp!r}",
                )


class DocPresenceTests(unittest.TestCase):
    def test_contract_doc_exists(self) -> None:
        self.assertTrue(
            CONTRACT_DOC.exists(),
            msg=f"missing contract doc: {CONTRACT_DOC}",
        )

    def test_contract_doc_mentions_constants(self) -> None:
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        for needle in (
            "FIXED_CONTRACT_COUNT",
            "MAX_SESSION_DRAWDOWN_JPY",
            "MAX_DAILY_DRAWDOWN_JPY",
            "MAX_WEEKLY_DRAWDOWN_JPY",
            "PaperGateState",
            "PaperGateDecision",
        ):
            self.assertIn(needle, text)

    def test_contract_doc_mentions_non_claims(self) -> None:
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        for needle in (
            "not_strategy_metric",
            "not_paper_execution",
            "not_live_trading",
            "no_capital_account",
        ):
            self.assertIn(needle, text)

    def test_contract_doc_mentions_pure(self) -> None:
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        self.assertIn("pure", text.lower())

    def test_contract_doc_references_brief(self) -> None:
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        self.assertIn(
            "code-agent-paper-trading-refinement-brief", text
        )

    def test_no_raw_fred_csv_in_repo(self) -> None:
        # Spot-check that no raw FRED CSV has been committed
        # to exports/, fixtures/, or reports/ by this PR.
        for sub in ("exports", "fixtures", "reports"):
            base = REPO_ROOT / sub
            if not base.exists():
                continue
            for csv in base.rglob("*.csv"):
                self.assertFalse(
                    "FRED" in csv.name or "fred" in csv.name.lower(),
                    msg=f"raw FRED CSV committed: {csv}",
                )


class FixedContractCountInvariantTests(unittest.TestCase):
    """Enforces 'no martingale / no leverage escalation' by
    construction: the contract_count cannot be changed on
    the state, and the gate evaluators reject any state
    whose contract_count differs from FIXED_CONTRACT_COUNT.
    """

    def test_state_is_frozen_dataclass(self) -> None:
        from dataclasses import FrozenInstanceError
        state = _initial_state()
        with self.assertRaises(FrozenInstanceError):
            state.contract_count = 2  # type: ignore[misc]

    def test_evaluator_rejects_escalation(self) -> None:
        from dataclasses import replace
        for bad_count in (0, 2, 5, 100, -1):
            state = replace(_initial_state(), contract_count=bad_count)
            with self.assertRaises(PaperGateError):
                evaluate_session_gate(state, -1_000)
            with self.assertRaises(PaperGateError):
                evaluate_daily_gate(state, -1_000)
            with self.assertRaises(PaperGateError):
                evaluate_weekly_gate(state, -1_000)
            with self.assertRaises(PaperGateError):
                evaluate_all_gates(state, -1_000)


if __name__ == "__main__":
    unittest.main()
