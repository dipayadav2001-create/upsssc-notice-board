import os
import json
import random
import sqlite3
import time
import threading
import asyncio

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

DB_PATH = os.getenv("DB_PATH", "exam_prep.db")
PORT = int(os.getenv("PORT", "10000"))

EXAM = "SSC CGL"
MOCK_NAME = "SSC CGL Tier-I"

QUESTIONS_PER_SECTION = 25
TOTAL_QUESTIONS = 100

SECTION_TIME = 15 * 60

MARKS_PER_QUESTION = 2
NEGATIVE_MARK = 0.50

SECTIONS = [
    ("General Intelligence & Reasoning", "Reasoning"),
    ("General Awareness", "General Awareness"),
    ("Quantitative Aptitude", "Maths"),
    ("English Comprehension", "English"),
]


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"EXAMPREP BOT IS RUNNING")

    def log_message(self, format, *args):
        return


def start_health_server():
    try:
        server = ThreadingHTTPServer(
            ("0.0.0.0", PORT),
            HealthHandler
        )
        print(f"Health server running on port {PORT}")
        server.serve_forever()
    except Exception as e:
        print("Health server error:", e)


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

def validate_question(q):

    if not isinstance(q, dict):
        return False

    required = [
        "question",
        "options",
        "answer"
    ]

    for key in required:
        if key not in q:
            return False

    if not isinstance(q["question"], str):
        return False

    if not isinstance(q["options"], list):
        return False

    if len(q["options"]) != 4:
        return False

    try:
        answer = int(q["answer"])
    except Exception:
        return False

    if answer not in [0, 1, 2, 3]:
        return False

    return True


def load_question_bank():

    path = "question_bank.json"

    if not os.path.exists(path):
        print("ERROR: question_bank.json not found.")
        return False

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            bank = json.load(f)

    except Exception as e:

        print("QUESTION BANK JSON ERROR:", e)
        return False

    if not isinstance(bank, list):
        print("ERROR: question_bank.json must contain a JSON array.")
        return False

    valid = []

    for q in bank:

        if validate_question(q):
            valid.append(q)
        else:
            print("Skipped invalid question.")

    print(f"Valid questions in JSON: {len(valid)}")

    # -----------------------------------------------------
    # IMPORTANT:
    # Remove old ORIGINAL/PRACTICE questions.
    # This fixes old 97-question database problem.
    # PYQs are NOT removed.
    # -----------------------------------------------------

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM questions
        WHERE exam = ?
        AND kind = 'Practice'
    """, (EXAM,))

    conn.commit()

    inserted = 0

    for q in valid:

        try:

            subject = q.get("subject", "").strip()

            if subject not in [
                "Reasoning",
                "General Awareness",
                "Maths",
                "English"
            ]:
                print(
                    "Skipped question with invalid subject:",
                    subject
                )
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
                q.get("exam", EXAM),
                subject,
                q.get("topic", ""),
                q["question"],
                json.dumps(
                    q["options"],
                    ensure_ascii=False
                ),
                int(q["answer"]),
                q.get("explanation", ""),
                q.get("kind", "Practice"),
                int(q.get("verified", 0)),
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

    print("")
    print("========== QUESTION BANK ==========")

    counts_ok = True

    for section_name, subject in SECTIONS:

        cur.execute("""
            SELECT COUNT(*)
            FROM questions
            WHERE exam = ?
            AND subject = ?
            AND kind = 'Practice'
        """, (
            EXAM,
            subject
        ))

        count = cur.fetchone()[0]

        print(
            f"{subject}: {count} questions"
        )

        if count < QUESTIONS_PER_SECTION:
            counts_ok = False

    print(
        f"New questions loaded: {inserted}"
    )

    print("===================================")

    conn.close()

    return counts_ok


BANK_OK = load_question_bank()


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


async def start(update, context):

    save_user(update.effective_user)

    # Cancel old timer
    old_task = context.user_data.get("timer_task")

    if old_task:
        try:
            old_task.cancel()
        except Exception:
            pass

    context.user_data.clear()

    text = """
🎯 EXAMPREP

Welcome to your Competitive Exam Practice Platform! 🇮🇳

📚 Exam: SSC CGL

Practice • Mock Test • PYQ • Performance

👇 नीचे से option चुनें:
"""

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardRemove()
    )

    await update.message.reply_text(
        "🏠 Main Menu",
        reply_markup=home_keyboard()
    )


# =========================================================
# SIMPLE MENU
# =========================================================

async def simple_menu(query, title, body):

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

async def mock_intro(query):

    text = f"""
📝 {MOCK_NAME}

SSC CGL Tier-I Pattern

🧠 Reasoning
25 Questions

🌍 General Awareness
25 Questions

🔢 Quantitative Aptitude
25 Questions

🇬🇧 English Comprehension
25 Questions

━━━━━━━━━━━━━━━━━━

📌 Total: 100 Questions
📌 Marks: 200
📌 Time: 60 Minutes

⏱️ Section Time:
15 Minutes each

❌ Negative Marking:
0.50 marks per wrong answer

⚠️ हर section का timer अलग है।
Timer खत्म होने पर अगला section शुरू होगा.
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

    for _, subject in SECTIONS:

        cur.execute("""
            SELECT *
            FROM questions
            WHERE exam = ?
            AND subject = ?
            AND kind = 'Practice'
            ORDER BY RANDOM()
            LIMIT ?
        """, (
            EXAM,
            subject,
            QUESTIONS_PER_SECTION
        ))

        rows = cur.fetchall()

        if len(rows) != QUESTIONS_PER_SECTION:

            print(
                f"MOCK ERROR: {subject} has {len(rows)} questions"
            )

            conn.close()
            return None

        all_questions.extend(
            [dict(row) for row in rows]
        )

    conn.close()

    if len(all_questions) != TOTAL_QUESTIONS:
        return None

    return all_questions


# =========================================================
# SECTION HELPERS
# =========================================================

def get_section_range(section):

    start = section * QUESTIONS_PER_SECTION
    end = start + QUESTIONS_PER_SECTION - 1

    return start, end


def remaining_time(context):

    deadline = context.user_data.get(
        "section_deadline"
    )

    if not deadline:
        return SECTION_TIME

    return max(
        0,
        int(deadline - time.time())
    )


# =========================================================
# QUESTION SCREEN
# =========================================================

async def show_question(query, context):

    questions = context.user_data.get(
        "mock_questions"
    )

    if not questions:
        return

    section = context.user_data.get(
        "current_section",
        0
    )

    start, end = get_section_range(section)

    index = context.user_data.get(
        "mock_index",
        start
    )

    if index < start:
        index = start

    if index > end:
        index = end

    context.user_data["mock_index"] = index

    q = questions[index]

    try:
        options = json.loads(q["options"])
    except Exception:
        options = []

    answers = context.user_data.setdefault(
        "answers",
        {}
    )

    selected = answers.get(str(q["id"]))

    remaining = remaining_time(context)

    minutes = remaining // 60
    seconds = remaining % 60

    if remaining <= 60:
        timer_text = (
            f"🔴 Time Left: {minutes:02d}:{seconds:02d}"
        )
    elif remaining <= 300:
        timer_text = (
            f"🟠 Time Left: {minutes:02d}:{seconds:02d}"
        )
    else:
        timer_text = (
            f"⏱️ Time Left: {minutes:02d}:{seconds:02d}"
        )

    section_title = SECTIONS[section][0]

    text = f"""
📝 {MOCK_NAME}

📚 Section {section + 1}/4
{section_title}

{timer_text}

━━━━━━━━━━━━━━━━━━

❓ Question {index + 1}/100

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

    navigation = []

    if index > start:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data="prev"
            )
        )

    if index < end:
        navigation.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data="next"
            )
        )

    if navigation:
        buttons.append(navigation)

    review_set = context.user_data.setdefault(
        "reviews",
        set()
    )

    review_text = (
        "🔖 Reviewed ✓"
        if index in review_set
        else "🔖 Mark for Review"
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

    try:

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:

        print("show_question error:", e)


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

        await section_finished(
            query,
            context
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

    context.user_data.setdefault(
        "answers",
        {}
    )[str(q["id"])] = option

    await query.answer("Answer saved ✓")

    await show_question(
        query,
        context
    )


# =========================================================
# MOVE
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

        await section_finished(
            query,
            context
        )

        return

    section = context.user_data.get(
        "current_section",
        0
    )

    start, end = get_section_range(section)

    index = context.user_data.get(
        "mock_index",
        start
    )

    index += direction

    index = max(
        start,
        min(end, index)
    )

    context.user_data["mock_index"] = index

    await show_question(
        query,
        context
    )


# =========================================================
# CLEAR ANSWER
# =========================================================

async def clear_answer(query, context):

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

    context.user_data.setdefault(
        "answers",
        {}
    ).pop(
        str(q["id"]),
        None
    )

    await query.answer("Answer cleared ✓")

    await show_question(
        query,
        context
    )


# =========================================================
# REVIEW
# =========================================================

async def mark_review(query, context):

    index = context.user_data.get(
        "mock_index",
        0
    )

    reviews = context.user_data.setdefault(
        "reviews",
        set()
    )

    if index in reviews:
        reviews.remove(index)
        await query.answer("Review removed")
    else:
        reviews.add(index)
        await query.answer("Marked for review 🔖")

    await show_question(
        query,
        context
    )


# =========================================================
# QUESTION GRID
# =========================================================

async def question_grid(query, context):

    questions = context.user_data.get(
        "mock_questions"
    )

    if not questions:
        return

    section = context.user_data.get(
        "current_section",
        0
    )

    start, end = get_section_range(section)

    answers = context.user_data.get(
        "answers",
        {}
    )

    reviews = context.user_data.get(
        "reviews",
        set()
    )

    buttons = []

    row = []

    for i in range(start, end + 1):

        q = questions[i]

        if str(q["id"]) in answers:
            text = f"🟢 {i + 1}"
        elif i in reviews:
            text = f"🔖 {i + 1}"
        else:
            text = f"⚪ {i + 1}"

        row.append(
            InlineKeyboardButton(
                text,
                callback_data=f"goto:{i}"
            )
        )

        if len(row) == 5:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data="back_question"
        )
    ])

    await query.edit_message_text(
        f"""
📋 Question List

Section {section + 1}/4

🟢 Answered
⚪ Not Answered
🔖 Marked for Review

Question पर tap करके सीधे वहाँ जाएँ।
""",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================================================
# GOTO
# =========================================================

async def goto_question(
    query,
    context,
    index
):

    section = context.user_data.get(
        "current_section",
        0
    )

    start, end = get_section_range(section)

    if index < start or index > end:
        return

    context.user_data["mock_index"] = index

    await show_question(
        query,
        context
    )


# =========================================================
# SUBMIT
# =========================================================

async def submit_confirm(query, context):

    questions = context.user_data.get(
        "mock_questions"
    )

    if not questions:
        return

    answers = context.user_data.get(
        "answers",
        {}
    )

    answered = len(answers)

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "✅ Yes, Submit",
                callback_data="final_submit"
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Continue Test",
                callback_data="back_question"
            )
        ]
    ])

    await query.edit_message_text(
        f"""
🏁 Submit Mock Test?

Answered: {answered}/100
Skipped: {100 - answered}

क्या आप test submit करना चाहते हैं?
""",
        reply_markup=keyboard
    )


# =========================================================
# RESULT CALCULATION
# =========================================================

def calculate_result(context):

    questions = context.user_data.get(
        "mock_questions",
        []
    )

    answers = context.user_data.get(
        "answers",
        {}
    )

    attempted = 0
    correct = 0
    wrong = 0

    subject_stats = {}

    for q in questions:

        subject = q["subject"]

        if subject not in subject_stats:
            subject_stats[subject] = {
                "total": 0,
                "attempted": 0,
                "correct": 0,
                "wrong": 0
            }

        subject_stats[subject]["total"] += 1

        selected = answers.get(str(q["id"]))

        if selected is None:
            continue

        attempted += 1
        subject_stats[subject]["attempted"] += 1

        if int(selected) == int(q["answer"]):

            correct += 1
            subject_stats[subject]["correct"] += 1

        else:

            wrong += 1
            subject_stats[subject]["wrong"] += 1

    skipped = len(questions) - attempted

    score = (
        correct * MARKS_PER_QUESTION
        - wrong * NEGATIVE_MARK
    )

    accuracy = (
        (correct / attempted) * 100
        if attempted
        else 0
    )

    return {
        "attempted": attempted,
        "correct": correct,
        "wrong": wrong,
        "skipped": skipped,
        "score": score,
        "accuracy": accuracy,
        "subject_stats": subject_stats
    }


# =========================================================
# SAVE RESULT
# =========================================================

def save_result(context):

    if context.user_data.get(
        "result_saved",
        False
    ):
        return

    user_id = context.user_data.get(
        "user_id"
    )

    if not user_id:
        return

    result = calculate_result(context)

    start_time = context.user_data.get(
        "mock_start_time",
        time.time()
    )

    total_time = int(
        time.time() - start_time
    )

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
        user_id,
        EXAM,
        TOTAL_QUESTIONS,
        result["attempted"],
        result["correct"],
        result["wrong"],
        result["skipped"],
        result["score"],
        result["accuracy"],
        total_time,
        int(time.time())
    ))

    attempt_id = cur.lastrowid

    answers = context.user_data.get(
        "answers",
        {}
    )

    for q in context.user_data.get(
        "mock_questions",
        []
    ):

        selected = answers.get(
            str(q["id"])
        )

        if selected is None:
            continue

        is_correct = (
            int(selected) == int(q["answer"])
        )

        cur.execute("""
            INSERT INTO answers
            (
                attempt_id,
                user_id,
                question_id,
                selected,
                correct,
                seconds
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            attempt_id,
            user_id,
            q["id"],
            int(selected),
            1 if is_correct else 0,
            0
        ))

        if not is_correct:

            cur.execute("""
                INSERT OR IGNORE INTO wrong_questions
                (
                    user_id,
                    question_id
                )
                VALUES (?, ?)
            """, (
                user_id,
                q["id"]
            ))

    conn.commit()
    conn.close()

    context.user_data["result_saved"] = True


# =========================================================
# MOTIVATION
# =========================================================

def get_motivation(result):

    accuracy = result["accuracy"]
    score = result["score"]

    if accuracy >= 90:
        return "🔥 Excellent! आपका performance बहुत strong है।"

    if accuracy >= 75:
        return "💪 बहुत अच्छा! थोड़ी और practice आपको next level पर ले जाएगी।"

    if accuracy >= 60:
        return "📈 अच्छा प्रयास! अब weak topics पर focus करें।"

    if accuracy >= 40:
        return "🎯 Basics को थोड़ा और मजबूत करें। Improvement बिल्कुल possible है।"

    return "🌱 शुरुआत अच्छी है। Practice जारी रखें — score जरूर बढ़ेगा।"


# =========================================================
# RESULT SCREEN
# =========================================================

async def show_result(query, context):

    result = calculate_result(context)

    save_result(context)

    start_time = context.user_data.get(
        "mock_start_time",
        time.time()
    )

    total_time = int(
        time.time() - start_time
    )

    minutes = total_time // 60
    seconds = total_time % 60

    avg_time = (
        total_time / TOTAL_QUESTIONS
        if TOTAL_QUESTIONS
        else 0
    )

    text = f"""
🏆 MOCK TEST RESULT

📝 {MOCK_NAME}

━━━━━━━━━━━━━━━━━━

🎯 Score:
{result["score"]:.2f} / 200

📊 Accuracy:
{result["accuracy"]:.2f}%

✅ Correct:
{result["correct"]}

❌ Wrong:
{result["wrong"]}

⏭️ Skipped:
{result["skipped"]}

📝 Attempted:
{result["attempted"]}

⏱️ Your Time:
{minutes:02d}:{seconds:02d}

⏱️ Avg Time / Question:
{avg_time:.1f} sec

━━━━━━━━━━━━━━━━━━

{get_motivation(result)}
"""

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📊 Detailed Analysis",
                callback_data="analysis"
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
# SECTION TIMER
# =========================================================

async def section_timer(context):

    my_section = context.user_data.get(
        "current_section"
    )

    if my_section is None:
        return

    try:

        await asyncio.sleep(SECTION_TIME)

    except asyncio.CancelledError:
        return

    # Check that same section is still active
    if context.user_data.get(
        "current_section"
    ) != my_section:
        return

    if context.user_data.get(
        "mock_finished",
        False
    ):
        return

    await auto_next_section(context)


# =========================================================
# AUTO NEXT SECTION
# =========================================================

async def auto_next_section(context):

    current = context.user_data.get(
        "current_section",
        0
    )

    if current >= 3:

        context.user_data["mock_finished"] = True

        save_result(context)

        chat_id = context.user_data.get(
            "chat_id"
        )

        message_id = context.user_data.get(
            "message_id"
        )

        if chat_id:

            try:

                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⏰ English section का समय समाप्त हो गया है।\n\n🏁 Mock Test submitted."
                )

            except Exception as e:

                print(
                    "Final timer message error:",
                    e
                )

        return

    next_section = current + 1

    context.user_data[
        "current_section"
    ] = next_section

    start, _ = get_section_range(
        next_section
    )

    context.user_data[
        "mock_index"
    ] = start

    context.user_data[
        "section_deadline"
    ] = time.time() + SECTION_TIME

    old_task = context.user_data.get(
        "timer_task"
    )

    if old_task:

        try:
            old_task.cancel()
        except Exception:
            pass

    context.user_data[
        "timer_task"
    ] = asyncio.create_task(
        section_timer(context)
    )

    chat_id = context.user_data.get(
        "chat_id"
    )

    if not chat_id:
        return

    try:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⏰ Section {current + 1} का समय समाप्त!\n\n"
                f"➡️ अब Section {next_section + 1}/4 शुरू हो रहा है।"
            )
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text="👇 पहला प्रश्न",
            reply_markup=question_keyboard_for_bot(
                context
            )
        )

    except Exception as e:

        print(
            "Next section error:",
            e
        )


def question_keyboard_for_bot(context):

    questions = context.user_data.get(
        "mock_questions"
    )

    section = context.user_data.get(
        "current_section",
        0
    )

    index = context.user_data.get(
        "mock_index",
        section * QUESTIONS_PER_SECTION
    )

    q = questions[index]

    options = json.loads(q["options"])

    buttons = []

    answers = context.user_data.get(
        "answers",
        {}
    )

    selected = answers.get(str(q["id"]))

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

    start, end = get_section_range(section)

    nav = []

    if index > start:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data="prev"
            )
        )

    if index < end:
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
            "🔖 Review",
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

    return InlineKeyboardMarkup(buttons)


async def section_finished(query, context):

    await auto_next_section(context)


# =========================================================
# START MOCK
# =========================================================

async def mock_start(query, context):

    questions = create_mock()

    if not questions:

        await query.edit_message_text(
            """
❌ Mock Test अभी start नहीं हो सकता।

Question Bank में किसी section के 25 questions पूरे नहीं हैं।

Render Logs में section count check करें।
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

    # Cancel previous timer
    old_task = context.user_data.get(
        "timer_task"
    )

    if old_task:

        try:
            old_task.cancel()
        except Exception:
            pass

    context.user_data.clear()

    context.user_data["mock_questions"] = questions
    context.user_data["mock_index"] = 0
    context.user_data["current_section"] = 0

    context.user_data["answers"] = {}
    context.user_data["reviews"] = set()

    context.user_data["mock_start_time"] = time.time()
    context.user_data["section_deadline"] = (
        time.time() + SECTION_TIME
    )

    context.user_data["user_id"] = query.from_user.id
    context.user_data["chat_id"] = query.message.chat_id

    context.user_data["mock_finished"] = False
    context.user_data["result_saved"] = False

    context.user_data["timer_task"] = (
        asyncio.create_task(
            section_timer(context)
        )
    )

    await show_question(
        query,
        context
    )


# =========================================================
# ANALYSIS
# =========================================================

async def show_analysis(query, context):

    result = calculate_result(context)

    lines = [
        "📊 DETAILED ANALYSIS",
        "",
    ]

    for subject, stats in result[
        "subject_stats"
    ].items():

        attempted = stats["attempted"]

        accuracy = (
            stats["correct"] / attempted * 100
            if attempted
            else 0
        )

        lines.append(
            f"📚 {subject}"
        )

        lines.append(
            f"Total: {stats['total']}"
        )

        lines.append(
            f"Attempted: {attempted}"
        )

        lines.append(
            f"✅ Correct: {stats['correct']}"
        )

        lines.append(
            f"❌ Wrong: {stats['wrong']}"
        )

        lines.append(
            f"Accuracy: {accuracy:.1f}%"
        )

        lines.append("")

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🏆 Result",
                callback_data="result"
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
        "\n".join(lines),
        reply_markup=keyboard
    )


# =========================================================
# PERFORMANCE
# =========================================================

async def performance_menu(query):

    user_id = query.from_user.id

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) AS tests,
            COALESCE(AVG(score), 0) AS avg_score,
            COALESCE(AVG(accuracy), 0) AS avg_accuracy,
            COALESCE(MAX(score), 0) AS best_score
        FROM attempts
        WHERE user_id = ?
        AND exam = ?
    """, (
        user_id,
        EXAM
    ))

    row = cur.fetchone()

    conn.close()

    if not row or row["tests"] == 0:

        body = """
अभी आपने कोई mock test complete नहीं किया है।

पहला mock test देकर अपनी performance यहाँ देखें। 📈
"""

    else:

        body = f"""
📝 Tests Given: {row["tests"]}

🎯 Average Score:
{row["avg_score"]:.2f}

📊 Average Accuracy:
{row["avg_accuracy"]:.2f}%

🏆 Best Score:
{row["best_score"]:.2f}
"""

    await simple_menu(
        query,
        "📊 My Performance",
        body
    )


# =========================================================
# PRACTICE
# =========================================================

async def practice_menu(query):

    await simple_menu(
        query,
        "📚 Practice",
        """
Subject-wise practice mode जल्द available होगा।

अभी आप 📝 Mock Test से 100-question SSC CGL practice कर सकते हैं।
"""
    )


# =========================================================
# PYQ
# =========================================================

async def pyq_menu(query):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM questions
        WHERE exam = ?
        AND kind = 'PYQ'
        AND verified = 1
    """, (EXAM,))

    count = cur.fetchone()[0]

    conn.close()

    await simple_menu(
        query,
        "📜 PYQ",
        f"""
Verified SSC CGL PYQs available: {count}

⚠️ PYQ में केवल verified
year + shift + source वाले questions रखे जाएंगे।
"""
    )


# =========================================================
# CURRENT AFFAIRS
# =========================================================

async def current_affairs_menu(query):

    await simple_menu(
        query,
        "📰 Current Affairs",
        """
Current Affairs module जल्द available होगा।

Verified exam-oriented current affairs यहाँ जोड़े जाएंगे।
"""
    )


# =========================================================
# WRONG QUESTIONS
# =========================================================

async def wrong_menu(query):

    user_id = query.from_user.id

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM wrong_questions
        WHERE user_id = ?
    """, (user_id,))

    count = cur.fetchone()[0]

    conn.close()

    await simple_menu(
        query,
        "❌ Wrong Questions",
        f"""
आपके Wrong Questions: {count}

Mock Test में गलत किए गए questions यहाँ automatically save होंगे।
"""
    )


# =========================================================
# SAVED
# =========================================================

async def saved_menu(query):

    user_id = query.from_user.id

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM saved_questions
        WHERE user_id = ?
    """, (user_id,))

    count = cur.fetchone()[0]

    conn.close()

    await simple_menu(
        query,
        "🔖 Saved Questions",
        f"""
Saved Questions: {count}

आप important questions को बाद में revision के लिए save कर सकेंगे।
"""
    )


# =========================================================
# LEADERBOARD
# =========================================================

async def leaderboard_menu(query):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            u.first_name,
            MAX(a.score) AS best_score
        FROM attempts a
        LEFT JOIN users u
        ON u.user_id = a.user_id
        WHERE a.exam = ?
        GROUP BY a.user_id
        ORDER BY best_score DESC
        LIMIT 10
    """, (EXAM,))

    rows = cur.fetchall()

    conn.close()

    if not rows:

        body = "अभी leaderboard के लिए data उपलब्ध नहीं है।"

    else:

        lines = ["🏆 TOP PERFORMERS", ""]

        for i, row in enumerate(rows, 1):

            name = row["first_name"] or "Candidate"

            lines.append(
                f"{i}. {name} — {row['best_score']:.2f}"
            )

        body = "\n".join(lines)

    await simple_menu(
        query,
        "🏆 Leaderboard",
        body
    )


# =========================================================
# PROFILE
# =========================================================

async def profile_menu(query):

    user = query.from_user

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM attempts
        WHERE user_id = ?
    """, (user.id,))

    tests = cur.fetchone()[0]

    conn.close()

    await simple_menu(
        query,
        "👤 Profile",
        f"""
👤 Name: {user.first_name or "Candidate"}

🆔 User ID: {user.id}

📝 Mock Tests: {tests}

📚 Exam: SSC CGL
"""
    )


# =========================================================
# HELP
# =========================================================

async def help_menu(query):

    await simple_menu(
        query,
        "❓ Help",
        """
⚡ Quiz
Quick practice questions

📝 Mock Test
SSC CGL Tier-I style 100-question mock

📚 Practice
Subject/topic practice

📜 PYQ
Verified previous year questions

📰 Current Affairs
Exam-oriented current affairs

📊 My Performance
Your mock test statistics

❌ Wrong Questions
गलत किए questions

🔖 Saved Questions
Revision के लिए saved questions
"""
    )


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def callback_handler(update, context):

    query = update.callback_query

    data = query.data or ""

    # Answer callback ONLY once here.
    try:
        await query.answer()
    except Exception:
        pass

    # ---------------- HOME ----------------

    if data == "home":

        old_task = context.user_data.get(
            "timer_task"
        )

        if old_task:

            try:
                old_task.cancel()
            except Exception:
                pass

        context.user_data.clear()

        await query.edit_message_text(
            "🏠 EXAMPREP Main Menu\n\n👇 Choose an option:",
            reply_markup=home_keyboard()
        )

        return

    # ---------------- MOCK ----------------

    if data == "mock":
        await mock_intro(query)
        return

    if data == "mock_start":

        # query.answer already done
        await mock_start(
            query,
            context
        )

        return

    # ---------------- ANSWER ----------------

    if data.startswith("ans:"):

        try:
            option = int(
                data.split(":")[1]
            )
        except Exception:
            return

        # Don't call query.answer again.
        # answer_question normally answers itself,
        # so use direct logic here.

        if remaining_time(context) <= 0:

            await section_finished(
                query,
                context
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

        context.user_data.setdefault(
            "answers",
            {}
        )[str(q["id"])] = option

        await show_question(
            query,
            context
        )

        return

    # ---------------- NEXT ----------------

    if data == "next":

        await move_question(
            query,
            context,
            1
        )

        return

    # ---------------- PREVIOUS ----------------

    if data == "prev":

        await move_question(
            query,
            context,
            -1
        )

        return

    # ---------------- CLEAR ----------------

    if data == "clear":

        await clear_answer(
            query,
            context
        )

        return

    # ---------------- REVIEW ----------------

    if data == "review":

        index = context.user_data.get(
            "mock_index",
            0
        )

        reviews = context.user_data.setdefault(
            "reviews",
            set()
        )

        if index in reviews:

            reviews.remove(index)

        else:

            reviews.add(index)

        await show_question(
            query,
            context
        )

        return

    # ---------------- GRID ----------------

    if data == "qgrid":

        await question_grid(
            query,
            context
        )

        return

    # ---------------- BACK QUESTION ----------------

    if data == "back_question":

        await show_question(
            query,
            context
        )

        return

    # ---------------- GOTO ----------------

    if data.startswith("goto:"):

        try:
            index = int(
                data.split(":")[1]
            )
        except Exception:
            return

        await goto_question(
            query,
            context,
            index
        )

        return

    # ---------------- SUBMIT ----------------

    if data == "submit":

        await submit_confirm(
            query,
            context
        )

        return

    if data == "final_submit":

        # Cancel timer

        task = context.user_data.get(
            "timer_task"
        )

        if task:

            try:
                task.cancel()
            except Exception:
                pass

        context.user_data[
            "mock_finished"
        ] = True

        await show_result(
            query,
            context
        )

        return

    # ---------------- RESULT ----------------

    if data == "result":

        await show_result(
            query,
            context
        )

        return

    # ---------------- ANALYSIS ----------------

    if data == "analysis":

        await show_analysis(
            query,
            context
        )

        return

    # ---------------- OTHER MENUS ----------------

    if data == "quiz":

        await simple_menu(
            query,
            "⚡ Quiz",
            "Quick Quiz module जल्द available होगा।"
        )

        return

    if data == "practice":

        await practice_menu(query)
        return

    if data == "pyq":

        await pyq_menu(query)
        return

    if data == "current_affairs":

        await current_affairs_menu(query)
        return

    if data == "performance":

        await performance_menu(query)
        return

    if data == "wrong":

        await wrong_menu(query)
        return

    if data == "saved":

        await saved_menu(query)
        return

    if data == "leaderboard":

        await leaderboard_menu(query)
        return

    if data == "profile":

        await profile_menu(query)
        return

    if data == "help":

        await help_menu(query)
        return


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(update, context):

    print(
        "BOT ERROR:",
        repr(context.error)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:

        print(
            "ERROR: BOT_TOKEN environment variable missing."
        )

        return

    if not BANK_OK:

        print(
            "WARNING: Question bank does not have "
            "25 questions in every section."
        )

    print("===================================")
    print("EXAMPREP BOT STARTING")
    print("Exam:", EXAM)
    print("Mock:", MOCK_NAME)
    print("===================================")

    app = (
        Application.builder()
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
            callback_handler
        )
    )

    app.add_error_handler(
        error_handler
    )

    print("Bot polling started.")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
