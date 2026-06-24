# GITHUB_AUTOMATION_INCIDENT_RESPONSE.md

> Binding. What to do when automation (a workflow, a bot, a script,
> or an agent) breaches a forbidden surface in this repository.

## Trigger Conditions

This runbook applies when any of the following is detected:

- A secret, PAT, API key, or credential is committed or appears in
  a workflow run log.
- The GitHub Issues API is called by any code path in this repo.
- A push to `main` happens outside of a merged PR.
- A workflow uses `pull_request_target`, `issues: write`, or
  `contents: write` without an explicit PR justification.
- A broker / order API is referenced from any code path.
- An `.env` file, `secrets/` directory, or equivalent appears in
  the repository.

## Immediate Actions

1. **Stop the bleeding.**
   - If the breach is a secret: rotate the secret at the upstream
     provider **first**, before any cleanup commit. See
     `GITHUB_TOKEN_POLICY.md` "If a Secret Lands in the Repo".
   - If the breach is a workflow auto-applying state: disable the
     workflow in the GitHub UI and revoke any tokens it had access
     to.
2. **Preserve evidence.**
   - Capture the offending commit SHA, the workflow run URL, and a
     copy of the workflow run logs (locally; do not paste full logs
     into a public channel).
3. **Do not push a "fixup" commit to `main`.** A force-push is the
   acceptable remediation for a leaked secret, but only after
   rotation and only on the affected branch — never on `main`.
4. **Open a post-mortem PR** referencing this document. The PR must:
   - Describe the trigger, the impact, the rotation, and the
     remediation commit.
   - Update any policy file that the breach revealed as weak.
   - Be a **non-draft** PR and require a human approval.

## Communications

- Do not post a public incident notice in this repo. The repo
  does not use Issues, and a public notice in `docs/` is not
  appropriate until the post-mortem PR is merged.
- If the breach is severe enough to warrant a wider notice, do
  it in a controlled channel **outside** this repo.

## After-Action Review

- Within 7 days of merge of the post-mortem PR, the operator must
  either tighten the relevant policy or record an explicit
  decision not to, with rationale.
- The implementation report from the post-mortem PR must include
  a "candidate next actions" section with at least one
  `exact_fix_only` action.

## What This Document is Not

- This is not a substitute for a real incident response process.
  For a small research project, this document is sufficient. For
  anything larger, escalate.
