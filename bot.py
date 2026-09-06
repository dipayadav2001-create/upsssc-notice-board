import os
import re
import json
import time
import html
import hashlib
import threading
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify

# ============================================================
# GOVERNMENT JOB & EXAM ASSISTANT
# ============================================================
# Official sources are scanned first. Secondary educational /
# recruitment sites are used only for discovery and cross-checking.
#
# Environment variables required on Render:
# BOT_TOKEN
# ADMIN_ID
# WEBHOOK_URL
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID", "")).strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

MAX_LATEST = 50
MAX_ALERTS_PER_RUN = 20
SCAN_INTERVAL = 300  # 5 minutes

SEEN_FILE = "seen.json"
LATEST_FILE = "latest.json"
USERS_FILE = "users.json"
FOLLOWS_FILE = "follows.json"
CONTACT_FILE = "contact_waiting.json"

app = Flask(__name__)

# ------------------------------------------------------------
# OFFICIAL GOVERNMENT SOURCES
# ------------------------------------------------------------
SOURCES = {
    "UPSC": {
        "name": "UPSC",
        "url": "https://www.upsc.gov.in/whats-new",
        "home": "https://www.upsc.gov.in/",
        "priority": "official",
    },
    "SSC": {
        "name": "SSC",
        "url": "https://ssc.gov.in/",
        "home": "https://ssc.gov.in/",
        "priority": "official",
    },
    "RAILWAY": {
        "name": "Railway / RRB",
        "url": "https://rrb.indianrailways.gov.in/",
        "home": "https://www.rrcb.gov.in/rrbs.html",
        "priority": "official",
    },
    "UPSSSC": {
        "name": "UPSSSC",
        "url": "https://upsssc.gov.in/",
        "home": "https://upsssc.gov.in/",
        "priority": "official",
    },
    "BPSC": {
        "name": "BPSC",
        "url": "https://bpsc.bihar.gov.in/",
        "home": "https://bpsc.bihar.gov.in/",
        "priority": "official",
    },
    "UPESSC": {
        "name": "UP Education Service Selection Commission",
        "url": "https://apply.upessc.org/",
        "home": "https://apply.upessc.org/",
        "priority": "official",
    },
    "CTET": {
        "name": "CTET",
        "url": "https://ctet.nic.in/",
        "home": "https://ctet.nic.in/documents/",
        "priority": "official",
    },
    "UPTET": {
        "name": "UPTET / U.P. Pariksha Niyamak Pradhikari",
        "url": "https://updeled.gov.in/",
        "home": "https://updeled.gov.in/",
        "priority": "official",
    },
}

# Secondary sources: discovery only. A secondary item is never
# presented as an official notification.
SECONDARY_SOURCES = {
    "EDU_JAGRAN": {
        "name": "Jagran Josh",
        "url": "https://www.jagranjosh.com/",
        "home": "https://www.jagranjosh.com/",
        "priority": "secondary",
    },
    "EDU_ADDA": {
        "name": "Adda247",
        "url": "https://www.adda247.com/",
        "home": "https://www.adda247.com/",
        "priority": "secondary",
    },
    "EDU_TESTBOOK": {
        "name": "Testbook",
        "url": "https://testbook.com/",
        "home": "https://testbook.com/",
        "priority": "secondary",
    },
}

ALL_SOURCES = {**SOURCES, **SECONDARY_SOURCES}

# ------------------------------------------------------------
# EXAMS
# ------------------------------------------------------------
EXAMS = {
    "UPSC": [
        "Civil Services Examination (CSE)",
        "NDA",
        "CDS",
        "CAPF",
        "Engineering Services (ESE)",
        "Combined Medical Services (CMS)",
        "IES/ISS",
        "Geo-Scientist",
    ],
    "SSC": [
        "CGL",
        "CHSL",
        "MTS",
        "GD Constable",
        "CPO",
        "JE",
        "Stenographer",
        "Selection Post",
        "JHT",
    ],
    "RAILWAY": [
        "NTPC",
        "Group D",
        "ALP",
        "Technician",
        "JE",
        "RPF",
        "Paramedical",
        "RRB Level 1",
    ],
    "UPSSSC": [
        "PET",
        "Junior Assistant",
        "VDO",
        "Lekhpal",
        "Stenographer",
        "X-Ray Technician",
        "Forest Guard",
        "Junior Engineer",
        "Technical Assistant",
    ],
    "BPSC": [
        "BPSC CCE",
        "Teacher Recruitment / TRE",
        "Head Teacher",
        "Headmaster",
        "Assistant Engineer",
        "AEDO",
        "Assistant",
    ],
    "UPESSC": [
        "TGT",
        "PGT",
        "Special TET",
        "Teacher Recruitment",
        "Principal",
        "Assistant Professor",
    ],
    "CTET": [
        "CTET Paper I",
        "CTET Paper II",
        "CTET",
    ],
    "UPTET": [
        "UPTET Primary",
        "UPTET Upper Primary",
        "UPTET",
    ],
}

INFO_TYPES = [
    "Notification",
    "Application",
    "Admit Card",
    "Exam Date",
    "Answer Key",
    "Result",
    "Cut Off",
    "Vacancy",
    "All Updates",
]

# ------------------------------------------------------------
# QUALIFICATION PROFILE
# ------------------------------------------------------------
QUALIFICATIONS = {
    "10th": ["10th", "matric", "high school"],
    "12th": ["12th", "intermediate", "10+2", "senior secondary"],
    "ITI": ["iti", "industrial training institute"],
    "Diploma": ["diploma", "polytechnic"],
    "Graduation": [
        "graduation",
        "graduate",
        "bachelor",
        "degree",
        "any degree",
        "ba",
        "b.sc",
        "bsc",
        "b.com",
        "bcom",
        "bca",
    ],
    "B.Ed": ["b.ed", "bed", "bachelor of education"],
    "D.El.Ed": ["d.el.ed", "deled", "dled", "btc", "elementary education"],
    "B.Tech/BE": ["b.tech", "btech", "b.e", "be", "engineering"],
    "Post Graduation": [
        "post graduation",
        "postgraduate",
        "master degree",
        "masters",
        "ma ",
        "m.sc",
        "msc",
        "m.com",
        "mcom",
    ],
    "LLB": ["llb", "law degree"],
    "B.Pharm": ["b.pharm", "bpharm", "pharmacy"],
    "B.Sc": ["b.sc", "bsc", "bachelor of science"],
    "B.Com": ["b.com", "bcom", "bachelor of commerce"],
    "BA": ["b.a.", "b.a ", "ba degree", "bachelor of arts"],
}

TEACHING_KEYS = [
    "teacher",
    "tgt",
    "pgt",
    "tet",
    "ctet",
    "uptet",
    "bed",
    "b.ed",
    "d.el.ed",
    "deled",
    "btc",
    "primary teacher",
    "upper primary",
    "school teacher",
]

EXAM_ALIASES = {
    "cgl": ["cgl", "combined graduate level"],
    "chsl": ["chsl", "combined higher secondary"],
    "mts": ["mts", "multi tasking"],
    "gd": ["gd constable", "general duty"],
    "ntpc": ["ntpc"],
    "group d": ["group d", "level 1"],
    "alp": ["alp", "assistant loco pilot"],
    "technician": ["technician"],
    "je": ["junior engineer", "je"],
    "pet": ["pet", "preliminary eligibility test"],
    "lekhpal": ["lekhpal"],
    "vdo": ["vdo", "village development officer"],
    "tgt": ["tgt", "trained graduate teacher"],
    "pgt": ["pgt", "post graduate teacher"],
    "ctet": ["ctet", "central teacher eligibility test"],
    "uptet": ["uptet", "up teacher eligibility test"],
    "tet": ["tet", "teacher eligibility test"],
}

# ------------------------------------------------------------
# JSON HELPERS
# ------------------------------------------------------------
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_users():
    return load_json(USERS_FILE, {})


def save_user(user):
    users = load_users()
    uid = str(user.get("id"))
    users[uid] = {
        "id": user.get("id"),
        "first_name": user.get("first_name", ""),
        "username": user.get("username", ""),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        **users.get(uid, {}),
    }
    save_json(USERS_FILE, users)


# ------------------------------------------------------------
# TELEGRAM HELPERS
# ------------------------------------------------------------
def tg(method, data=None):
    if not BOT_TOKEN:
        return {}
    try:
        r = requests.post(
            f"{TELEGRAM_API}/{method}",
            data=data or {},
            timeout=25,
        )
        return r.json()
    except Exception as e:
        print("Telegram error:", e)
        return {}


def send_message(chat_id, text, reply_markup=None, disable_preview=True):
    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_preview,
        "parse_mode": "HTML",
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return tg("sendMessage", data)


def answer_callback(callback_id):
    tg("answerCallbackQuery", {"callback_query_id": callback_id})


def keyboard(rows):
    return {
        "keyboard": rows,
        "resize_keyboard": True,
        "is_persistent": True,
    }


MAIN_KB = keyboard([
    ["📚 Exams", "💼 Find Jobs"],
    ["🎓 My Qualification", "👨‍🏫 Teaching Jobs"],
    ["🆕 Latest Vacancies", "📢 Latest Notices"],
    ["🔔 My Alerts", "🔎 Search"],
    ["📊 Status", "❓ Help"],
    ["💬 Contact Admin"],
])

# ------------------------------------------------------------
# FORMATTING
# ------------------------------------------------------------
def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def source_label(source_key):
    return ALL_SOURCES.get(source_key, {}).get("name", source_key)


def make_notice_id(source_key, title, url):
    raw = f"{source_key}|{title}|{url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def notice_text(item):
    return f"{item.get('title', '')} {item.get('description', '')}".lower()


def format_notice(item):
    badge = "🏛️ Official" if item.get("priority") == "official" else "🔎 Secondary / cross-check"
    title = item.get("title", "Untitled")
    source = source_label(item.get("source", ""))
    url = item.get("url", "")
    desc = item.get("description", "")

    text = f"{badge}\n\n<b>{html.escape(title)}</b>\n\n"
    text += f"🏢 Source: {html.escape(source)}\n"
    if desc:
        text += f"📝 {html.escape(desc[:500])}\n"
    if url:
        text += f"\n🔗 {html.escape(url)}"
    return text


# ------------------------------------------------------------
# SCRAPING
# ------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GovtExamAssistant/2.0; "
        "+https://upsssc-notice-board.onrender.com)"
    )
}


def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print("HTTP", r.status_code, url)
            return ""
        return r.text
    except Exception as e:
        print("Fetch error:", url, e)
        return ""


def is_relevant_link(title, href):
    text = f"{title} {href}".lower()
    keywords = [
        "notification", "notice", "advertisement", "vacancy", "recruit",
        "recruitment", "application", "apply", "admit", "answer", "result",
        "exam", "cgl", "chsl", "mts", "gd", "ntpc", "railway", "rrb",
        "pet", "lekhpal", "teacher", "tgt", "pgt", "tet", "ctet", "uptet",
        "deled", "bed", "group d", "alp", "technician", "junior assistant",
        "stenographer", "cce", "bpsc", "upessc"
    ]
    return any(k in text for k in keywords)


def parse_source(source_key, source):
    html_text = fetch_page(source["url"])
    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    seen_local = set()

    # Source-specific page hints. We still keep a safe generic fallback
    # because official sites frequently change their HTML.
    anchors = soup.find_all("a", href=True)

    for a in anchors:
        title = clean_text(a.get_text(" ", strip=True))
        href = urljoin(source["url"], a.get("href", "").strip())

        if not title or len(title) < 4:
            continue
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        if href in seen_local:
            continue
        if not is_relevant_link(title, href):
            continue

        # Avoid obvious navigation/menu noise.
        if title.lower() in {
            "home", "login", "contact us", "about us", "sitemap",
            "privacy policy", "terms", "menu", "search"
        }:
            continue

        seen_local.add(href)

        item = {
            "id": make_notice_id(source_key, title, href),
            "source": source_key,
            "priority": source.get("priority", "official"),
            "title": title[:300],
            "description": "",
            "url": href,
            "found_at": datetime.now(timezone.utc).isoformat(),
        }

        items.append(item)

        if len(items) >= 40:
            break

    return items


def scan_all_sources():
    """
    Scan official sources first, then secondary sources.
    Official items are inserted before secondary items.
    """
    official_items = []
    secondary_items = []

    for key, source in SOURCES.items():
        try:
            found = parse_source(key, source)
            official_items.extend(found)
            print(f"{key}: {len(found)}")
        except Exception as e:
            print("Source error:", key, e)

    for key, source in SECONDARY_SOURCES.items():
        try:
            found = parse_source(key, source)
            secondary_items.extend(found)
            print(f"{key}: {len(found)}")
        except Exception as e:
            print("Secondary source error:", key, e)

    return official_items + secondary_items


# ------------------------------------------------------------
# MATCHING ENGINE
# ------------------------------------------------------------
def qualification_matches(profile, item):
    if not profile:
        return False

    text = notice_text(item)

    selected = profile.get("qualifications", [])
    if not selected:
        return True

    # Direct qualification keyword match.
    for q in selected:
        aliases = QUALIFICATIONS.get(q, [q.lower()])
        if any(alias.lower() in text for alias in aliases):
            return True

    # Generic "graduate/degree/any qualification" vacancies are useful
    # for graduation and PG profiles even when the title omits it.
    if "Graduation" in selected:
        if any(x in text for x in [
            "graduate", "graduation", "degree", "bachelor",
            "any degree", "cgl", "upsssc", "bpsc"
        ]):
            return True

    return False


def teaching_matches(profile, item):
    text = notice_text(item)
    if any(k in text for k in TEACHING_KEYS):
        if not profile:
            return True

        qs = profile.get("qualifications", [])
        if any(q in qs for q in ["B.Ed", "D.El.Ed", "Graduation", "Post Graduation"]):
            return True

    return False


def exam_matches(exam, item):
    text = notice_text(item)
    aliases = EXAM_ALIASES.get(exam.lower(), [exam.lower()])
    return any(x in text for x in aliases)


def search_items(query, limit=10):
    items = load_json(LATEST_FILE, [])
    q = query.lower().strip()
    if not q:
        return []

    result = []
    for item in items:
        hay = notice_text(item)
        if q in hay or q in item.get("source", "").lower():
            result.append(item)
        if len(result) >= limit:
            break
    return result


# ------------------------------------------------------------
# FOLLOW SYSTEM
# ------------------------------------------------------------
def get_follows():
    return load_json(FOLLOWS_FILE, {})


def save_follow(user_id, exam):
    follows = get_follows()
    uid = str(user_id)
    follows.setdefault(uid, [])
    if exam not in follows[uid]:
        follows[uid].append(exam)
    save_json(FOLLOWS_FILE, follows)


def remove_follow(user_id, exam):
    follows = get_follows()
    uid = str(user_id)
    follows[uid] = [x for x in follows.get(uid, []) if x != exam]
    save_json(FOLLOWS_FILE, follows)


# ------------------------------------------------------------
# CONTACT SYSTEM
# ------------------------------------------------------------
def get_contacts():
    return load_json(CONTACT_FILE, {})


def set_contact_waiting(user_id, value=True):
    contacts = get_contacts()
    uid = str(user_id)
    if value:
        contacts[uid] = True
    else:
        contacts.pop(uid, None)
    save_json(CONTACT_FILE, contacts)


# ------------------------------------------------------------
# QUALIFICATION PROFILE UI
# ------------------------------------------------------------
def qualification_keyboard():
    return keyboard([
        ["10th", "12th"],
        ["ITI", "Diploma"],
        ["Graduation", "Post Graduation"],
        ["B.Ed", "D.El.Ed"],
        ["B.Tech/BE", "B.Sc"],
        ["B.Com", "BA"],
        ["LLB", "B.Pharm"],
        ["✅ Done", "❌ Clear"],
    ])


def update_qualification(user_id, q):
    users = load_users()
    uid = str(user_id)
    profile = users.get(uid, {}).get("profile", {})
    qs = profile.get("qualifications", [])

    if q not in qs:
        qs.append(q)

    users.setdefault(uid, {})
    users[uid]["profile"] = {
        **profile,
        "qualifications": qs,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_json(USERS_FILE, users)


def clear_qualification(user_id):
    users = load_users()
    uid = str(user_id)
    users.setdefault(uid, {})
    users[uid]["profile"] = {"qualifications": []}
    save_json(USERS_FILE, users)


def get_profile(user_id):
    users = load_users()
    return users.get(str(user_id), {}).get("profile", {})


# ------------------------------------------------------------
# MENUS
# ------------------------------------------------------------
def show_exams(chat_id):
    rows = []
    for key, values in EXAMS.items():
        rows.append([f"🏛️ {key}"])
    rows.append(["⬅️ Main Menu"])
    send_message(
        chat_id,
        "📚 <b>Exam Boards</b>\n\nBoard चुनो:",
        keyboard(rows),
    )


def show_board_exams(chat_id, board):
    values = EXAMS.get(board, [])
    rows = []
    for exam in values:
        rows.append([f"🔎 {exam}"])
    rows.append(["⬅️ Exams"])
    send_message(
        chat_id,
        f"📚 <b>{html.escape(board)}</b>\n\nExam चुनो:",
        keyboard(rows),
    )


def show_info_types(chat_id, board, exam):
    rows = []
    for info in INFO_TYPES:
        rows.append([f"📌 {info}"])
    rows.append(["⬅️ Exams"])
    send_message(
        chat_id,
        f"🔎 <b>{html.escape(exam)}</b>\n\n"
        "अब information type चुनो:",
        keyboard(rows),
    )


def show_results(chat_id, items, heading="📢 Results"):
    if not items:
        send_message(
            chat_id,
            f"{heading}\n\n❌ Matching notice नहीं मिला.\n\n"
            "Official source पर नया update आने के बाद अगली scan में दिखाई देगा.",
            MAIN_KB,
        )
        return

    send_message(chat_id, f"{heading}\n\nकुल {len(items)} result मिले.")
    for item in items[:10]:
        send_message(chat_id, format_notice(item))


# ------------------------------------------------------------
# COMMAND HANDLERS
# ------------------------------------------------------------
def start(chat_id, user):
    save_user(user)
    send_message(
        chat_id,
        "👋 <b>नमस्ते!</b>\n\n"
        "मैं <b>Government Job & Exam Assistant</b> हूँ.\n\n"
        "मैं UPSC, SSC, Railway, UPSSSC, BPSC के साथ "
        "UPESSC, TGT, PGT, TET और CTET updates खोजता हूँ.\n\n"
        "🎓 अपनी qualification save करके matching jobs भी खोज सकते हो.\n\n"
        "नीचे menu से शुरू करो 👇",
        MAIN_KB,
    )


def help_text(chat_id):
    send_message(
        chat_id,
        "❓ <b>Help</b>\n\n"
        "📚 <b>Exams</b> — board और exam के हिसाब से notices\n"
        "💼 <b>Find Jobs</b> — आपकी saved qualification से matching updates\n"
        "🎓 <b>My Qualification</b> — qualification profile बनाओ\n"
        "👨‍🏫 <b>Teaching Jobs</b> — TGT/PGT/TET/CTET/UPTET आदि\n"
        "🆕 <b>Latest Vacancies</b> — latest recruitment-related notices\n"
        "📢 <b>Latest Notices</b> — सभी latest notices\n"
        "🔔 <b>My Alerts</b> — followed exams\n"
        "🔎 <b>Search</b> — keyword से notice search\n"
        "💬 <b>Contact Admin</b> — admin को message भेजो\n\n"
        "⚠️ Official government source को primary माना जाता है. "
        "Educational/recruitment websites केवल discovery/cross-check के लिए हैं.\n\n"
        "ℹ️ Qualification matching अभी notice/title keywords पर आधारित है; "
        "official PDF की detailed eligibility को बाद के version में और मजबूत किया जा सकता है.",
        MAIN_KB,
    )


def show_profile(chat_id, user_id):
    profile = get_profile(user_id)
    qs = profile.get("qualifications", [])

    if qs:
        text = "🎓 <b>My Qualification</b>\n\n"
        text += "आपकी qualifications:\n"
        text += "\n".join(f"• {html.escape(q)}" for q in qs)
        text += "\n\nनई qualification जोड़ने के लिए नीचे चुनो."
    else:
        text = (
            "🎓 <b>My Qualification</b>\n\n"
            "अपनी qualification चुनो. Multiple qualifications चुन सकते हो."
        )

    send_message(chat_id, text, qualification_keyboard())


def find_jobs(chat_id, user_id):
    profile = get_profile(user_id)
    if not profile.get("qualifications"):
        send_message(
            chat_id,
            "🎓 पहले <b>My Qualification</b> में अपनी qualification save करो.",
            MAIN_KB,
        )
        return

    items = load_json(LATEST_FILE, [])
    matched = [x for x in items if qualification_matches(profile, x)]

    # Official first.
    matched.sort(key=lambda x: 0 if x.get("priority") == "official" else 1)

    show_results(
        chat_id,
        matched,
        "💼 <b>Your Matching Jobs / Notices</b>",
    )


def teaching_jobs(chat_id, user_id):
    profile = get_profile(user_id)
    items = load_json(LATEST_FILE, [])
    matched = [x for x in items if teaching_matches(profile, x)]
    matched.sort(key=lambda x: 0 if x.get("priority") == "official" else 1)

    show_results(
        chat_id,
        matched,
        "👨‍🏫 <b>Teaching Jobs & Exams</b>",
    )


def latest_vacancies(chat_id):
    items = load_json(LATEST_FILE, [])
    keys = [
        "vacancy", "recruitment", "notification", "advertisement",
        "apply", "application", "teacher", "tgt", "pgt", "cgl",
        "chsl", "ntpc", "pet", "group d", "result"
    ]
    matched = [x for x in items if any(k in notice_text(x) for k in keys)]
    matched.sort(key=lambda x: 0 if x.get("priority") == "official" else 1)

    show_results(chat_id, matched[:15], "🆕 <b>Latest Vacancies</b>")


def latest_notices(chat_id):
    items = load_json(LATEST_FILE, [])
    show_results(chat_id, items[:15], "📢 <b>Latest Notices</b>")


def my_alerts(chat_id, user_id):
    follows = get_follows()
    exams = follows.get(str(user_id), [])

    if not exams:
        send_message(
            chat_id,
            "🔔 अभी कोई exam follow नहीं किया है.\n\n"
            "📚 Exams → exam चुनो → Follow option इस्तेमाल करो.",
            MAIN_KB,
        )
        return

    text = "🔔 <b>My Alerts</b>\n\n"
    text += "\n".join(f"• {html.escape(x)}" for x in exams)
    send_message(chat_id, text, MAIN_KB)


def show_status(chat_id):
    seen = load_json(SEEN_FILE, [])
    latest = load_json(LATEST_FILE, [])
    users = load_users()
    follows = get_follows()

    follow_count = sum(len(v) for v in follows.values())

    send_message(
        chat_id,
        "📊 <b>Bot Status</b>\n\n"
        "🟢 Bot Online\n"
        "🌐 Webhook Mode\n"
        f"🏛️ Official Sources: {len(SOURCES)}\n"
        f"🔎 Secondary Sources: {len(SECONDARY_SOURCES)}\n"
        f"📚 Tracked Notices: {len(seen)}\n"
        f"📰 Latest Saved: {len(latest)}\n"
        f"👤 Users: {len(users)}\n"
        f"🔔 Active Follows: {follow_count}\n"
        f"⏱️ Scan Interval: {SCAN_INTERVAL // 60} min",
        MAIN_KB,
    )


# ------------------------------------------------------------
# SEARCH / FOLLOW FLOW
# ------------------------------------------------------------
SEARCH_WAITING = set()
PENDING_EXAM = {}
PENDING_BOARD = {}


def handle_exam_button(chat_id, user_id, text):
    # Board selection
    if text.startswith("🏛️ "):
        board = text.replace("🏛️ ", "", 1).strip()
        if board in EXAMS:
            PENDING_BOARD[user_id] = board
            show_board_exams(chat_id, board)
            return True

    # Exam selection
    if text.startswith("🔎 "):
        exam = text.replace("🔎 ", "", 1).strip()
        board = PENDING_BOARD.get(user_id)
        if board and exam in EXAMS.get(board, []):
            PENDING_EXAM[user_id] = exam
            rows = [
                ["📌 Notification", "📌 Application"],
                ["📌 Admit Card", "📌 Exam Date"],
                ["📌 Answer Key", "📌 Result"],
                ["📌 Cut Off", "📌 Vacancy"],
                ["📌 All Updates"],
                ["🔔 Follow Exam"],
                ["⬅️ Exams"],
            ]
            send_message(
                chat_id,
                f"🔎 <b>{html.escape(exam)}</b>\n\n"
                "क्या देखना है?",
                keyboard(rows),
            )
            return True

    return False


def handle_info_button(chat_id, user_id, text):
    exam = PENDING_EXAM.get(user_id)
    if not exam:
        return False

    if text == "🔔 Follow Exam":
        save_follow(user_id, exam)
        send_message(
            chat_id,
            f"🔔 <b>Exam Followed</b>\n\n"
            f"{html.escape(exam)}\n\n"
            "New matching updates पर alert मिलेगा.",
            MAIN_KB,
        )
        return True

    if text.startswith("📌 "):
        info = text.replace("📌 ", "", 1).strip()
        items = load_json(LATEST_FILE, [])

        matched = []
        for item in items:
            if not exam_matches(exam, item):
                continue
            if info != "All Updates":
                if info.lower() not in notice_text(item):
                    continue
            matched.append(item)

        show_results(
            chat_id,
            matched,
            f"🔎 <b>{html.escape(exam)}</b> — {html.escape(info)}",
        )
        return True

    return False


# ------------------------------------------------------------
# ADMIN
# ------------------------------------------------------------
def is_admin(user_id):
    return ADMIN_ID and str(user_id) == ADMIN_ID


def admin_broadcast(chat_id, text):
    users = load_users()
    count = 0

    for uid in users:
        send_message(uid, text)
        count += 1
        time.sleep(0.05)

    send_message(chat_id, f"📢 Broadcast sent to {count} users.", MAIN_KB)


def admin_poll(chat_id, text):
    # Telegram native poll.
    question = text.strip()
    if not question:
        question = "आप किस exam update को सबसे पहले चाहते हैं?"

    tg(
        "sendPoll",
        {
            "chat_id": chat_id,
            "question": question[:300],
            "options": json.dumps(
                ["Notification", "Vacancy", "Admit Card", "Result"],
                ensure_ascii=False,
            ),
            "is_anonymous": "false",
        },
    )


def forward_contact_to_admin(message):
    if not ADMIN_ID:
        return

    user = message.get("from", {})
    chat = message.get("chat", {})
    uid = user.get("id")

    text = message.get("text", "")
    header = (
        "💬 <b>User Message</b>\n\n"
        f"👤 {html.escape(user.get('first_name', ''))}\n"
        f"🆔 {uid}\n"
        f"💬 {html.escape(text)}\n\n"
        "↩️ Reply to this forwarded message to answer the user."
    )

    result = send_message(ADMIN_ID, header)

    # Also send original text with an explicit command-friendly format.
    send_message(
        ADMIN_ID,
        f"USER_ID: {uid}\n\n{text}",
    )


# ------------------------------------------------------------
# AUTOMATIC ALERTS
# ------------------------------------------------------------
def send_follow_alerts(new_items):
    follows = get_follows()
    sent = 0

    if not new_items:
        return

    for uid, exams in follows.items():
        for item in new_items:
            if sent >= MAX_ALERTS_PER_RUN:
                return

            if item.get("priority") != "official":
                # Secondary sources do not trigger automatic exam alerts.
                continue

            title = item.get("title", "")
            text = notice_text(item)

            matched_exam = None
            for exam in exams:
                if exam_matches(exam, item):
                    matched_exam = exam
                    break

            if matched_exam:
                send_message(
                    uid,
                    "🔔 <b>New Exam Update</b>\n\n"
                    f"📚 {html.escape(matched_exam)}\n\n"
                    + format_notice(item),
                    MAIN_KB,
                )
                sent += 1


def scanner_loop():
    # Wait a little after app startup.
    time.sleep(15)

    while True:
        try:
            new_items = scan_and_store()
            send_follow_alerts(new_items)
        except Exception as e:
            print("Scanner loop error:", e)

        time.sleep(SCAN_INTERVAL)


def scan_and_store():
    all_items = scan_all_sources()

    seen = load_json(SEEN_FILE, [])
    seen_set = set(seen)

    latest = load_json(LATEST_FILE, [])
    new_items = []

    # Official sources first.
    for item in all_items:
        item_id = item["id"]

        if item_id not in seen_set:
            new_items.append(item)
            seen.append(item_id)
            seen_set.add(item_id)

        latest = [x for x in latest if x.get("id") != item_id]
        latest.insert(0, item)

    latest = latest[:MAX_LATEST]
    seen = seen[-5000:]

    save_json(SEEN_FILE, seen)
    save_json(LATEST_FILE, latest)

    # Admin gets a compact digest of genuinely new official items.
    official_new = [
        x for x in new_items if x.get("priority") == "official"
    ][:MAX_ALERTS_PER_RUN]

    if official_new and ADMIN_ID:
        send_message(
            ADMIN_ID,
            f"🆕 <b>{len(official_new)} new official updates detected</b>",
            MAIN_KB,
        )
        for item in official_new:
            send_message(ADMIN_ID, format_notice(item), MAIN_KB)

    print(
        f"Scan complete: total={len(all_items)}, "
        f"new={len(new_items)}, official_new={len(official_new)}"
    )
    return new_items


# ------------------------------------------------------------
# UPDATE PROCESSOR
# ------------------------------------------------------------
def process_update(update):
    # Callback queries are intentionally not required for this version;
    # Reply keyboards make it easier to operate on mobile.
    if "callback_query" in update:
        answer_callback(update["callback_query"]["id"])
        return

    message = update.get("message")
    if not message:
        return

    user = message.get("from", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user_id = user.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not user_id:
        return

    save_user(user)

    # Admin commands
    if is_admin(user_id):
        if text.startswith("/broadcast "):
            admin_broadcast(chat_id, text[len("/broadcast "):].strip())
            return

        if text.startswith("/poll "):
            admin_poll(chat_id, text[len("/poll "):].strip())
            return

        # Admin reply flow: reply to a message containing USER_ID.
        if message.get("reply_to_message"):
            replied = message["reply_to_message"].get("text", "")
            m = re.search(r"USER_ID:\s*(\d+)", replied)
            if m:
                target_uid = m.group(1)
                send_message(
                    target_uid,
                    "📩 <b>Admin Reply</b>\n\n" + html.escape(text),
                    MAIN_KB,
                )
                send_message(chat_id, "✅ Reply sent.", MAIN_KB)
                return

    # Contact waiting
    contacts = get_contacts()
    if str(user_id) in contacts and text not in {
        "💬 Contact Admin",
        "⬅️ Main Menu",
    }:
        set_contact_waiting(user_id, False)
        forward_contact_to_admin(message)
        send_message(
            chat_id,
            "✅ आपका message admin को भेज दिया गया है.",
            MAIN_KB,
        )
        return

    # Search waiting
    if user_id in SEARCH_WAITING:
        SEARCH_WAITING.discard(user_id)
        results = search_items(text, limit=10)
        show_results(
            chat_id,
            results,
            f"🔎 <b>Search: {html.escape(text)}</b>",
        )
        return

    # Navigation
    if text == "/start" or text == "⬅️ Main Menu":
        start(chat_id, user)
        return

    if text == "📚 Exams":
        show_exams(chat_id)
        return

    if text == "💼 Find Jobs":
        find_jobs(chat_id, user_id)
        return

    if text == "🎓 My Qualification":
        show_profile(chat_id, user_id)
        return

    if text == "👨‍🏫 Teaching Jobs":
        teaching_jobs(chat_id, user_id)
        return

    if text == "🆕 Latest Vacancies":
        latest_vacancies(chat_id)
        return

    if text == "📢 Latest Notices":
        latest_notices(chat_id)
        return

    if text == "🔔 My Alerts":
        my_alerts(chat_id, user_id)
        return

    if text == "🔎 Search":
        SEARCH_WAITING.add(user_id)
        send_message(
            chat_id,
            "🔎 <b>Search</b>\n\n"
            "Exam / post / keyword लिखकर भेजो.\n"
            "उदाहरण: <code>CGL</code>, <code>teacher</code>, "
            "<code>NTPC</code>, <code>lekhpal</code>",
            MAIN_KB,
        )
        return

    if text == "📊 Status":
        show_status(chat_id)
        return

    if text == "❓ Help":
        help_text(chat_id)
        return

    if text == "💬 Contact Admin":
        set_contact_waiting(user_id, True)
        send_message(
            chat_id,
            "💬 अपना message लिखकर भेजो.\n\n"
            "मैं उसे admin तक पहुंचा दूँगा.",
            MAIN_KB,
        )
        return

    # Qualification selection
    if text in QUALIFICATIONS:
        update_qualification(user_id, text)
        profile = get_profile(user_id)
        send_message(
            chat_id,
            f"✅ <b>{html.escape(text)}</b> added.\n\n"
            "और qualification चुन सकते हो या Done दबाओ.",
            qualification_keyboard(),
        )
        return

    if text == "❌ Clear":
        clear_qualification(user_id)
        send_message(
            chat_id,
            "🗑️ Qualification profile clear कर दिया गया.",
            qualification_keyboard(),
        )
        return

    if text == "✅ Done":
        profile = get_profile(user_id)
        qs = profile.get("qualifications", [])
        send_message(
            chat_id,
            "🎓 <b>Profile Saved</b>\n\n"
            + (
                "\n".join(f"• {html.escape(q)}" for q in qs)
                if qs
                else "कोई qualification select नहीं हुई."
            )
            + "\n\nअब 💼 Find Jobs इस्तेमाल करो.",
            MAIN_KB,
        )
        return

    # Back buttons
    if text == "⬅️ Exams":
        show_exams(chat_id)
        return

    # Exam flow
    if handle_exam_button(chat_id, user_id, text):
        return

    if handle_info_button(chat_id, user_id, text):
        return

    # Natural language fallback
    if len(text) >= 3:
        results = search_items(text, limit=5)
        if results:
            show_results(
                chat_id,
                results,
                f"🔎 <b>Search: {html.escape(text)}</b>",
            )
            return

    send_message(
        chat_id,
        "🤔 यह option समझ नहीं आया.\n\n"
        "Menu से option चुनो या ❓ Help दबाओ.",
        MAIN_KB,
    )


# ------------------------------------------------------------
# FLASK WEBHOOK
# ------------------------------------------------------------
@app.get("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Government Job & Exam Assistant",
        "official_sources": len(SOURCES),
        "secondary_sources": len(SECONDARY_SOURCES),
    })


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/webhook")
def webhook():
    try:
        update = request.get_json(force=True, silent=True) or {}
        process_update(update)
        return jsonify({"ok": True})
    except Exception as e:
        print("Webhook error:", e)
        return jsonify({"ok": False, "error": str(e)}), 500


def set_webhook():
    if not BOT_TOKEN or not WEBHOOK_URL:
        print("BOT_TOKEN / WEBHOOK_URL missing; webhook not configured.")
        return

    url = f"{WEBHOOK_URL}/webhook"
    result = tg("setWebhook", {"url": url})
    print("Webhook:", result)


# ------------------------------------------------------------
# STARTUP
# ------------------------------------------------------------
if __name__ == "__main__":
    print("Starting Government Job & Exam Assistant...")
    print("Official sources:", len(SOURCES))
    print("Secondary sources:", len(SECONDARY_SOURCES))

    # Configure webhook before serving.
    set_webhook()

    # Background scanner.
    t = threading.Thread(target=scanner_loop, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=PORT)
