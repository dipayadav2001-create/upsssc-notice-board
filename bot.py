import os
import json
import random
import sqlite3
import time
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
DB_PATH = os.getenv("DB_PATH", "pet_mock.db")

TEST_NAME = "UPSSSC PET Mock Test"

TOTAL_QUESTIONS = 25
TEST_TIME = 20 * 60

MARKS_CORRECT = 2
NEGATIVE_MARK = 0.50

QUESTIONS_FILE = "question_bank.json"


# =========================================================
# HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"UPSSSC PET MOCK BOT IS RUNNING")

    def log_message(self, format, *args):
        pass


def start_health_server():

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
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

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT UNIQUE,
            options TEXT NOT NULL,
            answer INTEGER NOT NULL,
            explanation TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            created_at INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            score REAL,
            correct INTEGER,
            wrong INTEGER,
            skipped INTEGER,
            accuracy REAL,
            time_taken INTEGER,
            created_at INTEGER
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# LOAD QUESTIONS
# =========================================================

def load_questions():

    if not os.path.exists(QUESTIONS_FILE):

        print(
            "ERROR: question_bank.json not found."
        )

        return

    try:

        with open(
            QUESTIONS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

    except Exception as e:

        print(
            "JSON ERROR:",
            e
        )

        return

    if not isinstance(data, list):

        print(
            "ERROR: question_bank.json must contain a JSON array."
        )

        return

    conn = get_db()
    cur = conn.cursor()

    added = 0

    for q in data:

        try:

            question = str(
                q.get("question", "")
            ).strip()

            options = q.get(
                "options",
                []
            )

            answer = int(
                q.get(
                    "answer",
                    0
                )
            )

            explanation = q.get(
                "explanation",
                ""
            )

            if not question:
                continue

            if not isinstance(options, list):
                continue

            if len(options) != 4:
                continue

            if answer < 0 or answer > 3:
                continue

            cur.execute("""
                INSERT OR IGNORE INTO questions
                (
                    question,
                    options,
                    answer,
                    explanation
                )
                VALUES (?, ?, ?, ?)
            """, (
                question,
                json.dumps(
                    options,
                    ensure_ascii=False
                ),
                answer,
                explanation
            ))

            if cur.rowcount:
                added += 1

        except Exception as e:

            print(
                "Question error:",
                e
            )

    conn.commit()

    cur.execute(
        "SELECT COUNT(*) FROM questions"
    )

    total = cur.fetchone()[0]

    conn.close()

    print(
        f"Question bank: {total} questions"
    )

    print(
        f"New questions added: {added}"
    )


load_questions()


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
# KEYBOARDS
# =========================================================

def home_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📝 Start Mock Test",
                callback_data="start_test"
            )
        ],

        [
            InlineKeyboardButton(
                "🏆 Ranking",
                callback_data="ranking"
            ),

            InlineKeyboardButton(
                "📊 My Result",
                callback_data="my_result"
            )
        ]

    ])


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    save_user(
        update.effective_user
    )

    context.user_data.clear()

    text = f"""
🎯 {TEST_NAME}

25 Questions
⏱️ Time: 20 Minutes
📝 2 Marks per correct answer
❌ Negative Marking: 0.50

पूरे 25 questions एक साथ मिलेंगे।

Q1–Q13 पहले section में
Q14–Q25 दूसरे section में

कोई Next Question नहीं होगा।

👇 Test शुरू करने के लिए नीचे button दबाएँ।
"""

    await update.message.reply_text(
        text,
        reply_markup=home_keyboard()
    )


# =========================================================
# START TEST
# =========================================================

async def start_test(
    query,
    context
):

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM questions
        ORDER BY RANDOM()
        LIMIT ?
    """, (
        TOTAL_QUESTIONS,
    ))

    rows = cur.fetchall()

    conn.close()

    if len(rows) < TOTAL_QUESTIONS:

        await query.edit_message_text(
            "❌ Test अभी शुरू नहीं हो सकता।\n\n"
            f"Database में कम से कम "
            f"{TOTAL_QUESTIONS} questions चाहिए।\n\n"
            f"अभी केवल {len(rows)} questions हैं।"
        )

        return

    questions = [
        dict(row)
        for row in rows
    ]

    context.user_data.clear()

    context.user_data[
        "test_questions"
    ] = questions

    context.user_data[
        "answers"
    ] = {}

    context.user_data[
        "test_start"
    ] = time.time()

    context.user_data[
        "deadline"
    ] = (
        time.time()
        + TEST_TIME
    )

    context.user_data[
        "finished"
    ] = False

    await query.edit_message_text(
        "⏳ Test तैयार है...\n\n"
        "25 questions नीचे दिए जाएंगे।"
    )

    await send_test(
        query,
        context
    )


# =========================================================
# TIMER
# =========================================================

def get_remaining(context):

    deadline = context.user_data.get(
        "deadline"
    )

    if not deadline:
        return TEST_TIME

    return max(
        0,
        int(
            deadline - time.time()
        )
    )


# =========================================================
# SEND TEST
# =========================================================

async def send_test(
    query,
    context
):

    questions = context.user_data.get(
        "test_questions"
    )

    if not questions:
        return

    remaining = get_remaining(
        context
    )

    minutes = remaining // 60
    seconds = remaining % 60

    answers = context.user_data.get(
        "answers",
        {}
    )

    # -----------------------------------------------------
    # SECTION 1
    # -----------------------------------------------------

    text1 = f"""
📝 {TEST_NAME}

⏱️ Time Left: {minutes:02d}:{seconds:02d}

━━━━━━━━━━━━━━━━━━
📄 SECTION 1
Questions 1–13
━━━━━━━━━━━━━━━━━━

"""

    for i in range(13):

        q = questions[i]

        selected = answers.get(
            str(i)
        )

        text1 += (
            f"\nQ{i + 1}. "
            f"{q['question']}\n"
        )

        options = json.loads(
            q["options"]
        )

        for j, option in enumerate(options):

            mark = "○"

            if selected == j:
                mark = "🔘"

            text1 += (
                f"{mark} {option}\n"
            )

    buttons1 = []

    for i in range(13):

        row = []

        for j in range(4):

            selected = (
                answers.get(str(i))
                == j
            )

            prefix = "🔘" if selected else "○"

            row.append(
                InlineKeyboardButton(
                    prefix,
                    callback_data=f"a:{i}:{j}"
                )
            )

        buttons1.append(row)

    markup1 = InlineKeyboardMarkup(
        buttons1
    )

    try:

        await query.message.reply_text(
            text1,
            reply_markup=markup1
        )

    except Exception as e:

        print(
            "Section 1 error:",
            e
        )

    # -----------------------------------------------------
    # SECTION 2
    # -----------------------------------------------------

    text2 = f"""
━━━━━━━━━━━━━━━━━━
📄 SECTION 2
Questions 14–25
━━━━━━━━━━━━━━━━━━

"""

    for i in range(13, 25):

        q = questions[i]

        selected = answers.get(
            str(i)
        )

        text2 += (
            f"\nQ{i + 1}. "
            f"{q['question']}\n"
        )

        options = json.loads(
            q["options"]
        )

        for j, option in enumerate(options):

            mark = "○"

            if selected == j:
                mark = "🔘"

            text2 += (
                f"{mark} {option}\n"
            )

    buttons2 = []

    for i in range(13, 25):

        row = []

        for j in range(4):

            selected = (
                answers.get(str(i))
                == j
            )

            prefix = "🔘" if selected else "○"

            row.append(
                InlineKeyboardButton(
                    prefix,
                    callback_data=f"a:{i}:{j}"
                )
            )

        buttons2.append(row)

    buttons2.append([

        InlineKeyboardButton(
            "🏁 SUBMIT TEST",
            callback_data="submit"
        )

    ])

    markup2 = InlineKeyboardMarkup(
        buttons2
    )

    try:

        await query.message.reply_text(
            text2,
            reply_markup=markup2
        )

    except Exception as e:

        print(
            "Section 2 error:",
            e
        )


# =========================================================
# ANSWER CLICK
# =========================================================

async def answer_click(
    query,
    context,
    question_index,
    option_index
):

    if context.user_data.get(
        "finished",
        False
    ):

        await query.answer(
            "Test already submitted."
        )

        return

    if get_remaining(context) <= 0:

        await query.answer(
            "⏰ Time समाप्त हो गया।"
        )

        await finish_test(
            query,
            context
        )

        return

    answers = context.user_data.setdefault(
        "answers",
        {}
    )

    answers[
        str(question_index)
    ] = option_index

    await query.answer(
        "Answer saved ✓"
    )

    # Button state update
    try:

        await update_answer_buttons(
            query,
            context
        )

    except Exception as e:

        print(
            "Button update error:",
            e
        )


# =========================================================
# UPDATE BUTTONS
# =========================================================

async def update_answer_buttons(
    query,
    context
):

    answers = context.user_data.get(
        "answers",
        {}
    )

    rows = []

    # Determine whether this message
    # belongs to section 1 or section 2.
    first_index = (
        0
        if query.message.message_id
        else 0
    )

    # We identify based on callback/message
    # by checking stored section messages.
    section = context.user_data.get(
        "last_section",
        None
    )

    # Telegram callback itself contains
    # the selected question, so simply
    # recreate both possible ranges.
    #
    # To avoid changing message text,
    # only answer buttons are rebuilt.

    # Find selected question from callback
    data = query.data.split(":")

    q_index = int(data[1])

    if q_index < 13:

        start = 0
        end = 13

    else:

        start = 13
        end = 25

    for i in range(start, end):

        row = []

        for j in range(4):

            selected = (
                answers.get(str(i))
                == j
            )

            prefix = "🔘" if selected else "○"

            row.append(
                InlineKeyboardButton(
                    prefix,
                    callback_data=f"a:{i}:{j}"
                )
            )

        rows.append(row)

    if start == 13:

        rows.append([

            InlineKeyboardButton(
                "🏁 SUBMIT TEST",
                callback_data="submit"
            )

        ])

    try:

        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(rows)
        )

    except Exception as e:

        print(
            "Reply markup error:",
            e
        )


# =========================================================
# SUBMIT
# =========================================================

async def submit_test(
    query,
    context
):

    await finish_test(
        query,
        context
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

        await query.answer(
            "Test already submitted."
        )

        return

    questions = context.user_data.get(
        "test_questions"
    )

    answers = context.user_data.get(
        "answers",
        {}
    )

    if not questions:

        await query.answer(
            "Test data not found."
        )

        return

    context.user_data[
        "finished"
    ] = True

    time_taken = int(
        time.time()
        - context.user_data.get(
            "test_start",
            time.time()
        )
    )

    if time_taken > TEST_TIME:
        time_taken = TEST_TIME

    correct = 0
    wrong = 0
    skipped = 0

    for i, q in enumerate(questions):

        selected = answers.get(
            str(i)
        )

        if selected is None:

            skipped += 1

        elif selected == q["answer"]:

            correct += 1

        else:

            wrong += 1

    score = (
        correct * MARKS_CORRECT
        - wrong * NEGATIVE_MARK
    )

    attempted = (
        correct + wrong
    )

    accuracy = 0

    if attempted:

        accuracy = (
            correct
            / attempted
            * 100
        )

    user = query.from_user

    save_user(user)

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO attempts
        (
            user_id,
            score,
            correct,
            wrong,
            skipped,
            accuracy,
            time_taken,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user.id,
        score,
        correct,
        wrong,
        skipped,
        accuracy,
        time_taken,
        int(time.time())
    ))

    attempt_id = cur.lastrowid

    conn.commit()

    # Ranking
    cur.execute("""
        SELECT COUNT(*)
        FROM attempts
        WHERE score > ?
        OR (
            score = ?
            AND time_taken < ?
        )
    """, (
        score,
        score,
        time_taken
    ))

    better = cur.fetchone()[0]

    rank = better + 1

    cur.execute(
        "SELECT COUNT(*) FROM attempts"
    )

    participants = cur.fetchone()[0]

    conn.commit()
    conn.close()

    minutes = time_taken // 60
    seconds = time_taken % 60

    result_text = f"""
🏆 TEST COMPLETED

🎯 {TEST_NAME}

━━━━━━━━━━━━━━━━━━

📊 SCORE
{score:.2f} / 50

✅ Correct: {correct}
❌ Wrong: {wrong}
⏭️ Skipped: {skipped}

🎯 Accuracy: {accuracy:.2f}%

⏱️ Time Taken:
{minutes:02d}:{seconds:02d}

━━━━━━━━━━━━━━━━━━

🏅 Rank: #{rank}
👥 Participants: {participants}
"""

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🔄 New Test",
                callback_data="start_test"
            )
        ],

        [
            InlineKeyboardButton(
                "🏆 Ranking",
                callback_data="ranking"
            ),

            InlineKeyboardButton(
                "📊 My Result",
                callback_data="my_result"
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 Home",
                callback_data="home"
            )
        ]

    ])

    await query.message.reply_text(
        result_text,
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
            a.user_id,
            a.score,
            a.time_taken,
            u.first_name,
            u.username
        FROM attempts a
        LEFT JOIN users u
        ON a.user_id = u.user_id
        ORDER BY
            a.score DESC,
            a.time_taken ASC,
            a.created_at ASC
        LIMIT 10
    """)

    rows = cur.fetchall()

    conn.close()

    text = """
🏆 TOP 10 RANKING

━━━━━━━━━━━━━━━━━━
"""

    if not rows:

        text += "\nअभी कोई attempt नहीं है।"

    else:

        for i, row in enumerate(
            rows,
            start=1
        ):

            name = (
                row["first_name"]
                or row["username"]
                or "User"
            )

            minutes = (
                row["time_taken"]
                // 60
            )

            seconds = (
                row["time_taken"]
                % 60
            )

            text += (
                f"\n{i}. {name}\n"
                f"   🎯 {row['score']:.2f}"
                f" | ⏱️ {minutes:02d}:{seconds:02d}\n"
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
        reply_markup=keyboard
    )


# =========================================================
# MY RESULT
# =========================================================

async def my_result(
    query,
    context
):

    user_id = query.from_user.id

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM attempts
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (
        user_id,
    ))

    row = cur.fetchone()

    cur.execute("""
        SELECT
            MAX(score) AS best_score,
            COUNT(*) AS attempts
        FROM attempts
        WHERE user_id = ?
    """, (
        user_id,
    ))

    stats = cur.fetchone()

    conn.close()

    if not row:

        text = """
📊 MY RESULT

अभी आपने कोई test नहीं दिया है।
"""

    else:

        text = f"""
📊 MY RESULT

━━━━━━━━━━━━━━━━━━

Latest Score:
🎯 {row['score']:.2f}/50

✅ Correct: {row['correct']}
❌ Wrong: {row['wrong']}
⏭️ Skipped: {row['skipped']}

🎯 Accuracy:
{row['accuracy']:.2f}%

⏱️ Time:
{row['time_taken'] // 60:02d}:
{row['time_taken'] % 60:02d}

━━━━━━━━━━━━━━━━━━

🏆 Best Score:
{stats['best_score']:.2f}

📝 Total Attempts:
{stats['attempts']}
"""

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
        reply_markup=keyboard
    )


# =========================================================
# HOME CALLBACK
# =========================================================

async def home(
    query,
    context
):

    await query.edit_message_text(
        f"""
🎯 {TEST_NAME}

25 Random Questions
⏱️ 20 Minutes
❌ Negative Marking: 0.50

👇 Choose an option
""",
        reply_markup=home_keyboard()
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    save_user(
        query.from_user
    )

    if data == "home":

        await home(
            query,
            context
        )

    elif data == "start_test":

        await start_test(
            query,
            context
        )

    elif data == "submit":

        await submit_test(
            query,
            context
        )

    elif data == "ranking":

        await ranking(
            query,
            context
        )

    elif data == "my_result":

        await my_result(
            query,
            context
        )

    elif data.startswith("a:"):

        parts = data.split(":")

        question_index = int(
            parts[1]
        )

        option_index = int(
            parts[2]
        )

        await answer_click(
            query,
            context,
            question_index,
            option_index
        )


# =========================================================
# RUN BOT
# =========================================================

def main():

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable missing."
        )

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    print(
        "UPSSCC PET Mock Bot started..."
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":

    main()
