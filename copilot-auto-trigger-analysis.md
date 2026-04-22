# Fully Automatic Copilot Agent Trigger — Analysis

## The problem with the current setup

The issue template sets `assignees: ["copilot"]`, but **assigning Copilot via the template does not automatically start the agent**. It only puts Copilot in the assignee field. The dev still has to open the issue, click the assignee, and confirm — and the custom agent dropdown (to select `sql-reviewer`) requires an extra manual step on top of that.

---

## Solution: GitHub Actions calls the GraphQL API to assign + start the agent

GitHub provides a GraphQL API (`replaceActorsForAssignable`) that can:
- Assign Copilot to an issue programmatically
- Specify the `sql-reviewer` **custom agent**
- Pass `customInstructions` if needed
- All in a single API call, triggered automatically when the issue opens

This means: **the dev opens the issue — Copilot starts automatically with the right agent, zero clicks.**

---

## How it works

```
Dev opens issue using the sql-review template
    → GitHub Actions workflow triggers (issues: opened, label: sql-review)
    → Workflow calls GraphQL API:
         - assigns copilot-swe-agent to the issue
         - sets customAgent: "sql-reviewer"
    → Copilot coding agent starts automatically
    → Agent uses sql-reviewer.agent.md + skill file rules
    → Posts reformatted SQL + analysis as issue comment
    → Reviewer reads comment, applies "approved" label
```

---

## Required setup

### 1. PAT with `repo` scope (or fine-grained PAT)

The `GITHUB_TOKEN` available in Actions **cannot** assign Copilot via the GraphQL API — GitHub requires a **user token** (not an installation token) to trigger the coding agent. This is a platform restriction.

You need to:
1. Create a **fine-grained PAT** (Settings → Developer settings → Fine-grained tokens) with:
   - **Read and write** access to: Actions, Contents, Issues, Pull Requests
   - **Read** access to: Metadata
2. Store it as a repo secret: `COPILOT_PAT`

### 2. Find the Copilot bot ID and repo ID (one-time setup)

The workflow needs the GraphQL IDs of the Copilot bot and the repo. Run these once and store the results:

```bash
# Get the Copilot bot ID
gh api graphql -f query='
query {
  repository(owner: "NickThys3012", name: "QueryCheck_POC") {
    suggestedActors(capabilities: [CAN_BE_ASSIGNED], first: 10) {
      nodes { login ... on Bot { id } }
    }
  }
}' -H 'GraphQL-Features: issues_copilot_assignment_api_support'

# Get the repo ID
gh api graphql -f query='
query {
  repository(owner: "NickThys3012", name: "QueryCheck_POC") { id }
}'
```

Store both IDs as repo secrets:
- `COPILOT_BOT_ID` — the `id` of the `copilot-swe-agent` node
- `REPO_GRAPHQL_ID` — the `id` of the repository

### 3. Workflow file

Replace the current `sql-review.yml` workflow (or add alongside it) with this:

```yaml
name: SQL Auto-Assign to Copilot

on:
  issues:
    types: [opened]

jobs:
  assign:
    if: contains(github.event.issue.labels.*.name, 'sql-review')
    runs-on: ubuntu-latest

    steps:
      - name: Get issue GraphQL ID
        id: issue
        env:
          GH_TOKEN: ${{ secrets.COPILOT_PAT }}
        run: |
          ISSUE_ID=$(gh api graphql -f query='
            query($owner: String!, $repo: String!, $number: Int!) {
              repository(owner: $owner, name: $repo) {
                issue(number: $number) { id }
              }
            }' \
            -f owner="${{ github.repository_owner }}" \
            -f repo="${{ github.event.repository.name }}" \
            -F number=${{ github.event.issue.number }} \
            --jq '.data.repository.issue.id')
          echo "id=$ISSUE_ID" >> $GITHUB_OUTPUT

      - name: Assign Copilot with sql-reviewer agent
        env:
          GH_TOKEN: ${{ secrets.COPILOT_PAT }}
        run: |
          gh api graphql \
            -H 'GraphQL-Features: issues_copilot_assignment_api_support,coding_agent_model_selection' \
            -f query='
            mutation($issueId: ID!, $botId: ID!, $repoId: ID!) {
              replaceActorsForAssignable(input: {
                assignableId: $issueId,
                actorIds: [$botId],
                agentAssignment: {
                  targetRepositoryId: $repoId,
                  customAgent: "sql-reviewer"
                }
              }) {
                assignable {
                  ... on Issue { id title }
                }
              }
            }' \
            -f issueId="${{ steps.issue.outputs.id }}" \
            -f botId="${{ secrets.COPILOT_BOT_ID }}" \
            -f repoId="${{ secrets.REPO_GRAPHQL_ID }}"
```

### 4. Remove the manual assignee from the issue template

Since the workflow now handles assignment, remove `assignees: ["copilot"]` from the template — it's no longer needed and may cause a conflict.

---

## Comparison to current GitHub Actions + Models API approach

| | GitHub Actions + Models API (current) | GitHub Actions + Copilot Agent (this) |
|--|--|--|
| Manual steps | 0 | 0 |
| Uses Copilot AI | ❌ (separate Models API call) | ✅ actual Copilot agent |
| Uses sql-reviewer agent | ❌ (prompt only) | ✅ full agent file + skill |
| Requires extra secret | ❌ (GITHUB_TOKEN) | ✅ (PAT with repo scope) |
| Output location | Issue comment | Issue comment |
| Can do re-review | ✅ via /re-review comment | ⚠️ would need re-assignment |

---

## Recommendation

Use this approach **alongside** the current one during a transition period:

1. **Short term**: current GitHub Actions + Models API works today with zero extra secrets
2. **Switch to this** once the GraphQL API graduates from public preview — it uses the actual Copilot agent with the full skill file, giving better and more consistent results

The one hard requirement is the PAT. If creating a PAT is acceptable, this is the cleaner long-term solution.
