import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup


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
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def make_absolute_url(base_url, href):
    if href.startswith("http://") or href.startswith("https://"):
        return href

    if href.startswith("/"):
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"

    return base_url.rstrip("/") + "/" + href.lstrip("/")


def get_items(source_name, url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10) "
            "AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a.get("href", "").strip()

        if not text or len(text) < 5:
            continue

        text_lower = text.lower()

        if not any(keyword in text_lower for keyword in KEYWORDS):
            continue

        link = make_absolute_url(url, href)

        key_text = f"{source_name}|{text}|{link}"

        key = hashlib.sha256(
            key_text.encode("utf-8")
        ).hexdigest()

        items.append({
            "key": key,
            "source": source_name,
            "text": text,
            "link": link
        })

    return items


def send_telegram(message):
    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        telegram_url,
        data={
            "chat_id": ADMIN_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()


def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is missing")
        return

    if not ADMIN_ID:
        print("ERROR: ADMIN_ID is missing")
        return

    seen = load_seen()

    all_items = []
    successful_sources = 0

    for source_name, url in SOURCES.items():

        try:
            items = get_items(source_name, url)

            print(
                f"{source_name}: "
                f"{len(items)} relevant items found"
            )

            all_items.extend(items)
            successful_sources += 1

        except Exception as e:
            print(
                f"{source_name}: FAILED - "
                f"{type(e).__name__}: {e}"
            )

    new_items = []

    for item in all_items:
        if item["key"] not in seen:
            new_items.append(item)
            seen.add(item["key"])

    # First run: save existing notices but don't send hundreds of old alerts.
    first_run = not os.path.exists(SEEN_FILE)

    if first_run:
        print(
            f"First run complete. "
            f"Saved {len(all_items)} existing items."
        )

    else:
        for item in new_items:

            message = (
                f"🚨 NEW GOVERNMENT JOB UPDATE\n\n"
                f"🏛 Source: {item['source']}\n\n"
                f"📌 {item['text']}\n\n"
                f"🔗 {item['link']}"
            )

            try:
                send_telegram(message)

                print(
                    f"Telegram sent: "
                    f"{item['source']} - {item['text']}"
                )

            except Exception as e:
                print(
                    f"Telegram failed: "
                    f"{type(e).__name__}: {e}"
                )

    save_seen(seen)

    print(
        f"Scan complete. "
        f"Sources successful: {successful_sources}/5"
    )

    print(
        f"Total saved items: {len(seen)}"
    )

    if not first_run:
        print(
            f"New items detected: {len(new_items)}"
        )


if __name__ == "__main__":
    main()
