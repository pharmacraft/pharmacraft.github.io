#!/usr/bin/env python3
"""
PharmaCraft daily multi-stream poster.
Posts one labelled MCQ quiz per exam stream (MBBS, NEET PG, INI-CET, FMGE,
MD Pharmacology) to the Telegram channel each day, and writes daily.json
(used by the website "MCQ of the Day" box and the WhatsApp share button).
No external libraries needed.

Secrets (GitHub repo secrets):
  BOT_TOKEN  -> bot token from @BotFather
  CHANNEL    -> channel username, e.g. @pharmacraft_official
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

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "content.json"), encoding="utf-8") as f:
    data = json.load(f)

order   = data.get("stream_order", list(data.get("streams", {}).keys()))
emoji   = data.get("stream_emoji", {})
streams = data.get("streams", {})
start   = datetime.date.fromisoformat(data.get("start_date"))
today   = datetime.date.today()
day_index = max(0, (today - start).days)

date_str = today.strftime("%d %b %Y")

# 1) Header message
call("sendMessage", {
    "chat_id": CHANNEL,
    "text": "📅 <b>PharmaCraft Daily, " + date_str + "</b>\n5 exam streams, 1 question each. Tap an option to answer.",
    "parse_mode": "HTML",
    "disable_web_page_preview": "true",
})

daily = {"date": today.isoformat(), "items": []}

# 2) One quiz per stream
for s in order:
    lst = streams.get(s, [])
    if not lst:
        continue
    q = lst[day_index % len(lst)]
    tag = (emoji.get(s, "") + " [" + s + "]").strip()
    call("sendPoll", {
        "chat_id": CHANNEL,
        "question": (tag + " " + q.get("topic", "") + "\n" + q["question"])[:300],
        "options": json.dumps(q["options"]),
        "type": "quiz",
        "correct_option_id": q["correct"],
        "explanation": q.get("explanation", "")[:200],
        "is_anonymous": "true",
    })
    daily["items"].append({
        "stream": s, "emoji": emoji.get(s, ""),
        "topic": q.get("topic", ""), "question": q["question"],
        "options": q["options"], "correct": q["correct"],
        "explanation": q.get("explanation", ""),
    })
    print("Posted:", s, "index", day_index % len(lst))

# 3) Build WhatsApp share text + link
lines = ["*PharmaCraft Daily - " + date_str + "*", ""]
for it in daily["items"]:
    ans = it["options"][it["correct"]]
    lines.append((it["emoji"] + " *" + it["stream"] + "* (" + it["topic"] + ")").strip())
    lines.append("Q: " + it["question"])
    lines.append("Ans: " + ans)
    lines.append("Why: " + it["explanation"])
    lines.append("")
lines.append("Join: https://t.me/pharmacraft_official")
lines.append("More: https://pharmacraft.in")
wa_text = "\n".join(lines)
daily["whatsapp_text"] = wa_text
daily["whatsapp_url"]  = "https://wa.me/?text=" + urllib.parse.quote(wa_text)

with open(os.path.join(here, "daily.json"), "w", encoding="utf-8") as f:
    json.dump(daily, f, ensure_ascii=False, indent=2)
print("Wrote daily.json with", len(daily["items"]), "items.")
print("Done.")
