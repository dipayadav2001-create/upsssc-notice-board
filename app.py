import os
import json
import time
import threading
import requests
from flask import Flask, request, jsonify

# Import your existing bot functions
import bot

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_request(method, data=None):
    try:
        r = requests.post(
            f"{TELEGRAM_API}/{method}",
            data=data or {},
            timeout=30
        )
        return r.json()
    except Exception as e:
        print("Telegram error:", e)
        return None


def answer_callback(callback_id):
    telegram_request(
        "answerCallbackQuery",
        {"callback_query_id": callback_id}
    )


def handle_update(update):
    try:
        # -------------------------------
        # CALLBACK BUTTON
        # -------------------------------
        if "callback_query" in update:
            callback = update["callback_query"]

            callback_id = callback.get("id")
            data = callback.get("data", "")
            message = callback.get("message", {})
            chat = message.get("chat", {})
            chat_id = chat.get("id")

            if callback_id:
                answer_callback(callback_id)

            if str(chat_id) != str(ADMIN_ID):
                bot.send_message(
                    chat_id,
                    "❌ आपको इस bot को use करने की अनुमति नहीं है।"
                )
                return

            if data.startswith("EXAM_"):
                exam = data.replace("EXAM_", "")

                if exam == "ALL":
                    bot.send_message(
                        chat_id,
                        "📢 <b>All Exams</b>\n\n"
                        "UPSC • SSC • Railway/RRB • UPSSSC • BPSC",
                        bot.main_keyboard()
                    )
                else:
                    bot.send_message(
                        chat_id,
                        f"📚 <b>{exam}</b>\n\n"
                        "इस exam के latest available notices check किए जा रहे हैं।",
                        bot.main_keyboard()
                    )

            return

        # -------------------------------
        # NORMAL MESSAGE
        # -------------------------------
        message = update.get("message")

        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()

        if not text:
            return

        # Admin protection
        if str(chat_id) != str(ADMIN_ID):
            bot.send_message(
                chat_id,
                "❌ <b>Unauthorized User</b>\n\n"
                "यह private notice bot है।"
            )
            return

        # -------------------------------
        # COMMANDS
        # -------------------------------

        if text.startswith("/start"):
            bot.send_message(
                chat_id,
                "👋 <b>नमस्ते!</b>\n\n"
                "🎯 <b>Government Exam Notice Board</b> में आपका स्वागत है।\n\n"
                "मैं इन exams के official notices track करता हूँ:\n\n"
                "🇮🇳 UPSC\n"
                "📝 SSC\n"
                "🚆 Railway / RRB\n"
                "🟢 UPSSSC\n"
                "🔵 BPSC\n\n"
                "नीचे menu से option चुनें 👇",
                bot.main_keyboard()
            )
            return

        if text.startswith("/help") or text == "❓ Help":
            bot.send_help(chat_id)
            return

        if text == "📚 Exams" or text.startswith("/exams"):
            bot.send_message(
                chat_id,
                "📚 <b>Exam Select करें</b>\n\n"
                "जिस exam के notices देखना चाहते हैं, उसे चुनें:",
                bot.exam_keyboard()
            )
            return

        if text == "📊 Status" or text.startswith("/status"):
            bot.send_status(chat_id)
            return

        if text == "🆕 New Notices" or text.startswith("/latest"):
            bot.send_latest(chat_id)
            return

        if text == "🔔 All Updates":
            bot.send_latest(chat_id)
            return

        bot.send_message(
            chat_id,
            "🤖 मुझे यह command समझ नहीं आया।\n\n"
            "नीचे दिए menu से option चुनें 👇",
            bot.main_keyboard()
        )

    except Exception as e:
        print("Update handling error:", e)


@app.route("/", methods=["GET"])
def home():
    return "Government Job Notice Bot is running."


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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "bot": "running"
    })


def set_webhook():
    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return

    if not WEBHOOK_URL:
        print("WEBHOOK_URL missing")
        return

    webhook = WEBHOOK_URL.rstrip("/") + "/telegram-webhook"

    result = telegram_request(
        "setWebhook",
        {
            "url": webhook,
            "drop_pending_updates": False
        }
    )

    print("Webhook result:", result)


def notice_scanner():
    """
    Background notice scanner.
    Runs independently from Telegram webhook.
    """

    while True:
        try:
            print("Starting notice scan...")

            # Existing bot main scan
            bot.scan_and_notify()

            print("Notice scan completed.")

        except Exception as e:
            print("Scanner error:", e)

        # 5 minutes
        time.sleep(300)


if __name__ == "__main__":

    # Set Telegram webhook
    set_webhook()

    # Start notice scanner
    scanner = threading.Thread(
        target=notice_scanner,
        daemon=True
    )

    scanner.start()

    # Start web server
    app.run(
        host="0.0.0.0",
        port=PORT
)
