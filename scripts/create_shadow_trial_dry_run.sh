#!/usr/bin/env bash
# Shadow trial ledger dry-run script.
#
# Generates a synthetic artifact to a temp path using
# scripts/export_composed_market_context.py, validates it
# with scripts/validate_market_context_artifact.py
# --expect-synthetic, then calls
# scripts/create_shadow_trial.py to append a single
# shadow trial record to a temp JSONL ledger. Verifies
# the record shape, the ledger contents, and the
# `executable=false` invariant. Cleans up temp files.
# Does not commit any generated artifact or ledger.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[shadow-trial-dry-run] repo_root: ${REPO_ROOT}"
echo "[shadow-trial-dry-run] python:   $(python3 --version 2>&1)"

# 1. Generate a synthetic artifact to a temp path.
TMP_ARTIFACT="$(mktemp -t composed-market-context-dry-run.XXXXXX.json)"
TMP_LEDGER="$(mktemp -t shadow-trial-ledger-dry-run.XXXXXX.jsonl)"
trap 'rm -f "${TMP_ARTIFACT}" "${TMP_LEDGER}"' EXIT

python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_ARTIFACT}" \
    --overwrite

if [ ! -f "${TMP_ARTIFACT}" ]; then
    echo "[shadow-trial-dry-run] ERROR: expected artifact not found"
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
    echo "[shadow-trial-dry-run] ERROR: validator exited ${VALIDATE_EXIT}"
    exit 1
fi

# 3. Create the shadow trial record.
set +e
python3 "${REPO_ROOT}/scripts/create_shadow_trial.py" \
    --artifact "${TMP_ARTIFACT}" \
    --ledger-output "${TMP_LEDGER}" \
    --planned-side buy \
    --reference-price 40000 \
    --trial-size 1 \
    --created-at-utc 2026-06-24T00:00:00Z \
    --expect-synthetic > /dev/null
CREATE_EXIT=$?
set -e

if [ "${CREATE_EXIT}" -ne 0 ]; then
    echo "[shadow-trial-dry-run] ERROR: create_shadow_trial exited ${CREATE_EXIT}"
    exit 1
fi

# 4. Verify ledger exists and has exactly one JSONL line.
if [ ! -f "${TMP_LEDGER}" ]; then
    echo "[shadow-trial-dry-run] ERROR: ledger not found at ${TMP_LEDGER}"
    exit 1
fi

LINE_COUNT="$(wc -l < "${TMP_LEDGER}" | tr -d ' ')"
if [ "${LINE_COUNT}" -ne 1 ]; then
    echo "[shadow-trial-dry-run] ERROR: expected 1 line, got ${LINE_COUNT}"
    exit 1
fi

# 5. Verify the JSON contains the expected fields.
TMP_LEDGER_PATH="${TMP_LEDGER}"
export TMP_LEDGER_PATH

python3 - <<'PY'
import json
import os
import sys

with open(os.environ['TMP_LEDGER_PATH'], 'r', encoding='utf-8') as fh:
    line = fh.readline().rstrip('\n')
record = json.loads(line)

expected_keys = {
    'schema_version',
    'trial_id',
    'artifact_sha256',
    'session_date',
    'planned_side',
    'reference_price',
    'trial_size',
    'executable',
    'blocked_reason',
    'score',
}
missing = expected_keys - set(record.keys())
if missing:
    print(
        f'[shadow-trial-dry-run] ERROR: missing keys: {sorted(missing)}'
    )
    sys.exit(1)

if 'classification' not in record['score']:
    print("[shadow-trial-dry-run] ERROR: missing score.classification")
    sys.exit(1)

if record['executable'] is not False:
    print(
        f"[shadow-trial-dry-run] ERROR: executable is "
        f"{record['executable']!r}, expected False"
    )
    sys.exit(1)

if record['blocked_reason'] != 'shadow_trial_not_executable':
    print(
        f"[shadow-trial-dry-run] ERROR: blocked_reason is "
        f"{record['blocked_reason']!r}, expected "
        f"'shadow_trial_not_executable'"
    )
    sys.exit(1)

print(
    '[shadow-trial-dry-run] ledger ok: '
    f"executable={record['executable']}, "
    f"blocked_reason={record['blocked_reason']!r}, "
    f"score.classification={record['score']['classification']!r}"
)
PY
