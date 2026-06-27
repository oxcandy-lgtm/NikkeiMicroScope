#!/usr/bin/env bash
# Shadow trial close dry-run script.
#
# Generates a synthetic artifact to a temp path with
# scripts/export_composed_market_context.py, validates it,
# creates a shadow trial record in a temp trial ledger
# with scripts/create_shadow_trial.py, extracts the trial_id
# from the trial ledger using Python, then calls
# scripts/close_shadow_trial.py to append a single close
# record to a temp close ledger. Verifies the record shape,
# the ledger contents, the `executable=false` invariant,
# and the expected delta computation for the dry-run buy
# case. Cleans up temp files. Does not commit any generated
# artifact or ledger.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[shadow-close-dry-run] repo_root: ${REPO_ROOT}"
echo "[shadow-close-dry-run] python:   $(python3 --version 2>&1)"

# 1. Generate a synthetic artifact to a temp path.
TMP_ARTIFACT="$(mktemp -t composed-market-context-dry-run.XXXXXX.json)"
TMP_TRIAL_LEDGER="$(mktemp -t shadow-trial-ledger-dry-run.XXXXXX.jsonl)"
TMP_CLOSE_LEDGER="$(mktemp -t shadow-close-ledger-dry-run.XXXXXX.jsonl)"
trap 'rm -f "${TMP_ARTIFACT}" "${TMP_TRIAL_LEDGER}" "${TMP_CLOSE_LEDGER}"' EXIT

python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_ARTIFACT}" \
    --overwrite > /dev/null

if [ ! -f "${TMP_ARTIFACT}" ]; then
    echo "[shadow-close-dry-run] ERROR: expected artifact not found"
    exit 1
fi

# 2. Validate the artifact.
set +e
python3 "${REPO_ROOT}/scripts/validate_market_context_artifact.py" \
    --input "${TMP_ARTIFACT}" \
    --expect-synthetic > /dev/null
VALIDATE_EXIT=$?
set -e

if [ "${VALIDATE_EXIT}" -ne 0 ]; then
    echo "[shadow-close-dry-run] ERROR: validator exited ${VALIDATE_EXIT}"
    exit 1
fi

# 3. Create a shadow trial record in a temp trial ledger.
set +e
python3 "${REPO_ROOT}/scripts/create_shadow_trial.py" \
    --artifact "${TMP_ARTIFACT}" \
    --ledger-output "${TMP_TRIAL_LEDGER}" \
    --planned-side buy \
    --reference-price 40000 \
    --trial-size 1 \
    --created-at-utc 2026-06-24T00:00:00Z \
    --expect-synthetic > /dev/null
CREATE_EXIT=$?
set -e

if [ "${CREATE_EXIT}" -ne 0 ]; then
    echo "[shadow-close-dry-run] ERROR: create_shadow_trial exited ${CREATE_EXIT}"
    exit 1
fi

# 4. Extract trial_id from the trial ledger.
TMP_TRIAL_LEDGER_PATH="${TMP_TRIAL_LEDGER}"
export TMP_TRIAL_LEDGER_PATH
TRIAL_ID="$(python3 - <<'PY'
import json
import os
with open(os.environ['TMP_TRIAL_LEDGER_PATH'], 'r', encoding='utf-8') as fh:
    line = fh.readline().rstrip('\n')
record = json.loads(line)
print(record['trial_id'])
PY
)"

# 5. Call close_shadow_trial.py.
set +e
python3 "${REPO_ROOT}/scripts/close_shadow_trial.py" \
    --trial-ledger "${TMP_TRIAL_LEDGER}" \
    --trial-id "${TRIAL_ID}" \
    --close-ledger-output "${TMP_CLOSE_LEDGER}" \
    --close-price 40125 \
    --closed-at-utc 2026-06-24T06:00:00Z > /dev/null
CLOSE_EXIT=$?
set -e

if [ "${CLOSE_EXIT}" -ne 0 ]; then
    echo "[shadow-close-dry-run] ERROR: close_shadow_trial exited ${CLOSE_EXIT}"
    exit 1
fi

# 6. Verify close ledger exists and has exactly one line.
if [ ! -f "${TMP_CLOSE_LEDGER}" ]; then
    echo "[shadow-close-dry-run] ERROR: close ledger not found"
    exit 1
fi

LINE_COUNT="$(wc -l < "${TMP_CLOSE_LEDGER}" | tr -d ' ')"
if [ "${LINE_COUNT}" -ne 1 ]; then
    echo "[shadow-close-dry-run] ERROR: expected 1 line, got ${LINE_COUNT}"
    exit 1
fi

# 7. Verify the JSON contains the expected fields and values.
TMP_CLOSE_LEDGER_PATH="${TMP_CLOSE_LEDGER}"
export TMP_CLOSE_LEDGER_PATH

python3 - <<'PY'
import json
import os
import sys

with open(os.environ['TMP_CLOSE_LEDGER_PATH'], 'r', encoding='utf-8') as fh:
    line = fh.readline().rstrip('\n')
record = json.loads(line)

expected_keys = {
    'schema_version',
    'close_id',
    'trial_id',
    'source_ledger_sha256',
    'planned_side',
    'reference_price',
    'close_price',
    'price_delta_points',
    'directional_delta_points',
    'executable',
    'blocked_reason',
}
missing = expected_keys - set(record.keys())
if missing:
    print(
        f'[shadow-close-dry-run] ERROR: missing keys: {sorted(missing)}'
    )
    sys.exit(1)

if record['executable'] is not False:
    print(
        f"[shadow-close-dry-run] ERROR: executable is "
        f"{record['executable']!r}, expected False"
    )
    sys.exit(1)

if record['blocked_reason'] != 'shadow_close_not_executable':
    print(
        f"[shadow-close-dry-run] ERROR: blocked_reason is "
        f"{record['blocked_reason']!r}, expected "
        f"'shadow_close_not_executable'"
    )
    sys.exit(1)

# Verify the dry-run buy case: reference_price=40000, close_price=40125.
if record['reference_price'] != 40000.0:
    print(
        f"[shadow-close-dry-run] ERROR: reference_price is "
        f"{record['reference_price']!r}, expected 40000.0"
    )
    sys.exit(1)
if record['close_price'] != 40125.0:
    print(
        f"[shadow-close-dry-run] ERROR: close_price is "
        f"{record['close_price']!r}, expected 40125.0"
    )
    sys.exit(1)
if record['price_delta_points'] != 125.0:
    print(
        f"[shadow-close-dry-run] ERROR: price_delta_points is "
        f"{record['price_delta_points']!r}, expected 125.0"
    )
    sys.exit(1)
if record['directional_delta_points'] != 125.0:
    print(
        f"[shadow-close-dry-run] ERROR: directional_delta_points "
        f"is {record['directional_delta_points']!r}, expected 125.0"
    )
    sys.exit(1)

print(
    '[shadow-close-dry-run] close ok: '
    f"executable={record['executable']}, "
    f"blocked_reason={record['blocked_reason']!r}, "
    f"price_delta_points={record['price_delta_points']}, "
    f"directional_delta_points={record['directional_delta_points']}"
)
PY
