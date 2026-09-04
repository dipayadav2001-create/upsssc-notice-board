import os
import json
import time
import html
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

MAX_ALERTS_PER_RUN = 10

SOURCES = {
    "UPSSSC": "https://upsssc.gov.in/Default.aspx",
    "SSC": "https://ssc.gov.in/",
    "Sarkari Result": "https://www.sarkariresult.com/",
}

KEYWORDS = [
    "notice",
    "notification",
    "advertisement",
    "recruitment",
    "vacancy",
    "result",
    "final result",
    "written result",
    "answer key",
    "admit card",
    "exam",
    "important",
    "corrigendum",
    "application",
    "online form",
    "response sheet",
    "cut off",
    "cutoff",
    "merit",
    "syllabus",
    "marks",
    "selection",
    "shortlist",
    "document verification",
    "counselling",
    "skill test",
    "typing test",
    "physical",
    "pet",
    "pst",
]


# =========================================================
# CATEGORY DETECTION
# =========================================================

def detect_category(title):

    t = title.lower()

    if "answer key" in t or "response sheet" in t:
        return "ANSWER KEY"

    if "admit card" in t or "hall ticket" in t:
        return "ADMIT CARD"

    if "final result" in t:
        return "FINAL RESULT"

    if "result" in t:
        return "RESULT"

    if (
        "advertisement" in t
        or "recruitment" in t
        or "vacancy" in t
        or "online form" in t
        or "application" in t
    ):
        return "RECRUITMENT / FORM"

    if "corrigendum" in t:
        return "CORRIGENDUM"

    if "exam" in t:
        return "EXAM UPDATE"

    if "syllabus" in t:
        return "SYLLABUS"

    if "cut off" in t or "cutoff" in t:
        return "CUT OFF"

    if "merit" in t or "shortlist" in t:
        return "MERIT / SHORTLIST"

    if "important" in t:
        return "IMPORTANT NOTICE"

    return "NOTICE"


# =========================================================
# DATABASE
# =========================================================

def load_seen():

    try:
        with open("seen.json", "r", encoding="utf-8") as f:
            data = json.load(f)

            if isinstance(data, list):
                return set(data)

            if isinstance(data, dict):
                return set(data.keys())

            return set()

    except Exception:
        return set()


def save_seen(seen):

    with open("seen.json", "w", encoding="utf-8") as f:
        json.dump(
            sorted(list(seen)),
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# HTTP SESSION
# =========================================================

def make_session():

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })

    return session


SESSION = make_session()


# =========================================================
# FETCH
# =========================================================

def fetch(url, source):

    last_error = None

    for attempt in range(1, 4):

        try:

            verify = True

            # UPSSSC sometimes has SSL problems
            if source == "UPSSSC":
                verify = True

            response = SESSION.get(
                url,
                timeout=(20, 35),
                verify=verify,
                allow_redirects=True
            )

            response.raise_for_status()

            return response.text

        except requests.exceptions.SSLError as e:

            last_error = e

            if source == "UPSSSC":

                try:

                    response = SESSION.get(
                        url,
                        timeout=(20, 35),
                        verify=False,
                        allow_redirects=True
                    )

                    response.raise_for_status()

                    return response.text

                except Exception as e2:
                    last_error = e2

        except Exception as e:

            last_error = e

        if attempt < 3:
            time.sleep(3)

    raise last_error


# =========================================================
# GENERIC PARSER
# =========================================================

def extract_generic_items(source, url, html_text):

    soup = BeautifulSoup(html_text, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):

        title = a.get_text(" ", strip=True)

        href = a.get("href", "").strip()

        if not title or len(title) < 8:
            continue

        low = title.lower()

        if not any(k in low for k in KEYWORDS):
            continue

        full_url = urljoin(url, href)

        items.append({
            "source": source,
            "title": title,
            "url": full_url,
        })

    return items


# =========================================================
# SSC DEDICATED PARSER
# =========================================================

def extract_ssc_items(url, html_text):

    soup = BeautifulSoup(html_text, "html.parser")

    items = []
    seen_urls = set()

    # -----------------------------------------------------
    # SSC official Notice Board uses attachment/PDF links
    # -----------------------------------------------------

    for a in soup.find_all("a", href=True):

        href = a.get("href", "").strip()

        if not href:
            continue

        full_url = urljoin(url, href)

        href_low = full_url.lower()

        # SSC notice PDFs normally use this path
        if "/api/attachment/" not in href_low:
            continue

        # -------------------------------------------------
        # Find useful title
        # -------------------------------------------------

        title = a.get_text(" ", strip=True)

        # Sometimes anchor itself has no useful text.
        # Search nearby parent/container text.
        if not title or len(title) < 8:

            parent = a.parent

            if parent:
                title = parent.get_text(
                    " ",
                    strip=True
                )

        # Search a few ancestor levels if required
        if not title or len(title) < 8:

            node = a

            for _ in range(4):

                node = node.parent

                if not node:
                    break

                text = node.get_text(
                    " ",
                    strip=True
                )

                if len(text) >= 8:
                    title = text
                    break

        if not title:
            continue

        # Clean excessive spaces
        title = " ".join(title.split())

        # Remove common UI words
        remove_words = [
            "view",
            "download",
            "pdf",
            "eye",
            "image",
        ]

        for word in remove_words:

            if title.lower() == word:
                title = ""

        if not title:
            continue

        # Avoid duplicate URLs
        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)

        items.append({
            "source": "SSC",
            "title": title,
            "url": full_url,
        })

    return items


# =========================================================
# SARKARI RESULT PARSER
# =========================================================

def extract_sarkari_items(url, html_text):

    soup = BeautifulSoup(html_text, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):

        title = a.get_text(" ", strip=True)

        href = a.get("href", "").strip()

        if not title or len(title) < 8:
            continue

        low = title.lower()

        if not any(k in low for k in KEYWORDS):
            continue

        full_url = urljoin(url, href)

        items.append({
            "source": "Sarkari Result",
            "title": title,
            "url": full_url,
        })

    return items


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    if not BOT_TOKEN or not ADMIN_ID:

        print("❌ Telegram secrets missing")

        return False

    api_url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": ADMIN_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:

        response = requests.post(
            api_url,
            data=payload,
            timeout=20
        )

        response.raise_for_status()

        return True

    except Exception as e:

        print(f"❌ Telegram error: {e}")

        return False


# =========================================================
# NOTICE FORMAT
# =========================================================

def format_notice(item):

    source = item["source"]
    title = html.escape(item["title"])
    url = html.escape(item["url"], quote=True)

    category = detect_category(item["title"])

    if source == "UPSSSC":
        icon = "🟢"

    elif source == "SSC":
        icon = "🔵"

    else:
        icon = "🟠"

    message = f"""
🚨 <b>NEW GOVERNMENT EXAM UPDATE</b>
━━━━━━━━━━━━━━━━━━━━

{icon} <b>{html.escape(source)}</b>

📌 <b>{category}</b>

<b>{title}</b>

━━━━━━━━━━━━━━━━━━━━

🔗 <a href="{url}">📄 OPEN NOTICE / DETAILS</a>

━━━━━━━━━━━━━━━━━━━━

🎯 <b>ALL GOVT EXAM ALERT</b>
⚡ Fast • Reliable • Automatic

Source: {html.escape(source)}
"""

    return message.strip()


# =========================================================
# SOURCE SCANNER
# =========================================================

def scan_source(source, url):

    print(f"\n🔎 Checking: {source}")

    html_text = fetch(url, source)

    if source == "SSC":

        items = extract_ssc_items(
            url,
            html_text
        )

    elif source == "Sarkari Result":

        items = extract_sarkari_items(
            url,
            html_text
        )

    else:

        items = extract_generic_items(
            source,
            url,
            html_text
        )

    print(
        f"✅ {source}: "
        f"{len(items)} relevant items"
    )

    return items


# =========================================================
# MAIN
# =========================================================

def main():

    print()
    print("==============================================")
    print("🎯 ALL GOVERNMENT EXAM ALERT")
    print("🔒 PRIVATE TESTING MODE")
    print("==============================================")

    seen = load_seen()

    all_new = []
    successful_sources = 0

    # -----------------------------------------------------
    # Scan sources
    # -----------------------------------------------------

    for source, url in SOURCES.items():

        try:

            items = scan_source(
                source,
                url
            )

            successful_sources += 1

            for item in items:

                key = item["url"]

                if key not in seen:

                    all_new.append(item)

        except Exception as e:

            print(
                f"❌ {source}: "
                f"{type(e).__name__}: {e}"
            )

    # -----------------------------------------------------
    # Remove duplicate URLs
    # -----------------------------------------------------

    unique = []
    unique_urls = set()

    for item in all_new:

        if item["url"] in unique_urls:
            continue

        unique_urls.add(item["url"])
        unique.append(item)

    all_new = unique

    print()
    print("==============================================")
    print(f"🆕 New notices found: {len(all_new)}")
    print("==============================================")

    # -----------------------------------------------------
    # Limit Telegram alerts
    # -----------------------------------------------------

    alerts_sent = 0

    for item in all_new[:MAX_ALERTS_PER_RUN]:

        print(
            f"📨 Sending: "
            f"{item['source']} - "
            f"{item['title'][:100]}"
        )

        message = format_notice(item)

        if send_telegram(message):

            seen.add(item["url"])

            alerts_sent += 1

            print("✅ Telegram alert sent")

        else:

            print(
                "⚠️ Alert failed; "
                "will retry next run"
            )

    # -----------------------------------------------------
    # Important:
    # Mark remaining found items as seen only when
    # they are successfully sent.
    # -----------------------------------------------------

    save_seen(seen)

    # -----------------------------------------------------
    # Final report
    # -----------------------------------------------------

    print()
    print("==============================================")
    print("📊 SCAN SUMMARY")
    print("==============================================")

    print(
        f"📡 Successful sources: "
        f"{successful_sources}/{len(SOURCES)}"
    )

    print(
        f"🆕 New notices: "
        f"{len(all_new)}"
    )

    print(
        f"📨 Alerts sent: "
        f"{alerts_sent}"
    )

    print(
        f"💾 Saved notices: "
        f"{len(seen)}"
    )

    if len(all_new) > MAX_ALERTS_PER_RUN:

        print(
            f"⚠️ More notices remain. "
            f"Next run will continue sending."
        )

    print()
    print("✅ SCAN COMPLETE")
    print("==============================================")


if __name__ == "__main__":
    main()
