# GITHUB_STEWARDSHIP.md

> Binding. Lower-priority instructions (chat, scripts, LLM completions)
> cannot override this document. If in conflict, this document wins.

This file collects the GitHub-side stewardship rules for
NikkeiMicroScope. Each rule is also restated in a dedicated document
listed below. The dedicated documents are authoritative for their
respective scope; this index file exists for orientation.

## Index

- `GITHUB_ISSUES_BAN.md` — Issues are banned. Use PRs and `docs/`.
- `GITHUB_TOKEN_POLICY.md` — No PAT. No secrets. Use GitHub App / `gh`.
- `GITHUB_ACTIONS_SAFETY.md` — Workflow permissions, forbidden triggers.
- `GITHUB_PR_MERGE_POLICY.md` — No direct-to-`main`. Draft -> review ->
  merge.
- `GITHUB_BRANCH_PROTECTION.md` — Branch protection expectations.
- `GITHUB_COMPLIANCE_REFERENCE.md` — Cross-reference to project rules.
- `GITHUB_AUTOMATION_INCIDENT_RESPONSE.md` — What to do if a forbidden
  surface is breached by automation.
- `HUMAN_PLATFORM_COVENANT.md` — Human / platform covenant.

## Top-Level Rules (Summary)

1. **No GitHub Issues.** Ever. See `GITHUB_ISSUES_BAN.md`.
2. **No Personal Access Tokens.** See `GITHUB_TOKEN_POLICY.md`.
3. **No secrets in repo.** No `.env`, no API keys, no broker creds.
4. **No direct push to `main`.** `main` is updated only by merge of an
   approved, non-draft PR.
5. **No live trading or broker integration** in this repo without the
   operator charter described in `AGENTS.md §4`.
6. **No financial advice or profit guarantees.**
7. **Workflows must be read-only** unless explicitly justified in the
   PR that introduces them. No `pull_request_target`, no `issues: write`
   on `main` / bootstrap, no PAT references.

## Conflict Resolution

If a future PR proposes to relax any of the above rules, that PR must:

- Update this document and the relevant dedicated file in the same PR.
- Be a non-bootstrap PR.
- Reference an explicit operator instruction.

Silent relaxation is forbidden.
