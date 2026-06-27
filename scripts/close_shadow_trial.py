#!/usr/bin/env python3
"""Shadow trial close CLI.

Builds a :class:`nms.shadow.close.ShadowTrialCloseRecord`
from an existing local JSONL shadow trial ledger plus an
operator-provided close price, and appends it to a local
append-only JSONL close ledger.

This CLI is the no-cash close entry point. It is not paper
trading. It is not live trading. It does not place, route,
simulate, or transmit any order. It does not perform
network I/O, no subprocess, no environment credential
reads.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.shadow.close import (
    DEFAULT_CLOSE_LEDGER_PATH,
    ShadowTrialCloseError,
    append_shadow_trial_close_record_jsonl,
    build_shadow_trial_close_record,
    shadow_trial_close_record_to_json_text,
)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a no-cash shadow close record from a "
            "local shadow trial ledger and an operator-"
            "provided close price."
        )
    )
    parser.add_argument(
        "--trial-ledger",
        required=True,
        help="Path to the local JSONL shadow trial ledger.",
    )
    parser.add_argument(
        "--trial-id",
        required=True,
        help="trial_id of the trial to close.",
    )
    parser.add_argument(
        "--close-ledger-output",
        default=DEFAULT_CLOSE_LEDGER_PATH,
        help=(
            "Destination JSONL close ledger path. Default: "
            f"{DEFAULT_CLOSE_LEDGER_PATH}"
        ),
    )
    parser.add_argument(
        "--close-price",
        required=True,
        type=float,
        help="Operator-provided close price (must be > 0).",
    )
    parser.add_argument(
        "--closed-at-utc",
        required=True,
        help="Operator-provided UTC ISO-8601 timestamp ending in 'Z'.",
    )
    args = parser.parse_args(argv)

    ledger_path = Path(args.trial_ledger)
    close_ledger_path = Path(args.close_ledger_output)

    try:
        record = build_shadow_trial_close_record(
            ledger_path,
            trial_id=args.trial_id,
            close_price=args.close_price,
            closed_at_utc=args.closed_at_utc,
        )
    except ShadowTrialCloseError as exc:
        print(f"[shadow-close] ERROR: {exc}")
        return 1

    append_shadow_trial_close_record_jsonl(record, close_ledger_path)

    # Print the deterministic JSON record to stdout.
    print(shadow_trial_close_record_to_json_text(record), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
