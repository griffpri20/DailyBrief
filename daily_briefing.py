import os
import re
import smtplib
import datetime
import xml.etree.ElementTree as ET
import requests
from email.mime.text import MIMEText
from dateutil import parser

# Google Auth/API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# --- 0. Environment Setup ---

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Fixed reference date: the week containing today = Week 1.
# Adjust this date to whatever Monday you want "Week 1" to begin.
MOBILITY_WEEK1_START = datetime.date(2026, 2, 24)  # Today = Week 1, Day 1


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
    "EMAIL": "griffp97@gmail.com",
    "LAT": 41.8781,
    "LON": -87.6298,
    "CITY": os.getenv("CITY_NAME", "Chicago, IL"),
    "TODOIST_TOKEN": os.getenv("TODOIST_API_TOKEN"),
    "OWM_KEY": os.getenv("OPENWEATHER_API_KEY"),
    "GMAIL_CREDS": os.getenv("GMAIL_CREDENTIALS_JSON", os.path.join(SCRIPT_DIR, "credentials.json")),
    "GMAIL_APP_PWD": os.getenv("GMAIL_APP_PASSWORD"),
}

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Calendar names to skip in the briefing (case-insensitive).
# Add any calendar name here that you don't want to see.
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
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CONFIG["GMAIL_CREDS"], SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
    return build(name, version, credentials=creds)


def get_weather():
    try:
        base = f"?lat={CONFIG['LAT']}&lon={CONFIG['LON']}&appid={CONFIG['OWM_KEY']}&units=imperial"

        # Current conditions
        current = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather{base}", timeout=10
        ).json()

        # 5-day / 3-hour forecast — filter to today's date to get high/low
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


def get_mobility_routine():
    today = datetime.date.today()
    days_since_start = (today - MOBILITY_WEEK1_START).days
    week_num = days_since_start // 7  # 0-indexed

    # Alternate A/B by day parity from the start date
    routine_a = (
        "<b>ROUTINE A &mdash; Hip Flexor Strength + Thoracic Mobility</b><br>"
        "1. Seated Hip Flexor Lift-Off: 3 reps/side, 5s hold.<br>"
        "2. Half-Kneeling Hip Flexor PNF: 20s stretch, 8s drive, 15s relax.<br>"
        "3. T-Spine: Weighted extension (6 reps) OR Quadruped rotations (6/side)."
    )

    routine_b = (
        "<b>ROUTINE B &mdash; Hip ER/IR Strength + Adductor Mobility</b><br>"
        "1. 90/90 Lift-Offs: 3 reps/side, 5s hold.<br>"
        "2. Cossack Squat Eccentrics: 2 reps/side (5s lower).<br>"
        "3. Frog Stretch: 20s hold, 8s drive, 15s relax."
    )

    progression = [
        "Week 1: Follow as written. Moderate effort.",
        "Week 2: Add 1 extra lift-off rep per side. Slightly deeper stretch positions.",
        "Week 3: Add small load to lift-offs. Add 1 extra Cossack rep per side.",
        "Week 4+: Increase isometric holds to 8-10 seconds. Focus on smooth control.",
    ]

    active_routine = routine_a if days_since_start % 2 == 0 else routine_b
    prog_note = progression[min(week_num, 3)]
    return active_routine, prog_note


def _normalize_task(t):
    if isinstance(t, dict):
        due = t.get("due") or {}
        return {
            "content": t.get("content", ""),
            "priority": t.get("priority", 1),
            "url": t.get("url", ""),
            "due_date": due.get("date") if isinstance(due, dict) else None,
        }
    due = getattr(t, "due", None)
    return {
        "content": getattr(t, "content", str(t)),
        "priority": getattr(t, "priority", 1),
        "url": getattr(t, "url", ""),
        "due_date": due.date if due else None,
    }


def get_todoist():
    token = CONFIG["TODOIST_TOKEN"]
    if not token:
        print("Todoist error: TODOIST_API_TOKEN not set")
        return [{"content": "⚠️ TODOIST_API_TOKEN secret is not configured", "priority": 4, "url": "", "due_date": None}]
    try:
        resp = requests.get(
            "https://api.todoist.com/rest/v2/tasks",
            headers={"Authorization": f"Bearer {token}"},
            params={"filter": "today | overdue"},
            timeout=10,
        )
        print(f"Todoist API status: {resp.status_code}")
        if not resp.ok:
            print(f"Todoist API error body: {resp.text[:300]}")
            resp.raise_for_status()
        raw = resp.json()
        print(f"Todoist: raw response has {len(raw)} task(s)")
        tasks = []
        for t in raw:
            due = t.get("due") or {}
            tasks.append({
                "content": t.get("content", ""),
                "priority": t.get("priority", 1),
                "url": t.get("url", ""),
                "due_date": due.get("date") if isinstance(due, dict) else None,
            })
        # Sort by priority descending (4=urgent … 1=normal in Todoist)
        tasks.sort(key=lambda x: x["priority"], reverse=True)
        print(f"Todoist: returning {len(tasks)} task(s) due today/overdue")
        return tasks
    except Exception as e:
        print(f"Todoist error: {e}")
        return [{"content": f"⚠️ Todoist fetch failed: {e}", "priority": 4, "url": "", "due_date": None}]


def get_calendar():
    """
    Fetches events across all non-excluded calendars for today + next 2 days.
    Window is always anchored to midnight of the current day so a 6am run
    still captures events that started earlier in the morning.

    NOTE: The Google Calendar API must be enabled in your Google Cloud Console project.
    If you see a 403 error, visit:
      https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview
    and enable it for your project, then re-run.

    To exclude a calendar, add its name (lowercase) to CALENDAR_EXCLUDE above.
    """
    try:
        service = get_google_service("calendar", "v3", "token_calendar.json")

        # Anchor to midnight of the current local day so we never miss morning events.
        now_local = datetime.datetime.now()
        start_of_today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_of_today_local + datetime.timedelta(days=3)  # today + 2 full days

        # Convert to UTC for the API
        utc_offset = datetime.datetime.utcnow() - now_local
        start_utc = (start_of_today_local + utc_offset).isoformat() + "Z"
        end_utc = (end_local + utc_offset).isoformat() + "Z"

        # Gather all calendars
        cal_list = service.calendarList().list().execute()
        all_events = []

        for cal in cal_list.get("items", []):
            cal_name = cal.get("summary", "")
            if cal_name.lower() in CALENDAR_EXCLUDE:
                print(f"  Skipping excluded calendar: {cal_name}")
                continue
            cal_id = cal["id"]
            try:
                result = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=start_utc,
                        timeMax=end_utc,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )
                for e in result.get("items", []):
                    e["_calendar_name"] = cal.get("summary", "")
                all_events.extend(result.get("items", []))
            except Exception:
                continue

        # Sort by start time
        def event_sort_key(e):
            start = e.get("start", {})
            return start.get("dateTime", start.get("date", ""))

        all_events.sort(key=event_sort_key)
        return all_events
    except Exception as e:
        print(f"Calendar error: {e}")
        return []


# --- News via RSS (no API key required) ---

RSS_FEEDS = [
    # (category_label, feed_url)
    ("🌍 World",    "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("🇺🇸 US",      "https://feeds.npr.org/1001/rss.xml"),        # NPR US News
    ("🏆 Sports",   "https://feeds.bbci.co.uk/sport/rss.xml"),
    ("🤖 AI / Tech","https://feeds.feedburner.com/venturebeat/SZYF"),
]


def _fetch_rss(url, max_items=3):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "DailyBriefing/1.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else "#"
            desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            desc = re.sub(r"<[^>]+>", "", desc)[:160]
            if title:
                items.append({"headline": title, "summary": desc, "url": link})
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"RSS fetch error ({url}): {e}")
        return []


def get_news():
    results = {}
    for label, url in RSS_FEEDS:
        items = _fetch_rss(url, max_items=3)
        if items:
            results[label] = items
    return results


# --- 2. Build HTML ---

def build_html(data):
    w = data["weather"]
    routine, prog = data["mobility"]

    def news_section(news):
        if not news:
            return "<p>News unavailable.</p>"
        sections = []
        for label, items in news.items():
            links = "".join(
                f"<li style='margin-bottom:6px;'>"
                f"<a href='{i.get('url', '#')}' style='color:#2563eb; text-decoration:none;'>{i.get('headline', '')}</a>"
                f"</li>"
                for i in items
            )
            sections.append(
                f"<p style='margin-bottom:4px;'><b>{label}</b></p>"
                f"<ul style='margin-top:0; padding-left:18px;'>{links}</ul>"
            )
        return "\n".join(sections)

    def todoist_section(tasks):
        if not tasks:
            return "<p>No tasks found.</p>"
        today_str = datetime.datetime.now().date().isoformat()
        items = ""
        for t in tasks:
            due = t.get("due_date", "")
            overdue = due and due < today_str
            color = "#dc2626" if overdue else "#374151"
            badge = " <span style='color:#dc2626; font-size:11px;'>(overdue)</span>" if overdue else ""
            items += (
                f"<li style='margin-bottom:8px; color:{color};'>"
                f"<b>{t['content']}</b>{badge} "
                f"<small>(<a href='{t['url']}' style='color:#2563eb;'>View</a>)</small></li>"
            )
        return f"<ul style='padding-left:20px;'>{items}</ul>"

    def calendar_section(events):
        if not events:
            return (
                "<p style='color:#666;'>No upcoming events found. "
                "<b>Note:</b> If you expected events here, make sure the Google Calendar API "
                "is enabled in your Google Cloud Console project.</p>"
            )
        items = ""
        for e in events:
            start = e.get("start", {})
            start_raw = start.get("dateTime", start.get("date", ""))
            # Format nicely
            try:
                dt = parser.parse(start_raw)
                start_fmt = dt.strftime("%-m/%-d %I:%M %p") if "T" in start_raw else dt.strftime("%-m/%-d (all day)")
            except Exception:
                start_fmt = start_raw
            cal_name = e.get("_calendar_name", "")
            cal_badge = f" <span style='color:#6b7280; font-size:11px;'>[{cal_name}]</span>" if cal_name else ""
            location = e.get("location", "")
            loc_str = f" &bull; {location}" if location else ""
            items += (
                f"<li style='margin-bottom:10px; padding:10px; background:#fafafa; border-radius:5px;'>"
                f"<b>{e.get('summary', 'Untitled')}</b>{cal_badge}<br>"
                f"<small style='color:#555;'>{start_fmt}{loc_str}</small></li>"
            )
        return f"<ul style='list-style:none; padding:0;'>{items}</ul>"

    wind_str = f" | &#x1F4A8; {w['wind']} mph" if isinstance(w['wind'], (int, float)) and w['wind'] > 15 else ""

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:'Segoe UI',Arial,sans-serif; background-color:#f4f7f6; margin:0; padding:20px;">
  <div style="max-width:680px; margin:auto; background:white; border-radius:15px; overflow:hidden; border:1px solid #ddd;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%); padding:35px; color:white;">
      <h1 style="margin:0; font-size:28px;">Good morning, Griff &#x1F31E;</h1>
      <p style="margin:5px 0 20px 0; opacity:0.85;">{datetime.datetime.now().strftime('%A, %B %d')}</p>
      <div style="background:rgba(255,255,255,0.15); padding:15px; border-radius:10px; display:inline-block; font-size:15px;">
        &#x1F4CD; {CONFIG['CITY']} &nbsp;|&nbsp;
        <b>{w['temp']}&deg;F</b> (Feels {w['feels']}&deg;) &nbsp;|&nbsp;
        &uarr;{w['high']}&deg; / &darr;{w['low']}&deg; &nbsp;|&nbsp;
        {w['desc']}{wind_str}
      </div>
    </div>

    <div style="padding:25px;">

      <!-- Tasks -->
      <h3 style="border-bottom:2px solid #f0f0f0; padding-bottom:10px;">&#x2705; Today's Tasks</h3>
      {todoist_section(data['todoist'])}

      <!-- Calendar -->
      <h3 style="border-bottom:2px solid #f0f0f0; padding-bottom:10px;">&#x1F4C5; Calendar</h3>
      {calendar_section(data['calendar'])}

      <!-- Inbox -->
      <h3 style="border-bottom:2px solid #f0f0f0; padding-bottom:10px;">&#x1F4EC; Inbox</h3>
      <p style="margin:0;">
        <a href="https://gemini.google.com/app/8185d8045c3a9424"
           style="display:inline-block; padding:10px 22px; background:#2563eb; color:white;
                  border-radius:8px; text-decoration:none; font-weight:bold; font-size:14px;">
          Review Emails with Gemini &rarr;
        </a>
      </p>

      <!-- News -->
      <h3 style="border-bottom:2px solid #f0f0f0; padding-bottom:10px;">&#x1F4F0; News Highlights</h3>
      {news_section(data['news'])}

      <!-- Mobility (at bottom as a reference/reminder) -->
      <h3 style="border-bottom:2px solid #f0f0f0; padding-bottom:10px;">&#x1F3CB; Mobility Routine</h3>
      <div style="background:#eff6ff; border-left:5px solid #2563eb; padding:20px; border-radius:5px;">
        <p style="margin-top:0; color:#1e3a5f; font-weight:bold;">{prog}</p>
        <div style="line-height:1.6;">{routine}</div>
      </div>

    </div>

    <!-- Footer -->
    <div style="background:#f8fafc; padding:20px; text-align:center; font-size:12px; color:#94a3b8; border-top:1px solid #eee;">
      Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>

  </div>
</body>
</html>"""
    return html


# --- 3. Send Email ---

def send_email(html_content):
    if not CONFIG["GMAIL_APP_PWD"]:
        preview_path = os.path.join(SCRIPT_DIR, "daily_briefing_preview.html")
        with open(preview_path, "w") as f:
            f.write(html_content)
        print(f"No App Password found. Preview saved to {preview_path}")
        return

    msg = MIMEText(html_content, "html")
    msg["Subject"] = f"Daily Briefing - {datetime.datetime.now().strftime('%b %d')}"
    msg["From"] = CONFIG["EMAIL"]
    msg["To"] = CONFIG["EMAIL"]

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(CONFIG["EMAIL"], CONFIG["GMAIL_APP_PWD"])
        server.send_message(msg)
    print("Briefing sent successfully.")


# --- 4. Main ---

if __name__ == "__main__":
    print("Fetching data...")
    payload = {
        "weather": get_weather(),
        "mobility": get_mobility_routine(),
        "todoist": get_todoist(),
        "calendar": get_calendar(),
        "news": get_news(),
    }
    print("Building and sending email...")
    send_email(build_html(payload))
