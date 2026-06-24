# GITHUB_PR_MERGE_POLICY.md

> Binding. See `AGENTS.md §2`.

## Branch and PR Workflow

- All work happens on a feature / bootstrap branch off `main`.
- The base branch for PRs is `main`.
- `main` is updated **only** by merging an approved, non-draft
  pull request.
- Draft PRs are allowed during bootstrap and pre-merge review.
  They must be marked **Ready for review** before merge.
- Force-push is forbidden on shared branches, including during
  PR review.

## PR Author Requirements

Every non-trivial PR must include:

1. A clear title and description.
2. A reference to the issue tracker **policy** if relevant
   (we do not use Issues, so this is just a reference to
   `docs/`, never an issue number).
3. An implementation report per `AGENTS.md §5` (scope, files
   touched with `file:line`, validation, safety/privacy audit,
   non-claims, blockers/unknowns, candidate next actions).
4. Confirmation that the change does not introduce any
   forbidden surface (see `AGENTS.md §3`).

## Review Requirements

- At least one human approval is required before merge.
- The human approver must verify, at minimum:
  - No `.env`, no PAT, no secret of any kind.
  - No live trading / broker integration code.
  - No use of the GitHub Issues API.
  - No direct push to `main`.
- The human approver must run the validation commands listed in
  the implementation report and paste results into the PR
  conversation.

## Merge Mechanics

- Squash merge is the default. The squash commit message must
  start with a conventional prefix (`feat:`, `fix:`, `chore:`,
  `docs:`, `refactor:`, `test:`, `build:`, `ci:`).
- Merge commits are allowed only when the PR explicitly needs to
  preserve individual commits in history (rare; justify in the PR).
- Rebase merge is allowed.

## Direct Push to `main`

- **Forbidden.** Even for the operator, even for trivial fixes.
- The only exception is the initial bootstrap creation of the
  `main` branch from an empty commit, which is a one-time
  repository-initialization step. All subsequent `main` changes
  go through PRs.
- CI must reject any direct push to `main` (see
  `GITHUB_BRANCH_PROTECTION.md`).
