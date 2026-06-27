#!/usr/bin/env bash
# FRED NASDAQ100 dry-run script.
#
# Exercises the FRED public NASDAQ-100 adapter end-to-end with
# mocked ``http_get``. No real network access. No environment
# variable reads. No subprocess calls. No raw FRED NASDAQ100 data
# is committed in this script — the CSVs inside are small synthetic
# examples.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[fred-nasdaq100-dry-run] repo_root: ${REPO_ROOT}"
echo "[fred-nasdaq100-dry-run] python:   $(python3 --version 2>&1)"

python3 "${REPO_ROOT}/scripts/fred_nasdaq100.py"
