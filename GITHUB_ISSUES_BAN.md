# GITHUB_ISSUES_BAN.md

> Binding. See `AGENTS.md §3`.

GitHub Issues are **not used** in this repository.

## What is forbidden

- Opening a new issue.
- Commenting on any issue.
- Reacting to any issue.
- Triaging, labeling, or closing any issue.
- Using the Issues API for any purpose, including read-only listing,
  from any code path (scripts, workflows, bots, agents).

## What is allowed instead

- **Pull requests** — every actionable item is a PR or a draft PR.
- **`docs/` markdown** — design discussions, decision records, and
  research plans are written into `docs/` and reviewed in PRs.
- **PR descriptions** — long-form context goes into the PR body.
- **PR review comments** — line-level discussion goes into PR review
  comments.

## Why

- Pull requests carry diffs, commits, signatures, and a review trail.
- Issues are easy to leak, easy to spam, and easy to abuse for
  financial-advice claims.
- The project is a research and observation tool; it does not need a
  public issue tracker.

## Enforcement

- The repository's automation must not enable or call the Issues API.
- Any code or workflow that references `issues: write`, `issues: read`,
  or any issue-related endpoint is forbidden in this repo.
- If a forbidden surface is discovered, follow
  `GITHUB_AUTOMATION_INCIDENT_RESPONSE.md`.
