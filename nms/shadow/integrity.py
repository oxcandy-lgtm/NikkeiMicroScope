"""Shadow replay integrity checker for NikkeiMicroScope.

This module compares a local shadow replay result manifest with the
local trial and close ledgers that the replay wrote.

The checker is intentionally narrow. It validates schema, row status,
count consistency, duplicate ledger identifiers, and result-to-ledger
references. It does not calculate scored-result metrics, does not
summarize outcome quality, and does not create or modify replay rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from nms.shadow.close import (
    SHADOW_CLOSE_NOT_EXECUTABLE,
    SHADOW_CLOSE_SCHEMA_VERSION,
)
from nms.shadow.ledger import (
    SHADOW_TRIAL_NOT_EXECUTABLE,
    SHADOW_TRIAL_SCHEMA_VERSION,
)
from nms.shadow.replay import (
    ROW_STATUS_CLOSE_CREATED,
    ROW_STATUS_ROW_ERROR,
    ROW_STATUS_TRIAL_CREATED,
    SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
)


SHADOW_REPLAY_INTEGRITY_REPORT_SCHEMA_VERSION = (
    "shadow-replay-integrity-report/1"
)

SHADOW_REPLAY_INTEGRITY_NON_CLAIMS: Tuple[str, ...] = (
    "not_backtest",
    "not_strategy_metric",
    "not_paper_execution",
    "not_live_trading",
    "not_venue_integration",
    "not_order_placement",
    "not_order_routing",
    "no_capital_account",
    "no_exposure_state",
    "no_delta_money_metric",
    "no_ratio_metric",
    "not_signal",
    "not_advice",
    "no_real_cash",
)

_ALLOWED_ROW_STATUSES = {
    ROW_STATUS_CLOSE_CREATED,
    ROW_STATUS_TRIAL_CREATED,
    ROW_STATUS_ROW_ERROR,
}


@dataclass(frozen=True)
class ShadowReplayIntegrityIssue:
    """A single integrity issue."""

    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ShadowReplayIntegrityReport:
    """Counts/status-only integrity report for a replay result."""

    schema_version: str
    ok: bool
    result_manifest_path: str
    trial_ledger_path: str
    close_ledger_path: str
    result_rows: int
    result_valid_rows: int
    result_trial_refs: int
    result_close_refs: int
    trial_ledger_records: int
    close_ledger_records: int
    issues: Tuple[ShadowReplayIntegrityIssue, ...]
    non_claims: Tuple[str, ...]


def _issue(code: str, path: str, message: str) -> ShadowReplayIntegrityIssue:
    return ShadowReplayIntegrityIssue(code=code, path=path, message=message)


def _is_non_bool_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _load_json_object(
    path: Path,
    *,
    label: str,
) -> Tuple[Optional[dict], Tuple[ShadowReplayIntegrityIssue, ...]]:
    issues: List[ShadowReplayIntegrityIssue] = []
    path = Path(path)
    if not path.exists():
        return None, (
            _issue(
                "missing_file",
                label,
                f"{label} does not exist: {path}",
            ),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, (
            _issue(
                "invalid_json",
                label,
                f"{label} is not valid JSON: {exc}",
            ),
        )
    if not isinstance(payload, dict):
        issues.append(
            _issue(
                "not_json_object",
                label,
                f"{label} must be a JSON object",
            )
        )
        return None, tuple(issues)
    return payload, tuple(issues)


def _load_jsonl_records(
    path: Path,
    *,
    label: str,
) -> Tuple[Tuple[dict, ...], Tuple[ShadowReplayIntegrityIssue, ...]]:
    issues: List[ShadowReplayIntegrityIssue] = []
    records: List[dict] = []
    path = Path(path)
    if not path.exists():
        return (), (
            _issue(
                "missing_file",
                label,
                f"{label} does not exist: {path}",
            ),
        )
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        line_path = f"{label}[line {lineno}]"
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(
                _issue(
                    "invalid_jsonl_line",
                    line_path,
                    f"{label} line {lineno} is not valid JSON: {exc}",
                )
            )
            continue
        if not isinstance(payload, dict):
            issues.append(
                _issue(
                    "jsonl_line_not_object",
                    line_path,
                    f"{label} line {lineno} must be a JSON object",
                )
            )
            continue
        records.append(payload)
    return tuple(records), tuple(issues)


def _index_by_id(
    records: Sequence[dict],
    *,
    id_key: str,
    label: str,
) -> Tuple[dict, Tuple[ShadowReplayIntegrityIssue, ...]]:
    issues: List[ShadowReplayIntegrityIssue] = []
    index: dict = {}
    seen: dict = {}
    for i, record in enumerate(records):
        item_path = f"{label}[{i}]"
        value = record.get(id_key)
        if not _is_non_empty_str(value):
            issues.append(
                _issue(
                    "missing_record_id",
                    item_path,
                    f"{id_key} must be a non-empty string",
                )
            )
            continue
        if value in seen:
            issues.append(
                _issue(
                    "duplicate_record_id",
                    item_path,
                    f"duplicate {id_key}: {value!r}",
                )
            )
            continue
        seen[value] = i
        index[value] = record
    return index, tuple(issues)


def _validate_result_manifest(
    result: Optional[dict],
) -> Tuple[
    Tuple[dict, ...],
    int,
    int,
    Tuple[ShadowReplayIntegrityIssue, ...],
]:
    issues: List[ShadowReplayIntegrityIssue] = []
    if result is None:
        return (), 0, 0, tuple(issues)

    schema_version = result.get("schema_version")
    if schema_version != SHADOW_REPLAY_RESULT_SCHEMA_VERSION:
        issues.append(
            _issue(
                "bad_result_schema_version",
                "result.schema_version",
                "result schema_version must be "
                f"{SHADOW_REPLAY_RESULT_SCHEMA_VERSION!r}; "
                f"got {schema_version!r}",
            )
        )

    rows_raw = result.get("rows")
    if not isinstance(rows_raw, list):
        issues.append(
            _issue(
                "bad_result_rows",
                "result.rows",
                "result rows must be a list",
            )
        )
        return (), 0, 0, tuple(issues)

    rows: List[dict] = []
    seen_row_ids = set()
    valid_rows = 0
    trial_refs = 0
    close_refs = 0
    for i, row in enumerate(rows_raw):
        row_path = f"result.rows[{i}]"
        if not isinstance(row, dict):
            issues.append(
                _issue(
                    "bad_result_row",
                    row_path,
                    "result row must be a JSON object",
                )
            )
            continue

        row_id = row.get("row_id")
        if not _is_non_empty_str(row_id):
            issues.append(
                _issue(
                    "bad_result_row_id",
                    f"{row_path}.row_id",
                    "row_id must be a non-empty string",
                )
            )
        elif row_id in seen_row_ids:
            issues.append(
                _issue(
                    "duplicate_result_row_id",
                    f"{row_path}.row_id",
                    f"duplicate row_id: {row_id!r}",
                )
            )
        else:
            seen_row_ids.add(row_id)

        status = row.get("status")
        if status not in _ALLOWED_ROW_STATUSES:
            issues.append(
                _issue(
                    "bad_result_row_status",
                    f"{row_path}.status",
                    f"unknown row status: {status!r}",
                )
            )

        trial_id = row.get("trial_id")
        close_id = row.get("close_id")
        error = row.get("error")

        if trial_id is not None:
            if _is_non_empty_str(trial_id):
                trial_refs += 1
            else:
                issues.append(
                    _issue(
                        "bad_result_trial_id",
                        f"{row_path}.trial_id",
                        "trial_id must be null or a non-empty string",
                    )
                )

        if close_id is not None:
            if _is_non_empty_str(close_id):
                close_refs += 1
            else:
                issues.append(
                    _issue(
                        "bad_result_close_id",
                        f"{row_path}.close_id",
                        "close_id must be null or a non-empty string",
                    )
                )

        if status == ROW_STATUS_CLOSE_CREATED:
            valid_rows += 1
            if not _is_non_empty_str(trial_id):
                issues.append(
                    _issue(
                        "close_row_missing_trial_id",
                        f"{row_path}.trial_id",
                        "close_created row requires trial_id",
                    )
                )
            if not _is_non_empty_str(close_id):
                issues.append(
                    _issue(
                        "close_row_missing_close_id",
                        f"{row_path}.close_id",
                        "close_created row requires close_id",
                    )
                )
            if error is not None:
                issues.append(
                    _issue(
                        "close_row_has_error",
                        f"{row_path}.error",
                        "close_created row must have error=null",
                    )
                )
        elif status == ROW_STATUS_TRIAL_CREATED:
            valid_rows += 1
            if not _is_non_empty_str(trial_id):
                issues.append(
                    _issue(
                        "trial_row_missing_trial_id",
                        f"{row_path}.trial_id",
                        "trial_created row requires trial_id",
                    )
                )
            if close_id is not None:
                issues.append(
                    _issue(
                        "trial_row_has_close_id",
                        f"{row_path}.close_id",
                        "trial_created row must have close_id=null",
                    )
                )
            if error is not None:
                issues.append(
                    _issue(
                        "trial_row_has_error",
                        f"{row_path}.error",
                        "trial_created row must have error=null",
                    )
                )
        elif status == ROW_STATUS_ROW_ERROR:
            if close_id is not None:
                issues.append(
                    _issue(
                        "error_row_has_close_id",
                        f"{row_path}.close_id",
                        "row_error row must have close_id=null",
                    )
                )
            if not _is_non_empty_str(error):
                issues.append(
                    _issue(
                        "error_row_missing_error",
                        f"{row_path}.error",
                        "row_error row requires a non-empty error string",
                    )
                )

        rows.append(row)

    expected_counts = {
        "requested_rows": len(rows),
        "valid_rows": valid_rows,
        "trial_records_created": trial_refs,
        "close_records_created": sum(
            1 for row in rows
            if row.get("status") == ROW_STATUS_CLOSE_CREATED
        ),
    }
    for key, expected in expected_counts.items():
        actual = result.get(key)
        if not _is_non_bool_int(actual):
            issues.append(
                _issue(
                    "bad_result_count",
                    f"result.{key}",
                    f"{key} must be an integer; got {actual!r}",
                )
            )
            continue
        if actual != expected:
            issues.append(
                _issue(
                    "result_count_mismatch",
                    f"result.{key}",
                    f"{key}={actual!r}; expected {expected}",
                )
            )

    return tuple(rows), trial_refs, close_refs, tuple(issues)


def _validate_trial_ledger_records(
    records: Sequence[dict],
) -> Tuple[ShadowReplayIntegrityIssue, ...]:
    issues: List[ShadowReplayIntegrityIssue] = []
    for i, record in enumerate(records):
        path = f"trial_ledger[{i}]"
        if record.get("schema_version") != SHADOW_TRIAL_SCHEMA_VERSION:
            issues.append(
                _issue(
                    "bad_trial_schema_version",
                    f"{path}.schema_version",
                    "trial record schema_version must be "
                    f"{SHADOW_TRIAL_SCHEMA_VERSION!r}",
                )
            )
        if record.get("executable") is not False:
            issues.append(
                _issue(
                    "trial_executable_not_false",
                    f"{path}.executable",
                    "trial record executable must be false",
                )
            )
        if record.get("blocked_reason") != SHADOW_TRIAL_NOT_EXECUTABLE:
            issues.append(
                _issue(
                    "bad_trial_blocked_reason",
                    f"{path}.blocked_reason",
                    "trial record blocked_reason must be "
                    f"{SHADOW_TRIAL_NOT_EXECUTABLE!r}",
                )
            )
    return tuple(issues)


def _validate_close_ledger_records(
    records: Sequence[dict],
) -> Tuple[ShadowReplayIntegrityIssue, ...]:
    issues: List[ShadowReplayIntegrityIssue] = []
    for i, record in enumerate(records):
        path = f"close_ledger[{i}]"
        if record.get("schema_version") != SHADOW_CLOSE_SCHEMA_VERSION:
            issues.append(
                _issue(
                    "bad_close_schema_version",
                    f"{path}.schema_version",
                    "close record schema_version must be "
                    f"{SHADOW_CLOSE_SCHEMA_VERSION!r}",
                )
            )
        if record.get("executable") is not False:
            issues.append(
                _issue(
                    "close_executable_not_false",
                    f"{path}.executable",
                    "close record executable must be false",
                )
            )
        if record.get("blocked_reason") != SHADOW_CLOSE_NOT_EXECUTABLE:
            issues.append(
                _issue(
                    "bad_close_blocked_reason",
                    f"{path}.blocked_reason",
                    "close record blocked_reason must be "
                    f"{SHADOW_CLOSE_NOT_EXECUTABLE!r}",
                )
            )
        if not _is_non_empty_str(record.get("trial_id")):
            issues.append(
                _issue(
                    "close_record_missing_trial_id",
                    f"{path}.trial_id",
                    "close record trial_id must be a non-empty string",
                )
            )
    return tuple(issues)


def _validate_result_references(
    rows: Sequence[dict],
    trial_index: dict,
    close_index: dict,
) -> Tuple[ShadowReplayIntegrityIssue, ...]:
    issues: List[ShadowReplayIntegrityIssue] = []
    for i, row in enumerate(rows):
        row_path = f"result.rows[{i}]"
        trial_id = row.get("trial_id")
        close_id = row.get("close_id")
        if _is_non_empty_str(trial_id) and trial_id not in trial_index:
            issues.append(
                _issue(
                    "missing_trial_record",
                    f"{row_path}.trial_id",
                    f"trial_id {trial_id!r} is not present in trial ledger",
                )
            )
        if _is_non_empty_str(close_id):
            close_record = close_index.get(close_id)
            if close_record is None:
                issues.append(
                    _issue(
                        "missing_close_record",
                        f"{row_path}.close_id",
                        f"close_id {close_id!r} is not present in close ledger",
                    )
                )
            elif (
                _is_non_empty_str(trial_id)
                and close_record.get("trial_id") != trial_id
            ):
                issues.append(
                    _issue(
                        "close_trial_mismatch",
                        f"{row_path}.close_id",
                        "close record trial_id does not match result row "
                        f"trial_id {trial_id!r}",
                    )
                )
    return tuple(issues)


def _validate_close_ledger_trial_refs(
    close_records: Sequence[dict],
    trial_index: dict,
) -> Tuple[ShadowReplayIntegrityIssue, ...]:
    issues: List[ShadowReplayIntegrityIssue] = []
    for i, record in enumerate(close_records):
        trial_id = record.get("trial_id")
        if _is_non_empty_str(trial_id) and trial_id not in trial_index:
            issues.append(
                _issue(
                    "close_record_missing_source_trial",
                    f"close_ledger[{i}].trial_id",
                    f"close ledger trial_id {trial_id!r} is missing "
                    "from trial ledger",
                )
            )
    return tuple(issues)


def build_shadow_replay_integrity_report(
    result_manifest_path: Path,
    *,
    trial_ledger_path: Path,
    close_ledger_path: Path,
) -> ShadowReplayIntegrityReport:
    """Build an integrity report for one replay result.

    Extra records in the ledgers are allowed because ledgers are
    append-only and may contain earlier local runs. The checker requires
    all result-referenced ids to exist and rejects duplicate ledger ids.
    """

    result_manifest_path = Path(result_manifest_path)
    trial_ledger_path = Path(trial_ledger_path)
    close_ledger_path = Path(close_ledger_path)

    issues: List[ShadowReplayIntegrityIssue] = []
    result, result_load_issues = _load_json_object(
        result_manifest_path, label="result_manifest"
    )
    issues.extend(result_load_issues)

    trial_records, trial_load_issues = _load_jsonl_records(
        trial_ledger_path, label="trial_ledger"
    )
    issues.extend(trial_load_issues)

    close_records, close_load_issues = _load_jsonl_records(
        close_ledger_path, label="close_ledger"
    )
    issues.extend(close_load_issues)

    rows, trial_refs, close_refs, result_issues = _validate_result_manifest(
        result
    )
    issues.extend(result_issues)

    trial_index, trial_index_issues = _index_by_id(
        trial_records, id_key="trial_id", label="trial_ledger"
    )
    issues.extend(trial_index_issues)

    close_index, close_index_issues = _index_by_id(
        close_records, id_key="close_id", label="close_ledger"
    )
    issues.extend(close_index_issues)

    issues.extend(_validate_trial_ledger_records(trial_records))
    issues.extend(_validate_close_ledger_records(close_records))
    issues.extend(_validate_result_references(rows, trial_index, close_index))
    issues.extend(
        _validate_close_ledger_trial_refs(close_records, trial_index)
    )

    return ShadowReplayIntegrityReport(
        schema_version=SHADOW_REPLAY_INTEGRITY_REPORT_SCHEMA_VERSION,
        ok=len(issues) == 0,
        result_manifest_path=str(result_manifest_path),
        trial_ledger_path=str(trial_ledger_path),
        close_ledger_path=str(close_ledger_path),
        result_rows=len(rows),
        result_valid_rows=sum(
            1 for row in rows
            if row.get("status") != ROW_STATUS_ROW_ERROR
        ),
        result_trial_refs=trial_refs,
        result_close_refs=close_refs,
        trial_ledger_records=len(trial_records),
        close_ledger_records=len(close_records),
        issues=tuple(issues),
        non_claims=SHADOW_REPLAY_INTEGRITY_NON_CLAIMS,
    )


def shadow_replay_integrity_report_to_ordered_dict(
    report: ShadowReplayIntegrityReport,
) -> dict:
    """Convert a report to a plain dict for JSON serialization."""

    return {
        "close_ledger_path": report.close_ledger_path,
        "close_ledger_records": report.close_ledger_records,
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "path": issue.path,
            }
            for issue in report.issues
        ],
        "non_claims": list(report.non_claims),
        "ok": report.ok,
        "result_close_refs": report.result_close_refs,
        "result_manifest_path": report.result_manifest_path,
        "result_rows": report.result_rows,
        "result_trial_refs": report.result_trial_refs,
        "result_valid_rows": report.result_valid_rows,
        "schema_version": report.schema_version,
        "trial_ledger_path": report.trial_ledger_path,
        "trial_ledger_records": report.trial_ledger_records,
    }


def shadow_replay_integrity_report_to_json_text(
    report: ShadowReplayIntegrityReport,
) -> str:
    """Serialize a report to deterministic UTF-8 JSON text."""

    text = json.dumps(
        shadow_replay_integrity_report_to_ordered_dict(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_shadow_replay_integrity_report_json(
    report: ShadowReplayIntegrityReport,
    output_path: Path,
    *,
    allow_overwrite: bool = False,
) -> Path:
    """Write a replay integrity report to a local JSON file."""

    output_path = Path(output_path)
    if output_path.exists() and not allow_overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing file: {output_path}. "
            "Pass allow_overwrite=True to override."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(shadow_replay_integrity_report_to_json_text(report))
    return output_path
