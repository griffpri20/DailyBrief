import os
import re
import time
import datetime
import xml.etree.ElementTree as ET
import requests
from dateutil import parser

# Google Auth/API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# --- 0. Environment Setup ---

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Fixed reference date: the week containing today = Week 1.
MOBILITY_WEEK1_START = datetime.date(2026, 2, 24)


def load_env():
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value


load_env()

CONFIG = {
    "LAT": 41.8781,
    "LON": -87.6298,
    "CITY": os.getenv("CITY_NAME", "Chicago, IL"),
    "TODOIST_TOKEN": os.getenv("TODOIST_API_TOKEN"),
    "OWM_KEY": os.getenv("OPENWEATHER_API_KEY"),
    "GCAL_CREDS": os.getenv("GCAL_CREDENTIALS_JSON", os.path.join(SCRIPT_DIR, "credentials.json")),
}

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Calendar names to skip (case-insensitive).
CALENDAR_EXCLUDE = {
    "egp/flp",
    "birthdays",
    "holidays in united states",
}


# --- 1. Data Retrieval ---

def get_google_service(name, version, token_file):
    token_path = os.path.join(SCRIPT_DIR, token_file)
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as refresh_err:
                print(f"Token refresh failed ({refresh_err}), re-authenticating...")
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(CONFIG["GCAL_CREDS"], SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
    return build(name, version, credentials=creds)


def get_weather():
    try:
        base = f"?lat={CONFIG['LAT']}&lon={CONFIG['LON']}&appid={CONFIG['OWM_KEY']}&units=imperial"
        current = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather{base}", timeout=10
        ).json()
        forecast = requests.get(
            f"https://api.openweathermap.org/data/2.5/forecast{base}", timeout=10
        ).json()
        today_str = datetime.date.today().isoformat()
        today_temps = [
            entry["main"]
            for entry in forecast.get("list", [])
            if entry.get("dt_txt", "").startswith(today_str)
        ]
        high = round(max(e["temp_max"] for e in today_temps)) if today_temps else "N/A"
        low  = round(min(e["temp_min"] for e in today_temps)) if today_temps else "N/A"
        return {
            "temp":  round(current["main"]["temp"]),
            "feels": round(current["main"]["feels_like"]),
            "desc":  current["weather"][0]["description"].capitalize(),
            "high":  high,
            "low":   low,
            "wind":  current["wind"]["speed"],
        }
    except Exception:
        return {"temp": "N/A", "feels": "N/A", "desc": "Weather Error", "high": "N/A", "low": "N/A", "wind": 0}


def weather_action(w):
    """Returns a concise, action-oriented weather line."""
    temp  = w.get("temp", "N/A")
    feels = w.get("feels", "N/A")
    desc  = w.get("desc", "").lower()
    wind  = w.get("wind", 0)
    high  = w.get("high", "N/A")
    low   = w.get("low", "N/A")

    actions = []
    if isinstance(feels, (int, float)):
        if feels <= 15:
            actions.append("dangerously cold — minimize outdoor exposure")
        elif feels <= 32:
            actions.append("freezing — heavy coat, gloves, hat")
        elif feels <= 45:
            actions.append("cold — coat required")
        elif feels >= 95:
            actions.append("extreme heat — hydrate, avoid midday sun")
        elif feels >= 85:
            actions.append("hot — light layers, stay hydrated")

    if any(x in desc for x in ("rain", "drizzle", "shower")):
        actions.append("bring an umbrella")
    elif any(x in desc for x in ("snow", "sleet", "blizzard", "ice")):
        actions.append("allow extra travel time")
    elif any(x in desc for x in ("thunder", "storm")):
        actions.append("check radar before heading out")

    if isinstance(wind, (int, float)) and wind > 20:
        actions.append(f"gusty at {round(wind)} mph")

    base = f"{temp}°F (feels {feels}°) · ↑{high}° ↓{low}° · {w.get('desc', '')}"
    if actions:
        return base + " → " + "; ".join(actions)
    return base


# --- Mobility Routine Data ---
# 3-day rotation. Left knee has documented lateral patellar tilt + trochlear cartilage loss (2019 MRI).
# Constraints: no open-chain knee exercises; Cossack squats capped ~60 deg knee flexion.
# Left big toe (hallux rigidus) exercises appear every day — Days A/C as final item, Day B as primary focus.

ROUTINE_DATA = {
    "A": {
        "title": "QL Chain Reset",
        "focus": "Right QL inhibition · core stabilization · right glute med activation",
        "exercises": [
            ("Contralateral breathing",
             "Left side down, breathe into right ribcage. 5 slow breaths. ~1.5 min."),
            ("90/90 hip switch + right lateral reach",
             "5 switches/side, pause at end range. ~1.5 min."),
            ("Dead bug",
             "5 reps/side, lower back pressed flat throughout. ~2 min."),
            ("Side-lying clam — right leg working",
             "Left side down, lead with heel, 15 reps. ~1 min."),
            ("[Daily] Left big toe passive extensions",
             "Grip at base of toe (proximal phalanx), traction + extension. 10 holds x 3s. ~1.5 min."),
        ],
    },
    "B": {
        "title": "Hallux + Ankle + Patellofemoral",
        "focus": "Left first MTP mobilization · ankle dorsiflexion · left patella tracking",
        "exercises": [
            ("Left first MTP joint distraction",
             "Grip proximal phalanx, traction + extension. 10 reps x 5s. ~2 min."),
            ("Short foot drill — both feet",
             "Pull ball of foot toward heel, no toe curl. 10 reps x 5s each. ~1 min."),
            ("Left lateral patella mobilization",
             "Fingertips lateral to kneecap, glide medially. 10 reps x 5s. ~1 min."),
            ("Terminal knee extension — closed chain",
             "Band behind knee, pump to full extension from 30 deg. 15 reps/side. ~1.5 min."),
            ("Single-leg balance — eyes closed",
             "30s each leg. Folded towel if available. ~1.5 min."),
        ],
    },
    "C": {
        "title": "Posterior Chain + Splits Prep",
        "focus": "Hamstrings · adductors · straddle · butterfly · split progression",
        "exercises": [
            ("Jefferson curl",
             "Roll down vertebra by vertebra, chin tucked. Light weight optional. 5 reps x 5s descent. ~1 min."),
            ("Straddle PAILs/RAILs",
             "60s passive settle → 20s press legs into floor (PAIL) → 20s try to lift legs (RAIL). ~3 min."),
            ("Cossack squat — hip-dominant",
             "Max 60 deg knee flex. Emphasis on adductor/hip stretch. 3 reps/side x 5s hold. ~1.5 min."),
            ("Butterfly PNF",
             "20s passive → 8s press knees into hands → 15s relax deeper. Posterior pelvic tilt throughout. ~2 min."),
            ("[Daily] Left big toe passive extensions",
             "Grip at base of toe (proximal phalanx), traction + extension. 10 holds x 3s. ~1.5 min."),
        ],
    },
}


def get_mobility_routine():
    today = datetime.date.today()
    days_since_start = (today - MOBILITY_WEEK1_START).days
    day_key = ["A", "B", "C"][days_since_start % 3]
    week_num = days_since_start // 7

    progression_notes = [
        "Week 1: Follow as written. Moderate effort — notice asymmetries.",
        "Week 2: +1 dead bug rep/side. Slightly deeper PAILs/RAILs positions.",
        "Week 3: +2s on all isometric holds. +5 reps TKE. Widen straddle 2-3 cm.",
        "Week 4+: All holds 8-10s. Smooth neuromuscular control is the goal, not depth.",
    ]
    prog_note = progression_notes[min(week_num, 3)]

    data = ROUTINE_DATA[day_key]
    return day_key, data["title"], data["focus"], data["exercises"], prog_note


def get_todoist():
    token = CONFIG["TODOIST_TOKEN"]
    if not token:
        print("Todoist error: TODOIST_API_TOKEN not set")
        return [{"content": "⚠️ TODOIST_API_TOKEN secret is not configured", "priority": 4, "url": "", "due_date": None}]
    try:
        resp = None
        for attempt in range(1, 4):
            try:
                resp = requests.get(
                    "https://api.todoist.com/api/v1/tasks",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"filter": "today | overdue"},
                    timeout=20,
                )
            except requests.exceptions.Timeout:
                print(f"Todoist timeout on attempt {attempt}")
                if attempt < 3:
                    time.sleep(2 ** attempt)
                continue
            print(f"Todoist API status: {resp.status_code} (attempt {attempt})")
            if resp.status_code < 500:
                break
            if attempt < 3:
                time.sleep(2 ** attempt)
        if resp is None:
            raise Exception("All 3 Todoist attempts timed out")
        if not resp.ok:
            print(f"Todoist API error body: {resp.text[:300]}")
            resp.raise_for_status()
        raw = resp.json()
        task_list = raw.get("results", raw) if isinstance(raw, dict) else raw
        print(f"Todoist: {len(task_list)} raw task(s)")
        today = datetime.date.today()
        tasks = []
        for t in task_list:
            due = t.get("due") or {}
            due_date_str = due.get("date") if isinstance(due, dict) else None
            if not due_date_str:
                continue
            try:
                if datetime.date.fromisoformat(due_date_str[:10]) > today:
                    continue
            except (ValueError, TypeError):
                continue
            tasks.append({
                "content": t.get("content", ""),
                "priority": t.get("priority", 1),
                "url": t.get("url", ""),
                "due_date": due_date_str[:10],
            })
        tasks.sort(key=lambda x: x["priority"], reverse=True)
        print(f"Todoist: {len(tasks)} task(s) due today/overdue")
        return tasks
    except Exception as e:
        print(f"Todoist error: {e}")
        return [{"content": f"⚠️ Todoist fetch failed: {e}", "priority": 4, "url": "", "due_date": None}]


def create_todoist_mobility_tasks(day_key, title, exercises):
    """Creates a Todoist parent task + one subtask per exercise for today's mobility routine."""
    token = CONFIG["TODOIST_TOKEN"]
    if not token:
        print("Todoist mobility tasks: no token, skipping.")
        return
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Find or create a "Mobility" project
    try:
        resp = requests.get("https://api.todoist.com/api/v1/projects", headers=headers, timeout=10)
        resp.raise_for_status()
        projects = resp.json()
        project_list = projects.get("results", projects) if isinstance(projects, dict) else projects
        mobility_project_id = next(
            (p["id"] for p in project_list if p.get("name", "").lower() == "mobility"), None
        )
        if not mobility_project_id:
            r = requests.post(
                "https://api.todoist.com/api/v1/projects",
                headers=headers, json={"name": "Mobility"}, timeout=10,
            )
            r.raise_for_status()
            mobility_project_id = r.json()["id"]
    except Exception as e:
        print(f"Todoist mobility: project lookup failed — {e}")
        return

    # Skip if today's task already exists
    today_label = datetime.date.today().strftime("%b %-d")
    parent_content = f"Morning Mobility — Day {day_key}: {title} ({today_label})"
    try:
        existing = requests.get(
            "https://api.todoist.com/api/v1/tasks",
            headers=headers, params={"project_id": mobility_project_id}, timeout=10,
        ).json()
        task_list = existing.get("results", existing) if isinstance(existing, dict) else existing
        if any(parent_content in t.get("content", "") for t in task_list):
            print("Mobility checklist already exists for today — skipping.")
            return
    except Exception as e:
        print(f"Todoist mobility: duplicate check failed — {e}")

    # Create parent task
    try:
        r = requests.post(
            "https://api.todoist.com/api/v1/tasks",
            headers=headers,
            json={"content": parent_content, "project_id": mobility_project_id,
                  "due_string": "today", "priority": 2},
            timeout=10,
        )
        r.raise_for_status()
        parent_id = r.json()["id"]
    except Exception as e:
        print(f"Todoist mobility: parent task creation failed — {e}")
        return

    # Subtasks
    for name, desc in exercises:
        try:
            requests.post(
                "https://api.todoist.com/api/v1/tasks",
                headers=headers,
                json={"content": f"{name} — {desc}", "project_id": mobility_project_id,
                      "parent_id": parent_id},
                timeout=10,
            ).raise_for_status()
        except Exception as e:
            print(f"Todoist mobility: subtask '{name}' failed — {e}")

    print(f"Mobility checklist created: {parent_content} ({len(exercises)} items).")


# --- 2. Task Prioritization (deterministic) ---

# Keywords that signal a task is a quick action (short, synchronous, low-friction)
QUICK_WIN_KEYWORDS = {
    "reply", "send", "call", "check", "update", "schedule", "confirm", "book",
    "email", "ping", "message", "skim", "read", "log", "submit", "approve",
    "follow", "upload", "share", "post", "notify", "remind", "forward", "respond",
}

# Keywords that signal a task requires focused cognitive effort
DEEP_WORK_KEYWORDS = {
    "research", "write", "build", "design", "analyze", "review", "prepare",
    "develop", "draft", "plan", "create", "architect", "investigate", "strategy",
    "model", "implement", "code", "ship", "launch", "outline", "structure",
    "evaluate", "assess", "synthesize", "propose",
}


def prioritize_tasks(tasks):
    """
    Buckets tasks using deterministic heuristics. No LLM.

    Rules:
      - Carryover: due_date < today (overdue)
      - Top 3: highest-priority tasks due today, capped at 3
      - Quick Wins: content <= 50 chars OR hits a quick-action keyword (not also a deep-work keyword)
      - Deep Work: content > 60 chars OR hits a deep-work keyword
      - Anything uncategorized falls into Deep Work

    Returns dict: {top3, quick_wins, deep_work, carryover}
    """
    today_str = datetime.date.today().isoformat()

    carryover = []
    actionable = []
    for t in tasks:
        due = t.get("due_date", "")
        if due and due < today_str:
            carryover.append(t)
        else:
            actionable.append(t)

    # Sort descending by Todoist priority (4=urgent, 1=normal)
    actionable.sort(key=lambda t: t["priority"], reverse=True)
    top3 = actionable[:3]
    rest = actionable[3:]

    quick_wins, deep_work = [], []
    for t in rest:
        words = set(t["content"].lower().split())
        is_quick = len(t["content"]) <= 50 or bool(words & QUICK_WIN_KEYWORDS)
        is_deep  = len(t["content"]) >  60 or bool(words & DEEP_WORK_KEYWORDS)
        if is_quick and not is_deep:
            quick_wins.append(t)
        else:
            deep_work.append(t)

    return {"top3": top3, "quick_wins": quick_wins, "deep_work": deep_work, "carryover": carryover}


# --- 3. Daily Focus Inference (deterministic) ---

def _event_local_dt(e):
    """Returns a naive local datetime for an event's start, or None."""
    start = e.get("start", {})
    raw = start.get("dateTime", "")
    if not raw:
        return None
    try:
        return parser.parse(raw).replace(tzinfo=None)
    except Exception:
        return None


def _event_date(e):
    """Returns the local date of an event's start, or None."""
    start = e.get("start", {})
    raw = start.get("dateTime", start.get("date", ""))
    try:
        return parser.parse(raw).date()
    except Exception:
        return None


def infer_daily_focus(buckets, calendar_events):
    """
    Returns a single directive sentence for the day.

    Heuristic priority (first match wins):
      1. ≥4 overdue → clear the backlog
      2. ≥5 meetings today → protect execution gaps
      3. ≥3 morning meetings AND free afternoon → front-loaded; use PM for focus
      4. ≥3 afternoon meetings AND free morning → use AM for deep work
      5. ≥2 overdue → address carryover first
      6. Monday → planning/alignment frame
      7. Friday → close/ship/reflect frame
      8. ≥2 top-3 tasks → execution day
      9. Default → light/strategic day
    """
    today = datetime.date.today()
    dow = today.weekday()  # 0=Mon … 6=Sun

    overdue_count = len(buckets["carryover"])
    top3_count    = len(buckets["top3"])

    morning_meetings   = 0
    afternoon_meetings = 0
    for e in calendar_events:
        dt = _event_local_dt(e)
        if dt is None or dt.date() != today:
            continue
        if dt.hour < 12:
            morning_meetings += 1
        elif dt.hour < 17:
            afternoon_meetings += 1

    total_meetings = morning_meetings + afternoon_meetings

    if overdue_count >= 4:
        return (
            f"Backlog heavy — {overdue_count} overdue items. "
            "Work through the oldest before taking on anything new."
        )
    if total_meetings >= 5:
        return "Back-to-back meeting day — protect every open block for decisions and execution."
    if morning_meetings >= 3 and afternoon_meetings == 0:
        return "Meetings front-loaded — keep your afternoon clear and go heads-down after lunch."
    if afternoon_meetings >= 3 and morning_meetings == 0:
        return "Morning is open — use it for deep work before meetings take over."
    if overdue_count >= 2:
        return f"{overdue_count} tasks carried over — address these before starting anything new."
    if dow == 0:
        return "Monday: anchor the week — validate your top 3 and surface any blockers early."
    if dow == 4:
        return "Friday: ship what's shippable, close open loops, and set up a clean Monday."
    if top3_count >= 2:
        return f"Clear execution day — drive your top {top3_count} priorities to done."
    return "Light day — use the space for deep work or strategic thinking you've been deferring."


# --- 4. Calendar (filtered) ---

def get_calendar():
    """
    Fetches today + tomorrow's events. Drops anything that ended >15 min ago.
    """
    try:
        service = get_google_service("calendar", "v3", "token_calendar.json")

        now_local       = datetime.datetime.now()
        start_of_today  = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_window   = start_of_today + datetime.timedelta(days=2)

        utc_offset = datetime.datetime.utcnow() - now_local
        start_utc  = (start_of_today + utc_offset).isoformat() + "Z"
        end_utc    = (end_of_window  + utc_offset).isoformat() + "Z"

        cal_list   = service.calendarList().list().execute()
        all_events = []

        for cal in cal_list.get("items", []):
            cal_name = cal.get("summary", "")
            if cal_name.lower() in CALENDAR_EXCLUDE:
                print(f"  Skipping excluded calendar: {cal_name}")
                continue
            try:
                result = service.events().list(
                    calendarId=cal["id"],
                    timeMin=start_utc,
                    timeMax=end_utc,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                for e in result.get("items", []):
                    e["_calendar_name"] = cal_name
                all_events.extend(result.get("items", []))
            except Exception:
                continue

        # Drop events that ended more than 15 minutes ago
        cutoff = now_local - datetime.timedelta(minutes=15)
        live_events = []
        for e in all_events:
            end_raw = e.get("end", {}).get("dateTime", "")
            if end_raw:
                try:
                    end_dt = parser.parse(end_raw).replace(tzinfo=None)
                    if end_dt < cutoff:
                        continue
                except Exception:
                    pass
            live_events.append(e)

        live_events.sort(
            key=lambda e: e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
        )
        return live_events
    except Exception as e:
        print(f"Calendar error: {e}")
        return []


# --- 5. News (relevance-ranked) ---

# Feeds grouped by primary topic. Items are re-scored across all topics after fetch.
RSS_FEEDS = [
    ("AI & Tech",          "https://feeds.feedburner.com/venturebeat/SZYF"),
    ("AI & Tech",          "https://www.technologyreview.com/feed/"),
    ("Product & Startups", "https://www.theverge.com/rss/index.xml"),
    ("Macro & Markets",    "https://feeds.npr.org/1001/rss.xml"),
    ("Macro & Markets",    "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("Strategy",           "https://feeds.hbr.org/harvardbusiness"),
]

# Keyword sets for topic scoring. Phrase matching on lowercased headline + summary.
TOPIC_KEYWORDS = {
    "AI & Tech": {
        "ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai",
        "anthropic", "model", "automation", "robot", "neural", "nvidia", "microsoft",
        "google", "agent", "compute", "deepmind", "gemini", "claude", "chatgpt",
    },
    "Product & Startups": {
        "product", "startup", "launch", "saas", "platform", "app", "feature",
        "funding", "seed", "series a", "venture", "y combinator", "yc",
        "product-market fit", "roadmap",
    },
    "Strategy & Macro": {
        "strategy", "economy", "inflation", "federal reserve", "interest rate",
        "gdp", "recession", "market", "stock", "nasdaq", "unemployment", "tariff",
        "acquisition", "merger", "ipo", "valuation", "earnings", "growth",
    },
    "Recruiting & Talent": {
        "hiring", "talent", "recruiting", "workforce", "layoff", "headcount",
        "remote", "culture", "compensation", "hr", "employees", "attrition",
    },
}

# Display order in the briefing
TOPIC_ORDER = ["AI & Tech", "Strategy & Macro", "Product & Startups", "Recruiting & Talent"]


def _score_item(headline, summary=""):
    """Returns {topic: hit_count} for all topics with ≥1 keyword match."""
    text = (headline + " " + summary).lower()
    return {
        topic: sum(1 for kw in kws if kw in text)
        for topic, kws in TOPIC_KEYWORDS.items()
        if any(kw in text for kw in kws)
    }


def _fetch_rss(url, max_items=8):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "DailyBriefing/1.0"})
        r.raise_for_status()
        root  = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            desc_el  = item.find("description")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link  = link_el.text.strip()  if link_el  is not None and link_el.text  else "#"
            desc  = re.sub(r"<[^>]+>", "", desc_el.text or "")[:160] if desc_el is not None else ""
            if title:
                items.append({"headline": title, "summary": desc, "url": link})
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"RSS fetch error ({url}): {e}")
        return []


def get_news():
    """
    Fetches all feeds, scores each headline against topic keyword sets,
    assigns each item to its highest-scoring topic, deduplicates, and
    returns the top 3 items per topic in TOPIC_ORDER.
    """
    topic_buckets  = {topic: [] for topic in TOPIC_KEYWORDS}
    seen_headlines = set()

    for _label, url in RSS_FEEDS:
        for item in _fetch_rss(url):
            headline = item["headline"]
            if headline in seen_headlines:
                continue
            seen_headlines.add(headline)

            scores = _score_item(headline, item.get("summary", ""))
            if scores:
                best_topic = max(scores, key=scores.get)
                topic_buckets[best_topic].append((scores[best_topic], item))

    ranked = {}
    for topic in TOPIC_ORDER:
        bucket = sorted(topic_buckets.get(topic, []), key=lambda x: x[0], reverse=True)
        top_items = [item for _score, item in bucket[:3]]
        if top_items:
            ranked[topic] = top_items

    return ranked


def _format_event_time(e):
    start = e.get("start", {})
    raw   = start.get("dateTime", start.get("date", ""))
    try:
        dt = parser.parse(raw)
        return dt.strftime("%-I:%M %p") if "T" in raw else "All day"
    except Exception:
        return raw


def _wx_icon(desc):
    d = desc.lower()
    if any(x in d for x in ("rain", "drizzle", "shower")):
        return "🌧️"
    if any(x in d for x in ("snow", "sleet")):
        return "❄️"
    if "thunder" in d or "storm" in d:
        return "⛈️"
    if "cloud" in d:
        return "☁️"
    if "clear" in d or "sun" in d:
        return "☀️"
    return "🌤️"


# --- 7. Notion ---

NOTION_PAGE_ID = "32d4f6d1d79381e9bbe3e872cf32ae71"


def _notion_headers():
    return {
        "Authorization": f"Bearer {os.getenv('NOTION_TOKEN')}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _clear_notion_page(page_id, headers):
    resp = requests.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=headers, timeout=10,
    )
    for block in resp.json().get("results", []):
        requests.delete(
            f"https://api.notion.com/v1/blocks/{block['id']}",
            headers=headers, timeout=10,
        )


def _txt(content, bold=False, color="default", url=None):
    text = {"type": "text", "text": {"content": content}}
    if url:
        text["text"]["link"] = {"url": url}
    if bold or color != "default":
        text["annotations"] = {}
        if bold:
            text["annotations"]["bold"] = True
        if color != "default":
            text["annotations"]["color"] = color
    return text


def build_notion_blocks(data):
    w        = data["weather"]
    buckets  = data["task_buckets"]
    focus    = data["daily_focus"]
    events   = data["calendar"]
    news     = data["news"]
    day_key, mob_title, mob_focus, mob_exercises, mob_prog = data["mobility"]

    today     = datetime.date.today()
    today_str = today.isoformat()
    blocks    = []

    # Header
    blocks.append({"object": "block", "type": "heading_1", "heading_1": {
        "rich_text": [_txt(f"Good morning, Griff ☀️  —  {datetime.datetime.now().strftime('%A, %B %d')}")]
    }})
    wx_note = f" · 💨 {round(w['wind'])} mph" if isinstance(w["wind"], (int, float)) and w["wind"] > 20 else ""
    blocks.append({"object": "block", "type": "callout", "callout": {
        "rich_text": [_txt(weather_action(w) + wx_note)],
        "icon": {"type": "emoji", "emoji": _wx_icon(w.get("desc", ""))},
    }})

    # Daily Focus
    blocks.append({"object": "block", "type": "callout", "callout": {
        "rich_text": [_txt("TODAY'S FOCUS  ", bold=True), _txt(focus)],
        "icon": {"type": "emoji", "emoji": "🎯"},
        "color": "yellow_background",
    }})

    # Top 3
    blocks.append({"object": "block", "type": "heading_2", "heading_2": {
        "rich_text": [_txt("🎯  Top 3 Today")]
    }})
    for t in buckets["top3"]:
        overdue = t.get("due_date") and t["due_date"] < today_str
        label   = ("(URGENT) " if t["priority"] == 4 else "") + t["content"] + (" ⚠️ overdue" if overdue else "")
        blocks.append({"object": "block", "type": "to_do", "to_do": {
            "rich_text": [_txt(label, color="red" if overdue else "default")],
            "checked": False,
        }})

    # Calendar
    blocks.append({"object": "block", "type": "heading_2", "heading_2": {
        "rich_text": [_txt("📅  Schedule")]
    }})
    today_events = [e for e in events if _event_date(e) == today]
    if today_events:
        for e in today_events:
            time_str = _format_event_time(e)
            cal_note = f"  [{e.get('_calendar_name','')}]" if e.get("_calendar_name") else ""
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {
                "rich_text": [
                    _txt(time_str, color="gray"),
                    _txt(f"  {e.get('summary','Untitled')}", bold=True),
                    _txt(cal_note, color="gray"),
                ]
            }})
    else:
        blocks.append({"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [_txt("No events today.", color="gray")]
        }})

    # Quick Wins
    if buckets["quick_wins"]:
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {
            "rich_text": [_txt("⚡  Quick Wins")]
        }})
        for t in buckets["quick_wins"]:
            blocks.append({"object": "block", "type": "to_do", "to_do": {
                "rich_text": [_txt(t["content"])], "checked": False,
            }})

    # Deep Work
    if buckets["deep_work"]:
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {
            "rich_text": [_txt("🔭  Deep Work")]
        }})
        for t in buckets["deep_work"]:
            blocks.append({"object": "block", "type": "to_do", "to_do": {
                "rich_text": [_txt(t["content"])], "checked": False,
            }})

    # Carryover
    if buckets["carryover"]:
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {
            "rich_text": [_txt("⚠️  Carryover", color="red")]
        }})
        for t in buckets["carryover"]:
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {
                "rich_text": [_txt(t["content"] + f" (due {t['due_date']})", color="red")]
            }})

    # News Signal
    blocks.append({"object": "block", "type": "heading_2", "heading_2": {
        "rich_text": [_txt("📰  Signal")]
    }})
    for topic, items in news.items():
        blocks.append({"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [_txt(topic, bold=True)]
        }})
        for item in items:
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {
                "rich_text": [_txt(item["headline"], url=item.get("url") or None)]
            }})

    # Mobility
    blocks.append({"object": "block", "type": "heading_2", "heading_2": {
        "rich_text": [_txt("🌅  Morning Mobility")]
    }})
    mob_toggle_children = [
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [_txt(f"Focus: {mob_focus}", color="gray")]
        }},
    ]
    for ex_name, ex_desc in mob_exercises:
        mob_toggle_children.append({"object": "block", "type": "to_do", "to_do": {
            "rich_text": [_txt(ex_name, bold=True), _txt(f" — {ex_desc}")],
            "checked": False,
        }})
    mob_toggle_children.append({"object": "block", "type": "paragraph", "paragraph": {
        "rich_text": [_txt(mob_prog, color="gray")]
    }})
    blocks.append({"object": "block", "type": "toggle", "toggle": {
        "rich_text": [_txt(f"Day {day_key} · {mob_title}  (~7 min)", bold=True)],
        "children": mob_toggle_children,
    }})

    # Footer
    blocks.append({"object": "block", "type": "paragraph", "paragraph": {
        "rich_text": [_txt(f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", color="gray")]
    }})

    return blocks


def write_to_notion(data):
    token = os.getenv("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN not set. Skipping Notion write.")
        return
    headers = _notion_headers()
    print("Clearing Notion page...")
    _clear_notion_page(NOTION_PAGE_ID, headers)

    blocks = build_notion_blocks(data)
    for i in range(0, len(blocks), 100):
        resp = requests.patch(
            f"https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children",
            headers=headers,
            json={"children": blocks[i:i + 100]},
            timeout=15,
        )
        if not resp.ok:
            print(f"Notion API error: {resp.text[:300]}")
            return

    requests.patch(
        f"https://api.notion.com/v1/pages/{NOTION_PAGE_ID}",
        headers=headers,
        json={"properties": {"title": {"title": [{"text": {"content":
            f"☀️ Daily Briefing — {datetime.datetime.now().strftime('%B %d, %Y')}"
        }}]}}},
        timeout=10,
    )
    print(f"Briefing written to Notion: https://www.notion.so/{NOTION_PAGE_ID}")


# --- 9. Main ---

if __name__ == "__main__":
    print("Fetching data...")
    raw_tasks    = get_todoist()
    calendar     = get_calendar()
    buckets      = prioritize_tasks(raw_tasks)
    focus        = infer_daily_focus(buckets, calendar)
    mobility     = get_mobility_routine()
    day_key, mob_title, _focus, mob_exercises, _prog = mobility
    create_todoist_mobility_tasks(day_key, mob_title, mob_exercises)

    payload = {
        "weather":      get_weather(),
        "mobility":     mobility,
        "todoist":      raw_tasks,
        "task_buckets": buckets,
        "daily_focus":  focus,
        "calendar":     calendar,
        "news":         get_news(),
    }

    print(f"Daily focus: {focus}")
    print(f"Tasks — Top 3: {len(buckets['top3'])} | Quick wins: {len(buckets['quick_wins'])} | "
          f"Deep work: {len(buckets['deep_work'])} | Carryover: {len(buckets['carryover'])}")

    print("Writing to Notion...")
    write_to_notion(payload)
