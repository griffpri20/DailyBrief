# Daily Briefing — PythonAnywhere Deployment Guide

A daily HTML email sent every morning with weather, mobility routine, Todoist tasks,
Google Calendar events, important unread Gmail, top job listings, and Gemini-powered news.

---

## Prerequisites (do this on your local machine first)

### 1. Generate OAuth tokens locally

PythonAnywhere cannot open a browser for OAuth flows. You **must** generate the token files
on your personal machine before uploading.

Run the script once locally:

```bash
python3 daily_briefing.py
```

This will open browser windows asking you to authorize Gmail and Google Calendar access.
Two files will be created in the same directory:

- `token_gmail.json`
- `token_calendar.json`

**These tokens must be uploaded to PythonAnywhere along with the other files.**

---

## Files to Upload

Upload all of the following to PythonAnywhere (e.g., into `/home/<username>/daily_briefing/`):

| File | Description |
|---|---|
| `daily_briefing.py` | Main script |
| `.env` | API keys and config (see below) |
| `credentials.json` | Google OAuth client credentials (downloaded from Google Cloud Console) |
| `token_gmail.json` | Gmail OAuth token (generated locally) |
| `token_calendar.json` | Calendar OAuth token (generated locally) |
| `requirements.txt` | Python dependencies |
| `top_jobs_YYYYMMDD.csv` | Optional: job listings CSV (if using the jobs feature) |

---

## .env File

Create a `.env` file with the following content (fill in your actual values):

```
GEMINI_API_KEY=your_gemini_api_key_here
TODOIST_API_TOKEN=your_todoist_token_here
OPENWEATHER_API_KEY=your_openweather_key_here
GMAIL_APP_PASSWORD=your_gmail_app_password_here
GMAIL_CREDENTIALS_JSON=credentials.json
JOB_CSV_DIR=/home/<your-pythonanywhere-username>/daily_briefing
```

> **Gmail App Password**: Go to your Google Account → Security → 2-Step Verification →
> App passwords. Generate one for "Mail" on "Other (custom name)".

---

## PythonAnywhere Setup

### Step 1: Upload files

1. Log in to [pythonanywhere.com](https://www.pythonanywhere.com)
2. Go to the **Files** tab
3. Navigate to or create the directory `/home/<username>/daily_briefing/`
4. Upload each file listed in the "Files to Upload" section above using the upload button

### Step 2: Open a Bash console

Go to the **Consoles** tab and click **Bash**.

### Step 3: Install dependencies

```bash
pip3.10 install --user requests python-dateutil google-auth google-auth-oauthlib google-api-python-client todoist-api-python pandas
```

> PythonAnywhere free tier uses Python 3.10. Always use `pip3.10` and `python3.10`.

### Step 4: Test the script manually

```bash
cd ~/daily_briefing
python3.10 daily_briefing.py
```

Check for the output `Briefing sent successfully.` or, if `GMAIL_APP_PASSWORD` is not set,
check that `daily_briefing_preview.html` was created.

### Step 5: Set up the scheduled task

1. Go to the **Tasks** tab in PythonAnywhere
2. Click **Add a new scheduled task**
3. Set the time to **12:30 UTC** (= 6:30 AM Chicago time, CST; adjust to 11:30 UTC in CDT/summer)
4. Set the command to:

```
python3.10 /home/<your-pythonanywhere-username>/daily_briefing/daily_briefing.py
```

5. Click **Create**

---

## Timezone Note

Chicago observes:
- **CST (UTC-6)**: November → March → use **12:30 UTC** for 6:30 AM local
- **CDT (UTC-5)**: March → November → use **11:30 UTC** for 6:30 AM local

Update the scheduled task time when daylight saving time changes.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError` | Re-run the `pip3.10 install --user ...` command |
| OAuth error / token expired | Regenerate `token_gmail.json` and `token_calendar.json` locally and re-upload |
| Gemini returns no news | Check `GEMINI_API_KEY` in `.env`; verify the key has the Generative Language API enabled |
| Email not sending | Verify `GMAIL_APP_PASSWORD` is set correctly (not your regular Gmail password) |
| Jobs section empty | Confirm a `top_jobs_YYYYMMDD.csv` file exists in the path set by `JOB_CSV_DIR` |
| Script runs but no email | Check the PythonAnywhere task log under the Tasks tab for error output |

---

## Google Cloud Console Setup (if starting from scratch)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project
3. Enable these APIs: **Gmail API**, **Google Calendar API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Download the JSON file and rename it to `credentials.json`
