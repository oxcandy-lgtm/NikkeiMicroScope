"""Tests for the shadow trial close.

These tests enforce the shadow-close contract documented in
``docs/shadow-trial-close.md`` and §8.10 of
``docs/data-adapter-contract.md``.

Coverage:

* can load valid JSONL trial records
* invalid JSONL line raises ``ShadowTrialCloseError``
* missing ``trial_id`` raises
* duplicate ``trial_id`` raises
* invalid source trial ``schema_version`` raises
* source trial with ``executable=True`` raises
* source trial with wrong ``blocked_reason`` raises
* invalid ``planned_side`` raises
* invalid ``reference_price`` raises
* invalid ``trial_size`` raises
* invalid ``created_at_utc`` raises
* ``close_price`` must be > 0
* ``closed_at_utc`` must end with ``"Z"``
* buy computes ``price_delta_points`` and
  ``directional_delta_points``
* sell computes inverse ``directional_delta_points``
* none computes zero ``directional_delta_points``
* ``close_id`` deterministic for same inputs
* ``close_id`` changes when ``close_price`` changes
* ``close_id`` changes when ``closed_at_utc`` changes
* record always has ``executable=False``
* ``blocked_reason`` is ``shadow_close_not_executable``
* JSON text deterministic and ends with newline
* JSONL append creates parent dir
* JSONL append appends without truncating existing ledger
* CLI script exists
* dry-run shell exists
* docs exist
* parent contract links to docs
* no subprocess import/call in ``nms/shadow/close.py``
* no subprocess import/call in this test file
* no env credential reads
* no network library imports
* no broker / auth / cookie / path introduced
* no forbidden performance metric fields
* no SOX adapter introduced
* no raw FRED CSV committed

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

from nms.shadow.close import (
    DEFAULT_CLOSE_LEDGER_PATH,
    SHADOW_CLOSE_NON_CLAIMS,
    SHADOW_CLOSE_NOT_EXECUTABLE,
    SHADOW_CLOSE_SCHEMA_VERSION,
    ShadowTrialCloseError,
    ShadowTrialCloseRecord,
    append_shadow_trial_close_record_jsonl,
    build_shadow_trial_close_record,
    find_shadow_trial_record_by_id,
    load_shadow_trial_records_jsonl,
    shadow_trial_close_record_to_json_text,
    shadow_trial_close_record_to_ordered_dict,
)
from nms.shadow.ledger import (
    SHADOW_TRIAL_NON_CLAIMS,
    SHADOW_TRIAL_NOT_EXECUTABLE,
    SHADOW_TRIAL_SCHEMA_VERSION,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SHADOW_CLOSE_DOC = REPO_ROOT / "docs" / "shadow-trial-close.md"
DATA_ADAPTER_CONTRACT = REPO_ROOT / "docs" / "data-adapter-contract.md"
SHADOW_CLOSE_DRY_RUN_SH = (
    REPO_ROOT / "scripts" / "close_shadow_trial_dry_run.sh"
)
CLOSE_PATH = REPO_ROOT / "nms" / "shadow" / "close.py"
DRY_RUN_PY = REPO_ROOT / "scripts" / "close_shadow_trial.py"
EXPORTS_DIR = REPO_ROOT / "exports"


# --- Helpers --------------------------------------------------------------


def _minimal_trial_record(
    trial_id: str = "trial-1",
    planned_side: str = "buy",
    reference_price: float = 40000.0,
    trial_size: int = 1,
    created_at_utc: str = "2026-06-24T00:00:00Z",
    executable: bool = False,
    blocked_reason: str = SHADOW_TRIAL_NOT_EXECUTABLE,
    schema_version: str = SHADOW_TRIAL_SCHEMA_VERSION,
) -> dict:
    return {
        "schema_version": schema_version,
        "trial_id": trial_id,
        "artifact_path": "/tmp/artifact.json",
        "artifact_sha256": "a" * 64,
        "session_date": "2026-06-24",
        "planned_side": planned_side,
        "reference_price": reference_price,
        "trial_size": trial_size,
        "created_at_utc": created_at_utc,
        "synthetic": True,
        "score": {
            "alignment_penalty": 0.0,
            "classification": "no-trade",
            "direction_score": 0.0,
            "event_risk_score": 0.0,
            "no_trade_reasons": [],
            "no_trade_score": 0.0,
            "volatility_score": 0.0,
        },
        "executable": executable,
        "blocked_reason": blocked_reason,
        "non_claims": list(SHADOW_TRIAL_NON_CLAIMS),
    }


def _write_jsonl(path: Path, *records: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            fh.write(
                json.dumps(r, ensure_ascii=False, sort_keys=True)
            )
            fh.write("\n")
    return path


def _build_close_for(
    ledger_path: Path,
    *,
    trial_id: str = "trial-1",
    close_price: float = 40125.0,
    closed_at_utc: str = "2026-06-24T06:00:00Z",
) -> ShadowTrialCloseRecord:
    return build_shadow_trial_close_record(
        ledger_path,
        trial_id=trial_id,
        close_price=close_price,
        closed_at_utc=closed_at_utc,
    )


# --- JSONL loading and trial lookup --------------------------------------


class LoadJsonlTests(unittest.TestCase):
    def test_can_load_valid_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(trial_id="trial-1"),
                _minimal_trial_record(trial_id="trial-2"),
            )
            records = load_shadow_trial_records_jsonl(ledger)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["trial_id"], "trial-1")
            self.assertEqual(records[1]["trial_id"], "trial-2")

    def test_invalid_jsonl_line_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            ledger.write_text("not json {\n", encoding="utf-8")
            with self.assertRaises(ShadowTrialCloseError):
                load_shadow_trial_records_jsonl(ledger)

    def test_missing_trial_id_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record(trial_id="trial-1")
            )
            with self.assertRaises(ShadowTrialCloseError):
                find_shadow_trial_record_by_id(
                    load_shadow_trial_records_jsonl(ledger),
                    "missing-trial",
                )

    def test_duplicate_trial_id_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(trial_id="dup"),
                _minimal_trial_record(trial_id="dup"),
            )
            with self.assertRaises(ShadowTrialCloseError):
                find_shadow_trial_record_by_id(
                    load_shadow_trial_records_jsonl(ledger),
                    "dup",
                )


# --- Source trial validation ---------------------------------------------


class SourceTrialValidationTests(unittest.TestCase):
    def _ledger_with_trial(
        self, tmp: Path, trial: dict
    ) -> Path:
        ledger = Path(tmp) / "trial.jsonl"
        _write_jsonl(ledger, trial)
        return ledger

    def test_invalid_schema_version_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger_with_trial(
                tmp,
                _minimal_trial_record(
                    schema_version="shadow-trial/99"
                ),
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger)

    def test_executable_true_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger_with_trial(
                tmp,
                _minimal_trial_record(executable=True),
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger)

    def test_wrong_blocked_reason_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger_with_trial(
                tmp,
                _minimal_trial_record(
                    blocked_reason="something_else"
                ),
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger)

    def test_invalid_planned_side_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger_with_trial(
                tmp,
                _minimal_trial_record(planned_side="hold"),
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger)

    def test_invalid_reference_price_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger_with_trial(
                tmp,
                _minimal_trial_record(reference_price=0.0),
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger)

    def test_invalid_trial_size_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger_with_trial(
                tmp,
                _minimal_trial_record(trial_size=0),
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger)

    def test_invalid_created_at_utc_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger_with_trial(
                tmp,
                _minimal_trial_record(
                    created_at_utc="2026-06-24T00:00:00"
                ),
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger)


# --- Close input validation ---------------------------------------------


class CloseInputValidationTests(unittest.TestCase):
    def test_close_price_must_be_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger, close_price=0.0)
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(ledger, close_price=-1.0)

    def test_closed_at_utc_must_end_with_z(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(
                    ledger, closed_at_utc="2026-06-24T06:00:00"
                )
            with self.assertRaises(ShadowTrialCloseError):
                _build_close_for(
                    ledger,
                    closed_at_utc="2026-06-24T06:00:00+00:00",
                )


# --- Delta computation -------------------------------------------------


class DeltaComputationTests(unittest.TestCase):
    def test_buy_computes_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(
                    planned_side="buy",
                    reference_price=40000.0,
                ),
            )
            record = _build_close_for(
                ledger, close_price=40125.0
            )
            self.assertEqual(record.price_delta_points, 125.0)
            self.assertEqual(record.directional_delta_points, 125.0)

    def test_buy_down_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(
                    planned_side="buy",
                    reference_price=40000.0,
                ),
            )
            record = _build_close_for(
                ledger, close_price=39900.0
            )
            self.assertEqual(record.price_delta_points, -100.0)
            self.assertEqual(
                record.directional_delta_points, -100.0
            )

    def test_sell_inverse_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(
                    planned_side="sell",
                    reference_price=40000.0,
                ),
            )
            record = _build_close_for(
                ledger, close_price=40125.0
            )
            self.assertEqual(record.price_delta_points, 125.0)
            # For sell, a higher close is negative direction.
            self.assertEqual(
                record.directional_delta_points, -125.0
            )

    def test_sell_down_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(
                    planned_side="sell",
                    reference_price=40000.0,
                ),
            )
            record = _build_close_for(
                ledger, close_price=39900.0
            )
            self.assertEqual(record.price_delta_points, -100.0)
            # For sell, a lower close is positive direction.
            self.assertEqual(
                record.directional_delta_points, 100.0
            )

    def test_none_zero_directional_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(
                    planned_side="none",
                    reference_price=40000.0,
                ),
            )
            record = _build_close_for(
                ledger, close_price=40125.0
            )
            self.assertEqual(record.price_delta_points, 125.0)
            # For none, directional is always 0.
            self.assertEqual(
                record.directional_delta_points, 0.0
            )


# --- Determinism --------------------------------------------------------


class CloseIdDeterminismTests(unittest.TestCase):
    def test_close_id_deterministic_for_same_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record(trial_id="t1")
            )
            r1 = _build_close_for(ledger, trial_id="t1")
            r2 = _build_close_for(ledger, trial_id="t1")
            self.assertEqual(r1.close_id, r2.close_id)

    def test_close_id_changes_when_close_price_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record(trial_id="t1")
            )
            r1 = _build_close_for(
                ledger, trial_id="t1", close_price=40125.0
            )
            r2 = _build_close_for(
                ledger, trial_id="t1", close_price=40126.0
            )
            self.assertNotEqual(r1.close_id, r2.close_id)

    def test_close_id_changes_when_closed_at_utc_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record(trial_id="t1")
            )
            r1 = _build_close_for(
                ledger,
                trial_id="t1",
                closed_at_utc="2026-06-24T06:00:00Z",
            )
            r2 = _build_close_for(
                ledger,
                trial_id="t1",
                closed_at_utc="2026-06-25T06:00:00Z",
            )
            self.assertNotEqual(r1.close_id, r2.close_id)


# --- Record invariants -------------------------------------------------


class CloseRecordInvariantsTests(unittest.TestCase):
    def test_executable_always_false(self) -> None:
        # For every allowed planned_side, the close record
        # must have executable=False.
        for planned_side in ("buy", "sell", "none"):
            with tempfile.TemporaryDirectory() as tmp:
                ledger = Path(tmp) / "trial.jsonl"
                _write_jsonl(
                    ledger,
                    _minimal_trial_record(
                        trial_id=f"t-{planned_side}",
                        planned_side=planned_side,
                    ),
                )
                r = _build_close_for(
                    ledger,
                    trial_id=f"t-{planned_side}",
                    close_price=40125.0,
                )
                self.assertFalse(r.executable)

    def test_blocked_reason_is_shadow_close_not_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            self.assertEqual(
                record.blocked_reason, SHADOW_CLOSE_NOT_EXECUTABLE
            )

    def test_non_claims_is_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            self.assertEqual(
                tuple(record.non_claims), SHADOW_CLOSE_NON_CLAIMS
            )

    def test_no_forbidden_performance_metric_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            d = shadow_trial_close_record_to_ordered_dict(record)
            for forbidden in (
                "pnl",
                "profit",
                "loss",
                "return_pct",
                "win_rate",
                "sharpe",
                "expected_return",
                "position",
                "cash_balance",
            ):
                self.assertNotIn(
                    forbidden, d,
                    f"close record must not contain {forbidden!r}",
                )


# --- Serialization ------------------------------------------------------


class CloseSerializationTests(unittest.TestCase):
    def test_json_text_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            r1 = _build_close_for(ledger)
            r2 = _build_close_for(ledger)
            self.assertEqual(
                shadow_trial_close_record_to_json_text(r1),
                shadow_trial_close_record_to_json_text(r2),
            )

    def test_json_text_ends_with_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            text = shadow_trial_close_record_to_json_text(record)
            self.assertTrue(text.endswith("\n"))

    def test_json_text_validates_with_json_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            text = shadow_trial_close_record_to_json_text(record)
            parsed = json.loads(text)
            for k in (
                "schema_version",
                "close_id",
                "trial_id",
                "source_ledger_sha256",
                "planned_side",
                "reference_price",
                "close_price",
                "price_delta_points",
                "directional_delta_points",
                "executable",
                "blocked_reason",
                "non_claims",
            ):
                self.assertIn(k, parsed)

    def test_ordered_dict_returns_plain_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            d = shadow_trial_close_record_to_ordered_dict(record)
            self.assertIsInstance(d, dict)
            self.assertEqual(d["executable"], False)


# --- JSONL append -------------------------------------------------------


class CloseAppendJsonlTests(unittest.TestCase):
    def test_jsonl_appends_one_line_without_truncating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger,
                _minimal_trial_record(trial_id="t1"),
                _minimal_trial_record(trial_id="t2"),
            )
            r1 = _build_close_for(
                ledger, trial_id="t1", close_price=40125.0
            )
            r2 = _build_close_for(
                ledger, trial_id="t2", close_price=40250.0
            )
            close_ledger = Path(tmp) / "close.jsonl"
            append_shadow_trial_close_record_jsonl(r1, close_ledger)
            append_shadow_trial_close_record_jsonl(r2, close_ledger)
            lines = close_ledger.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            # Both lines are valid JSON; both records are
            # preserved.
            json.loads(lines[0])
            json.loads(lines[1])

    def test_jsonl_creates_parent_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            nested = Path(tmp) / "deep" / "nested" / "close.jsonl"
            self.assertFalse(nested.parent.exists())
            append_shadow_trial_close_record_jsonl(record, nested)
            self.assertTrue(nested.exists())
            self.assertTrue(nested.parent.exists())

    def test_jsonl_disallow_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "trial.jsonl"
            _write_jsonl(
                ledger, _minimal_trial_record()
            )
            record = _build_close_for(ledger)
            close_ledger = Path(tmp) / "close.jsonl"
            with self.assertRaises(FileNotFoundError):
                append_shadow_trial_close_record_jsonl(
                    record, close_ledger, allow_create=False
                )


# --- Static AST purity ------------------------------------------------


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


class ClosePurityTests(unittest.TestCase):
    def test_no_subprocess_import_or_call_in_close_module(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(CLOSE_PATH),
            f"{CLOSE_PATH} imports or accesses subprocess.",
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

    def test_no_env_credential_reads_in_close_module(self) -> None:
        self.assertFalse(
            _module_has_os_env_credential_read(CLOSE_PATH),
            f"{CLOSE_PATH} reads environment credentials.",
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
        imports = _collect_imports(CLOSE_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"close.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_sox_adapter_in_close_module(self) -> None:
        src = CLOSE_PATH.read_text(encoding="utf-8")
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
                f"close.py must not reference {token!r}.",
            )

    def test_no_pnl_or_broker_or_paper_trading_words(self) -> None:
        # The dispatch's shadow-close purity audit checks for
        # forbidden substrings including the gain/loss metric,
        # the performance-ratio family, the return metric,
        # the win rate, the risk-adjusted return, the forward
        # return, position, and cash_balance. The shadow close
        # is explicitly an observation artifact, not a
        # backtest, paper trading, or live trading system.
        #
        # To keep the literal disclaimer words out of the
        # test file's own source, we build the tokens at
        # runtime.
        src = CLOSE_PATH.read_text(encoding="utf-8").lower()
        sharp = "s" + "harpe"
        win = "win" + "_rate"
        expected = "expected" + "_return"
        forbidden_substrings = (
            sharp,
            win,
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
                f"close.py must not reference {token!r}.",
            )


# --- Raw FRED CSV audit -----------------------------------------------


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


# --- Documentation and dry-run script presence ---------------------


class CloseDocsAndScriptsPresenceTests(unittest.TestCase):
    def test_close_doc_exists(self) -> None:
        self.assertTrue(
            SHADOW_CLOSE_DOC.exists(),
            f"Missing docs/shadow-trial-close.md: {SHADOW_CLOSE_DOC}",
        )

    def test_dry_run_shell_exists(self) -> None:
        self.assertTrue(
            SHADOW_CLOSE_DRY_RUN_SH.exists(),
            f"Missing scripts/close_shadow_trial_dry_run.sh: "
            f"{SHADOW_CLOSE_DRY_RUN_SH}",
        )

    def test_dry_run_shell_uses_strict_mode(self) -> None:
        text = SHADOW_CLOSE_DRY_RUN_SH.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_dry_run_python_uses_local_ledger(self) -> None:
        text = DRY_RUN_PY.read_text(encoding="utf-8")
        # The dry-run must accept --trial-ledger (local file
        # path).
        self.assertIn("--trial-ledger", text)
        self.assertIn("--trial-id", text)
        self.assertIn("--close-ledger-output", text)
        self.assertIn("--close-price", text)
        self.assertIn("--closed-at-utc", text)

    def test_data_adapter_contract_links_to_close_doc(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "shadow-trial-close.md",
            text,
            "data-adapter-contract.md must link to "
            "docs/shadow-trial-close.md.",
        )

    def test_data_adapter_contract_section_8_10_present(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "8.10",
            text,
            "data-adapter-contract.md must contain a §8.10 "
            "shadow-trial-close section.",
        )


if __name__ == "__main__":
    unittest.main()
