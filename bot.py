import os
import json
import random
import sqlite3
import time
import asyncio
import threading

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


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

DB_PATH = os.getenv(
    "DB_PATH",
    "exam_prep.db"
)

PORT = int(
    os.getenv("PORT", "10000")
)

EXAM = "SSC CGL"

MOCK_NAME = "SSC CGL Tier-I"

QUESTIONS_PER_SECTION = 25

SECTION_TIME = 15 * 60

TOTAL_QUESTIONS = 100

MARKS_PER_QUESTION = 2

NEGATIVE_MARK = 0.50

SECTIONS = [
    (
        "General Intelligence & Reasoning",
        "Reasoning"
    ),
    (
        "General Awareness",
        "General Awareness"
    ),
    (
        "Quantitative Aptitude",
        "Maths"
    ),
    (
        "English Comprehension",
        "English"
    ),
]


# =========================================================
# HEALTH SERVER - FOR RENDER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain"
        )
        self.end_headers()

        self.wfile.write(
            b"EXAMPREP BOT IS RUNNING"
        )

    def log_message(
        self,
        format,
        *args
    ):
        return


def start_health_server():

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
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

    conn = sqlite3.connect(
        DB_PATH
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER,
            user_id INTEGER,
            question_id INTEGER,
            selected INTEGER,
            correct INTEGER,
            seconds INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_questions (
            user_id INTEGER,
            question_id INTEGER,
            UNIQUE(user_id, question_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wrong_questions (
            user_id INTEGER,
            question_id INTEGER,
            UNIQUE(user_id, question_id)
        )
    """)

    conn.commit()

    conn.close()


init_db()


# =========================================================
# QUESTION BANK
# =========================================================

def load_question_bank():

    path = "question_bank.json"

    if not os.path.exists(path):

        print(
            "WARNING: question_bank.json not found."
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
                    EXAM
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

    # Show section counts
    for _, subject in SECTIONS:

        cur.execute("""
            SELECT COUNT(*)
            FROM questions
            WHERE exam = ?
            AND subject = ?
        """, (
            EXAM,
            subject
        ))

        count = cur.fetchone()[0]

        print(
            f"{subject}: {count} questions"
        )

    conn.close()

    print(
        f"Question bank loaded. New questions: {inserted}"
    )


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
                callback_data="current_affairs"
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
            )
        ],

        [
            InlineKeyboardButton(
                "🏆 Leaderboard",
                callback_data="leaderboard"
            ),
            InlineKeyboardButton(
                "👤 Profile",
                callback_data="profile"
            )
        ],

        [
            InlineKeyboardButton(
                "❓ Help",
                callback_data="help"
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
🎯 EXAMPREP

Welcome to your Competitive Exam Practice Platform! 🇮🇳

📚 Exam: SSC CGL

Choose an option below:
"""

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardRemove()
    )

    await update.message.reply_text(
        "👇 Main Menu",
        reply_markup=home_keyboard()
    )


# =========================================================
# SIMPLE MENU
# =========================================================

async def simple_menu(
    query,
    title,
    body
):

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🏠 Home",
                callback_data="home"
            )
        ]
    ])

    await query.edit_message_text(
        f"{title}\n\n{body}",
        reply_markup=keyboard
    )


# =========================================================
# MOCK INTRO
# =========================================================

async def mock_intro(
    query
):

    text = f"""
📝 {MOCK_NAME}

SSC CGL Tier-I pattern:

🧠 General Intelligence & Reasoning
25 Questions

🌍 General Awareness
25 Questions

🔢 Quantitative Aptitude
25 Questions

🇬🇧 English Comprehension
25 Questions

━━━━━━━━━━━━━━━━━━

📌 Total Questions: 100
📌 Total Marks: 200
📌 Total Time: 60 Minutes

⏱️ Each section:
15 Minutes

❌ Negative Marking:
0.50 marks per wrong answer

⚠️ Section का समय खत्म होने पर
अगला section automatically शुरू होगा.
"""

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🚀 Start Mock Test",
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

    await query.edit_message_text(
        text,
        reply_markup=keyboard
    )


# =========================================================
# CREATE MOCK
# =========================================================

def create_mock():

    conn = get_db()

    cur = conn.cursor()

    all_questions = []

    for section_name, subject in SECTIONS:

        cur.execute("""
            SELECT *
            FROM questions
            WHERE exam = ?
            AND subject = ?
            ORDER BY RANDOM()
            LIMIT ?
        """, (
            EXAM,
            subject,
            QUESTIONS_PER_SECTION
        ))

        rows = cur.fetchall()

        if len(rows) < QUESTIONS_PER_SECTION:

            conn.close()

            return None

        all_questions.extend(
            [dict(row) for row in rows]
        )

    conn.close()

    return all_questions


# =========================================================
# CURRENT SECTION
# =========================================================

def get_current_section(context):

    return context.user_data.get(
        "current_section",
        0
    )


def get_section_range(section_index):

    start = (
        section_index
        * QUESTIONS_PER_SECTION
    )

    end = (
        start
        + QUESTIONS_PER_SECTION
        - 1
    )

    return start, end


# =========================================================
# QUESTION TIMER
# =========================================================

def remaining_time(context):

    deadline = context.user_data.get(
        "section_deadline"
    )

    if not deadline:

        return SECTION_TIME

    return max(
        0,
        int(
            deadline - time.time()
        )
    )


# =========================================================
# QUESTION SCREEN
# =========================================================

async def show_question(
    query,
    context
):

    questions = context.user_data.get(
        "mock_questions"
    )

    if not questions:
        return

    index = context.user_data.get(
        "mock_index",
        0
    )

    current_section = get_current_section(
        context
    )

    section_start, section_end = (
        get_section_range(
            current_section
        )
    )

    # Safety
    if index < section_start:
        index = section_start

    if index > section_end:
        index = section_end

    context.user_data[
        "mock_index"
    ] = index

    q = questions[index]

    options = json.loads(
        q["options"]
    )

    answers = context.user_data.setdefault(
        "answers",
        {}
    )

    selected = answers.get(
        str(q["id"])
    )

    remaining = remaining_time(
        context
    )

    minutes = remaining // 60
    seconds = remaining % 60

    if remaining <= 60:

        timer = (
            f"🔴 Time Left: "
            f"{minutes:02d}:{seconds:02d}"
        )

    elif remaining <= 300:

        timer = (
            f"🟠 Time Left: "
            f"{minutes:02d}:{seconds:02d}"
        )

    else:

        timer = (
            f"⏱️ Time Left: "
            f"{minutes:02d}:{seconds:02d}"
        )

    section_title = SECTIONS[
        current_section
    ][0]

    text = f"""
📝 {MOCK_NAME}

📚 Section {current_section + 1}/4
{section_title}

{timer}

━━━━━━━━━━━━━━━━━━

❓ Question {index + 1}/{TOTAL_QUESTIONS}

{q["question"]}
"""

    buttons = []

    for i, option in enumerate(
        options
    ):

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

    if index > section_start:

        nav.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data="prev"
            )
        )

    if index < section_end:

        nav.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data="next"
            )
        )

    if nav:

        buttons.append(nav)

    review_text = "🔖 Mark for Review"

    if index in context.user_data.get(
        "reviews",
        set()
    ):

        review_text = (
            "🔖 Reviewed ✓"
        )

    buttons.append([

        InlineKeyboardButton(
            review_text,
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

    markup = InlineKeyboardMarkup(
        buttons
    )

    try:

        await query.edit_message_text(
            text,
            reply_markup=markup
        )

    except Exception as e:

        print(
            "show_question error:",
            e
        )


# =========================================================
# ANSWER
# =========================================================

async def answer_question(
    query,
    context,
    option
):

    if context.user_data.get(
        "mock_finished",
        False
    ):

        return

    if remaining_time(context) <= 0:

        await query.answer(
            "⏰ Section का समय समाप्त हो गया है।"
        )

        return

    questions = context.user_data.get(
        "mock_questions"
    )

    if not questions:
        return

    index = context.user_data.get(
        "mock_index",
        0
    )

    q = questions[index]

    answers = context.user_data.setdefault(
        "answers",
        {}
    )

    answers[
        str(q["id"])
    ] = option

    await query.answer(
        "Answer saved ✓"
    )

    await show_question(
        query,
        context
    )


# =========================================================
# MOVE QUESTION
# =========================================================

async def move_question(
    query,
    context,
    direction
):

    if remaining_time(context) <= 0:

        await query.answer(
            "⏰ Section का समय समाप्त हो गया है।"
        )

        return

    current_section = get_current_section(
        context
    )

    section_start, section_end = (
        get_section_range(
            current_section
        )
    )

    index = context.user_data.get(
        "mock_index",
        section_start
    )

    new_index = index + direction

    if new_index < section_start:

        new_index = section_start

    if new_index > section_end:

        new_index = section_end

    context.user_data[
        "mock_index"
    ] = new_index

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

    questions = context.user_data.get(
        "mock_questions"
    )

    index = context.user_data.get(
        "mock_index",
        0
    )

    if questions:

        q = questions[index]

        context.user_data.setdefault(
            "answers",
            {}
        ).pop(
            str(q["id"]),
            None
        )

    await query.answer(
        "Answer cleared"
    )

    await show_question(
        query,
       
