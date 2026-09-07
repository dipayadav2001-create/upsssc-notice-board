import os
import json
import random
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
DB = os.getenv("DB_PATH", "exam_prep.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)

EXAM = "SSC CGL"
MOCK_NAME = "SSC CGL Tier-I"
SECTION_ORDER = [
    "General Intelligence & Reasoning",
    "General Awareness",
    "Quantitative Aptitude",
    "English Comprehension",
]
SECTION_SHORT = {
    "General Intelligence & Reasoning": "Reasoning",
    "General Awareness": "General Awareness",
    "Quantitative Aptitude": "Maths",
    "English Comprehension": "English",
}
QUESTIONS_PER_SECTION = 25
SECTION_SECONDS = 15 * 60
TOTAL_SECONDS = 60 * 60
NEGATIVE_PER_WRONG = 0.50

MOTIVATIONS = {
    "excellent": [
        "बहुत बढ़िया! आपकी accuracy मजबूत है—अब इसी consistency को बनाए रखो। 🏆",
        "आज की performance selection-level discipline दिखा रही है। इसी pace पर चलते रहो। 🔥",
    ],
    "good": [
        "अच्छी performance! अब थोड़ी accuracy और speed सुधारकर score को अगले स्तर पर ले जाओ। 🚀",
        "आप सही दिशा में बढ़ रहे हो। Weak areas पर targeted practice करो। 🎯",
    ],
    "average": [
        "आज का attempt आपकी अगली improvement list तैयार कर गया। गलत सवालों को दोबारा जरूर पढ़ो। 📚",
        "Score से ज्यादा महत्वपूर्ण है कि आपने क्या सीखा। अगला attempt और मजबूत होगा। 💪",
    ],
    "low": [
        "कम score सिर्फ आज का result है, आपकी क्षमता नहीं। गलतियों को practice में बदलो। 🌱",
        "आज की गलतियाँ कल के सही answers बन सकती हैं—बस revision मत छोड़ो। 🔥",
    ],
}

# These are foundation/practice questions only. They are NOT claimed as PYQs.
SEED_QUESTIONS = [
    ("General Awareness", "Polity", "भारतीय संविधान में मौलिक अधिकार किस भाग में वर्णित हैं?", ["भाग I", "भाग II", "भाग III", "भाग IV"], 2, "भारतीय संविधान के भाग III में मौलिक अधिकारों का वर्णन है।"),
    ("General Awareness", "History", "भारतीय राष्ट्रीय कांग्रेस की स्थापना किस वर्ष हुई थी?", ["1885", "1905", "1919", "1947"], 0, "भारतीय राष्ट्रीय कांग्रेस की स्थापना 1885 में हुई थी।"),
    ("General Awareness", "Geography", "क्षेत्रफल की दृष्टि से भारत का सबसे बड़ा राज्य कौन-सा है?", ["मध्य प्रदेश", "राजस्थान", "उत्तर प्रदेश", "महाराष्ट्र"], 1, "राजस्थान क्षेत्रफल की दृष्टि से भारत का सबसे बड़ा राज्य है।"),
    ("General Awareness", "Science", "रक्त को छानकर अपशिष्ट पदार्थों को बाहर निकालने में मुख्य भूमिका किस अंग की है?", ["हृदय", "फेफड़े", "गुर्दे", "मस्तिष्क"], 2, "गुर्दे रक्त को filter करके अपशिष्ट पदार्थों को मूत्र के माध्यम से बाहर निकालने में प्रमुख भूमिका निभाते हैं।"),
    ("General Awareness", "Economics", "भारत में मौद्रिक नीति का संचालन मुख्यतः कौन करता है?", ["SEBI", "RBI", "NITI Aayog", "Finance Commission"], 1, "भारतीय रिज़र्व बैंक मौद्रिक नीति का संचालन करता है।"),
    ("General Intelligence & Reasoning", "Analogy", "Book : Read :: Food : ?", ["Cook", "Eat", "Buy", "Serve"], 1, "Book को Read किया जाता है; Food को Eat किया जाता है।"),
    ("Quantitative Aptitude", "Percentage", "200 का 15% कितना है?", ["15", "20", "30", "35"], 2, "200 × 15/100 = 30।"),
    ("English Comprehension", "Vocabulary", 'Choose the synonym of “Rapid”.', ["Slow", "Fast", "Weak", "Late"], 1, "Rapid का अर्थ Fast होता है।"),
]


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = connect()
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam TEXT NOT NULL,
        subject TEXT NOT NULL,
        topic TEXT NOT NULL,
        question TEXT NOT NULL,
        options TEXT NOT NULL,
        answer INTEGER NOT NULL,
        explanation TEXT,
        kind TEXT NOT NULL DEFAULT 'Practice',
        year INTEGER,
        shift TEXT,
        source TEXT,
        verified INTEGER NOT NULL DEFAULT 0,
        difficulty TEXT DEFAULT 'Mixed'
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        exam TEXT NOT NULL,
        mode TEXT NOT NULL,
        score REAL NOT NULL,
        total INTEGER NOT NULL,
        correct INTEGER NOT NULL,
        wrong INTEGER NOT NULL,
        skipped INTEGER NOT NULL,
        seconds INTEGER NOT NULL,
        negative_marks REAL NOT NULL DEFAULT 0,
        accuracy REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS answers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        selected INTEGER,
        correct INTEGER NOT NULL,
        seconds INTEGER NOT NULL DEFAULT 0,
        marked_review INTEGER NOT NULL DEFAULT 0
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        target_exam TEXT DEFAULT 'SSC CGL',
        language TEXT DEFAULT 'Hindi'
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS saved_questions(
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, question_id)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS user_wrong_questions(
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, question_id)
    )""")
    if con.execute("SELECT COUNT(*) FROM questions WHERE exam=?", (EXAM,)).fetchone()[0] == 0:
        con.executemany(
            """INSERT INTO questions
            (exam,subject,topic,question,options,answer,explanation,kind,verified,difficulty)
            VALUES (?,?,?,?,?,?,?,?,0,'Mixed')""",
            [(EXAM, s, t, q, json.dumps(o, ensure_ascii=False), a, e, "Practice") for s,t,q,o,a,e in SEED_QUESTIONS]
        )
    con.commit()
    con.close()


def markup(rows):
    return InlineKeyboardMarkup(rows)


def home_markup():
    return markup([
        [InlineKeyboardButton("⚡ Quiz", callback_data="menu:quiz"), InlineKeyboardButton("📝 Mock Test", callback_data="menu:mock")],
        [InlineKeyboardButton("📚 Practice", callback_data="menu:practice"), InlineKeyboardButton("📜 PYQ", callback_data="menu:pyq")],
        [InlineKeyboardButton("📰 Current Affairs", callback_data="menu:ca")],
        [InlineKeyboardButton("📊 My Performance", callback_data="performance"), InlineKeyboardButton("❌ Wrong Questions", callback_data="wrong")],
        [InlineKeyboardButton("🔖 Saved Questions", callback_data="saved"), InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile"), InlineKeyboardButton("❓ Help", callback_data="help")],
    ])


def back_home():
    return markup([[InlineKeyboardButton("🏠 Home", callback_data="home")]])


def ensure_user(user):
    con = connect()
    con.execute("INSERT OR IGNORE INTO users(user_id,name) VALUES (?,?)", (user.id, user.first_name or "Aspirant"))
    con.execute("UPDATE users SET name=? WHERE user_id=?", (user.first_name or "Aspirant", user.id))
    con.commit()
    con.close()


def get_question_count_by_subject():
    con = connect()
    rows = con.execute("SELECT subject,COUNT(*) n FROM questions WHERE exam=? GROUP BY subject", (EXAM,)).fetchall()
    con.close()
    return {r["subject"]: r["n"] for r in rows}


def mock_ready():
    counts = get_question_count_by_subject()
    return all(counts.get(s, 0) >= QUESTIONS_PER_SECTION for s in SECTION_ORDER)


def format_score(score):
    return str(int(score)) if float(score).is_integer() else f"{score:.1f}"


def pick_motivation(accuracy):
    if accuracy >= 90:
        pool = MOTIVATIONS["excellent"]
    elif accuracy >= 75:
        pool = MOTIVATIONS["good"]
    elif accuracy >= 50:
        pool = MOTIVATIONS["average"]
    else:
        pool = MOTIVATIONS["low"]
    return random.choice(pool)


def cancel_jobs(context, user_id):
    jq = context.application.job_queue
    if not jq:
        return
    for job in jq.get_jobs_by_name(f"mock_timeout_{user_id}"):
        job.schedule_removal()


def schedule_section_timeout(context, user_id):
    cancel_jobs(context, user_id)
    jq = context.application.job_queue
    if jq:
        jq.run_once(section_timeout, when=SECTION_SECONDS, data={"user_id": user_id}, name=f"mock_timeout_{user_id}")


def selected_status(t, index):
    a = t["answers"].get(index)
    if a and a.get("selected") is not None:
        return "🟢"
    if index in t["review"]:
        return "🟡"
    return "⚪"


def navigation_markup(t):
    rows = []
    start = t["section_start"]
    end = t["section_end"]
    for base in range(start, end, 5):
        row = []
        for i in range(base, min(base + 5, end)):
            row.append(InlineKeyboardButton(f"{selected_status(t,i)} {i-base+1}", callback_data=f"goto:{i}"))
        rows.append(row)
    rows.append([
        InlineKeyboardButton("⬅️ Prev", callback_data="prev"),
        InlineKeyboardButton("☷ Questions", callback_data="nav"),
        InlineKeyboardButton("Next ➡️", callback_data="next"),
    ])
    rows.append([
        InlineKeyboardButton("🔖 Mark Review", callback_data="review"),
        InlineKeyboardButton("🧹 Clear", callback_data="clear"),
    ])
    rows.append([InlineKeyboardButton("🏁 Submit Test", callback_data="submit_confirm")])
    return markup(rows)


def quiz_markup(item, saved=False):
    opts = json.loads(item["options"])
    rows = [[InlineKeyboardButton(f"{chr(65+i)}", callback_data=f"qans:{i}") for i in range(len(opts))]]
    rows.append([
        InlineKeyboardButton("🔖 Saved" if saved else "🔖 Save", callback_data="save_toggle"),
        InlineKeyboardButton("⏭️ Skip", callback_data="qskip"),
    ])
    rows.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
    return markup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    ensure_user(update.effective_user)
    context.user_data.pop("test", None)
    await update.message.reply_text(
        "🧠 EXAMPREP\n\nनमस्ते 👋\n\n🎯 अभी focus: SSC CGL\n\n⚡ Quiz और 📝 Mock Test अलग-अलग हैं।\n\nनीचे से अपना विकल्प चुनें:",
        reply_markup=home_markup()
    )


async def home_callback(q):
    await q.edit_message_text("🧠 EXAMPREP\n\nअपना विकल्प चुनें:", reply_markup=home_markup())


async def show_mock_menu(q):
    counts = get_question_count_by_subject()
    status = "\n".join(f"• {SECTION_SHORT[s]}: {counts.get(s,0)}/25" for s in SECTION_ORDER)
    ready = mock_ready()
    if ready:
        text = (
            f"📝 {MOCK_NAME}\n\n"
            "Official-pattern configuration:\n"
            "• 100 Questions\n• 60 Minutes total\n• 25 Questions per section\n• 15 Minutes per section\n• 0.50 negative marking per wrong answer\n\n"
            "हर section का timer अलग चलेगा। समय समाप्त होने पर section automatically submit होकर अगला section खुलेगा।\n\n"
            "🚀 Ready to start?"
        )
        rows = [[InlineKeyboardButton("🚀 Start Full Mock", callback_data="mock:instructions")]]
    else:
        text = (
            f"📝 {MOCK_NAME}\n\n"
            "Mock engine तैयार है, लेकिन पूरा 100-question bank अभी load नहीं हुआ है।\n\n"
            f"Current question-bank coverage:\n{status}\n\n"
            "⚠️ मैं 8 questions को 100-question mock बनाकर fake test नहीं चलाऊँगा। पहले real question bank import करना होगा।"
        )
        rows = [[InlineKeyboardButton("📥 Import Guide", callback_data="admin:guide")]] if ADMIN_ID else []
    rows.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
    await q.edit_message_text(text, reply_markup=markup(rows))


async def show_quiz_menu(q):
    await q.edit_message_text(
        "⚡ QUICK QUIZ\n\n📘 SSC CGL\n\nPractice mode — answer के बाद तुरंत सही उत्तर और explanation मिलेगा।\n\nकितने प्रश्न?",
        reply_markup=markup([
            [InlineKeyboardButton("🔟 10", callback_data="quizsetup:10"), InlineKeyboardButton("2️⃣0️⃣ 20", callback_data="quizsetup:20")],
            [InlineKeyboardButton("3️⃣0️⃣ 30", callback_data="quizsetup:30"), InlineKeyboardButton("🎲 Mixed 10", callback_data="quizsetup:10")],
            [InlineKeyboardButton("🏠 Home", callback_data="home")],
        ])
    )


async def show_practice_menu(q):
    counts = get_question_count_by_subject()
    rows = []
    for s in SECTION_ORDER:
        rows.append([InlineKeyboardButton(f"{SECTION_SHORT[s]} ({counts.get(s,0)})", callback_data=f"practice:{s}")])
    rows.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
    await q.edit_message_text("📚 PRACTICE\n\nSSC CGL — Subject चुनें:", reply_markup=markup(rows))


async def show_help(q):
    await q.edit_message_text(
        "❓ HELP\n\n"
        "⚡ Quiz = practice + instant explanation\n"
        "📝 Mock = timed SSC CGL Tier-I simulation\n"
        "📜 PYQ = verified previous-year questions\n"
        "📊 Performance = score + accuracy + timing\n\n"
        "🟢 Answered  🟡 Marked for Review  ⚪ Unattempted\n\n"
        "PYQ में year/shift/source verification के बिना किसी question को PYQ नहीं कहा जाएगा।",
        reply_markup=back_home()
    )


async def show_profile(q):
    con = connect()
    u = con.execute("SELECT * FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()
    con.close()
    await q.edit_message_text(
        f"👤 PROFILE\n\n🎯 Target Exam: {u['target_exam'] if u else EXAM}\n🇮🇳 Language: {u['language'] if u else 'Hindi'}",
        reply_markup=back_home()
    )


async def performance(q):
    con = connect()
    row = con.execute("""SELECT COUNT(*) n, COALESCE(SUM(correct),0) correct,
        COALESCE(SUM(wrong),0) wrong, COALESCE(SUM(skipped),0) skipped,
        COALESCE(SUM(total),0) total, COALESCE(SUM(seconds),0) seconds,
        COALESCE(SUM(negative_marks),0) neg FROM attempts
        WHERE user_id=? AND exam=?""", (q.from_user.id, EXAM)).fetchone()
    con.close()
    avg_q = round(row["seconds"] / row["total"], 1) if row["total"] else 0
    acc = round(row["correct"] / row["correct"] + row["wrong"] * 0 if False else (row["correct"] / (row["correct"] + row["wrong"]) * 100 if row["correct"] + row["wrong"] else 0), 1)
    await q.edit_message_text(
        "📊 MY PERFORMANCE\n\n"
        f"📝 Tests Attempted: {row['n']}\n"
        f"❓ Questions: {row['total']}\n"
        f"✅ Correct: {row['correct']}\n❌ Wrong: {row['wrong']}\n⏭️ Skipped: {row['skipped']}\n"
        f"📈 Accuracy: {acc}%\n"
        f"⚡ Avg. Time / Question: {avg_q} sec\n"
        f"➖ Negative Marks: {row['neg']:.1f}",
        reply_markup=back_home()
    )


async def begin_quiz(q, context, n, subject: Optional[str] = None):
    con = connect()
    if subject:
        qs = con.execute("SELECT * FROM questions WHERE exam=? AND subject=? ORDER BY RANDOM() LIMIT ?", (EXAM, subject, n)).fetchall()
    else:
        qs = con.execute("SELECT * FROM questions WHERE exam=? ORDER BY RANDOM() LIMIT ?", (EXAM, n)).fetchall()
    con.close()
    if len(qs) < n:
        await q.edit_message_text(f"इस selection में केवल {len(qs)} questions उपलब्ध हैं। {n} पूरे questions के लिए question bank बढ़ाना होगा।", reply_markup=back_home())
        return
    context.user_data["test"] = {
        "mode": "Quiz", "qs": [dict(x) for x in qs], "i": 0, "answers": {}, "review": set(),
        "start": time.time(), "q_start": time.time(), "negative": False, "saved": set()
    }
    await send_quiz_question(q, context)


async def send_quiz_question(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Quiz":
        await q.edit_message_text("कोई active quiz नहीं है।", reply_markup=home_markup())
        return
    if t["i"] >= len(t["qs"]):
        await finish_test(q, context)
        return
    item = t["qs"][t["i"]]
    con = connect()
    saved = con.execute("SELECT 1 FROM saved_questions WHERE user_id=? AND question_id=?", (q.from_user.id, item["id"])).fetchone() is not None
    con.close()
    opts = json.loads(item["options"])
    text = f"⚡ QUICK QUIZ\n📘 {EXAM}\n📚 {item['subject']} • {item['topic']}\n\nQuestion {t['i']+1}/{len(t['qs'])}\n\n{item['question']}\n\n" + "\n".join(f"{chr(65+i)}. {o}" for i,o in enumerate(opts))
    await q.edit_message_text(text, reply_markup=quiz_markup(item, saved))


async def answer_quiz(q, context, idx):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Quiz":
        return
    item = t["qs"][t["i"]]
    elapsed = max(1, int(time.time() - t["q_start"]))
    t["answers"][t["i"]] = {"selected": idx, "seconds": elapsed}
    opts = json.loads(item["options"])
    correct = idx == item["answer"]
    icon = "✅ CORRECT" if correct else "❌ INCORRECT"
    text = f"{icon}\n\nसही उत्तर: {chr(65+item['answer'])}. {opts[item['answer']]}\n\n📖 Explanation\n{item['explanation'] or 'Explanation उपलब्ध नहीं है।'}\n\n🏷️ Topic: {item['topic']}\n⏱️ Your time: {elapsed} sec"
    if not correct:
        con = connect()
        con.execute("INSERT OR REPLACE INTO user_wrong_questions(user_id,question_id,created_at) VALUES (?,?,?)", (q.from_user.id,item["id"],datetime.now(timezone.utc).isoformat()))
        con.commit(); con.close()
    await q.edit_message_text(text, reply_markup=markup([[InlineKeyboardButton("➡️ Next Question", callback_data="qnext")]]))


async def quiz_skip(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Quiz":
        return
    elapsed = max(1, int(time.time() - t["q_start"]))
    t["answers"][t["i"]] = {"selected": None, "seconds": elapsed}
    t["i"] += 1
    t["q_start"] = time.time()
    await send_quiz_question(q, context)


async def save_toggle(q, context):
    t = context.user_data.get("test")
    if not t:
        return
    item = t["qs"][t["i"]]
    con = connect()
    exists = con.execute("SELECT 1 FROM saved_questions WHERE user_id=? AND question_id=?", (q.from_user.id,item["id"])).fetchone()
    if exists:
        con.execute("DELETE FROM saved_questions WHERE user_id=? AND question_id=?", (q.from_user.id,item["id"]))
        label = "🔖 Save"
    else:
        con.execute("INSERT OR IGNORE INTO saved_questions(user_id,question_id,created_at) VALUES (?,?,?)", (q.from_user.id,item["id"],datetime.now(timezone.utc).isoformat()))
        label = "🔖 Saved"
    con.commit(); con.close()
    opts = json.loads(item["options"])
    text = f"⚡ QUICK QUIZ\n📘 {EXAM}\n📚 {item['subject']} • {item['topic']}\n\nQuestion {t['i']+1}/{len(t['qs'])}\n\n{item['question']}\n\n" + "\n".join(f"{chr(65+i)}. {o}" for i,o in enumerate(opts))
    rows = [[InlineKeyboardButton(chr(65+i), callback_data=f"qans:{i}") for i in range(len(opts))], [InlineKeyboardButton(label, callback_data="save_toggle"), InlineKeyboardButton("⏭️ Skip", callback_data="qskip")], [InlineKeyboardButton("🏠 Home", callback_data="home")]]
    await q.edit_message_text(text, reply_markup=markup(rows))


async def build_mock_questions():
    con = connect()
    all_qs = []
    for subject in SECTION_ORDER:
        rows = con.execute("SELECT * FROM questions WHERE exam=? AND subject=? ORDER BY RANDOM() LIMIT ?", (EXAM, subject, QUESTIONS_PER_SECTION)).fetchall()
        if len(rows) < QUESTIONS_PER_SECTION:
            con.close(); return None
        all_qs.extend(dict(x) for x in rows)
    con.close()
    return all_qs


async def start_mock(q, context):
    qs = await build_mock_questions()
    if not qs:
        await show_mock_menu(q); return
    context.user_data["test"] = {
        "mode": "Mock Test", "qs": qs, "i": 0, "answers": {}, "review": set(),
        "start": time.time(), "q_start": time.time(), "section": 0,
        "section_start": 0, "section_end": 25, "negative": True, "saved": set(),
        "completed_sections": [], "section_seconds": {}, "section_started": time.time()
    }
    await send_mock_question(q, context, instructions=False)
    schedule_section_timeout(context, q.from_user.id)


async def send_mock_question(q, context, instructions=True):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test":
        await q.edit_message_text("कोई active mock नहीं है।", reply_markup=home_markup()); return
    if t["i"] < t["section_start"] or t["i"] >= t["section_end"]:
        t["i"] = t["section_start"]
    item = t["qs"][t["i"]]
    remaining = max(0, SECTION_SECONDS - int(time.time() - t["section_started"])) if "section_started" in t else SECTION_SECONDS
    opts = json.loads(item["options"])
    answer = t["answers"].get(t["i"], {}).get("selected")
    selected_note = f"\n\n🟢 Selected: {chr(65+answer)}" if answer is not None else ""
    text = (
        f"📝 {MOCK_NAME}\n"
        f"📚 Section: {SECTION_SHORT[SECTION_ORDER[t['section']]]}\n"
        f"⏱️ Section Time Left: {remaining//60:02d}:{remaining%60:02d}\n\n"
        f"Question {t['i']-t['section_start']+1}/{QUESTIONS_PER_SECTION}  •  Overall {t['i']+1}/100\n\n"
        f"{item['question']}\n\n" + "\n".join(f"{chr(65+i)}. {o}" for i,o in enumerate(opts)) + selected_note
    )
    await q.edit_message_text(text, reply_markup=navigation_markup(t))


async def show_instructions(q):
    await q.edit_message_text(
        f"📋 {MOCK_NAME} — Instructions\n\n"
        "1️⃣ कुल 100 प्रश्न होंगे।\n"
        "2️⃣ 4 sections में 25-25 प्रश्न होंगे।\n"
        "3️⃣ हर section के लिए 15 मिनट होंगे।\n"
        "4️⃣ Wrong answer पर 0.50 mark कटेगा।\n"
        "5️⃣ Section timer खत्म होने पर अगला section automatically शुरू होगा।\n"
        "6️⃣ Mark for Review बाद में उसी section में question खोलने के लिए है।\n"
        "7️⃣ Submit के बाद detailed result और question-wise analysis मिलेगा।\n\n"
        "⚠️ यह real exam जैसा practice simulation है। PYQ और practice questions अलग database में रखे जाते हैं।",
        reply_markup=markup([
            [InlineKeyboardButton("🚀 I Agree — Start Mock", callback_data="mock:start")],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu:mock")],
        ])
    )


async def answer_mock(q, context, idx):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    if t["i"] < t["section_start"] or t["i"] >= t["section_end"]: return
    elapsed = max(1, int(time.time()-t["q_start"]))
    old = t["answers"].get(t["i"], {})
    t["answers"][t["i"]] = {"selected": idx, "seconds": old.get("seconds",0)+elapsed}
    t["q_start"] = time.time()
    await send_mock_question(q, context, instructions=False)


async def mock_skip(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    t["answers"].setdefault(t["i"], {"selected": None, "seconds": 0})
    t["i"] += 1
    t["q_start"] = time.time()
    if t["i"] >= t["section_end"]:
        await complete_section(q, context)
    else:
        await send_mock_question(q, context, instructions=False)


async def mock_next(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    if t["i"] < t["section_end"]-1:
        t["i"] += 1
        t["q_start"] = time.time()
        await send_mock_question(q, context, instructions=False)
    else:
        await complete_section(q, context)


async def mock_prev(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    if t["i"] > t["section_start"]:
        t["i"] -= 1
        t["q_start"] = time.time()
        await send_mock_question(q, context, instructions=False)


async def goto_question(q, context, idx):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    if t["section_start"] <= idx < t["section_end"]:
        t["i"] = idx
        t["q_start"] = time.time()
        await send_mock_question(q, context, instructions=False)


async def mark_review(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    if t["i"] in t["review"]:
        t["review"].remove(t["i"])
    else:
        t["review"].add(t["i"])
    await send_mock_question(q, context, instructions=False)


async def clear_answer(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    t["answers"].pop(t["i"], None)
    await send_mock_question(q, context, instructions=False)


async def show_navigation(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    await q.edit_message_text(
        f"☷ Question Navigator\n\n🟢 Answered  🟡 Review  ⚪ Unattempted\n\nSection: {SECTION_SHORT[SECTION_ORDER[t['section']]]}",
        reply_markup=navigation_markup(t)
    )


async def submit_confirm(q, context):
    t = context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    start,end=t["section_start"],t["section_end"]
    attempted=sum(1 for i in range(start,end) if t["answers"].get(i,{}).get("selected") is not None)
    review=sum(1 for i in range(start,end) if i in t["review"])
    unanswered=QUESTIONS_PER_SECTION-attempted
    await q.edit_message_text(
        "🏁 Submit Current Test?\n\n"
        f"Section: {SECTION_SHORT[SECTION_ORDER[t['section']]]}\n"
        f"Attempted: {attempted}\n"
        f"Unattempted: {unanswered}\n"
        f"Marked Review: {review}\n\n"
        "आप अभी पूरा mock submit कर सकते हैं, या वापस जाकर questions check कर सकते हैं।",
        reply_markup=markup([
            [InlineKeyboardButton("🏁 Submit Full Mock", callback_data="submit:full")],
            [InlineKeyboardButton("↩️ Continue Test", callback_data="continue")],
        ])
    )


async def complete_section(q, context, auto=False):
    t=context.user_data.get("test")
    if not t or t.get("mode") != "Mock Test": return
    elapsed=min(SECTION_SECONDS,int(time.time()-t.get("section_started",time.time())))
    t["section_seconds"][t["section"]]=elapsed
    t["completed_sections"].append(t["section"])
    if t["section"] >= 3:
        return await finish_test(q, context, timed_out=auto)
    t["section"] += 1
    t["section_start"] = t["section"]*QUESTIONS_PER_SECTION
    t["section_end"] = t["section_start"]+QUESTIONS_PER_SECTION
    t["i"] = t["section_start"]
    t["section_started"] = time.time()
    t["q_start"] = time.time()
    schedule_section_timeout(context, q.from_user.id)
    note = "⏰ पिछला section का समय समाप्त हो गया।" if auto else "✅ Section complete!"
    await q.edit_message_text(
        f"{note}\n\n➡️ अब {SECTION_SHORT[SECTION_ORDER[t['section']]]} शुरू है।\n\n⏱️ 15:00",
        reply_markup=markup([[InlineKeyboardButton("🚀 Start Section", callback_data="section:start")]])
    )


async def section_timeout(context: ContextTypes.DEFAULT_TYPE):
    data=context.job.data if context.job else {}
    user_id=data.get("user_id")
    # Job callbacks do not have the original CallbackQuery message, so edit the saved chat/message if available.
    # The current session is held in application user_data via user_data access from user id.
    ud = context.application.user_data.get(user_id)
    if not ud or ud.get("test",{}).get("mode") != "Mock Test": return
    t=ud["test"]
    # Count the section and move state; user sees the transition on their next interaction.
    t["section_seconds"][t["section"]]=SECTION_SECONDS
    t["completed_sections"].append(t["section"])
    if t["section"] >= 3:
        # Cannot safely create a message without chat_id stored; use bot send_message.
        await context.bot.send_message(chat_id=user_id, text="⏰ समय समाप्त! Mock का final section भी complete हो गया है। अब result तैयार हो रहा है।")
        return await finish_without_query(context, user_id, timed_out=True)
    t["section"] += 1
    t["section_start"] = t["section"]*QUESTIONS_PER_SECTION
    t["section_end"] = t["section_start"]+QUESTIONS_PER_SECTION
    t["i"] = t["section_start"]
    t["section_started"] = time.time()
    t["q_start"] = time.time()
    schedule_section_timeout(context, user_id)
    await context.bot.send_message(chat_id=user_id, text=f"⏰ Time up!\n\n➡️ अब {SECTION_SHORT[SECTION_ORDER[t['section']]]} शुरू है।", reply_markup=markup([[InlineKeyboardButton("🚀 Open Section", callback_data="section:start")]]))


async def finish_without_query(context, user_id, timed_out=False):
    # Shared finalizer using bot.send_message.
    t=context.application.user_data.get(user_id,{}).get("test")
    if not t: return
    result=save_attempt(user_id,t)
    cancel_jobs(context,user_id)
    text=build_result_text(result,timed_out)
    await context.bot.send_message(chat_id=user_id,text=text,reply_markup=result_markup(t))
    context.application.user_data[user_id].pop("test",None)


def save_attempt(user_id,t):
    total=len(t["qs"])
    correct=wrong=skipped=0
    per=[]
    for i,item in enumerate(t["qs"]):
        a=t["answers"].get(i,{})
        selected=a.get("selected")
        sec=max(0,int(a.get("seconds",0)))
        if selected is None:
            skipped+=1
        else:
            if selected==item["answer"]: correct+=1
            else: wrong+=1
        per.append((i,item,selected,sec,selected is not None and selected==item["answer"],i in t["review"]))
    negative=wrong*NEGATIVE_PER_WRONG if t.get("negative") else 0
    score=correct-negative
    answered=correct+wrong
    accuracy=round(correct/answered*100,1) if answered else 0
    seconds=min(int(time.time()-t["start"]),TOTAL_SECONDS) if t.get("mode")=="Mock Test" else int(time.time()-t["start"])
    con=connect()
    cur=con.execute("""INSERT INTO attempts(user_id,exam,mode,score,total,correct,wrong,skipped,seconds,negative_marks,accuracy,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",(user_id,EXAM,t["mode"],score,total,correct,wrong,skipped,seconds,negative,accuracy,datetime.now(timezone.utc).isoformat()))
    attempt_id=cur.lastrowid
    for i,item,selected,sec,is_correct,is_review in per:
        con.execute("INSERT INTO answers(attempt_id,question_id,selected,correct,seconds,marked_review) VALUES (?,?,?,?,?,?)",(attempt_id,item["id"],selected,1 if is_correct else 0,sec,1 if is_review else 0))
        if selected is not None and not is_correct:
            con.execute("INSERT OR REPLACE INTO user_wrong_questions(user_id,question_id,created_at) VALUES (?,?,?)",(user_id,item["id"],datetime.now(timezone.utc).isoformat()))
    con.commit()
    con.close()
    section_stats=[]
    for sidx,subject in enumerate(SECTION_ORDER):
        start=sidx*25; end=start+25
        c=w=sk=0
        for i in range(start,end):
            a=t["answers"].get(i,{})
            sel=a.get("selected")
            if sel is None: sk+=1
            elif sel==t["qs"][i]["answer"]: c+=1
            else: w+=1
        neg=w*NEGATIVE_PER_WRONG
        section_stats.append((subject,c,w,sk,c-neg))
    avg_time=round(sum(x[3] for x in per if x[2] is not None)/answered,1) if answered else 0
    return {"attempt_id":attempt_id,"total":total,"correct":correct,"wrong":wrong,"skipped":skipped,"negative":negative,"score":score,"accuracy":accuracy,"seconds":seconds,"avg_time":avg_time,"sections":section_stats}


def build_result_text(r,t,timed_out=False):
    mins,secs=divmod(r["seconds"],60)
    text=(
        "🏆 TEST COMPLETED\n\n"
        f"📘 {EXAM} • {t['mode']}\n"
        f"{'⏰ Time limit reached.\n\n' if timed_out else ''}"
        "━━━━━━━━━━━━━━\n"
        f"🎯 Score: {format_score(r['score'])}/{r['total']}\n"
        f"📈 Accuracy: {r['accuracy']}%\n"
        f"⏱️ Your Time: {mins:02d}:{secs:02d}\n"
        f"⚡ Avg Time / Question: {r['avg_time']} sec\n\n"
        f"✅ Correct: {r['correct']}\n❌ Wrong: {r['wrong']}\n⏭️ Skipped: {r['skipped']}\n"
        f"➖ Negative Marks: -{r['negative']:.1f}\n"
        "━━━━━━━━━━━━━━\n\n"
        "📚 SECTION ANALYSIS\n"
    )
    for s,c,w,sk,score in r["sections"]:
        text += f"• {SECTION_SHORT[s]}: {c}/25 correct | {w} wrong | {sk} skipped | Score {format_score(score)}\n"
    text += f"\n🌟 आज की बात\n\n“{pick_motivation(r['accuracy'])}”\n\n🔥 Keep Practicing!"
    return text


def result_markup(t):
    return markup([
        [InlineKeyboardButton("📊 Question-wise Analysis", callback_data="analysis")],
        [InlineKeyboardButton("📊 Performance", callback_data="performance"), InlineKeyboardButton("🏠 Home", callback_data="home")],
    ])


async def finish_test(q, context, timed_out=False):
    t=context.user_data.get("test")
    if not t: return
    result=save_attempt(q.from_user.id,t)
    cancel_jobs(context,q.from_user.id)
    await q.edit_message_text(build_result_text(result,t,timed_out),reply_markup=result_markup(t))
    context.user_data.pop("test",None)
    context.user_data["last_attempt_id"]=result["attempt_id"]


async def analysis(q, context):
    attempt_id=context.user_data.get("last_attempt_id")
    if not attempt_id:
        await q.edit_message_text("इस session में कोई result analysis उपलब्ध नहीं है।",reply_markup=back_home()); return
    con=connect()
    rows=con.execute("""SELECT a.question_id,a.selected,a.correct,a.seconds,q.question,q.answer,q.options,q.explanation,q.subject,q.topic
        FROM answers a JOIN questions q ON q.id=a.question_id WHERE a.attempt_id=? ORDER BY a.id""",(attempt_id,)).fetchall()
    con.close()
    if not rows:
        await q.edit_message_text("Analysis उपलब्ध नहीं है।",reply_markup=back_home()); return
    # Telegram message length is limited; show compact question-wise analysis in chunks.
    text="📊 QUESTION-WISE ANALYSIS\n\n"
    for n,r in enumerate(rows,1):
        status="⏭️ Skipped" if r["selected"] is None else ("✅ Correct" if r["correct"] else "❌ Wrong")
        selected="—" if r["selected"] is None else chr(65+r["selected"])
        text += f"{n}. {status} | Your: {selected} | Correct: {chr(65+r['answer'])} | {r['seconds']}s\n"
    if len(text)>3900:
        text=text[:3850]+"\n… बाकी analysis आगे build में pagination के साथ जोड़ी जाएगी।"
    await q.edit_message_text(text,reply_markup=back_home())


async def generic_module(q,data):
    labels={
        "menu:pyq":"📜 PYQ\n\nVerified PYQs year/shift/source metadata के साथ अलग database में रखे जाएंगे।\n\n⚠️ Unverified questions को PYQ नहीं कहा जाएगा।",
        "menu:ca":"📰 CURRENT AFFAIRS\n\nDaily, Monthly और Topic-wise Current Affairs module अगला content phase है।",
        "wrong":"❌ WRONG QUESTIONS\n\nआपके गलत किए हुए questions automatically save किए जाते हैं। Full reattempt screen अगले module में जोड़ा जाएगा।",
        "saved":"🔖 SAVED QUESTIONS\n\nआप saved questions को बाद में revise कर सकेंगे।",
        "leaderboard":"🏆 LEADERBOARD\n\nRank/Percentile केवल पर्याप्त real-user data आने पर दिखाया जाएगा। कोई fake rank नहीं।",
    }
    await q.edit_message_text(labels.get(data,"Module under development."),reply_markup=back_home())


async def admin_guide(q):
    if ADMIN_ID and q.from_user.id != ADMIN_ID:
        await q.answer("Admin only",show_alert=True); return
    await q.edit_message_text(
        "📥 QUESTION BANK IMPORT\n\n"
        "Admin JSON import format:\n\n"
        '[{"exam":"SSC CGL","subject":"General Awareness","topic":"Polity","question":"...","options":["A","B","C","D"],"answer":2,"explanation":"...","kind":"PYQ","year":2025,"shift":"Shift 1","source":"Official/verified source","verified":1}]\n\n'
        "PYQ के लिए year + shift + source + verified=1 जरूरी रखा जाएगा।",
        reply_markup=back_home()
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    await q.answer()
    data=q.data
    ensure_user(q.from_user)

    if data=="home": return await home_callback(q)
    if data=="menu:quiz": return await show_quiz_menu(q)
    if data=="menu:mock": return await show_mock_menu(q)
    if data=="menu:practice": return await show_practice_menu(q)
    if data=="menu:pyq" or data=="menu:ca" or data in ("wrong","saved","leaderboard"): return await generic_module(q,data)
    if data=="help": return await show_help(q)
    if data=="profile": return await show_profile(q)
    if data=="performance": return await performance(q)
    if data=="admin:guide": return await admin_guide(q)
    if data.startswith("quizsetup:"): return await q.edit_message_text(f"⚡ QUICK QUIZ\n\n❓ {data.split(':')[1]} Questions\n🎲 Mixed Subjects\n\nStart करें?",reply_markup=markup([[InlineKeyboardButton("🚀 START",callback_data=f"quizstart:{data.split(':')[1]}")],[InlineKeyboardButton("🏠 Home",callback_data="home")]]))
    if data.startswith("quizstart:"): return await begin_quiz(q,context,int(data.split(':')[1]))
    if data.startswith("practice:"): return await begin_quiz(q,context,10,data.split(':',1)[1])
    if data=="qans:" or data.startswith("qans:"): return await answer_quiz(q,context,int(data.split(':')[1]))
    if data=="qskip": return await quiz_skip(q,context)
    if data=="qnext":
        t=context.user_data.get("test")
        if t and t.get("mode")=="Quiz":
            t["i"]+=1; t["q_start"]=time.time(); return await send_quiz_question(q,context)
    if data=="save_toggle": return await save_toggle(q,context)
    if data=="mock:instructions": return await show_instructions(q)
    if data=="mock:start": return await start_mock(q,context)
    if data=="section:start": return await send_mock_question(q,context,instructions=False)
    if data=="qskip": return await quiz_skip(q,context)
    if data.startswith("qans:"): return await answer_quiz(q,context,int(data.split(':')[1]))
    if data.startswith("goto:"): return await goto_question(q,context,int(data.split(':')[1]))
    if data=="next": return await mock_next(q,context)
    if data=="prev": return await mock_prev(q,context)
    if data=="review": return await mark_review(q,context)
    if data=="clear": return await clear_answer(q,context)
    if data=="nav": return await show_navigation(q,context)
    if data=="submit_confirm": return await submit_confirm(q,context)
    if data=="continue": return await send_mock_question(q,context,instructions=False)
    if data=="submit:full": return await finish_test(q,context)
    if data=="analysis": return await analysis(q,context)


async def error_handler(update, context):
    print("BOT ERROR:", repr(context.error))


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("BOT_TOKEN is required")
    init_db()
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_error_handler(error_handler)
    app.run_polling(drop_pending_updates=True)
