# Copilot Instructions

## Purpose

This repository is a proof-of-concept for automating T-SQL correction script review using the GitHub Copilot coding agent. The goal is to replace a manual, Jira-based review loop with a GitHub Issue workflow where a custom Copilot agent reformats and analyses SQL scripts automatically.

The full design is documented in `workflow-analysis.md`.

## Planned repository structure

```
.github/
  agents/
    sql-reviewer.agent.md       ← custom agent: reformat + analyse SQL, post as issue comment
  ISSUE_TEMPLATE/
    sql-review.yml              ← structured form for devs to submit SQL for review
  workflows/
    close-approved.yml          ← auto-close issue when "approved" label is applied
  copilot-setup-steps.yml       ← agent environment setup
workflow-analysis.md            ← design document for this workflow
```

## Key conventions

- **Agent file, not skill file.** The review logic lives in `.github/agents/sql-reviewer.agent.md` (a custom cloud agent), not a skill file. The agent is selectable from the Copilot dropdown when assigning an issue — no label routing required.
- **Everything stays in the issue.** The agent posts its output (reformatted SQL + analysis) as a comment on the GitHub Issue. It does **not** create a branch or open a PR.
- **The SQL repo is separate.** The actual T-SQL correction scripts and their `review-sql` / `create-script` skill files live in the `WiV/SQL` repository. This repo only contains the workflow automation layer that triggers and routes to that skill.
- **Approval via label.** The reviewer closes the loop by applying an `approved` label (or posting an approval comment). The `close-approved.yml` workflow reacts to the label to auto-close the issue.
- **Issue template drives assignment.** The `sql-review.yml` template auto-assigns `@github-copilot` so the dev only needs to fill in the form — no manual agent selection needed (though they can override the agent via the dropdown).
