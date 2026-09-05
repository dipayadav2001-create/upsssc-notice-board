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
# OFFICIAL SOURCES
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
# IMPORTANT KEYWORDS
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


def telegram_request(
    method,
    data=None,
    timeout=30
):

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

        print(
            "Telegram request error:",
            e
        )

        return None


# ============================================================
# SEND MESSAGE
# ============================================================

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
# JSON FUNCTIONS
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
            f"Error loading {filename}:",
            e
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
            f"Error saving {filename}:",
            e
        )


# ============================================================
# SEEN
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
# LATEST
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

    if title_clean in BLOCKED_EXACT_TITLES:

        return False

    for keyword in BLOCKED_KEYWORDS:

        if keyword in title_clean:

            return False

    generic_titles = [

       
