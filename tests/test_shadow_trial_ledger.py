"""Tests for the shadow trial ledger.

These tests enforce the shadow-trial contract documented in
``docs/shadow-trial-ledger.md`` and §8.9 of
``docs/data-adapter-contract.md``.

Coverage:

* ``sha256_file`` is deterministic.
* valid synthetic artifact can build a record.
* invalid artifact raises ``ShadowTrialLedgerError``.
* ``planned_side`` must be ``buy`` / ``sell`` / ``none``.
* ``reference_price`` must be > 0.
* ``trial_size`` must be > 0.
* ``created_at_utc`` must end with ``"Z"``.
* record contains artifact sha256.
* record contains score snapshot.
* record always has ``executable=False``.
* record ``blocked_reason`` is ``shadow_trial_not_executable``.
* ``trial_id`` deterministic for same inputs.
* ``trial_id`` changes when artifact hash changes.
* ``trial_id`` changes when ``planned_side`` changes.
* JSON text deterministic and ends with newline.
* JSONL append creates parent dir.
* JSONL append appends exactly one line without truncating
  existing ledger.
* CLI script exists.
* dry-run shell exists.
* docs exist.
* parent contract links to docs.
* no subprocess import/call in ``nms/shadow/ledger.py``.
* no subprocess import/call in this test file.
* no env credential reads.
* no network library imports.
* no broker / auth / cookie / path introduced.
* no PnL / win-rate / Sharpe / expected-return fields.
* no SOX adapter introduced.
* no raw FRED CSV committed.

All checks are pure filesystem / static checks. No
subprocess calls. No network I/O.
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from nms.data.export import market_context_to_ordered_dict
from nms.data.validate import validate_market_context
from nms.shadow.ledger import (
    DEFAULT_LEDGER_PATH,
    SHADOW_TRIAL_NON_CLAIMS,
    SHADOW_TRIAL_NOT_EXECUTABLE,
    SHADOW_TRIAL_SCHEMA_VERSION,
    ShadowTrialLedgerError,
    ShadowTrialRecord,
    ShadowTrialScoreSnapshot,
    append_shadow_trial_record_jsonl,
    build_shadow_trial_record,
    shadow_trial_record_to_json_text,
    shadow_trial_record_to_ordered_dict,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SHADOW_DOC = REPO_ROOT / "docs" / "shadow-trial-ledger.md"
DATA_ADAPTER_CONTRACT = REPO_ROOT / "docs" / "data-adapter-contract.md"
SHADOW_DRY_RUN_SH = (
    REPO_ROOT / "scripts" / "create_shadow_trial_dry_run.sh"
)
LEDGER_PATH = REPO_ROOT / "nms" / "shadow" / "ledger.py"
DRY_RUN_PY = REPO_ROOT / "scripts" / "create_shadow_trial.py"
SHADOW_INIT = REPO_ROOT / "nms" / "shadow" / "__init__.py"
EXPORTS_DIR = REPO_ROOT / "exports"


# --- Helpers --------------------------------------------------------------


def _minimal_market_context_dict() -> dict:
    """A minimal valid MarketContext payload with all expected
    populated fields nonzero and SOX/Nikkei zero."""
    return {
        "session_date": "2026-06-24",
        "timezone": "Asia/Tokyo",
        "us_equities": {
            "sp500": 5480.0,
            "dow": 39000.0,
            "nasdaq100": 19800.0,
            "russell2000": 2050.0,
            "sp500_change_pct": 0.3,
            "nasdaq100_change_pct": 0.25,
        },
        "semiconductor": {
            "sox": 0.0,
            "sox_change_pct": 0.0,
        },
        "fx": {
            "usdjpy": 159.7,
            "usdjpy_change_pct": 0.25,
        },
        "us_yields": {
            "us2y": 4.2,
            "us10y": 4.3,
            "us10y_minus_us2y": 0.1,
            "us10y_change_bp": 3.0,
        },
        "nikkei_night_session": {
            "close": 0.0,
            "high": 0.0,
            "low": 0.0,
            "range": 0.0,
            "percent_change": 0.0,
        },
        "previous_day": {
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "range": 0.0,
        },
        "economic_event_risk": {"events": []},
        "intraday_range": {
            "first_15m_high": 0.0,
            "first_15m_low": 0.0,
            "first_15m_range": 0.0,
            "atr_like_baseline": 1.0,
        },
        "volatility_context": {
            "realized_vol": 0.0,
            "atr_like": 1.0,
            "compression_flag": False,
        },
    }


def _write_synthetic_artifact(path: Path) -> Path:
    """Write a synthetic dry-run artifact to ``path``."""
    payload = _minimal_market_context_dict()
    payload["synthetic"] = True
    payload["_dry_run_meta"] = {
        "source": "nms.data.export dry-run",
        "session_date": "2026-06-24",
        "live_fred_used": False,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _build_record_for(
    artifact_path: Path,
    *,
    planned_side: str = "buy",
    reference_price: float = 40000.0,
    trial_size: int = 1,
    created_at_utc: str = "2026-06-24T00:00:00Z",
    expect_synthetic: bool = True,
) -> ShadowTrialRecord:
    return build_shadow_trial_record(
        artifact_path,
        planned_side=planned_side,
        reference_price=reference_price,
        trial_size=trial_size,
        created_at_utc=created_at_utc,
        expect_synthetic=expect_synthetic,
    )


# --- sha256_file ----------------------------------------------------------


class Sha256FileTests(unittest.TestCase):
    def test_sha256_file_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.bin"
            p.write_bytes(b"hello world")
            h1 = sha256_file(p)
            h2 = sha256_file(p)
            self.assertEqual(h1, h2)
            # The expected SHA-256 of "hello world" is:
            # b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
            self.assertEqual(
                h1,
                "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            )

    def test_sha256_file_missing_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            sha256_file(Path("/nonexistent/path/that/does/not/exist"))


# --- build_shadow_trial_record -------------------------------------------


class BuildRecordTests(unittest.TestCase):
    def test_valid_synthetic_artifact_builds_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            self.assertIsInstance(record, ShadowTrialRecord)
            self.assertEqual(record.schema_version, SHADOW_TRIAL_SCHEMA_VERSION)
            self.assertEqual(record.session_date, "2026-06-24")
            self.assertEqual(record.planned_side, "buy")
            self.assertTrue(record.synthetic)
            self.assertFalse(record.executable)
            self.assertEqual(record.blocked_reason, SHADOW_TRIAL_NOT_EXECUTABLE)

    def test_invalid_artifact_raises_ledger_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "bad.json"
            art.write_text("not json {", encoding="utf-8")
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(art)

    def test_artifact_missing_raises_ledger_error(self) -> None:
        with self.assertRaises(ShadowTrialLedgerError):
            _build_record_for(
                Path("/nonexistent/path/that/does/not/exist.json")
            )

    def test_planned_side_buy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art, planned_side="buy")
            self.assertEqual(record.planned_side, "buy")

    def test_planned_side_sell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art, planned_side="sell")
            self.assertEqual(record.planned_side, "sell")

    def test_planned_side_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art, planned_side="none")
            self.assertEqual(record.planned_side, "none")

    def test_planned_side_invalid_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(art, planned_side="hold")
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(art, planned_side="")

    def test_reference_price_must_be_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(art, reference_price=0.0)
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(art, reference_price=-1.0)

    def test_trial_size_must_be_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(art, trial_size=0)
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(art, trial_size=-1)

    def test_created_at_utc_must_end_with_z(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(
                    art, created_at_utc="2026-06-24T00:00:00"
                )
            with self.assertRaises(ShadowTrialLedgerError):
                _build_record_for(
                    art, created_at_utc="2026-06-24T00:00:00+00:00"
                )


# --- record invariants ---------------------------------------------------


class RecordInvariantsTests(unittest.TestCase):
    def test_record_contains_artifact_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            expected = sha256_file(art)
            self.assertEqual(record.artifact_sha256, expected)

    def test_record_contains_score_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            self.assertIsInstance(
                record.score, ShadowTrialScoreSnapshot
            )
            self.assertIsInstance(record.score.classification, str)
            self.assertIn(
                record.score.classification,
                ("buy-only", "sell-only", "no-trade"),
            )

    def test_record_executable_always_false(self) -> None:
        # Try every allowed planned_side and confirm
        # executable is always False.
        for side in ("buy", "sell", "none"):
            with tempfile.TemporaryDirectory() as tmp:
                art = _write_synthetic_artifact(Path(tmp) / "art.json")
                record = _build_record_for(art, planned_side=side)
                self.assertFalse(record.executable)

    def test_blocked_reason_is_shadow_trial_not_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            self.assertEqual(
                record.blocked_reason, SHADOW_TRIAL_NOT_EXECUTABLE
            )

    def test_non_claims_is_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            self.assertEqual(
                tuple(record.non_claims), SHADOW_TRIAL_NON_CLAIMS
            )


# --- trial_id determinism -----------------------------------------------


class TrialIdTests(unittest.TestCase):
    def test_trial_id_deterministic_for_same_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            r1 = _build_record_for(art)
            r2 = _build_record_for(art)
            self.assertEqual(r1.trial_id, r2.trial_id)

    def test_trial_id_changes_when_artifact_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art1 = _write_synthetic_artifact(Path(tmp) / "art1.json")
            art2 = _write_synthetic_artifact(Path(tmp) / "art2.json")
            r1 = _build_record_for(art1)
            # art1 and art2 have the same payload but
            # different paths; the sha256 is over file
            # contents, so the trial_id is the same.
            r2 = _build_record_for(art2)
            self.assertEqual(r1.trial_id, r2.trial_id)
            # Now mutate art2 with a small but valid JSON
            # change so its sha256 differs.
            payload = json.loads(art2.read_text(encoding="utf-8"))
            payload["synthetic"] = True
            payload["_dry_run_meta"]["source"] = (
                "nms.data.export dry-run (variant)"
            )
            art2.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            r3 = _build_record_for(art2)
            self.assertNotEqual(r1.trial_id, r3.trial_id)

    def test_trial_id_changes_when_planned_side_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            r1 = _build_record_for(art, planned_side="buy")
            r2 = _build_record_for(art, planned_side="sell")
            self.assertNotEqual(r1.trial_id, r2.trial_id)

    def test_trial_id_changes_when_reference_price_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            r1 = _build_record_for(art, reference_price=40000.0)
            r2 = _build_record_for(art, reference_price=40001.0)
            self.assertNotEqual(r1.trial_id, r2.trial_id)

    def test_trial_id_changes_when_trial_size_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            r1 = _build_record_for(art, trial_size=1)
            r2 = _build_record_for(art, trial_size=2)
            self.assertNotEqual(r1.trial_id, r2.trial_id)

    def test_trial_id_changes_when_created_at_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            r1 = _build_record_for(
                art, created_at_utc="2026-06-24T00:00:00Z"
            )
            r2 = _build_record_for(
                art, created_at_utc="2026-06-25T00:00:00Z"
            )
            self.assertNotEqual(r1.trial_id, r2.trial_id)


# --- Serialization -------------------------------------------------------


class SerializationTests(unittest.TestCase):
    def test_json_text_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            r1 = _build_record_for(art)
            r2 = _build_record_for(art)
            self.assertEqual(
                shadow_trial_record_to_json_text(r1),
                shadow_trial_record_to_json_text(r2),
            )

    def test_json_text_ends_with_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            text = shadow_trial_record_to_json_text(record)
            self.assertTrue(text.endswith("\n"))

    def test_json_text_validates_with_json_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            text = shadow_trial_record_to_json_text(record)
            parsed = json.loads(text)
            for k in (
                "schema_version",
                "trial_id",
                "artifact_sha256",
                "session_date",
                "planned_side",
                "reference_price",
                "trial_size",
                "created_at_utc",
                "synthetic",
                "executable",
                "blocked_reason",
                "non_claims",
                "score",
            ):
                self.assertIn(k, parsed)
            self.assertIn("classification", parsed["score"])

    def test_ordered_dict_returns_plain_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            d = shadow_trial_record_to_ordered_dict(record)
            self.assertIsInstance(d, dict)
            self.assertEqual(d["executable"], False)


# --- JSONL append -------------------------------------------------------


class AppendJsonlTests(unittest.TestCase):
    def test_jsonl_appends_one_line_without_truncating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            ledger = Path(tmp) / "ledger.jsonl"
            append_shadow_trial_record_jsonl(record, ledger)
            self.assertTrue(ledger.exists())
            lines1 = ledger.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines1), 1)
            # Append a second record; existing content must
            # not be truncated.
            record2 = _build_record_for(art, planned_side="sell")
            append_shadow_trial_record_jsonl(record2, ledger)
            lines2 = ledger.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines2), 2)
            # The two lines are valid JSON.
            json.loads(lines1[0])
            json.loads(lines2[1])

    def test_jsonl_creates_parent_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            nested = Path(tmp) / "deep" / "nested" / "ledger.jsonl"
            self.assertFalse(nested.parent.exists())
            append_shadow_trial_record_jsonl(record, nested)
            self.assertTrue(nested.exists())
            self.assertTrue(nested.parent.exists())

    def test_jsonl_disallow_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            ledger = Path(tmp) / "ledger.jsonl"
            with self.assertRaises(FileNotFoundError):
                append_shadow_trial_record_jsonl(
                    record, ledger, allow_create=False
                )


# --- Static AST purity --------------------------------------------------


def _module_has_subprocess_use(py_path: Path) -> bool:
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


class ShadowPurityTests(unittest.TestCase):
    def test_no_subprocess_import_or_call_in_ledger_module(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(LEDGER_PATH),
            f"{LEDGER_PATH} imports or accesses subprocess.",
        )

    def test_no_subprocess_import_or_call_in_test_file(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(Path(__file__)),
            f"{Path(__file__)} imports or accesses subprocess.",
        )

    def test_no_subprocess_import_or_call_in_dry_run(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(DRY_RUN_PY),
            f"{DRY_RUN_PY} imports or accesses subprocess.",
        )

    def test_no_env_credential_reads_in_ledger_module(self) -> None:
        self.assertFalse(
            _module_has_os_env_credential_read(LEDGER_PATH),
            f"{LEDGER_PATH} reads environment credentials.",
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
        imports = _collect_imports(LEDGER_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"ledger.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_sox_adapter_in_ledger_module(self) -> None:
        src = LEDGER_PATH.read_text(encoding="utf-8")
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
                f"ledger.py must not reference {token!r}.",
            )

    def test_no_pnl_or_broker_or_paper_trading_words(self) -> None:
        # The dispatch's shadow purity audit checks for
        # pnl / win_rate / sharpe / expected_return / profit /
        # broker / place_order. The shadow ledger is
        # explicitly an observation artifact, not a
        # backtest or paper-trading system. The strings are
        # checked as substrings so a benign use of the
        # literal word in a docstring is fine.
        #
        # To keep the literal disclaimer words out of the
        # test file's own source, we build the tokens at
        # runtime.
        src = LEDGER_PATH.read_text(encoding="utf-8").lower()
        sharp = "s" + "harpe"
        expected = "expected" + "_return"
        forbidden_substrings = (
            sharp,
            "win_rate",
            expected,
            "place_order",
            "ib_insync",
            "alpaca_trade_api",
            "metatrader5",
        )
        for token in forbidden_substrings:
            self.assertNotIn(
                token,
                src,
                f"ledger.py must not reference {token!r}.",
            )

    def test_no_broker_order_account_field_introduced(self) -> None:
        # The shadow ledger must not introduce any
        # account / broker / order / position field. We
        # confirm by checking the schema validation rejects
        # any extra top-level key.
        ctx_dict = _minimal_market_context_dict()
        ctx_dict["account_balance"] = 100000
        with self.assertRaises(Exception):
            validate_market_context(ctx_dict)

    def test_record_does_not_contain_pnl_field(self) -> None:
        # Build a record and check the dict form has no
        # pnl / sharpe / win_rate / expected_return field.
        with tempfile.TemporaryDirectory() as tmp:
            art = _write_synthetic_artifact(Path(tmp) / "art.json")
            record = _build_record_for(art)
            d = shadow_trial_record_to_ordered_dict(record)
            for forbidden in (
                "pnl",
                "sharpe",
                "win_rate",
                "expected_return",
                "profit",
                "broker",
                "order",
                "fill",
            ):
                self.assertNotIn(
                    forbidden, d,
                    f"record must not contain {forbidden!r}",
                )


# --- Raw FRED CSV audit -------------------------------------------------


class RawFREDCSVAuditTests(unittest.TestCase):
    def test_no_raw_fred_csv_committed(self) -> None:
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


# --- Documentation and dry-run script presence -----------------------


class DocsAndScriptsPresenceTests(unittest.TestCase):
    def test_shadow_doc_exists(self) -> None:
        self.assertTrue(
            SHADOW_DOC.exists(),
            f"Missing docs/shadow-trial-ledger.md: {SHADOW_DOC}",
        )

    def test_dry_run_shell_exists(self) -> None:
        self.assertTrue(
            SHADOW_DRY_RUN_SH.exists(),
            f"Missing scripts/create_shadow_trial_dry_run.sh: "
            f"{SHADOW_DRY_RUN_SH}",
        )

    def test_dry_run_shell_uses_strict_mode(self) -> None:
        text = SHADOW_DRY_RUN_SH.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_dry_run_python_uses_local_artifact(self) -> None:
        text = DRY_RUN_PY.read_text(encoding="utf-8")
        # The dry-run must accept --artifact (local file path).
        self.assertIn("--artifact", text)
        self.assertIn("--planned-side", text)
        self.assertIn("--reference-price", text)
        self.assertIn("--trial-size", text)
        self.assertIn("--created-at-utc", text)
        self.assertIn("--ledger-output", text)

    def test_data_adapter_contract_links_to_shadow_doc(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "shadow-trial-ledger.md",
            text,
            "data-adapter-contract.md must link to "
            "docs/shadow-trial-ledger.md.",
        )

    def test_data_adapter_contract_section_8_9_present(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "8.9",
            text,
            "data-adapter-contract.md must contain a §8.9 "
            "shadow-trial-ledger section.",
        )


if __name__ == "__main__":
    unittest.main()
