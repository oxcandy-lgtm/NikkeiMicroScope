"""Artifact validation / report layer for exported
:class:`MarketContext` JSON artifacts.

This module is the read-only validation/report layer for
NikkeiMicroScope. It reads an exported ``MarketContext`` JSON
artifact from local disk, validates it, and produces a
deterministic read-only report. It does **not** add a new
market data source. It does **not** perform network I/O. It
does **not** read environment credentials. It does **not** use
subprocess. It does **not** import broker SDKs, exchange
clients, or paid data sources.

Hard constraints (enforced socially and via unit tests):

* No new market data source. The artifact's populated
  fields must come from the already-approved FRED overlay
  adapters; no SOX / semiconductor adapter is approved yet.
* No broker / auth / cookie / paid source.
* No subprocess / shell-out.
* No environment-variable credential reading.
* No new runtime dependencies; stdlib only.
* The ``MarketContext`` schema is not widened. Allowed
  artifact-level metadata (``synthetic``, ``_dry_run_meta``) is
  stripped before schema validation; the underlying schema
  remains the documented ``MarketContext`` schema in
  ``nms.data.models``.

The report is read-only. It does not score, signal, or
execute. It is not a backtest, not paper trading, and not
live trading.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Tuple

from nms.data.validate import ValidationError, validate_market_context


#: Top-level keys that are allowed as artifact-level metadata
#: but are not part of the ``MarketContext`` schema. These keys
#: are stripped from the loaded payload before
#: :func:`nms.data.validate.validate_market_context` is called.
ALLOWED_ARTIFACT_METADATA_KEYS: Tuple[str, ...] = (
    "synthetic",
    "_dry_run_meta",
)

#: Field paths that the approved dry-run pipeline is expected
#: to populate (i.e. the fields the four approved FRED overlay
#: adapters write).
EXPECTED_POPULATED_FIELDS: Tuple[str, ...] = (
    "us_yields.us2y",
    "us_yields.us10y",
    "us_yields.us10y_minus_us2y",
    "us_yields.us10y_change_bp",
    "us_equities.sp500",
    "us_equities.sp500_change_pct",
    "fx.usdjpy",
    "fx.usdjpy_change_pct",
    "us_equities.nasdaq100",
    "us_equities.nasdaq100_change_pct",
)

#: Field paths that the approved dry-run pipeline must NOT
#: populate from an approved source. SOX is not approved
#: (see §8.5 of ``docs/data-adapter-contract.md`` and
#: ``docs/sox-source-selection.md``). The two
#: ``nikkei_night_session`` fields are listed as intentional
#: unpopulated fields because the approved dry-run pipeline
#: does not include a Nikkei night-session overlay; the base
#: fixture may have placeholder values for them, but the
#: pipeline does not source them from an approved Nikkei
#: data feed.
INTENTIONALLY_MISSING_OR_UNAPPROVED_FIELDS: Tuple[str, ...] = (
    "semiconductor.sox",
    "semiconductor.sox_change_pct",
    "nikkei_night_session.close",
    "nikkei_night_session.percent_change",
)


@dataclass(frozen=True)
class ArtifactFieldStatus:
    """Status of a single field path in the artifact."""

    path: str
    present: bool
    value: object
    populated: bool
    expected: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expected": self.expected,
            "path": self.path,
            "populated": self.populated,
            "present": self.present,
            "value": self.value,
        }


@dataclass(frozen=True)
class MarketContextArtifactReport:
    """A read-only validation / report for an exported
    :class:`MarketContext` JSON artifact.
    """

    artifact_path: str
    valid_json: bool
    valid_market_context: bool
    session_date: str
    synthetic: bool
    dry_run_meta_present: bool
    populated_fields: Tuple[ArtifactFieldStatus, ...]
    intentionally_missing_or_unapproved_fields: Tuple[
        ArtifactFieldStatus, ...
    ]
    errors: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """``True`` iff every check passed.

        Specifically:
          * JSON was valid.
          * The ``MarketContext`` schema validation passed
            after stripping allowed artifact metadata.
          * All :data:`EXPECTED_POPULATED_FIELDS` are present
            and populated (nonzero).
          * If ``expect_synthetic`` was set when the report
            was built, the synthetic marker is present and
            ``live_fred_used`` is ``False``.
          * For SOX (an unapproved source), the
            ``semiconductor.sox`` and
            ``semiconductor.sox_change_pct`` fields are zero
            in any synthetic approved dry-run artifact.
        """
        return not self.errors


def load_market_context_artifact(path: Path) -> Dict[str, Any]:
    """Load an artifact from a local JSON file.

    Returns:
        The parsed JSON as a plain ``dict``. The dict is a
        fresh copy; the caller may mutate it without
        affecting the file.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        OSError: If the file cannot be read for any other
            reason.
    """
    text = Path(path).read_text(encoding="utf-8")
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        # The artifact must be a JSON object at the top level.
        raise ValueError(
            f"artifact must be a JSON object at the top level; "
            f"got {type(loaded).__name__}"
        )
    return loaded


def _strip_allowed_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``payload`` with the allowed
    artifact-level metadata keys removed.

    The original ``payload`` is not mutated.
    """
    return {
        k: v
        for k, v in payload.items()
        if k not in ALLOWED_ARTIFACT_METADATA_KEYS
    }


def _classify_field(
    payload: Dict[str, Any], path: str
) -> ArtifactFieldStatus:
    """Return an :class:`ArtifactFieldStatus` for the given
    dotted ``path`` (e.g. ``"us_yields.us2y"``).
    """
    parts = path.split(".")
    cur: Any = payload
    present = True
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            present = False
            break
        cur = cur[part]
    if present:
        populated = _is_populated(cur)
    else:
        populated = False
    return ArtifactFieldStatus(
        path=path,
        present=present,
        value=cur if present else None,
        populated=populated,
        expected="populated"
        if path in EXPECTED_POPULATED_FIELDS
        else "unpopulated",
    )


def _is_populated(value: Any) -> bool:
    """Return ``True`` iff ``value`` is a number that is
    strictly positive or strictly negative (i.e. nonzero).
    """
    if isinstance(value, bool):
        # bools are ints in Python; we treat False/True as
        # not-populated here so that a synthetic marker does
        # not accidentally count as a populated field.
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _allowed_top_level_keys() -> set:
    """Return the set of top-level keys allowed in an
    artifact: the ``MarketContext`` schema keys plus the
    allowed artifact metadata keys.
    """
    from nms.data.models import MarketContext

    schema_keys = {
        f.name
        for f in MarketContext.__dataclass_fields__.values()
    }
    return schema_keys | set(ALLOWED_ARTIFACT_METADATA_KEYS)


def build_market_context_artifact_report(
    path: Path,
    *,
    expect_synthetic: bool = False,
) -> MarketContextArtifactReport:
    """Build a :class:`MarketContextArtifactReport` for the
    artifact at ``path``.

    Steps:
      1. Load the JSON file. If it is not valid JSON, return
         a report with ``valid_json=False`` and an error.
      2. Detect the synthetic marker.
      3. Strip allowed artifact metadata before validating
         against the ``MarketContext`` schema.
      4. Flag unknown top-level metadata keys.
      5. Report populated and unpopulated / unapproved field
         statuses.
      6. If ``expect_synthetic`` is set, require the
         synthetic marker.
      7. For SOX (an unapproved source), require zero
         values in any synthetic approved dry-run artifact.
    """
    path = Path(path)
    errors: list = []

    # 1. Load JSON.
    try:
        payload = load_market_context_artifact(path)
    except FileNotFoundError as e:
        return MarketContextArtifactReport(
            artifact_path=str(path),
            valid_json=False,
            valid_market_context=False,
            session_date="",
            synthetic=False,
            dry_run_meta_present=False,
            populated_fields=(),
            intentionally_missing_or_unapproved_fields=(),
            errors=(f"file not found: {e}",),
        )
    except json.JSONDecodeError as e:
        return MarketContextArtifactReport(
            artifact_path=str(path),
            valid_json=False,
            valid_market_context=False,
            session_date="",
            synthetic=False,
            dry_run_meta_present=False,
            populated_fields=(),
            intentionally_missing_or_unapproved_fields=(),
            errors=(f"invalid JSON: {e}",),
        )
    except (OSError, ValueError) as e:
        return MarketContextArtifactReport(
            artifact_path=str(path),
            valid_json=False,
            valid_market_context=False,
            session_date="",
            synthetic=False,
            dry_run_meta_present=False,
            populated_fields=(),
            intentionally_missing_or_unapproved_fields=(),
            errors=(f"failed to load artifact: {e}",),
        )

    # 2. Detect the synthetic marker with strict type
    #    checking. The dispatch defines `synthetic` as a
    #    boolean; we reject any truthy non-boolean value
    #    (e.g. the string "yes", the integer 1, a non-empty
    #    list) so that callers cannot accidentally opt in
    #    to the synthetic-approved-dry-run code path with
    #    an unexpected type.
    synthetic_key_present = "synthetic" in payload
    synthetic_raw = payload.get("synthetic", False)
    if synthetic_key_present and not isinstance(synthetic_raw, bool):
        errors.append("'synthetic' must be boolean true/false")
        synthetic = False
    else:
        synthetic = synthetic_raw is True

    dry_run_meta = payload.get("_dry_run_meta")
    dry_run_meta_key_present = "_dry_run_meta" in payload
    if dry_run_meta_key_present and not isinstance(dry_run_meta, dict):
        errors.append("'_dry_run_meta' must be an object")
    dry_run_meta_present = isinstance(dry_run_meta, dict)
    session_date = str(payload.get("session_date", ""))

    # 3. Flag unknown top-level metadata keys.
    allowed = _allowed_top_level_keys()
    unknown_top_level = [
        k for k in payload.keys() if k not in allowed
    ]
    if unknown_top_level:
        errors.append(
            f"unknown top-level metadata keys: "
            f"{sorted(unknown_top_level)}"
        )

    # 4. Strip allowed metadata and validate as MarketContext.
    schema_payload = _strip_allowed_metadata(payload)
    try:
        validate_market_context(schema_payload)
        valid_market_context = True
    except ValidationError as e:
        valid_market_context = False
        errors.append(f"MarketContext schema validation failed: {e}")

    # 5. Build field status lists.
    populated_status = tuple(
        _classify_field(payload, path)
        for path in EXPECTED_POPULATED_FIELDS
    )
    for status in populated_status:
        if not status.populated:
            errors.append(
                f"expected populated field {status.path!r} is "
                f"missing or zero"
            )

    unapproved_status = tuple(
        _classify_field(payload, path)
        for path in INTENTIONALLY_MISSING_OR_UNAPPROVED_FIELDS
    )

    # 6. If expect_synthetic is set, require the marker.
    if expect_synthetic:
        if not synthetic:
            errors.append(
                "expect_synthetic=True but 'synthetic' is not True"
            )
        if not dry_run_meta_present:
            errors.append(
                "expect_synthetic=True but '_dry_run_meta' is "
                "missing or is not an object"
            )
        elif isinstance(dry_run_meta, dict):
            if "live_fred_used" not in dry_run_meta:
                errors.append(
                    "expect_synthetic=True but "
                    "_dry_run_meta.live_fred_used is missing"
                )
            else:
                live_fred_used = dry_run_meta["live_fred_used"]
                if not isinstance(live_fred_used, bool):
                    errors.append(
                        "expect_synthetic=True but "
                        f"_dry_run_meta.live_fred_used is "
                        f"{live_fred_used!r} "
                        "(must be boolean true/false)"
                    )
                elif live_fred_used is not False:
                    errors.append(
                        "expect_synthetic=True but "
                        f"_dry_run_meta.live_fred_used is "
                        f"{live_fred_used!r} (expected False)"
                    )

    # 7. For SOX (an unapproved source), require zero in any
    #    synthetic approved dry-run artifact. In a non-synthetic
    #    artifact, SOX is still not approved, so we just
    #    report the value without demanding zero.
    if synthetic and dry_run_meta_present:
        sox_status = _classify_field(payload, "semiconductor.sox")
        sox_change_status = _classify_field(
            payload, "semiconductor.sox_change_pct"
        )
        if sox_status.populated:
            errors.append(
                "synthetic approved dry-run artifact has nonzero "
                f"semiconductor.sox = {sox_status.value!r}; "
                "SOX adapter is not approved"
            )
        if sox_change_status.populated:
            errors.append(
                "synthetic approved dry-run artifact has nonzero "
                "semiconductor.sox_change_pct = "
                f"{sox_change_status.value!r}; "
                "SOX adapter is not approved"
            )

    return MarketContextArtifactReport(
        artifact_path=str(path),
        valid_json=True,
        valid_market_context=valid_market_context,
        session_date=session_date,
        synthetic=synthetic,
        dry_run_meta_present=dry_run_meta_present,
        populated_fields=populated_status,
        intentionally_missing_or_unapproved_fields=unapproved_status,
        errors=tuple(errors),
    )


def report_to_ordered_dict(
    report: MarketContextArtifactReport,
) -> Dict[str, Any]:
    """Convert a :class:`MarketContextArtifactReport` to a
    plain ``dict`` suitable for JSON serialization.

    The returned dict is a fresh copy; mutating it does not
    affect the report.
    """
    return {
        "artifact_path": report.artifact_path,
        "dry_run_meta_present": report.dry_run_meta_present,
        "errors": list(report.errors),
        "intentionally_missing_or_unapproved_fields": [
            s.to_dict()
            for s in report.intentionally_missing_or_unapproved_fields
        ],
        "ok": report.ok,
        "populated_fields": [s.to_dict() for s in report.populated_fields],
        "session_date": report.session_date,
        "synthetic": report.synthetic,
        "valid_json": report.valid_json,
        "valid_market_context": report.valid_market_context,
    }


def report_to_json_text(report: MarketContextArtifactReport) -> str:
    """Serialize a :class:`MarketContextArtifactReport` to
    deterministic UTF-8 JSON text.

    The output format is:

    * UTF-8 encoded.
    * ``ensure_ascii=False``.
    * ``indent=2``.
    * ``sort_keys=True``.
    * A final newline is appended.
    """
    text = json.dumps(
        report_to_ordered_dict(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text
