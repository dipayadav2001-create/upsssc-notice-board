import os
import json
import random
import sqlite3
import time
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

EXAM = "SSC CGL"

QUESTION_FILE = "question_bank.json"

TOTAL_QUESTIONS = 100
SECTION_SIZE = 25
SECTION_TIME = 15 * 60
TOTAL_TIME = 60 * 60

NEGATIVE_MARKS = 0.50
CORRECT_MARKS = 2.0

SECTIONS = [
    ("Reasoning", "General Intelligence & Reasoning"),
    ("General Awareness", "General Awareness"),
    ("Maths", "Quantitative Aptitude"),
    ("English", "English Comprehension"),
]


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"EXAMPREP SSC CGL BOT LIVE")

    def log_message(self, format, *args):
        return


def start_health_server():

    port = int(os.environ.get("PORT", "10000"))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"Health server running on port {port}")

    server.serve_forever()


threading.Thread(
    target=start_health_server,
    daemon=True
).start()


# =========================================================
# DATABASE
# =========================================================

DB_FILE = "examprep.db"


def get_db():

    conn = sqlite3.connect(
        DB_FILE,
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
            username TEXT,
            first_name TEXT,
            created_at REAL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# LOAD QUESTIONS
# =========================================================

def load_questions():

    if not os.path.exists(QUESTION_FILE):
        raise FileNotFoundError(
            f"{QUESTION_FILE} not found"
        )

    with open(
        QUESTION_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "question_bank.json must contain a JSON list"
        )

    valid = []

    for q in data:

        if not isinstance(q, dict):
            continue

        required = [
            "subject",
            "question",
            "options",
            "answer",
        ]

        if not all(k in q for k in required):
            continue

        if q["subject"] not in [
            "Reasoning",
            "General Awareness",
            "Maths",
            "English",
        ]:
            continue

        if not isinstance(q["options"], list):
            continue

        if len(q["options"]) != 4:
            continue

        if not isinstance(q["answer"], int):
            continue

        if not 0 <= q["answer"] <= 3:
            continue

        valid.append(q)

    counts = {}

    for q in valid:

        subject = q["subject"]

        counts[subject] = counts.get(
            subject,
            0
        ) + 1

    print("================================")
    print("SSC CGL QUESTION BANK")
    print("Total:", len(valid))

    for subject, _ in SECTIONS:
        print(
            subject,
            ":",
            counts.get(subject, 0)
        )

    print("================================")

    for subject, _ in SECTIONS:

        if counts.get(subject, 0) < 25:

            raise ValueError(
                f"{subject} has only "
                f"{counts.get(subject, 0)} questions. "
                f"Need 25."
            )

    # exactly 25 from every section
    final_questions = []

    for subject, _ in SECTIONS:

        pool = [
            q for q in valid
            if q["subject"] == subject
        ]

        random.shuffle(pool)

        final_questions.extend(
            pool[:25]
        )

    if len(final_questions) != 100:

        raise ValueError(
            "Unable to create 100 question mock."
        )

    print("100-question SSC CGL mock ready.")

    return final_questions


QUESTIONS = load_questions()


# =========================================================
# USER DATA
# =========================================================

def register_user(update):

    user = update.effective_user

    conn = get_db()

    conn.execute(
        """
        INSERT OR IGNORE INTO users
        (user_id, username, first_name, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            user.id,
            user.username or "",
            user.first_name or "",
            time.time(),
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# HOME
# =========================================================

def home_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📝 Mock Test",
                callback_data="mock"
            )
        ],

        [
            InlineKeyboardButton(
                "⚡ Quiz",
                callback_data="quiz"
            ),

            InlineKeyboardButton(
                "📚 Practice",
                callback_data="practice"
            )
        ],

        [
            InlineKeyboardButton(
                "📜 PYQ",
                callback_data="pyq"
            ),

            InlineKeyboardButton(
                "📰 Current Affairs",
                callback_data="current"
            )
        ],

        [
            InlineKeyboardButton(
                "📊 My Performance",
                callback_data="performance"
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Wrong Questions",
                callback_data="wrong"
            ),

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
        ],

    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    register_user(update)

    context.user_data.clear()

    text = (
        "🎯 <b>EXAMPREP</b>\n\n"
        "Competitive Exam Practice Platform\n\n"
        "👇 नीचे से अपना विकल्प चुनें:"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=home_keyboard()
    )


# =========================================================
# MOCK INTRO
# =========================================================

async def mock_intro(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🇮🇳 SSC CGL Tier-I",
                callback_data="start_mock"
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="home"
            )
        ]

    ])

    text = (
        "📝 <b>SSC CGL Tier-I</b>\n\n"

        "📌 Total Questions: <b>100</b>\n"
        "⏱ Total Time: <b>60 Minutes</b>\n"
        "🎯 Marks: <b>200</b>\n"
        "❌ Negative Marking: <b>0.50</b>\n\n"

        "Sections:\n"
        "🧠 Reasoning — 25\n"
        "🌍 General Awareness — 25\n"
        "➗ Quantitative Aptitude — 25\n"
        "🔤 English Comprehension — 25\n\n"

        "⚠️ प्रत्येक section के लिए 15 मिनट का timer होगा।"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# CREATE MOCK
# =========================================================

async def start_mock(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    questions = QUESTIONS.copy()

    # हर section को अलग रखकर क्रम बनाएं
    ordered = []

    for subject, _ in SECTIONS:

        section_questions = [
            q for q in questions
            if q["subject"] == subject
        ]

        random.shuffle(section_questions)

        ordered.extend(
            section_questions[:25]
        )

    context.user_data["mock"] = {

        "questions": ordered,

        "current": 0,

        "answers": {},

        "marked": set(),

        "started_at": time.time(),

        "section_started": time.time(),

        "finished": False,

    }

    await show_question(
        query,
        context
    )


# =========================================================
# SECTION HELPERS
# =========================================================

def get_mock(context):

    return context.user_data.get("mock")


def get_section(index):

    return index // SECTION_SIZE


def get_section_name(index):

    section_index = get_section(index)

    if section_index >= 4:
        section_index = 3

    return SECTIONS[section_index][1]


def get_section_short(index):

    section_index = get_section(index)

    if section_index >= 4:
        section_index = 3

    return SECTIONS[section_index][0]


def get_remaining_section_seconds(mock):

    elapsed = int(
        time.time() -
        mock["section_started"]
    )

    return max(
        0,
        SECTION_TIME - elapsed
    )


def format_time(seconds):

    seconds = max(0, int(seconds))

    minutes = seconds // 60
    secs = seconds % 60

    return f"{minutes:02d}:{secs:02d}"


# =========================================================
# QUESTION TEXT
# =========================================================

def question_text(
    q,
    number,
    mock
):

    answered = len(
        mock["answers"]
    )

    remaining = (
        TOTAL_QUESTIONS -
        answered
    )

    section_name = get_section_name(
        number - 1
    )

    section_number = (
        get_section(number - 1) + 1
    )

    section_time = format_time(
        get_remaining_section_seconds(
            mock
        )
    )

    total_elapsed = int(
        time.time() -
        mock["started_at"]
    )

    total_remaining = format_time(
        max(
            0,
            TOTAL_TIME -
            total_elapsed
        )
    )

    return (
        f"📝 <b>SSC CGL Tier-I</b>  |  "
        f"<b>Mock Test</b>\n\n"

        f"<b>Question {number} / 100</b>     "
        f"⏱ <b>{section_time}</b>\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"

        f"📚 Section {section_number}/4\n"
        f"<b>{section_name}</b>\n\n"

        f"⏳ Total Time: {total_remaining}\n"
        f"✅ Attempted: {answered}   "
        f"📌 Remaining: {remaining}\n\n"

        f"<b>{q['question']}</b>"
    )


# =========================================================
# QUESTION BUTTONS
# =========================================================

def answer_keyboard(
    q,
    selected
):

    rows = []

    labels = [
        "A",
        "B",
        "C",
        "D",
    ]

    for i in range(4):

        prefix = "🔵"

        if selected == i:
            prefix = "✅"

        text = (
            f"{prefix} {labels[i]}. "
            f"{q['options'][i]}"
        )

        rows.append([
            InlineKeyboardButton(
                text,
                callback_data=f"ans:{i}"
            )
        ])

    return rows


# =========================================================
# MAIN MOCK UI
# =========================================================

async def show_question(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    if mock["finished"]:
        return

    current = mock["current"]

    # Section auto transition
    if current > 0:

        current_section = get_section(
            current
        )

        previous_section = get_section(
            current - 1
        )

        if current_section != previous_section:

            mock["section_started"] = time.time()

    # section timeout
    remaining_section = (
        get_remaining_section_seconds(
            mock
        )
    )

    if remaining_section <= 0:

        next_index = (
            ((current // 25) + 1)
            * 25
        )

        if next_index >= 100:

            await finish_mock(
                query,
                context
            )

            return

        mock["current"] = next_index
        mock["section_started"] = time.time()

        current = next_index

    # total timeout
    total_elapsed = (
        time.time() -
        mock["started_at"]
    )

    if total_elapsed >= TOTAL_TIME:

        await finish_mock(
            query,
            context
        )

        return

    q = mock["questions"][current]

    selected = mock["answers"].get(
        current
    )

    text = question_text(
        q,
        current + 1,
        mock
    )

    rows = answer_keyboard(
        q,
        selected
    )

    # Navigation
    previous_button = InlineKeyboardButton(
        "⬅️ Previous",
        callback_data="previous"
    )

    next_button = InlineKeyboardButton(
        "Save & Next ➡️",
        callback_data="next"
    )

    mark_text = (
        "🔖 Unmark"
        if current in mock["marked"]
        else "🔖 Mark"
    )

    mark_button = InlineKeyboardButton(
        mark_text,
        callback_data="mark"
    )

    rows.append([
        previous_button,
        next_button,
        mark_button
    ])

    # Question palette button
    rows.append([
        InlineKeyboardButton(
            "☷  Questions",
            callback_data="palette"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            "🏁 Submit Test",
            callback_data="submit_confirm"
        )
    ])

    keyboard = InlineKeyboardMarkup(
        rows
    )

    try:

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
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
    context
):

    mock = get_mock(context)

    if not mock:
        return

    try:

        option = int(
            query.data.split(":")[1]
        )

    except:

        return

    current = mock["current"]

    mock["answers"][current] = option

    await query.answer(
        "उत्तर save हो गया ✅"
    )

    await show_question(
        query,
        context
    )


# =========================================================
# NEXT
# =========================================================

async def next_question(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    current = mock["current"]

    if current >= 99:

        await finish_mock(
            query,
            context
        )

        return

    next_index = current + 1

    # Section changed
    if get_section(next_index) != get_section(current):

        mock["section_started"] = time.time()

    mock["current"] = next_index

    await query.answer()

    await show_question(
        query,
        context
    )


# =========================================================
# PREVIOUS
# =========================================================

async def previous_question(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    current = mock["current"]

    if current <= 0:

        await query.answer(
            "यह पहला प्रश्न है।"
        )

        return

    previous_index = current - 1

    if get_section(previous_index) != get_section(current):

        # Do not reset section timer when going backward
        pass

    mock["current"] = previous_index

    await query.answer()

    await show_question(
        query,
        context
    )


# =========================================================
# MARK
# =========================================================

async def mark_question(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    current = mock["current"]

    if current in mock["marked"]:

        mock["marked"].remove(
            current
        )

        await query.answer(
            "Review हटाया गया"
        )

    else:

        mock["marked"].add(
            current
        )

        await query.answer(
            "Question marked 🔖"
        )

    await show_question(
        query,
        context
    )


# =========================================================
# QUESTION PALETTE
# =========================================================

def palette_keyboard(mock):

    rows = []

    for start in range(
        0,
        100,
        10
    ):

        row = []

        for i in range(
            start,
            min(start + 10, 100)
        ):

            if i == mock["current"]:

                text = f"🔵 {i + 1}"

            elif i in mock["marked"]:

                text = f"🟠 {i + 1}"

            elif i in mock["answers"]:

                text = f"🟢 {i + 1}"

            else:

                text = f"{i + 1}"

            row.append(
                InlineKeyboardButton(
                    text,
                    callback_data=f"goto:{i}"
                )
            )

        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            "❌ Close",
            callback_data="close_palette"
        )
    ])

    return InlineKeyboardMarkup(
        rows
    )


async def show_palette(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    answered = len(
        mock["answers"]
    )

    marked = len(
        mock["marked"]
    )

    text = (
        "☷ <b>Question Palette</b>\n\n"

        "🔵 Current\n"
        "🟢 Answered\n"
        "🟠 Marked\n"
        "⚪ Not Visited\n\n"

        f"✅ Answered: {answered}/100\n"
        f"🔖 Marked: {marked}\n\n"

        "किसी भी question number पर tap करके "
        "सीधे उस question पर जाएँ।"
    )

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=palette_keyboard(mock)
    )


# =========================================================
# GOTO QUESTION
# =========================================================

async def goto_question(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    try:

        index = int(
            query.data.split(":")[1]
        )

    except:

        return

    if index < 0 or index >= 100:
        return

    mock["current"] = index

    await query.answer(
        f"Question {index + 1}"
    )

    await show_question(
        query,
        context
    )


# =========================================================
# CLOSE PALETTE
# =========================================================

async def close_palette(
    query,
    context
):

    await query.answer()

    await show_question(
        query,
        context
    )


# =========================================================
# SUBMIT CONFIRM
# =========================================================

async def submit_confirm(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    answered = len(
        mock["answers"]
    )

    marked = len(
        mock["marked"]
    )

    unanswered = (
        100 - answered
    )

    text = (
        "🏁 <b>Submit Test?</b>\n\n"

        f"✅ Attempted: <b>{answered}</b>\n"
        f"⚪ Unattempted: <b>{unanswered}</b>\n"
        f"🔖 Marked: <b>{marked}</b>\n\n"

        "क्या आप test submit करना चाहते हैं?"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "✅ Submit",
                callback_data="submit_final"
            ),

            InlineKeyboardButton(
                "❌ Continue Test",
                callback_data="continue_test"
            )
        ]

    ])

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# SUBMIT
# =========================================================

async def finish_mock(
    query,
    context
):

    mock = get_mock(context)

    if not mock:
        return

    if mock["finished"]:
        return

    mock["finished"] = True

    correct = 0
    wrong = 0
    skipped = 0

    questions = mock["questions"]

    for i, q in enumerate(questions):

        if i not in mock["answers"]:

            skipped += 1

            continue

        selected = mock["answers"][i]

        if selected == q["answer"]:

            correct += 1

        else:

            wrong += 1

   
