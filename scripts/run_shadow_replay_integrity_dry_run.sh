#!/usr/bin/env bash
# Shadow replay integrity dry-run script.
#
# Generates a local replay result using temp artifacts and ledgers,
# then verifies that the result manifest references existing ledger
# records. This is counts/status-only. It does not write committed
# runtime artifacts and does not produce scored-result metrics.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[shadow-replay-integrity-dry-run] repo_root: ${REPO_ROOT}"
echo "[shadow-replay-integrity-dry-run] python:   $(python3 --version 2>&1)"

TMP_ARTIFACT_1="$(mktemp -t nms-integrity-artifact-1.XXXXXX.json)"
TMP_ARTIFACT_2="$(mktemp -t nms-integrity-artifact-2.XXXXXX.json)"
TMP_INPUT="$(mktemp -t nms-integrity-input.XXXXXX.json)"
TMP_TRIAL_LEDGER="$(mktemp -t nms-integrity-trial.XXXXXX.jsonl)"
TMP_CLOSE_LEDGER="$(mktemp -t nms-integrity-close.XXXXXX.jsonl)"
TMP_RESULT="$(mktemp -t nms-integrity-result.XXXXXX.json)"
TMP_REPORT="$(mktemp -t nms-integrity-report.XXXXXX.json)"
trap 'rm -f "${TMP_ARTIFACT_1}" "${TMP_ARTIFACT_2}" "${TMP_INPUT}" "${TMP_TRIAL_LEDGER}" "${TMP_CLOSE_LEDGER}" "${TMP_RESULT}" "${TMP_REPORT}"' EXIT

python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_ARTIFACT_1}" --overwrite > /dev/null
python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_ARTIFACT_2}" --overwrite > /dev/null

export TMP_INPUT TMP_ARTIFACT_1 TMP_ARTIFACT_2
python3 - <<'PY'
import json
import os
payload = {
    "schema_version": "shadow-replay-input/1",
    "rows": [
        {
            "row_id": "integrity-buy-001",
            "artifact_path": os.environ["TMP_ARTIFACT_1"],
            "planned_side": "buy",
            "reference_price": 40000.0,
            "trial_size": 1,
            "trial_created_at_utc": "2026-06-24T00:00:00Z",
            "close_price": 40125.0,
            "closed_at_utc": "2026-06-24T06:00:00Z",
            "expect_synthetic": True,
        },
        {
            "row_id": "integrity-sell-002",
            "artifact_path": os.environ["TMP_ARTIFACT_2"],
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
with open(os.environ["TMP_INPUT"], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
PY

python3 "${REPO_ROOT}/scripts/run_shadow_replay.py" \
    --input-manifest "${TMP_INPUT}" \
    --trial-ledger-output "${TMP_TRIAL_LEDGER}" \
    --close-ledger-output "${TMP_CLOSE_LEDGER}" \
    --result-output "${TMP_RESULT}" \
    --created-at-utc 2026-06-24T07:00:00Z \
    --overwrite-result > /dev/null

python3 "${REPO_ROOT}/scripts/check_shadow_replay_integrity.py" \
    --result-manifest "${TMP_RESULT}" \
    --trial-ledger "${TMP_TRIAL_LEDGER}" \
    --close-ledger "${TMP_CLOSE_LEDGER}" \
    --report-output "${TMP_REPORT}" \
    --overwrite-report > /dev/null

export TMP_REPORT
python3 - <<'PY'
import json
import os
import sys
with open(os.environ["TMP_REPORT"], "r", encoding="utf-8") as fh:
    report = json.load(fh)

if report.get("ok") is not True:
    print("[shadow-replay-integrity-dry-run] ERROR: report not ok")
    print(json.dumps(report, indent=2, sort_keys=True))
    sys.exit(1)

expected = {
    "result_rows": 2,
    "result_valid_rows": 2,
    "result_trial_refs": 2,
    "result_close_refs": 2,
}
for key, value in expected.items():
    if report.get(key) != value:
        print(
            f"[shadow-replay-integrity-dry-run] ERROR: {key}="
            f"{report.get(key)!r}; expected {value!r}"
        )
        sys.exit(1)

for forbidden in (
    "aggregate_delta",
    "average_delta",
    "total_delta",
    "score_average",
):
    if forbidden in report:
        print(
            "[shadow-replay-integrity-dry-run] ERROR: report contains "
            f"forbidden field {forbidden!r}"
        )
        sys.exit(1)

print(
    "[shadow-replay-integrity-dry-run] integrity ok: "
    f"result_rows={report['result_rows']}, "
    f"trial_refs={report['result_trial_refs']}, "
    f"close_refs={report['result_close_refs']}"
)
PY
