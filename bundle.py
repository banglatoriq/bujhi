"""
নামানো ডেটা থেকে অ্যাপ-রেডি SQLite ডেটাবেস বানায়।
Flutter অ্যাপে assets হিসেবে সরাসরি bundle করা যাবে।
"""

import json
import os
import re
import sqlite3
from collections import Counter

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS subjects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_slug       TEXT NOT NULL,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    question_count  INTEGER DEFAULT 0,
    UNIQUE(exam_slug, slug)
);

CREATE TABLE IF NOT EXISTS topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id      INTEGER NOT NULL REFERENCES subjects(id),
    name            TEXT NOT NULL,
    question_count  INTEGER DEFAULT 0,
    priority_rank   INTEGER,               -- ১ = সবচেয়ে বেশি প্রশ্ন আসে
    coverage_pct    REAL,                  -- এই টপিক সাবজেক্টের কত % দখল করে
    UNIQUE(subject_id, name)
);

-- পাঠ: এই টেবিলটাই তোমার আসল কাজ। রো তৈরি হয়ে যাবে, ঘর ফাঁকা থাকবে।
CREATE TABLE IF NOT EXISTS lessons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id        INTEGER NOT NULL REFERENCES topics(id),
    title           TEXT NOT NULL,
    hook            TEXT DEFAULT '',       -- কেন এটা পড়ব
    concept         TEXT DEFAULT '',       -- মূল ব্যাখ্যা, সহজ ভাষায়
    why             TEXT DEFAULT '',       -- নিয়মটা কেন এমন
    examples        TEXT DEFAULT '',       -- উদাহরণ
    mnemonic        TEXT DEFAULT '',       -- মনে রাখার কৌশল
    common_mistakes TEXT DEFAULT '',       -- যেখানে সবাই ভুল করে
    source_ref      TEXT DEFAULT '',       -- কোন বইয়ের কোন পরিচ্ছেদ
    status          TEXT DEFAULT 'draft',  -- draft | done
    order_index     INTEGER DEFAULT 0,
    UNIQUE(topic_id)
);

CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id      INTEGER REFERENCES subjects(id),
    topic_id        INTEGER REFERENCES topics(id),
    lesson_id       INTEGER REFERENCES lessons(id),
    question        TEXT NOT NULL,
    opt_a           TEXT, opt_b TEXT, opt_c TEXT, opt_d TEXT,
    answer          TEXT,                  -- পরে ভরবে
    explanation     TEXT,                  -- পরে ভরবে
    year            TEXT,
    exam_tag        TEXT,
    source_url      TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_q_lesson  ON questions(lesson_id);
CREATE INDEX IF NOT EXISTS idx_q_topic   ON questions(topic_id);
CREATE INDEX IF NOT EXISTS idx_q_subject ON questions(subject_id);
"""


def _clean(name):
    if not name:
        return "অশ্রেণীবদ্ধ"
    # "সমান্তর ধারা (Arithmetic Progression)" → বাংলা অংশ রাখো
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    return name or "অশ্রেণীবদ্ধ"


def build(db_path, exam_slug, subject_name, subject_slug, questions):
    """একটা সাবজেক্টের প্রশ্ন DB-তে ঢোকায়। বারবার চালানো নিরাপদ।"""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    cur = con.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO subjects(exam_slug, name, slug) VALUES (?,?,?)",
        (exam_slug, subject_name, subject_slug or "all"))
    cur.execute("SELECT id FROM subjects WHERE exam_slug=? AND slug=?",
                (exam_slug, subject_slug or "all"))
    subject_id = cur.fetchone()[0]

    # টপিক গণনা ও অগ্রাধিকার
    counts = Counter(_clean(q.get("topic")) for q in questions)
    total = sum(counts.values()) or 1
    topic_ids = {}

    for rank, (tname, n) in enumerate(counts.most_common(), 1):
        cur.execute("""INSERT INTO topics(subject_id, name, question_count,
                                          priority_rank, coverage_pct)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(subject_id, name) DO UPDATE SET
                         question_count=excluded.question_count,
                         priority_rank=excluded.priority_rank,
                         coverage_pct=excluded.coverage_pct""",
                    (subject_id, tname, n, rank, round(n / total * 100, 2)))
        cur.execute("SELECT id FROM topics WHERE subject_id=? AND name=?",
                    (subject_id, tname))
        tid = cur.fetchone()[0]
        topic_ids[tname] = tid

        # প্রতিটি টপিকের জন্য একটা খালি পাঠ
        cur.execute("""INSERT OR IGNORE INTO lessons(topic_id, title, order_index)
                       VALUES (?,?,?)""", (tid, tname, rank))

    lesson_of = {}
    for tname, tid in topic_ids.items():
        cur.execute("SELECT id FROM lessons WHERE topic_id=?", (tid,))
        row = cur.fetchone()
        if row:
            lesson_of[tname] = row[0]

    for q in questions:
        tname = _clean(q.get("topic"))
        opts = (q.get("options") or []) + [None] * 4
        cur.execute("""INSERT OR IGNORE INTO questions
            (subject_id, topic_id, lesson_id, question,
             opt_a, opt_b, opt_c, opt_d, year, exam_tag, source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (subject_id, topic_ids.get(tname), lesson_of.get(tname),
                     q.get("question"), opts[0], opts[1], opts[2], opts[3],
                     q.get("year"),
                     " > ".join(q.get("tags") or []),
                     q.get("url")))

    cur.execute("""UPDATE subjects SET question_count =
                   (SELECT COUNT(*) FROM questions WHERE subject_id=?)
                   WHERE id=?""", (subject_id, subject_id))
    con.commit()
    con.close()
    return subject_id


def stats(db_path):
    if not os.path.exists(db_path):
        return None
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    out = {}
    for label, sql in [
        ("সাবজেক্ট", "SELECT COUNT(*) FROM subjects"),
        ("টপিক", "SELECT COUNT(*) FROM topics"),
        ("প্রশ্ন", "SELECT COUNT(*) FROM questions"),
        ("পাঠ লেখা বাকি", "SELECT COUNT(*) FROM lessons WHERE status='draft'"),
        ("পাঠ শেষ", "SELECT COUNT(*) FROM lessons WHERE status='done'"),
    ]:
        out[label] = cur.fetchone()[0] if cur.execute(sql) else 0
    con.close()
    return out


def export_json(db_path, out_dir):
    """অ্যাপে চাইলে JSON-ও লাগতে পারে।"""
    os.makedirs(out_dir, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    files = []
    for table in ("subjects", "topics", "lessons", "questions"):
        rows = [dict(r) for r in con.execute(f"SELECT * FROM {table}")]
        p = os.path.join(out_dir, f"{table}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        files.append(p)
    con.close()
    return files
