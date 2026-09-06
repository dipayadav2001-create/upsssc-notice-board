import os
import json
import html
import hashlib
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None

MAX_LATEST = 50
MAX_ALERTS_PER_RUN = 10

SEEN_FILE = "seen.json"
LATEST_FILE = "latest.json"
USERS_FILE = "users.json"
FOLLOWS_FILE = "follows.json"
CONTACT_FILE = "contact_waiting.json"

# ============================================================
# OFFICIAL GOVERNMENT SOURCES
# ============================================================

SOURCES = {
    "UPSC": {
        "name": "UPSC",
        "url": "https://www.upsc.gov.in/whats-new",
        "home": "https://www.upsc.gov.in/"
    },
    "SSC": {
        "name": "SSC",
        "url": "https://ssc.gov.in/",
        "home": "https://ssc.gov.in/"
    },
    "RAILWAY": {
        "name": "Railway / RRB",
        "url": "https://rrb.indianrailways.gov.in/",
        "home": "https://www.rrcb.gov.in/rrbs.html"
    },
    "UPSSSC": {
        "name": "UPSSSC",
        "url": "https://upsssc.gov.in/",
        "home": "https://upsssc.gov.in/"
    },
    "BPSC": {
        "name": "BPSC",
        "url": "https://bpsc.bihar.gov.in/",
        "home": "https://bpsc.bihar.gov.in/"
    }
}

# ============================================================
# SPECIFIC EXAMS
# ============================================================

EXAMS = {
    "UPSC": [
        "Civil Services Examination (CSE)",
        "NDA",
        "CDS",
        "CAPF",
        "IES/ISS",
        "Engineering Services (ESE)",
        "CMS"
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
        "JHT"
    ],
    "RAILWAY": [
        "NTPC",
        "Group D",
        "ALP",
        "Technician",
        "JE",
        "RPF Constable",
        "RPF SI",
        "Paramedical"
    ],
    "UPSSSC": [
        "PET",
        "Junior Assistant",
        "VDO",
        "Stenographer",
        "Lekhpal",
        "Assistant Store Keeper",
        "Enforcement Constable"
    ],
    "BPSC": [
        "70th CCE",
        "71st CCE",
        "72nd CCE",
        "Teacher Recruitment",
        "TRE",
        "Head Teacher",
        "Assistant Engineer",
        "AEDO"
    ]
}

INFO_TYPES = [
    ("Notification", "NOTIFICATION"),
    ("Application / Apply", "APPLICATION"),
    ("Admit Card", "ADMIT"),
    ("Exam Date", "EXAMDATE"),
    ("Answer Key", "ANSWERKEY"),
    ("Result", "RESULT"),
    ("Cut Off", "CUTOFF"),
    ("Vacancy", "VACANCY"),
    ("All Updates", "ALL")
]

# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
})

# ============================================================
# STORAGE
# ============================================================

def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("load error", path, e)
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save error", path, e)


def load_seen():
    return set(load_json(SEEN_FILE, []))


def save_seen(value):
    save_json(SEEN_FILE, sorted(value))


def load_latest():
    return load_json(LATEST_FILE, [])


def save_latest(items):
    save_json(LATEST_FILE, items[-MAX_LATEST:])


def load_users():
    return load_json(USERS_FILE, {})


def save_user(chat_id, user):
    users = load_users()
    users[str(chat_id)] = {
        "chat_id": chat_id,
        "name": user.get("first_name", ""),
        "username": user.get("username", "")
    }
    save_json(USERS_FILE, users)


def load_follows():
    return load_json(FOLLOWS_FILE, {})


def save_follows(data):
    save_json(FOLLOWS_FILE, data)


def load_contact_waiting():
    return set(load_json(CONTACT_FILE, []))


def save_contact_waiting(data):
    save_json(CONTACT_FILE, sorted(data))

# ============================================================
# TELEGRAM API
# ============================================================

def telegram_request(method, data=None):
    if not TELEGRAM_API:
        print("BOT_TOKEN missing")
        return None

    try:
        response = requests.post(
            f"{TELEGRAM_API}/{method}",
            data=data or {},
            timeout=30
        )

        if response.status_code != 200:
            print(
                "Telegram error:",
                method,
                response.status_code,
                response.text[:500]
            )
            return None

        return response.json()

    except Exception as e:
        print("Telegram request error:", method, e)
        return None


def send_message(chat_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    if reply_markup:
        data["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False
        )

    return telegram_request("sendMessage", data)


def answer_callback(callback_id):
    if callback_id:
        telegram_request(
            "answerCallbackQuery",
            {"callback_query_id": callback_id}
        )

# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard():
    return {
        "keyboard": [
            [
                {"text": "📚 Exams"},
                {"text": "🆕 New Notices"}
            ],
            [
                {"text": "🔎 Search Exam"},
                {"text": "🔔 My Follows"}
            ],
            [
                {"text": "📊 Status"},
                {"text": "❓ Help"}
            ],
            [
                {"text": "💬 Contact Admin"}
            ]
        ],
        "resize_keyboard": True
    }


def exam_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🇮🇳 UPSC", "callback_data": "BOARD:UPSC"},
                {"text": "📝 SSC", "callback_data": "BOARD:SSC"}
            ],
            [
                {"text": "🚆 Railway / RRB", "callback_data": "BOARD:RAILWAY"},
                {"text": "🟢 UPSSSC", "callback_data": "BOARD:UPSSSC"}
            ],
            [
                {"text": "🔵 BPSC", "callback_data": "BOARD:BPSC"}
            ],
            [
                {"text": "📢 All Exams", "callback_data": "BOARD:ALL"}
            ]
        ]
    }


def make_exam_id(board, exam):
    # Short stable ID so callback_data stays well below Telegram's 64-byte limit.
    return hashlib.md5(
        f"{board}|{exam}".encode("utf-8")
    ).hexdigest()[:10]


def exam_from_id(board, exam_id):
    for exam in EXAMS.get(board, []):
        if make_exam_id(board, exam) == exam_id:
            return exam
    return None


def exam_list_keyboard(board):
    rows = []

    exams = EXAMS.get(board, [])

    for i in range(0, len(exams), 2):
        row = []

        for exam in exams[i:i + 2]:
            row.append({
                "text": exam,
                "callback_data": (
                    f"EXAM:{board}:{make_exam_id(board, exam)}"
                )
            })

        rows.append(row)

    rows.append([
        {
            "text": "🔙 Exams",
            "callback_data": "BACK:EXAMS"
        }
    ])

    return {"inline_keyboard": rows}


def info_keyboard(board, exam):
    exam_id = make_exam_id(board, exam)
    rows = []

    for i in range(0, len(INFO_TYPES), 2):
        row = []

        for label, code in INFO_TYPES[i:i + 2]:
            row.append({
                "text": label,
                "callback_data": (
                    f"INFO:{board}:{code}:{exam_id}"
                )
            })

        rows.append(row)

    rows.append([
        {
            "text": "🔔 Follow this Exam",
            "callback_data": f"FOLLOW:{board}:{exam_id}"
        }
    ])

    rows.append([
        {
            "text": "🔙 Back",
            "callback_data": f"BOARD:{board}"
        }
    ])

    return {"inline_keyboard": rows}

# ============================================================
# SCRAPING
# ============================================================

IMPORTANT = [
    "notification",
    "recruitment",
    "vacancy",
    "vacancies",
    "application",
    "apply online",
    "online application",
    "advertisement",
    "admit card",
    "admitcard",
    "hall ticket",
    "result",
    "final result",
    "written result",
    "merit list",
    "selection list",
    "cut off",
    "cutoff",
    "answer key",
    "answerkey",
    "response sheet",
    "exam date",
    "exam schedule",
    "examination schedule",
    "timetable",
    "important notice",
    "public notice",
    "revised notice",
    "document verification",
    "skill test",
    "typing test",
    "interview",
    "registration",
    "appointment"
]

BLOCKED = [
    "tender",
    "procurement",
    "litigation",
    "court case",
    "representation on question papers",
    "lateral recruitment",
    "departmental exam",
    "internal recruitment"
]


def clean(text):
    return " ".join((text or "").split())


def fetch(url):
    try:
        response = SESSION.get(
            url,
            timeout=25,
            allow_redirects=True
        )
        response.raise_for_status()
        return response.text
    except Exception as e:
        print("Fetch failed:", url, e)
        return None


def relevant(title):
    text = clean(title).lower()

    if len(text) < 8:
        return False

    if any(word in text for word in BLOCKED):
        return False

    return any(word in text for word in IMPORTANT)


def make_id(source, title, url):
    raw = f"{source}|{title}|{url}"
    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def detect_exam(board, title):
    text = title.lower()

    aliases = {
        "CGL": ["cgl", "combined graduate level"],
        "CHSL": ["chsl", "combined higher secondary"],
        "MTS": ["mts", "multi tasking"],
        "GD Constable": [
            "gd constable",
            "constable (gd)",
            "ssc gd"
        ],
        "CPO": ["cpo"],
        "JE": ["junior engineer", "ssc je", "rrb je"],
        "NTPC": ["ntpc"],
        "Group D": ["group d", "level 1"],
        "ALP": ["alp", "assistant loco"],
        "Technician": ["technician"],
        "PET": ["pet", "preliminary eligibility test"],
        "VDO": ["vdo", "village development officer"],
        "Junior Assistant": ["junior assistant"],
        "Lekhpal": ["lekhpal"],
        "70th CCE": ["70th cce", "70th combined"],
        "71st CCE": ["71st cce", "71st combined"],
        "72nd CCE": ["72nd cce", "72nd combined"],
        "Civil Services Examination (CSE)": [
            "civil services",
            "cse",
            "ias"
        ],
        "NDA": ["nda"],
        "CDS": ["cds"],
        "CAPF": ["capf"]
    }

    for exam, words in aliases.items():
        for word in words:
            if word in text:
                return exam

    return board


def extract_items(html_text, page_url, board):
    soup = BeautifulSoup(
        html_text,
        "html.parser"
    )

    source = SOURCES[board]
    items = []
    seen_urls = set()

    for anchor in soup.find_all(
        "a",
        href=True
    ):
        title = clean(
            anchor.get_text(
                " ",
                strip=True
            )
        )

        href = anchor.get(
            "href",
            ""
        ).strip()

        if not title or not href:
            continue

        if not relevant(title):
            continue

        url = urljoin(
            page_url,
            href
        )

        if not url.startswith("http"):
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        items.append({
            "id": make_id(
                board,
                title,
                url
            ),
            "source_key": board,
            "source": source["name"],
            "title": title[:350],
            "url": url,
            "exam": detect_exam(
                board,
                title
            )
        })

    return items


def scan_source(board):
    source = SOURCES[board]

    pages = [
        source["url"]
    ]

    if source["home"] not in pages:
        pages.append(source["home"])

    all_items = []

    for page in pages:
        text = fetch(page)

        if not text:
            continue

        try:
            all_items.extend(
                extract_items(
                    text,
                    page,
                    board
                )
            )
        except Exception as e:
            print(
                "Parse error:",
                board,
                e
            )

    unique = {}

    for item in all_items:
        unique[item["id"]] = item

    return list(unique.values())


def scan_all():
    all_items = []

    for board in SOURCES:
        try:
            all_items.extend(
                scan_source(board)
            )
        except Exception as e:
            print(
                "Scan error:",
                board,
                e
            )

    unique = {}

    for item in all_items:
        unique[item["id"]] = item

    items = list(unique.values())

    save_latest(
        items[-MAX_LATEST:]
    )

    return items

# ============================================================
# SEARCH / FILTER
# ============================================================

def info_words(code):
    return {
        "NOTIFICATION": [
            "notification",
            "advertisement"
        ],
        "APPLICATION": [
            "application",
            "apply",
            "registration"
        ],
        "ADMIT": [
            "admit",
            "hall ticket"
        ],
        "EXAMDATE": [
            "exam date",
            "schedule",
            "timetable"
        ],
        "ANSWERKEY": [
            "answer key",
            "answerkey",
            "response"
        ],
        "RESULT": [
            "result",
            "merit",
            "selection"
        ],
        "CUTOFF": [
            "cut off",
            "cutoff"
        ],
        "VACANCY": [
            "vacancy",
            "vacancies",
            "recruitment",
            "posts"
        ]
    }.get(code, [])


def matches_item(item, board, exam, code):
    if board != "ALL":
        if item.get("source_key") != board:
            return False

    if exam and exam != "ALL":
        wanted = exam.lower()
        title = item.get(
            "title",
            ""
        ).lower()

        detected = item.get(
            "exam",
            ""
        ).lower()

        if (
            wanted not in title
            and wanted not in detected
        ):
            return False

    if code != "ALL":
        title = item.get(
            "title",
            ""
        ).lower()

        if not any(
            word in title
            for word in info_words(code)
        ):
            return False

    return True


def search_updates(board, exam, code="ALL"):
    latest = load_latest()

    matches = [
        item
        for item in latest
        if matches_item(
            item,
            board,
            exam,
            code
        )
    ]

    if matches:
        return matches[-10:][::-1]

    # On-demand fresh scan if stored data has no match.
    boards = (
        list(SOURCES)
        if board == "ALL"
        else [board]
    )

    fresh = []

    for b in boards:
        fresh.extend(
            scan_source(b)
        )

    if fresh:
        merged = (
            latest + fresh
        )

        unique = {}

        for item in merged:
            unique[item["id"]] = item

        save_latest(
            list(unique.values())[-MAX_LATEST:]
        )

    matches = [
        item
        for item in fresh
        if matches_item(
            item,
            board,
            exam,
            code
        )
    ]

    return matches[-10:][::-1]

# ============================================================
# DISPLAY
# ============================================================

def format_item(item, index=None):
    prefix = (
        f"{index}. "
        if index
        else ""
    )

    title = html.escape(
        item.get(
            "title",
            "Notice"
        )
    )

    source = html.escape(
        item.get(
            "source",
            ""
        )
    )

    url = html.escape(
        item.get(
            "url",
            ""
        ),
        quote=True
    )

    return (
        f"{prefix}<b>{title}</b>\n"
        f"🏢 {source}\n"
        f"🔗 <a href=\"{url}\">Official Link</a>"
    )


def send_items(chat_id, items, heading):
    if not items:
        send_message(
            chat_id,
            (
                f"ℹ️ <b>{html.escape(heading)}</b>\n\n"
                "इस category में अभी matching notice नहीं मिला।\n\n"
                "Official website पर भी verify करें।"
            ),
            main_keyboard()
        )
        return

    text = (
        f"📢 <b>{html.escape(heading)}</b>\n\n"
        + "\n\n".join(
            format_item(
                item,
                i + 1
            )
            for i, item in enumerate(
                items[:10]
            )
        )
    )

    send_message(
        chat_id,
        text,
        main_keyboard()
    )

# ============================================================
# FOLLOWS
# ============================================================

def follow(chat_id, board, exam):
    data = load_follows()
    key = str(chat_id)

    data.setdefault(
        key,
        []
    )

    tag = f"{board}|{exam}"

    if tag not in data[key]:
        data[key].append(tag)
        save_follows(data)
        return True

    return False


def send_follows(chat_id):
    data = load_follows().get(
        str(chat_id),
        []
    )

    if not data:
        send_message(
            chat_id,
            (
                "🔔 <b>My Follows</b>\n\n"
                "अभी कोई exam follow नहीं किया है।\n\n"
                "📚 Exams → Board → Exam → "
                "🔔 Follow this Exam"
            ),
            main_keyboard()
        )
        return

    lines = [
        "🔔 <b>My Followed Exams</b>",
        ""
    ]

    for tag in data:
        try:
            board, exam = tag.split(
                "|",
                1
            )
        except ValueError:
            continue

        lines.append(
            f"• {html.escape(exam)} — "
            f"{html.escape(board)}"
        )

    lines.append(
        "\nNew matching updates मिलने पर "
        "bot alert भेजेगा।"
    )

    send_message(
        chat_id,
        "\n".join(lines),
        main_keyboard()
    )


def notify_followers(items):
    follows = load_follows()
    sent = 0

    for item in items:
        board = item.get(
            "source_key"
        )

        title = item.get(
            "title",
            ""
        ).lower()

        detected = item.get(
            "exam",
            ""
        ).lower()

        for uid, tags in follows.items():
            for tag in tags:
                try:
                    follow_board, exam = tag.split(
                        "|",
                        1
                    )
                except ValueError:
                    continue

                if follow_board != board:
                    continue

                wanted = exam.lower()

                # For known exams, title or detected exam must match.
                if (
                    wanted not in title
                    and wanted not in detected
                ):
                    continue

                result = send_message(
                    uid,
                    (
                        "🔔 <b>NEW MATCHING EXAM UPDATE</b>\n\n"
                        + format_item(item)
                    )
                )

                if result and result.get("ok"):
                    sent += 1

                break

    return sent

# ============================================================
# HELP / STATUS
# ============================================================

def send_help(chat_id):
    text = """🤖 <b>Government Exam Information Assistant</b>

यह bot UPSC, SSC, Railway/RRB, UPSSSC और BPSC के official sources से exam updates खोजने में मदद करता है।

<b>आप देख सकते हैं:</b>
• Notification
• Application / Apply
• Admit Card
• Exam Date
• Answer Key
• Result
• Cut Off
• Vacancy
• All Updates

<b>📚 Exams</b>
Board → Specific Exam → Information Type चुनें।

<b>🔎 Search Exam</b>
CGL, CHSL, MTS, PET, NTPC जैसे exam नाम search करें।

<b>🔔 Follow</b>
अपने exam को follow करके matching updates के alerts पाएँ।

<b>💬 Contact Admin</b>
Admin को message भेजने के लिए इसका उपयोग करें।

⚠️ आवेदन, फीस और तारीख से पहले official notice जरूर verify करें।"""

    send_message(
        chat_id,
        text,
        main_keyboard()
    )


def send_status(chat_id):
    seen = load_seen()
    latest = load_latest()
    users = load_users()
    follows = load_follows()

    followed_count = sum(
        len(value)
        for value in follows.values()
    )

    text = (
        "📊 <b>BOT STATUS</b>\n\n"
        "🟢 Bot: Online\n"
        "⚡ Telegram: Webhook Mode\n"
        f"📚 Official Boards: {len(SOURCES)}\n"
        f"🔎 Tracked Notices: {len(seen)}\n"
        f"🆕 Latest Saved: {len(latest)}\n"
        f"👥 Users: {len(users)}\n"
        f"🔔 Follows: {followed_count}"
    )

    send_message(
        chat_id,
        text,
        main_keyboard()
    )

# ============================================================
# ADMIN CONTACT / BROADCAST / POLL
# ============================================================

def contact_admin(chat_id):
    waiting = load_contact_waiting()

    waiting.add(
        str(chat_id)
    )

    save_contact_waiting(
        waiting
    )

    send_message(
        chat_id,
        (
            "💬 <b>Contact Admin</b>\n\n"
            "अपना message अगली message में भेजें।\n"
            "मैं उसे admin तक forward कर दूँगा।\n\n"
            "❌ Cancel करने के लिए /cancel भेजें।"
        ),
        main_keyboard()
    )


def forward_user_message(message):
    if not ADMIN_ID:
        return False

    chat_id = message.get(
        "chat",
        {}
    ).get("id")

    if not chat_id:
        return False

    waiting = load_contact_waiting()

    if str(chat_id) not in waiting:
        return False

    if message.get("text") == "/cancel":
        waiting.discard(
            str(chat_id)
        )

        save_contact_waiting(
            waiting
        )

        send_message(
            chat_id,
            "ठीक है 👍",
            main_keyboard()
        )

        return True

    result = telegram_request(
        "forwardMessage",
        {
            "chat_id": ADMIN_ID,
            "from_chat_id": chat_id,
            "message_id": message.get(
                "message_id"
            )
        }
    )

    if result and result.get("ok"):
        waiting.discard(
            str(chat_id)
        )

        save_contact_waiting(
            waiting
        )

        send_message(
            chat_id,
            (
                "✅ आपका message admin को भेज दिया गया है।\n"
                "Admin reply आने पर आपको भेज दिया जाएगा।"
            ),
            main_keyboard()
        )

    return True


def admin_reply_to_forward(message):
    if not ADMIN_ID:
        return False

    chat_id = message.get(
        "chat",
        {}
    ).get("id")

    if str(chat_id) != str(ADMIN_ID):
        return False

    reply = message.get(
        "reply_to_message"
    )

    if not reply:
        return False

    origin = reply.get(
        "forward_origin"
    )

    if not origin:
        origin = reply.get(
            "forward_from"
        )

    if not isinstance(
        origin,
        dict
    ):
        return False

    user_id = origin.get(
        "sender_user",
        {}
    ).get("id")

    if not user_id:
        user_id = origin.get(
            "id"
        )

    if not user_id:
        return False

    text = message.get(
        "text"
    )

    if not text:
        return False

    result = send_message(
        user_id,
        (
            "📩 <b>Admin Reply</b>\n\n"
            + html.escape(text)
        ),
        main_keyboard()
    )

    if result and result.get("ok"):
        send_message(
            ADMIN_ID,
            "✅ Reply user को भेज दिया गया।"
        )

    return True


def admin_broadcast(text):
    users = load_users()
    sent = 0

    for uid in users:
        result = send_message(
            uid,
            (
                "📢 <b>Admin Announcement</b>\n\n"
                + html.escape(text)
            ),
            main_keyboard()
        )

        if result and result.get("ok"):
            sent += 1

    return sent


def admin_poll(command):
    # /poll Question | Option 1 | Option 2 | ...
    body = command[5:].strip()

    parts = [
        part.strip()
        for part in body.split("|")
        if part.strip()
    ]

    if len(parts) < 3:
        return (
            "❌ Format:\n"
            "/poll Question | Option 1 | Option 2"
        )

    question = parts[0]
    options = parts[1:11]

    users = load_users()
    sent = 0

    for uid in users:
        result = telegram_request(
            "sendPoll",
            {
                "chat_id": uid,
                "question": question[:300],
                "options": json.dumps(
                    options,
                    ensure_ascii=False
                ),
                "is_anonymous": True
            }
        )

        if result and result.get("ok"):
            sent += 1

    return f"📊 Poll sent to {sent} users."

# ============================================================
# NEW NOTICES / ALL UPDATES
# ============================================================

def new_notices(chat_id):
    items = load_latest()

    if not items:
        items = scan_all()

    send_items(
        chat_id,
        items[-10:][::-1],
        "Latest Government Exam Notices"
    )


def all_updates(chat_id):
    items = scan_all()

    send_items(
        chat_id,
        items[-10:][::-1],
        "All Latest Government Exam Updates"
    )

# ============================================================
# CALLBACK HANDLER
# ============================================================

def process_callback(query):
    answer_callback(
        query.get("id")
    )

    data = query.get(
        "data",
        ""
    )

    chat_id = query.get(
        "message",
        {}
    ).get(
        "chat",
        {}
    ).get("id")

    if not chat_id:
        return

    if data == "BACK:EXAMS":
        send_message(
            chat_id,
            "📚 <b>Select Exam Board</b>",
            exam_keyboard()
        )
        return

    if data.startswith("BOARD:"):
        board = data.split(
            ":",
            1
        )[1]

        if board == "ALL":
            all_updates(chat_id)
            return

        send_message(
            chat_id,
            (
                f"📚 <b>{html.escape(SOURCES[board]['name'])}</b>\n\n"
                "अपना specific exam चुनें:"
            ),
            exam_list_keyboard(board)
        )
        return

    if data.startswith("EXAM:"):
        parts = data.split(
            ":",
            2
        )

        if len(parts) != 3:
            return

        _, board, exam_id = parts

        exam = exam_from_id(
            board,
            exam_id
        )

        if not exam:
            send_message(
                chat_id,
                "❌ Exam information नहीं मिली।",
                main_keyboard()
            )
            return

        send_message(
            chat_id,
            (
                f"📌 <b>{html.escape(exam)}</b>\n\n"
                "क्या जानकारी चाहिए?"
            ),
            info_keyboard(
                board,
                exam
            )
        )
        return

    if data.startswith("INFO:"):
        parts = data.split(
            ":",
            3
        )

        if len(parts) != 4:
            return

        _, board, code, exam_id = parts

        exam = exam_from_id(
            board,
            exam_id
        )

        if not exam:
            return

        items = search_updates(
            board,
            exam,
            code
        )

        label = next(
            (
                label
                for label, value
                in INFO_TYPES
                if value == code
            ),
            code
        )

        send_items(
            chat_id,
            items,
            f"{exam} — {label}"
        )
        return

    if data.startswith("FOLLOW:"):
        parts = data.split(
            ":",
            2
        )

        if len(parts) != 3:
            return

        _, board, exam_id = parts

        exam = exam_from_id(
            board,
            exam_id
        )

        if not exam:
            return

        changed = follow(
            chat_id,
            board,
            exam
        )

        if changed:
            text = (
                "🔔 <b>Exam Followed</b>\n\n"
                f"{html.escape(exam)}\n\n"
                "New matching updates पर alert मिलेगा।"
            )
        else:
            text = (
                "ℹ️ <b>Already Following</b>\n\n"
                f"{html.escape(exam)}"
            )

        send_message(
            chat_id,
            text,
            main_keyboard()
        )

# ============================================================
# FREE TEXT SEARCH
# ============================================================

def free_text_search(chat_id, text):
    q = text.lower()

    exam_terms = [
        ("cgl", "CGL"),
        ("chsl", "CHSL"),
        ("mts", "MTS"),
        ("ssc gd", "GD Constable"),
        ("cpo", "CPO"),
        ("ntpc", "NTPC"),
        ("group d", "Group D"),
        ("alp", "ALP"),
        ("technician", "Technician"),
        ("upsssc pet", "PET"),
        ("pet", "PET"),
        ("vdo", "VDO"),
        ("lekhpal", "Lekhpal"),
        ("nda", "NDA"),
        ("cds", "CDS"),
        ("capf", "CAPF"),
        ("civil services", "Civil Services Examination (CSE)"),
        ("upsc cse", "Civil Services Examination (CSE)"),
        ("70th cce", "70th CCE"),
        ("71st cce", "71st CCE"),
        ("72nd cce", "72nd CCE")
    ]

    selected_exam = None

    for keyword, exam in exam_terms:
        if keyword in q:
            selected_exam = exam
            break

    board = None

    if "upsssc" in q:
        board = "UPSSSC"
    elif "bpsc" in q:
        board = "BPSC"
    elif "upsc" in q:
        board = "UPSC"
    elif "ssc" in q:
        board = "SSC"
    elif "railway" in q or "rrb" in q:
        board = "RAILWAY"

    if selected_exam:
        if board is None:
            for b, exams in EXAMS.items():
                if selected_exam in exams:
                    board = b
                    break

        if board:
            items = search_updates(
                board,
                selected_exam,
                "ALL"
            )

            if items:
                send_items(
                    chat_id,
                    items,
                    f"{selected_exam} — Latest Updates"
                )
                return

    # Generic word search in stored notices.
    latest = load_latest()

    words = [
        word
        for word in q.split()
        if len(word) >= 3
    ]

    matches = []

    for item in latest:
        title = item.get(
            "title",
            ""
        ).lower()

        if words and all(
            word in title
            for word in words
        ):
            matches.append(item)

    if matches:
        send_items(
            chat_id,
            matches[-10:][::-1],
            f"Search: {text}"
        )
    else:
        send_message(
            chat_id,
            (
                "🔎 <b>कोई matching update नहीं मिला।</b>\n\n"
                "उदाहरण:\n"
                "• SSC CGL\n"
                "• SSC CHSL admit card\n"
                "• UPSSSC PET\n"
                "• Railway NTPC\n"
                "• UPSC CSE result\n"
                "• BPSC 72nd CCE"
            ),
            main_keyboard()
        )

# ============================================================
# MESSAGE HANDLER
# ============================================================

def process_message(message):
    chat_id = message.get(
        "chat",
        {}
    ).get("id")

    if not chat_id:
        return

    user = message.get(
        "from",
        {}
    )

    save_user(
        chat_id,
        user
    )

    text = clean(
        message.get(
            "text",
            ""
        )
    )

    # Admin functions.
    if (
        ADMIN_ID
        and str(chat_id) == str(ADMIN_ID)
    ):
        if admin_reply_to_forward(message):
            return

        if text.startswith("/broadcast "):
            sent = admin_broadcast(
                text[len("/broadcast "):]
            )

            send_message(
                chat_id,
                f"📢 Broadcast sent: {sent}"
            )
            return

        if text.startswith("/poll "):
            send_message(
                chat_id,
                admin_poll(text)
            )
            return

    # Contact flow must be checked before generic search.
    if text == "/cancel":
        waiting = load_contact_waiting()

        waiting.discard(
            str(chat_id)
        )

        save_contact_waiting(
            waiting
        )

        send_message(
            chat_id,
            "ठीक है 👍",
            main_keyboard()
        )
        return

    if forward_user_message(message):
        return

    if text in [
        "/start",
        "start"
    ]:
        send_message(
            chat_id,
            (
                "🇮🇳 <b>Government Exam Information Assistant</b>\n\n"
                "नमस्ते! 👋\n"
                "अपना exam चुनें या सीधे search करें।"
            ),
            main_keyboard()
        )

    elif text in [
        "📚 Exams",
        "Exams"
    ]:
        send_message(
            chat_id,
            "📚 <b>Select Exam Board</b>",
            exam_keyboard()
        )

    elif text == "🆕 New Notices":
        new_notices(
            chat_id
        )

    elif text == "🔎 Search Exam":
        send_message(
            chat_id,
            (
                "🔎 <b>Exam Search</b>\n\n"
                "Exam का नाम/type करें, जैसे:\n"
                "• SSC CGL\n"
                "• SSC CHSL\n"
                "• MTS\n"
                "• UPSSSC PET\n"
                "• Railway NTPC\n"
                "• UPSC CSE\n"
                "• BPSC 72nd CCE"
            ),
            main_keyboard()
        )

    elif text == "🔔 My Follows":
        send_follows(
            chat_id
        )

    elif text == "📊 Status":
        send_status(
            chat_id
        )

    elif text == "❓ Help":
        send_help(
            chat_id
        )

    elif text == "💬 Contact Admin":
        contact_admin(
            chat_id
        )

    elif text == "🔔 All Updates":
        all_updates(
            chat_id
        )

    elif text.startswith("/"):
        send_message(
            chat_id,
            "❓ Unknown command. /start दबाएँ।",
            main_keyboard()
        )

    else:
        free_text_search(
            chat_id,
            text
        )

# ============================================================
# WEBHOOK / APP COMPATIBILITY
# ============================================================

def handle_update(update):
    process_update(update)


def process_update(update):
    if "callback_query" in update:
        process_callback(
            update["callback_query"]
        )
    elif "message" in update:
        process_message(
            update["message"]
        )

# ============================================================
# BACKGROUND SCANNER
# ============================================================

def scan_and_notify():
    seen = load_seen()

    fresh = scan_all()

    new_items = [
        item
        for item in fresh
        if item["id"] not in seen
    ]

    for item in new_items:
        seen.add(
            item["id"]
        )

    save_seen(
        seen
    )

    if not new_items:
        return []

    limited = new_items[
        :MAX_ALERTS_PER_RUN
    ]

    # Alert users who follow a matching exam.
    notify_followers(
        limited
    )

    # Admin gets every detected new item for review.
    if ADMIN_ID:
        for item in limited:
            send_message(
                ADMIN_ID,
                (
                    "🚨 <b>NEW GOVERNMENT EXAM NOTICE</b>\n\n"
                    + format_item(item)
                )
            )

    return new_items


if __name__ == "__main__":
    print("bot.py loaded successfully")
