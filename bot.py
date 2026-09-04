import os
import json
import hashlib
import html
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# =========================================================
# CONFIGURATION
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

SEEN_FILE = "seen.json"

# केवल ये 3 sources monitor होंगे
SOURCES = {
    "UPSSSC": "https://upsssc.gov.in/Default.aspx",
    "SSC": "https://ssc.gov.in/",
    "Sarkari Result": "https://www.sarkariresult.com/",
}

# =========================================================
# KEYWORDS
# =========================================================

KEYWORDS = (
    "notice",
    "notification",
    "advertisement",
    "result",
    "answer key",
    "answerkey",
    "admit card",
    "admitcard",
    "exam",
    "recruitment",
    "vacancy",
    "important",
    "corrigendum",
    "final result",
    "written result",
    "marks",
    "merit",
    "syllabus",
    "application",
    "online form",
    "response sheet",
    "cut off",
    "cutoff",
)

# =========================================================
# CATEGORY DETECTION
# =========================================================

def detect_category(text):
    t = text.lower()

    if "answer key" in t or "answerkey" in t:
        return "🔑 Answer Key"

    if "admit card" in t or "admitcard" in t:
        return "🎫 Admit Card"

    if "final result" in t:
        return "🏆 Final Result"

    if "result" in t or "marks" in t or "merit" in t:
        return "📊 Result"

    if "advertisement" in t or "recruitment" in t or "vacancy" in t:
        return "📢 Recruitment / Advertisement"

    if "exam" in t or "syllabus" in t:
        return "📝 Exam Update"

    if "corrigendum" in t:
        return "✏️ Corrigendum"

    if "application" in t or "online form" in t:
        return "📝 Application / Form"

    if "important" in t or "notice" in t or "notification" in t:
        return "⚠️ Important Notice"

    return "📌 Government Job Update"


# =========================================================
# SEEN DATABASE
# =========================================================

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return set(data)

    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            sorted(seen),
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# URL HANDLING
# =========================================================

def make_absolute_url(base_url, href):
    if not href:
        return base_url

    return urljoin(base_url, href)


# =========================================================
# WEBSITE FETCH
# =========================================================

def fetch_page(url, source_name):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0 Mobile Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()
        return response

    except requests.exceptions.SSLError:

        # UPSSSC पर कभी-कभी SSL issue आता है।
        # केवल SSL failure होने पर fallback.
        if source_name == "UPSSSC":
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
                verify=False
            )

            response.raise_for_status()
            return response

        raise


# =========================================================
# EXTRACT NOTICES
# =========================================================

def get_items(source_name, url):

    response = fetch_page(url, source_name)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    items = []

    for a in soup.find_all("a", href=True):

        text = a.get_text(
            " ",
            strip=True
        )

        href = a.get(
            "href",
            ""
        ).strip()

        if not text:
            continue

        if len(text) < 5:
            continue

        text_lower = text.lower()

        # केवल relevant government-job updates
        if not any(
            keyword in text_lower
            for keyword in KEYWORDS
        ):
            continue

        link = make_absolute_url(
            url,
            href
        )

        # Hash = duplicate protection
        key_text = (
            f"{source_name}|"
            f"{text}|"
            f"{link}"
        )

        key = hashlib.sha256(
            key_text.encode("utf-8")
        ).hexdigest()

        items.append(
            {
                "key": key,
                "source": source_name,
                "text": text,
                "link": link,
            }
        )

    # Same notice page पर duplicate links हटाना
    unique = {}

    for item in items:
        unique[item["key"]] = item

    return list(unique.values())


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    telegram_url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        telegram_url,
        data={
            "chat_id": ADMIN_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()

    return True


# =========================================================
# NOTICE DESIGN
# =========================================================

def create_notice_message(item):

    source = html.escape(
        item["source"]
    )

    title = html.escape(
        item["text"]
    )

    link = html.escape(
        item["link"],
        quote=True
    )

    category = html.escape(
        detect_category(item["text"])
    )

    # Source branding
    if item["source"] == "UPSSSC":
        source_icon = "🟢"
        source_name = "UPSSSC"

    elif item["source"] == "SSC":
        source_icon = "🔵"
        source_name = "SSC"

    else:
        source_icon = "🟠"
        source_name = "Sarkari Result"

    message = f"""
<b>🚨 NEW GOVERNMENT JOB UPDATE</b>

━━━━━━━━━━━━━━━━━━━━

{source_icon} <b>{source_name}</b>

📌 <b>UPDATE</b>
{title}

📂 <b>CATEGORY</b>
{category}

━━━━━━━━━━━━━━━━━━━━

🔗 <b><a href="{link}">📄 OFFICIAL NOTICE / DETAILS</a></b>

━━━━━━━━━━━━━━━━━━━━

⚡ <b>UPSSSC NOTICE BOARD</b>
📡 Automatic Monitoring
🔔 Fast Government Job Alerts

<i>Source: {source}</i>
"""

    return message.strip()


# =========================================================
# MAIN MONITOR
# =========================================================

def main():

    print("=" * 60)
    print("UPSSSC NOTICE BOARD - PRIVATE TESTING")
    print("=" * 60)

    # Secrets check
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN is missing")
        return

    if not ADMIN_ID:
        print("❌ ERROR: ADMIN_ID is missing")
        return

    seen = load_seen()

    first_run = not os.path.exists(
        SEEN_FILE
    )

    all_items = []

    successful_sources = 0

    # -----------------------------------------------------
    # CHECK ALL SOURCES
    # -----------------------------------------------------

    for source_name, url in SOURCES.items():

        try:

            items = get_items(
                source_name,
                url
            )

            print(
                f"✅ {source_name}: "
                f"{len(items)} relevant items found"
            )

            all_items.extend(items)

            successful_sources += 1

        except Exception as e:

            print(
                f"❌ {source_name}: FAILED - "
                f"{type(e).__name__}: {e}"
            )

    # -----------------------------------------------------
    # FIRST RUN
    # -----------------------------------------------------

    if first_run:

        for item in all_items:
            seen.add(item["key"])

        save_seen(seen)

        print()
        print(
            f"🟢 First run complete."
        )

        print(
            f"📦 Existing items saved: "
            f"{len(all_items)}"
        )

        print(
            "🔕 No old notices were sent."
        )

    # -----------------------------------------------------
    # NORMAL RUN
    # -----------------------------------------------------

    else:

        new_items = []

        for item in all_items:

            if item["key"] not in seen:
                new_items.append(item)

        print()
        print(
            f"🆕 New items detected: "
            f"{len(new_items)}"
        )

        # Send new notices
        for item in new_items:

            message = create_notice_message(
                item
            )

            try:

                send_telegram(
                    message
                )

                # केवल successful send के बाद
                # database में save करें
                seen.add(
                    item["key"]
                )

                print(
                    f"📨 Telegram sent: "
                    f"{item['source']} - "
                    f"{item['text']}"
                )

            except Exception as e:

                print(
                    f"❌ Telegram failed: "
                    f"{type(e).__name__}: {e}"
                )

        save_seen(seen)

    # -----------------------------------------------------
    # FINAL STATUS
    # -----------------------------------------------------

    print()
    print("=" * 60)

    print(
        f"📡 Sources successful: "
        f"{successful_sources}/3"
    )

    print(
        f"💾 Total saved notices: "
        f"{len(seen)}"
    )

    print(
        "✅ Scan complete"
    )

    print("=" * 60)


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
