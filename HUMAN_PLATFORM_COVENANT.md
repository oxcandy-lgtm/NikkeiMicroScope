# HUMAN_PLATFORM_COVENANT.md

> Binding. See `AGENTS.md §6`.

This covenant is between the human operator(s) of this repository
and the platform (GitHub) and the agents (human and autonomous) that
work in it. It states the working agreement in plain language.

## Operator Commitments

- The operator will not bypass the rules in `AGENTS.md §3`
  (no Issues, no PAT, no secrets, no live trading, no advice).
- The operator will not push directly to `main` (see
  `GITHUB_PR_MERGE_POLICY.md`).
- The operator will read every implementation report attached
  to a PR before approving it.
- The operator will keep branch protection settings on `main`
  in effect (see `GITHUB_BRANCH_PROTECTION.md`).
- The operator will not generate, store, or accept a Personal
  Access Token for this repository.

## Agent Commitments (Human and Autonomous)

- Agents will treat `AGENTS.md` and the `GITHUB_*.md` files as
  binding. Lower-priority instructions cannot override them.
- Agents will not introduce forbidden surfaces, even when asked
  to "just this once" (see `AGENTS.md §6`).
- Agents will not optimize for "ship it now" over "ship it
  honestly". Conservative scope wins.
- Agents will produce implementation reports for non-trivial
  changes, with the section list in `AGENTS.md §5`.
- Agents will mark uncertainty explicitly in the
  "blockers / unknowns" section rather than guessing.

## Platform (GitHub) Use

- We use GitHub for what it is good at: source hosting, PR
  review, branch protection, signed commits, and read-only
  automation.
- We do not use GitHub Issues. See `GITHUB_ISSUES_BAN.md`.
- We do not use GitHub Actions to write to the repository from
  automation. See `GITHUB_ACTIONS_SAFETY.md`.
- We do not store secrets in GitHub. See `GITHUB_TOKEN_POLICY.md`.

## What This Covenant Forbids in Plain Language

- "Just push it to main, it's a small fix." — Forbidden.
- "Use my PAT for now, we'll rotate later." — Forbidden.
- "Open an issue to track this." — Forbidden.
- "Add a workflow that auto-merges dependabot." — Forbidden in
  MVP. If and when added, must respect
  `GITHUB_ACTIONS_SAFETY.md` and `GITHUB_PR_MERGE_POLICY.md`.
- "Skip the implementation report, it's obvious." — Forbidden
  for non-trivial changes.
- "Wire up the broker SDK, it's just paper trading." — Forbidden
  until the operator charter in `AGENTS.md §4` exists.

## What This Covenant Allows in Plain Language

- Draft PRs, multiple iterations, and patience.
- Docs-only PRs that have no code change.
- "I don't know" as a valid answer in an implementation report.
- Backing out a change that turns out to be wider than intended.

## Conflict Resolution

If two commitments in this covenant conflict, the more
conservative reading wins. If the conflict cannot be resolved by
reading, the operator decides, and the decision is recorded in a
PR that updates the relevant policy file.
