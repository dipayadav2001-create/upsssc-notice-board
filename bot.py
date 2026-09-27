import os
import re
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
    MessageHandler,
    filters,
)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

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
# HEALTH SERVER
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
# QUESTION BANK - JSON LOADER
# =========================================================

def load_question_bank():

    path = "question_bank.json"

    if not os.path.exists(path):

        print(
            "question_bank.json not found"
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
            "JSON ERROR:",
            e
        )

        return

    if not isinstance(bank, list):

        print(
            "question_bank.json must contain a list"
        )

        return

    conn = get_db()

    cur = conn.cursor()

    inserted = 0

    for q in bank:

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

            if not question:
                continue

            if not isinstance(
                options,
                list
            ):
                continue

            if len(options) < 2:
                continue

            if answer < 0 or answer >= len(options):
                continue

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
                    "General"
                ),

                q.get(
                    "topic",
                    ""
                ),

                question,

                json.dumps(
                    options,
                    ensure_ascii=False
                ),

                answer,

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
                    "Admin"
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

    conn.close()

    print(
        f"{EXAM_NAME}: {total} questions"
    )

    print(
        f"New questions: {inserted}"
    )


load_question_bank()


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(user_id):

    return (
        ADMIN_ID != 0
        and user_id == ADMIN_ID
    )


# =========================================================
# PARSE ADMIN QUESTIONS
# =========================================================

def parse_questions(text):

    text = text.strip()

    pattern = re.compile(
        r"""
        Q(?:uestion)?\.?\s*
        (?P<question>.*?)

        \s*
        A[\)\.\:]\s*
        (?P<a>.*?)

        \s*
        B[\)\.\:]\s*
        (?P<b>.*?)

        \s*
        C[\)\.\:]\s*
        (?P<c>.*?)

        \s*
        D[\)\.\:]\s*
        (?P<d>.*?)

        \s*
        Answer\s*[:\-]\s*
        (?P<answer>[ABCD])

        (?:\s*
        Explanation\s*[:\-]\s*
        (?P<explanation>.*?))?

        (?=
            \n\s*
            Q(?:uestion)?\.?\s*
            |
            $
        )
        """,
        re.IGNORECASE |
        re.DOTALL |
        re.VERBOSE
    )

    matches = list(
        pattern.finditer(text)
    )

    results = []

    for match in matches:

        question = (
            match.group(
                "question"
            )
            .strip()
        )

        options = [

            match.group("a").strip(),

            match.group("b").strip(),

            match.group("c").strip(),

            match.group("d").strip()

        ]

        answer_letter = (
            match.group(
                "answer"
            )
            .upper()
        )

        answer = (
            ord(answer_letter)
            - ord("A")
        )

        explanation = (
            match.group(
                "explanation"
            )
            or ""
        ).strip()

        if question:

            results.append({

                "question": question,

                "options": options,

                "answer": answer,

                "explanation": explanation

            })

    return results


# =========================================================
# SAVE ADMIN QUESTIONS
# =========================================================

def save_uploaded_questions(
    questions
):

    conn = get_db()

    cur = conn.cursor()

    inserted = 0

    duplicate = 0

    for q in questions:

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

                EXAM_NAME,

                "General",

                "",

                q["question"],

                json.dumps(
                    q["options"],
                    ensure_ascii=False
                ),

                q["answer"],

                q["explanation"],

                "Admin Uploaded",

                1,

                "Admin"

            ))

            if cur.rowcount:

                inserted += 1

            else:

                duplicate += 1

        except Exception as e:

            print(
                "SAVE ERROR:",
                e
            )

    conn.commit()

    cur.execute("""
        SELECT COUNT(*)
        FROM questions
        WHERE exam = ?
    """, (EXAM_NAME,))

    total = cur.fetchone()[0]

    conn.close()

    return (
        inserted,
        duplicate,
        total
    )


# =========================================================
# ADMIN COMMANDS
# =========================================================

async def questions_command(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM questions
        WHERE exam = ?
    """, (EXAM_NAME,))

    total = cur.fetchone()[0]

    conn.close()

    await update.message.reply_text(
        f"📚 {EXAM_NAME}\n\n"
        f"Total Questions: {total}\n\n"
        f"Mock के लिए minimum: "
        f"{TOTAL_QUESTIONS}"
    )


async def clear_questions_command(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return

    conn = get_db()

    conn.execute("""
        DELETE FROM questions
        WHERE exam = ?
    """, (EXAM_NAME,))

    conn.commit()
    conn.close()

    await update.message.reply_text(
        "🗑️ UPSSSC PET question bank साफ कर दिया गया।"
    )


# =========================================================
# ADMIN QUESTION MESSAGE
# =========================================================

async def admin_question_message(
    update,
    context
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(
        user.id
    ):

        return

    text = update.message.text or ""

    questions = parse_questions(
        text
    )

    if not questions:

        await update.message.reply_text(
            """
❌ Question format समझ नहीं आया।

इस format में भेजें:

Q. भारत का संविधान कब लागू हुआ?
A) 15 अगस्त 1947
B) 26 जनवरी 1950
C) 26 नवंबर 1949
D) 2 अक्टूबर 1950
Answer: B
Explanation: संविधान 26 जनवरी 1950 को लागू हुआ।
"""
        )

        return

    inserted, duplicate, total = (
        save_uploaded_questions(
            questions
        )
    )

    await update.message.reply_text(

        f"""
✅ QUESTIONS ADDED

📥 Received: {len(questions)}

➕ New Added: {inserted}

♻️ Duplicate: {duplicate}

📚 Total Question Bank: {total}

🎯 Mock में random 25 questions आएंगे।
"""
    )


# =========================================================
# HOME
# =========================================================

def home_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🚀 Start PET Mock",
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
    update,
    context
):

    save_user(
        update.effective_user
    )

    context.user_data.clear()

    await update.message.reply_text(

        """
🎯 <b>UPSSSC PET TEST</b>

📝 25 Questions
⏱️ 20 Minutes
🎯 +1 Correct
❌ -0.25 Wrong

📚 Test 2 sections में होगा।

👇 नीचे से test शुरू करें।
""",

        parse_mode="HTML",

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

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*)
            FROM questions
            WHERE exam = ?
        """, (EXAM_NAME,))

        count = cur.fetchone()[0]

        conn.close()

        await query.edit_message_text(

            f"""
❌ <b>TEST START नहीं हो सकता</b>

Question Bank में अभी:
<b>{count}</b> questions हैं।

कम से कम:
<b>{TOTAL_QUESTIONS}</b> questions चाहिए।

Admin को और questions भेजने होंगे।
""",

            parse_mode="HTML",

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

    context.user_data["current_section"] = 1

    context.user_data["start_time"] = time.time()

    context.user_data["deadline"] = (
        time.time()
        + TOTAL_TIME
    )

    await query.answer(
        "🚀 Test शुरू!"
    )

    await send_section(
        query,
        context,
        1
    )


# =========================================================
# BUILD QUESTION
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

    text = (
        f"\n<b>Q{number}. "
        f"{q['question']}</b>\n\n"
    )

    for i, option in enumerate(
        options
    ):

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
# SEND SECTION
# =========================================================

async def send_section(
    query,
    context,
    section
):

    context.user_data[
        "current_section"
    ] = section

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
        f"📝 <b>UPSSSC PET MOCK</b>\n\n"
        f"<b>{title}</b>\n"
        f"Q{start} – Q{end}\n\n"
        f"⏱️ {minutes:02d}:{seconds:02d}\n"
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

        for i, option in enumerate(
            options
        ):

            if answers.get(number) == i:

                label = f"🔘 {option}"

            else:

                label = option

            row.append(

                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"a:{number}:{i}"
                    )
                )

            )

        keyboard.append(row)

    if section == 1:

        keyboard.append([

            InlineKeyboardButton(
                "➡️ SECTION 2",
                callback_data="section:2"
            )

        ])

    else:

        keyboard.append([

            InlineKeyboardButton(
                "⬅️ SECTION 1",
                callback_data="section:1"
            )

        ])

    keyboard.append([

        InlineKeyboardButton(
            "🏁 SUBMIT TEST",
            callback_data="submit"
        )

    ])

    try:

        await query.edit_message_text(

            text,

            parse_mode="HTML",

            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as e:

        print(
            "SEND SECTION ERROR:",
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
            "⏰ Time समाप्त!",
            show_alert=True
        )

        await finish_test(
            query,
            context
        )

        return

    data = query.data.split(":")

    number = int(
        data[1]
    )

    option = int(
        data[2]
    )

    questions = context.user_data[
        "questions"
    ]

    q = questions[
        number - 1
    ]

    correct_answer = int(
        q["answer"]
    )

    answers = context.user_data[
        "answers"
    ]

    answers[
        number
    ] = option

    if option == correct_answer:

        await query.answer(
            "🎉 सही उत्तर! 🎈🎈🎈",
            show_alert=True
        )

    else:

        options = json.loads(
            q["options"]
        )

        correct_text = options[
            correct_answer
        ]

        await query.answer(

            f"❌ गलत!\n\n"
            f"✅ सही: {correct_text}",

            show_alert=True
        )

    section = (
        1
        if number <= SECTION_1_COUNT
        else 2
    )

    await send_section(
        query,
        context,
        section
    )


# =========================================================
# SECTION
# =========================================================

async def section_click(
    query,
    context
):

    section = int(
        query.data.split(":")[1]
    )

    if remaining_time(context) <= 0:

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
# SUBMIT
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
                "✅ SUBMIT",
                callback_data="submit_yes"
            ),

            InlineKeyboardButton(
                "❌ CANCEL",
                callback_data="submit_cancel"
            )

        ]

    ])

    await query.edit_message_text(

        f"""
🏁 <b>SUBMIT TEST?</b>

📝 Attempted: {attempted}

⏭️ Skipped: {skipped}

क्या आप test submit करना चाहते हैं?
""",

        parse_mode="HTML",

        reply_markup=keyboard
    )


async def submit_cancel(
    query,
    context
):

    section = context.user_data.get(
        "current_section",
        1
    )

    await query.answer(
        "Test जारी है."
    )

    await send_section(
        query,
        context,
        section
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

    attempted = (
        correct
        + wrong
    )

    score = (
        correct
        * MARKS_CORRECT
    ) - (
        wrong
        * NEGATIVE_MARK
    )

    accuracy = 0

    if attempted:

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

    conn.close()

    minutes = total_time // 60
    seconds = total_time % 60

    await query.edit_message_text(

        f"""
🏆 <b>TEST RESULT</b>

<b>{EXAM_NAME}</b>

━━━━━━━━━━━━━━━━━━

📊 Total: {TOTAL_QUESTIONS}

📝 Attempted: {attempted}

✅ Correct: {correct}

❌ Wrong: {wrong}

⏭️ Skipped: {skipped}

━━━━━━━━━━━━━━━━━━

🎯 <b>Score: {score:.2f}</b>

📈 Accuracy: {accuracy:.2f}%

⏱️ Time: {minutes:02d}:{seconds:02d}

━━━━━━━━━━━━━━━━━━

🔥 Test completed!
""",

        parse_mode="HTML",

        reply_markup=InlineKeyboardMarkup([

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
            u.first_name,
            u.username,
            MAX(a.score) AS best_score,
            MAX(a.accuracy) AS best_accuracy,
            MIN(a.total_time) AS fastest
        FROM attempts a
        LEFT JOIN users u
        ON a.user_id = u.user_id
        WHERE a.exam = ?
        GROUP BY a.user_id
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

    text = (
        "🏆 <b>UPSSSC PET RANKING</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    if not rows:

        text += "\nअभी कोई attempt नहीं है।"

    else:

        for i, row in enumerate(
            rows,
            start=1
        ):

            medal = (
                medals[i - 1]
                if i <= 3
                else f"{i}."
            )

            name = (
                row["first_name"]
                or row["username"]
                or "User"
            )

            text += (
                f"\n{medal} "
                f"<b>{name}</b>\n"
                f"   🎯 {row['best_score']:.2f}"
                f" marks\n"
            )

    text += (
        f"\n👥 Total Attempts: "
        f"{total_attempts}"
    )

    await query.edit_message_text(

        text,

        parse_mode="HTML",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🏠 Home",
                    callback_data="home"
                )
            ]

        ])
    )


# =========================================================
# HOME CALLBACK
# =========================================================

async def home(
    query,
    context
):

    context.user_data.clear()

    await query.edit_message_text(

        """
🎯 <b>UPSSSC PET TEST</b>

📝 25 Questions
⏱️ 20 Minutes
🎯 +1 Correct
❌ -0.25 Wrong

👇 Test शुरू करें।
""",

        parse_mode="HTML",

        reply_markup=home_keyboard()
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_router(
    update,
    context
):

    query = update.callback_query

    data = query.data

    if data == "start_test":

        await query.answer()

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

        await query.answer()

        await
