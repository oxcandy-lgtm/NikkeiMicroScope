#!/usr/bin/env bash
# Adapter composition dry-run script.
#
# Exercises ComposedMarketContextAdapter end-to-end with mocked
# http_get for all four FRED overlay adapters. No real network
# access. No environment variable reads. No subprocess calls. No
# raw FRED data committed in this script — the CSVs inside are
# small synthetic examples.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[compose-mc-dry-run] repo_root: ${REPO_ROOT}"
echo "[compose-mc-dry-run] python:   $(python3 --version 2>&1)"

python3 "${REPO_ROOT}/scripts/compose_market_context.py"
