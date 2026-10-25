"""SQLite data layer for Clutch.

Every function takes an open connection as its first argument, so the same code
works from Flask (one connection per request) and from tests or scripts.
"""
import json
import os
import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BACKEND_DIR / "schema.sql"
DEFAULT_DB_PATH = BACKEND_DIR / "user_data" / "clutch.db"
SCHEMA_VERSION = 3  # 2: quizzes + badges, 3: events (both new tables only, created by schema.sql)

# How much a new session review moves topic mastery (0-1). Higher = reacts faster.
MASTERY_WEIGHT = 0.4


def db_path():
    return Path(os.getenv("DATABASE_PATH") or DEFAULT_DB_PATH)


def connect(path=None):
    path = Path(path or db_path())
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    """Create tables if missing and run any pending migrations."""
    conn.executescript(SCHEMA_PATH.read_text())
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    # Migrations for changes schema.sql can't apply on its own (e.g. new columns):
    # if version < 3:
    #     conn.execute("ALTER TABLE topics ADD COLUMN ...")
    if version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _row(row):
    return dict(row) if row is not None else None


def _rows(rows):
    return [dict(r) for r in rows]


# ---------- users ----------

def get_or_create_user(conn, username, display_name=None):
    username = username.strip()
    conn.execute(
        "INSERT OR IGNORE INTO users (username, display_name) VALUES (?, ?)",
        (username, display_name or username),
    )
    conn.commit()
    return _row(conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone())


def get_user(conn, user_id):
    return _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


# ---------- subjects & topics ----------

def create_subject(conn, user_id, name):
    cur = conn.execute("INSERT INTO subjects (user_id, name) VALUES (?, ?)", (user_id, name.strip()))
    conn.commit()
    return _row(conn.execute("SELECT * FROM subjects WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_subject(conn, subject_id):
    return _row(conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone())


def delete_subject(conn, subject_id):
    conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    conn.commit()


def list_subjects_with_topics(conn, user_id):
    subjects = _rows(conn.execute(
        "SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user_id,)
    ))
    topics = _rows(conn.execute(
        """SELECT t.* FROM topics t JOIN subjects s ON s.id = t.subject_id
           WHERE s.user_id = ? ORDER BY t.name""",
        (user_id,),
    ))
    for s in subjects:
        s["topics"] = [t for t in topics if t["subject_id"] == s["id"]]
    return subjects


def create_topic(conn, subject_id, name, description=None):
    cur = conn.execute(
        "INSERT INTO topics (subject_id, name, description) VALUES (?, ?, ?)",
        (subject_id, name.strip(), description),
    )
    conn.commit()
    return get_topic(conn, cur.lastrowid)


def get_topic(conn, topic_id):
    return _row(conn.execute(
        """SELECT t.*, s.name AS subject_name, s.user_id
           FROM topics t JOIN subjects s ON s.id = t.subject_id WHERE t.id = ?""",
        (topic_id,),
    ).fetchone())


def delete_topic(conn, topic_id):
    conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    conn.commit()


# ---------- conversations & messages ----------

def create_conversation(conn, user_id, topic_id=None, title=None):
    cur = conn.execute(
        "INSERT INTO conversations (user_id, topic_id, title) VALUES (?, ?, ?)",
        (user_id, topic_id, title or "New chat"),
    )
    conn.commit()
    return get_conversation(conn, cur.lastrowid)


def get_conversation(conn, conversation_id):
    return _row(conn.execute(
        """SELECT c.*, t.name AS topic_name
           FROM conversations c LEFT JOIN topics t ON t.id = c.topic_id
           WHERE c.id = ?""",
        (conversation_id,),
    ).fetchone())


def list_conversations(conn, user_id):
    return _rows(conn.execute(
        """SELECT c.*, t.name AS topic_name,
                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
           FROM conversations c LEFT JOIN topics t ON t.id = c.topic_id
           WHERE c.user_id = ? ORDER BY c.updated_at DESC, c.id DESC""",
        (user_id,),
    ))


def delete_conversation(conn, conversation_id):
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()


def get_messages(conn, conversation_id):
    return _rows(conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
    ))


def add_message(conn, conversation_id, role, content):
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conversation_id, role, content),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conversation_id,)
    )
    # Name the chat after the student's first question.
    if role == "user":
        conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND title = 'New chat'",
            (content.strip()[:60], conversation_id),
        )
    conn.commit()
    return _row(conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone())


def delete_message(conn, message_id):
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()


# ---------- documents (study material) ----------

def create_document(conn, user_id, title, content, topic_id=None):
    cur = conn.execute(
        """INSERT INTO documents (user_id, topic_id, title, content, char_count)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, topic_id, title.strip(), content, len(content)),
    )
    conn.commit()
    return get_document(conn, cur.lastrowid)


def get_document(conn, document_id):
    return _row(conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())


def list_documents(conn, user_id, query=None):
    """Document metadata only (no content), for listing in the UI.

    With a query, only documents whose title or content contain it (case-insensitive) are
    returned, and content matches get a short "snippet" of text around the first hit.
    """
    sql = """SELECT d.id, d.user_id, d.topic_id, d.title, d.char_count, d.created_at,
                    t.name AS topic_name, s.name AS subject_name, d.content
             FROM documents d
             LEFT JOIN topics t ON t.id = d.topic_id
             LEFT JOIN subjects s ON s.id = t.subject_id
             WHERE d.user_id = ?"""
    params = [user_id]
    query = (query or "").strip()
    if query:
        like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (d.title LIKE ? ESCAPE '\\' OR d.content LIKE ? ESCAPE '\\')"
        params += [like, like]
    docs = _rows(conn.execute(sql + " ORDER BY d.created_at DESC, d.id DESC", params))
    for doc in docs:
        content = doc.pop("content")
        if query:
            doc["snippet"] = _snippet(content, query)
    return docs


def _snippet(content, query, radius=60):
    """A one-line excerpt of content around the first match of query, or None."""
    at = content.lower().find(query.lower())
    if at < 0:
        return None
    start, end = max(0, at - radius), min(len(content), at + len(query) + radius)
    text = " ".join(content[start:end].split())
    return ("…" if start else "") + text + ("…" if end < len(content) else "")


def topic_documents(conn, topic_id):
    return _rows(conn.execute(
        "SELECT * FROM documents WHERE topic_id = ? ORDER BY id", (topic_id,)
    ))


def delete_document(conn, document_id):
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    conn.commit()


# ---------- progress ----------

def get_topic_progress(conn, user_id, topic_id):
    return _row(conn.execute(
        "SELECT * FROM topic_progress WHERE user_id = ? AND topic_id = ?", (user_id, topic_id)
    ).fetchone())


def save_session_review(conn, conversation_id, understanding, confidence, summary, strengths, gaps):
    """Store the review for a finished session and fold it into topic progress.

    Mastery is a moving average of session scores. Each score blends the model's
    assessment (70%) with the student's own confidence (30%) when both are given.
    """
    convo = get_conversation(conn, conversation_id)
    topic_id = convo["topic_id"]
    conn.execute(
        """INSERT INTO session_reviews
               (conversation_id, topic_id, understanding, confidence, summary, strengths, gaps)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (conversation_id) DO UPDATE SET
               understanding = excluded.understanding, confidence = excluded.confidence,
               summary = excluded.summary, strengths = excluded.strengths, gaps = excluded.gaps,
               created_at = datetime('now')""",
        (conversation_id, topic_id, understanding, confidence, summary, strengths, gaps),
    )
    already_ended = convo["ended_at"] is not None
    conn.execute("UPDATE conversations SET ended_at = datetime('now') WHERE id = ?", (conversation_id,))

    if topic_id is not None:
        score = session_score(understanding, confidence)
        n_messages = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND role = 'user'",
            (conversation_id,),
        ).fetchone()[0]
        prev = get_topic_progress(conn, convo["user_id"], topic_id)
        if prev is None:
            conn.execute(
                """INSERT INTO topic_progress
                       (user_id, topic_id, mastery, sessions_count, messages_count,
                        last_gaps, last_studied_at)
                   VALUES (?, ?, ?, 1, ?, ?, datetime('now'))""",
                (convo["user_id"], topic_id, score if score is not None else 0, n_messages, gaps),
            )
        else:
            mastery = prev["mastery"]
            if score is not None:
                # First scored session sets mastery directly; later ones nudge it.
                mastery = score if prev["sessions_count"] == 0 else (
                    (1 - MASTERY_WEIGHT) * mastery + MASTERY_WEIGHT * score
                )
            # Re-reviewing the same session updates scores but doesn't count it twice.
            conn.execute(
                """UPDATE topic_progress SET
                       mastery = ?, sessions_count = sessions_count + ?,
                       messages_count = messages_count + ?, last_gaps = ?,
                       last_studied_at = datetime('now'), updated_at = datetime('now')
                   WHERE user_id = ? AND topic_id = ?""",
                (round(mastery, 4), 0 if already_ended else 1,
                 0 if already_ended else n_messages, gaps, convo["user_id"], topic_id),
            )
    conn.commit()
    return _row(conn.execute(
        "SELECT * FROM session_reviews WHERE conversation_id = ?", (conversation_id,)
    ).fetchone())


def session_score(understanding, confidence):
    parts = []
    if understanding is not None:
        parts.append((0.7, float(understanding)))
    if confidence is not None:
        parts.append((0.3, (int(confidence) - 1) / 4))
    if not parts:
        return None
    total = sum(w for w, _ in parts)
    return round(sum(w * v for w, v in parts) / total, 4)


def get_review(conn, conversation_id):
    return _row(conn.execute(
        "SELECT * FROM session_reviews WHERE conversation_id = ?", (conversation_id,)
    ).fetchone())


def progress_overview(conn, user_id):
    """Every topic the student has, with progress (zeros if never studied)."""
    return _rows(conn.execute(
        """SELECT s.id AS subject_id, s.name AS subject_name,
                  t.id AS topic_id, t.name AS topic_name,
                  COALESCE(p.mastery, 0) AS mastery,
                  b.earned_at AS badge_earned_at,
                  COALESCE(p.sessions_count, 0) AS sessions_count,
                  COALESCE(p.messages_count, 0) AS messages_count,
                  p.last_gaps, p.last_studied_at
           FROM subjects s
           JOIN topics t ON t.subject_id = s.id
           LEFT JOIN topic_progress p ON p.topic_id = t.id AND p.user_id = s.user_id
           LEFT JOIN badges b ON b.topic_id = t.id AND b.user_id = s.user_id
           WHERE s.user_id = ?
           ORDER BY s.name, t.name""",
        (user_id,),
    ))


# ---------- calendar events ----------

EVENT_KINDS = ("exam", "quiz", "homework", "other")
EVENT_FIELDS = ("subject_id", "kind", "title", "date", "time", "notes", "done")


def _with_topics(conn, events):
    """Attach topic_ids to each event (the topics an exam or quiz covers)."""
    for e in events:
        e["topic_ids"] = [r[0] for r in conn.execute(
            "SELECT topic_id FROM event_topics WHERE event_id = ? ORDER BY topic_id", (e["id"],)
        )]
        e["done"] = bool(e["done"])
    return events


def create_event(conn, user_id, kind, title, date, time=None, subject_id=None, notes=None,
                 topic_ids=()):
    cur = conn.execute(
        """INSERT INTO events (user_id, subject_id, kind, title, date, time, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, subject_id, kind, title.strip(), date, time or None, notes or None),
    )
    set_event_topics(conn, cur.lastrowid, topic_ids)
    conn.commit()
    return get_event(conn, cur.lastrowid)


def get_event(conn, event_id):
    row = _row(conn.execute(
        """SELECT e.*, s.name AS subject_name FROM events e
           LEFT JOIN subjects s ON s.id = e.subject_id WHERE e.id = ?""",
        (event_id,),
    ).fetchone())
    return _with_topics(conn, [row])[0] if row else None


def list_events(conn, user_id, start=None, end=None):
    """Events in date order, optionally only those with start <= date <= end."""
    sql = """SELECT e.*, s.name AS subject_name FROM events e
             LEFT JOIN subjects s ON s.id = e.subject_id WHERE e.user_id = ?"""
    params = [user_id]
    if start:
        sql += " AND e.date >= ?"
        params.append(start)
    if end:
        sql += " AND e.date <= ?"
        params.append(end)
    sql += " ORDER BY e.date, COALESCE(e.time, '99:99'), e.id"
    return _with_topics(conn, _rows(conn.execute(sql, params)))


def update_event(conn, event_id, fields, topic_ids=None):
    sets = {k: v for k, v in fields.items() if k in EVENT_FIELDS}
    if "done" in sets:
        sets["done"] = 1 if sets["done"] else 0
    if sets:
        conn.execute(
            f"UPDATE events SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
            (*sets.values(), event_id),
        )
    if topic_ids is not None:
        set_event_topics(conn, event_id, topic_ids)
    conn.commit()
    return get_event(conn, event_id)


def set_event_topics(conn, event_id, topic_ids):
    conn.execute("DELETE FROM event_topics WHERE event_id = ?", (event_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO event_topics (event_id, topic_id) VALUES (?, ?)",
        [(event_id, t) for t in topic_ids],
    )


def delete_event(conn, event_id):
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()


def study_activity(conn, user_id, since):
    """UTC timestamps of the student's own messages since `since` (UTC 'YYYY-MM-DD HH:MM:SS'),
    with the topic of each, for streaks and activity charts."""
    return _rows(conn.execute(
        """SELECT m.created_at, c.topic_id, m.conversation_id FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE c.user_id = ? AND m.role = 'user' AND m.created_at >= ?
           ORDER BY m.created_at""",
        (user_id, since),
    ))


def quizzes_since(conn, user_id, since):
    return _rows(conn.execute(
        """SELECT topic_id, passed, submitted_at FROM quizzes
           WHERE user_id = ? AND submitted_at IS NOT NULL AND submitted_at >= ?""",
        (user_id, since),
    ))


# ---------- quizzes & badges ----------

def create_quiz(conn, user_id, topic_id, questions):
    cur = conn.execute(
        "INSERT INTO quizzes (user_id, topic_id, questions_json, total) VALUES (?, ?, ?, ?)",
        (user_id, topic_id, json.dumps(questions), len(questions)),
    )
    conn.commit()
    return get_quiz(conn, cur.lastrowid)


def get_quiz(conn, quiz_id):
    row = _row(conn.execute(
        """SELECT q.*, t.name AS topic_name FROM quizzes q
           JOIN topics t ON t.id = q.topic_id WHERE q.id = ?""",
        (quiz_id,),
    ).fetchone())
    if row:
        row["questions"] = json.loads(row.pop("questions_json"))
        answers = row.pop("answers_json")
        row["answers"] = json.loads(answers) if answers else None
        row["passed"] = None if row["passed"] is None else bool(row["passed"])
    return row


def submit_quiz(conn, quiz_id, answers, pass_fraction):
    """Grade a quiz and award the topic badge if it passed. Returns (quiz, new_badge)."""
    quiz = get_quiz(conn, quiz_id)
    # A voided question (no correct option was offered) counts as right for everyone.
    score = sum(1 for q, a in zip(quiz["questions"], answers) if q.get("voided") or a == q["answer"])
    passed = score >= pass_fraction * quiz["total"]
    conn.execute(
        """UPDATE quizzes SET answers_json = ?, score = ?, passed = ?, submitted_at = datetime('now')
           WHERE id = ?""",
        (json.dumps(answers), score, int(passed), quiz_id),
    )
    new_badge = False
    if passed:
        cur = conn.execute(
            "INSERT OR IGNORE INTO badges (user_id, topic_id, quiz_id) VALUES (?, ?, ?)",
            (quiz["user_id"], quiz["topic_id"], quiz_id),
        )
        new_badge = cur.rowcount == 1
    conn.commit()
    return get_quiz(conn, quiz_id), new_badge


def open_quiz(conn, user_id, topic_id):
    """The student's latest unsubmitted quiz for this topic, if any."""
    row = conn.execute(
        """SELECT id FROM quizzes WHERE user_id = ? AND topic_id = ? AND submitted_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (user_id, topic_id),
    ).fetchone()
    return get_quiz(conn, row["id"]) if row else None


def get_badge(conn, user_id, topic_id):
    return _row(conn.execute(
        "SELECT * FROM badges WHERE user_id = ? AND topic_id = ?", (user_id, topic_id)
    ).fetchone())


def list_badges(conn, user_id):
    return _rows(conn.execute(
        """SELECT b.*, t.name AS topic_name, s.name AS subject_name, q.score, q.total
           FROM badges b
           JOIN topics t ON t.id = b.topic_id
           JOIN subjects s ON s.id = t.subject_id
           LEFT JOIN quizzes q ON q.id = b.quiz_id
           WHERE b.user_id = ? ORDER BY b.earned_at DESC""",
        (user_id,),
    ))
