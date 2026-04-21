# Fully Automated SQL Review — Analysis

## Why the current setup isn't fully automatic

The Copilot coding agent can be auto-assigned via the issue template, but selecting *which* custom agent to use (e.g. `sql-reviewer`) is a UI-only dropdown on GitHub.com. There is no way to pre-set this in the template. One manual click is always required.

To eliminate that step entirely the automation must move out of the Copilot coding agent and into a **GitHub Actions workflow**.

---

## Proposed approach: GitHub Actions + GitHub Models API

A workflow triggers the instant a `sql-review` issue is opened. It parses the SQL out of the issue body, calls an AI model with the full review rules embedded as a system prompt, and posts the result as a comment. The dev opens the issue — the review appears automatically, with zero further interaction.

```
Dev opens issue using the sql-review template
    → GitHub Actions workflow triggers immediately (issues: opened)
    → Workflow parses SQL from issue body
    → Calls GitHub Models API (GPT-4o) with review-sql rules as system prompt
    → Posts formatted comment:
         ✅ Reformatted SQL
         📋 Analysis (risks, risk summary table)
    → Reviewer reads comment, adds "approved" label
    → close-approved.yml auto-closes issue
```

**Why GitHub Models API:**
- Uses the repo's `GITHUB_TOKEN` — no extra secrets or credentials needed
- Free within GitHub's included quota
- Available in any GitHub Actions runner out of the box

---

## Implementation

### File: `.github/workflows/sql-review.yml`

```yaml
name: SQL Auto-Review

on:
  issues:
    types: [opened]

jobs:
  review:
    if: contains(github.event.issue.labels.*.name, 'sql-review')
    runs-on: ubuntu-latest
    permissions:
      issues: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install openai

      - name: Run SQL review
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ISSUE_BODY: ${{ github.event.issue.body }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          REPO: ${{ github.repository }}
        run: python .github/scripts/sql_review.py
```

> **Why `issues: opened` and not `issues: labeled`?**
> The issue template applies the `sql-review` label at creation time, so `opened` fires with the label already present. Using `labeled` would also work but fires for every label added — `opened` is cleaner.

---

### File: `.github/scripts/sql_review.py`

This script is called by the workflow. It extracts the SQL from the issue body, builds the prompt from the skill file, calls the GitHub Models API, and posts the comment.

```python
import os
import re
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN  = os.environ["GITHUB_TOKEN"]
ISSUE_BODY    = os.environ["ISSUE_BODY"]
ISSUE_NUMBER  = int(os.environ["ISSUE_NUMBER"])
REPO          = os.environ["REPO"]          # "owner/repo"

# GitHub Models API endpoint — same token, no extra secrets
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN,
)

# ── Parse issue body ──────────────────────────────────────────────────────────
def extract_section(body: str, heading: str) -> str:
    """Extract the content under a ### heading from a GitHub issue form body."""
    pattern = rf"### {re.escape(heading)}\s*\n+(.*?)(?=\n###|\Z)"
    match = re.search(pattern, body, re.DOTALL)
    return match.group(1).strip() if match else ""

ticket      = extract_section(ISSUE_BODY, "Jira ticket")
description = extract_section(ISSUE_BODY, "What does this script do?")
sql_block   = extract_section(ISSUE_BODY, "SQL script")

# Strip markdown fences if present
sql = re.sub(r"^```sql\s*|^```\s*", "", sql_block, flags=re.MULTILINE).strip()

# ── Load system prompt from skill file ───────────────────────────────────────
with open(".github/skills/review-sql/SKILL.md", encoding="utf-8") as f:
    skill_content = f.read()

SYSTEM_PROMPT = f"""
{skill_content}

You are reviewing a T-SQL correction script submitted via a GitHub Issue.
Output ONLY the two sections below — no preamble, no explanation outside them.

### ✅ Reformatted SQL
```sql
<reformatted script>
```

### 📋 Analysis
<full analysis following the structure in the skill file above>
""".strip()

USER_PROMPT = f"""
Ticket: {ticket}
Description: {description}

SQL:
```sql
{sql}
```
""".strip()

# ── Call GitHub Models API ────────────────────────────────────────────────────
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": USER_PROMPT},
    ],
    temperature=0,
)

comment_body = response.choices[0].message.content.strip()

# ── Post comment on issue ─────────────────────────────────────────────────────
import urllib.request, json

owner, repo = REPO.split("/")
url  = f"https://api.github.com/repos/{owner}/{repo}/issues/{ISSUE_NUMBER}/comments"
data = json.dumps({"body": comment_body}).encode()
req  = urllib.request.Request(
    url,
    data=data,
    headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github+json",
        "Content-Type":  "application/json",
    },
)
urllib.request.urlopen(req)
print(f"Posted review comment on issue #{ISSUE_NUMBER}")
```

---

### Skill file dependency

The script loads `.github/skills/review-sql/SKILL.md` at runtime as the system prompt. This means:
- The skill file must be present in **this** repo (copy or symlink from the SQL repo), **or**
- The workflow does a sparse checkout of the SQL repo to pull the skill file in, **or**
- The system prompt is inlined directly into the Python script (simplest, but requires manual sync when the skill file changes)

**Recommended for the POC:** copy the `review-sql/SKILL.md` content into the script directly. Once the workflow is stable, replace it with a checkout of the SQL repo.

---

## Comparison to current approach

| | Copilot coding agent + custom agent | GitHub Actions + GitHub Models |
|--|------|------|
| Manual steps | 1 (select agent dropdown) | **0** |
| Uses skill file | ✅ directly | ✅ loaded as system prompt |
| Output location | Issue comment | Issue comment |
| Requires extra secrets | ❌ | ❌ (uses `GITHUB_TOKEN`) |
| Predictability | Variable (agent reasons freely) | High (deterministic prompt) |
| Setup effort | Low | Medium |

---

## Files to create

| File | Purpose |
|------|---------|
| `.github/workflows/sql-review.yml` | Triggers on issue open, calls the script |
| `.github/scripts/sql_review.py` | Parses issue, calls AI, posts comment |
| `.github/skills/review-sql/SKILL.md` | Copy of the review-sql skill (system prompt source) |
