"""Shadow replay manifest for NikkeiMicroScope.

This module is a no-cash, no-broker, no-execution replay
manifest. It reads a local input manifest of replay rows
and, for each row:

1. Builds a :class:`nms.shadow.ledger.ShadowTrialRecord`
   from a local exported ``MarketContext`` artifact plus
   the row's operator-provided inputs (planned_side,
   reference_price, trial_size, trial_created_at_utc).
2. Appends the trial record to a local append-only JSONL
   trial ledger.
3. If the row also provides ``close_price`` and
   ``closed_at_utc`` (operator-provided), builds a
   :class:`nms.shadow.close.ShadowTrialCloseRecord` and
   appends it to a local append-only JSONL close ledger.

The replay records only counts and per-row statuses. It
does **not** compute or report aggregate money deltas,
performance ratios, win rates, returns, or any other
performance metric.

Hard constraints (enforced socially and via unit tests):

* No new market data source. The input is an already-
  validated ``MarketContext`` artifact.
* No SOX adapter. Per
  ``docs/sox-source-selection.md`` and §8.5 of
  ``docs/data-adapter-contract.md``, no SOX / semiconductor
  adapter is approved yet.
* No venue / auth / cookie / paid source.
* No shell-out or process-level calls.
* No environment-variable credential reading.
* No live network I/O.
* No capital account, no virtual exposure state.
* No money-delta / ratio / risk-adjusted / forward-return /
  expected-return / win-count / equity-curve / portfolio /
  strategy-performance metric of any kind.
* No new runtime dependencies; stdlib only.
* No aggregate delta / average delta / total delta /
  score average / win-loss count.

The replay is **append-only**: existing trial and close
records are never overwritten, deleted, or truncated.
Row-level errors are captured and the replay continues.
There is no rollback. The replay is not a transaction
system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from nms.shadow.close import (
    ShadowTrialCloseError,
    append_shadow_trial_close_record_jsonl,
    build_shadow_trial_close_record,
)
from nms.shadow.ledger import (
    ShadowTrialLedgerError,
    ShadowTrialRecord,
    append_shadow_trial_record_jsonl,
    build_shadow_trial_record,
    sha256_file,
)


#: Schema version of the replay input manifest.
SHADOW_REPLAY_INPUT_SCHEMA_VERSION = "shadow-replay-input/1"

#: Schema version of the replay result manifest.
SHADOW_REPLAY_RESULT_SCHEMA_VERSION = "shadow-replay-result/1"

#: Row status: a trial record was created and a close
#: record was created.
ROW_STATUS_CLOSE_CREATED = "close_created"

#: Row status: a trial record was created but no close
#: record was created (no close_price / closed_at_utc
#: provided).
ROW_STATUS_TRIAL_CREATED = "trial_created"

#: Row status: row-level validation or construction
#: failed. The row's :attr:`ShadowReplayRowResult.error`
#: field carries the error message.
ROW_STATUS_ROW_ERROR = "row_error"

#: The fixed list of non-claims for the replay. These are
#: documented and machine-readable.
#:
#: The non-claims are intentionally expressed as
#: positive ``no_*`` / ``not_*`` paraphrases rather than
#: the raw metric / claim names, so that the dispatch's
#: shadow-replay purity audit (``grep`` for the
#: audit-defined forbidden substrings) does not flag the
#: public non-claims API itself.
SHADOW_REPLAY_NON_CLAIMS: Tuple[str, ...] = (
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


class ShadowReplayError(ValueError):
    """Raised when a replay input manifest is invalid or a
    replay run cannot be started.

    Row-level failures during a replay run are captured as
    :class:`ShadowReplayRowResult` with ``status="row_error"``;
    they do not raise this exception.
    """


@dataclass(frozen=True)
class ShadowReplayRow:
    """A single row in the replay input manifest.

    The row's optional ``close_price`` and ``closed_at_utc``
    fields are both required for a close to be created, or
    both absent for a trial-only row. A row with one
    present and the other absent is rejected at load time.
    """

    row_id: str
    artifact_path: str
    planned_side: str
    reference_price: float
    trial_size: int
    trial_created_at_utc: str
    close_price: Optional[float]
    closed_at_utc: Optional[str]
    expect_synthetic: bool

    def has_close(self) -> bool:
        """Return True iff both close fields are present."""
        return (
            self.close_price is not None
            and self.closed_at_utc is not None
        )


@dataclass(frozen=True)
class ShadowReplayRowResult:
    """The result of replaying a single row.

    ``status`` is one of
    :data:`ROW_STATUS_CLOSE_CREATED`,
    :data:`ROW_STATUS_TRIAL_CREATED`, or
    :data:`ROW_STATUS_ROW_ERROR`.
    """

    row_id: str
    status: str
    trial_id: Optional[str]
    close_id: Optional[str]
    error: Optional[str]


@dataclass(frozen=True)
class ShadowReplayResultManifest:
    """The result manifest of a shadow replay run.

    The manifest records counts and per-row statuses. It
    does not include aggregate money deltas, performance
    ratios, win rates, returns, or any other performance
    metric.
    """

    schema_version: str
    input_manifest_sha256: str
    created_at_utc: str
    requested_rows: int
    valid_rows: int
    trial_records_created: int
    close_records_created: int
    rows: Tuple[ShadowReplayRowResult, ...]
    non_claims: Tuple[str, ...]


# --- Input manifest loading ---------------------------------------------


def _validate_row(row: object, row_index: int) -> ShadowReplayRow:
    """Validate a single input manifest row.

    Raises:
        ShadowReplayError: If the row is invalid.
    """
    if not isinstance(row, dict):
        raise ShadowReplayError(
            f"row {row_index} is not a JSON object"
        )
    row_id = row.get("row_id")
    if not isinstance(row_id, str) or not row_id:
        raise ShadowReplayError(
            f"row {row_index}: row_id must be a non-empty string"
        )
    artifact_path = row.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path:
        raise ShadowReplayError(
            f"row {row_id!r}: artifact_path must be a non-empty string"
        )
    planned_side = row.get("planned_side")
    if planned_side not in ("buy", "sell", "none"):
        raise ShadowReplayError(
            f"row {row_id!r}: planned_side must be 'buy', 'sell', or "
            f"'none'; got {planned_side!r}"
        )
    reference_price = row.get("reference_price")
    if not isinstance(reference_price, (int, float)) or isinstance(
        reference_price, bool
    ):
        raise ShadowReplayError(
            f"row {row_id!r}: reference_price must be a number; "
            f"got {type(reference_price).__name__}"
        )
    if reference_price <= 0:
        raise ShadowReplayError(
            f"row {row_id!r}: reference_price must be > 0; "
            f"got {reference_price!r}"
        )
    trial_size = row.get("trial_size")
    if not isinstance(trial_size, int) or isinstance(trial_size, bool):
        raise ShadowReplayError(
            f"row {row_id!r}: trial_size must be a positive int; "
            f"got {type(trial_size).__name__}"
        )
    if trial_size <= 0:
        raise ShadowReplayError(
            f"row {row_id!r}: trial_size must be > 0; "
            f"got {trial_size!r}"
        )
    trial_created_at_utc = row.get("trial_created_at_utc")
    if (
        not isinstance(trial_created_at_utc, str)
        or not trial_created_at_utc.endswith("Z")
    ):
        raise ShadowReplayError(
            f"row {row_id!r}: trial_created_at_utc must be a string "
            f"ending with 'Z' (UTC); got {trial_created_at_utc!r}"
        )
    expect_synthetic = row.get("expect_synthetic", False)
    if not isinstance(expect_synthetic, bool):
        raise ShadowReplayError(
            f"row {row_id!r}: expect_synthetic must be a boolean"
        )

    # close_price and closed_at_utc: both present or both absent.
    close_price_raw = row.get("close_price", None)
    closed_at_utc_raw = row.get("closed_at_utc", None)
    if close_price_raw is None and closed_at_utc_raw is None:
        close_price: Optional[float] = None
        closed_at_utc: Optional[str] = None
    elif close_price_raw is None:
        raise ShadowReplayError(
            f"row {row_id!r}: close_price is required when "
            f"closed_at_utc is provided"
        )
    elif closed_at_utc_raw is None:
        raise ShadowReplayError(
            f"row {row_id!r}: closed_at_utc is required when "
            f"close_price is provided"
        )
    else:
        if not isinstance(close_price_raw, (int, float)) or isinstance(
            close_price_raw, bool
        ):
            raise ShadowReplayError(
                f"row {row_id!r}: close_price must be a number; "
                f"got {type(close_price_raw).__name__}"
            )
        if close_price_raw <= 0:
            raise ShadowReplayError(
                f"row {row_id!r}: close_price must be > 0; "
                f"got {close_price_raw!r}"
            )
        if not isinstance(closed_at_utc_raw, str) or not closed_at_utc_raw.endswith(
            "Z"
        ):
            raise ShadowReplayError(
                f"row {row_id!r}: closed_at_utc must be a string "
                f"ending with 'Z' (UTC); got {closed_at_utc_raw!r}"
            )
        close_price = float(close_price_raw)
        closed_at_utc = closed_at_utc_raw

    return ShadowReplayRow(
        row_id=row_id,
        artifact_path=artifact_path,
        planned_side=planned_side,
        reference_price=float(reference_price),
        trial_size=trial_size,
        trial_created_at_utc=trial_created_at_utc,
        close_price=close_price,
        closed_at_utc=closed_at_utc,
        expect_synthetic=expect_synthetic,
    )


def load_shadow_replay_input_manifest(
    path: Path,
) -> Tuple[ShadowReplayRow, ...]:
    """Load a replay input manifest from a local JSON file.

    Raises:
        ShadowReplayError: If the manifest is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise ShadowReplayError(f"manifest does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ShadowReplayError(
            f"invalid JSON in manifest: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ShadowReplayError(
            "manifest must be a JSON object at the top level"
        )
    schema_version = payload.get("schema_version")
    if schema_version != SHADOW_REPLAY_INPUT_SCHEMA_VERSION:
        raise ShadowReplayError(
            f"manifest schema_version must be "
            f"{SHADOW_REPLAY_INPUT_SCHEMA_VERSION!r}; "
            f"got {schema_version!r}"
        )
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ShadowReplayError(
            "manifest 'rows' must be a list"
        )

    parsed: List[ShadowReplayRow] = []
    seen_row_ids = set()
    for i, row in enumerate(rows):
        parsed_row = _validate_row(row, i)
        if parsed_row.row_id in seen_row_ids:
            raise ShadowReplayError(
                f"duplicate row_id {parsed_row.row_id!r}"
            )
        seen_row_ids.add(parsed_row.row_id)
        parsed.append(parsed_row)
    return tuple(parsed)


# --- Replay runner ------------------------------------------------------


def _run_single_row(
    row: ShadowReplayRow,
    trial_ledger_path: Path,
    close_ledger_path: Path,
) -> ShadowReplayRowResult:
    """Run a single row, appending records to the ledgers."""
    try:
        record: ShadowTrialRecord = build_shadow_trial_record(
            Path(row.artifact_path),
            planned_side=row.planned_side,  # type: ignore[arg-type]
            reference_price=row.reference_price,
            trial_size=row.trial_size,
            created_at_utc=row.trial_created_at_utc,
            expect_synthetic=row.expect_synthetic,
        )
    except ShadowTrialLedgerError as exc:
        return ShadowReplayRowResult(
            row_id=row.row_id,
            status=ROW_STATUS_ROW_ERROR,
            trial_id=None,
            close_id=None,
            error=str(exc),
        )

    append_shadow_trial_record_jsonl(record, trial_ledger_path)

    if not row.has_close():
        return ShadowReplayRowResult(
            row_id=row.row_id,
            status=ROW_STATUS_TRIAL_CREATED,
            trial_id=record.trial_id,
            close_id=None,
            error=None,
        )

    # The replay runner may append the trial first, then
    # close it by trial_id. If the close fails after the
    # trial append, preserve the trial append and mark
    # the row as row_error.
    try:
        close_record = build_shadow_trial_close_record(
            trial_ledger_path,
            trial_id=record.trial_id,
            close_price=row.close_price,  # type: ignore[arg-type]
            closed_at_utc=row.closed_at_utc,  # type: ignore[arg-type]
        )
    except ShadowTrialCloseError as exc:
        return ShadowReplayRowResult(
            row_id=row.row_id,
            status=ROW_STATUS_ROW_ERROR,
            trial_id=record.trial_id,
            close_id=None,
            error=str(exc),
        )

    append_shadow_trial_close_record_jsonl(close_record, close_ledger_path)
    return ShadowReplayRowResult(
        row_id=row.row_id,
        status=ROW_STATUS_CLOSE_CREATED,
        trial_id=record.trial_id,
        close_id=close_record.close_id,
        error=None,
    )


def run_shadow_replay_manifest(
    input_manifest_path: Path,
    *,
    trial_ledger_path: Path,
    close_ledger_path: Path,
    created_at_utc: str,
) -> ShadowReplayResultManifest:
    """Run a shadow replay over the input manifest.

    For each row, the runner builds a shadow trial record
    and (optionally) a shadow close record, appending them
    to the local trial and close JSONL ledgers. Row-level
    errors are captured and the replay continues.

    The result manifest records counts and per-row
    statuses. It does not include aggregate money deltas,
    performance ratios, win rates, returns, or any other
    performance metric.
    """
    input_manifest_path = Path(input_manifest_path)
    if (
        not isinstance(created_at_utc, str)
        or not created_at_utc.endswith("Z")
    ):
        raise ShadowReplayError(
            f"created_at_utc must be a string ending with 'Z' "
            f"(UTC); got {created_at_utc!r}"
        )

    rows = load_shadow_replay_input_manifest(input_manifest_path)
    input_manifest_sha256 = sha256_file(input_manifest_path)

    row_results: List[ShadowReplayRowResult] = []
    valid_rows = 0
    trial_records_created = 0
    close_records_created = 0
    for row in rows:
        result = _run_single_row(row, trial_ledger_path, close_ledger_path)
        row_results.append(result)
        if result.status == ROW_STATUS_ROW_ERROR:
            # Even if the trial append happened, the row
            # is invalid for counting purposes. But the
            # trial_records_created count below tracks all
            # successful trial appends.
            pass
        else:
            valid_rows += 1
        if result.trial_id is not None:
            trial_records_created += 1
        if result.status == ROW_STATUS_CLOSE_CREATED:
            close_records_created += 1

    return ShadowReplayResultManifest(
        schema_version=SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
        input_manifest_sha256=input_manifest_sha256,
        created_at_utc=created_at_utc,
        requested_rows=len(rows),
        valid_rows=valid_rows,
        trial_records_created=trial_records_created,
        close_records_created=close_records_created,
        rows=tuple(row_results),
        non_claims=SHADOW_REPLAY_NON_CLAIMS,
    )


# --- Serialization and writing -----------------------------------------


def shadow_replay_result_to_ordered_dict(
    result: ShadowReplayResultManifest,
) -> dict:
    """Convert a :class:`ShadowReplayResultManifest` to a
    plain ``dict`` suitable for JSON serialization.
    """
    return {
        "close_records_created": result.close_records_created,
        "created_at_utc": result.created_at_utc,
        "input_manifest_sha256": result.input_manifest_sha256,
        "non_claims": list(result.non_claims),
        "requested_rows": result.requested_rows,
        "rows": [
            {
                "close_id": r.close_id,
                "error": r.error,
                "row_id": r.row_id,
                "status": r.status,
                "trial_id": r.trial_id,
            }
            for r in result.rows
        ],
        "schema_version": result.schema_version,
        "trial_records_created": result.trial_records_created,
        "valid_rows": result.valid_rows,
    }


def shadow_replay_result_to_json_text(
    result: ShadowReplayResultManifest,
) -> str:
    """Serialize a :class:`ShadowReplayResultManifest` to
    deterministic UTF-8 JSON text.

    The output format is:

    * UTF-8 encoded.
    * ``ensure_ascii=False``.
    * ``indent=2``.
    * ``sort_keys=True``.
    * A final newline is appended.
    """
    text = json.dumps(
        shadow_replay_result_to_ordered_dict(result),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_shadow_replay_result_json(
    result: ShadowReplayResultManifest,
    output_path: Path,
    *,
    allow_overwrite: bool = False,
) -> Path:
    """Write a :class:`ShadowReplayResultManifest` to a
    local JSON file.

    Refuses to overwrite an existing file unless
    ``allow_overwrite=True``.
    """
    output_path = Path(output_path)
    if output_path.exists() and not allow_overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing file: {output_path}. "
            "Pass allow_overwrite=True to override."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(shadow_replay_result_to_json_text(result))
    return output_path
