# GITHUB_BRANCH_PROTECTION.md

> Binding. See `AGENTS.md §2` and `GITHUB_PR_MERGE_POLICY.md`.

## `main` Branch Protection

The `main` branch in this repository must be protected with the
following settings (the operator is responsible for applying them
via the GitHub UI or `gh api`):

- **Require a pull request before merging.** Direct push to `main`
  is rejected.
- **Require approvals:** at least 1.
- **Dismiss stale pull request approvals when new commits are
  pushed.**
- **Require review from Code Owners** (once a `CODEOWNERS` file
  is added; until then, require review from the operator).
- **Require status checks to pass before merging.** Status checks
  must include at least the JSON validation step (see
  `GITHUB_ACTIONS_SAFETY.md`).
- **Require linear history** (recommended) — prevents merge
  commits that obscure the diff between feature branch and `main`.
- **Require signed commits** (recommended) — operator-only
  signing key, no PAT, no third-party.
- **Do not allow force pushes.**
- **Do not allow deletions.**
- **Restrict who can push to matching branches:** the operator
  account only, and only via PR (effectively a no-op for direct
  push but enforces the intent).
- **Allow auto-merge:** disabled by default. The operator must
  click the merge button explicitly.

## Working Branches

- Working branches are **not** protected by default. They are
  short-lived and operator-controlled.
- A working branch must be deleted within 7 days of merge, unless
  the operator records an exception in the PR.
- Branch names follow `codex/<short-slug>` for codex-driven
  work, and `<author-or-topic>/<short-slug>` otherwise.

## Tags

- Tags are signed (operator GPG key, no PAT).
- Tags are immutable once pushed.
- Tag names follow `vMAJOR.MINOR.PATCH` and are cut only from
  `main`.

## Why

- A research / observation tool must not silently mutate itself.
- The protection settings above are the GitHub-side enforcement
  of `AGENTS.md §2` and `GITHUB_PR_MERGE_POLICY.md`.
- Without these settings, a leaked credential or a misconfigured
  automation could push forbidden content to `main`.
