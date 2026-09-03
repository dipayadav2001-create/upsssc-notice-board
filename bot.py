import os
import hashlib
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8549471800"))

SOURCES = {
    "UPSSSC": "https://upsssc.gov.in/Default.aspx",
    "SSC": "https://ssc.gov.in/",
    "UPSC": "https://www.upsc.gov.in/",
    "UPPSC": "https://uppsc.up.nic.in/",
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
    "marks",
    "merit",
    "syllabus",
    "online form",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
    )
}


def get_items(source_name, url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=25,
            verify=False,
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = []

        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            href = a["href"].strip()

            if len(text) < 5:
                continue

            lower_text = text.lower()

            if not any(keyword in lower_text for keyword in KEYWORDS):
                continue

            if href.startswith("http"):
                link = href
            elif href.startswith("/"):
                base = url.split("/", 3)
                link = f"{base[0]}//{base[2]}{href}"
            else:
                link = url.rsplit("/", 1)[0] + "/" + href

            key = hashlib.sha256(
                f"{source_name}|{text}|{link}".encode()
            ).hexdigest()

            items.append((key, text, link))

        return items

    except Exception as e:
        print(f"{source_name}: {type(e).__name__}: {e}")
        return []


def send_message(text):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        api_url,
        json={
            "chat_id": ADMIN_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )

    response.raise_for_status()


def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return

    for source_name, url in SOURCES.items():
        print(f"Checking {source_name}...")

        items = get_items(source_name, url)

        print(f"{source_name}: {len(items)} relevant items found")

        for key, title, link in items[:10]:
            print(f"{source_name}: {title}")


if __name__ == "__main__":
    main()
