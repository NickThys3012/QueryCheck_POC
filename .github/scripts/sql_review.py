import os
import re
import json
import base64
import urllib.request
from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────
GITHUB_TOKEN  = os.environ["GITHUB_TOKEN"]
ISSUE_TITLE   = os.environ.get("ISSUE_TITLE", "")
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

def extract_ticket(raw_ticket: str, issue_title: str, sql: str) -> str:
    # Prefer a CIRHD ticket reference when available.
    for source in (raw_ticket, issue_title, sql):
        match = re.search(r"\bCIRHD-\d+\b", source or "", re.IGNORECASE)
        if match:
            return match.group(0).upper()
    fallback_ticket = raw_ticket.strip()
    if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?", fallback_ticket):
        return fallback_ticket
    raise ValueError("No valid ticket identifier found in issue or SQL content")

def safe_ticket_file_name(ticket: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", ticket):
        raise ValueError("Ticket contains invalid characters for a file name")
    if ".." in ticket:
        raise ValueError("Ticket cannot contain path traversal sequence")
    return ticket

def github_request(method: str, path: str, body: dict = None):
    owner, repo = REPO.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept":        "application/vnd.github+json",
            "Content-Type":  "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

# ── Determine source of SQL ────────────────────────────────────────────────────
if TRIGGER == "issue_comment":
    print("Trigger: re-review comment")
    raw_ticket  = extract_section(ISSUE_BODY, "Jira ticket")
    description = extract_section(ISSUE_BODY, "What does this script do?")
    comment_content = re.sub(r"^/re-review\s*", "", COMMENT_BODY, flags=re.IGNORECASE).strip()
    sql         = extract_sql_from_fences(comment_content)
    review_note = "> ♻️ **Re-review** of updated SQL from comment\n\n"
else:
    print("Trigger: issue opened")
    raw_ticket  = extract_section(ISSUE_BODY, "Jira ticket")
    description = extract_section(ISSUE_BODY, "What does this script do?")
    sql_block   = extract_section(ISSUE_BODY, "SQL script")
    sql         = extract_sql_from_fences(sql_block)
    review_note = ""

try:
    ticket = extract_ticket(raw_ticket, ISSUE_TITLE, sql)
    ticket_file_name = safe_ticket_file_name(ticket)
except ValueError as e:
    print(f"Ticket validation failed: {e}")
    exit(1)

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

ai_response  = response.choices[0].message.content.strip()
comment_body = review_note + ai_response
print("Got response.")

# ── Extract reformatted SQL from AI response and save to file ──────────────────
reformatted_sql = extract_sql_from_fences(
    re.split(r"### 📋 Analysis", ai_response)[0]  # only look in the SQL section
)

file_path = f"tickets/{ticket_file_name}.sql"
file_content_encoded = base64.b64encode(
    (reformatted_sql + "\n").encode("utf-8")
).decode("utf-8")

# Check if file already exists (needed for update — requires current SHA)
existing = github_request("GET", f"contents/{file_path}")
commit_message = (
    f"{'Update' if existing else 'Add'} {ticket}.sql (auto-reviewed from issue #{ISSUE_NUMBER})"
)

payload = {
    "message": commit_message,
    "content": file_content_encoded,
}
if existing:
    payload["sha"] = existing["sha"]  # required for updates

github_request("PUT", f"contents/{file_path}", payload)
print(f"✅ Saved reformatted SQL to {file_path}")

# ── Post comment on issue ──────────────────────────────────────────────────────
file_url = f"https://github.com/{REPO}/blob/main/{file_path}"
comment_body += f"\n\n---\n📁 Reformatted script saved to [`{file_path}`]({file_url})"

github_request(
    "POST",
    f"issues/{ISSUE_NUMBER}/comments",
    {"body": comment_body},
)
print(f"✅ Posted review comment on issue #{ISSUE_NUMBER}")
