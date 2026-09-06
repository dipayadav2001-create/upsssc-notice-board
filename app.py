import os
import time
import threading
import requests

from flask import Flask, request, jsonify

import bot
import vacancy_monitor

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

TELEGRAM_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
    if BOT_TOKEN else None
)

def telegram_request(method, data=None):
    if not TELEGRAM_API:
        print("BOT_TOKEN missing")
        return None

    try:
        response = requests.post(
            f"{TELEGRAM_API}/{method}",
            data=data or {},
            timeout=30
        )
        print("Telegram:", method, response.status_code)
        return response.json()
    except Exception as e:
        print("Telegram API error:", e)
        return None

def set_webhook():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return

    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL missing")
        return

    webhook_url = WEBHOOK_URL.rstrip("/") + "/telegram-webhook"

    result = telegram_request(
        "setWebhook",
        {
            "url": webhook_url,
            "drop_pending_updates": False
        }
    )

    print("Webhook result:", result)

def handle_update(update):
    try:
        if "callback_query" in update:
            callback = update["callback_query"]
            callback_id = callback.get("id")
            message = callback.get("message", {})
            chat_id = message.get("chat", {}).get("id")

            if callback_id:
                telegram_request(
                    "answerCallbackQuery",
                    {"callback_query_id": callback_id}
                )

            if ADMIN_ID and str(chat_id) != str(ADMIN_ID):
                bot.send_message(
                    chat_id,
                    "❌ <b>Unauthorized User</b>\n\n"
                    "यह private notice bot है।"
                )
                return

            bot.process_update(update)
            return

        message = update.get("message")
        if not message:
            return

        chat_id = message.get("chat", {}).get("id")
        if not chat_id:
            return

        if ADMIN_ID and str(chat_id) != str(ADMIN_ID):
            bot.send_message(
                chat_id,
                "❌ <b>Unauthorized User</b>\n\n"
                "यह private notice bot है।"
            )
            return

        bot.process_update(update)

    except Exception as e:
        print("Update handling error:", e)

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True)

    if update:
        threading.Thread(
            target=handle_update,
            args=(update,),
            daemon=True
        ).start()

    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def home():
    return "Government Job Notice Bot is running."

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "bot": "running",
        "webhook": "active"
    })

def notice_scanner():
    print("🚀 Vacancy monitor started")

    while True:
        try:
            print("\n================================")
            print("🔎 Checking government vacancy sources...")

            vacancy_monitor.scan_and_notify()

            print("✅ Vacancy scan completed")
            print("Next scan after 1 minute.")

        except Exception as e:
            print("❌ Vacancy scanner error:", e)

        time.sleep(60)

if __name__ == "__main__":
    print("\n========================================")
    print("🇮🇳 GOVERNMENT EXAM NOTICE BOARD V2")
    print("UPSC | SSC | RAILWAY | UPSSSC | BPSC")
    print("========================================")

    set_webhook()

    scanner_thread = threading.Thread(
        target=notice_scanner,
        daemon=True
    )
    scanner_thread.start()

    app.run(
        host="0.0.0.0",
        port=PORT
    )
