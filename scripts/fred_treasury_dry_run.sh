#!/usr/bin/env bash
# Fred treasury dry-run script.
#
# Exercises the FRED public treasury adapter end-to-end with mocked
# ``http_get``. No real network access. No environment variable reads.
# No subprocess calls.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[fred-treasury-dry-run] repo_root: ${REPO_ROOT}"
echo "[fred-treasury-dry-run] python:   $(python3 --version 2>&1)"

python3 "${REPO_ROOT}/scripts/fred_treasury.py"
