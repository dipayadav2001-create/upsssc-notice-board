import os
import json
import time
import html
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

MAX_ALERTS_PER_RUN = 10
MAX_LATEST = 10

SEEN_FILE = "seen.json"
LATEST_FILE = "latest.json"
OFFSET_FILE = ".telegram_offset"


# ============================================================
# OFFICIAL SOURCES
# ============================================================

SOURCES = {
    "UPSC": {
        "name": "UPSC",
        "url": "https://www.upsc.gov.in/",
        "keywords": [
            "exam",
            "examination",
            "notification",
            "advertisement",
            "recruitment",
            "result",
            "admit card",
            "answer key",
            "civil services",
            "nda",
            "cds",
            "capf",
            "ese",
            "cms",
            "ias",
            "ips",
            "ifs"
        ]
    },

    "SSC": {
        "name": "SSC",
        "url": "https://ssc.gov.in/",
        "keywords": [
            "notification",
            "examination",
            "exam",
            "result",
            "admit card",
            "answer key",
            "cgl",
            "chsl",
            "mts",
            "gd",
            "je",
            "stenographer",
            "selection post",
            "delhi police",
            "jht"
        ]
    },

    "RAILWAY": {
        "name": "Railway / RRB",
        "url": "https://indianrailways.gov.in/",
        "keywords": [
            "rrb",
            "railway",
            "recruitment",
            "cen",
            "notification",
            "exam",
            "result",
            "admit card",
            "answer key",
            "ntpc",
            "group d",
            "technician",
            "alp",
            "je",
            "rpf"
        ]
    },

    "UPSSSC": {
        "name": "UPSSSC",
        "url": "https://upsssc.gov.in/",
        "keywords": [
            "notification",
            "recruitment",
            "exam",
            "result",
            "admit card",
            "answer key",
            "pet",
            "junior assistant",
            "lekhpal",
            "enforcement",
            "stenographer",
            "forest guard",
            "vdo"
        ]
    },

    "BPSC": {
        "name": "BPSC",
        "url": "https://www.bpsc.bih.nic.in/",
        "keywords": [
            "notification",
            "recruitment",
            "exam",
            "result",
            "admit card",
            "answer key",
            "teacher",
            "bpsc",
            "70th",
            "71st",
            "72nd",
            "combined competitive",
            "assistant",
            "tre",
            "head teacher"
        ]
    }
}


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
    if BOT_TOKEN
    else None
)


def telegram_request(method, data=None, timeout=30):
    if not TELEGRAM_API:
        return None

    try:
        response = requests.post(
            f"{TELEGRAM_API}/{method}",
            data=data or {},
            timeout=timeout
        )

        if response.status_code != 200:
            print(
                f"Telegram error {response.status_code}: "
                f"{response.text[:500]}"
            )
            return None

        return response.json()

    except Exception as e:
        print(f"Telegram request error: {e}")
        return None


def send_message(chat_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    return telegram_request("sendMessage", data)


# ============================================================
# TELEGRAM KEYBOARDS
# ============================================================

def main_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🆕 New Notices"},
                {"text": "📚 Exams"}
            ],
            [
                {"text": "📊 Status"},
                {"text": "❓ Help"}
            ],
            [
                {"text": "🔔 All Updates"}
            ]
        ],
        "resize_keyboard": True
    }


def exam_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🇮🇳 UPSC", "callback_data": "EXAM_UPSC"},
                {"text": "📝 SSC", "callback_data": "EXAM_SSC"}
            ],
            [
                {"text": "🚆 Railway", "callback_data": "EXAM_RAILWAY"},
                {"text": "🟢 UPSSSC", "callback_data": "EXAM_UPSSSC"}
            ],
            [
                {"text": "🔵 BPSC", "callback_data": "EXAM_BPSC"}
            ],
            [
                {"text": "📢 All Exams", "callback_data": "EXAM_ALL"}
            ]
        ]
    }


# ============================================================
# FILE HANDLING
# ============================================================

def load_json(filename, default):
    try:
        if not os.path.exists(filename):
            return default

        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return default


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception as e:
        print(f"Error saving {filename}: {e}")


def load_seen():
    return set(load_json(SEEN_FILE, []))


def save_seen(seen):
    save_json(SEEN_FILE, sorted(list(seen)))


def load_latest():
    return load_json(LATEST_FILE, [])


def save_latest(latest):
    save_json(
        LATEST_FILE,
        latest[-MAX_LATEST:]
    )


def load_offset():
    try:
        if not os.path.exists(OFFSET_FILE):
            return None

        with open(OFFSET_FILE, "r") as f:
            return int(f.read().strip())

    except Exception:
        return None


def save_offset(offset):
    try:
        with open(OFFSET_FILE, "w") as f:
            f.write(str(offset))
    except Exception as e:
        print(f"Offset save error: {e}")


# ============================================================
# HTTP SESSION
# ============================================================

def make_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/120 Safari/537.36"
        )
    })

    return session


SESSION = make_session()


def fetch(url, timeout=30):
    try:
        response = SESSION.get(
            url,
            timeout=timeout,
            allow_redirects=True
        )

        response.raise_for_status()

        return response.text

    except Exception as e:
        print(f"Fetch failed: {url} -> {e}")
        return None


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(title, source_name):
    text = f"{title} {source_name}".lower()

    if source_name in SOURCES:
        return source_name

    if "upsssc" in text:
        return "UPSSSC"

    if "bpsc" in text:
        return "BPSC"

    if "ssc" in text:
        return "SSC"

    if "upsc" in text:
        return "UPSC"

    if "railway" in text or "rrb" in text:
        return "RAILWAY"

    return source_name


# ============================================================
# NOTICE FILTER
# ============================================================

def is_relevant(title, source):
    title_lower = title.lower()

    keywords = SOURCES[source]["keywords"]

    for keyword in keywords:
        if keyword.lower() in title_lower:
            return True

    return False


# ============================================================
# GENERIC PARSER
# ============================================================

def extract_generic_items(html_text, base_url, source_name):
    soup = BeautifulSoup(html_text, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):

        title = a.get_text(" ", strip=True)

        if not title:
            continue

        if len(title) < 8:
            continue

        href = a.get("href")

        if not href:
            continue

        url = urljoin(base_url, href)

        if not url.startswith("http"):
            continue

        if not is_relevant(title, source_name):
            continue

        items.append({
            "title": title[:300],
            "url": url,
            "source": source_name,
            "category": detect_category(
                title,
                source_name
            )
        })

    return items


# ============================================================
# SSC PARSER
# ============================================================

def extract_ssc_items(html_text, base_url):
    items = extract_generic_items(
        html_text,
        base_url,
        "SSC"
    )

    return items


# ============================================================
# UPSC PARSER
# ============================================================

def extract_upsc_items(html_text, base_url):
    items = extract_generic_items(
        html_text,
        base_url,
        "UPSC"
    )

    return items


# ============================================================
# RAILWAY PARSER
# ============================================================

def extract_railway_items(html_text, base_url):
    items = extract_generic_items(
        html_text,
        base_url,
        "RAILWAY"
    )

    return items


# ============================================================
# UPSSSC PARSER
# ============================================================

def extract_upsssc_items(html_text, base_url):
    items = extract_generic_items(
        html_text,
        base_url,
        "UPSSSC"
    )

    return items


# ============================================================
# BPSC PARSER
# ============================================================

def extract_bpsc_items(html_text, base_url):
    items = extract_generic_items(
        html_text,
        base_url,
        "BPSC"
    )

    return items


# ============================================================
# SCAN SOURCE
# ============================================================

def scan_source(source_key):
    source = SOURCES[source_key]

    html_text = fetch(source["url"])

    if not html_text:
        return []

    if source_key == "UPSC":
        return extract_upsc_items(
            html_text,
            source["url"]
        )

    if source_key == "SSC":
        return extract_ssc_items(
            html_text,
            source["url"]
        )

    if source_key == "RAILWAY":
        return extract_railway_items(
            html_text,
            source["url"]
        )

    if source_key == "UPSSSC":
        return extract_upsssc_items(
            html_text,
            source["url"]
        )

    if source_key == "BPSC":
        return extract_bpsc_items(
            html_text,
            source["url"]
        )

    return []


# ============================================================
# NOTICE FORMAT
# ============================================================

def format_notice(item):
    title = html.escape(
        item.get("title", "New Notice")
    )

    source = html.escape(
        item.get("source", "")
    )

    category = html.escape(
        item.get("category", "")
    )

    url = item.get("url", "")

    return (
        "🔔 <b>NEW GOVERNMENT JOB NOTICE</b>\n\n"
        f"📌 <b>{title}</b>\n\n"
        f"🏛️ Source: <b>{source}</b>\n"
        f"📚 Exam: <b>{category}</b>\n\n"
        f"🔗 <a href=\"{html.escape(url)}\">"
        "Official Notice</a>\n\n"
        "⚡ UPSSSC Notice Board"
    )


# ============================================================
# START COMMAND
# ============================================================

def send_start(chat_id):
    text = (
        "🙏 <b>नमस्ते!</b>\n\n"
        "🎓 <b>UPSSSC Notice Board</b> में आपका स्वागत है।\n\n"
        "मैं इन प्रमुख सरकारी भर्ती/exam sources "
        "की नई notifications track करता हूँ:\n\n"
        "🇮🇳 UPSC\n"
        "📝 SSC\n"
        "🚆 Railway / RRB\n"
        "🟢 UPSSSC\n"
        "🔵 BPSC\n\n"
        "🆕 <b>New Notices</b> दबाकर नई notifications देखें।\n"
        "📚 <b>Exams</b> से अपना exam चुनें।\n"
        "❓ <b>Help</b> से commands की जानकारी लें।\n\n"
        "👇 नीचे menu का उपयोग करें।"
    )

    send_message(
        chat_id,
        text,
        main_keyboard()
    )


# ============================================================
# HELP
# ============================================================

def send_help(chat_id):
    text = (
        "❓ <b>UPSSSC Notice Board - Help</b>\n\n"

        "🆕 <b>New Notices</b>\n"
        "→ हाल की नई government notifications\n\n"

        "📚 <b>Exams</b>\n"
        "→ UPSC / SSC / Railway / UPSSSC / BPSC चुनें\n\n"

        "📊 <b>Status</b>\n"
        "→ Bot monitoring status देखें\n\n"

        "🔔 <b>All Updates</b>\n"
        "→ सभी tracked exams के latest updates\n\n"

        "⌨️ <b>Commands</b>\n"
        "/start - Bot शुरू करें\n"
        "/help - Help menu\n"
        "/status - Monitoring status\n"
        "/latest - Latest notices\n"
        "/exams - Exam selection\n\n"

        "⏱️ Notice monitoring लगभग हर 5 मिनट में चलता है।"
    )

    send_message(
        chat_id,
        text,
        main_keyboard()
    )


# ============================================================
# STATUS
# ============================================================

def send_status(chat_id):
    seen = load_seen()
    latest = load_latest()

    text = (
        "📊 <b>Bot Status</b>\n\n"
        "🟢 Monitoring: <b>ACTIVE</b>\n"
        "⏱️ Scan interval: <b>5 minutes</b>\n\n"
        f"📌 Saved notices: <b>{len(seen)}</b>\n"
        f"🆕 Latest notices: <b>{len(latest)}</b>\n\n"
        "📡 Sources:\n"
        "🇮🇳 UPSC\n"
        "📝 SSC\n"
        "🚆 Railway / RRB\n"
        "🟢 UPSSSC\n"
        "🔵 BPSC"
    )

    send_message(
        chat_id,
        text,
        main_keyboard()
    )


# ============================================================
# LATEST NOTICES
# ============================================================

def send_latest(chat_id, category=None):
    latest = load_latest()

    if category and category != "ALL":
        latest = [
            x for x in latest
            if x.get("category") == category
        ]

    if not latest:
        send_message(
            chat_id,
            "ℹ️ अभी इस category में कोई saved notice नहीं मिला।",
            main_keyboard()
        )
        return

    lines = []

    heading = (
        "🆕 <b>Latest Notices</b>"
        if not category or category == "ALL"
        else f"🆕 <b>{html.escape(category)} Notices</b>"
    )

    lines.append(heading)
    lines.append("")

    for i, item in enumerate(
        reversed(latest[-MAX_LATEST:]),
        start=1
    ):
        title = html.escape(
            item.get("title", "")
        )

        url = item.get("url", "")

        source = html.escape(
            item.get("source", "")
        )

        lines.append(
            f"{i}. <b>{title}</b>\n"
            f"🏛️ {source}\n"
            f"🔗 <a href=\"{html.escape(url)}\">Open</a>\n"
        )

    send_message(
        chat_id,
        "\n".join(lines),
        main_keyboard()
    )


# ============================================================
# EXAM MENU
# ============================================================

def send_exam_menu(chat_id):
    send_message(
        chat_id,
        "📚 <b>Exam / Recruitment चुनें</b>\n\n"
        "जिस exam की notifications चाहिए उसे चुनें:",
        exam_keyboard()
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================

def answer_callback(callback_id):
    telegram_request(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id
        }
    )


def handle_callback(callback):
    callback_id = callback.get("id")

    if callback_id:
        answer_callback(callback_id)

    data = callback.get("data", "")

    message = callback.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")

    if not chat_id:
        return

    if data == "EXAM_UPSC":
        send_latest(chat_id, "UPSC")

    elif data == "EXAM_SSC":
        send_latest(chat_id, "SSC")

    elif data == "EXAM_RAILWAY":
        send_latest(chat_id, "RAILWAY")

    elif data == "EXAM_UPSSSC":
        send_latest(chat_id, "UPSSSC")

    elif data == "EXAM_BPSC":
        send_latest(chat_id, "BPSC")

    elif data == "EXAM_ALL":
        send_latest(chat_id, "ALL")


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_text(chat_id, text):

    text = text.strip()

    lower = text.lower()

    if lower.startswith("/start"):
        send_start(chat_id)
        return

    if lower.startswith("/help"):
        send_help(chat_id)
        return

    if lower.startswith("/status"):
        send_status(chat_id)
        return

    if lower.startswith("/latest"):
        send_latest(chat_id)
        return

    if lower.startswith("/exams"):
        send_exam_menu(chat_id)
        return

    if text == "🆕 New Notices":
        send_latest(chat_id)
        return

    if text == "📚 Exams":
        send_exam_menu(chat_id)
        return

    if text == "📊 Status":
        send_status(chat_id)
        return

    if text == "❓ Help":
        send_help(chat_id)
        return

    if text == "🔔 All Updates":
        send_latest(chat_id)
        return

    send_message(
        chat_id,
        "🤖 Command समझ नहीं आया।\n\n"
        "❓ Help दबाएँ या /help लिखें।",
        main_keyboard()
    )


# ============================================================
# TELEGRAM UPDATES
# ============================================================

def handle_commands():

    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return

    offset = load_offset()

    params = {
        "timeout": 1,
        "limit": 100
    }

    if offset is not None:
        params["offset"] = offset

    result = telegram_request(
        "getUpdates",
        params,
        timeout=10
    )

    if not result:
        return

    if not result.get("ok"):
        return

    updates = result.get("result", [])

    if not updates:
        return

    for update in updates:

        update_id = update.get("update_id")

        if update_id is not None:
            save_offset(update_id + 1)

        # -------------------------
        # CALLBACK
        # -------------------------

        if "callback_query" in update:
            callback = update["callback_query"]

            user = callback.get("from", {})
            user_id = str(user.get("id", ""))

            if ADMIN_ID and user_id != str(ADMIN_ID):
                answer_callback(
                    callback.get("id")
                )
                continue

            handle_callback(callback)
            continue

        # -------------------------
        # MESSAGE
        # -------------------------

        message = update.get("message")

        if not message:
            continue

        chat = message.get("chat", {})
        chat_id = chat.get("id")

        user = message.get("from", {})
        user_id = str(user.get("id", ""))

        if not chat_id:
            continue

        # ADMIN ONLY
        if ADMIN_ID and user_id != str(ADMIN_ID):
            send_message(
                chat_id,
                "⛔ यह bot केवल authorized admin के लिए है।"
            )
            continue

        text = message.get("text", "")

        if text:
            handle_text(
                chat_id,
                text
            )


# ============================================================
# SEND NEW NOTICE
# ============================================================

def send_new_notice(item):
    if not ADMIN_ID:
        print("ADMIN_ID missing")
        return False

    text = format_notice(item)

    result = send_message(
        ADMIN_ID,
        text
    )

    return bool(
        result and result.get("ok")
    )


# ============================================================
# MAIN MONITOR
# ============================================================

def main():

    print("=" * 60)
    print("UPSSSC NOTICE BOARD BOT")
    print("=" * 60)

    # First process Telegram commands
    handle_commands()

    seen = load_seen()
    latest = load_latest()

    all_new = []

    # --------------------------------------------------------
    # SCAN ALL SOURCES
    # --------------------------------------------------------

    for source_key in SOURCES:

        print(
            f"\nScanning {source_key}..."
        )

        try:
            items = scan_source(
                source_key
            )

            print(
                f"Found {len(items)} relevant items"
            )

        except Exception as e:
            print(
                f"Error scanning {source_key}: {e}"
            )
            continue

        for item in items:

            url = item.get("url")

            if not url:
                continue

            if url in seen:
                continue

            all_new.append(item)

    # --------------------------------------------------------
    # NEW NOTICES
    # --------------------------------------------------------

    print(
        f"\nTotal new notices: {len(all_new)}"
    )

    sent_count = 0

    for item in all_new:

        url = item.get("url")

        # Mark seen even if Telegram fails,
        # preventing repeated spam.
        seen.add(url)

        latest.append(item)

        if sent_count >= MAX_ALERTS_PER_RUN:
            continue

        try:

            success = send_new_notice(
                item
            )

            if success:
                sent_count += 1

                print(
                    f"Sent: {item.get('title')}"
                )

                time.sleep(1)

            else:
                print(
                    f"Telegram failed: "
                    f"{item.get('title')}"
                )

        except Exception as e:

            print(
                f"Send error: {e}"
            )

    # --------------------------------------------------------
    # SAVE DATA
    # --------------------------------------------------------

    save_seen(seen)

    save_latest(
        latest[-MAX_LATEST:]
    )

    print(
        f"\nSent this run: {sent_count}"
    )

    print("Monitoring completed.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
