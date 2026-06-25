#!/usr/bin/env bash
# FRED USDJPY dry-run script.
#
# Exercises the FRED public USDJPY adapter end-to-end with mocked
# ``http_get``. No real network access. No environment variable reads.
# No subprocess calls.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[fred-usdjpy-dry-run] repo_root: ${REPO_ROOT}"
echo "[fred-usdjpy-dry-run] python:   $(python3 --version 2>&1)"

python3 "${REPO_ROOT}/scripts/fred_usdjpy.py"
