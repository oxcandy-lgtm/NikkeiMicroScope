#!/usr/bin/env python3
"""Shadow replay manifest CLI.

Reads a local JSON input manifest and runs a shadow replay
over the rows, creating local shadow trial and (optionally)
close records and writing a deterministic result manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.shadow.replay import (
    ShadowReplayError,
    run_shadow_replay_manifest,
    shadow_replay_result_to_json_text,
    write_shadow_replay_result_json,
)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a shadow replay manifest from a local JSON "
            "input manifest."
        )
    )
    parser.add_argument(
        "--input-manifest",
        required=True,
        help="Path to the local JSON input manifest.",
    )
    parser.add_argument(
        "--trial-ledger-output",
        required=True,
        help="Destination JSONL trial ledger path.",
    )
    parser.add_argument(
        "--close-ledger-output",
        required=True,
        help="Destination JSONL close ledger path.",
    )
    parser.add_argument(
        "--result-output",
        required=True,
        help="Destination JSON result manifest path.",
    )
    parser.add_argument(
        "--created-at-utc",
        required=True,
        help="Operator-provided UTC ISO-8601 timestamp ending in 'Z'.",
    )
    parser.add_argument(
        "--overwrite-result",
        action="store_true",
        help="Allow overwriting the result file if it exists.",
    )
    args = parser.parse_args(argv)

    try:
        result = run_shadow_replay_manifest(
            Path(args.input_manifest),
            trial_ledger_path=Path(args.trial_ledger_output),
            close_ledger_path=Path(args.close_ledger_output),
            created_at_utc=args.created_at_utc,
        )
    except ShadowReplayError as exc:
        print(f"[shadow-replay] ERROR: {exc}")
        return 1

    try:
        write_shadow_replay_result_json(
            result,
            Path(args.result_output),
            allow_overwrite=args.overwrite_result,
        )
    except FileExistsError as exc:
        print(f"[shadow-replay] ERROR: {exc}")
        return 1

    # Print the deterministic JSON result to stdout.
    print(shadow_replay_result_to_json_text(result), end="")

    # Exit nonzero if any row had an error.
    has_error = any(
        r.status == "row_error" for r in result.rows
    )
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
