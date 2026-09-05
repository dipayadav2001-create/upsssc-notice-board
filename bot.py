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
                   
