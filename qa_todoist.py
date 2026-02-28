"""
QA script — verifies the Todoist REST API v2 is returning tasks.

Run:
    python3 qa_todoist.py

Requires TODOIST_API_TOKEN to be set in the environment or in a .env file.
"""
import os
import sys
import json
import datetime
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env():
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key, value)
        print("Loaded .env file.")


load_env()

token = os.getenv("TODOIST_API_TOKEN")
if not token:
    print("FAIL: TODOIST_API_TOKEN is not set.")
    print("  → Set it in your shell:  export TODOIST_API_TOKEN=your_token_here")
    print("  → Or add it to a .env file in this directory.")
    sys.exit(1)

print(f"Token found (length={len(token)}, starts={token[:6]}...)")
print()

# ── Test 1: basic connectivity ────────────────────────────────────────────────
print("=== Test 1: GET /rest/v2/tasks?filter=today|overdue ===")
resp = requests.get(
    "https://api.todoist.com/api/v1/tasks",
    headers={"Authorization": f"Bearer {token}"},
    params={"filter": "today | overdue"},
    timeout=10,
)
print(f"HTTP status : {resp.status_code}")

if not resp.ok:
    print(f"FAIL: API returned {resp.status_code}")
    print(f"Body: {resp.text[:500]}")
    sys.exit(1)

tasks = resp.json()
print(f"Tasks found : {len(tasks)}")

today_str = datetime.date.today().isoformat()
print(f"Today       : {today_str}")
print()

if not tasks:
    print("WARNING: 0 tasks returned — verify you have tasks due today or overdue in Todoist.")
else:
    print(f"{'#':<3} {'Priority':<10} {'Due Date':<12} {'Content'}")
    print("-" * 70)
    for i, t in enumerate(tasks, 1):
        due = (t.get("due") or {}).get("date", "no date")
        overdue_flag = " ← OVERDUE" if due and due < today_str else ""
        print(f"{i:<3} p{t.get('priority', 1):<9} {due:<12} {t.get('content', '')[:40]}{overdue_flag}")

# ── Test 2: confirm token owner ───────────────────────────────────────────────
print()
print("=== Test 2: GET /rest/v2/projects (auth sanity check) ===")
resp2 = requests.get(
    "https://api.todoist.com/api/v1/projects",
    headers={"Authorization": f"Bearer {token}"},
    timeout=10,
)
print(f"HTTP status : {resp2.status_code}")
if resp2.ok:
    projects = resp2.json()
    print(f"Projects    : {len(projects)}")
    for p in projects[:5]:
        print(f"  - {p.get('name', 'unknown')}")
else:
    print(f"FAIL: {resp2.status_code} {resp2.text[:200]}")

print()
print("=== QA COMPLETE ===")
if tasks:
    print(f"PASS: {len(tasks)} task(s) returned for today/overdue.")
else:
    print("WARNING: 0 tasks found. Check Todoist for tasks due today.")
