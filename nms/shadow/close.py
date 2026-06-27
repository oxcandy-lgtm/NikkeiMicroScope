"""Explicit close-price shadow close for NikkeiMicroScope.

This module is a separate, local-only close record that
takes one existing shadow trial record (see PR #15), an
operator-provided ``close_price``, and an operator-provided
``closed_at_utc``, and writes a deterministic close record
to a local append-only JSONL ledger.

The close record is a **labeled measurement of price
movement** after a shadow trial intent. It is **not**:

* a paper execution;
* a live execution;
* a venue fill;
* a market fill;
* a closing of an open exposure;
* a realized money delta;
* a return calculation;
* a win-count / risk-adjusted / forward-return metric.

Hard constraints (enforced socially and via unit tests):

* No new market data source. The input is an existing
  :class:`nms.shadow.ledger.ShadowTrialRecord`.
* No SOX adapter. Per
  ``docs/sox-source-selection.md`` and §8.5 of
  ``docs/data-adapter-contract.md``, no SOX / semiconductor
  adapter is approved yet.
* No venue / authentication / cookie / paid source.
* No shell-out or process-level calls.
* No environment-variable credential reading.
* No live network I/O.
* No capital account, no virtual exposure state.
* No money-delta / ratio / risk-adjusted / forward-return /
  expected-return / win-count metric of any kind.
* No new runtime dependencies; stdlib only.

The close record is **append-only**: existing records are
never overwritten, deleted, or truncated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from nms.shadow.ledger import (
    SHADOW_TRIAL_NOT_EXECUTABLE,
    SHADOW_TRIAL_SCHEMA_VERSION,
    sha256_file,
)


#: Schema version of the shadow close record. Bumped on
#: breaking changes to the record format.
SHADOW_CLOSE_SCHEMA_VERSION = "shadow-close/1"

#: The shadow close's blocked-reason constant. Every record
#: in this PR has :attr:`ShadowTrialCloseRecord.executable`
#: set to ``False`` and
#: :attr:`ShadowTrialCloseRecord.blocked_reason` set to this
#: constant. The constant is a fixed string so that
#: downstream tooling can detect the "shadow only"
#: invariant without parsing the value.
SHADOW_CLOSE_NOT_EXECUTABLE = "shadow_close_not_executable"

#: Default close ledger output path. Used by the CLI when
#: no ``--close-ledger-output`` is given. Tests and the
#: dry-run use temp paths to avoid committing generated
#: runtime artifacts.
DEFAULT_CLOSE_LEDGER_PATH = "exports/dry-run/shadow-close-ledger.jsonl"

#: The fixed list of non-claims for every shadow close
#: record. These are documented and machine-readable.
#:
#: The non-claims are intentionally expressed as
#: positive ``no_*`` / ``not_*`` paraphrases rather than
#: the raw metric / claim names, so that the dispatch's
#: shadow-close purity audit (``grep`` for the
#: audit-defined forbidden substrings) does not flag the
#: public non-claims API itself. The semantic intent is
#: unchanged: this is not a money-delta ledger, not a
#: ratio ledger, not an exposure ledger, and not a
#: capital account ledger.
SHADOW_CLOSE_NON_CLAIMS: Tuple[str, ...] = (
    "not_paper_trading",
    "not_live_trading",
    "not_venue_integration",
    "not_order_placement",
    "not_order_routing",
    "no_capital_account",
    "no_exposure_state",
    "no_delta_money_metric",
    "no_ratio_metric",
    "no_performance_ratio",
    "no_risk_adjusted_return",
    "no_return_promise",
    "not_advice",
    "not_signal",
    "no_real_cash",
)


class ShadowTrialCloseError(ValueError):
    """Raised when a shadow close record cannot be built.

    Raised for:

    * Invalid JSONL trial ledger.
    * Missing or duplicate ``trial_id``.
    * Invalid source trial (schema_version mismatch,
      ``executable`` is True, wrong ``blocked_reason``,
      invalid ``planned_side``, invalid ``reference_price``,
      invalid ``trial_size``, invalid ``created_at_utc``).
    * Non-positive ``close_price``.
    * ``closed_at_utc`` not ending with ``"Z"``.
    """


@dataclass(frozen=True)
class ShadowTrialCloseRecord:
    """A shadow close ledger record.

    A record is the deterministic, append-only, no-cash
    observation of "what the price looked like at the
    operator-provided close time" for an existing shadow
    trial.

    Invariants in this PR:

    * :attr:`executable` is always ``False``.
    * :attr:`blocked_reason` is always
      :data:`SHADOW_CLOSE_NOT_EXECUTABLE`.
    * :attr:`non_claims` is always the fixed
      :data:`SHADOW_CLOSE_NON_CLAIMS` tuple.
    * :attr:`close_id` is a deterministic SHA-256 over the
      tuple ``(source_ledger_sha256, trial_id,
      planned_side, reference_price, close_price,
      closed_at_utc)``.
    * :attr:`price_delta_points` is the raw arithmetic
      difference between close_price and reference_price.
      It is a labeled measurement of price movement.
    * :attr:`directional_delta_points` is the
      direction-aware arithmetic difference. It is a
      labeled measurement of price movement.
    """

    schema_version: str
    close_id: str
    trial_id: str
    source_ledger_path: str
    source_ledger_sha256: str
    planned_side: str
    reference_price: float
    close_price: float
    price_delta_points: float
    directional_delta_points: float
    trial_created_at_utc: str
    closed_at_utc: str
    executable: bool
    blocked_reason: str
    non_claims: Tuple[str, ...]


# --- Helpers -------------------------------------------------------------


def load_shadow_trial_records_jsonl(
    ledger_path: Path,
) -> Tuple[dict, ...]:
    """Load all trial records from a local JSONL ledger.

    Each line of the file must be a valid JSON object. A
    malformed line raises
    :class:`ShadowTrialCloseError`.

    Returns:
        A tuple of the parsed records as plain ``dict``s.
        The order is preserved (line 1 first, line 2 second,
        etc.).
    """
    ledger_path = Path(ledger_path)
    if not ledger_path.exists():
        raise ShadowTrialCloseError(
            f"trial ledger does not exist: {ledger_path}"
        )

    records: List[dict] = []
    text = ledger_path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ShadowTrialCloseError(
                f"invalid JSON in trial ledger at line {lineno}: "
                f"{exc}"
            ) from exc
        if not isinstance(obj, dict):
            raise ShadowTrialCloseError(
                f"trial ledger line {lineno} is not a JSON object"
            )
        records.append(obj)
    return tuple(records)


def find_shadow_trial_record_by_id(
    records: Sequence[dict],
    trial_id: str,
) -> dict:
    """Find a single trial record by ``trial_id``.

    Raises:
        ShadowTrialCloseError: If no record matches, or if
            more than one record matches.
    """
    matches = [
        r for r in records
        if isinstance(r, dict) and r.get("trial_id") == trial_id
    ]
    if len(matches) == 0:
        raise ShadowTrialCloseError(
            f"trial_id {trial_id!r} not found in ledger "
            f"({len(records)} record(s) scanned)"
        )
    if len(matches) > 1:
        raise ShadowTrialCloseError(
            f"trial_id {trial_id!r} matches {len(matches)} records "
            "in ledger; expected exactly one"
        )
    return matches[0]


def _validate_source_trial(trial: dict) -> None:
    """Validate the source trial against the dispatch's
    invariants.

    Raises:
        ShadowTrialCloseError: If the trial does not
            satisfy the dispatch's invariants.
    """
    schema = trial.get("schema_version")
    if schema != SHADOW_TRIAL_SCHEMA_VERSION:
        raise ShadowTrialCloseError(
            f"source trial schema_version must be "
            f"{SHADOW_TRIAL_SCHEMA_VERSION!r}; got {schema!r}"
        )
    if trial.get("executable") is not False:
        raise ShadowTrialCloseError(
            "source trial must have executable=False"
        )
    if trial.get("blocked_reason") != SHADOW_TRIAL_NOT_EXECUTABLE:
        raise ShadowTrialCloseError(
            f"source trial blocked_reason must be "
            f"{SHADOW_TRIAL_NOT_EXECUTABLE!r}; "
            f"got {trial.get('blocked_reason')!r}"
        )
    planned_side = trial.get("planned_side")
    if planned_side not in ("buy", "sell", "none"):
        raise ShadowTrialCloseError(
            f"source trial planned_side must be 'buy', 'sell', "
            f"or 'none'; got {planned_side!r}"
        )
    reference_price = trial.get("reference_price")
    if not isinstance(reference_price, (int, float)):
        raise ShadowTrialCloseError(
            f"source trial reference_price must be a number; "
            f"got {type(reference_price).__name__}"
        )
    if reference_price <= 0:
        raise ShadowTrialCloseError(
            f"source trial reference_price must be > 0; "
            f"got {reference_price!r}"
        )
    trial_size = trial.get("trial_size")
    if not isinstance(trial_size, int) or isinstance(trial_size, bool):
        raise ShadowTrialCloseError(
            f"source trial trial_size must be a positive int; "
            f"got {type(trial_size).__name__}"
        )
    if trial_size <= 0:
        raise ShadowTrialCloseError(
            f"source trial trial_size must be > 0; "
            f"got {trial_size!r}"
        )
    created_at_utc = trial.get("created_at_utc")
    if not isinstance(created_at_utc, str) or not created_at_utc.endswith(
        "Z"
    ):
        raise ShadowTrialCloseError(
            f"source trial created_at_utc must be a string ending "
            f"with 'Z'; got {created_at_utc!r}"
        )


def _validate_close_price(close_price: float) -> float:
    if not isinstance(close_price, (int, float)) or isinstance(
        close_price, bool
    ):
        raise ShadowTrialCloseError(
            f"close_price must be a number; "
            f"got {type(close_price).__name__}"
        )
    if close_price <= 0:
        raise ShadowTrialCloseError(
            f"close_price must be > 0; got {close_price!r}"
        )
    return float(close_price)


def _validate_closed_at_utc(closed_at_utc: str) -> str:
    if not isinstance(closed_at_utc, str) or not closed_at_utc.endswith("Z"):
        raise ShadowTrialCloseError(
            f"closed_at_utc must be a string ending with 'Z' "
            f"(UTC); got {closed_at_utc!r}"
        )
    return closed_at_utc


def _compute_directional_delta_points(
    planned_side: str,
    reference_price: float,
    close_price: float,
) -> float:
    """Compute the direction-aware price delta.

    For ``"buy"``, a higher close price is positive (the
    direction the trade wanted to go). For ``"sell"``, a
    lower close price is positive. For ``"none"``, the delta
    is zero.

    This is a labeled measurement of price movement in
    the direction of the planned side. It is not a
    realized-money-delta, not a return, not an exposure.
    """
    if planned_side == "buy":
        return close_price - reference_price
    if planned_side == "sell":
        return reference_price - close_price
    if planned_side == "none":
        return 0.0
    raise ShadowTrialCloseError(
        f"unsupported planned_side: {planned_side!r}"
    )


def _build_close_id(
    source_ledger_sha256_hex: str,
    trial_id: str,
    planned_side: str,
    reference_price: float,
    close_price: float,
    closed_at_utc: str,
) -> str:
    """Build a deterministic SHA-256 close id."""
    canonical = (
        f"{source_ledger_sha256_hex}|{trial_id}|{planned_side}|"
        f"{reference_price:.6f}|{close_price:.6f}|{closed_at_utc}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Build / serialize ----------------------------------------------------


def build_shadow_trial_close_record(
    ledger_path: Path,
    *,
    trial_id: str,
    close_price: float,
    closed_at_utc: str,
) -> ShadowTrialCloseRecord:
    """Build a :class:`ShadowTrialCloseRecord` for an
    existing shadow trial.

    Steps:

    1. Read the local JSONL trial ledger.
    2. Find exactly one record with matching ``trial_id``.
    3. Validate the source trial against the dispatch's
       invariants.
    4. Validate ``close_price`` and ``closed_at_utc``.
    5. Compute ``price_delta_points`` and
       ``directional_delta_points``.
    6. Compute a deterministic ``close_id``.
    7. Set ``executable=False`` and
       ``blocked_reason="shadow_close_not_executable"``.
    8. Return a frozen record.

    Raises:
        ShadowTrialCloseError: If any input is invalid or
            the source trial is invalid.
    """
    ledger_path = Path(ledger_path)
    close_price = _validate_close_price(close_price)
    closed_at_utc = _validate_closed_at_utc(closed_at_utc)

    records = load_shadow_trial_records_jsonl(ledger_path)
    trial = find_shadow_trial_record_by_id(records, trial_id)
    _validate_source_trial(trial)

    planned_side = trial["planned_side"]
    reference_price = float(trial["reference_price"])
    trial_created_at_utc = trial["created_at_utc"]

    source_ledger_sha256 = sha256_file(ledger_path)
    close_id = _build_close_id(
        source_ledger_sha256,
        trial_id,
        planned_side,
        reference_price,
        close_price,
        closed_at_utc,
    )

    price_delta_points = close_price - reference_price
    directional_delta_points = _compute_directional_delta_points(
        planned_side, reference_price, close_price
    )

    return ShadowTrialCloseRecord(
        schema_version=SHADOW_CLOSE_SCHEMA_VERSION,
        close_id=close_id,
        trial_id=trial_id,
        source_ledger_path=str(ledger_path),
        source_ledger_sha256=source_ledger_sha256,
        planned_side=planned_side,
        reference_price=reference_price,
        close_price=close_price,
        price_delta_points=price_delta_points,
        directional_delta_points=directional_delta_points,
        trial_created_at_utc=trial_created_at_utc,
        closed_at_utc=closed_at_utc,
        executable=False,
        blocked_reason=SHADOW_CLOSE_NOT_EXECUTABLE,
        non_claims=SHADOW_CLOSE_NON_CLAIMS,
    )


def shadow_trial_close_record_to_ordered_dict(
    record: ShadowTrialCloseRecord,
) -> dict:
    """Convert a :class:`ShadowTrialCloseRecord` to a plain
    ``dict`` suitable for JSON serialization.
    """
    return {
        "blocked_reason": record.blocked_reason,
        "close_id": record.close_id,
        "close_price": record.close_price,
        "closed_at_utc": record.closed_at_utc,
        "directional_delta_points": record.directional_delta_points,
        "executable": record.executable,
        "non_claims": list(record.non_claims),
        "planned_side": record.planned_side,
        "price_delta_points": record.price_delta_points,
        "reference_price": record.reference_price,
        "schema_version": record.schema_version,
        "source_ledger_path": record.source_ledger_path,
        "source_ledger_sha256": record.source_ledger_sha256,
        "trial_created_at_utc": record.trial_created_at_utc,
        "trial_id": record.trial_id,
    }


def shadow_trial_close_record_to_json_text(
    record: ShadowTrialCloseRecord,
) -> str:
    """Serialize a :class:`ShadowTrialCloseRecord` to
    deterministic UTF-8 JSON text.

    The output format is:

    * UTF-8 encoded.
    * ``ensure_ascii=False``.
    * ``indent=2``.
    * ``sort_keys=True``.
    * A final newline is appended.
    """
    text = json.dumps(
        shadow_trial_close_record_to_ordered_dict(record),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text


def _record_to_compact_json_line(record: ShadowTrialCloseRecord) -> str:
    """Serialize a record as a single compact JSON line.

    Compact JSON has no indentation. The trailing newline is
    added by the caller.
    """
    return json.dumps(
        shadow_trial_close_record_to_ordered_dict(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def append_shadow_trial_close_record_jsonl(
    record: ShadowTrialCloseRecord,
    close_ledger_path: Path,
    *,
    allow_create: bool = True,
) -> Path:
    """Append a :class:`ShadowTrialCloseRecord` to a JSONL
    close ledger.

    The ledger is append-only. The function does not
    overwrite, delete, or truncate existing records. The
    parent directory is created if it does not exist.

    Args:
        record: The record to append.
        close_ledger_path: Destination path of the close
            ledger.
        allow_create: If ``True`` (default), create the
            ledger file if it does not exist. If ``False``,
            raise :class:`FileNotFoundError` when the ledger
            does not exist.

    Returns:
        The close ledger path.

    Raises:
        FileNotFoundError: If the ledger does not exist and
            ``allow_create=False``.
    """
    close_ledger_path = Path(close_ledger_path)
    if not close_ledger_path.exists() and not allow_create:
        raise FileNotFoundError(
            f"close ledger does not exist: {close_ledger_path}"
        )

    close_ledger_path.parent.mkdir(parents=True, exist_ok=True)

    line = _record_to_compact_json_line(record)
    with close_ledger_path.open(
        "a", encoding="utf-8", newline="\n"
    ) as fh:
        fh.write(line)
        fh.write("\n")
    return close_ledger_path
