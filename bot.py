import os
import json
import random
import sqlite3
import time
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "exam_prep.db")
PORT = int(os.getenv("PORT", "10000"))

EXAM = "SSC CGL"
MOCK_NAME = "SSC CGL Tier-I"

SECTIONS = [
    ("General Intelligence & Reasoning", "Reasoning"),
    ("General Awareness", "General Awareness"),
    ("Quantitative Aptitude", "Maths"),
    ("English Comprehension", "English"),
]

QUESTIONS_PER_SECTION = 25
SECTION_TIME = 15 * 60
NEGATIVE_MARK = 0.50


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"EXAMPREP OK"

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )
            self.send_header(
                "Content-Length",
                str(len(body))
            )
            self.end_headers()

            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        return


def start_health_server():
    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )

    print(
        f"Health server running on "
        f"0.0.0.0:{PORT}"
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True
    )

    thread.start()

    return server


# =========================================================
# DATABASE
# =========================================================

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():

    con = db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            target_exam TEXT DEFAULT 'SSC CGL',
            created_at TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam TEXT NOT NULL,
            subject TEXT NOT NULL,
            topic TEXT,
            question TEXT NOT NULL,
            options TEXT NOT NULL,
            answer INTEGER NOT NULL,
            explanation TEXT,
            kind TEXT DEFAULT 'Practice',
            year INTEGER,
            shift TEXT,
            source TEXT,
            verified INTEGER DEFAULT 0,
            difficulty TEXT DEFAULT 'Mixed'
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exam TEXT,
            mode TEXT,
            score REAL,
            total INTEGER,
            correct INTEGER,
            wrong INTEGER,
            skipped INTEGER,
            seconds INTEGER,
            negative_marks REAL,
            accuracy REAL,
            created_at TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER,
            question_id INTEGER,
            selected INTEGER,
            correct INTEGER,
            seconds INTEGER,
            marked_review INTEGER DEFAULT 0
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS saved_questions (
            user_id INTEGER,
            question_id INTEGER,
            created_at TEXT,
            PRIMARY KEY(user_id, question_id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS wrong_questions (
            user_id INTEGER,
            question_id INTEGER,
            created_at TEXT,
            PRIMARY KEY(user_id, question_id)
        )
    """)

    con.commit()

    load_question_bank(con)

    con.close()


# =========================================================
# QUESTION BANK
# =========================================================

def load_question_bank(con):

    count = con.execute("""
        SELECT COUNT(*)
        FROM questions
        WHERE exam=?
    """, (EXAM,)).fetchone()[0]

    if count >= 100:
        return

    path = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        "question_bank.json"
    )

    if not os.path.exists(path):
        print("question_bank.json not found")
        return

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

    except Exception as e:
        print("Question bank error:", e)
        return

    for item in data:

        exists = con.execute("""
            SELECT id
            FROM questions
            WHERE exam=?
            AND question=?
            LIMIT 1
        """, (
            item.get("exam", EXAM),
            item["question"]
        )).fetchone()

        if exists:
            continue

        con.execute("""
            INSERT INTO questions (
                exam,
                subject,
                topic,
                question,
                options,
                answer,
                explanation,
                kind,
                year,
                shift,
                source,
                verified,
                difficulty
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("exam", EXAM),
            item["subject"],
            item.get("topic", "General"),
            item["question"],
            json.dumps(
                item["options"],
                ensure_ascii=False
            ),
            int(item["answer"]),
            item.get("explanation", ""),
            item.get("kind", "Practice"),
            item.get("year"),
            item.get("shift"),
            item.get("source"),
            int(item.get("verified", 0)),
            item.get("difficulty", "Mixed")
        ))

    con.commit()

    print(
        "Question bank loaded:",
        len(data)
    )


# =========================================================
# USER
# =========================================================

def save_user(user):

    con = db()

    con.execute("""
        INSERT OR IGNORE INTO users
        (user_id, name, target_exam, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        user.id,
        user.first_name or "Aspirant",
        EXAM,
        datetime.now(
            timezone.utc
        ).isoformat()
    ))

    con.execute("""
        UPDATE users
        SET name=?
        WHERE user_id=?
    """, (
        user.first_name or "Aspirant",
        user.id
    ))

    con.commit()
    con.close()


# =========================================================
# KEYBOARDS
# =========================================================

def home_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "⚡ Quiz",
                callback_data="quiz"
            ),
            InlineKeyboardButton(
                "📝 Mock Test",
                callback_data="mock"
            )
        ],

        [
            InlineKeyboardButton(
                "📚 Practice",
                callback_data="practice"
            ),
            InlineKeyboardButton(
                "📜 PYQ",
                callback_data="pyq"
            )
        ],

        [
            InlineKeyboardButton(
                "📰 Current Affairs",
                callback_data="ca"
            )
        ],

        [
            InlineKeyboardButton(
                "📊 My Performance",
                callback_data="performance"
            ),
            InlineKeyboardButton(
                "❌ Wrong Questions",
                callback_data="wrong"
            )
        ],

        [
            InlineKeyboardButton(
                "🔖 Saved Questions",
                callback_data="saved"
            ),
            InlineKeyboardButton(
                "🏆 Leaderboard",
                callback_data="leaderboard"
            )
        ],

        [
            InlineKeyboardButton(
                "👤 Profile",
                callback_data="profile"
            ),
            InlineKeyboardButton(
                "❓ Help",
                callback_data="help"
            )
        ]
    ])


def home_button():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🏠 Home",
                callback_data="home"
            )
        ]
    ])


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    save_user(update.effective_user)

    context.user_data.clear()

    text = f"""
🧠 EXAMPREP

नमस्ते 👋

🎯 अभी focus: {EXAM}

⚡ Quiz और 📝 Mock Test अलग-अलग हैं।

⚡ Quiz = Practice
📝 Mock Test = Real Exam Simulation

नीचे से अपना विकल्प चुनें:
"""

    await update.message.reply_text(
        text,
        reply_markup=home_keyboard(),
        reply_markup_remove=False
    )


# =========================================================
# HOME
# =========================================================

async def show_home(query):

    text = """
🧠 EXAMPREP

🎯 SSC CGL Preparation

अपना विकल्प चुनें:
"""

    await query.edit_message_text(
        text,
        reply_markup=home_keyboard()
    )


# =========================================================
# MOCK INTRO
# =========================================================

async def mock_intro(query):

    con = db()

    sections_ok = True

    for subject, short in SECTIONS:

        count = con.execute("""
            SELECT COUNT(*)
            FROM questions
            WHERE exam=?
            AND subject=?
        """, (
            EXAM,
            subject
        )).fetchone()[0]

        if count < QUESTIONS_PER_SECTION:
            sections_ok = False

    total = con.execute("""
        SELECT COUNT(*)
        FROM questions
        WHERE exam=?
    """, (EXAM,)).fetchone()[0]

    con.close()

    if not sections_ok:

        await query.edit_message_text(
            f"""
📝 {MOCK_NAME}

⚠️ अभी पूरा mock तैयार नहीं है।

Question Bank:
{total}/100 questions available

हर section में 25 questions चाहिए।

📌 पहले question bank पूरा load करना होगा।
""",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📥 Import Guide",
                        callback_data="import"
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

        return

    text = f"""
📝 {MOCK_NAME}

📌 परीक्षा pattern

• Total Questions: 100
• Total Marks: 200
• Total Time: 60 minutes

📚 Sections:

1️⃣ Reasoning — 25
2️⃣ General Awareness — 25
3️⃣ Maths — 25
4️⃣ English — 25

⏱️ प्रत्येक section: 15 minutes

➖ Wrong Answer: -0.50 marks

⏭️ Section timer समाप्त होने पर
अगले section में automatically जाएंगे।

⚠️ एक बार mock शुरू करने के बाद
exam mode में वापस नहीं जा सकते।
"""

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🚀 Start Mock",
                    callback_data="mock_start"
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
# CREATE MOCK
# =========================================================

def create_mock(user_id):

    con = db()

    questions = []

    for subject, short in SECTIONS:

        rows = con.execute("""
            SELECT *
            FROM questions
            WHERE exam=?
            AND subject=?
            ORDER BY RANDOM()
            LIMIT ?
        """, (
            EXAM,
            subject,
            QUESTIONS_PER_SECTION
        )).fetchall()

        if len(rows) != QUESTIONS_PER_SECTION:
            con.close()
            return None

        questions.extend(
            [dict(r) for r in rows]
        )

    con.close()

    return questions


# =========================================================
# SHOW QUESTION
# =========================================================

async def show_question(
    query,
    context,
    edit=True
):

    questions = context.user_data.get(
        "mock_questions"
    )

    index = context.user_data.get(
        "mock_index",
        0
    )

    if not questions:
        return

    q = questions[index]

    options = json.loads(q["options"])

    selected = context.user_data.get(
        "answers",
        {}
    ).get(str(q["id"]))

    section_index = index // QUESTIONS_PER_SECTION

    section_name = SECTIONS[
        section_index
    ][1]

    number = index + 1

    text = f"""
📝 {MOCK_NAME}

📚 Section: {section_name}

❓ Question {number}/100

{q["question"]}
"""

    buttons = []

    for i, option in enumerate(options):

        prefix = "▫️"

        if selected == i:
            prefix = "✅"

        buttons.append([
            InlineKeyboardButton(
                f"{prefix} {option}",
                callback_data=f"ans:{i}"
            )
        ])

    nav = []

    if index > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data="prev"
            )
        )

    if index < len(questions) - 1:
        nav.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data="next"
            )
        )

    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(
            "🔖 Mark for Review",
            callback_data="review"
        ),
        InlineKeyboardButton(
            "🧹 Clear",
            callback_data="clear"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "📋 Question List",
            callback_data="qgrid"
        ),
        InlineKeyboardButton(
            "🏁 Submit",
            callback_data="submit"
        )
    ])

    markup = InlineKeyboardMarkup(buttons)

    if edit:
        await query.edit_message_text(
            text,
            reply_markup=markup
        )


# =========================================================
# ANSWER
# =========================================================

async def answer_question(
    query,
    context,
    option
):

    answers = context.user_data.setdefault(
        "answers",
        {}
    )

    index = context.user_data.get(
        "mock_index",
        0
    )

    questions = context.user_data.get(
        "mock_questions"
    )

    q = questions[index]

    answers[str(q["id"])] = option

    await show_question(
        query,
        context
    )


# =========================================================
# QUESTION NAVIGATION
# =========================================================

async def move_question(
    query,
    context,
    direction
):

    questions = context.user_data.get(
        "mock_questions"
    )

    index = context.user_data.get(
        "mock_index",
        0
    )

    new_index = index + direction

    if new_index < 0:
        new_index = 0

    if new_index >= len(questions):
        new_index = len(questions) - 1

    context.user_data["mock_index"] = new_index

    await show_question(
        query,
        context
    )


# =========================================================
# CLEAR
# =========================================================

async def clear_answer(
    query,
    context
):

    questions = context.user_data[
        "mock_questions"
    ]

    index = context.user_data[
        "mock_index"
    ]

    q = questions[index]

    answers = context.user_data.setdefault(
        "answers",
        {}
    )

    answers.pop(
        str(q["id"]),
        None
    )

    await show_question(
        query,
        context
    )


# =========================================================
# REVIEW
# =========================================================

async def mark_review(
    query,
    context
):

    reviews = context.user_data.setdefault(
        "reviews",
        set()
    )

    questions = context.user_data[
        "mock_questions"
    ]

    index = context.user_data[
        "mock_index"
    ]

    qid = questions[index]["id"]

    if qid in reviews:
        reviews.remove(qid)
        message = "🔖 Review mark हटाया गया।"
    else:
        reviews.add(qid)
        message = "🔖 Question Mark for Review किया गया।"

    await query.answer(message)

    await show_question(
        query,
        context
    )


# =========================================================
# QUESTION GRID
# =========================================================

async def question_grid(
    query,
    context
):

    questions = context.user_data[
        "mock_questions"
    ]

    answers = context.user_data.get(
        "answers",
        {}
    )

    reviews = context.user_data.get(
        "reviews",
        set()
    )

    rows = []

    for start in range(
        0,
        len(questions),
        10
    ):

        row = []

        for i in range(
            start,
            min(start + 10, len(questions))
        ):

            qid = str(
                questions[i]["id"]
            )

            if i == context.user_data.get(
                "mock_index",
                0
            ):
                symbol = "🔵"

            elif i in reviews:
                symbol = "🔖"

            elif qid in answers:
                symbol = "🟢"

            else:
                symbol = "⚪"

            row.append(
                InlineKeyboardButton(
                    f"{symbol}{i+1}",
                    callback_data=f"goto:{i}"
                )
            )

        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data="back_question"
        ),
        InlineKeyboardButton(
            "🏁 Submit",
            callback_data="submit"
        )
    ])

    await query.edit_message_text(
        """
📋 Question Navigator

🟢 Answered
🔖 Review
⚪ Not Attempted
🔵 Current
""",
        reply_markup=InlineKeyboardMarkup(rows)
    )


# =========================================================
# SUBMIT CONFIRMATION
# =========================================================

async def submit_confirmation(
    query,
    context
):

    questions = context.user_data[
        "mock_questions"
    ]

    answers = context.user_data.get(
        "answers",
        {}
    )

    reviews = context.user_data.get(
        "reviews",
        set()
    )

    attempted = len(answers)

    skipped = len(
        questions
    ) - attempted

    text = f"""
🏁 Submit Mock Test?

📊 Summary

Total: 100
Attempted: {attempted}
Skipped: {skipped}
🔖 Review: {len(reviews)}

क्या आप test submit करना चाहते हैं?
"""

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Submit",
                    callback_data="final_submit"
                ),
                InlineKeyboardButton(
                    "↩️ Continue",
                    callback_data="back_question"
                )
            ]
        ])
    )


# =========================================================
# CALCULATE RESULT
# =========================================================

def calculate_result(
    user_id,
    context
):

    questions = context.user_data[
        "mock_questions"
    ]

    answers = context.user_data.get(
        "answers",
        {}
    )

    correct = 0
    wrong = 0

    section_stats = {}

    for section, short in SECTIONS:

        section_stats[short] = {
            "correct": 0,
            "wrong": 0,
            "skipped": 0,
            "total": QUESTIONS_PER_SECTION
        }

    for q in questions:

        selected = answers.get(
            str(q["id"])
        )

        section_index = questions.index(q) // QUESTIONS_PER_SECTION
        short = SECTIONS[
            section_index
        ][1]

        if selected is None:

            section_stats[
                short
            ]["skipped"] += 1

            continue

        if int(selected) == int(q["answer"]):

            correct += 1

            section_stats[
                short
            ]["correct"] += 1

        else:

            wrong += 1

            section_stats[
                short
            ]["wrong"] += 1

    skipped = len(questions) - correct - wrong

    negative = wrong * NEGATIVE_MARK

    score = (
        correct * 2
    ) - negative

    attempted = correct + wrong

    accuracy = (
        (correct / attempted) * 100
        if attempted else 0
    )

    seconds = int(
        time.time()
        - context.user_data.get(
            "mock_started",
            time.time()
        )
    )

    if seconds > 3600:
        seconds = 3600

    return {
        "correct": correct,
        "wrong": wrong,
        "skipped": skipped,
        "negative": negative,
        "score": score,
        "accuracy": accuracy,
        "seconds": seconds,
        "section_stats": section_stats
    }


# =========================================================
# MOTIVATION
# =========================================================

def motivation(score, accuracy):

    if accuracy >= 85:
        lines = [
            "🔥 शानदार! आपकी accuracy selection-level है।",
            "🏆 बहुत बढ़िया! अब इसी consistency को बनाए रखो।",
            "🚀 Excellent! अब speed को और मजबूत करो।"
        ]

    elif accuracy >= 70:
        lines = [
            "💪 अच्छी performance! थोड़ी accuracy बढ़ाओ।",
            "🎯 Direction सही है—weak topics पर काम करो।",
            "📚 अच्छा attempt! अगली बार score और ऊपर जाएगा।"
        ]

    elif accuracy >= 50:
        lines = [
            "🌱 Improvement की अच्छी गुंजाइश है। गलत questions revise करो।",
            "📖 आज की mistakes आपकी अगली strength बन सकती हैं।",
            "💪 Practice जारी रखो—consistency सबसे जरूरी है।"
        ]

    else:
        lines = [
            "🔥 हार मत मानो। हर गलत answer एक learning point है।",
            "🌱 आज का score आपकी final क्षमता नहीं बताता।",
            "💪 फिर से practice करो—अगला attempt बेहतर होगा।"
        ]

    return random.choice(lines)


# =========================================================
# SAVE RESULT
# =========================================================

def save_result(
    user_id,
    context,
    result
):

    con = db()

    cur = con.execute("""
        INSERT INTO attempts (
            user_id,
            exam,
            mode,
            score,
            total,
            correct,
            wrong,
            skipped,
            seconds,
            negative_marks,
            accuracy,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        EXAM,
        "Mock",
        result["score"],
        100,
        result["correct"],
        result["wrong"],
        result["skipped"],
        result["seconds"],
        result["negative"],
        result["accuracy"],
        datetime.now(
            timezone.utc
        ).isoformat()
    ))

    attempt_id = cur.lastrowid

    questions = context.user_data[
        "mock_questions"
    ]

    answers = context.user_data.get(
        "answers",
        {}
    )

    reviews = context.user_data.get(
        "reviews",
        set()
    )

    for q in questions:

        selected = answers.get(
            str(q["id"])
        )

        is_correct = (
            selected is not None
            and int(selected) == int(q["answer"])
        )

        con.execute("""
            INSERT INTO answers (
                attempt_id,
                question_id,
                selected,
                correct,
                seconds,
                marked_review
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            attempt_id,
            q["id"],
            selected,
            int(is_correct),
            0,
            int(q["id"] in reviews)
        ))

        if (
            selected is not None
            and not is_correct
        ):

            con.execute("""
                INSERT OR IGNORE INTO wrong_questions
                (user_id, question_id, created_at)
                VALUES (?, ?, ?)
            """, (
                user_id,
                q["id"],
                datetime.now(
                    timezone.utc
                ).isoformat()
            ))

    con.commit()
    con.close()

    return attempt_id


# =========================================================
# RESULT SCREEN
# =========================================================

async def show_result(
    query,
    context
):

    result = calculate_result(
        query.from_user.id,
        context
    )

    save_result(
        query.from_user.id,
        context,
        result
    )

    seconds = result["seconds"]

    minutes = seconds // 60
    sec = seconds % 60

    avg_time = (
        seconds / 100
    )

    text = f"""
🏆 MOCK TEST RESULT

📝 {MOCK_NAME}

━━━━━━━━━━━━━━━━━━

🎯 Score: {result["score"]:.2f}/200

📊 Accuracy: {result["accuracy"]:.2f}%

✅ Correct: {result["correct"]}
❌ Wrong: {result["wrong"]}
⏭️ Skipped: {result["skipped"]}

➖ Negative Marks:
-{result["negative"]:.2f}

⏱️ Your Time:
{minutes} min {sec} sec

⏱️ Avg Time / Question:
{avg_time:.1f} sec

━━━━━━━━━━━━━━━━━━

📚 SECTION ANALYSIS
"""

    for short, stat in result[
        "section_stats"
    ].items():

        attempted = (
            stat["correct"]
            + stat["wrong"]
        )

        acc = (
            stat["correct"]
            / attempted
            * 100
            if attempted else 0
        )

        text += f"""

{short}
✅ {stat["correct"]}  ❌ {stat["wrong"]}  ⏭️ {stat["skipped"]}
🎯 Accuracy: {acc:.1f}%
"""

    text += f"""

━━━━━━━━━━━━━━━━━━

💡 Feedback:
{motivation(
    result["score"],
    result["accuracy"]
)}
"""

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📋 Question Analysis",
                    callback_data="analysis"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 New Mock",
                    callback_data="mock"
                ),
                InlineKeyboardButton(
                    "🏠 Home",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# PERFORMANCE
# =========================================================

async def performance(
    query
):

    con = db()

    row = con.execute("""
        SELECT
            COUNT(*) AS tests,
            COALESCE(SUM(correct),0) AS correct,
            COALESCE(SUM(wrong),0) AS wrong,
            COALESCE(SUM(skipped),0) AS skipped,
            COALESCE(AVG(score),0) AS avg_score,
            COALESCE(AVG(accuracy),0) AS accuracy,
            COALESCE(AVG(seconds),0) AS avg_seconds
        FROM attempts
        WHERE user_id=?
    """, (
        query.from_user.id,
    )).fetchone()

    con.close()

    if not row or row["tests"] == 0:

        text = """
📊 MY PERFORMANCE

अभी कोई test attempt नहीं किया गया है।

पहला Mock Test देकर अपना performance dashboard शुरू करें। 🚀
"""

    else:

        avg_time_q = (
            row["avg_seconds"] / 100
        )

        text = f"""
📊 MY PERFORMANCE

📝 Tests Attempted: {row["tests"]}

✅ Correct: {row["correct"]}
❌ Wrong: {row["wrong"]}
⏭️ Skipped: {row["skipped"]}

🎯 Average Score:
{row["avg_score"]:.2f}

📈 Average Accuracy:
{row["accuracy"]:.2f}%

⏱️ Avg Time / Question:
{avg_time_q:.1f} sec
"""

    await query.edit_message_text(
        text,
        reply_markup=home_button()
    )


# =========================================================
# OTHER MENUS
# =========================================================

async def simple_menu(
    query,
    title,
    message
):

    await query.edit_message_text(
        f"{title}\n\n{message}",
        reply_markup=home_button()
    )


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    # HOME
    if data == "home":
        context.user_data.clear()
        await show_home(query)
        return

    # QUIZ
    if data == "quiz":

        await simple_menu(
            query,
            "⚡ QUIZ",
            """
Quiz system अगला practice module है।

यहाँ immediate answer,
explanation और topic-wise practice मिलेगी।
"""
        )

        return

    # MOCK
    if data == "mock":

        await mock_intro(query)

        return

    # START MOCK
    if data == "mock_start":

        questions = create_mock(
            query.from_user.id
        )

        if not questions:

            await simple_menu(
                query,
                "⚠️ Mock Ready नहीं है",
                "Question bank में अभी पर्याप्त questions नहीं हैं।"
            )

            return

        context.user_data.clear()

        context.user_data[
            "mock_questions"
        ] = questions

        context.user_data[
            "mock_index"
        ] = 0

        context.user_data[
            "answers"
        ] = {}

        context.user_data[
            "reviews"
        ] = set()

        context.user_data[
            "mock_started"
        ] = time.time()

        await show_question(
            query,
            context
        )

        return

    # ANSWER
    if data.startswith("ans:"):

        option = int(
            data.split(":")[1]
        )

        await answer_question(
            query,
            context,
            option
        )

        return

    # NEXT
    if data == "next":

        await move_question(
            query,
            context,
            1
        )

        return

    # PREVIOUS
    if data == "prev":

        await move_question(
            query,
            context,
            -1
        )

        return

    # CLEAR
    if data == "clear":

        await clear_answer(
            query,
            context
        )

        return

    # REVIEW
    if data == "review":

        await mark_review(
            query,
            context
        )

        return

    # GRID
    if data == "qgrid":

       
