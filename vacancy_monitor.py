import os
import json
import hashlib
import html
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

import bot

SEEN_FILE = "vacancy_seen.json"
MAX_ALERTS_PER_RUN = 20

SOURCES = {
    "UPSC": [
        "https://www.upsc.gov.in/whats-new",
        "https://www.upsc.gov.in/exams-related-info/exam-notification/archives",
    ],
    "SSC": [
        "https://ssc.gov.in/",
    ],
    "RAILWAY/RRB": [
        "https://rrb.indianrailways.gov.in/",
        "https://www.rrcb.gov.in/rrbs.html",
    ],
    "UPSSSC": [
        "https://upsssc.gov.in/",
    ],
    "BPSC": [
        "https://bpsc.bihar.gov.in/",
    ],
    "Employment News": [
        "https://employmentnews.gov.in/newemp/AllJobs.aspx?k=All",
    ],
    "NCS": [
        "https://www.ncs.gov.in/latest-update",
    ],
}

VACANCY_WORDS = [
    "vacancy", "vacancies", "recruitment", "direct recruitment",
    "online application", "apply online", "application form",
    "advertisement", "employment notice", "posts", "post of",
    "engagement", "hiring", "job opening", "cen ", "c.en.",
    "constable", "junior engineer", "assistant", "officer", "clerk",
    "technician", "teacher", "staff nurse",
]

IGNORE_WORDS = [
    "answer key", "admit card", "result", "cut off", "cutoff",
    "syllabus", "exam date", "timetable", "time table",
    "press release", "tender", "court case", "litigation",
    "representation", "internal", "departmental",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; GovernmentExamNoticeBot/2.0)"
})

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(seen), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("vacancy_seen save error:", e)

def fetch(url):
    try:
        r = session.get(url, timeout=25, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print("Vacancy fetch failed:", url, e)
        return None

def looks_like_vacancy(title):
    t = " ".join(title.lower().split())
    if len(t) < 12:
        return False
    if any(word in t for word in IGNORE_WORDS):
        return False
    return any(word in t for word in VACANCY_WORDS)

def make_id(source, title, url):
    raw = f"{source}|{title}|{url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def extract(source, page_url, text):
    soup = BeautifulSoup(text, "html.parser")
    items = []
    local_urls = set()

    for a in soup.find_all("a", href=True):
        title = " ".join(a.get_text(" ", strip=True).split())
        href = a.get("href", "").strip()

        if not title or not href:
            continue

        url = urljoin(page_url, href)

        if not url.startswith("http") or url in local_urls:
            continue

        if not looks_like_vacancy(title):
            continue

        local_urls.add(url)
        items.append({
            "id": make_id(source, title, url),
            "source": source,
            "title": title[:350],
            "url": url,
        })

    return items

def format_alert(item):
    title = html.escape(item["title"])
    source = html.escape(item["source"])
    url = html.escape(item["url"], quote=True)

    return (
        "🚨 <b>NEW VACANCY DETECTED</b>\n\n"
        f"🏢 <b>Source:</b> {source}\n"
        f"📌 <b>{title}</b>\n\n"
        f'🔗 <a href="{url}">Official / Source Link</a>\n\n'
        "⚠️ आवेदन करने से पहले official notification जरूर verify करें।"
    )

def scan_and_notify():
    seen = load_seen()
    new_items = []

    for source, urls in SOURCES.items():
        for page_url in urls:
            text = fetch(page_url)
            if not text:
                continue

            for item in extract(source, page_url, text):
                if item["id"] in seen:
                    continue

                seen.add(item["id"])
                new_items.append(item)

                if len(new_items) >= MAX_ALERTS_PER_RUN:
                    break

            if len(new_items) >= MAX_ALERTS_PER_RUN:
                break

        if len(new_items) >= MAX_ALERTS_PER_RUN:
            break

    save_seen(seen)

    sent = 0
    for item in new_items:
        if not bot.ADMIN_ID:
            break

        result = bot.send_message(
            bot.ADMIN_ID,
            format_alert(item)
        )

        if result and result.get("ok"):
            sent += 1

    print(f"Vacancy monitor: found={len(new_items)}, sent={sent}")
    return new_items
