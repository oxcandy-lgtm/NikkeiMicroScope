"""Tests for the composed MarketContext JSON export.

These tests enforce the JSON export contract documented in
``docs/market-context-export.md`` and §8.7 of
``docs/data-adapter-contract.md``.

Coverage:

* ``market_context_to_ordered_dict`` returns a plain dict.
* ``market_context_to_json_text`` returns deterministic JSON
  text.
* JSON text ends with a newline.
* JSON text validates with ``json.loads``.
* Export re-validates the input context.
* Write creates the parent directory.
* Write refuses overwrite by default.
* Write allows overwrite only with ``allow_overwrite=True``.
* Write returns the path it wrote to.
* Output contains the expected top-level keys.
* No subprocess import or call in production code
  (static AST check).
* No environment credential reads in production code
  (static AST check).
* No requests / httpx / aiohttp / yfinance / pandas in
  production code (static AST check).
* No SOX adapter reference in production code.
* No broker / order / account field introduced.
* No raw FRED CSV is committed by this PR.
* Dry-run script exists; shell wrapper exists; docs exist.
* ``docs/data-adapter-contract.md`` links to
  ``docs/market-context-export.md``.
* If a committed example JSON exists under ``exports/``,
  verify it is under ``exports/dry-run/`` and contains a
  synthetic marker (a top-level key called
  ``"synthetic"`` or ``"_dry_run_meta"``).
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any

from nms.data.adapters import FixtureMarketContextAdapter
from nms.data.export import (
    market_context_to_json_text,
    market_context_to_ordered_dict,
    write_market_context_json,
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
from nms.data.validate import (
    ValidationError,
    validate_market_context,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DOC = REPO_ROOT / "docs" / "market-context-export.md"
DATA_ADAPTER_CONTRACT = REPO_ROOT / "docs" / "data-adapter-contract.md"
EXPORT_DRY_RUN_SH = (
    REPO_ROOT / "scripts" / "export_composed_market_context_dry_run.sh"
)
EXPORT_PATH = REPO_ROOT / "nms" / "data" / "export.py"
DRY_RUN_PY = (
    REPO_ROOT / "scripts" / "export_composed_market_context.py"
)
EXPORTS_DIR = REPO_ROOT / "exports"


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


def _real_fixture_context() -> MarketContext:
    return FixtureMarketContextAdapter(
        base_path=REPO_ROOT / "fixtures" / "market_context"
    ).load("2026-06-24")


# --- dict / JSON shape tests ----------------------------------------------


class ExportShapeTests(unittest.TestCase):
    def test_to_ordered_dict_returns_plain_dict(self) -> None:
        ctx = _make_minimal_context("2026-06-24")
        d = market_context_to_ordered_dict(ctx)
        self.assertIsInstance(d, dict)
        # Top-level keys are the documented set.
        self.assertIn("session_date", d)
        self.assertIn("us_equities", d)
        self.assertIn("us_yields", d)
        self.assertIn("fx", d)
        self.assertIn("semiconductor", d)

    def test_to_json_text_returns_deterministic_text(self) -> None:
        ctx = _real_fixture_context()
        text1 = market_context_to_json_text(ctx)
        text2 = market_context_to_json_text(ctx)
        # Determinism: same input -> same output.
        self.assertEqual(text1, text2)
        # JSON validation.
        parsed = json.loads(text1)
        self.assertEqual(parsed["session_date"], "2026-06-24")

    def test_to_json_text_ends_with_newline(self) -> None:
        ctx = _real_fixture_context()
        text = market_context_to_json_text(ctx)
        self.assertTrue(text.endswith("\n"))

    def test_to_json_text_validates_with_json_loads(self) -> None:
        ctx = _make_minimal_context("2026-06-24")
        text = market_context_to_json_text(ctx)
        parsed = json.loads(text)
        self.assertEqual(parsed["session_date"], "2026-06-24")
        self.assertEqual(parsed["timezone"], "Asia/Tokyo")

    def test_to_json_text_uses_utf8_no_ascii_escape(self) -> None:
        # The output must not contain \uXXXX escapes for ASCII
        # characters. ensure_ascii=False implies that
        # non-ASCII characters (if any) are kept as-is.
        ctx = _make_minimal_context("2026-06-24")
        text = market_context_to_json_text(ctx)
        # No \uXXXX escapes for ASCII characters in the
        # current schema (no non-ASCII in the data).
        self.assertNotIn("\\u00", text)

    def test_to_json_text_keys_are_sorted(self) -> None:
        ctx = _make_minimal_context("2026-06-24")
        text = market_context_to_json_text(ctx)
        # sort_keys=True means the top-level keys appear in
        # alphabetical order. We assert by checking that the
        # first key in the text body is "fx" (alphabetically
        # first among fx / semiconductor / session_date /
        # timezone / us_equities / us_yields / ...).
        # We find the first key by looking for a line like
        # '"fx":'.
        first_key_line = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('"') and ":" in stripped:
                first_key_line = stripped.split(":", 1)[0]
                break
        self.assertIsNotNone(first_key_line)
        self.assertEqual(first_key_line, '"economic_event_risk"')


# --- re-validation tests -------------------------------------------------


class ExportReValidationTests(unittest.TestCase):
    def test_to_ordered_dict_re_validates(self) -> None:
        # If re-validation raises, the export layer must
        # surface the error before returning.
        ctx = _make_minimal_context("2026-06-24")
        # Mutate the context's __dict__ to introduce an
        # invalid field. Since UsEquities is frozen we have
        # to use object.__setattr__ to bypass. (We restore
        # the original value in finally.)
        original = ctx.us_equities
        try:
            object.__setattr__(
                ctx.us_equities, "sp500", "not-a-float"
            )
            with self.assertRaises(ValidationError):
                market_context_to_ordered_dict(ctx)
        finally:
            object.__setattr__(ctx, "us_equities", original)

    def test_to_json_text_re_validates(self) -> None:
        ctx = _make_minimal_context("2026-06-24")
        original = ctx.us_equities
        try:
            object.__setattr__(
                ctx.us_equities, "sp500", "not-a-float"
            )
            with self.assertRaises(ValidationError):
                market_context_to_json_text(ctx)
        finally:
            object.__setattr__(ctx, "us_equities", original)


# --- write tests ---------------------------------------------------------


class WriteJsonTests(unittest.TestCase):
    def test_write_creates_parent_directory(self) -> None:
        ctx = _real_fixture_context()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "sub" / "out.json"
            self.assertFalse(out.parent.exists())
            result = write_market_context_json(ctx, out)
            self.assertTrue(out.exists())
            self.assertEqual(result, out)
            self.assertTrue(out.parent.exists())

    def test_write_refuses_overwrite_by_default(self) -> None:
        ctx = _real_fixture_context()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            write_market_context_json(ctx, out)
            with self.assertRaises(FileExistsError):
                write_market_context_json(ctx, out)

    def test_write_allows_overwrite_with_flag(self) -> None:
        ctx = _real_fixture_context()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            write_market_context_json(ctx, out)
            # Should not raise.
            write_market_context_json(ctx, out, allow_overwrite=True)
            self.assertTrue(out.exists())
            # The content is still valid JSON.
            parsed = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(parsed["session_date"], "2026-06-24")

    def test_write_returns_path(self) -> None:
        ctx = _real_fixture_context()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            result = write_market_context_json(ctx, out)
            self.assertEqual(result, out)

    def test_write_output_contains_expected_top_level_keys(self) -> None:
        ctx = _real_fixture_context()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            write_market_context_json(ctx, out)
            parsed = json.loads(out.read_text(encoding="utf-8"))
            for key in (
                "session_date",
                "timezone",
                "us_equities",
                "us_yields",
                "fx",
                "semiconductor",
                "nikkei_night_session",
                "previous_day",
                "economic_event_risk",
                "intraday_range",
                "volatility_context",
            ):
                self.assertIn(key, parsed)

    def test_write_output_text_ends_with_newline(self) -> None:
        ctx = _real_fixture_context()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            write_market_context_json(ctx, out)
            text = out.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))


# --- Static AST purity checks --------------------------------------------


def _module_has_subprocess_use(py_path: Path) -> bool:
    """Static check: does the module import subprocess or
    access ``subprocess.<attr>``?
    """
    tree = ast.parse(
        py_path.read_text(encoding="utf-8"), filename=str(py_path)
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "subprocess":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "subprocess":
                return True
        elif isinstance(node, ast.Attribute) and isinstance(
            node.value, ast.Name
        ):
            if node.value.id == "subprocess":
                return True
    return False


def _module_has_os_env_credential_read(py_path: Path) -> bool:
    """Static check: does the module call ``os.environ.get``
    or ``os.getenv``?
    """
    tree = ast.parse(
        py_path.read_text(encoding="utf-8"), filename=str(py_path)
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and node.value.attr == "environ"
            and node.attr == "get"
        ):
            return True
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "getenv"
        ):
            return True
    return False


def _collect_imports(py_path: Path) -> set[str]:
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


class ExportPurityTests(unittest.TestCase):
    def test_no_subprocess_import_or_call_in_export_module(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(EXPORT_PATH),
            f"{EXPORT_PATH} imports or accesses subprocess.",
        )

    def test_no_env_credential_reads_in_export_module(self) -> None:
        self.assertFalse(
            _module_has_os_env_credential_read(EXPORT_PATH),
            f"{EXPORT_PATH} reads environment credentials.",
        )

    def test_no_subprocess_import_or_call_in_dry_run(self) -> None:
        # The dry-run script is allowed to have a docstring
        # that says "no subprocess calls". We test the actual
        # import / attribute-access patterns.
        self.assertFalse(
            _module_has_subprocess_use(DRY_RUN_PY),
            f"{DRY_RUN_PY} imports or accesses subprocess.",
        )

    def test_no_env_credential_reads_in_dry_run(self) -> None:
        self.assertFalse(
            _module_has_os_env_credential_read(DRY_RUN_PY),
            f"{DRY_RUN_PY} reads environment credentials.",
        )

    def test_no_forbidden_imports(self) -> None:
        forbidden = {
            "requests", "httpx", "aiohttp", "dotenv",
            "subprocess", "os", "shutil", "shelve", "pickle",
            "ib_insync", "ccxt", "alpaca_trade_api", "metatrader5",
            "urllib", "urllib3", "yfinance", "pandas",
        }
        imports = _collect_imports(EXPORT_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"export.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_sox_adapter_in_export_module(self) -> None:
        src = EXPORT_PATH.read_text(encoding="utf-8")
        sox = "S" + "O" + "X"
        fred = "Fred"
        forbidden = (
            fred + sox + "OverlayAdapter",
            sox + "OverlayAdapter",
            "Phlx" + sox + "Adapter",
            sox + "Adapter",
        )
        for token in forbidden:
            self.assertNotIn(
                token,
                src,
                f"export.py must not reference {token!r}.",
            )

    def test_no_broker_order_account_field_introduced(self) -> None:
        # The export layer must not introduce any
        # account / broker / order / position field. The
        # schema is fixed by validate_market_context. If a
        # new top-level field were added, validation would
        # raise. We confirm the validator rejects an extra
        # top-level field.
        ctx = _make_minimal_context("2026-06-24")
        ctx_dict = asdict(ctx)
        ctx_dict["account_balance"] = 100000
        with self.assertRaises(ValidationError):
            validate_market_context(ctx_dict)


# --- Raw FRED CSV audit --------------------------------------------------


class RawFREDCSVAuditTests(unittest.TestCase):
    def test_no_raw_fred_csv_committed(self) -> None:
        # The PR must not commit any raw FRED CSV. We check
        # the export, fixture, and report directories for
        # any CSV file whose header contains a FRED-style
        # DATE / series-id column.
        for d in (EXPORTS_DIR, REPO_ROOT / "fixtures", REPO_ROOT / "reports"):
            if not d.exists():
                continue
            for fp in d.rglob("*"):
                if not fp.is_file():
                    continue
                if fp.suffix.lower() not in (".json", ".csv", ".txt"):
                    continue
                try:
                    txt = fp.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for header in (
                    "DATE,DGS2",
                    "DATE,DGS10",
                    "DATE,SP500",
                    "DATE,DEXJPUS",
                    "DATE,NASDAQ100",
                ):
                    self.assertNotIn(
                        header,
                        txt,
                        f"Raw FRED CSV header {header!r} found in "
                        f"{fp}. PR must not commit raw FRED data.",
                    )


# --- Documentation and dry-run presence ----------------------------------


class ExportDocsAndScriptsTests(unittest.TestCase):
    def test_export_doc_exists(self) -> None:
        self.assertTrue(
            EXPORT_DOC.exists(),
            f"Missing docs/market-context-export.md: {EXPORT_DOC}",
        )

    def test_dry_run_shell_exists(self) -> None:
        self.assertTrue(
            EXPORT_DRY_RUN_SH.exists(),
            f"Missing scripts/export_composed_market_context_dry_run.sh: "
            f"{EXPORT_DRY_RUN_SH}",
        )

    def test_dry_run_shell_uses_strict_mode(self) -> None:
        text = EXPORT_DRY_RUN_SH.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_dry_run_python_uses_mocked_csv(self) -> None:
        text = DRY_RUN_PY.read_text(encoding="utf-8")
        # The dry-run must inject http_get (mocked CSV), not
        # perform real network I/O.
        self.assertIn("http_get", text)
        # It must reference the four approved FRED overlay
        # adapters and the composition helper.
        for token in (
            "FredTreasuryOverlayAdapter",
            "FredSP500OverlayAdapter",
            "FredUSDJPYOverlayAdapter",
            "FredNASDAQ100OverlayAdapter",
            "compose_market_context_adapter",
        ):
            self.assertIn(token, text)

    def test_data_adapter_contract_links_to_export_doc(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "market-context-export.md",
            text,
            "data-adapter-contract.md must link to "
            "docs/market-context-export.md.",
        )

    def test_data_adapter_contract_section_8_7_present(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "8.7",
            text,
            "data-adapter-contract.md must contain a §8.7 "
            "market-context-export section.",
        )


# --- Optional committed example JSON guard --------------------------------


class CommittedExampleGuardTests(unittest.TestCase):
    def test_committed_example_under_exports_dry_run(self) -> None:
        # If a committed example JSON exists in
        # exports/composed-market-context-*.json, it must be
        # under exports/dry-run/ and contain a synthetic
        # marker.
        if not EXPORTS_DIR.exists():
            return
        for fp in EXPORTS_DIR.rglob("composed-market-context-*.json"):
            rel = fp.relative_to(REPO_ROOT)
            parts = rel.parts
            # parts[0] = "exports"; parts[1] must be "dry-run"
            # (or deeper, but the top-level under exports must
            # be dry-run).
            self.assertGreaterEqual(
                len(parts),
                2,
                f"Committed example {fp} must be under exports/dry-run/.",
            )
            self.assertEqual(
                parts[0],
                "exports",
                f"Committed example {fp} must be under exports/.",
            )
            self.assertEqual(
                parts[1],
                "dry-run",
                f"Committed example {fp} must be under exports/dry-run/.",
            )
            txt = fp.read_text(encoding="utf-8")
            try:
                parsed = json.loads(txt)
            except json.JSONDecodeError:
                self.fail(
                    f"Committed example {fp} is not valid JSON."
                )
            # Must contain a synthetic marker.
            self.assertTrue(
                "synthetic" in parsed
                or "_dry_run_meta" in parsed,
                f"Committed example {fp} must include a synthetic "
                f"marker (top-level 'synthetic' or '_dry_run_meta' key).",
            )


if __name__ == "__main__":
    unittest.main()
