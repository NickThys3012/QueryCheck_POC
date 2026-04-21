# SQL Query Review Workflow

## 1. Current State

```
Dev writes SQL
    → pastes SQL file into Jira ticket
    → reviewer (support dev) downloads it
    → manually invokes review-sql skill in Copilot
    → Copilot reformats + writes analysis .md
    → reviewer pastes reformatted SQL back into Jira
    → reviewer pastes SQL file again into Ops ticket
```

**Pain points:**
- Skill invocation is manual (reviewer's burden)
- SQL is copied between Jira ↔ editor ↔ Ops ticket — drift risk
- No single canonical "approved" version of the script
- Ops always rely on a paste, not a source-controlled file

---

## 2. Proposed Workflow

```
Dev writes SQL
    → opens GitHub Issue using the sql-review template
    → pastes SQL in the issue body (fenced code block)
    → assigns @github-copilot and selects the "sql-reviewer" custom agent
    → Copilot coding agent picks it up and posts a comment containing:
         1. Reformatted SQL (fenced code block, ready to copy)
         2. Full analysis (risks, risk summary table)
    → reviewer reads the issue comment — no manual Copilot invocation
    → reviewer adds approval comment / applies "approved" label
    → Ops gets a link to the issue — reformatted SQL is in the agent comment
```

**Result:**
- Zero manual Copilot invocations for the reviewer
- Everything lives in one GitHub issue — no separate PR to manage
- Ops get the issue link; the approved script is in the agent's comment (no pasting)
- Full audit trail: who opened the issue, agent output, who approved

---

## 3. Required Setup

### 3.1 Repository

The existing `SQL` repo (already containing `.github/skills/` and `.github/copilot-instructions.md`) is the right place. No new repo needed.

### 3.2 Enable Copilot Coding Agent

In the repo settings on GitHub:
- **Settings → Copilot → Coding agent** → enable for the repo / org
- The agent only needs permission to **read issues and post comments** — no branch/PR permissions required for this workflow

### 3.3 Issue template

Create `.github/ISSUE_TEMPLATE/sql-review.yml` so the dev gets a structured form:

```yaml
name: SQL Review Request
description: Submit a T-SQL correction script for review
title: "CIRHD-XXXXX: <short description>"
labels: ["sql-review"]
assignees: ["github-copilot"]
body:
  - type: input
    id: ticket
    attributes:
      label: Jira ticket
      placeholder: CIRHD-12345
    validations:
      required: true

  - type: textarea
    id: description
    attributes:
      label: What does this script do?
      description: Plain-language summary (becomes the script header comment)
    validations:
      required: true

  - type: textarea
    id: sql
    attributes:
      label: SQL script
      description: Paste the full script here
      render: sql
    validations:
      required: true

  - type: dropdown
    id: steps
    attributes:
      label: Single-step or multi-step?
      options:
        - Single-step
        - Multi-step
    validations:
      required: true
```

> **Why not attach a file?**
> GitHub Issues only allow image attachments natively. `.sql` files must be pasted as code blocks
> (the `render: sql` field above) or renamed to `.txt`. Pasting in the issue body is the
> lowest-friction option and keeps the SQL readable inline.

### 3.4 Custom agent file

Instead of routing via labels + `copilot-instructions.md`, create a **custom agent file** at `.github/agents/sql-reviewer.agent.md`. This gives the review logic its own named agent that the dev can explicitly select when assigning Copilot to the issue — no label routing needed.

```markdown
---
name: sql-reviewer
description: Reviews and reformats T-SQL correction scripts for the CIR housing registration system. Posts reformatted SQL and risk analysis as a comment on the issue.
tools: ["read", "search"]
---

When assigned to a GitHub issue:

1. Read the ticket number and SQL script from the issue body.
2. Apply the review-sql skill:
   - Reformat the SQL using the formatting rules in .github/skills/review-sql/SKILL.md
   - Produce the full analysis (what the script does, risks by severity, risk summary table)
3. Post a single comment on the issue with this structure:

   ### ✅ Reformatted SQL
   (reformatted script in a sql fenced block)

   ### 📋 Analysis
   (full analysis following the review-sql analysis structure)

Do **not** create a branch or open a pull request.
```

When a dev assigns Copilot to the issue on GitHub.com, a **dropdown lets them pick "sql-reviewer"** instead of the default cloud agent — so it truly feels like assigning to a specific agent.

### 3.5 Copilot setup steps (optional but recommended)

Create `.github/copilot-setup-steps.yml` to pre-install any tools the agent might need in its environment:

```yaml
steps:
  - name: No special tools needed for SQL-only review
    run: echo "ready"
```

If you later add automated linting (e.g. `sqlfluff`), add the install step here.

---

## 4. Day-to-day workflow (after setup)

| Who | Action |
|-----|--------|
| **Dev** | Opens issue using the *SQL Review Request* template, fills in ticket number + SQL |
| **Agent** | Auto-assigned by template; reads the issue, reformats SQL, produces analysis, posts one comment |
| **Reviewer** | Opens the issue — reformatted SQL and full analysis are already in the agent comment |
| **Reviewer** | Adds approval comment (e.g. "✅ approved") or applies `approved` label, closes issue |
| **Ops** | Gets a link to the closed issue; copies the reformatted SQL from the agent comment |

---

## 5. What stays the same

- The `review-sql` skill file is unchanged — the custom agent reads it directly
- The `copilot-instructions.md` domain context is unchanged
- Jira is still the source for the ticket description; GitHub is now the source for the script

---

## 6. What changes for each role

| Role | Before | After |
|------|--------|-------|
| Dev | Pastes SQL in Jira comment | Opens GitHub issue with template |
| Reviewer | Manually invokes Copilot skill, pastes results back | Reads agent comment in the issue — done |
| Ops | Copies SQL from Jira/Slack | Copies SQL from the agent comment in the GitHub issue |

---

## 7. Optional enhancements (future)

### 7a. Approved label → auto-close issue

Add a GitHub Actions workflow that closes the issue and posts a final summary comment when the `approved` label is applied:

```yaml
# .github/workflows/close-approved.yml
name: Close approved SQL review
on:
  issues:
    types: [labeled]
jobs:
  close:
    if: github.event.label.name == 'approved'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: '✅ Script approved and ready for Ops.'
            });
            await github.rest.issues.update({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              state: 'closed'
            });
```

### 7b. Auto-post GitHub issue link back to Jira

Using the Jira GitHub integration (or a small Actions step with the Jira API), automatically add a comment to the Jira ticket with a link to the GitHub issue once it is opened.

### 7c. Ops notification on approval

When the `approved` label is applied, a GitHub Actions step posts the issue URL to a Slack/Teams channel that Ops monitors — removing the need for manual handoff entirely.

---

## 8. Files to create (summary)

| File | Purpose |
|------|---------|
| `.github/ISSUE_TEMPLATE/sql-review.yml` | Structured issue form for devs |
| `.github/agents/sql-reviewer.agent.md` | Custom agent — carries the review logic, selectable from the Copilot dropdown when assigning an issue |
| `.github/copilot-setup-steps.yml` | Agent environment setup (optional, add tools if needed) |
| `.github/workflows/close-approved.yml` | Auto-close issue on `approved` label (optional) |
