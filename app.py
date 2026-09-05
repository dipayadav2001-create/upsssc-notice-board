import os
import time
import threading
import requests

from flask import Flask, request, jsonify

import bot


app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

PORT = int(os.getenv("PORT", "10000"))

TELEGRAM_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
    if BOT_TOKEN
    else None
)


# ============================================================
# TELEGRAM API
# ============================================================

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

        print(
            "Telegram:",
            method,
            response.status_code
        )

        return response.json()

    except Exception as e:
        print("Telegram API error:", e)
        return None


# ============================================================
# WEBHOOK
# ============================================================

def set_webhook():

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return

    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL missing")
        return

    webhook_url = (
        WEBHOOK_URL.rstrip("/")
        + "/telegram-webhook"
    )

    print("Setting webhook:")
    print(webhook_url)

    result = telegram_request(
        "setWebhook",
        {
            "url": webhook_url,
            "drop_pending_updates": False
        }
    )

    print("Webhook result:")
    print(result)


# ============================================================
# UPDATE HANDLER
# ============================================================

def handle_update(update):

    try:

        # ----------------------------------------------------
        # CALLBACK BUTTON
        # ----------------------------------------------------

        if "callback_query" in update:

            callback = update["callback_query"]

            callback_id = callback.get("id")

            message = callback.get(
                "message",
                {}
            )

            chat = message.get(
                "chat",
                {}
            )

            chat_id = chat.get("id")

            # Answer button immediately
            if callback_id:

                telegram_request(
                    "answerCallbackQuery",
                    {
                        "callback_query_id":
                        callback_id
                    }
                )

            # Admin protection
            if (
                ADMIN_ID
                and str(chat_id)
                != str(ADMIN_ID)
            ):

                bot.send_message(
                    chat_id,
                    "❌ <b>Unauthorized User</b>\n\n"
                    "यह private notice bot है।"
                )

                return

            # Let bot.py process exam button
            bot.process_update(update)

            return


        # ----------------------------------------------------
        # NORMAL MESSAGE
        # ----------------------------------------------------

        message = update.get("message")

        if not message:
            return

        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get("id")

        if not chat_id:
            return

        # Admin protection
        if (
            ADMIN_ID
            and str(chat_id)
            != str(ADMIN_ID)
        ):

            bot.send_message(
                chat_id,
                "❌ <b>Unauthorized User</b>\n\n"
                "यह private notice bot है।"
            )

            return

        # Send complete update to bot.py
        bot.process_update(update)

    except Exception as e:

        print(
            "Update handling error:",
            e
        )


# ============================================================
# TELEGRAM WEBHOOK ROUTE
# ============================================================

@app.route(
    "/telegram-webhook",
    methods=["POST"]
)
def telegram_webhook():

    update = request.get_json(
        silent=True
    )

    if update:

        # Process Telegram update
        # without blocking Telegram
        threading.Thread(
            target=handle_update,
            args=(update,),
            daemon=True
        ).start()

    return jsonify({
        "ok": True
    })


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return (
        "Government Job Notice Bot "
        "is running."
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({
        "status": "ok",
        "bot": "running",
        "webhook": "active"
    })


# ============================================================
# NOTICE SCANNER
# ============================================================

def notice_scanner():

    print(
        "🚀 Notice scanner started"
    )

    while True:

        try:

            print(
                "\n"
                "================================"
            )

            print(
                "🔎 Starting notice scan..."
            )

            bot.scan_and_notify()

            print(
                "✅ Notice scan completed"
            )

            print(
                "Next scan after 5 minutes."
            )

        except Exception as e:

            print(
                "❌ Scanner error:",
                e
            )

        # Scan every 5 minutes
        time.sleep(300)


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        "========================================"
    )

    print(
        "🇮🇳 GOVERNMENT EXAM NOTICE BOARD"
    )

    print(
        "UPSC | SSC | RAILWAY | UPSSSC | BPSC"
    )

    print(
        "========================================"
    )

    # Set Telegram webhook
    set_webhook()

    # Start notice scanner
    scanner_thread = threading.Thread(
        target=notice_scanner,
        daemon=True
    )

    scanner_thread.start()

    # Start Flask server
    app.run(
        host="0.0.0.0",
        port=PORT
    )
