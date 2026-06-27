#!/usr/bin/env bash
# MarketContext artifact validation dry-run script.
#
# Generates a synthetic artifact to a temp path using
# scripts/export_composed_market_context.py, then validates
# it with scripts/validate_market_context_artifact.py
# --expect-synthetic. Verifies the report flags the
# artifact as a valid, synthetic, ok approved dry-run
# artifact. Cleans up temp files. Does not commit any
# generated artifact.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[artifact-validate-dry-run] repo_root: ${REPO_ROOT}"
echo "[artifact-validate-dry-run] python:   $(python3 --version 2>&1)"

# 1. Generate a synthetic artifact to a temp path.
TMP_ARTIFACT="$(mktemp -t composed-market-context-dry-run.XXXXXX.json)"
TMP_REPORT="$(mktemp -t artifact-report-dry-run.XXXXXX.json)"
trap 'rm -f "${TMP_ARTIFACT}" "${TMP_REPORT}"' EXIT

python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_ARTIFACT}" \
    --overwrite

if [ ! -f "${TMP_ARTIFACT}" ]; then
    echo "[artifact-validate-dry-run] ERROR: expected artifact not found"
    exit 1
fi

# 2. Validate the artifact. Capture the exit code separately
#    so we can assert it after the report is verified.
set +e
python3 "${REPO_ROOT}/scripts/validate_market_context_artifact.py" \
    --input "${TMP_ARTIFACT}" \
    --expect-synthetic \
    --report-output "${TMP_REPORT}" \
    --overwrite > "${TMP_REPORT}.stdout"
EXIT_CODE=$?
set -e

# 3. Verify exit code is zero.
if [ "${EXIT_CODE}" -ne 0 ]; then
    echo "[artifact-validate-dry-run] ERROR: validator exited ${EXIT_CODE}"
    cat "${TMP_REPORT}.stdout"
    exit 1
fi

# 4. Verify the report contains the expected flags.
TMP_ARTIFACT_PATH="${TMP_ARTIFACT}"
TMP_REPORT_PATH="${TMP_REPORT}"
export TMP_ARTIFACT_PATH TMP_REPORT_PATH

python3 - <<'PY'
import json
import os
import sys

with open(os.environ['TMP_REPORT_PATH'], 'r', encoding='utf-8') as fh:
    report = json.load(fh)

expected_keys = {
    'valid_json': True,
    'valid_market_context': True,
    'synthetic': True,
    'dry_run_meta_present': True,
    'ok': True,
}
for k, v in expected_keys.items():
    if report.get(k) != v:
        print(
            f"[artifact-validate-dry-run] ERROR: report[{k!r}] "
            f"= {report.get(k)!r}, expected {v!r}"
        )
        sys.exit(1)

# 5. Confirm the report was generated from the synthetic
#    artifact we just produced.
if report.get('artifact_path') != os.environ['TMP_ARTIFACT_PATH']:
    print(
        f"[artifact-validate-dry-run] ERROR: report.artifact_path "
        f"= {report.get('artifact_path')!r}, expected "
        f"{os.environ['TMP_ARTIFACT_PATH']!r}"
    )
    sys.exit(1)

# 6. Confirm no errors.
if report.get('errors'):
    print(
        f"[artifact-validate-dry-run] ERROR: report.errors = "
        f"{report.get('errors')!r}"
    )
    sys.exit(1)

print(
    '[artifact-validate-dry-run] valid_json=True, '
    'valid_market_context=True, synthetic=True, '
    'dry_run_meta_present=True, ok=True'
)
PY
