"""JSON fixture loader for NikkeiMicroScope.

This module is pure local file I/O. It MUST NOT import network
libraries, broker SDKs, ``dotenv``, or shell out to external
processes. The constraint is enforced by
``tests/test_fixture_loader.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nms.data.validate import validate_market_context


def load_fixture_file(path: str | Path) -> "MarketContext":  # noqa: F821
    """Load and validate a single fixture file.

    Returns a :class:`nms.data.models.MarketContext`. Raises
    :class:`FileNotFoundError` if the file is missing, :class:`json.JSONDecodeError`
    if the file is not valid JSON, and :class:`nms.data.validate.ValidationError`
    if the parsed payload does not match the expected schema.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return validate_market_context(raw)


def load_fixture_dict(data: Mapping[str, Any]):
    """Validate an already-parsed fixture dict.

    Exposed for tests that want to exercise the validator without
    touching the filesystem.
    """
    return validate_market_context(data)
