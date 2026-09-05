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
MAX_LATEST = 20

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
    },

    "SSC": {
        "name": "SSC",
        "url": "https://ssc.gov.in/",
    },

    "RAILWAY": {
        "name": "Railway / RRB",
        "url": "https://indianrailways.gov.in/",
    },

    "UPSSSC": {
        "name": "UPSSSC",
        "url": "https://upsssc.gov.in/",
    },

    "BPSC": {
        "name": "BPSC",
        "url": "https://www.bpsc.bih.nic.in/",
    }
}


# ============================================================
# KEYWORDS
# ============================================================

IMPORTANT_KEYWORDS = [

    # Recruitment
    "notification",
    "recruitment",
    "vacancy",
    "vacancies",
    "application",
    "apply online",
    "online application",
    "advertisement",

    # Examination
    "exam",
    "examination",
    "exam date",
    "exam schedule",
    "examination schedule",
    "timetable",
    "time table",

    # Admit Card
    "admit card",
    "admitcard",
    "hall ticket",

    # Result
    "result",
    "final result",
    "written result",
    "merit list",
    "selection list",
    "cut off",
    "cutoff",

    # Answer Key
    "answer key",
    "answerkey",
    "response sheet",
    "provisional answer key",
    "final answer key",

    # Candidate updates
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

    # Other exam related
    "eligibility",
    "syllabus",
    "fee",
    "registration",
    "registration date",
    "appointment"
]


# ============================================================
# GENERIC / ADMINISTRATIVE TITLES TO IGNORE
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
                f"Telegram error {response.status_code}: "
                f"{response.text[:500]}"
            )

            return None

        return response.json()

    except Exception as e:

        print(
            f"Telegram request error: {e}"
        )

        return None


def send_message(
    chat_id,
    text,
    reply_markup=None
):

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
# MAIN KEYBOARD
# ============================================================

def main_keyboard():

    return {

        "keyboard": [

            [
                {
                    "text": "🆕 New Notices"
                },
                {
                    "text": "📚 Exams"
                }
            ],

            [
                {
                    "text": "📊 Status"
                },
                {
                    "text": "❓ Help"
                }
            ],

            [
                {
                    "text": "🔔 All Updates"
                }
            ]
        ],

        "resize_keyboard": True
    }


# ============================================================
# EXAM KEYBOARD
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
# FILE FUNCTIONS
# ============================================================

def load_json(
    filename,
    default
):

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
            f"Error loading {filename}: {e}"
        )

        return default


def save_json(
    filename,
    data
):

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
            f"Error saving {filename}: {e}"
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
# TELEGRAM OFFSET
# ============================================================

def load_offset():

    try:

        if not os.path.exists(
            OFFSET_FILE
        ):

            return None

        with open(
            OFFSET_FILE,
            "r"
        ) as f:

            return int(
                f.read().strip()
            )

    except Exception:

        return None


def save_offset(offset):

    try:

        with open(
            OFFSET_FILE,
            "w"
        ) as f:

            f.write(
                str(offset)
            )

    except Exception as e:

        print(
            f"Offset error: {e}"
        )


# ============================================================
# HTTP SESSION
# ============================================================

def make_session():

    session = requests.Session()

    session.headers.update({

        "User-Agent":
        (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )

    })

    return session


SESSION = make_session()


# ============================================================
# FETCH WEBSITE
# ============================================================

def fetch(
    url,
    timeout=30
):

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

def is_relevant(
    title,
    source
):

    title_clean = " ".join(
        title.lower().split()
    )

    # --------------------------------------------------------
    # Exact generic navigation titles
    # --------------------------------------------------------

    if title_clean in BLOCKED_EXACT_TITLES:

        return False


    # --------------------------------------------------------
    # Administrative / internal notices
    # --------------------------------------------------------

    for keyword in BLOCKED_KEYWORDS:

        if keyword in title_clean:

            return False


    # --------------------------------------------------------
    # Very short generic navigation
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Candidate-facing keywords
    # --------------------------------------------------------

    for keyword in IMPORTANT_KEYWORDS:

        if keyword in title_clean:

            return True


    return False


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(
    title,
    source
):

    text = (
        f"{title} {source}"
    ).lower()

    if "upsssc" in text:

        return "UPSSSC"

    if "bpsc" in text:

        return "BPSC"

    if "upsc" in text:

        return "UPSC"

    if "ssc" in text:

        return "SSC"

    if (
        "railway" in text
        or "rrb" in text
    ):

        return "RAILWAY"

    return source


# ============================================================
# GENERIC HTML PARSER
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

        href = a.get(
            "href"
        )

        if not href:

            continue

        url = urljoin(
            base_url,
            href
        )

        if not url.startswith(
            "http"
        ):

            continue

        if url in seen_urls:

            continue

        if not is_relevant(
            title,
            source_name
        ):

            continue

        seen_urls.add(url)

        category = detect_category(
            title,
            source_name
        )

        items.append({

            "title":
                title[:300],

            "url":
                url,

            "source":
                source_name,

            "category":
                category
        })


    return items


# ============================================================
# SOURCE PARSERS
# ============================================================

def extract_upsc_items(
    html_text,
    base_url
):

    return extract_generic_items(
        html_text,
        base_url,
        "UPSC"
    )


def extract_ssc_items(
    html_text,
    base_url
):

    return extract_generic_items(
        html_text,
        base_url,
        "SSC"
    )


def extract_railway_items(
    html_text,
    base_url
):

    return extract_generic_items(
        html_text,
        base_url,
        "RAILWAY"
    )


def extract_upsssc_items(
    html_text,
    base_url
):

    return extract_generic_items(
        html_text,
        base_url,
        "UPSSSC"
    )


def extract_bpsc_items(
    html_text,
    base_url
):

    return extract_generic_items(
        html_text,
        base_url,
        "BPSC"
    )


# ============================================================
# SCAN SOURCE
# ============================================================

def scan_source(
    source_key
):

    source = SOURCES[
        source_key
    ]

    html_text = fetch(
        source["url"]
    )

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
            ""
        )
    )

    category = html.escape(
        item.get(
            "category",
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

        "🔔 <b>NEW GOVERNMENT JOB NOTICE</b>\n\n"

        f"📌 <b>{title}</b>\n\n"

        f"🏛️ Source: <b>{source}</b>\n"

        f"📚 Exam: <b>{category}</b>\n\n"

        f"🔗 <a href=\"{url}\">"
        "Official Notice</a>\n\n"

        "⚡ <b>UPSSSC Notice Board</b>"
    )


# ============================================================
# START
# ============================================================

def send_start(chat_id):

    text = (

        "🙏 <b>नमस्ते!</b>\n\n"

        "🎓 <b>UPSSSC Notice Board</b> "
        "में आपका स्वागत है।\n\n"

        "मैं सरकारी भर्ती एवं परीक्षा "
        "notifications को track करता हूँ।\n\n"

        "🇮🇳 <b>UPSC</b>\n"
        "📝 <b>SSC</b>\n"
        "🚆 <b>Railway / RRB</b>\n"
        "🟢 <b>UPSSSC</b>\n"
        "🔵 <b>BPSC</b>\n\n"

        "🆕 <b>New Notices</b> "
        "से latest notices देखें।\n\n"

        "📚 <b>Exams</b> "
        "से अपना exam चुनें।\n\n"

        "❓ <b>Help</b> "
        "से bot की जानकारी देखें।\n\n"

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

        "❓ <b>UPSSSC Notice Board - HELP</b>\n\n"

        "🆕 <b>New Notices</b>\n"
        "→ सभी नए saved government notices\n\n"

        "📚 <b>Exams</b>\n"
        "→ UPSC, SSC, Railway, UPSSSC और BPSC चुनें\n\n"

        "📊 <b>Status</b>\n"
        "→ Bot और monitoring की स्थिति\n\n"

        "🔔 <b>All Updates</b>\n"
        "→ सभी exams के latest updates\n\n"

        "⌨️ <b>Commands</b>\n\n"

        "/start\n"
        "→ Bot का welcome menu\n\n"

        "/help\n"
        "→ Help और commands\n\n"

        "/status\n"
        "→ Bot status\n\n"

        "/latest\n"
        "→ Latest notices\n\n"

        "/exams\n"
        "→ Exam selection\n\n"

        "⏱️ Monitoring लगभग हर <b>5 मिनट</b> में चलता है।"
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

        "📊 <b>BOT STATUS</b>\n\n"

        "🟢 Bot: <b>ACTIVE</b>\n"

        "⏱️ Monitoring: <b>5 Minutes</b>\n\n"

        f"📌 Tracked notices: "
        f"<b>{len(seen)}</b>\n"

        f"🆕 Latest saved notices: "
        f"<b>{len(latest)}</b>\n\n"

        "📡 <b>Sources</b>\n"

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

            "ℹ️ <b>कोई notice नहीं मिला।</b>\n\n"
            "नई notification आने के बाद "
            "यहाँ दिखाई जाएगी।",

            main_keyboard()
        )

        return


    if category and category != "ALL":

        heading = (
            f"🆕 <b>{html.escape(category)} "
            "Latest Notices</b>"
        )

    else:

        heading = (
            "🆕 <b>Latest Government Notices</b>"
        )


    lines = [
        heading,
        ""
    ]


    for index, item in enumerate(

        reversed(
            latest[-MAX_LATEST:]
        ),

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

            f"<b>{index}. {title}</b>\n"
            f"🏛️ {source}\n"
            f"🔗 <a href=\"{url}\">Open Official Notice</a>\n"
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
        "जिस exam की notifications चाहिए "
        "उसे नीचे से चुनें 👇",

        exam_keyboard()
    )


# ============================================================
# CALLBACK
# ============================================================

def answer_callback(
    callback_id
):

    telegram_request(

        "answerCallbackQuery",

        {
            "callback_query_id":
                callback_id
        }
    )


def handle_callback(
    callback
):

    callback_id = callback.get(
        "id"
    )

    if callback_id:

        answer_callback(
            callback_id
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


    if data == "EXAM_UPSC":

        send_latest(
            chat_id,
            "UPSC"
        )


    elif data == "EXAM_SSC":

        send_latest(
            chat_id,
            "SSC"
        )


    elif data == "EXAM_RAILWAY":

        send_latest(
            chat_id,
            "RAILWAY"
        )


    elif data == "EXAM_UPSSSC":

        send_latest(
            chat_id,
            "UPSSSC"
        )


    elif data == "EXAM_BPSC":

        send_latest(
            chat_id,
            "BPSC"
        )


    elif data == "EXAM_ALL":

        send_latest(
            chat_id,
            "ALL"
        )


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_text(
    chat_id,
    text
):

    text = text.strip()

    lower = text.lower()


    if lower == "/start":

        send_start(
            chat_id
        )

        return


    if lower == "/help":

        send_help(
            chat_id
        )

        return


    if lower == "/status":

        send_status(
            chat_id
        )

        return


    if lower == "/latest":

        send_latest(
            chat_id
        )

        return


    if lower == "/exams":

        send_exam_menu(
            chat_id
        )

        return


    if text == "🆕 New Notices":

        send_latest(
            chat_id
        )

        return


    if text == "📚 Exams":

        send_exam_menu(
            chat_id
        )

        return


    if text == "📊 Status":

        send_status(
            chat_id
        )

        return


    if text == "❓ Help":

        send_help(
            chat_id
        )

        return


    if text == "🔔 All Updates":

        send_latest(
            chat_id
        )

        return


    send_message(

        chat_id,

        "🤖 Command समझ नहीं आया।\n\n"
        "❓ <b>Help</b> दबाएँ या "
        "<code>/help</code> लिखें।",

        main_keyboard()
    )


# ============================================================
# TELEGRAM UPDATES
# ============================================================

def handle_commands():

    if not BOT_TOKEN:

        print(
            "BOT_TOKEN missing"
        )

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


    if not result.get(
        "ok"
    ):

        return


    updates = result.get(
        "result",
        []
    )


    if not updates:

        return


    for update in updates:


        update_id = update.get(
            "update_id"
        )


        if update_id is not None:

            save_offset(
                update_id + 1
            )


        # ----------------------------------------------------
        # CALLBACK
        # ----------------------------------------------------

        if "callback_query" in update:

            callback = update[
                "callback_query"
            ]

            user = callback.get(
                "from",
                {}
            )

            user_id = str(
                user.get(
                    "id",
                    ""
                )
            )


            if (
                ADMIN_ID
                and user_id
                != str(ADMIN_ID)
            ):

                answer_callback(
                    callback.get(
                        "id"
                    )
                )

                continue


            handle_callback(
                callback
            )

            continue


        # ----------------------------------------------------
        # MESSAGE
        # ----------------------------------------------------

        message = update.get(
            "message"
        )


        if not message:

            continue


        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )


        user = message.get(
            "from",
            {}
        )

        user_id = str(
            user.get(
                "id",
                ""
            )
        )


        if not chat_id:

            continue


        # ----------------------------------------------------
        # ADMIN ONLY
        # ----------------------------------------------------

        if (
            ADMIN_ID
            and user_id
            != str(ADMIN_ID)
        ):

            send_message(

                chat_id,

                "⛔ यह bot केवल "
                "authorized admin के लिए है।"
            )

            continue


        text = message.get(
            "text",
            ""
        )


        if text:

            handle_text(

                chat_id,

                text
            )


# ============================================================
# SEND NEW NOTICE
# ============================================================

def send_new_notice(
    item
):

    if not ADMIN_ID:

        print(
            "ADMIN_ID missing"
        )

        return False


    message = format_notice(
        item
    )


    result = send_message(

        ADMIN_ID,

        message
    )


    if result and result.get(
        "ok"
    ):

        return True


    return False


# ============================================================
# MAIN MONITOR
# ============================================================

def main():

    print(
        "=" * 60
    )

    print(
        "UPSSSC NOTICE BOARD BOT"
    )

    print(
        "UPSC | SSC | RAILWAY | UPSSSC | BPSC"
    )

    print(
        "=" * 60
    )


    # --------------------------------------------------------
    # Telegram commands
    # --------------------------------------------------------

    handle_commands()


    # --------------------------------------------------------
    # Load saved data
    # --------------------------------------------------------

    seen = load_seen()

    latest = load_latest()

    all_new = []


    # --------------------------------------------------------
    # Scan every source
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


    # --------------------------------------------------------
    # Remove duplicate URLs
    # --------------------------------------------------------

    unique_new = []

    new_urls = set()


    for item in all_new:

        url = item.get(
            "url"
        )


        if url in new_urls:

            continue


        new_urls.add(
            url
        )

        unique_new.append(
            item
        )


    all_new = unique_new


    print(
        f"\nTotal NEW notices: "
        f"{len(all_new)}"
    )


    # --------------------------------------------------------
    # Send notices
    # --------------------------------------------------------

    sent_count = 0


    for item in all_new:

        url = item.get(
            "url"
        )


        # Save as seen
        seen.add(
            url
        )


        # Save in latest list
        latest.append(
            item
        )


        # Limit alerts per run
        if (
            sent_count
            >= MAX_ALERTS_PER_RUN
        ):

            continue


        try:

            success = send_new_notice(
                item
            )


            if success:

                sent_count += 1

                print(
                    "Sent: "
                    + item.get(
                        "title",
                        ""
                    )
                )

                time.sleep(1)


            else:

                print(
                    "Telegram send failed: "
                    + item.get(
                        "title",
                        ""
                    )
                )


        except Exception as e:

            print(
                f"Send error: {e}"
            )


    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_seen(
        seen
    )


    save_latest(
        latest[-MAX_LATEST:]
    )


    print(
        f"\nSent this run: "
        f"{sent_count}"
    )


    print(
        "Monitoring completed."
    )


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":

    main()
