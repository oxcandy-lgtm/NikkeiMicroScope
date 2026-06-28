"""Tests for the shadow replay integrity checker."""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from nms.shadow.integrity import (
    SHADOW_REPLAY_INTEGRITY_NON_CLAIMS,
    SHADOW_REPLAY_INTEGRITY_REPORT_SCHEMA_VERSION,
    ShadowReplayIntegrityReport,
    build_shadow_replay_integrity_report,
    shadow_replay_integrity_report_to_json_text,
    shadow_replay_integrity_report_to_ordered_dict,
    write_shadow_replay_integrity_report_json,
)
from nms.shadow.replay import (
    ROW_STATUS_CLOSE_CREATED,
    ROW_STATUS_ROW_ERROR,
    ROW_STATUS_TRIAL_CREATED,
    SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRITY_PATH = REPO_ROOT / "nms" / "shadow" / "integrity.py"
INTEGRITY_CLI = REPO_ROOT / "scripts" / "check_shadow_replay_integrity.py"
INTEGRITY_DRY_RUN = (
    REPO_ROOT / "scripts" / "run_shadow_replay_integrity_dry_run.sh"
)
INTEGRITY_DOC = REPO_ROOT / "docs" / "shadow-replay-integrity-checker.md"


def _trial_record(trial_id: str) -> dict:
    return {
        "schema_version": "shadow-trial/1",
        "trial_id": trial_id,
        "executable": False,
        "blocked_reason": "shadow_trial_not_executable",
    }


def _close_record(close_id: str, trial_id: str) -> dict:
    return {
        "schema_version": "shadow-close/1",
        "close_id": close_id,
        "trial_id": trial_id,
        "executable": False,
        "blocked_reason": "shadow_close_not_executable",
    }


def _result_row(
    row_id: str,
    status: str,
    trial_id: str | None,
    close_id: str | None,
    error: str | None = None,
) -> dict:
    return {
        "row_id": row_id,
        "status": status,
        "trial_id": trial_id,
        "close_id": close_id,
        "error": error,
    }


def _result_payload(*rows: dict) -> dict:
    trial_refs = sum(1 for row in rows if row.get("trial_id") is not None)
    close_count = sum(
        1 for row in rows
        if row.get("status") == ROW_STATUS_CLOSE_CREATED
    )
    valid_rows = sum(
        1 for row in rows
        if row.get("status") != ROW_STATUS_ROW_ERROR
    )
    return {
        "schema_version": SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
        "input_manifest_sha256": "a" * 64,
        "created_at_utc": "2026-06-24T07:00:00Z",
        "requested_rows": len(rows),
        "valid_rows": valid_rows,
        "trial_records_created": trial_refs,
        "close_records_created": close_count,
        "rows": list(rows),
        "non_claims": [],
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_jsonl(path: Path, *records: dict) -> Path:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            fh.write("\n")
    return path


class IntegrityReportTests(unittest.TestCase):
    def test_valid_result_and_ledgers_are_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _write_json(
                root / "result.json",
                _result_payload(
                    _result_row(
                        "row-1",
                        ROW_STATUS_CLOSE_CREATED,
                        "trial-1",
                        "close-1",
                    ),
                    _result_row(
                        "row-2",
                        ROW_STATUS_TRIAL_CREATED,
                        "trial-2",
                        None,
                    ),
                ),
            )
            trial = _write_jsonl(
                root / "trial.jsonl",
                _trial_record("trial-1"),
                _trial_record("trial-2"),
            )
            close = _write_jsonl(
                root / "close.jsonl",
                _close_record("close-1", "trial-1"),
            )
            report = build_shadow_replay_integrity_report(
                result,
                trial_ledger_path=trial,
                close_ledger_path=close,
            )
            self.assertTrue(report.ok)
            self.assertEqual(report.result_rows, 2)
            self.assertEqual(report.result_valid_rows, 2)
            self.assertEqual(report.result_trial_refs, 2)
            self.assertEqual(report.result_close_refs, 1)
            self.assertEqual(report.trial_ledger_records, 2)
            self.assertEqual(report.close_ledger_records, 1)
            self.assertEqual(report.issues, ())

    def test_missing_result_referenced_trial_is_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _write_json(
                root / "result.json",
                _result_payload(
                    _result_row(
                        "row-1",
                        ROW_STATUS_TRIAL_CREATED,
                        "trial-missing",
                        None,
                    ),
                ),
            )
            trial = _write_jsonl(root / "trial.jsonl")
            close = _write_jsonl(root / "close.jsonl")
            report = build_shadow_replay_integrity_report(
                result,
                trial_ledger_path=trial,
                close_ledger_path=close,
            )
            self.assertFalse(report.ok)
            self.assertIn(
                "missing_trial_record",
                {issue.code for issue in report.issues},
            )

    def test_duplicate_trial_id_is_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _write_json(
                root / "result.json",
                _result_payload(
                    _result_row(
                        "row-1",
                        ROW_STATUS_TRIAL_CREATED,
                        "trial-1",
                        None,
                    ),
                ),
            )
            trial = _write_jsonl(
                root / "trial.jsonl",
                _trial_record("trial-1"),
                _trial_record("trial-1"),
            )
            close = _write_jsonl(root / "close.jsonl")
            report = build_shadow_replay_integrity_report(
                result,
                trial_ledger_path=trial,
                close_ledger_path=close,
            )
            self.assertFalse(report.ok)
            self.assertIn(
                "duplicate_record_id",
                {issue.code for issue in report.issues},
            )

    def test_result_count_mismatch_is_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _result_payload(
                _result_row(
                    "row-1",
                    ROW_STATUS_TRIAL_CREATED,
                    "trial-1",
                    None,
                ),
            )
            payload["trial_records_created"] = 99
            result = _write_json(root / "result.json", payload)
            trial = _write_jsonl(root / "trial.jsonl", _trial_record("trial-1"))
            close = _write_jsonl(root / "close.jsonl")
            report = build_shadow_replay_integrity_report(
                result,
                trial_ledger_path=trial,
                close_ledger_path=close,
            )
            self.assertFalse(report.ok)
            self.assertIn(
                "result_count_mismatch",
                {issue.code for issue in report.issues},
            )

    def test_close_record_trial_mismatch_is_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _write_json(
                root / "result.json",
                _result_payload(
                    _result_row(
                        "row-1",
                        ROW_STATUS_CLOSE_CREATED,
                        "trial-1",
                        "close-1",
                    ),
                ),
            )
            trial = _write_jsonl(root / "trial.jsonl", _trial_record("trial-1"))
            close = _write_jsonl(
                root / "close.jsonl",
                _close_record("close-1", "different-trial"),
            )
            report = build_shadow_replay_integrity_report(
                result,
                trial_ledger_path=trial,
                close_ledger_path=close,
            )
            self.assertFalse(report.ok)
            self.assertIn(
                "close_trial_mismatch",
                {issue.code for issue in report.issues},
            )

    def test_error_row_with_trial_id_counts_trial_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _write_json(
                root / "result.json",
                _result_payload(
                    _result_row(
                        "row-1",
                        ROW_STATUS_ROW_ERROR,
                        "trial-1",
                        None,
                        error="close construction failed",
                    ),
                ),
            )
            trial = _write_jsonl(root / "trial.jsonl", _trial_record("trial-1"))
            close = _write_jsonl(root / "close.jsonl")
            report = build_shadow_replay_integrity_report(
                result,
                trial_ledger_path=trial,
                close_ledger_path=close,
            )
            self.assertTrue(report.ok)
            self.assertEqual(report.result_valid_rows, 0)
            self.assertEqual(report.result_trial_refs, 1)
            self.assertEqual(report.result_close_refs, 0)


class IntegritySerializationTests(unittest.TestCase):
    def _report(self) -> ShadowReplayIntegrityReport:
        return ShadowReplayIntegrityReport(
            schema_version=SHADOW_REPLAY_INTEGRITY_REPORT_SCHEMA_VERSION,
            ok=True,
            result_manifest_path="result.json",
            trial_ledger_path="trial.jsonl",
            close_ledger_path="close.jsonl",
            result_rows=1,
            result_valid_rows=1,
            result_trial_refs=1,
            result_close_refs=0,
            trial_ledger_records=1,
            close_ledger_records=0,
            issues=(),
            non_claims=SHADOW_REPLAY_INTEGRITY_NON_CLAIMS,
        )

    def test_ordered_dict_contains_counts_only_surface(self) -> None:
        d = shadow_replay_integrity_report_to_ordered_dict(self._report())
        self.assertEqual(d["schema_version"], "shadow-replay-integrity-report/1")
        self.assertEqual(d["ok"], True)
        self.assertEqual(d["result_rows"], 1)
        for forbidden in (
            "aggregate_delta",
            "average_delta",
            "total_delta",
            "score_average",
        ):
            self.assertNotIn(forbidden, d)

    def test_json_text_deterministic_and_newline(self) -> None:
        report = self._report()
        text1 = shadow_replay_integrity_report_to_json_text(report)
        text2 = shadow_replay_integrity_report_to_json_text(report)
        self.assertEqual(text1, text2)
        self.assertTrue(text1.endswith("\n"))
        self.assertEqual(json.loads(text1)["ok"], True)

    def test_writer_refuses_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            write_shadow_replay_integrity_report_json(self._report(), out)
            with self.assertRaises(FileExistsError):
                write_shadow_replay_integrity_report_json(self._report(), out)

    def test_writer_allows_overwrite_with_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            write_shadow_replay_integrity_report_json(self._report(), out)
            write_shadow_replay_integrity_report_json(
                self._report(), out, allow_overwrite=True
            )
            self.assertTrue(out.exists())


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
    tree = ast.parse(
        py_path.read_text(encoding="utf-8"), filename=str(py_path)
    )
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module.split(".")[0])
    return names


class IntegrityPurityTests(unittest.TestCase):
    def test_no_subprocess_import_or_call_in_module_or_cli(self) -> None:
        for path in (INTEGRITY_PATH, INTEGRITY_CLI, Path(__file__)):
            self.assertFalse(
                _module_has_subprocess_use(path),
                f"{path} imports or accesses subprocess.",
            )

    def test_no_env_credential_reads_in_module_or_cli(self) -> None:
        for path in (INTEGRITY_PATH, INTEGRITY_CLI):
            self.assertFalse(
                _module_has_os_env_credential_read(path),
                f"{path} reads environment credentials.",
            )

    def test_no_forbidden_imports_in_module(self) -> None:
        forbidden = {
            "requests", "httpx", "aiohttp", "dotenv",
            "subprocess", "os", "shutil", "shelve", "pickle",
            "ib_insync", "ccxt", "alpaca_trade_api", "metatrader5",
            "urllib", "urllib3", "yfinance", "pandas",
        }
        imports = _collect_imports(INTEGRITY_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"integrity.py imports forbidden modules: {sorted(bad)}",
        )


class IntegrityDocsAndScriptsTests(unittest.TestCase):
    def test_integrity_doc_exists(self) -> None:
        self.assertTrue(INTEGRITY_DOC.exists())

    def test_integrity_cli_exists(self) -> None:
        self.assertTrue(INTEGRITY_CLI.exists())
        text = INTEGRITY_CLI.read_text(encoding="utf-8")
        self.assertIn("--result-manifest", text)
        self.assertIn("--trial-ledger", text)
        self.assertIn("--close-ledger", text)
        self.assertIn("--report-output", text)

    def test_integrity_dry_run_exists_and_strict(self) -> None:
        self.assertTrue(INTEGRITY_DRY_RUN.exists())
        text = INTEGRITY_DRY_RUN.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)
        self.assertIn("check_shadow_replay_integrity.py", text)


if __name__ == "__main__":
    unittest.main()
