#!/usr/bin/env bash
# scripts/validate-fixtures.sh
#
# Run the read-only fixture validation:
#   * compile the nms package and tests
#   * run the stdlib unittest suite
#   * re-validate the sample fixture via the public adapter
#
# This script is intentionally local and read-only. It:
#   * does not perform network access;
#   * does not read environment-variable credentials;
#   * does not write outside the working tree's test/cache paths
#     (compileall may emit a small .pyc under __pycache__, which is
#     gitignored);
#   * does not touch exports/.

set -euo pipefail

# Resolve repo root from this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo "[validate-fixtures] repo_root: ${REPO_ROOT}"
echo "[validate-fixtures] python:   $(python3 --version 2>&1)"

echo
echo "=== [1/3] compileall: nms + tests ==="
python3 -m compileall -q nms tests

echo
echo "=== [2/3] unittest discover -s tests ==="
python3 -m unittest discover -s tests -v

echo
echo "=== [3/3] public adapter smoke test on sample fixture ==="
python3 - <<'PY'
"""End-to-end smoke test via the public adapter API.

This runs entirely on local fixture data. It performs no network
access, no subprocess, no environment credential reads.
"""
from pathlib import Path
from nms.data import FixtureMarketContextAdapter

REPO_ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "market_context"

adapter = FixtureMarketContextAdapter(base_path=FIXTURE_DIR)
ctx = adapter.load("2026-06-24")

print(f"  session_date          = {ctx.session_date}")
print(f"  timezone              = {ctx.timezone}")
print(f"  us_equities.sp500     = {ctx.us_equities.sp500}")
print(f"  fx.usdjpy             = {ctx.fx.usdjpy}")
print(f"  us_yields.us10y       = {ctx.us_yields.us10y}")
print(f"  nikkei_night.close    = {ctx.nikkei_night_session.close}")
print(f"  previous_day.close    = {ctx.previous_day.close}")
print(f"  events count          = {len(ctx.economic_event_risk.events)}")
print(f"  intraday range        = {ctx.intraday_range.first_15m_range}")
print(f"  realized_vol          = {ctx.volatility_context.realized_vol}")
PY

echo
echo "[validate-fixtures] OK"
