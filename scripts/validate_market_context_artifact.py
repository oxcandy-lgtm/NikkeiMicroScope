#!/usr/bin/env python3
"""MarketContext artifact validation CLI.

Reads an exported ``MarketContext`` JSON artifact from a
local file and prints (and optionally writes) a deterministic
validation report. No live network. No subprocess. No env
credential reads.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.data.artifact_report import (
    build_market_context_artifact_report,
    report_to_json_text,
)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a MarketContext JSON artifact and print "
            "a deterministic report."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the JSON artifact to validate.",
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
    parser.add_argument(
        "--report-output",
        default=None,
        help=(
            "Optional path to write the deterministic JSON "
            "report to. Refuses to overwrite an existing file."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Allow overwriting the --report-output file if it "
            "already exists."
        ),
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    report = build_market_context_artifact_report(
        input_path, expect_synthetic=args.expect_synthetic
    )

    # Always print the report to stdout.
    print(report_to_json_text(report), end="")

    # Optionally write the report to a file.
    if args.report_output:
        output_path = Path(args.report_output)
        if output_path.exists() and not args.overwrite:
            print(
                f"[artifact-report] ERROR: refusing to overwrite "
                f"existing file: {output_path}. Pass --overwrite "
                f"to override."
            )
            return 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(report_to_json_text(report))

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
