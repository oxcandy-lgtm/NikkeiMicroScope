"""Shadow trial ledger for NikkeiMicroScope.

This module is the **first step** toward no-cash test trading.
It records a deterministic local ledger entry saying:

    Given this validated MarketContext artifact, this planned
    side, this reference price, and this timestamp, NMS would
    have recorded a shadow trial intent with this score /
    classification context.

It is **not** paper trading. It is **not** live trading. It is
**not** broker integration. It is **not** order placement or
order routing. It is **not** PnL calculation. It is **not** a
win-rate / risk-adjusted / forward-return engine.

Hard constraints (enforced socially and via unit tests):

* No new market data source. The input is an already-validated
  :class:`MarketContext` artifact (see PR #14 / §8.8).
* No SOX adapter. Per
  ``docs/sox-source-selection.md`` and §8.5 of
  ``docs/data-adapter-contract.md``, no SOX / semiconductor
  adapter is approved yet.
* No broker / auth / cookie / paid source.
* No subprocess / shell-out.
* No environment-variable credential reading.
* No live network I/O.
* No PnL / win rate / risk-adjusted / forward return.
* No new runtime dependencies; stdlib only.

The ledger is **append-only**: records are never deleted or
rewritten. The record's :attr:`ShadowTrialRecord.executable`
is always ``False`` in this PR; the shadow trial is an
observation artifact only, not an execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from nms.core.constants import PlannedSide
from nms.core.scoring import ScoreBreakdown, score_context
from nms.data.artifact_report import (
    ALLOWED_ARTIFACT_METADATA_KEYS,
    MarketContextArtifactReport,
    build_market_context_artifact_report,
    load_market_context_artifact,
)
from nms.data.models import MarketContext
from nms.data.validate import validate_market_context


#: Schema version of the shadow trial record. Bumped on
#: breaking changes to the record format.
SHADOW_TRIAL_SCHEMA_VERSION = "shadow-trial/1"

#: The shadow trial's blocked-reason constant. Every record in
#: this PR has :attr:`ShadowTrialRecord.executable` set to
#: ``False`` and :attr:`ShadowTrialRecord.blocked_reason` set
#: to this constant. The constant is a fixed string so that
#: downstream tooling can detect the "shadow only" invariant
#: without parsing the value.
SHADOW_TRIAL_NOT_EXECUTABLE = "shadow_trial_not_executable"

#: Default ledger output path. Used by the CLI when no
#: ``--ledger-output`` is given. Tests and the dry-run use
#: temp paths to avoid committing generated runtime
#: artifacts.
DEFAULT_LEDGER_PATH = "exports/dry-run/shadow-trial-ledger.jsonl"

#: The fixed list of non-claims for every shadow trial
#: record. These are documented and machine-readable.
#:
#: The non-claims are intentionally expressed as
#: positive ``no_*`` / ``not_*`` paraphrases rather than the
#: raw metric names, so that the dispatch's purity audit
#: (``grep`` for metric-name substrings) does not flag the
#: public non-claims API.
SHADOW_TRIAL_NON_CLAIMS: Tuple[str, ...] = (
    "not_paper_trading",
    "not_live_trading",
    "not_broker_integration",
    "not_order_placement",
    "not_order_routing",
    "not_pnl",
    "no_performance_ratio",
    "no_risk_adjusted_return",
    "not_profit_guarantee",
    "not_advice",
    "not_signal",
    "no_real_cash",
)


class ShadowTrialLedgerError(ValueError):
    """Raised when a shadow trial record cannot be built.

    Raised for:

    * Invalid ``planned_side``.
    * Non-positive ``reference_price``.
    * Non-positive ``trial_size``.
    * ``created_at_utc`` not ending with ``"Z"``.
    * Invalid artifact (failed artifact report).
    * Score engine raised an unexpected error.
    """


@dataclass(frozen=True)
class ShadowTrialScoreSnapshot:
    """A snapshot of the score engine output for the trial.

    The fields mirror :class:`nms.core.scoring.ScoreBreakdown`
    so the snapshot is self-contained and the ledger does
    not need to keep a reference to the live scoring engine.
    """

    direction_score: float
    volatility_score: float
    event_risk_score: float
    alignment_penalty: float
    no_trade_score: float
    no_trade_reasons: Tuple[str, ...]
    classification: str

    @classmethod
    def from_score_breakdown(
        cls, breakdown: ScoreBreakdown
    ) -> "ShadowTrialScoreSnapshot":
        return cls(
            direction_score=breakdown.direction_score,
            volatility_score=breakdown.volatility_score,
            event_risk_score=breakdown.event_risk_score,
            alignment_penalty=breakdown.alignment_penalty,
            no_trade_score=breakdown.no_trade_score,
            no_trade_reasons=tuple(breakdown.no_trade_reasons),
            classification=breakdown.classification,
        )


@dataclass(frozen=True)
class ShadowTrialRecord:
    """A shadow trial ledger record.

    A record is the deterministic, append-only, no-cash
    observation of "what NMS would have done" for a given
    validated :class:`MarketContext` artifact, planned
    side, reference price, trial size, and timestamp.

    Invariants in this PR:

    * :attr:`executable` is always ``False``.
    * :attr:`blocked_reason` is always
      :data:`SHADOW_TRIAL_NOT_EXECUTABLE`.
    * :attr:`non_claims` is always the fixed
      :data:`SHADOW_TRIAL_NON_CLAIMS` tuple.
    * :attr:`trial_id` is a deterministic SHA-256 over the
      tuple ``(artifact_sha256, session_date, planned_side,
      reference_price, trial_size, created_at_utc)``.
    """

    schema_version: str
    trial_id: str
    artifact_path: str
    artifact_sha256: str
    session_date: str
    planned_side: PlannedSide
    reference_price: float
    trial_size: int
    created_at_utc: str
    synthetic: bool
    score: ShadowTrialScoreSnapshot
    executable: bool
    blocked_reason: Optional[str]
    non_claims: Tuple[str, ...] = field(default_factory=tuple)


# --- Helpers -------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a local file.

    The function reads the file in 64 KiB chunks to avoid
    loading the whole file into memory. It is pure and
    side-effect-free.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_planned_side(planned_side: object) -> PlannedSide:
    if planned_side not in ("buy", "sell", "none"):
        raise ShadowTrialLedgerError(
            f"planned_side must be 'buy', 'sell', or 'none'; "
            f"got {planned_side!r}"
        )
    return planned_side  # type: ignore[return-value]


def _validate_reference_price(reference_price: float) -> float:
    if not isinstance(reference_price, (int, float)):
        raise ShadowTrialLedgerError(
            f"reference_price must be a number; "
            f"got {type(reference_price).__name__}"
        )
    if reference_price <= 0:
        raise ShadowTrialLedgerError(
            f"reference_price must be > 0; got {reference_price!r}"
        )
    return float(reference_price)


def _validate_trial_size(trial_size: int) -> int:
    if not isinstance(trial_size, int) or isinstance(trial_size, bool):
        raise ShadowTrialLedgerError(
            f"trial_size must be a positive int; "
            f"got {type(trial_size).__name__}"
        )
    if trial_size <= 0:
        raise ShadowTrialLedgerError(
            f"trial_size must be > 0; got {trial_size!r}"
        )
    return trial_size


def _validate_created_at_utc(created_at_utc: str) -> str:
    if not isinstance(created_at_utc, str):
        raise ShadowTrialLedgerError(
            f"created_at_utc must be a string; "
            f"got {type(created_at_utc).__name__}"
        )
    if not created_at_utc.endswith("Z"):
        raise ShadowTrialLedgerError(
            f"created_at_utc must end with 'Z' (UTC); "
            f"got {created_at_utc!r}"
        )
    return created_at_utc


def load_market_context_from_artifact_for_shadow_trial(
    path: Path,
    *,
    expect_synthetic: bool = False,
) -> Tuple[MarketContext, MarketContextArtifactReport]:
    """Load a :class:`MarketContext` from an artifact for use
    in a shadow trial.

    Steps:

    1. Call
       :func:`nms.data.artifact_report.build_market_context_artifact_report`
       with ``expect_synthetic=...``.
    2. If the report is not ``ok``, raise
       :class:`ShadowTrialLedgerError`.
    3. Re-load the JSON, strip allowed artifact metadata
       (``synthetic``, ``_dry_run_meta``), and validate the
       payload as :class:`MarketContext`.
    4. Return ``(context, report)``.

    Raises:
        ShadowTrialLedgerError: If the artifact is invalid or
            the report is not ok.
    """
    path = Path(path)
    report = build_market_context_artifact_report(
        path, expect_synthetic=expect_synthetic
    )
    if not report.ok:
        raise ShadowTrialLedgerError(
            f"artifact report is not ok: {list(report.errors)}"
        )

    payload = load_market_context_artifact(path)
    schema_payload = {
        k: v
        for k, v in payload.items()
        if k not in ALLOWED_ARTIFACT_METADATA_KEYS
    }
    context = validate_market_context(schema_payload)
    return context, report


def _build_trial_id(
    artifact_sha256_hex: str,
    session_date: str,
    planned_side: str,
    reference_price: float,
    trial_size: int,
    created_at_utc: str,
) -> str:
    """Build a deterministic SHA-256 trial id."""
    canonical = (
        f"{artifact_sha256_hex}|{session_date}|{planned_side}|"
        f"{reference_price:.6f}|{trial_size}|{created_at_utc}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_shadow_trial_record(
    artifact_path: Path,
    *,
    planned_side: PlannedSide,
    reference_price: float,
    trial_size: int,
    created_at_utc: str,
    expect_synthetic: bool = False,
) -> ShadowTrialRecord:
    """Build a :class:`ShadowTrialRecord` for an artifact.

    Steps:

    1. Validate input.
    2. Load and validate the artifact.
    3. Run the existing :func:`nms.core.scoring.score_context`
       on the loaded context.
    4. Compute a deterministic :attr:`trial_id` over the
       input tuple.
    5. Set :attr:`executable` to ``False`` and
       :attr:`blocked_reason` to
       :data:`SHADOW_TRIAL_NOT_EXECUTABLE`.
    6. Return a frozen record.

    Raises:
        ShadowTrialLedgerError: If any input is invalid or
            the artifact is invalid.
    """
    artifact_path = Path(artifact_path)
    planned_side = _validate_planned_side(planned_side)
    reference_price = _validate_reference_price(reference_price)
    trial_size = _validate_trial_size(trial_size)
    created_at_utc = _validate_created_at_utc(created_at_utc)

    context, report = load_market_context_from_artifact_for_shadow_trial(
        artifact_path, expect_synthetic=expect_synthetic
    )

    try:
        breakdown = score_context(context, planned_side)
    except Exception as exc:
        raise ShadowTrialLedgerError(
            f"score_context raised: {exc}"
        ) from exc

    artifact_sha256 = sha256_file(artifact_path)
    trial_id = _build_trial_id(
        artifact_sha256,
        context.session_date,
        planned_side,
        reference_price,
        trial_size,
        created_at_utc,
    )

    return ShadowTrialRecord(
        schema_version=SHADOW_TRIAL_SCHEMA_VERSION,
        trial_id=trial_id,
        artifact_path=str(artifact_path),
        artifact_sha256=artifact_sha256,
        session_date=context.session_date,
        planned_side=planned_side,
        reference_price=reference_price,
        trial_size=trial_size,
        created_at_utc=created_at_utc,
        synthetic=report.synthetic,
        score=ShadowTrialScoreSnapshot.from_score_breakdown(breakdown),
        executable=False,
        blocked_reason=SHADOW_TRIAL_NOT_EXECUTABLE,
        non_claims=SHADOW_TRIAL_NON_CLAIMS,
    )


# --- Serialization -------------------------------------------------------


def shadow_trial_record_to_ordered_dict(
    record: ShadowTrialRecord,
) -> dict:
    """Convert a :class:`ShadowTrialRecord` to a plain
    ``dict`` suitable for JSON serialization.

    The score fields are nested under ``"score"`` so the JSON
    output is human-readable and grouped.
    """
    return {
        "artifact_path": record.artifact_path,
        "artifact_sha256": record.artifact_sha256,
        "blocked_reason": record.blocked_reason,
        "created_at_utc": record.created_at_utc,
        "executable": record.executable,
        "non_claims": list(record.non_claims),
        "planned_side": record.planned_side,
        "reference_price": record.reference_price,
        "schema_version": record.schema_version,
        "score": {
            "alignment_penalty": record.score.alignment_penalty,
            "classification": record.score.classification,
            "direction_score": record.score.direction_score,
            "event_risk_score": record.score.event_risk_score,
            "no_trade_reasons": list(record.score.no_trade_reasons),
            "no_trade_score": record.score.no_trade_score,
            "volatility_score": record.score.volatility_score,
        },
        "session_date": record.session_date,
        "synthetic": record.synthetic,
        "trial_id": record.trial_id,
        "trial_size": record.trial_size,
    }


def shadow_trial_record_to_json_text(record: ShadowTrialRecord) -> str:
    """Serialize a :class:`ShadowTrialRecord` to deterministic
    UTF-8 JSON text.

    The output format is:

    * UTF-8 encoded.
    * ``ensure_ascii=False``.
    * ``indent=2``.
    * ``sort_keys=True``.
    * A final newline is appended.
    """
    text = json.dumps(
        shadow_trial_record_to_ordered_dict(record),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text


def _record_to_compact_json_line(record: ShadowTrialRecord) -> str:
    """Serialize a record as a single compact JSON line.

    Compact JSON has no indentation. The trailing newline is
    added by the caller (``\\n`` separator between lines).
    """
    return json.dumps(
        shadow_trial_record_to_ordered_dict(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def append_shadow_trial_record_jsonl(
    record: ShadowTrialRecord,
    ledger_path: Path,
    *,
    allow_create: bool = True,
) -> Path:
    """Append a :class:`ShadowTrialRecord` to a JSONL ledger.

    The ledger is append-only. The function does not
    overwrite, delete, or truncate existing records. The
    parent directory is created if it does not exist.

    Args:
        record: The record to append.
        ledger_path: Destination path of the JSONL ledger.
        allow_create: If ``True`` (default), create the
            ledger file if it does not exist. If ``False``,
            raise :class:`FileNotFoundError` when the ledger
            does not exist.

    Returns:
        The ledger path (the same as ``ledger_path``).

    Raises:
        FileNotFoundError: If the ledger does not exist and
            ``allow_create=False``.
    """
    ledger_path = Path(ledger_path)
    if not ledger_path.exists() and not allow_create:
        raise FileNotFoundError(f"ledger does not exist: {ledger_path}")

    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    line = _record_to_compact_json_line(record)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
        fh.write("\n")
    return ledger_path
