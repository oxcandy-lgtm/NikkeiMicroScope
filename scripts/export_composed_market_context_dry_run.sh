#!/usr/bin/env bash
# Composed MarketContext JSON export dry-run script.
#
# Exercises write_market_context_json end-to-end with mocked
# http_get for all four FRED overlay adapters. No real network
# access. No environment variable reads. No subprocess calls.
# No raw FRED data is committed in this script — the CSVs
# inside are small synthetic examples with placeholder values.
#
# The Python script writes to a temporary directory so this
# wrapper does not leave committed artifacts behind unless
# explicitly configured. To commit a synthetic example, run
# the Python script directly with a path under
# exports/dry-run/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[export-mc-dry-run] repo_root: ${REPO_ROOT}"
echo "[export-mc-dry-run] python:   $(python3 --version 2>&1)"

# Use a temporary output path so this wrapper does not commit
# any artifact. Operators who want a committed synthetic
# example should run the Python script directly with an
# explicit --output path under exports/dry-run/.
TMP_OUTPUT="$(mktemp -t composed-market-context-dry-run.XXXXXX.json)"
trap 'rm -f "${TMP_OUTPUT}"' EXIT

python3 "${REPO_ROOT}/scripts/export_composed_market_context.py" \
    --output "${TMP_OUTPUT}" \
    --overwrite

if [ ! -f "${TMP_OUTPUT}" ]; then
    echo "[export-mc-dry-run] ERROR: expected output file not found"
    exit 1
fi

# Verify the output: valid JSON, expected top-level keys,
# non-zero overlay fields, SOX unchanged from base, synthetic
# marker present. All checks run via env-var-passed paths so
# the embedded Python script does not depend on shell
# variable interpolation.
TMP_OUTPUT_PATH="${TMP_OUTPUT}"
BASE_FIXTURE_PATH="${REPO_ROOT}/fixtures/market_context/sample-session-2026-06-24.json"
export TMP_OUTPUT_PATH BASE_FIXTURE_PATH

python3 - <<'PY'
import json
import os
import sys

with open(os.environ['TMP_OUTPUT_PATH'], 'r', encoding='utf-8') as fh:
    payload = json.load(fh)
with open(os.environ['BASE_FIXTURE_PATH'], 'r', encoding='utf-8') as fh:
    base = json.load(fh)

# 1. Top-level keys.
expected_top_keys = {
    'session_date', 'us_yields', 'us_equities', 'fx', 'semiconductor',
}
missing = expected_top_keys - set(payload.keys())
if missing:
    print(
        f'[export-mc-dry-run] ERROR: missing top-level keys: '
        f'{sorted(missing)}'
    )
    sys.exit(1)

# 2. Overlay fields are non-zero (i.e. all four approved FRED
#    overlays were applied).
checks = [
    ('us_yields', 'us2y'),
    ('us_yields', 'us10y'),
    ('us_yields', 'us10y_minus_us2y'),
    ('us_yields', 'us10y_change_bp'),
    ('us_equities', 'sp500'),
    ('us_equities', 'sp500_change_pct'),
    ('fx', 'usdjpy'),
    ('fx', 'usdjpy_change_pct'),
    ('us_equities', 'nasdaq100'),
    ('us_equities', 'nasdaq100_change_pct'),
]
for section, key in checks:
    v = payload[section][key]
    if v == 0 or v == 0.0:
        print(f'[export-mc-dry-run] ERROR: {section}.{key} = 0')
        sys.exit(1)

# 3. SOX remains unchanged from the base. No SOX adapter is
#    in the composition, so semiconductor.sox and
#    semiconductor.sox_change_pct must equal the base
#    fixture's values.
base_sox = base['semiconductor']['sox']
base_sox_change = base['semiconductor']['sox_change_pct']
out_sox = payload['semiconductor']['sox']
out_sox_change = payload['semiconductor']['sox_change_pct']
if out_sox != base_sox:
    print(
        f'[export-mc-dry-run] ERROR: semiconductor.sox = {out_sox} '
        f'(expected {base_sox} from base; SOX adapter is not approved)'
    )
    sys.exit(1)
if out_sox_change != base_sox_change:
    print(
        f'[export-mc-dry-run] ERROR: semiconductor.sox_change_pct = '
        f'{out_sox_change} (expected {base_sox_change} from base)'
    )
    sys.exit(1)

# 4. Synthetic marker is present.
if not payload.get('synthetic') and not payload.get('_dry_run_meta'):
    print(
        '[export-mc-dry-run] ERROR: dry-run payload missing synthetic marker'
    )
    sys.exit(1)

print('[export-mc-dry-run] payload validated ok')
print(f'[export-mc-dry-run] semiconductor.sox = {out_sox} (unchanged from base, no SOX adapter applied)')
PY
