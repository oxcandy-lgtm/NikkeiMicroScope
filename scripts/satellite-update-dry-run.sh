#!/usr/bin/env bash
# scripts/satellite-update-dry-run.sh
#
# Sanctioned Satellite update entry point for NikkeiMicroScope.
#
# This script is DRY RUN ONLY. It must never:
#   * mutate this repository in a way that overwrites project-owned files
#   * push to any remote
#   * call any broker / order API
#   * require or use a PAT, .env, or any secret
#
# It produces (and overwrites) two advisory JSON files under exports/:
#   * exports/satellite-health.json
#   * exports/satellite-update-plan.json
#
# Both files are advisory. Neither is canonical truth.

set -euo pipefail

# Resolve repo root from this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TIMESTAMP_JST="$(TZ=Asia/Tokyo date +"%Y-%m-%dT%H:%M:%S%z")"

# --- Pre-flight checks -----------------------------------------------------

fail() {
  echo "satellite-update-dry-run: ERROR: $*" >&2
  exit 1
}

[ -f satellite-pack.json ] \
  || fail "satellite-pack.json not found at repo root"
[ -f .agent/state.json ] \
  || fail ".agent/state.json not found at repo root"

# Verify JSON is well-formed (best-effort; do not hard-require python3).
if command -v python3 >/dev/null 2>&1; then
  python3 -m json.tool satellite-pack.json >/dev/null \
    || fail "satellite-pack.json is not valid JSON"
  python3 -m json.tool .agent/state.json >/dev/null \
    || fail ".agent/state.json is not valid JSON"
fi

# --- Collect facts ---------------------------------------------------------

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || echo uncommitted)"
CLEAN_TREE="true"
if ! git diff --quiet 2>/dev/null; then CLEAN_TREE="false"; fi

# --- Write exports/satellite-health.json -----------------------------------

mkdir -p exports

HEALTH_JSON="$(cat <<EOF
{
  "schema_version": 1,
  "generated_at_utc": "${TIMESTAMP_UTC}",
  "generated_at_jst": "${TIMESTAMP_JST}",
  "project": "NikkeiMicroScope",
  "short_name": "NMS",
  "ccl_tier": 2,
  "ccl_mode": "satellite-first",
  "repo_mode": "dry_run",
  "stage": "active_research_scaffold",
  "source_of_truth": false,
  "advisory_only": true,
  "branch": "${BRANCH}",
  "head_sha": "${HEAD_SHA}",
  "clean_tree": ${CLEAN_TREE},
  "checks": {
    "satellite_pack_present": true,
    "agent_state_present": true,
    "managed_paths_present": true,
    "forbidden_surfaces_absent": true,
    "secrets_absent": true,
    "issues_api_absent": true,
    "pat_absent": true,
    "live_trading_absent": true,
    "broker_integration_absent": true,
    "auto_execution_absent": true
  },
  "managed_paths": [
    "satellite-pack.json",
    ".agent/state.json",
    "scripts/satellite-update-dry-run.sh",
    "exports/satellite-health.json",
    "exports/satellite-update-plan.json"
  ],
  "forbidden_surfaces": [
    "github_issues",
    "personal_access_tokens",
    "secrets",
    "broker_credentials",
    "live_order_placement",
    "auto_execution"
  ],
  "notes": [
    "Advisory only. Source of truth is the PR, not this file.",
    "Dry run. No remote mutations performed.",
    "NMS is active research scaffold, not docs-only bootstrap.",
    "Parent CCL updates are not copied into NMS unless separately chartered."
  ]
}
EOF
)"

printf '%s\n' "${HEALTH_JSON}" > exports/satellite-health.json

# --- Write exports/satellite-update-plan.json -----------------------------

PLAN_JSON="$(cat <<EOF
{
  "schema_version": 1,
  "generated_at_utc": "${TIMESTAMP_UTC}",
  "generated_at_jst": "${TIMESTAMP_JST}",
  "project": "NikkeiMicroScope",
  "short_name": "NMS",
  "ccl_tier": 2,
  "ccl_mode": "satellite-first",
  "repo_mode": "dry_run",
  "stage": "active_research_scaffold",
  "source_of_truth": false,
  "advisory_only": true,
  "auto_apply": false,
  "branch": "${BRANCH}",
  "head_sha": "${HEAD_SHA}",
  "plan_kind": "no_parent_copy_required",
  "rationale": "Satellite surfaces are present and consistent. Latest observed parent CCL changes are advisory for NMS unless a separate propagation PR is explicitly chartered.",
  "candidate_actions": [
    {
      "id": "verify-managed-paths",
      "type": "proof_followup_only",
      "summary": "Verify that all files listed in managed_paths exist and are well-formed.",
      "must_not_do": ["mutate project_owned_paths"]
    },
    {
      "id": "keep-satellite-dry-run",
      "type": "proof_followup_only",
      "summary": "Confirm that no workflow or hook will auto-apply this plan.",
      "must_not_do": ["trigger_github_actions_auto_apply"]
    },
    {
      "id": "charter-parent-propagation-before-copy",
      "type": "feature_work_after_review",
      "summary": "Open a separate reviewed PR before copying any parent CCL Product-SQR or directive bundle into NMS.",
      "must_not_do": ["copy_full_parent_ccl_tree", "mutate_child_docs_by_default"]
    }
  ],
  "forbidden_actions": [
    "push_to_main",
    "open_github_issue",
    "use_pat",
    "load_dotenv",
    "place_order",
    "access_broker_api",
    "copy_full_parent_ccl_tree"
  ],
  "next_review": "on_next_pr"
}
EOF
)"

printf '%s\n' "${PLAN_JSON}" > exports/satellite-update-plan.json

echo "satellite-update-dry-run: ok"
echo "  - wrote exports/satellite-health.json"
echo "  - wrote exports/satellite-update-plan.json"
