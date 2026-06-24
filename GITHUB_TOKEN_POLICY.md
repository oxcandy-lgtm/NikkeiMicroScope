# GITHUB_TOKEN_POLICY.md

> Binding. See `AGENTS.md §3`.

## Scope

This document governs authentication for the GitHub side of the
repository (push, PR, workflow, API). It does not govern the
content of the repository, which is also covered by
`GITHUB_ISSUES_BAN.md` and `docs/risk-policy.md`.

## Rules

1. **No Personal Access Tokens (PAT).**
   - No PAT-based authentication for git push / fetch.
   - No PAT in code, scripts, workflows, docs, or commits.
   - No PAT in issue templates, PR templates, or any markdown file.
   - The token used by the operator's local environment is the
     `gh` CLI token, managed by GitHub, never written into this
     repository.
2. **No secrets in the repository.**
   - No `.env`, no `.env.example`, no `secrets/`, no `credentials/`.
   - No API keys, no broker credentials, no private keys, no
     service account tokens, no OAuth client secrets.
   - No SSH private keys, no GPG private keys, no signing keys.
3. **No secrets in workflows.**
   - Workflows that need a secret must not be added to this
     repository in MVP. Workflows must be read-only.
4. **No secrets in commit messages.**
   - No tokens, no API keys, no URLs containing tokens in commit
     messages or PR descriptions.
5. **No third-party secret scanners that exfiltrate.**
   - If a secret scanner is added, it must run on PRs only, must
     not phone home with the secret contents, and must be documented
     in the PR that adds it.

## Operator Authentication

- The operator authenticates to GitHub using the `gh` CLI, signed
  in via the local keyring.
- Workflow authentication, when used, is the GitHub-provided
  `GITHUB_TOKEN` secret with **read-only** scopes.
- No long-lived PAT is generated for this repository.

## If a Secret Lands in the Repo

1. **Do not push a follow-up "remove the secret" commit.** That
   still leaves the secret in history.
2. Rotate the secret at the upstream provider immediately.
3. Purge from history with a tool such as `git filter-repo`, and
   force-push the affected branch (force-push is otherwise
   forbidden — this is the one exception, and it must be followed
   by a PR noting the rotation and purge).
4. Open a post-mortem PR referencing
   `GITHUB_AUTOMATION_INCIDENT_RESPONSE.md`.
