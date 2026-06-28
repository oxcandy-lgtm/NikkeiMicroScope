#!/usr/bin/env bash
# Shadow replay dry-run script.
#
# Generates two synthetic artifacts to temp paths using
# scripts/export_composed_market_context.py. Builds a
# local input manifest with two rows (one buy, one sell).
# Calls scripts/run_shadow_replay.py with temp ledgers
# and a temp result path. Verifies the trial ledger,
# close ledger, and result manifest contents. Verifies
# the result manifest contains counts only and no
# aggregate delta / forbidden performance fields.
# Cleans up temp files. Does not commit any generated
# artifact or ledger.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[shadow-replay-dry-run] repo_root: ${REPO_ROOT}"
echo "[shadow-replay-dry-run] python:   $(python3 --version 2>&1)"

# 1. Generate two synthetic artifacts.
TMP_ARTIFACT_1="$(mktemp -t composed-market-context-1.XXXXXX.json)"
TMP_ARTIFACT_2="$(mktemp -t composed-market-context-2.XXXXXX.json)"
TMP_TRIAL_LEDGER="$(mktemp -t shadow-trial-ledger-dry-run.XXXXXX.jsonl)"
TMP_CLOSE_LEDGER="$(mktemp -t shadow-close-ledger-dry-run.XXXXXX.jsonl)"
TMP_RESULT="$(mktemp -t shadow-replay-result-dry-run.XXXXXX.json)"
TMP_INPUT="$(mktemp -t shadow-replay-input-dry-run.XXXXXX.json)"
trap 'rm -f "${TMP_ARTIFACT_1}" "${TMP_ARTIFACT_2}" "${TMP_TRIAL_LEDGER}" "${TMP_CLOSE_LEDGER}" "${TMP_RESULT}" "${TMP_INPUT}"' EXIT

python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_ARTIFACT_1}" --overwrite > /dev/null
python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_ARTIFACT_2}" --overwrite > /dev/null

if [ ! -f "${TMP_ARTIFACT_1}" ] || [ ! -f "${TMP_ARTIFACT_2}" ]; then
    echo "[shadow-replay-dry-run] ERROR: artifacts not produced"
    exit 1
fi

# 2. Build the local input manifest with two rows.
TMP_INPUT_PATH="${TMP_INPUT}"
TMP_ARTIFACT_1_PATH="${TMP_ARTIFACT_1}"
TMP_ARTIFACT_2_PATH="${TMP_ARTIFACT_2}"
export TMP_INPUT_PATH
TMP_ARTIFACT_1_PATH="${TMP_ARTIFACT_1}"
TMP_ARTIFACT_2_PATH="${TMP_ARTIFACT_2}"
export TMP_INPUT_PATH TMP_ARTIFACT_1_PATH TMP_ARTIFACT_2_PATH

python3 - <<'PY'
import json
import os
out = {
    "schema_version": "shadow-replay-input/1",
    "rows": [
        {
            "row_id": "row-buy-001",
            "artifact_path": os.environ["TMP_ARTIFACT_1_PATH"],
            "planned_side": "buy",
            "reference_price": 40000.0,
            "trial_size": 1,
            "trial_created_at_utc": "2026-06-24T00:00:00Z",
            "close_price": 40125.0,
            "closed_at_utc": "2026-06-24T06:00:00Z",
            "expect_synthetic": True,
        },
        {
            "row_id": "row-sell-002",
            "artifact_path": os.environ["TMP_ARTIFACT_2_PATH"],
            "planned_side": "sell",
            "reference_price": 40000.0,
            "trial_size": 1,
            "trial_created_at_utc": "2026-06-25T00:00:00Z",
            "close_price": 39900.0,
            "closed_at_utc": "2026-06-25T06:00:00Z",
            "expect_synthetic": True,
        },
    ],
}
with open(os.environ["TMP_INPUT_PATH"], "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, sort_keys=True)
PY

# 3. Call run_shadow_replay.py.
set +e
python3 "${REPO_ROOT}/scripts/run_shadow_replay.py" \
    --input-manifest "${TMP_INPUT}" \
    --trial-ledger-output "${TMP_TRIAL_LEDGER}" \
    --close-ledger-output "${TMP_CLOSE_LEDGER}" \
    --result-output "${TMP_RESULT}" \
    --created-at-utc 2026-06-24T07:00:00Z \
    --overwrite-result > /dev/null
REPLAY_EXIT=$?
set -e

if [ "${REPLAY_EXIT}" -ne 0 ]; then
    echo "[shadow-replay-dry-run] ERROR: replay exited ${REPLAY_EXIT}"
    exit 1
fi

# 4. Verify trial ledger, close ledger, and result manifest.
if [ ! -f "${TMP_TRIAL_LEDGER}" ]; then
    echo "[shadow-replay-dry-run] ERROR: trial ledger not found"
    exit 1
fi
if [ ! -f "${TMP_CLOSE_LEDGER}" ]; then
    echo "[shadow-replay-dry-run] ERROR: close ledger not found"
    exit 1
fi
if [ ! -f "${TMP_RESULT}" ]; then
    echo "[shadow-replay-dry-run] ERROR: result manifest not found"
    exit 1
fi

# 5. Verify the result manifest contents.
TMP_TRIAL_LEDGER_PATH="${TMP_TRIAL_LEDGER}"
TMP_CLOSE_LEDGER_PATH="${TMP_CLOSE_LEDGER}"
TMP_RESULT_PATH="${TMP_RESULT}"
export TMP_TRIAL_LEDGER_PATH TMP_CLOSE_LEDGER_PATH TMP_RESULT_PATH

python3 - <<'PY'
import json
import os
import sys

with open(os.environ["TMP_TRIAL_LEDGER_PATH"], "r", encoding="utf-8") as fh:
    trial_lines = [l for l in fh.read().splitlines() if l]
with open(os.environ["TMP_CLOSE_LEDGER_PATH"], "r", encoding="utf-8") as fh:
    close_lines = [l for l in fh.read().splitlines() if l]
with open(os.environ["TMP_RESULT_PATH"], "r", encoding="utf-8") as fh:
    result = json.load(fh)

if len(trial_lines) != 2:
    print(
        f"[shadow-replay-dry-run] ERROR: trial ledger has "
        f"{len(trial_lines)} lines, expected 2"
    )
    sys.exit(1)
if len(close_lines) != 2:
    print(
        f"[shadow-replay-dry-run] ERROR: close ledger has "
        f"{len(close_lines)} lines, expected 2"
    )
    sys.exit(1)

for k, expected in (
    ("requested_rows", 2),
    ("valid_rows", 2),
    ("trial_records_created", 2),
    ("close_records_created", 2),
):
    if result.get(k) != expected:
        print(
            f"[shadow-replay-dry-run] ERROR: result[{k!r}] = "
            f"{result.get(k)!r}, expected {expected}"
        )
        sys.exit(1)

for row in result.get("rows", []):
    if row.get("status") != "close_created":
        print(
            f"[shadow-replay-dry-run] ERROR: row "
            f"{row.get('row_id')!r} status is "
            f"{row.get('status')!r}, expected 'close_created'"
        )
        sys.exit(1)

# No aggregate delta fields.
for forbidden in (
    "aggregate_delta",
    "average_delta",
    "total_delta",
    "score_average",
    "win_loss_count",
    "equity_curve",
    "portfolio",
    "pnl",
    "profit",
    "loss",
    "return_pct",
    "win_rate",
    "sharpe",
    "expected_return",
    "position",
    "cash_balance",
    "performance",
):
    if forbidden in result:
        print(
            f"[shadow-replay-dry-run] ERROR: result contains "
            f"forbidden field {forbidden!r}"
        )
        sys.exit(1)

print(
    "[shadow-replay-dry-run] replay ok: "
    f"requested_rows={result['requested_rows']}, "
    f"valid_rows={result['valid_rows']}, "
    f"trial_records_created={result['trial_records_created']}, "
    f"close_records_created={result['close_records_created']}"
)
PY
