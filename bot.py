import os
import json
import hashlib
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

SEEN_FILE = "seen.json"

SOURCES = {
    "UPSSSC": "https://upsssc.gov.in/Default.aspx",
    "SSC": "https://ssc.gov.in/",
    "Sarkari Result": "https://www.sarkariresult.com/",
}

KEYWORDS = (
    "notice",
    "notification",
    "advertisement",
    "result",
    "answer key",
    "admit card",
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


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
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


def detect_category(text):
    t = text.lower()

    if "answer key" in t:
        return "🔑 Answer Key"

    if "admit card" in t:
        return "🎫 Admit Card"

    if "final result" in t:
        return "🏆 Final Result"

    if "result" in t or "marks" in t or "merit" in t:
        return "📊 Result"

    if (
        "advertisement" in t
        or "recruitment" in t
        or "vacancy" in t
    ):
        return "📢 Recruitment / Advertisement"

    if "exam" in t or "syllabus" in t:
        return "📝 Exam Update"

    if "corrigendum" in t:
        return "✏️ Corrigendum"

    if "application" in t or "online form" in t:
        return "📝 Application / Form"

    return "⚠️ Important Notice"


def fetch(url, source):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    # UPSSSC कभी-कभी slow/TLS issue देता है
    for attempt in range(3):

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=45,
                verify=True
            )

            response.raise_for_status()
            return response

        except requests.exceptions.SSLError:

            if source == "UPSSSC":

                response = requests.get(
                    url,
                    headers=headers,
                    timeout=45,
                    verify=False
                )

                response.raise_for_status()
                return response

            raise

        except requests.exceptions.RequestException:

            if attempt == 2:
                raise

            time.sleep(3)


def extract_items(source, url):

    response = fetch(url, source)

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

        if not text or len(text) < 5:
            continue

        lower = text.lower()

        if not any(
            keyword in lower
            for keyword in KEYWORDS
        ):
            continue

        link = urljoin(
            url,
            href
        )

        # Empty/javascript links ignore
        if link.startswith("javascript:"):
            continue

        unique_string = (
            f"{source}|{text}|{link}"
        )

        key = hashlib.sha256(
            unique_string.encode("utf-8")
        ).hexdigest()

        items.append({
            "key": key,
            "source": source,
            "title": text,
            "link": link,
        })

    # duplicates हटाना
    unique = {}

    for item in items:
        unique[item["key"]] = item

    return list(unique.values())


def send_telegram(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": ADMIN_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()


def format_notice(item):

    source = item["source"]
    title = item["title"]
    link = item["link"]

    category = detect_category(title)

    if source == "UPSSSC":
        icon = "🟢"
        source_title = "UPSSSC"

    elif source == "SSC":
        icon = "🔵"
        source_title = "SSC"

    else:
        icon = "🟠"
        source_title = "SARKARI RESULT"

    return f"""
<b>🚨 NEW GOVERNMENT EXAM UPDATE</b>

━━━━━━━━━━━━━━━━━━━━

{icon} <b>{source_title}</b>

📌 <b>UPDATE</b>
{title}

📂 <b>CATEGORY</b>
{category}

━━━━━━━━━━━━━━━━━━━━

🔗 <b><a href="{link}">📄 OPEN NOTICE / DETAILS</a></b>

━━━━━━━━━━━━━━━━━━━━

🎯 <b>ALL GOVT EXAM ALERT</b>
⚡ Fast • Reliable • Automatic

<i>Source: {source_title}</i>
""".strip()


def main():

    print("=" * 60)
    print("🎯 ALL GOVERNMENT EXAM ALERT")
    print("🔒 PRIVATE TESTING MODE")
    print("=" * 60)

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return

    if not ADMIN_ID:
        print("❌ ADMIN_ID missing")
        return

    seen = load_seen()

    first_run = not os.path.exists(
        SEEN_FILE
    )

    all_items = []

    successful = 0

    # -----------------------------------------
    # SOURCE SCAN
    # -----------------------------------------

    for source, url in SOURCES.items():

        try:

            items = extract_items(
                source,
                url
            )

            print(
                f"✅ {source}: "
                f"{len(items)} relevant items"
            )

            all_items.extend(items)

            successful += 1

        except Exception as e:

            print(
                f"❌ {source}: "
                f"{type(e).__name__}: {e}"
            )

    # -----------------------------------------
    # FIRST RUN
    # -----------------------------------------

    if first_run:

        for item in all_items:
            seen.add(item["key"])

        save_seen(seen)

        print()
        print("🆕 FIRST RUN")
        print(
            f"📦 Saved old notices: "
            f"{len(all_items)}"
        )
        print(
            "🔕 Old notices were NOT sent."
        )

    # -----------------------------------------
    # NORMAL RUN
    # -----------------------------------------

    else:

        new_items = [
            item
            for item in all_items
            if item["key"] not in seen
        ]

        print()
        print(
            f"🆕 New notices: "
            f"{len(new_items)}"
        )

        for item in new_items:

            message = format_notice(
                item
            )

            try:

                send_telegram(
                    message
                )

                seen.add(
                    item["key"]
                )

                print(
                    f"📨 SENT → "
                    f"{item['source']} | "
                    f"{item['title']}"
                )

            except Exception as e:

                print(
                    f"❌ Telegram failed: "
                    f"{type(e).__name__}: {e}"
                )

        save_seen(seen)

    # -----------------------------------------
    # FINAL LOG
    # -----------------------------------------

    print()
    print("=" * 60)
    print(
        f"📡 Successful sources: "
        f"{successful}/{len(SOURCES)}"
    )
    print(
        f"💾 Saved notices: "
        f"{len(seen)}"
    )
    print("✅ SCAN COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
