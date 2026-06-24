# GITHUB_ACTIONS_SAFETY.md

> Binding. See `AGENTS.md §3` and `GITHUB_TOKEN_POLICY.md`.

## Default Posture

- **Read-only workflows by default.** A workflow in this repository
  must declare the minimum permissions it needs, and that minimum
  is usually `contents: read`.
- No workflow in MVP writes to the repository from automation. All
  state changes are operator-initiated PRs.

## Forbidden Workflow Patterns

The following are hard prohibitions. Any workflow that contains one
must not be merged.

- `pull_request_target` — forks can run untrusted code with
  elevated scopes.
- `issues: write` — we do not use Issues at all
  (see `GITHUB_ISSUES_BAN.md`).
- `contents: write` on bootstrap or on `main` — the bootstrap PR
  explicitly does not add any workflow with `contents: write`.
- Any reference to a Personal Access Token as a `secret:` value.
- Any `actions/checkout` with a `token:` parameter pointing to a
  PAT. The default `GITHUB_TOKEN` is acceptable **only** for
  read-only scopes, and only with explicit justification in the PR.
- Cron-scheduled workflows that auto-apply Satellite updates.
  Satellite updates are advisory and require a human or an
  explicit workflow run, never an unattended schedule.
- Self-hosted runners that have access to credentials, network
  egress, or long-lived state.

## Allowed Patterns (with Justification)

- `on: pull_request` workflows that lint, validate JSON, and
  render docs. Permissions: `contents: read`.
- `on: workflow_dispatch` workflows that produce advisory
  artifacts under `exports/`. Permissions: `contents: read`,
  artifact write only.
- `on: push` to non-`main` branches: same as `pull_request`.

## Permissions Block

Every workflow in this repository must start with an explicit
`permissions:` block. The default is:

```yaml
permissions:
  contents: read
```

Adding any other scope requires a justification comment in the
workflow file and a note in the PR description.

## Bootstrap Note

The bootstrap PR is **docs-only**. It does not add any workflow
with write permissions. If a workflow is added in this PR, it
must be `contents: read` only and must not call the Issues API.
