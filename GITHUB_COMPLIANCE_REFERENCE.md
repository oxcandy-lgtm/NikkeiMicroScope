# GITHUB_COMPLIANCE_REFERENCE.md

> Cross-reference. Lists where each compliance topic is enforced.

This file is **not** a policy. It points at the files that *are*
the policy. If a topic is missing from this index, that does not
mean it is permitted; it means the index is incomplete.

## Issues

- Policy: `GITHUB_ISSUES_BAN.md`
- Reinforced in: `AGENTS.md §3`, `GITHUB_STEWARDSHIP.md`

## Personal Access Tokens

- Policy: `GITHUB_TOKEN_POLICY.md`
- Reinforced in: `AGENTS.md §3`, `GITHUB_ACTIONS_SAFETY.md`

## Secrets in the Repository

- Policy: `GITHUB_TOKEN_POLICY.md`
- Reinforced in: `AGENTS.md §3`, `docs/risk-policy.md §2`

## Live Trading and Broker Integration

- Policy: `docs/risk-policy.md §1`
- Charter gate: `AGENTS.md §4`
- Reinforced in: `README.md`, `docs/product-spec.md`, `docs/architecture.md`

## Branch Protection and PR Workflow

- Policy: `GITHUB_PR_MERGE_POLICY.md`
- Enforcement: `GITHUB_BRANCH_PROTECTION.md`
- Reinforced in: `AGENTS.md §2`

## Workflow Safety

- Policy: `GITHUB_ACTIONS_SAFETY.md`
- Reinforced in: `GITHUB_TOKEN_POLICY.md`, `GITHUB_BRANCH_PROTECTION.md`

## Incident Response

- Policy: `GITHUB_AUTOMATION_INCIDENT_RESPONSE.md`
- Cross-referenced from: `GITHUB_TOKEN_POLICY.md`,
  `GITHUB_ISSUES_BAN.md`, `GITHUB_ACTIONS_SAFETY.md`

## Human / Platform Covenant

- Policy: `HUMAN_PLATFORM_COVENANT.md`
- Reinforced in: `AGENTS.md §6`

## CCL Tier 2 / Satellite

- Pack manifest: `satellite-pack.json`
- Agent state: `.agent/state.json`
- Dry-run entry: `scripts/satellite-update-dry-run.sh`
- Advisory exports: `exports/satellite-health.json`,
  `exports/satellite-update-plan.json`
- Reinforced in: `AGENTS.md §7`, `README.md`
