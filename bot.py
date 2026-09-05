import os
import json
import html
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

MAX_ALERTS_PER_RUN = 10
MAX_LATEST = 20

SEEN_FILE = "seen.json"
LATEST_FILE = "latest.json"


# ============================================================
# OFFICIAL GOVERNMENT SOURCES
# ============================================================

SOURCES = {
    "UPSC": {
        "name": "UPSC",
        "url": "https://www.upsc.gov.in/"
    },

    "SSC": {
        "name": "SSC",
        "url": "https://ssc.gov.in/"
    },

    "RAILWAY": {
        "name": "Railway / RRB",
        "url": "https://indianrailways.gov.in/"
    },

    "UPSSSC": {
        "name": "UPSSSC",
        "url": "https://upsssc.gov.in/"
    },

    "BPSC": {
        "name": "BPSC",
        "url": "https://www.bpsc.bih.nic.in/"
    }
}


# ============================================================
# IMPORTANT NOTICE KEYWORDS
# ============================================================

IMPORTANT_KEYWORDS = [
    "notification",
    "recruitment",
    "vacancy",
    "vacancies",
    "application",
    "apply online",
    "online application",
    "advertisement",

    "exam",
    "examination",
    "exam date",
    "exam schedule",
    "examination schedule",
    "timetable",
    "time table",

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
    "provisional answer key",
    "final answer key",

    "correction",
    "correction window",
    "application status",

    "important notice",
    "public notice",
    "revised notice",
    "revised schedule",

    "document verification",
    "skill test",
    "typing test",
    "interview",

    "eligibility",
    "syllabus",
    "fee",
    "registration",
    "registration date",
    "appointment"
]


# ============================================================
# BLOCKED TITLES
# ============================================================

BLOCKED_EXACT_TITLES = [
    "advertisements",
    "recruitment",
    "recruitment tests",
    "recruitment requisition",
    "status of recruitment cases",
    "status of recruitment cases (advertisement-wise)",
    "representation on question papers",
    "recruitment cases kept on hold on account of pending litigations",
    "lateral recruitment cases",
    "status of lateral recruitment cases",
    "news",
    "events",
    "tenders",
    "press releases",
    "what's new",
    "whats new"
]


BLOCKED_KEYWORDS = [
    "representation on question papers",
    "recruitment requisition",
    "pending litigation",
    "litigation cases",
    "court case",
    "court cases",
    "recruitment cases kept on hold",
    "status of recruitment cases",
    "advertisement-wise status",
    "lateral recruitment cases",
    "departmental",
    "internal"
]


# ============================================================
# TELEGRAM API
# ============================================================

TELEGRAM_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
    if BOT_TOKEN
    else None
)


def telegram_request(method, data=None, timeout=30):

    if not TELEGRAM_API:
        print("BOT_TOKEN missing")
        return None

    try:

        response = requests.post(
            f"{TELEGRAM_API}/{method}",
            data=data or {},
            timeout=timeout
        )

        if response.status_code != 200:

            print(
                "Telegram error:",
                response.status_code,
                response.text[:500]
            )

            return None

        return response.json()

    except Exception as e:

        print("Telegram request error:", e)

        return None


# ============================================================
# SEND TELEGRAM MESSAGE
# ============================================================

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

    return telegram_request(
        "sendMessage",
        data
    )


# ============================================================
# MAIN MENU
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


# ============================================================
# EXAM MENU
# ============================================================

def exam_keyboard():

    return {
        "inline_keyboard": [

            [
                {
                    "text": "🇮🇳 UPSC",
                    "callback_data": "EXAM_UPSC"
                },

                {
                    "text": "📝 SSC",
                    "callback_data": "EXAM_SSC"
                }
            ],

            [
                {
                    "text": "🚆 Railway",
                    "callback_data": "EXAM_RAILWAY"
                },

                {
                    "text": "🟢 UPSSSC",
                    "callback_data": "EXAM_UPSSSC"
                }
            ],

            [
                {
                    "text": "🔵 BPSC",
                    "callback_data": "EXAM_BPSC"
                }
            ],

            [
                {
                    "text": "📢 All Exams",
                    "callback_data": "EXAM_ALL"
                }
            ]

        ]
    }


# ============================================================
# JSON STORAGE
# ============================================================

def load_json(filename, default):

    try:

        if not os.path.exists(filename):
            return default

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(
            f"Error loading {filename}:",
            e
        )

        return default


def save_json(filename, data):

    try:

        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:

        print(
            f"Error saving {filename}:",
            e
        )


# ============================================================
# SEEN NOTICES
# ============================================================

def load_seen():

    return set(
        load_json(
            SEEN_FILE,
            []
        )
    )


def save_seen(seen):

    save_json(
        SEEN_FILE,
        sorted(list(seen))
    )


# ============================================================
# LATEST NOTICES
# ============================================================

def load_latest():

    return load_json(
        LATEST_FILE,
        []
    )


def save_latest(latest):

    save_json(
        LATEST_FILE,
        latest[-MAX_LATEST:]
    )


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({

    "User-Agent":
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"

})


# ============================================================
# FETCH WEBSITE
# ============================================================

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

        print(
            f"Fetch failed: {url}"
        )

        print(e)

        return None


# ============================================================
# NOTICE FILTER
# ============================================================

def is_relevant(title, source):

    title_clean = " ".join(
        title.lower().split()
    )

    # Block exact unwanted pages
    if title_clean in BLOCKED_EXACT_TITLES:
        return False

    # Block unwanted categories
    for keyword in BLOCKED_KEYWORDS:

        if keyword in title_clean:
            return False

    # Generic website links
    generic_titles = [

        "home",
        "about us",
        "contact us",
        "login",
        "sitemap",
        "gallery",
        "archive",
        "downloads",
        "links",
        "feedback",
        "careers"

    ]

    if title_clean in generic_titles:
        return False

    # Important notice keywords
    for keyword in IMPORTANT_KEYWORDS:

        if keyword in title_clean:
            return True

    return False


# ============================================================
# DETECT EXAM CATEGORY
# ============================================================

def detect_category(title, source):

    text = f"{title} {source}".lower()

    if "upsssc" in text:
        return "UPSSSC"

    if "bpsc" in text:
        return "BPSC"

    if "upsc" in text:
        return "UPSC"

    if "ssc" in text:
        return "SSC"

    if "railway" in text or "rrb" in text:
        return "RAILWAY"

    return source


# ============================================================
# EXTRACT NOTICE LINKS
# ============================================================

def extract_generic_items(
    html_text,
    base_url,
    source_name
):

    soup = BeautifulSoup(
        html_text,
        "html.parser"
    )

    items = []

    seen_urls = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        title = a.get_text(
            " ",
            strip=True
        )

        if not title:
            continue

        title = " ".join(
            title.split()
        )

        if len(title) < 8:
            continue

        href = a.get("href")

        if not href:
            continue

        url = urljoin(
            base_url,
            href
        )

        if not url.startswith("http"):
            continue

        if url in seen_urls:
            continue

        if not is_relevant(
            title,
            source_name
        ):
            continue

        seen_urls.add(url)

        items.append({

            "title": title[:300],

            "url": url,

            "source": source_name,

            "category":
                detect_category(
                    title,
                    source_name
                )

        })

    return items


# ============================================================
# SCAN ONE SOURCE
# ============================================================

def scan_source(source_key):

    source = SOURCES[source_key]

    html_text = fetch(
        source["url"]
    )

    if not html_text:
        return []

    return extract_generic_items(
        html_text,
        source["url"],
        source["name"]
    )


# ============================================================
# FORMAT NOTICE
# ============================================================

def format_notice(item):

    title = html.escape(
        item.get(
            "title",
            "New Notice"
        )
    )

    source = html.escape(
        item.get(
            "source",
            "Unknown"
        )
    )

    category = html.escape(
        item.get(
            "category",
            source
        )
    )

    url = item.get(
        "url",
        ""
    )

    safe_url = html.escape(
        url,
        quote=True
    )

    return (

        "🔔 <b>NEW GOVERNMENT EXAM NOTICE</b>\n\n"

        f"📚 <b>Exam:</b> {category}\n"

        f"🏢 <b>Source:</b> {source}\n\n"

        f"📌 <b>{title}</b>\n\n"

        f"🔗 <a href=\"{safe_url}\">"
        "Open Official Notice"
        "</a>"

    )


# ============================================================
# SEND NEW NOTICE
# ============================================================

def send_new_notice(item):

    if not ADMIN_ID:

        print(
            "ADMIN_ID missing"
        )

        return False

    result = send_message(
        ADMIN_ID,
        format_notice(item)
    )

    return bool(
        result
        and result.get("ok")
    )


# ============================================================
# HELP
# ============================================================

def send_help(chat_id):

    text = """

🤖 <b>Government Exam Notice Board</b>

यह bot official government exam websites से important notices track करता है।

<b>📚 Available Exams</b>

🇮🇳 UPSC
📝 SSC
🚆 Railway / RRB
🟢 UPSSSC
🔵 BPSC

<b>👇 Options</b>

🆕 <b>New Notices</b>
Latest available notices देखें।

📚 <b>Exams</b>
अपना exam select करें।

📊 <b>Status</b>
Bot की monitoring स्थिति देखें।

🔔 <b>All Updates</b>
सभी available latest updates देखें।

❓ <b>Help</b>
Bot का उपयोग समझें।

<b>⏱ Monitoring</b>

Government exam websites automatically scan की जाती हैं।

"""

    send_message(
        chat_id,
        text,
        main_keyboard()
    )


# ============================================================
# STATUS
# ============================================================

def send_status(chat_id):

    latest = load_latest()

    seen = load_seen()

    text = (

        "📊 <b>BOT STATUS</b>\n\n"

        "🟢 <b>Bot:</b> Online\n"

        "⚡ <b>Telegram:</b> Webhook Mode\n\n"

        f"📚 <b>Sources:</b> "
        f"{len(SOURCES)}\n"

        f"🔎 <b>Tracked Notices:</b> "
        f"{len(seen)}\n"

        f"🆕 <b>Latest Saved:</b> "
        f"{len(latest)}\n\n"

        "🌐 <b>Official Sources</b>\n\n"

        "• UPSC\n"
        "• SSC\n"
        "• Railway / RRB\n"
        "• UPSSSC\n"
        "• BPSC"

    )

    send_message(
        chat_id,
        text,
        main_keyboard()
    )


# ============================================================
# LATEST NOTICES
# ============================================================

def send_latest(
    chat_id,
    category=None
):

    latest = load_latest()

    if category and category != "ALL":

        latest = [

            item
            for item in latest

            if item.get(
                "category"
            ) == category

        ]

    if not latest:

        send_message(

            chat_id,

            "📭 <b>No notices found.</b>\n\n"
            "नई notices आने पर यहाँ दिखाई देंगी।",

            main_keyboard()

        )

        return

    latest = latest[-10:]

    lines = [
        "🆕 <b>LATEST NOTICES</b>\n"
    ]

    for index, item in enumerate(
        reversed(latest),
        start=1
    ):

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

        lines.append(

            f"{index}. <b>{source}</b>\n"
            f"{title}\n"
            f"🔗 <a href=\"{url}\">"
            "Open Notice"
            "</a>\n"

        )

    send_message(
        chat_id,
        "\n".join(lines),
        main_keyboard()
    )


# ============================================================
# TEXT COMMAND HANDLER
# ============================================================

def handle_text(
    chat_id,
    text
):

    text = text.strip()

    # /start
    if text.startswith("/start"):

        send_message(

            chat_id,

            "👋 <b>नमस्ते!</b>\n\n"

            "🎯 <b>Government Exam Notice Board</b> "
            "में आपका स्वागत है।\n\n"

            "मैं इन official exam websites को monitor करता हूँ:\n\n"

            "🇮🇳 UPSC\n"
            "📝 SSC\n"
            "🚆 Railway / RRB\n"
            "🟢 UPSSSC\n"
            "🔵 BPSC\n\n"

            "नीचे menu से option चुनें 👇",

            main_keyboard()

        )

        return

    # /help
    if (
        text.startswith("/help")
        or text == "❓ Help"
    ):

        send_help(chat_id)

        return

    # Exams
    if (
        text == "📚 Exams"
        or text.startswith("/exams")
    ):

        send_message(

            chat_id,

            "📚 <b>Exam Select करें</b>\n\n"
            "जिस exam के notices देखना चाहते हैं "
            "उसे चुनें 👇",

            exam_keyboard()

        )

        return

    # Status
    if (
        text == "📊 Status"
        or text.startswith("/status")
    ):

        send_status(chat_id)

        return

    # Latest
    if (
        text.startswith("/latest")
        or text == "🆕 New Notices"
        or text == "🔔 All Updates"
    ):

        send_latest(chat_id)

        return

    # Unknown command
    send_message(

        chat_id,

        "🤖 <b>Option select करें</b>\n\n"
        "मुझे यह command समझ नहीं आया।",

        main_keyboard()

    )


# ============================================================
# CALLBACK BUTTON HANDLER
# ============================================================

def handle_callback(callback):

    callback_id = callback.get(
        "id"
    )

    if callback_id:

        telegram_request(

            "answerCallbackQuery",

            {
                "callback_query_id":
                    callback_id
            }

        )

    data = callback.get(
        "data",
        ""
    )

    message = callback.get(
        "message",
        {}
    )

    chat = message.get(
        "chat",
        {}
    )

    chat_id = chat.get(
        "id"
    )

    if not chat_id:
        return

    # Security
    if (
        ADMIN_ID
        and str(chat_id) != str(ADMIN_ID)
    ):

        send_message(

            chat_id,

            "❌ <b>Unauthorized User</b>\n\n"
            "यह private notice bot है।"

        )

        return

    # Exam buttons
    if data.startswith("EXAM_"):

        category = data.replace(
            "EXAM_",
            ""
        )

        if category == "ALL":

            send_latest(
                chat_id,
                "ALL"
            )

            return

        send_latest(
            chat_id,
            category
        )


# ============================================================
# PROCESS TELEGRAM UPDATE
# ============================================================

def process_update(update):

    try:

        # Inline button
        if "callback_query" in update:

            handle_callback(
                update["callback_query"]
            )

            return

        # Normal message
        message = update.get(
            "message"
        )

        if not message:
            return

        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )

        text = message.get(
            "text",
            ""
        )

        if not chat_id:
            return

        # Security
        if (
            ADMIN_ID
            and str(chat_id)
            != str(ADMIN_ID)
        ):

            send_message(

                chat_id,

                "❌ <b>Unauthorized User</b>\n\n"
                "यह private notice bot है।"

            )

            return

        if text:

            handle_text(
                chat_id,
                text
            )

    except Exception as e:

        print(
            "Update handling error:",
            e
        )


# ============================================================
# SCAN ALL SOURCES AND SEND NEW NOTICES
# ============================================================

def scan_and_notify():

    print("=" * 60)

    print(
        "GOVERNMENT EXAM NOTICE BOARD"
    )

    print(
        "UPSC | SSC | RAILWAY | UPSSSC | BPSC"
    )

    print("=" * 60)

    seen = load_seen()

    latest = load_latest()

    all_new = []

    # Scan all websites
    for source_key in SOURCES:

        print(
            f"Scanning {source_key}..."
        )

        try:

            items = scan_source(
                source_key
            )

            print(
                f"Relevant items found: "
                f"{len(items)}"
            )

        except Exception as e:

            print(
                f"Scan error "
                f"{source_key}: {e}"
            )

            continue

        for item in items:

            url = item.get(
                "url"
            )

            if not url:
                continue

            if url in seen:
                continue

            all_new.append(
                item
            )

    # Remove duplicates
    unique_new = []

    new_urls = set()

    for item in all_new:

        url = item.get(
            "url"
        )

        if url in new_urls:
            continue

        new_urls.add(url)

        unique_new.append(
            item
        )

    all_new = unique_new

    print(
        f"Total NEW notices: "
        f"{len(all_new)}"
    )

    sent_count = 0

    for item in all_new:

        url = item.get(
            "url"
        )

        # Mark as seen
        seen.add(url)

        latest.append(item)

        # Telegram alert limit
        if sent_count >= MAX_ALERTS_PER_RUN:
            continue

        try:

            success = send_new_notice(
                item
            )

            if success:

                sent_count += 1

                print(
                    "Sent:",
                    item.get(
                        "title",
                        ""
                    )
                )

                time.sleep(1)

            else:

                print(
                    "Telegram send failed:",
                    item.get(
                        "title",
                        ""
                    )
                )

        except Exception as e:

            print(
                "Send error:",
                e
            )

    # Save data
    save_seen(
        seen
    )

    save_latest(
        latest[-MAX_LATEST:]
    )

    print(
        f"Sent this run: "
        f"{sent_count}"
    )

    print(
        "Monitoring completed."
    )


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    print(
        "Bot module test started..."
    )

    if not BOT_TOKEN:

        print(
            "WARNING: BOT_TOKEN is missing"
        )

    if not ADMIN_ID:

        print(
            "WARNING: ADMIN_ID is missing"
        )

    print(
        "Running notice scan..."
    )

    scan_and_notify()
