# AGENTS.md — Operator and Agent Rules for NikkeiMicroScope

This file is the single source of truth for human operators, autonomous
agents, and code-generation tools working in this repository. It is
GitHub-visible and binding. If a lower-priority instruction (a chat reply, a
script, an LLM completion) conflicts with this file, **this file wins**.

## 1. GitHub-Visible Truth Rule

- Anything important must live in a file tracked by git on a branch that is
  reachable from a pull request.
- Operator chat, agent transcripts, and ephemeral reasoning are **not**
  authoritative. The PR is the truth.
- Generated Satellite exports are advisory. `source_of_truth: false`.

## 2. Branch and PR Workflow

- All work happens on a feature / bootstrap branch off `main`.
- **No direct push to `main`.** `main` is updated only by merging an
  approved, non-draft pull request.
- Force-push is forbidden on shared branches.
- Draft PRs are allowed during bootstrap. They must be marked ready for
  review before merge.

## 3. Forbidden Surfaces

The following are hard prohibitions in this repository:

- **No GitHub Issues.** Do not open, comment on, or react to issues. Use
  PRs and `docs/` for everything. See `GITHUB_ISSUES_BAN.md`.
- **No Personal Access Tokens (PAT).** No PAT-based auth, no PAT in code,
  config, docs, or commits. Use the GitHub App or `gh` CLI auth managed by
  the operator. See `GITHUB_TOKEN_POLICY.md`.
- **No secrets.** No `.env`, no API keys, no broker credentials, no
  private keys, no tokens of any kind in the repository. See
  `GITHUB_TOKEN_POLICY.md`.
- **No live trading or broker integration.** No order placement, no
  auto-execution, no broker SDK, no exchange adapter that can place
  orders. See `docs/risk-policy.md`.
- **No financial advice claims or profit guarantees.** See
  `docs/risk-policy.md` and `README.md` disclaimer.

## 4. Live-Trading Charter Gate

Live trading, broker integration, or any code path that can place orders
**must not** be added to this repository without an explicit operator
charter that:

1. Is committed to `docs/` as a dated, signed charter file.
2. Updates `docs/risk-policy.md` and `AGENTS.md` to reflect the new scope.
3. Passes a separate, non-bootstrap review PR.

Until that charter exists, MVP code paths must not import, require, or
reference any broker SDK or live-order API.

## 5. Implementation Reports

For every non-trivial change, the implementing agent (human or autonomous)
must produce an implementation report. The report is part of the PR
description or a file in the PR. It must include:

- **Scope:** what was added, modified, removed.
- **Files touched:** exact paths, with line refs (`file:line`) for
  non-trivial changes.
- **Validation:** commands run and their results.
- **Safety / privacy audit:** confirmation of no secrets, no PAT, no
  Issues API, no live-trading surface.
- **Non-claims:** explicit list of what the change does *not* claim
  (advice, profit, accuracy).
- **Blockers / unknowns:** anything that could not be verified.
- **Candidate next actions:** bounded next steps with type tags:
  `proof_followup_only` / `exact_fix_only` / `feature_work_after_review`.

## 6. Working Agreement

- Be conservative. When in doubt, do less.
- Prefer docs and tests over speculative code.
- Never widen scope without an explicit operator instruction recorded in
  the PR.
- Never bypass a forbidden surface (Issues, PAT, secrets, live trading)
  "just for this one task."

## 7. Satellite Mode Discipline

- `repo_mode: dry_run` is the default and stays the default.
- `satellite-pack.json` `managed_paths` are limited to CCL / Satellite
  support surfaces. Project-owned docs and code go in
  `local_override_paths`.
- Generated exports are advisory and must not be cited as canonical truth.
- The dry-run script `scripts/satellite-update-dry-run.sh` is the only
  sanctioned Satellite update entry point in this repo.
