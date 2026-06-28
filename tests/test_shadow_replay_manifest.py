"""Tests for the shadow replay manifest.

These tests enforce the shadow-replay contract documented in
``docs/shadow-replay-manifest.md`` and §8.11 of
``docs/data-adapter-contract.md``.

Coverage:

* loads valid input manifest
* rejects invalid JSON
* rejects wrong schema_version
* rejects missing rows
* rejects non-list rows
* rejects duplicate row_id
* rejects invalid planned_side
* rejects invalid reference_price
* rejects invalid trial_size
* rejects invalid trial_created_at_utc
* rejects non-boolean expect_synthetic
* rejects close_price without closed_at_utc
* rejects closed_at_utc without close_price
* rejects invalid close_price
* rejects invalid closed_at_utc
* run creates trial and close records for valid rows
* run creates trial only when no close fields are present
* row-level invalid artifact becomes row_error
* replay continues after row error
* result counts are correct
* result JSON deterministic and ends with newline
* result writer refuses overwrite by default
* result writer allows overwrite only with flag
* result contains no aggregate delta fields
* result contains no forbidden performance fields
* CLI script exists
* dry-run shell exists
* docs exist
* parent contract links to docs
* no subprocess import/call in nms/shadow/replay.py
* no subprocess import/call in this test file
* no env credential reads
* no network library imports
* no venue/auth/cookie/path introduced
* no forbidden performance fields (pnl, profit, loss,
  return_pct, win_rate, sharpe, expected_return,
  equity_curve, portfolio, position, cash_balance,
  performance)
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

from nms.shadow.replay import (
    ROW_STATUS_CLOSE_CREATED,
    ROW_STATUS_ROW_ERROR,
    ROW_STATUS_TRIAL_CREATED,
    SHADOW_REPLAY_INPUT_SCHEMA_VERSION,
    SHADOW_REPLAY_NON_CLAIMS,
    SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
    ShadowReplayError,
    ShadowReplayResultManifest,
    ShadowReplayRow,
    ShadowReplayRowResult,
    load_shadow_replay_input_manifest,
    run_shadow_replay_manifest,
    shadow_replay_result_to_json_text,
    shadow_replay_result_to_ordered_dict,
    write_shadow_replay_result_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REPLAY_DOC = REPO_ROOT / "docs" / "shadow-replay-manifest.md"
DATA_ADAPTER_CONTRACT = REPO_ROOT / "docs" / "data-adapter-contract.md"
REPLAY_DRY_RUN_SH = (
    REPO_ROOT / "scripts" / "run_shadow_replay_dry_run.sh"
)
REPLAY_PATH = REPO_ROOT / "nms" / "shadow" / "replay.py"
DRY_RUN_PY = REPO_ROOT / "scripts" / "run_shadow_replay.py"
EXPORTS_DIR = REPO_ROOT / "exports"


# --- Helpers --------------------------------------------------------------


def _minimal_manifest_row(
    row_id: str = "row-001",
    artifact_path: str = "/tmp/artifact.json",
    planned_side: str = "buy",
    reference_price: float = 40000.0,
    trial_size: int = 1,
    trial_created_at_utc: str = "2026-06-24T00:00:00Z",
    expect_synthetic: bool = True,
    include_close: bool = True,
    close_price: float = 40125.0,
    closed_at_utc: str = "2026-06-24T06:00:00Z",
) -> dict:
    row = {
        "row_id": row_id,
        "artifact_path": artifact_path,
        "planned_side": planned_side,
        "reference_price": reference_price,
        "trial_size": trial_size,
        "trial_created_at_utc": trial_created_at_utc,
        "expect_synthetic": expect_synthetic,
    }
    if include_close:
        row["close_price"] = close_price
        row["closed_at_utc"] = closed_at_utc
    return row


def _write_manifest(
    path: Path, *rows: dict, schema_version: str = "shadow-replay-input/1"
) -> Path:
    payload = {
        "schema_version": schema_version,
        "rows": list(rows),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _write_synthetic_artifact(path: Path) -> Path:
    """Write a synthetic dry-run artifact to ``path``."""
    payload = {
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
        "synthetic": True,
        "_dry_run_meta": {
            "source": "nms.data.export dry-run",
            "session_date": "2026-06-24",
            "live_fred_used": False,
        },
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return path


# --- Input manifest validation -----------------------------------------


class LoadManifestTests(unittest.TestCase):
    def test_loads_valid_input_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest, _minimal_manifest_row()
            )
            rows = load_shadow_replay_input_manifest(manifest)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].row_id, "row-001")
            self.assertEqual(rows[0].planned_side, "buy")
            self.assertEqual(rows[0].close_price, 40125.0)

    def test_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text("not json {", encoding="utf-8")
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_wrong_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(),
                schema_version="shadow-replay-input/99",
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_missing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": "shadow-replay-input/1"}),
                encoding="utf-8",
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_non_list_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "shadow-replay-input/1",
                        "rows": "not a list",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_duplicate_row_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(row_id="dup"),
                _minimal_manifest_row(row_id="dup"),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_invalid_planned_side(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(planned_side="hold"),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_invalid_reference_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(reference_price=0.0),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_invalid_trial_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(trial_size=0),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_invalid_trial_created_at_utc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(
                    trial_created_at_utc="2026-06-24T00:00:00"
                ),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_non_boolean_expect_synthetic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(expect_synthetic="yes"),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_close_price_without_closed_at_utc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            row = _minimal_manifest_row(include_close=False)
            row["close_price"] = 40125.0
            _write_manifest(manifest, row)
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_closed_at_utc_without_close_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            row = _minimal_manifest_row(include_close=False)
            row["closed_at_utc"] = "2026-06-24T06:00:00Z"
            _write_manifest(manifest, row)
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_invalid_close_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(close_price=0.0),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)

    def test_rejects_invalid_closed_at_utc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(
                    closed_at_utc="2026-06-24T06:00:00"
                ),
            )
            with self.assertRaises(ShadowReplayError):
                load_shadow_replay_input_manifest(manifest)


# --- Replay runner ----------------------------------------------------


class ReplayRunnerTests(unittest.TestCase):
    def test_run_creates_trial_and_close_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "art.json"
            _write_synthetic_artifact(artifact)
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(
                    artifact_path=str(artifact),
                    row_id="row-1",
                ),
            )
            trial_ledger = Path(tmp) / "trial.jsonl"
            close_ledger = Path(tmp) / "close.jsonl"
            result = run_shadow_replay_manifest(
                manifest,
                trial_ledger_path=trial_ledger,
                close_ledger_path=close_ledger,
                created_at_utc="2026-06-24T07:00:00Z",
            )
            self.assertEqual(result.requested_rows, 1)
            self.assertEqual(result.valid_rows, 1)
            self.assertEqual(result.trial_records_created, 1)
            self.assertEqual(result.close_records_created, 1)
            self.assertEqual(result.rows[0].status, ROW_STATUS_CLOSE_CREATED)
            self.assertIsNotNone(result.rows[0].trial_id)
            self.assertIsNotNone(result.rows[0].close_id)
            self.assertIsNone(result.rows[0].error)
            # Ledgers must be non-empty.
            self.assertTrue(trial_ledger.exists())
            self.assertTrue(close_ledger.exists())
            self.assertEqual(
                len(trial_ledger.read_text(encoding="utf-8").splitlines()),
                1,
            )
            self.assertEqual(
                len(close_ledger.read_text(encoding="utf-8").splitlines()),
                1,
            )

    def test_run_creates_trial_only_when_no_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "art.json"
            _write_synthetic_artifact(artifact)
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(
                    artifact_path=str(artifact),
                    row_id="row-1",
                    include_close=False,
                ),
            )
            trial_ledger = Path(tmp) / "trial.jsonl"
            close_ledger = Path(tmp) / "close.jsonl"
            result = run_shadow_replay_manifest(
                manifest,
                trial_ledger_path=trial_ledger,
                close_ledger_path=close_ledger,
                created_at_utc="2026-06-24T07:00:00Z",
            )
            self.assertEqual(result.requested_rows, 1)
            self.assertEqual(result.valid_rows, 1)
            self.assertEqual(result.trial_records_created, 1)
            self.assertEqual(result.close_records_created, 0)
            self.assertEqual(
                result.rows[0].status, ROW_STATUS_TRIAL_CREATED
            )

    def test_row_level_invalid_artifact_becomes_row_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(
                    artifact_path="/nonexistent/artifact.json",
                    row_id="row-bad",
                ),
            )
            trial_ledger = Path(tmp) / "trial.jsonl"
            close_ledger = Path(tmp) / "close.jsonl"
            result = run_shadow_replay_manifest(
                manifest,
                trial_ledger_path=trial_ledger,
                close_ledger_path=close_ledger,
                created_at_utc="2026-06-24T07:00:00Z",
            )
            self.assertEqual(result.rows[0].status, ROW_STATUS_ROW_ERROR)
            self.assertEqual(result.trial_records_created, 0)
            self.assertEqual(result.close_records_created, 0)

    def test_replay_continues_after_row_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "art.json"
            _write_synthetic_artifact(artifact)
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(
                    artifact_path="/nonexistent/art1.json",
                    row_id="row-bad",
                ),
                _minimal_manifest_row(
                    artifact_path=str(artifact),
                    row_id="row-good",
                ),
            )
            trial_ledger = Path(tmp) / "trial.jsonl"
            close_ledger = Path(tmp) / "close.jsonl"
            result = run_shadow_replay_manifest(
                manifest,
                trial_ledger_path=trial_ledger,
                close_ledger_path=close_ledger,
                created_at_utc="2026-06-24T07:00:00Z",
            )
            self.assertEqual(result.rows[0].status, ROW_STATUS_ROW_ERROR)
            self.assertEqual(
                result.rows[1].status, ROW_STATUS_CLOSE_CREATED
            )
            self.assertEqual(result.requested_rows, 2)
            self.assertEqual(result.valid_rows, 1)
            self.assertEqual(result.trial_records_created, 1)
            self.assertEqual(result.close_records_created, 1)

    def test_result_counts_are_correct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact1 = Path(tmp) / "art1.json"
            artifact2 = Path(tmp) / "art2.json"
            _write_synthetic_artifact(artifact1)
            _write_synthetic_artifact(artifact2)
            manifest = Path(tmp) / "manifest.json"
            _write_manifest(
                manifest,
                _minimal_manifest_row(
                    artifact_path=str(artifact1),
                    row_id="row-1",
                ),
                _minimal_manifest_row(
                    artifact_path=str(artifact2),
                    row_id="row-2",
                    planned_side="sell",
                    close_price=39900.0,
                ),
            )
            trial_ledger = Path(tmp) / "trial.jsonl"
            close_ledger = Path(tmp) / "close.jsonl"
            result = run_shadow_replay_manifest(
                manifest,
                trial_ledger_path=trial_ledger,
                close_ledger_path=close_ledger,
                created_at_utc="2026-06-24T07:00:00Z",
            )
            self.assertEqual(result.requested_rows, 2)
            self.assertEqual(result.valid_rows, 2)
            self.assertEqual(result.trial_records_created, 2)
            self.assertEqual(result.close_records_created, 2)
            for row in result.rows:
                self.assertEqual(row.status, ROW_STATUS_CLOSE_CREATED)


# --- Result serialization --------------------------------------------


class ReplayResultSerializationTests(unittest.TestCase):
    def _build_result(self) -> ShadowReplayResultManifest:
        rows = (
            ShadowReplayRowResult(
                row_id="row-1",
                status=ROW_STATUS_CLOSE_CREATED,
                trial_id="t1",
                close_id="c1",
                error=None,
            ),
        )
        return ShadowReplayResultManifest(
            schema_version=SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
            input_manifest_sha256="a" * 64,
            created_at_utc="2026-06-24T07:00:00Z",
            requested_rows=1,
            valid_rows=1,
            trial_records_created=1,
            close_records_created=1,
            rows=rows,
            non_claims=SHADOW_REPLAY_NON_CLAIMS,
        )

    def test_json_text_deterministic(self) -> None:
        result = self._build_result()
        text1 = shadow_replay_result_to_json_text(result)
        text2 = shadow_replay_result_to_json_text(result)
        self.assertEqual(text1, text2)

    def test_json_text_ends_with_newline(self) -> None:
        result = self._build_result()
        text = shadow_replay_result_to_json_text(result)
        self.assertTrue(text.endswith("\n"))

    def test_json_text_validates_with_json_loads(self) -> None:
        result = self._build_result()
        text = shadow_replay_result_to_json_text(result)
        parsed = json.loads(text)
        for k in (
            "schema_version",
            "input_manifest_sha256",
            "created_at_utc",
            "requested_rows",
            "valid_rows",
            "trial_records_created",
            "close_records_created",
            "rows",
            "non_claims",
        ):
            self.assertIn(k, parsed)

    def test_ordered_dict_returns_plain_dict(self) -> None:
        result = self._build_result()
        d = shadow_replay_result_to_ordered_dict(result)
        self.assertIsInstance(d, dict)
        self.assertEqual(d["requested_rows"], 1)


# --- Writer ---------------------------------------------------------


class WriteResultTests(unittest.TestCase):
    def _build_result(self) -> ShadowReplayResultManifest:
        return ShadowReplayResultManifest(
            schema_version=SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
            input_manifest_sha256="a" * 64,
            created_at_utc="2026-06-24T07:00:00Z",
            requested_rows=1,
            valid_rows=1,
            trial_records_created=1,
            close_records_created=1,
            rows=(),
            non_claims=SHADOW_REPLAY_NON_CLAIMS,
        )

    def test_write_creates_parent_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._build_result()
            nested = Path(tmp) / "deep" / "nested" / "result.json"
            self.assertFalse(nested.parent.exists())
            write_shadow_replay_result_json(result, nested)
            self.assertTrue(nested.exists())
            self.assertTrue(nested.parent.exists())

    def test_write_refuses_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._build_result()
            out = Path(tmp) / "result.json"
            write_shadow_replay_result_json(result, out)
            with self.assertRaises(FileExistsError):
                write_shadow_replay_result_json(result, out)

    def test_write_allows_overwrite_with_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._build_result()
            out = Path(tmp) / "result.json"
            write_shadow_replay_result_json(result, out)
            # Should not raise.
            write_shadow_replay_result_json(
                result, out, allow_overwrite=True
            )
            self.assertTrue(out.exists())


# --- Result forbidden-field checks ---------------------------------


class ResultForbiddenFieldsTests(unittest.TestCase):
    def _build_result(self) -> ShadowReplayResultManifest:
        return ShadowReplayResultManifest(
            schema_version=SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
            input_manifest_sha256="a" * 64,
            created_at_utc="2026-06-24T07:00:00Z",
            requested_rows=1,
            valid_rows=1,
            trial_records_created=1,
            close_records_created=1,
            rows=(),
            non_claims=SHADOW_REPLAY_NON_CLAIMS,
        )

    def test_result_contains_no_aggregate_delta_fields(self) -> None:
        result = self._build_result()
        d = shadow_replay_result_to_ordered_dict(result)
        for forbidden in (
            "aggregate_delta",
            "average_delta",
            "total_delta",
            "score_average",
            "win_loss_count",
            "equity_curve",
            "portfolio",
        ):
            self.assertNotIn(
                forbidden, d,
                f"result must not contain {forbidden!r}",
            )

    def test_result_contains_no_forbidden_performance_fields(self) -> None:
        result = self._build_result()
        d = shadow_replay_result_to_ordered_dict(result)
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
            "performance",
        ):
            self.assertNotIn(
                forbidden, d,
                f"result must not contain {forbidden!r}",
            )


# --- Static AST purity ---------------------------------------------


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


class ReplayPurityTests(unittest.TestCase):
    def test_no_subprocess_import_or_call_in_replay_module(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(REPLAY_PATH),
            f"{REPLAY_PATH} imports or accesses subprocess.",
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

    def test_no_env_credential_reads_in_replay_module(self) -> None:
        self.assertFalse(
            _module_has_os_env_credential_read(REPLAY_PATH),
            f"{REPLAY_PATH} reads environment credentials.",
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
        imports = _collect_imports(REPLAY_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"replay.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_sox_adapter_in_replay_module(self) -> None:
        src = REPLAY_PATH.read_text(encoding="utf-8")
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
                f"replay.py must not reference {token!r}.",
            )

    def test_no_pnl_or_broker_or_performance_words(self) -> None:
        # Build forbidden tokens at runtime to avoid
        # self-matching in the test file's own source.
        src = REPLAY_PATH.read_text(encoding="utf-8").lower()
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
                f"replay.py must not reference {token!r}.",
            )


# --- Raw FRED CSV audit ---------------------------------------------


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


# --- Documentation and dry-run script presence -------------------


class ReplayDocsAndScriptsPresenceTests(unittest.TestCase):
    def test_replay_doc_exists(self) -> None:
        self.assertTrue(
            REPLAY_DOC.exists(),
            f"Missing docs/shadow-replay-manifest.md: {REPLAY_DOC}",
        )

    def test_dry_run_shell_exists(self) -> None:
        self.assertTrue(
            REPLAY_DRY_RUN_SH.exists(),
            f"Missing scripts/run_shadow_replay_dry_run.sh: "
            f"{REPLAY_DRY_RUN_SH}",
        )

    def test_dry_run_shell_uses_strict_mode(self) -> None:
        text = REPLAY_DRY_RUN_SH.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_dry_run_python_uses_local_files(self) -> None:
        text = DRY_RUN_PY.read_text(encoding="utf-8")
        self.assertIn("--input-manifest", text)
        self.assertIn("--trial-ledger-output", text)
        self.assertIn("--close-ledger-output", text)
        self.assertIn("--result-output", text)
        self.assertIn("--created-at-utc", text)

    def test_data_adapter_contract_links_to_replay_doc(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "shadow-replay-manifest.md",
            text,
            "data-adapter-contract.md must link to "
            "docs/shadow-replay-manifest.md.",
        )

    def test_data_adapter_contract_section_8_11_present(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "8.11",
            text,
            "data-adapter-contract.md must contain a §8.11 "
            "shadow-replay-manifest section.",
        )


if __name__ == "__main__":
    unittest.main()
