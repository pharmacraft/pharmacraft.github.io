#!/usr/bin/env python3
"""
PharmaCraft daily Telegram poster.
Posts one MCQ (as a native quiz) and one note to the channel each day.
Runs automatically via GitHub Actions. No external libraries needed.

Reads two secrets from environment variables:
  BOT_TOKEN  -> your bot token from @BotFather
  CHANNEL    -> your channel username, e.g. @pharmacraft_official
"""
import json, os, sys, datetime, urllib.request, urllib.parse

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL   = os.environ.get("CHANNEL", "").strip()

if not BOT_TOKEN or not CHANNEL:
    sys.exit("ERROR: BOT_TOKEN and CHANNEL must be set as GitHub secrets.")

API = "https://api.telegram.org/bot" + BOT_TOKEN + "/"

def call(method, params):
    data = urllib.parse.urlencode(params, doseq=True).encode()
    req = urllib.request.Request(API + method, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if not res.get("ok"):
        raise RuntimeError(method + " failed: " + json.dumps(res))
    return res

# Load content
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "content.json"), encoding="utf-8") as f:
    data = json.load(f)

mcqs  = data.get("mcqs", [])
notes = data.get("notes", [])
start = datetime.date.fromisoformat(data.get("start_date"))
today = datetime.date.today()
day_index = (today - start).days          # 0 on start_date, 1 next day, etc.
if day_index < 0:
    day_index = 0

# Pick today's items (loops back to start when the list ends)
header = "📅 <b>PharmaCraft Daily, " + today.strftime("%d %b %Y") + "</b>"

if notes:
    note = notes[day_index % len(notes)]
    call("sendMessage", {
        "chat_id": CHANNEL,
        "text": header + "\n\n" + note,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })
    print("Note posted (index", day_index % len(notes), ")")

if mcqs:
    q = mcqs[day_index % len(mcqs)]
    call("sendPoll", {
        "chat_id": CHANNEL,
        "question": "MCQ (" + q.get("topic", "Pharmacology") + "): " + q["question"],
        "options": json.dumps(q["options"]),
        "type": "quiz",
        "correct_option_id": q["correct"],
        "explanation": q.get("explanation", "")[:200],
        "is_anonymous": "true",
    })
    print("MCQ quiz posted (index", day_index % len(mcqs), ")")

print("Done.")
