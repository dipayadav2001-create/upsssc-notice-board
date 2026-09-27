import os
import json
import time
import sqlite3
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

PORT = int(os.getenv("PORT", "10000"))

DB_PATH = os.getenv(
    "DB_PATH",
    "exam_prep.db"
)

EXAM_NAME = "UPSSSC PET"

TOTAL_QUESTIONS = 25

SECTION_1_COUNT = 13
SECTION_2_COUNT = 12

TOTAL_TIME = 20 * 60

MARKS_CORRECT = 1
NEGATIVE_MARK = 0.25


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"UPSSSC PET TEST BOT IS RUNNING"
        )

    def log_message(self, format, *args):
        return


def start_health_server():

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )

    print(
        f"Health server running on port {PORT}"
    )

    server.serve_forever()


threading.Thread(
    target=start_health_server,
    daemon=True
).start()


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            created_at INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam TEXT,
            subject TEXT,
            topic TEXT,
            question TEXT UNIQUE,
            options TEXT,
            answer INTEGER,
            explanation TEXT,
            kind TEXT,
            verified INTEGER DEFAULT 0,
            source TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exam TEXT,
            total_questions INTEGER,
            attempted INTEGER,
            correct INTEGER,
            wrong INTEGER,
            skipped INTEGER,
            score REAL,
            accuracy REAL,
            total_time INTEGER,
            created_at INTEGER
        )
    """)

    conn.commit()

    conn.close()


init_db()


# =========================================================
# LOAD QUESTION BANK
# =========================================================

def load_question_bank():

    path = "question_bank.json"

    if not os.path.exists(path):

        print(
            "WARNING: question_bank.json not found"
        )

        return

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            bank = json.load(f)

    except Exception as e:

        print(
            "Question bank error:",
            e
        )

        return

    conn = get_db()

    cur = conn.cursor()

    inserted = 0

    for q in bank:

        try:

            cur.execute("""
                INSERT OR IGNORE INTO questions
                (
                    exam,
                    subject,
                    topic,
                    question,
                    options,
                    answer,
                    explanation,
                    kind,
                    verified,
                    source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (

                q.get(
                    "exam",
                    EXAM_NAME
                ),

                q.get(
                    "subject",
                    ""
                ),

                q.get(
                    "topic",
                    ""
                ),

                q.get(
                    "question",
                    ""
                ),

                json.dumps(
                    q.get(
                        "options",
                        []
                    ),
                    ensure_ascii=False
                ),

                int(
                    q.get(
                        "answer",
                        0
                    )
                ),

                q.get(
                    "explanation",
                    ""
                ),

                q.get(
                    "kind",
                    "Practice"
                ),

                int(
                    q.get(
                        "verified",
                        0
                    )
                ),

                q.get(
                    "source",
                    "Original Practice Question"
                )
            ))

            if cur.rowcount:
                inserted += 1

        except Exception as e:

            print(
                "Question insert error:",
                e
            )

    conn.commit()

    cur.execute("""
        SELECT COUNT(*)
        FROM questions
        WHERE exam = ?
    """, (EXAM_NAME,))

    total = cur.fetchone()[0]

    print(
        f"{EXAM_NAME} Question Bank: {total}"
    )

    print(
        f"New questions: {inserted}"
    )

    conn.close()


load_question_bank()


# =========================================================
# USER
# =========================================================

def save_user(user):

    if not user:
        return

    conn = get_db()

    conn.execute("""
        INSERT OR REPLACE INTO users
        (
            user_id,
            first_name,
            username,
            created_at
        )
        VALUES (
            ?,
            ?,
            ?,
            COALESCE(
                (
                    SELECT created_at
                    FROM users
                    WHERE user_id = ?
                ),
                ?
            )
        )
    """, (

        user.id,

        user.first_name or "",

        user.username or "",

        user.id,

        int(time.time())
    ))

    conn.commit()

    conn.close()


# =========================================================
# HOME
# =========================================================

def home_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🚀 Start PET Mock Test",
                callback_data="start_test"
            )
        ],

        [
            InlineKeyboardButton(
                "🏆 Ranking",
                callback_data="ranking"
            )
        ]

    ])


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    save_user(
        update.effective_user
    )

    context.user_data.clear()

    text = """
🎯 UPSSSC PET TEST

📝 25 Questions
⏱️ 20 Minutes
🎯 1 Mark per Correct Answer
❌ Negative Marking: 0.25

📚 Test 2 Sections में होगा:

SECTION 1
Q1 – Q13

SECTION 2
Q14 – Q25

👇 Test शुरू करें
"""

    await update.message.reply_text(
        text,
        reply_markup=home_keyboard()
    )


# =========================================================
# CREATE TEST
# =========================================================

def create_test():

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM questions
        WHERE exam = ?
        ORDER BY RANDOM()
        LIMIT ?
    """, (
        EXAM_NAME,
        TOTAL_QUESTIONS
    ))

    rows = cur.fetchall()

    conn.close()

    if len(rows) < TOTAL_QUESTIONS:
        return None

    return [
        dict(row)
        for row in rows
    ]


# =========================================================
# TIMER
# =========================================================

def remaining_time(context):

    deadline = context.user_data.get(
        "deadline"
    )

    if not deadline:
        return TOTAL_TIME

    return max(
        0,
        int(
            deadline - time.time()
        )
    )


# =========================================================
# START TEST
# =========================================================

async def start_test(
    query,
    context
):

    questions = create_test()

    if not questions:

        await query.edit_message_text(
            """
❌ Test अभी शुरू नहीं हो सकता।

Question Bank में कम से कम
25 questions होने चाहिए।

अभी 25 questions उपलब्ध नहीं हैं।
""",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 Home",
                        callback_data="home"
                    )
                ]
            ])
        )

        return

    context.user_data.clear()

    context.user_data["questions"] = questions

    context.user_data["answers"] = {}

    context.user_data["finished"] = False

    context.user_data["start_time"] = time.time()

    context.user_data["deadline"] = (
        time.time()
        + TOTAL_TIME
    )

    await query.answer(
        "🚀 Test शुरू हो गया!"
    )

    await send_section(
        query,
        context,
        1
    )


# =========================================================
# BUILD QUESTION TEXT
# =========================================================

def build_question_text(
    q,
    number,
    answers
):

    options = json.loads(
        q["options"]
    )

    selected = answers.get(
        number
    )

    text = f"""

<b>Q{number}. {q["question"]}</b>

"""

    for i, option in enumerate(options):

        if selected == i:

            text += (
                f"🔘 <b>{option}</b>\n"
            )

        else:

            text += (
                f"▫️ {option}\n"
            )

    return text


# =========================================================
# SECTION MESSAGE
# =========================================================

async def send_section(
    query,
    context,
    section
):

    questions = context.user_data[
        "questions"
    ]

    answers = context.user_data[
        "answers"
    ]

    if section == 1:

        start = 1
        end = SECTION_1_COUNT

        title = "📘 SECTION 1"

    else:

        start = SECTION_1_COUNT + 1
        end = TOTAL_QUESTIONS

        title = "📗 SECTION 2"

    remaining = remaining_time(
        context
    )

    minutes = remaining // 60
    seconds = remaining % 60

    text = (
        f"📝 <b>{EXAM_NAME} MOCK TEST</b>\n\n"
        f"{title}\n"
        f"Questions {start}–{end}\n\n"
        f"⏱️ Time Left: "
        f"{minutes:02d}:{seconds:02d}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )

    keyboard = []

    for number in range(
        start,
        end + 1
    ):

        q = questions[number - 1]

        text += build_question_text(
            q,
            number,
            answers
        )

        text += "\n"

        options = json.loads(
            q["options"]
        )

        row = []

        for i, option in enumerate(options):

            selected = (
                answers.get(number) == i
            )

            if selected:

                label = f"🔘 {option}"

            else:

                label = f"{option}"

            row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=f"a:{number}:{i}"
                )
            )

        keyboard.append(row)

    # SECTION SWITCH

    if section == 1:

        keyboard.append([

            InlineKeyboardButton(
                "➡️ Section 2",
                callback_data="section:2"
            )

        ])

    else:

        keyboard.append([

            InlineKeyboardButton(
                "⬅️ Section 1",
                callback_data="section:1"
            )

        ])

    keyboard.append([

        InlineKeyboardButton(
            "🏁 SUBMIT TEST",
            callback_data="submit"
        )

    ])

    markup = InlineKeyboardMarkup(
        keyboard
    )

    try:

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup
        )

    except Exception as e:

        print(
            "send_section error:",
            e
        )


# =========================================================
# ANSWER CLICK
# =========================================================

async def answer_click(
    query,
    context
):

    if context.user_data.get(
        "finished",
        False
    ):

        await query.answer(
            "Test already submitted.",
            show_alert=True
        )

        return

    if remaining_time(context) <= 0:

        await query.answer(
            "⏰ Time समाप्त हो गया!",
            show_alert=True
        )

        await finish_test(
            query,
            context
        )

        return

    data = query.data.split(":")

    number = int(data[1])

    option = int(data[2])

    questions = context.user_data[
        "questions"
    ]

    q = questions[number - 1]

    correct_answer = int(
        q["answer"]
    )

    answers = context.user_data[
        "answers"
    ]

    # -----------------------------------------------------
    # CHANGE ANSWER
    # -----------------------------------------------------

    answers[number] = option

    # -----------------------------------------------------
    # CORRECT
    # -----------------------------------------------------

    if option == correct_answer:

        await query.answer(
            "🎉 सही उत्तर! 🎈🎈🎈",
            show_alert=True
        )

    # -----------------------------------------------------
    # WRONG
    # -----------------------------------------------------

    else:

        options = json.loads(
            q["options"]
        )

        correct_text = options[
            correct_answer
        ]

        await query.answer(
            f"❌ गलत!\n\n"
            f"✅ सही उत्तर: {correct_text}",
            show_alert=True
        )

    # Find current section

    if number <= SECTION_1_COUNT:

        section = 1

    else:

        section = 2

    await send_section(
        query,
        context,
        section
    )


# =========================================================
# SECTION BUTTON
# =========================================================

async def section_click(
    query,
    context
):

    section = int(
        query.data.split(":")[1]
    )

    if remaining_time(context) <= 0:

        await query.answer(
            "⏰ Time समाप्त हो गया!",
            show_alert=True
        )

        await finish_test(
            query,
            context
        )

        return

    await query.answer()

    await send_section(
        query,
        context,
        section
    )


# =========================================================
# SUBMIT CONFIRMATION
# =========================================================

async def submit_confirm(
    query,
    context
):

    if context.user_data.get(
        "finished",
        False
    ):

        return

    answers = context.user_data.get(
        "answers",
        {}
    )

    attempted = len(
        answers
    )

    skipped = (
        TOTAL_QUESTIONS
        - attempted
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "✅ Yes, Submit",
                callback_data="submit_yes"
            ),

            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="submit_cancel"
            )
        ]

    ])

    await query.edit_message_text(

        f"""
🏁 <b>SUBMIT TEST?</b>

Attempted: {attempted}
Skipped: {skipped}

क्या आप test submit करना चाहते हैं?
""",

        parse_mode="HTML",

        reply_markup=keyboard
    )


# =========================================================
# SUBMIT CANCEL
# =========================================================

async def submit_cancel(
    query,
    context
):

    await query.answer(
        "Test जारी है."
    )

    # Determine current section

    current = context.user_data.get(
        "current_section",
        1
    )

    await send_section(
        query,
        context,
        current
    )


# =========================================================
# FINISH TEST
# =========================================================

async def finish_test(
    query,
    context
):

    if context.user_data.get(
        "finished",
        False
    ):

        return

    context.user_data[
        "finished"
    ] = True

    questions = context.user_data[
        "questions"
    ]

    answers = context.user_data[
        "answers"
    ]

    correct = 0
    wrong = 0
    skipped = 0

    for number, q in enumerate(
        questions,
        start=1
    ):

        if number not in answers:

            skipped += 1

            continue

        selected = answers[
            number
        ]

        if selected == int(
            q["answer"]
        ):

            correct += 1

        else:

            wrong += 1

    attempted = correct + wrong

    score = (
        correct * MARKS_CORRECT
    ) - (
        wrong * NEGATIVE_MARK
    )

    accuracy = 0

    if attempted > 0:

        accuracy = (
            correct
            / attempted
        ) * 100

    total_time = int(
        time.time()
        - context.user_data.get(
            "start_time",
            time.time()
        )
    )

    user = query.from_user

    save_user(user)

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO attempts
        (
            user_id,
            exam,
            total_questions,
            attempted,
            correct,
            wrong,
            skipped,
            score,
            accuracy,
            total_time,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        user.id,

        EXAM_NAME,

        TOTAL_QUESTIONS,

        attempted,

        correct,

        wrong,

        skipped,

        score,

        accuracy,

        total_time,

        int(time.time())
    ))

    conn.commit()

    attempt_id = cur.lastrowid

    conn.close()

    minutes = total_time // 60
    seconds = total_time % 60

    text = f"""
🏆 <b>TEST RESULT</b>

<b>{EXAM_NAME}</b>

━━━━━━━━━━━━━━━━━━

📊 Total Questions: {TOTAL_QUESTIONS}

📝 Attempted: {attempted}

✅ Correct: {correct}

❌ Wrong: {wrong}

⏭️ Skipped: {skipped}

━━━━━━━━━━━━━━━━━━

🎯 <b>Score: {score:.2f}</b>

📈 Accuracy: {accuracy:.2f}%

⏱️ Time: {minutes:02d}:{seconds:02d}

━━━━━━━━━━━━━━━━━━

अच्छा प्रयास! 🔥
"""

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🏆 Ranking",
                callback_data="ranking"
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 New Test",
                callback_data="start_test"
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 Home",
                callback_data="home"
            )
        ]

    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# RANKING
# =========================================================

async def ranking(
    query,
    context
):

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT
            user_id,
            MAX(score) AS best_score,
            MAX(accuracy) AS best_accuracy,
            MIN(total_time) AS fastest
        FROM attempts
        WHERE exam = ?
        GROUP BY user_id
        ORDER BY
            best_score DESC,
            best_accuracy DESC,
            fastest ASC
        LIMIT 10
    """, (EXAM_NAME,))

    rows = cur.fetchall()

    cur.execute("""
        SELECT COUNT(*)
        FROM attempts
        WHERE exam = ?
    """, (EXAM_NAME,))

    total_attempts = cur.fetchone()[0]

    conn.close()

    text = """
🏆 <b>UPSSSC PET RANKING</b>

━━━━━━━━━━━━━━━━━━
"""

    if not rows:

        text += "\nअभी कोई attempt नहीं है."

    else:

        medals = [
            "🥇",
            "🥈",
            "🥉"
        ]

        for i, row in enumerate(
            rows,
            start=1
        ):

            medal = (
                medals[i - 1]
                if i <= 3
                else f"{i}."
            )

            text += (
                f"\n{medal} "
                f"<b>{row['best_score']:.2f}</b> "
                f"marks"
            )

    text += (
        f"\n\n👥 Total Attempts: "
        f"{total_attempts}"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🏠 Home",
                callback_data="home"
            )
        ]

    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# HOME CALLBACK
# =========================================================

async def home(
    query,
    context
):

    context.user_data.clear()

    text = """
🎯 <b>UPSSSC PET TEST</b>

📝 25 Questions
⏱️ 20 Minutes
🎯 +1 Correct
❌ -0.25 Wrong

👇 नीचे से test शुरू करें।
"""

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=home_keyboard()
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    if data == "start_test":

        await start_test(
            query,
            context
        )

    elif data.startswith("a:"):

        await answer_click(
            query,
            context
        )

    elif data.startswith("section:"):

        await section_click(
            query,
            context
        )

    elif data == "submit":

        await submit_confirm(
            query,
            context
        )

    elif data == "submit_yes":

        await finish_test(
            query,
            context
        )

    elif data == "submit_cancel":

        await submit_cancel(
            query,
            context
        )

    elif data == "ranking":

        await ranking(
            query,
            context
        )

    elif data == "home":

        await home(
            query,
            context
        )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update,
    context
):

    print(
        "BOT ERROR:",
        context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable missing."
        )

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    app.add_error_handler(
        error_handler
    )

    print(
        "================================"
    )

    print(
        "UPSSSC PET TEST BOT STARTED"
    )

    print(
        "25 Questions / 20 Minutes"
    )

    print(
        "================================"
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":

    main()
