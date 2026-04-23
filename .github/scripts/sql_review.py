import os
import re
import json
import urllib.request
from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────
GITHUB_TOKEN  = os.environ["GITHUB_TOKEN"]
ISSUE_BODY    = os.environ["ISSUE_BODY"]
ISSUE_NUMBER  = int(os.environ["ISSUE_NUMBER"])
REPO          = os.environ["REPO"]
COMMENT_BODY  = os.environ.get("COMMENT_BODY", "")
TRIGGER       = os.environ.get("TRIGGER", "issues")

client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN,
)

# ── Parse helpers ──────────────────────────────────────────────────────────────
def extract_section(body: str, heading: str) -> str:
    pattern = rf"### {re.escape(heading)}\s*\n+(.*?)(?=\n###|\Z)"
    match = re.search(pattern, body, re.DOTALL)
    return match.group(1).strip() if match else ""

def extract_sql_from_fences(text: str) -> str:
    match = re.search(r"```sql\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return re.sub(r"^```\w*\s*|^```\s*", "", text, flags=re.MULTILINE).strip()

# ── Determine source of SQL ────────────────────────────────────────────────────
if TRIGGER == "issue_comment":
    print("Trigger: re-review comment")
    ticket      = extract_section(ISSUE_BODY, "Jira ticket")
    description = extract_section(ISSUE_BODY, "What does this script do?")
    comment_content = re.sub(r"^/re-review\s*", "", COMMENT_BODY, flags=re.IGNORECASE).strip()
    sql         = extract_sql_from_fences(comment_content)
    review_note = "> ♻️ **Re-review** of updated SQL from comment\n\n"
else:
    print("Trigger: issue opened")
    ticket      = extract_section(ISSUE_BODY, "Jira ticket")
    description = extract_section(ISSUE_BODY, "What does this script do?")
    sql_block   = extract_section(ISSUE_BODY, "SQL script")
    sql         = extract_sql_from_fences(sql_block)
    review_note = ""

print(f"Ticket: {ticket}")
print(f"SQL length: {len(sql)} chars")

if not sql:
    print("No SQL found — aborting.")
    exit(1)

# ── Load system prompt from skill file ─────────────────────────────────────────
with open(".github/skills/review-sql/SKILL.md", encoding="utf-8") as f:
    skill_content = f.read()

SYSTEM_PROMPT = f"""{skill_content}

You are reviewing a T-SQL correction script submitted via a GitHub Issue.
Output ONLY the two sections below — no preamble, no explanation outside them.

### ✅ Reformatted SQL
```sql
<reformatted script>
```

### 📋 Analysis
<full analysis following the structure in the skill file above>
""".strip()

USER_PROMPT = f"""Ticket: {ticket}
Description: {description}

SQL:
```sql
{sql}
```""".strip()

# ── Call GitHub Models API ─────────────────────────────────────────────────────
print("Calling GitHub Models API...")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": USER_PROMPT},
    ],
    temperature=0,
)

comment_body = review_note + response.choices[0].message.content.strip()
print("Got response, posting comment...")

# ── Post comment on issue ──────────────────────────────────────────────────────
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
print(f"✅ Posted review comment on issue #{ISSUE_NUMBER}")
