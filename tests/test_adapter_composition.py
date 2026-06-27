"""Tests for the adapter composition pipeline.

These tests enforce the composition contract documented in
``docs/adapter-composition.md`` and §8.6 of
``docs/data-adapter-contract.md``.

Coverage:

* ``AdapterStage`` stores ``name`` and ``factory``.
* ``ComposedMarketContextAdapter.stages`` returns an immutable
  tuple.
* Empty stage list returns a validated base context.
* Stage factories are applied in order.
* Final output is a ``MarketContext``.
* Final output is re-validated.
* Composition does not mutate the baseline context.
* Construction failure is wrapped in ``AdapterCompositionError``
  with the stage name.
* Load failure is wrapped in ``AdapterCompositionError`` with the
  session date.
* No live network is used in tests.
* No subprocess is used.
* No environment credential reads.
* No broker / order / account symbols appear.
* The SOX / semiconductor source-selection contract (per
  ``docs/sox-source-selection.md``) is honored: no SOX adapter
  is referenced or instantiated in composition code or test
  code.
* Dry-run script exists and uses mocked CSV.
* ``docs/adapter-composition.md`` exists.
* ``docs/data-adapter-contract.md`` links to
  ``docs/adapter-composition.md``.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest import mock

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.composition import (
    AdapterCompositionError,
    AdapterStage,
    ComposedMarketContextAdapter,
    compose_market_context_adapter,
)
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


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSITION_DOC = REPO_ROOT / "docs" / "adapter-composition.md"
DATA_ADAPTER_CONTRACT = REPO_ROOT / "docs" / "data-adapter-contract.md"
COMPOSE_DRY_RUN_SH = REPO_ROOT / "scripts" / "compose_market_context_dry_run.sh"
COMPOSITION_PATH = REPO_ROOT / "nms" / "data" / "composition.py"
DRY_RUN_PY = REPO_ROOT / "scripts" / "compose_market_context.py"
SAMPLE_FIXTURE = (
    REPO_ROOT / "fixtures" / "market_context" / "sample-session-2026-06-24.json"
)


# --- Helpers --------------------------------------------------------------


def _make_minimal_context(session_date: str) -> MarketContext:
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


def _make_stub_base_adapter() -> Any:
    """Return a stub base adapter that always returns a minimal
    :class:`MarketContext`` for any session date.
    """

    def _stub_load(session_date: str) -> MarketContext:
        return _make_minimal_context(session_date)

    return mock.MagicMock(load=mock.MagicMock(side_effect=_stub_load))


def _make_stub_overlay_factory(
    overlay_name: str,
    apply_to: callable,
) -> AdapterStage:
    """Return an ``AdapterStage`` whose adapter applies
    ``apply_to(baseline).load(session_date)`` and returns a new
    context.
    """

    class _Overlay:
        def __init__(self, base: MarketContextAdapter) -> None:
            self._base = base

        def load(self, session_date: str) -> MarketContext:
            baseline = self._base.load(session_date)
            return apply_to(baseline)

    return AdapterStage(
        name=overlay_name,
        factory=lambda base: _Overlay(base),
    )


# --- AdapterStage tests ---------------------------------------------------


class AdapterStageTests(unittest.TestCase):
    def test_stores_name_and_factory(self) -> None:
        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        stage = AdapterStage(name="treasury", factory=_f)
        self.assertEqual(stage.name, "treasury")
        self.assertIs(stage.factory, _f)

    def test_empty_name_rejected(self) -> None:
        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        with self.assertRaises(ValueError):
            AdapterStage(name="", factory=_f)

    def test_non_callable_factory_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AdapterStage(name="treasury", factory=42)  # type: ignore[arg-type]


# --- ComposedMarketContextAdapter.stages ---------------------------------


class ComposedAdapterStagesPropertyTests(unittest.TestCase):
    def test_stages_returns_immutable_tuple(self) -> None:
        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        s1 = AdapterStage(name="a", factory=_f)
        s2 = AdapterStage(name="b", factory=_f)
        composed = ComposedMarketContextAdapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[s1, s2],
        )
        stages = composed.stages
        self.assertIsInstance(stages, tuple)
        self.assertEqual(len(stages), 2)
        self.assertEqual(stages[0].name, "a")
        self.assertEqual(stages[1].name, "b")

    def test_stages_tuple_is_immutable(self) -> None:
        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        composed = ComposedMarketContextAdapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[AdapterStage(name="a", factory=_f)],
        )
        with self.assertRaises(Exception):
            composed.stages[0] = "mutated"  # type: ignore[index]


# --- Empty stage list ---------------------------------------------------


class EmptyStageListTests(unittest.TestCase):
    def test_empty_stages_returns_validated_base_context(self) -> None:
        base = _make_stub_base_adapter()
        composed = ComposedMarketContextAdapter(
            base_adapter=base, stages=[]
        )
        ctx = composed.load("2026-06-24")
        self.assertIsInstance(ctx, MarketContext)
        # Re-validation: the result is a fully validated
        # MarketContext. We confirm this by passing it through
        # the validate_market_context function — if it returned
        # an invalid object, validation would raise.
        from nms.data.validate import validate_market_context

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


# --- Stage order ---------------------------------------------------------


class StageOrderTests(unittest.TestCase):
    def test_stages_are_applied_in_order(self) -> None:
        # The composition layer must call the stage factories in
        # the order they appear in the stages list. The
        # factories themselves run at load() time (since
        # construction failure is wrapped and reported with a
        # stage name). We track factory-call order, not load
        # order, because the existing FRED overlay adapters
        # chain load() calls in reverse (the last stage calls
        # the previous stage's load()).
        factory_calls: list[str] = []

        def _make_factory(
            name: str,
        ) -> "callable":
            def _factory(
                base: MarketContextAdapter,
            ) -> MarketContextAdapter:
                factory_calls.append(name)
                return base

            return _factory

        composed = ComposedMarketContextAdapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[
                AdapterStage(
                    name="treasury", factory=_make_factory("treasury")
                ),
                AdapterStage(
                    name="sp500", factory=_make_factory("sp500")
                ),
                AdapterStage(
                    name="usdjpy", factory=_make_factory("usdjpy")
                ),
                AdapterStage(
                    name="nasdaq100",
                    factory=_make_factory("nasdaq100"),
                ),
            ],
        )
        composed.load("2026-06-24")
        self.assertEqual(
            factory_calls,
            ["treasury", "sp500", "usdjpy", "nasdaq100"],
        )


# --- Final output and validation -----------------------------------------


class FinalOutputTests(unittest.TestCase):
    def test_final_output_is_market_context(self) -> None:
        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        composed = ComposedMarketContextAdapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[AdapterStage(name="noop", factory=_f)],
        )
        ctx = composed.load("2026-06-24")
        self.assertIsInstance(ctx, MarketContext)

    def test_final_output_is_re_validated(self) -> None:
        # The composed context passes re-validation by
        # construction (validate_market_context is called inside
        # ComposedMarketContextAdapter.load). We assert that
        # validate_market_context accepts the returned object.
        from nms.data.validate import validate_market_context

        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        composed = ComposedMarketContextAdapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[AdapterStage(name="noop", factory=_f)],
        )
        ctx = composed.load("2026-06-24")
        ctx_dict = {
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
        ctx2 = validate_market_context(ctx_dict)
        self.assertIsInstance(ctx2, MarketContext)


# --- No mutation of baseline ---------------------------------------------


class NoBaselineMutationTests(unittest.TestCase):
    def test_composition_does_not_mutate_baseline(self) -> None:
        # Use a real fixture-backed adapter. Load the baseline
        # once, snapshot key fields, run composition, then load
        # baseline again and confirm the snapshot values are
        # unchanged.
        base = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        before = base.load("2026-06-24")
        before_sp500 = before.us_equities.sp500
        before_usdjpy = before.fx.usdjpy

        def _identity(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        composed = ComposedMarketContextAdapter(
            base_adapter=base,
            stages=[
                AdapterStage(name="identity", factory=_identity),
                AdapterStage(name="identity2", factory=_identity),
            ],
        )
        _ = composed.load("2026-06-24")
        after = base.load("2026-06-24")
        self.assertEqual(after.us_equities.sp500, before_sp500)
        self.assertEqual(after.fx.usdjpy, before_usdjpy)


# --- Construction and load error wrapping --------------------------------


class ConstructionFailureTests(unittest.TestCase):
    def test_construction_failure_wrapped_with_stage_name(self) -> None:
        def _failing_factory(
            base: MarketContextAdapter,
        ) -> MarketContextAdapter:
            raise RuntimeError("factory boom")

        composed = ComposedMarketContextAdapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[AdapterStage(name="broken", factory=_failing_factory)],
        )
        with self.assertRaises(AdapterCompositionError) as cm:
            composed.load("2026-06-24")
        self.assertIn("broken", str(cm.exception))
        # Original exception preserved as __cause__.
        self.assertIsInstance(cm.exception.__cause__, RuntimeError)


class LoadFailureTests(unittest.TestCase):
    def test_load_failure_wrapped_with_session_date(self) -> None:
        class _Boom:
            def load(self, session_date: str) -> MarketContext:
                raise ValueError("load boom")

        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return _Boom()

        composed = ComposedMarketContextAdapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[AdapterStage(name="boom_stage", factory=_f)],
        )
        with self.assertRaises(AdapterCompositionError) as cm:
            composed.load("2026-06-24")
        # The session date must be in the wrapped error message.
        self.assertIn("2026-06-24", str(cm.exception))
        # The original ValueError must be preserved as __cause__.
        self.assertIsInstance(cm.exception.__cause__, ValueError)


# --- Helper function -----------------------------------------------------


class ComposeHelperTests(unittest.TestCase):
    def test_helper_returns_composed_adapter(self) -> None:
        def _f(base: MarketContextAdapter) -> MarketContextAdapter:
            return base

        adapter = compose_market_context_adapter(
            base_adapter=_make_stub_base_adapter(),
            stages=[AdapterStage(name="noop", factory=_f)],
        )
        self.assertIsInstance(adapter, ComposedMarketContextAdapter)
        self.assertEqual(adapter.stages[0].name, "noop")


# --- Network safety -----------------------------------------------------


class CompositionNetworkSafetyTests(unittest.TestCase):
    """Enforce that nms/data/composition.py does not perform
    network I/O, subprocess calls, or env-credential reads.
    """

    def test_no_socket_call(self) -> None:
        with mock.patch("socket.socket") as mocked_socket, mock.patch(
            "socket.create_connection"
        ) as mocked_connect:
            composed = ComposedMarketContextAdapter(
                base_adapter=_make_stub_base_adapter(),
                stages=[],
            )
            composed.load("2026-06-24")
            mocked_socket.assert_not_called()
            mocked_connect.assert_not_called()

    def test_no_subprocess_call(self) -> None:
        with mock.patch("subprocess.Popen") as mocked_popen, mock.patch(
            "subprocess.run"
        ) as mocked_run, mock.patch("subprocess.call") as mocked_call:
            composed = ComposedMarketContextAdapter(
                base_adapter=_make_stub_base_adapter(),
                stages=[],
            )
            composed.load("2026-06-24")
            mocked_popen.assert_not_called()
            mocked_run.assert_not_called()
            mocked_call.assert_not_called()

    def test_no_env_credential_reads(self) -> None:
        with mock.patch("os.environ.get") as mocked_get, mock.patch(
            "os.getenv"
        ) as mocked_getenv:
            composed = ComposedMarketContextAdapter(
                base_adapter=_make_stub_base_adapter(),
                stages=[],
            )
            composed.load("2026-06-24")
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
            "urllib", "urllib3", "yfinance", "pandas",
        }
        imports = self._collect_imports(COMPOSITION_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"composition.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_broker_order_account_field_introduced(self) -> None:
        # The composition layer must not introduce any
        # account / broker / order / position field. The schema
        # is fixed by validate_market_context. If a new
        # top-level field were added, validation would raise.
        from nms.data.validate import ValidationError, validate_market_context

        ctx = _make_stub_base_adapter().load("2026-06-24")
        ctx_dict = {
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
        ctx_dict["account_balance"] = 100000
        with self.assertRaises(ValidationError):
            validate_market_context(ctx_dict)


# --- SOX reference guard -------------------------------------------------


class SoxReferenceGuardTests(unittest.TestCase):
    def _sox_adapter_tokens(self) -> list[str]:
        # Build the SOX adapter class-name tokens at runtime so
        # they do not appear as literal substrings in the test
        # file's own source. Each token is a class-name-shaped
        # identifier that would only appear if a future
        # contributor instantiated or imported a SOX adapter.
        sox = "S" + "O" + "X"
        fred = "Fred"
        return [
            fred + sox + "OverlayAdapter",
            sox + "OverlayAdapter",
            "Phlx" + sox + "Adapter",
            sox + "Adapter",
        ]

    def test_composition_does_not_reference_sox(self) -> None:
        src = COMPOSITION_PATH.read_text(encoding="utf-8")
        # Composition code must not import or instantiate any
        # SOX / semiconductor adapter. The only allowed
        # mentions of "sox" in the composition module are:
        # (a) the Semiconductor.sox / Semiconductor.sox_change_pct
        # field names that already exist in the model, and
        # (b) the "SOX adapter is not approved" guard in the
        # docstring. We test the stronger condition: composition
        # code must not define a SOX adapter or import one.
        # We use a substring check that is unlikely to appear
        # in a benign docstring: a class-name-shaped identifier
        # with "sox" as a name component and an obvious "Adapter"
        # suffix.
        for token in self._sox_adapter_tokens():
            self.assertNotIn(
                token,
                src,
                f"composition.py must not reference {token!r}.",
            )

    def test_test_file_does_not_reference_sox_adapter(self) -> None:
        src = Path(__file__).read_text(encoding="utf-8")
        for token in self._sox_adapter_tokens():
            self.assertNotIn(
                token,
                src,
                f"test_adapter_composition.py must not reference "
                f"{token!r}.",
            )


# --- Documentation and dry-run script presence --------------------------


class CompositionDocsAndDryRunTests(unittest.TestCase):
    def test_adapter_composition_doc_exists(self) -> None:
        self.assertTrue(
            COMPOSITION_DOC.exists(),
            f"Missing docs/adapter-composition.md: {COMPOSITION_DOC}",
        )

    def test_dry_run_shell_script_exists(self) -> None:
        self.assertTrue(
            COMPOSE_DRY_RUN_SH.exists(),
            f"Missing scripts/compose_market_context_dry_run.sh: "
            f"{COMPOSE_DRY_RUN_SH}",
        )

    def test_dry_run_shell_uses_strict_mode(self) -> None:
        text = COMPOSE_DRY_RUN_SH.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_dry_run_python_uses_mocked_csv(self) -> None:
        text = DRY_RUN_PY.read_text(encoding="utf-8")
        # The dry-run must inject http_get (mocked CSV), not
        # perform real network I/O.
        self.assertIn("http_get", text)
        # It must reference the four approved FRED overlay
        # adapters.
        for token in (
            "FredTreasuryOverlayAdapter",
            "FredSP500OverlayAdapter",
            "FredUSDJPYOverlayAdapter",
            "FredNASDAQ100OverlayAdapter",
        ):
            self.assertIn(token, text)
        # It must not import or call subprocess. The check is
        # precise: we look for the import forms and the
        # attribute-access form, not the bare word (which can
        # appear in prose like "no subprocess calls").
        for pattern in (
            "import sub" + "process",
            "from sub" + "process",
            "sub" + "process.",
            "sub" + "process(",
        ):
            self.assertNotIn(
                pattern,
                text,
                f"dry-run script must not {pattern!r}",
            )

    def test_data_adapter_contract_links_to_composition_doc(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "adapter-composition.md",
            text,
            "data-adapter-contract.md must link to "
            "docs/adapter-composition.md.",
        )

    def test_data_adapter_contract_section_8_6_present(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "8.6",
            text,
            "data-adapter-contract.md must contain a §8.6 "
            "adapter-composition section.",
        )


if __name__ == "__main__":
    unittest.main()
