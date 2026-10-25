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
# 2: quizzes + badges, 3: events (new tables), 4: subjects.catalog_id on one branch and
# users.password_hash + is_demo on another, 5: users.recovery_hash, 6: both branches merged
SCHEMA_VERSION = 7  # v7: course_badges (a new table, so no migration block)

# How much a new session review moves topic mastery (0-1). Higher = reacts faster.
MASTERY_WEIGHT = 0.4

# A course trophy needs every topic's badge, and at least this many topics (so a course
# with one easy topic doesn't count as mastered).
COURSE_TROPHY_MIN_TOPICS = 3


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
    # Migrations for changes schema.sql can't apply on its own (e.g. new columns).
    # Each checks first, because a brand-new database already has the column. Two branches
    # both shipped a "version 4" with different columns, so every database below 6 re-checks
    # all of them: a database from either branch (or neither) ends up with every column.
    if version < 6:
        for table, column, definition in [
            ("subjects", "catalog_id", "TEXT"),
            ("users", "password_hash", "TEXT"),
            ("users", "is_demo", "INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1))"),
            ("users", "recovery_hash", "TEXT"),
        ]:
            if column not in _columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    if version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _row(row):
    return dict(row) if row is not None else None


def _rows(rows):
    return [dict(r) for r in rows]


# ---------- users ----------

PUBLIC_USER_FIELDS = ("id, username, display_name, is_demo, created_at, "
                      "password_hash IS NOT NULL AS has_password, recovery_hash IS NOT NULL AS has_recovery")


def _public_user(row):
    """A user without the password hash, safe to send to the browser."""
    if row is None:
        return None
    user = dict(row)
    user["is_demo"] = bool(user["is_demo"])
    user["has_password"] = bool(user["has_password"])
    user["has_recovery"] = bool(user["has_recovery"])
    return user


def create_user(conn, username, password_hash, display_name=None, is_demo=False, recovery_hash=None):
    username = username.strip()
    cur = conn.execute(
        """INSERT INTO users (username, display_name, password_hash, recovery_hash, is_demo)
           VALUES (?, ?, ?, ?, ?)""",
        (username, (display_name or "").strip() or username, password_hash, recovery_hash,
         1 if is_demo else 0),
    )
    conn.commit()
    return get_user(conn, cur.lastrowid)


def get_or_create_user(conn, username, display_name=None):
    """For scripts and tests: the profile with this name, made without a password if missing.
    The app itself signs people up through create_user, with a password."""
    row = find_user_login(conn, username)
    return get_user(conn, row["id"]) if row else create_user(conn, username, None, display_name)


def get_user(conn, user_id):
    return _public_user(conn.execute(
        f"SELECT {PUBLIC_USER_FIELDS} FROM users WHERE id = ?", (user_id,)
    ).fetchone())


def find_user_login(conn, username):
    """The full row, password hash included, for checking a sign-in. Never send it out."""
    return _row(conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone())


def set_password(conn, user_id, password_hash, recovery_hash=None):
    """Set a new password, and with it a new recovery code (the old code stops working)."""
    conn.execute("UPDATE users SET password_hash = ?, recovery_hash = ? WHERE id = ?",
                 (password_hash, recovery_hash, user_id))
    conn.commit()


def list_profiles(conn):
    """Every profile on this computer, demo first, for the sign-in screen."""
    return [_public_user(r) for r in conn.execute(
        f"SELECT {PUBLIC_USER_FIELDS} FROM users ORDER BY is_demo DESC, display_name COLLATE NOCASE"
    )]


# Which user owns a row, for checking that the signed-in student only touches their own data.
OWNER_QUERIES = {
    "user_id": "SELECT id FROM users WHERE id = ?",
    "subject_id": "SELECT user_id FROM subjects WHERE id = ?",
    "topic_id": "SELECT s.user_id FROM topics t JOIN subjects s ON s.id = t.subject_id WHERE t.id = ?",
    "conversation_id": "SELECT user_id FROM conversations WHERE id = ?",
    "document_id": "SELECT user_id FROM documents WHERE id = ?",
    "event_id": "SELECT user_id FROM events WHERE id = ?",
    "quiz_id": "SELECT user_id FROM quizzes WHERE id = ?",
}


def owner_of(conn, kind, row_id):
    """The owning user's id, or None if the row doesn't exist."""
    row = conn.execute(OWNER_QUERIES[kind], (row_id,)).fetchone()
    return row[0] if row else None


# ---------- subjects & topics ----------

def create_subject(conn, user_id, name, catalog_id=None):
    cur = conn.execute(
        "INSERT INTO subjects (user_id, name, catalog_id) VALUES (?, ?, ?)",
        (user_id, name.strip(), catalog_id),
    )
    conn.commit()
    return _row(conn.execute("SELECT * FROM subjects WHERE id = ?", (cur.lastrowid,)).fetchone())


def link_catalog_names(conn, names_to_ids):
    """Link custom subjects whose name exactly matches a catalog course ("elementary math")."""
    rows = conn.execute("SELECT id, name FROM subjects WHERE catalog_id IS NULL").fetchall()
    for row in rows:
        course_id = names_to_ids.get(row["name"].strip().lower())
        if course_id:
            conn.execute("UPDATE subjects SET catalog_id = ? WHERE id = ?", (course_id, row["id"]))
    conn.commit()


def set_subject_catalog(conn, subject_id, catalog_id):
    conn.execute("UPDATE subjects SET catalog_id = ? WHERE id = ?", (catalog_id, subject_id))
    conn.commit()
    return get_subject(conn, subject_id)


def find_subject(conn, user_id, name):
    return _row(conn.execute(
        "SELECT * FROM subjects WHERE user_id = ? AND name = ?", (user_id, name.strip())
    ).fetchone())


def find_topic(conn, subject_id, name):
    return _row(conn.execute(
        "SELECT * FROM topics WHERE subject_id = ? AND lower(name) = lower(?)",
        (subject_id, name.strip()),
    ).fetchone())


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
        """SELECT t.*, s.name AS subject_name, s.user_id, s.catalog_id
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
    Reviewing the same session again replaces that session's share of mastery instead of
    blending it in a second time (see _rescore).
    """
    convo = get_conversation(conn, conversation_id)
    topic_id = convo["topic_id"]
    old_review = get_review(conn, conversation_id)
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
            old_score = (session_score(old_review["understanding"], old_review["confidence"])
                         if already_ended and old_review else None)
            if old_score is not None and score is not None:
                mastery = _rescore(conn, convo["user_id"], topic_id, conversation_id,
                                   mastery, old_score, score)
            elif score is not None:
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


def _rescore(conn, user_id, topic_id, conversation_id, mastery, old_score, new_score):
    """Swap one session's score for a new one in a topic's mastery, exactly.

    Mastery is a chain of blends, so each session's score sits in it with a fixed weight:
    100% for the topic's first scored session (it set mastery outright) or MASTERY_WEIGHT
    for later ones, times (1 - MASTERY_WEIGHT) for every scored session that came after.
    Changing the score moves mastery by that weight times the change.
    """
    rows = conn.execute(
        """SELECT r.conversation_id, r.understanding, r.confidence FROM session_reviews r
           JOIN conversations c ON c.id = r.conversation_id
           WHERE c.user_id = ? AND r.topic_id = ? ORDER BY r.id""",
        (user_id, topic_id),
    ).fetchall()
    scored = [r["conversation_id"] for r in rows
              if r["conversation_id"] == conversation_id
              or session_score(r["understanding"], r["confidence"]) is not None]
    position = scored.index(conversation_id)
    weight = 1.0 if position == 0 else MASTERY_WEIGHT
    weight *= (1 - MASTERY_WEIGHT) ** (len(scored) - position - 1)
    return min(1.0, max(0.0, mastery + weight * (new_score - old_score)))


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
        """SELECT s.id AS subject_id, s.name AS subject_name, s.catalog_id,
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


def course_progress(conn, user_id):
    """{subject_id: course progress} for each of the student's courses.

    mastery: the average of its topics' mastery, where topics not studied yet count as 0,
    so studying one topic hard doesn't make the whole course look mastered.
    """
    rows = conn.execute(
        """SELECT s.id AS subject_id, COUNT(t.id) AS topics,
                  COALESCE(SUM(COALESCE(p.mastery, 0)), 0) AS mastery_sum,
                  COUNT(b.topic_id) AS badges,
                  SUM(CASE WHEN p.sessions_count > 0 THEN 1 ELSE 0 END) AS studied,
                  cb.earned_at AS trophy_earned_at
           FROM subjects s
           LEFT JOIN topics t ON t.subject_id = s.id
           LEFT JOIN topic_progress p ON p.topic_id = t.id AND p.user_id = s.user_id
           LEFT JOIN badges b ON b.topic_id = t.id AND b.user_id = s.user_id
           LEFT JOIN course_badges cb ON cb.subject_id = s.id AND cb.user_id = s.user_id
           WHERE s.user_id = ?
           GROUP BY s.id""",
        (user_id,),
    )
    out = {}
    for r in rows:
        topics = r["topics"]
        out[r["subject_id"]] = {
            "topics": topics,
            "studied": r["studied"] or 0,
            "badges": r["badges"],
            "mastery": r["mastery_sum"] / topics if topics else 0.0,
            "min_topics": COURSE_TROPHY_MIN_TOPICS,
            "trophy_earned_at": r["trophy_earned_at"],
        }
    return out


def award_course_trophy(conn, user_id, subject_id):
    """Give the course trophy if every topic has its badge (and there are enough topics).
    Returns True if it was just earned."""
    p = course_progress(conn, user_id).get(subject_id)
    if (not p or p["trophy_earned_at"] or p["topics"] < COURSE_TROPHY_MIN_TOPICS
            or p["badges"] < p["topics"]):
        return False
    cur = conn.execute(
        "INSERT OR IGNORE INTO course_badges (user_id, subject_id, topics, mastery) VALUES (?, ?, ?, ?)",
        (user_id, subject_id, p["topics"], p["mastery"]),
    )
    conn.commit()
    return cur.rowcount == 1


def list_course_trophies(conn, user_id):
    return _rows(conn.execute(
        """SELECT cb.*, s.name AS subject_name, s.catalog_id FROM course_badges cb
           JOIN subjects s ON s.id = cb.subject_id
           WHERE cb.user_id = ? ORDER BY cb.earned_at DESC""",
        (user_id,),
    ))


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
