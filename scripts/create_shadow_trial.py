#!/usr/bin/env python3
"""Shadow trial creation CLI.

Builds a :class:`nms.shadow.ledger.ShadowTrialRecord` from
a local :class:`MarketContext` JSON artifact, appends it to
a JSONL ledger, and prints the deterministic JSON record to
stdout.

This CLI is the no-cash entry point for the shadow trial
ledger. It is not paper trading. It is not live trading. It
does not place, route, simulate, or transmit any order. It
performs no network I/O, no subprocess, no environment
credential reads.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.shadow.ledger import (
    DEFAULT_LEDGER_PATH,
    build_shadow_trial_record,
    shadow_trial_record_to_json_text,
    append_shadow_trial_record_jsonl,
)
from nms.shadow.ledger import ShadowTrialLedgerError


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a no-cash shadow trial ledger entry from "
            "a local MarketContext JSON artifact."
        )
    )
    parser.add_argument(
        "--artifact",
        required=True,
        help="Path to the JSON artifact to record a trial for.",
    )
    parser.add_argument(
        "--ledger-output",
        default=DEFAULT_LEDGER_PATH,
        help=(
            "Destination JSONL ledger path. Default: "
            f"{DEFAULT_LEDGER_PATH}"
        ),
    )
    parser.add_argument(
        "--planned-side",
        required=True,
        choices=("buy", "sell", "none"),
        help="Planned side: buy, sell, or none.",
    )
    parser.add_argument(
        "--reference-price",
        required=True,
        type=float,
        help="Reference price (must be > 0).",
    )
    parser.add_argument(
        "--trial-size",
        required=True,
        type=int,
        help="Trial size (must be > 0).",
    )
    parser.add_argument(
        "--created-at-utc",
        required=True,
        help="UTC ISO-8601 timestamp ending in 'Z'.",
    )
    parser.add_argument(
        "--expect-synthetic",
        action="store_true",
        help=(
            "Require the artifact to declare "
            "'synthetic: true' and '_dry_run_meta' with "
            "'live_fred_used: false'."
        ),
    )
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact)
    ledger_path = Path(args.ledger_output)

    try:
        record = build_shadow_trial_record(
            artifact_path,
            planned_side=args.planned_side,
            reference_price=args.reference_price,
            trial_size=args.trial_size,
            created_at_utc=args.created_at_utc,
            expect_synthetic=args.expect_synthetic,
        )
    except ShadowTrialLedgerError as exc:
        print(f"[shadow-trial] ERROR: {exc}")
        return 1

    append_shadow_trial_record_jsonl(record, ledger_path)

    # Print the deterministic JSON record to stdout.
    print(shadow_trial_record_to_json_text(record), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
