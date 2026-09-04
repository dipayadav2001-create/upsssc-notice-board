import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

QUESTIONS = [
    {
        "q": "भारत का संविधान कब लागू हुआ?",
        "options": [
            "15 अगस्त 1947",
            "26 जनवरी 1950",
            "26 नवंबर 1949",
            "2 अक्टूबर 1950",
        ],
        "answer": 1,
        "explanation": "भारतीय संविधान 26 जनवरी 1950 को लागू हुआ।",
    },
    {
        "q": "भारत के संविधान का संरक्षक किसे माना जाता है?",
        "options": [
            "संसद",
            "राष्ट्रपति",
            "सर्वोच्च न्यायालय",
            "प्रधानमंत्री",
        ],
        "answer": 2,
        "explanation": "सर्वोच्च न्यायालय को संविधान का संरक्षक माना जाता है।",
    },
    {
        "q": "उत्तर प्रदेश की राजधानी कौन-सी है?",
        "options": [
            "कानपुर",
            "प्रयागराज",
            "लखनऊ",
            "वाराणसी",
        ],
        "answer": 2,
        "explanation": "लखनऊ उत्तर प्रदेश की राजधानी है।",
    },
    {
        "q": "भारतीय संविधान में वर्तमान में कितनी अनुसूचियाँ हैं?",
        "options": [
            "10",
            "11",
            "12",
            "13",
        ],
        "answer": 2,
        "explanation": "भारतीय संविधान में वर्तमान में 12 अनुसूचियाँ हैं।",
    },
    {
        "q": "भारत का राष्ट्रीय पशु कौन है?",
        "options": [
            "सिंह",
            "बाघ",
            "हाथी",
            "तेंदुआ",
        ],
        "answer": 1,
        "explanation": "बाघ भारत का राष्ट्रीय पशु है।",
    },
    {
        "q": "UPSSSC का पूरा नाम क्या है?",
        "options": [
            "Uttar Pradesh Staff Selection Commission",
            "Uttar Pradesh Subordinate Services Selection Commission",
            "Uttar Pradesh State Selection Commission",
            "Uttar Pradesh Service Selection Council",
        ],
        "answer": 1,
        "explanation": "UPSSSC का पूरा नाम Uttar Pradesh Subordinate Services Selection Commission है।",
    },
    {
        "q": "SSC का पूरा नाम क्या है?",
        "options": [
            "Staff Selection Commission",
            "State Selection Commission",
            "Service Selection Council",
            "Staff Service Commission",
        ],
        "answer": 0,
        "explanation": "SSC का पूरा नाम Staff Selection Commission है।",
    },
    {
        "q": "भारत में मतदान की न्यूनतम आयु कितनी है?",
        "options": [
            "16 वर्ष",
            "18 वर्ष",
            "21 वर्ष",
            "25 वर्ष",
        ],
        "answer": 1,
        "explanation": "भारत में मतदान की न्यूनतम आयु 18 वर्ष है।",
    },
    {
        "q": "भारतीय संविधान का अनुच्छेद 14 किससे संबंधित है?",
        "options": [
            "स्वतंत्रता का अधिकार",
            "समानता का अधिकार",
            "शिक्षा का अधिकार",
            "धार्मिक स्वतंत्रता",
        ],
        "answer": 1,
        "explanation": "अनुच्छेद 14 कानून के समक्ष समानता और कानूनों के समान संरक्षण से संबंधित है।",
    },
    {
        "q": "भारत का राष्ट्रीय खेल आधिकारिक रूप से कौन-सा है?",
        "options": [
            "हॉकी",
            "क्रिकेट",
            "कबड्डी",
            "कोई आधिकारिक राष्ट्रीय खेल नहीं",
        ],
        "answer": 3,
        "explanation": "भारत सरकार ने किसी खेल को आधिकारिक राष्ट्रीय खेल घोषित नहीं किया है।",
    },
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["score"] = 0
    context.user_data["question_no"] = 0
    context.user_data["questions"] = random.sample(QUESTIONS, min(5, len(QUESTIONS)))

    keyboard = [
        [InlineKeyboardButton("🎯 Quiz शुरू करें", callback_data="start_quiz")]
    ]

    await update.message.reply_text(
        "🎓 <b>EXAM QUIZ BOT</b>\n\n"
        "नमस्ते! 👋\n"
        "UPSSSC / SSC परीक्षा की तैयारी के लिए Quiz शुरू करें।\n\n"
        "📝 Questions: 5\n"
        "🏆 Score: Automatic\n"
        "📖 Explanation: हर प्रश्न के बाद\n\n"
        "👇 नीचे button दबाएँ:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def send_question(query, context):
    questions = context.user_data["questions"]
    no = context.user_data["question_no"]

    if no >= len(questions):
        score = context.user_data["score"]

        await query.edit_message_text(
            f"🏆 <b>QUIZ COMPLETE!</b>\n\n"
            f"📊 Your Score: <b>{score}/{len(questions)}</b>\n\n"
            f"🎯 Accuracy: <b>{score / len(questions) * 100:.0f}%</b>\n\n"
            f"🔥 बहुत बढ़िया! फिर से खेलें:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Play Again", callback_data="restart")]
            ]),
        )
        return

    item = questions[no]

    keyboard = []

    for i, option in enumerate(item["options"]):
        keyboard.append([
            InlineKeyboardButton(
                f"{chr(65+i)}) {option}",
                callback_data=f"answer_{i}",
            )
        ])

    await query.edit_message_text(
        f"🧠 <b>QUESTION {no + 1}/{len(questions)}</b>\n\n"
        f"📌 {item['q']}\n\n"
        f"👇 सही उत्तर चुनें:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "start_quiz":
        context.user_data["question_no"] = 0
        context.user_data["score"] = 0
        await send_question(query, context)
        return

    if query.data == "restart":
        context.user_data["score"] = 0
        context.user_data["question_no"] = 0
        context.user_data["questions"] = random.sample(
            QUESTIONS,
            min(5, len(QUESTIONS))
        )
        await send_question(query, context)
        return

    if query.data.startswith("answer_"):
        selected = int(query.data.split("_")[1])

        questions = context.user_data["questions"]
        no = context.user_data["question_no"]
        item = questions[no]

        correct = item["answer"]

        if selected == correct:
            context.user_data["score"] += 1

            result = "✅ <b>सही उत्तर!</b>"
        else:
            result = (
                "❌ <b>गलत उत्तर!</b>\n"
                f"सही उत्तर: <b>{chr(65+correct)}) "
                f"{item['options'][correct]}</b>"
            )

        await query.edit_message_text(
            f"{result}\n\n"
            f"📖 <b>Explanation:</b>\n"
            f"{item['explanation']}\n\n"
            f"🏆 Score: "
            f"<b>{context.user_data['score']}/{no + 1}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ अगला प्रश्न", callback_data="next")]
            ]),
        )
        return

    if query.data == "next":
        context.user_data["question_no"] += 1
        await send_question(query, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎓 <b>EXAM QUIZ BOT</b>\n\n"
        "/start — Quiz शुरू करें\n"
        "/help — Help\n\n"
        "📝 अभी Private Testing Mode में है।",
        parse_mode="HTML",
    )


def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN missing")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🚀 QUIZ BOT STARTED")
    print("📡 Waiting for Telegram messages...")

    app.run_polling()


if __name__ == "__main__":
    main()
