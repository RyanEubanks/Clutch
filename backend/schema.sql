-- Clutch database schema (SQLite).
-- Every statement is idempotent, so this file runs safely on every startup.
-- When the schema changes later, bump SCHEMA_VERSION in db.py and add a migration there.

PRAGMA foreign_keys = ON;

-- A student. No passwords yet: this is a local, hackathon-stage app.
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY,
    username     TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A course or area of study, e.g. "Calculus I". Owned by one student.
-- catalog_id links the subject to a standard course in backend/courses.py (v4), which says
-- whether the course is verified. NULL means a custom course the student made up.
CREATE TABLE IF NOT EXISTS subjects (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    catalog_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, name)
);

-- A unit inside a subject, e.g. "Chain rule". Progress is tracked per topic.
CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (subject_id, name)
);

-- One study session with the tutor. topic_id is optional (general questions).
-- ended_at is set when the student ends the session and it gets reviewed.
CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id   INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    title      TEXT NOT NULL DEFAULT 'New chat',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);

-- Study material (notes, textbook excerpts) as plain text.
-- Documents attached to a topic are given to the tutor as context in that topic's chats.
CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id   INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_documents_topic ON documents(topic_id);

-- The review written when a session ends: the model's read of how well the
-- student understood, plus the student's own confidence rating.
CREATE TABLE IF NOT EXISTS session_reviews (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL UNIQUE REFERENCES conversations(id) ON DELETE CASCADE,
    topic_id        INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    understanding   REAL CHECK (understanding BETWEEN 0 AND 1),  -- model-assessed
    confidence      INTEGER CHECK (confidence BETWEEN 1 AND 5),  -- student self-rating
    summary         TEXT,
    strengths       TEXT,
    gaps            TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Running per-student, per-topic progress. Updated after each reviewed session.
CREATE TABLE IF NOT EXISTS topic_progress (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id        INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    mastery         REAL NOT NULL DEFAULT 0 CHECK (mastery BETWEEN 0 AND 1),
    sessions_count  INTEGER NOT NULL DEFAULT 0,
    messages_count  INTEGER NOT NULL DEFAULT 0,
    last_gaps       TEXT,
    last_studied_at TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, topic_id)
);

-- ---------- v2: quizzes and badges ----------

-- A mastery quiz for one topic. Unlocks once topic mastery reaches the threshold
-- (QUIZ_UNLOCK_MASTERY in app.py). questions_json holds the questions WITH answers;
-- the API strips the answers until the quiz is submitted.
CREATE TABLE IF NOT EXISTS quizzes (
    id             INTEGER PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id       INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    questions_json TEXT NOT NULL,
    answers_json   TEXT,                 -- the student's chosen option per question
    score          INTEGER,              -- number correct, set on submit
    total          INTEGER NOT NULL,
    passed         INTEGER CHECK (passed IN (0, 1)),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    submitted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_quizzes_user_topic ON quizzes(user_id, topic_id);

-- One badge per student per topic, earned by passing that topic's quiz.
CREATE TABLE IF NOT EXISTS badges (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id  INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    quiz_id   INTEGER REFERENCES quizzes(id) ON DELETE SET NULL,
    earned_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, topic_id)
);

-- ---------- v3: planner (calendar + spaced repetition) ----------

-- A date on the student's calendar. date/time are the student's local date and time
-- (YYYY-MM-DD, HH:MM), since an exam "on Friday" means Friday where the student is.
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('exam', 'quiz', 'homework', 'other')),
    title      TEXT NOT NULL,
    date       TEXT NOT NULL,
    time       TEXT,
    notes      TEXT,
    done       INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)),  -- e.g. homework handed in
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_user_date ON events(user_id, date);

-- The topics an exam or quiz covers. Reviews of these topics are packed in before it.
CREATE TABLE IF NOT EXISTS event_topics (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, topic_id)
);
