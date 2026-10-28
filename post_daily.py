#!/usr/bin/env python3
"""
PharmaCraft daily 5-stream MCQ poster (v2: fresh questions written by Claude).

Every day at 9:00 AM IST (GitHub Actions) this script:
  1. Asks Claude (Anthropic API) to write 5 NEW MCQs, one per stream
     (MBBS, FMGE, NEET PG, INI-CET, MD Pharmacology), following the
     PharmaCraft rules: 14-topic rotation, MD as per NMC syllabus (Paper I-IV
     rotation), 1 clinical-case MCQ + 1 recent-advance/latest-guideline MCQ
     per day, and NO repeats (checked against mcq_log.json).
  2. Posts them to Telegram as quiz polls.
  3. Writes daily.json for the website "MCQ of the Day" box + WhatsApp share.
  4. Appends the 5 questions to mcq_log.json (the permanent no-repeat log).

If the API key is missing or Claude fails twice, it falls back to the
question bank in content.json, using only bank questions not posted before.

GitHub repo secrets:
  BOT_TOKEN          -> Telegram bot token (from @BotFather)
  CHANNEL            -> @pharmacraft_official
  ANTHROPIC_API_KEY  -> Anthropic API key (console.anthropic.com)
Optional repo variable:
  CLAUDE_MODEL       -> model id to use (default below)

Standard library only.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT_FILE = os.path.join(HERE, "content.json")
LOG_FILE = os.path.join(HERE, "mcq_log.json")
DAILY_FILE = os.path.join(HERE, "daily.json")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL = os.environ.get("CHANNEL", "").strip()
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
DRY_RUN = os.environ.get("DRY_RUN", "").strip() == "1"   # local testing: no Telegram calls
MODELS = [m for m in [os.environ.get("CLAUDE_MODEL", "").strip(),
                      "claude-opus-5-5", "claude-sonnet-4-5"] if m]

# Daily order of the 5 slots (Q1..Q5) and their depth
SLOTS = [
    ("MBBS",            "Core concept, easy. Map to an NMC CBME UG pharmacology competency (PH code) where possible."),
    ("FMGE",            "Easy-moderate, frequently tested FMGE facts."),
    ("NEET PG",         "Moderate, applied NEET-PG style."),
    ("INI-CET",         "Moderate-hard, conceptual / two-step reasoning, INI-CET style."),
    ("MD Pharmacology", "Hard, MD Pharmacology level, from today's NMC MD theory paper (see below)."),
]
EMOJI = {"MBBS": "🎓", "NEET PG": "🩺", "INI-CET": "🏥", "FMGE": "🌍", "MD Pharmacology": "🔬"}

TOPICS = [
    "General Pharmacology",
    "Autonomic Nervous System (ANS)",
    "Cardiovascular System (CVS)",
    "Central Nervous System (CNS)",
    "Autacoids, NSAIDs & Analgesics",
    "Respiratory System",
    "Gastrointestinal Drugs (GIT)",
    "Endocrine & Hormones",
    "Antimicrobials - Antibacterials",
    "Antiviral, Antifungal, Antiprotozoal & Anthelmintic",
    "Anticancer & Immunosuppressants",
    "Hematology - Blood, Coagulation, Hematinics",
    "Renal & Diuretics",
    "Toxicology & Chelating Agents",
]

MD_PAPERS = [
    ("Paper I - General Pharmacology",
     "molecular pharmacology, receptors, PK/PD, biotransformation, pharmacogenomics, drug delivery systems, "
     "pharmacometrics, experimental pharmacology (dose-response, EC50/ED50, pA2/pD2, isolated tissue, bioassays, "
     "screening models, CPCSEA, 3Rs), analytical methods (HPLC, ELISA, spectrophotometry, immunoassays)"),
    ("Paper II - Clinical Pharmacology",
     "clinical trial phases and design, GCP, informed consent, SAE reporting, New Drugs and Clinical Trials Rules 2019, "
     "Drugs & Cosmetics Act, pharmacovigilance and PvPI causality (WHO-UMC, Naranjo), pharmacoeconomics, "
     "pharmacoepidemiology, drug utilization studies, prescription audit, NLEM/essential medicines, rational and generic "
     "drug use, antimicrobial stewardship, TDM, special populations, biostatistics, research methodology, OTC/herbal"),
    ("Paper III - Systemic Pharmacology",
     "today's PharmaCraft topic at MD depth (molecular mechanism, PK nuances, landmark trial evidence)"),
    ("Paper IV - Recent Advances in Pharmacology",
     "new drug approvals (CDSCO/FDA/EMA), novel targets and drug classes, biologics and biosimilars, gene and cell "
     "therapies, updated treatment guidelines"),
]


# ───────────────────────── helpers ─────────────────────────
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def stem_hash(q):
    return hashlib.sha1(norm(q).encode()).hexdigest()[:12]


def tg(method, params):
    if DRY_RUN:
        print("[DRY_RUN] Telegram", method, json.dumps(params, ensure_ascii=False)[:160])
        return {"ok": True}
    data = urllib.parse.urlencode(params, doseq=True).encode()
    req = urllib.request.Request("https://api.telegram.org/bot" + BOT_TOKEN + "/" + method, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if not res.get("ok"):
        raise RuntimeError(method + " failed: " + json.dumps(res))
    return res


# ───────────────────────── today's plan ─────────────────────────
def todays_plan(log, today):
    """Work out today's topic, MD paper, case slot and recent-advance slot from the log."""
    days = [d for d in log.get("days", []) if d.get("date") != today.isoformat()]
    if days:
        last = days[-1]
        topic_i = (last.get("topic_index", -1) + 1) % len(TOPICS)
        paper_i = (last.get("md_paper_index", -1) + 1) % len(MD_PAPERS)
        case_slot = (last.get("case_slot", -1) + 1) % 5
    else:
        topic_i, paper_i, case_slot = 0, 0, 0
    ra_slot = (case_slot + 2) % 5            # always a different slot from the case
    return {"topic_index": topic_i, "md_paper_index": paper_i, "case_slot": case_slot, "ra_slot": ra_slot}


def used_concepts(log):
    used = {s: [] for s, _ in SLOTS}
    for d in log.get("days", []):
        for it in d.get("items", []):
            used.setdefault(it.get("stream", ""), []).append(it.get("concept", ""))
    return used


# ───────────────────────── Claude generation ─────────────────────────
def build_prompt(plan, log, today):
    topic = TOPICS[plan["topic_index"]]
    paper, paper_scope = MD_PAPERS[plan["md_paper_index"]]
    used = used_concepts(log)
    recent_all = []
    for d in log.get("days", [])[-60:]:
        for it in d.get("items", []):
            recent_all.append(f'{it.get("concept","")} ({it.get("angle","")})')

    slot_lines = []
    for i, (stream, depth) in enumerate(SLOTS):
        extra = []
        if i == plan["case_slot"]:
            extra.append("THIS MUST BE THE FULL CLINICAL CASE-BASED SCENARIO (age, sex, complaint, key findings/"
                         "investigation, clear clinical question; 50-90 words)")
        if i == plan["ra_slot"]:
            extra.append("THIS MUST BE THE RECENT ADVANCE / LATEST GUIDELINE question (recent approval or current "
                         "guideline such as GINA, GOLD, ESC, ADA, KDIGO, NTEP, NACO, WHO, NLEM, PvPI, CDSCO). "
                         "Verify it with web search first and cite source + year in the explanation")
        topic_for_slot = (f"NMC MD syllabus, {paper}: {paper_scope}" if stream == "MD Pharmacology"
                          else f"PharmaCraft topic #{plan['topic_index']+1}: {topic}")
        slot_lines.append(f"Q{i+1} | {stream} | {depth} | Topic: {topic_for_slot}"
                          + (" | " + "; ".join(extra) if extra else ""))

    avoid = "\n".join(f"- {s}: " + (", ".join(sorted(set(c for c in used.get(s, []) if c))) or "none yet")
                      for s, _ in SLOTS)
    recent = ", ".join(recent_all[-150:]) or "none yet"

    return f"""You are Dr. Susheel Kumar's PharmaCraft MCQ writer (Assistant Professor of Pharmacology).
Write today's ({today.isoformat()}) set of 5 original pharmacology MCQs, one per slot:

{chr(10).join(slot_lines)}

NO-REPEAT RULES (strict):
1. For each stream, the concept must NOT be any concept already used for that stream:
{avoid}
2. Do not repeat the same drug + same angle used in the last 60 days at any level: {recent}
3. Today's 5 questions must each test a different angle (MOA / PK / Uses / ADR / Contraindication / Interaction /
   Classification / Applied), and must not share the same drug.

QUALITY RULES:
- Single best answer, exactly 4 options. No "all of the above" / "none of the above". Avoid negative stems.
- Plausible distractors (same class, look-alike names, classic confusions).
- Facts must match standard texts (KD Tripathi, Goodman & Gilman, Katzung, Rang & Dale) or the cited guideline.
  Never invent facts, doses, approvals or dates. If unsure, choose another concept.
- Indian generic names (paracetamol, adrenaline). Original wording, natural professor's voice. Not copied from
  question banks or past papers.
- Spread the correct answer: across the 5 questions no option position may be correct more than twice.
- Length limits (Telegram): each option <= 95 characters; non-case stems <= 230 characters;
  "explanation_short" <= 190 characters; "explanation" 2-4 sentences (why correct, why the strongest distractor is wrong).

OUTPUT: return ONLY a JSON object, no markdown fences, no other text:
{{"items": [
  {{"slot": 1, "stream": "MBBS", "topic": "<short topic label>", "concept": "<drug/concept tested, 2-6 words>",
    "angle": "<MOA|PK|Uses|ADR|CI|Interaction|Classification|Applied>", "type": "<Recall|Applied|Clinical case|Recent advance>",
    "difficulty": "<Easy|Moderate|Hard>", "question": "...", "options": ["...","...","...","..."], "correct": 0,
    "explanation": "...", "explanation_short": "...", "source": "<guideline/agency + year, only for recent advance else empty>"}},
  ... 5 items in slot order 1-5 ...
]}}"""


def call_claude(prompt):
    last_err = None
    for model in MODELS:
        body = {
            "model": model,
            "max_tokens": 6000,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(),
            headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                res = json.load(r)
            text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
            print("Claude model used:", model)
            return text
        except urllib.error.HTTPError as e:
            last_err = f"{model}: HTTP {e.code} {e.read()[:300]!r}"
            print("Claude call failed:", last_err)
        except Exception as e:  # network/timeout
            last_err = f"{model}: {e}"
            print("Claude call failed:", last_err)
    raise RuntimeError(last_err or "Claude call failed")


def parse_items(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("No JSON in Claude response")
    items = json.loads(m.group(0))["items"]
    return items


def validate(items, log, plan):
    if len(items) != 5:
        raise ValueError(f"Expected 5 items, got {len(items)}")
    used = {s: set(norm(c) for c in cs) for s, cs in used_concepts(log).items()}
    old_stems = {it.get("stem_hash") for d in log.get("days", []) for it in d.get("items", [])}
    letters = []
    for i, (it, (stream, _)) in enumerate(zip(items, SLOTS)):
        it["stream"] = stream
        opts = it.get("options", [])
        if len(opts) != 4 or len(set(norm(o) for o in opts)) != 4:
            raise ValueError(f"Q{i+1}: need 4 distinct options")
        if not isinstance(it.get("correct"), int) or not 0 <= it["correct"] <= 3:
            raise ValueError(f"Q{i+1}: bad correct index")
        if not it.get("question") or not it.get("concept"):
            raise ValueError(f"Q{i+1}: missing question/concept")
        if norm(it["concept"]) in used.get(stream, set()):
            raise ValueError(f"Q{i+1}: concept '{it['concept']}' already used for {stream}")
        if stem_hash(it["question"]) in old_stems:
            raise ValueError(f"Q{i+1}: repeated stem")
        it["options"] = [o[:100] for o in opts]
        letters.append(it["correct"])
    if max(letters.count(k) for k in range(4)) > 2:
        # fix answer spread by rotating options of the offending questions
        for i, it in enumerate(items):
            if letters.count(it["correct"]) > 2:
                tgt = min(range(4), key=lambda k: letters.count(k))
                o = it["options"]
                o[it["correct"]], o[tgt] = o[tgt], o[it["correct"]]
                letters[i] = tgt
                it["correct"] = tgt
    return items


def generate_with_claude(plan, log, today):
    prompt = build_prompt(plan, log, today)
    errors = []
    for attempt in range(2):
        try:
            p = prompt if not errors else prompt + "\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED: " + errors[-1] + \
                ". Fix this and return the full JSON again."
            items = validate(parse_items(call_claude(p)), log, plan)
            return items
        except Exception as e:
            errors.append(str(e))
            print("Attempt", attempt + 1, "rejected:", e)
    raise RuntimeError("; ".join(errors))


# ───────────────────────── fallback: question bank ─────────────────────────
def from_bank(log):
    bank = load_json(CONTENT_FILE, {}).get("streams", {})
    old = {it.get("stem_hash") for d in log.get("days", []) for it in d.get("items", [])}
    items = []
    for stream, _ in SLOTS:
        lst = bank.get(stream, [])
        if not lst:
            continue
        fresh = [q for q in lst if stem_hash(q["question"]) not in old]
        _n = len([d for d in log.get("days", []) if d.get("items")])
        q = dict(fresh[0] if fresh else lst[_n % len(lst)])
        q.update({"stream": stream, "concept": q.get("topic", ""), "angle": "", "type": "Bank",
                  "explanation_short": q.get("explanation", "")[:190]})
        items.append(q)
    return items


def seed_log_from_bank(log, today):
    """First run only: mark bank questions already posted since start_date so they never repeat."""
    if log.get("days"):
        return
    data = load_json(CONTENT_FILE, {})
    try:
        start = datetime.date.fromisoformat(data.get("start_date"))
    except (TypeError, ValueError):
        return
    n_days = max(0, (today - start).days)
    seeded = []
    for stream, lst in data.get("streams", {}).items():
        for q in lst[:min(n_days, len(lst))]:
            seeded.append({"stream": stream, "concept": q.get("topic", "") + ": " + q["question"][:60],
                           "stem_hash": stem_hash(q["question"]), "source": "bank"})
    log.setdefault("days", []).append({"date": "seed-from-bank", "topic_index": -1, "md_paper_index": -1,
                                       "case_slot": -1, "items": seeded})


# ───────────────────────── main ─────────────────────────
def main():
    if not DRY_RUN and (not BOT_TOKEN or not CHANNEL):
        sys.exit("ERROR: BOT_TOKEN and CHANNEL must be set as GitHub secrets.")

    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()
    log = load_json(LOG_FILE, {"days": []})
    pass  # bank-seed disabled
    if any(d.get("date") == today.isoformat() for d in log["days"]):
        print("Already posted today - nothing to do.")
        return

    plan = todays_plan(log, today)
    source = "claude"
    items = []
    if API_KEY:
        try:
            items = generate_with_claude(plan, log, today)
        except Exception as e:
            print("Claude generation failed, using question bank:", e)
    if not items:
        source = "bank"
        items = from_bank(log)
    if not items:
        sys.exit("ERROR: no questions available.")

    date_str = today.strftime("%d %b %Y")
    topic_name = TOPICS[plan["topic_index"]]
    paper_name = MD_PAPERS[plan["md_paper_index"]][0].split(" - ")[0]
    header = (f"📅 <b>PharmaCraft Daily, {date_str}</b>\n"
              f"Topic: {topic_name} | MD: {paper_name}\n"
              "5 exam streams, 1 question each. Tap an option to answer.")
    tg("sendMessage", {"chat_id": CHANNEL, "text": header, "parse_mode": "HTML",
                       "disable_web_page_preview": "true"})

    daily = {"date": today.isoformat(), "items": []}
    for it in items:
        label = it.get("type", "")
        label = f" ({label})" if label in ("Clinical case", "Recent advance") else ""
        tag = f'{EMOJI.get(it["stream"], "")} [{it["stream"]}] {it.get("topic", "")}{label}'.strip()
        full_q = tag + "\n" + it["question"]
        if len(full_q) <= 300:
            poll_q = full_q
        else:  # long clinical case: send the case as a message, then the poll
            tg("sendMessage", {"chat_id": CHANNEL, "text": full_q})
            poll_q = (tag + "\n☝️ Choose the single best answer for the case above.")[:300]
        expl_short = it.get("explanation_short") or it.get("explanation", "")
        tg("sendPoll", {"chat_id": CHANNEL, "question": poll_q, "options": json.dumps(it["options"]),
                        "type": "quiz", "correct_option_id": it["correct"],
                        "explanation": expl_short[:200], "is_anonymous": "true"})
        expl = it.get("explanation", "")
        if it.get("source") and it["source"] not in expl:
            expl += f' (Source: {it["source"]})'
        daily["items"].append({"stream": it["stream"], "emoji": EMOJI.get(it["stream"], ""),
                               "topic": it.get("topic", "") + label, "question": it["question"],
                               "options": it["options"], "correct": it["correct"], "explanation": expl})
        print("Posted:", it["stream"], "-", it.get("concept", ""))

    lines = [f"*PharmaCraft Daily - {date_str}*", ""]
    for it in daily["items"]:
        lines += [f'{it["emoji"]} *{it["stream"]}* ({it["topic"]})'.strip(), "Q: " + it["question"],
                  "Ans: " + it["options"][it["correct"]], "Why: " + it["explanation"], ""]
    lines += ["Join: https://t.me/pharmacraft_official", "More: https://pharmacraft.in"]
    wa_text = "\n".join(lines)
    daily["whatsapp_text"] = wa_text
    daily["whatsapp_url"] = "https://wa.me/?text=" + urllib.parse.quote(wa_text)
    with open(DAILY_FILE, "w", encoding="utf-8") as f:
        json.dump(daily, f, ensure_ascii=False, indent=2)

    log["days"].append({
        "date": today.isoformat(), "source": source, **plan,
        "items": [{"stream": it["stream"], "concept": it.get("concept", ""), "angle": it.get("angle", ""),
                   "type": it.get("type", ""), "topic": it.get("topic", ""),
                   "stem_hash": stem_hash(it["question"]), "stem": it["question"][:120]} for it in items],
    })
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print(f"Done. {len(items)} questions from {source}; log now has {len(log['days'])} entries.")


if __name__ == "__main__":
    main()
