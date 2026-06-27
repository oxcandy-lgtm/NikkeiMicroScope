"""Deterministic JSON export for a composed :class:`MarketContext`.

This module is the read-only JSON export layer for NikkeiMicroScope.
It serializes an already-validated :class:`MarketContext` to
deterministic UTF-8 JSON, and writes the result to a local path
with a refuse-overwrite-by-default policy. It does **not** add a
new market data source. It does **not** perform network I/O. It
does **not** read environment credentials. It does **not** use
subprocess. It does **not** import broker SDKs, exchange clients,
or paid data sources.

Hard constraints (enforced socially and via unit tests):

* No new market data source. Only the already-approved
  :class:`MarketContext` schema and the four FRED overlay
  adapters may have contributed to the input context.
* No SOX adapter. Per
  ``docs/sox-source-selection.md`` and §8.5 of
  ``docs/data-adapter-contract.md``, no SOX / semiconductor
  adapter is approved yet, so the exported
  ``semiconductor`` section is left at whatever the base /
  composition provided — it must not be populated by a SOX
  source.
* No broker / auth / cookie / paid source.
* No subprocess / shell-out.
* No environment-variable credential reading.
* No new runtime dependencies; stdlib only.

The export format is deterministic:

* UTF-8.
* ``ensure_ascii=False``.
* ``indent=2``.
* ``sort_keys=True``.
* A final newline is appended.

The export layer is intentionally minimal. It does not include a
default live pipeline, a CLI flag for live network, or a
cron / systemd / timer integration.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from nms.data.models import MarketContext
from nms.data.validate import validate_market_context


def market_context_to_ordered_dict(ctx: MarketContext) -> Dict[str, Any]:
    """Convert a :class:`MarketContext` to a plain
    :class:`dict` suitable for JSON serialization.

    Steps:

    1. Re-validate the context through
       :func:`nms.data.validate.validate_market_context` to
       enforce the schema and nested strictness.
    2. Return a plain ``dict``.

    The returned dict is the same shape as the validated
    ``MarketContext`` payload that
    :func:`nms.data.validate.validate_market_context` accepts.
    The keys at the top level are sorted alphabetically when
    serialized to JSON by :func:`market_context_to_json_text`.
    """
    validated = validate_market_context(asdict(ctx))
    return asdict(validated)


def market_context_to_json_text(ctx: MarketContext) -> str:
    """Serialize a :class:`MarketContext` to deterministic
    UTF-8 JSON text.

    The output format is:

    * UTF-8 (``ensure_ascii=False`` so non-ASCII characters are
      preserved as-is).
    * ``indent=2`` (human-readable).
    * ``sort_keys=True`` (key order is deterministic).
    * A final newline is appended.

    Returns:
        A JSON string with a trailing newline.

    Raises:
        nms.data.ValidationError: If the input context fails
            re-validation.
    """
    ordered = market_context_to_ordered_dict(ctx)
    text = json.dumps(
        ordered,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_market_context_json(
    ctx: MarketContext,
    output_path: Path,
    *,
    allow_overwrite: bool = False,
) -> Path:
    """Write a :class:`MarketContext` to a local JSON file.

    The output is deterministic UTF-8 JSON (see
    :func:`market_context_to_json_text` for the format).

    Args:
        ctx: A :class:`MarketContext` to serialize.
        output_path: Destination path. Parent directories are
            created if needed.
        allow_overwrite: If ``False`` (the default), an
            existing file at ``output_path`` causes
            :class:`FileExistsError`. If ``True``, an existing
            file is overwritten.

    Returns:
        The path the JSON was written to (the same as
        ``output_path``).

    Raises:
        FileExistsError: If ``output_path`` exists and
            ``allow_overwrite`` is ``False``.
        nms.data.ValidationError: If the input context fails
            re-validation.
        OSError: If the file cannot be written for any other
            reason (e.g. parent is not a directory, permission
            denied).
    """
    output_path = Path(output_path)

    if output_path.exists() and not allow_overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing file: {output_path}. "
            "Pass allow_overwrite=True to override."
        )

    text = market_context_to_json_text(ctx)

    # Create the parent directory if needed. exist_ok=True
    # is safe because the parent may already exist.
    parent = output_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Open in text mode with explicit UTF-8 encoding and the
    # newline suffix that the deterministic format requires.
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return output_path
