#!/usr/bin/env python3
"""Shadow replay integrity checker CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nms.shadow.integrity import (
    build_shadow_replay_integrity_report,
    shadow_replay_integrity_report_to_json_text,
    write_shadow_replay_integrity_report_json,
)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check one shadow replay result manifest against local "
            "trial and close ledgers."
        )
    )
    parser.add_argument(
        "--result-manifest",
        required=True,
        help="Path to the local replay result JSON manifest.",
    )
    parser.add_argument(
        "--trial-ledger",
        required=True,
        help="Path to the local shadow trial JSONL ledger.",
    )
    parser.add_argument(
        "--close-ledger",
        required=True,
        help="Path to the local shadow close JSONL ledger.",
    )
    parser.add_argument(
        "--report-output",
        required=True,
        help="Destination JSON integrity report path.",
    )
    parser.add_argument(
        "--overwrite-report",
        action="store_true",
        help="Allow overwriting the report file if it exists.",
    )
    args = parser.parse_args(argv)

    report = build_shadow_replay_integrity_report(
        Path(args.result_manifest),
        trial_ledger_path=Path(args.trial_ledger),
        close_ledger_path=Path(args.close_ledger),
    )

    try:
        write_shadow_replay_integrity_report_json(
            report,
            Path(args.report_output),
            allow_overwrite=args.overwrite_report,
        )
    except FileExistsError as exc:
        print(f"[shadow-replay-integrity] ERROR: {exc}")
        return 1

    print(shadow_replay_integrity_report_to_json_text(report), end="")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
