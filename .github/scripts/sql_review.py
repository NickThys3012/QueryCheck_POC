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