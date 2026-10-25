# Clutch database

SQLite, stdlib `sqlite3`, no extra installs. The file lives at `backend/user_data/clutch.db`
(git-ignored) and is created on first start. Override with `DATABASE_PATH` in `.env`.
Schema: `backend/schema.sql`. Data access: `backend/db.py`.

## Tables

| Table | What it holds |
|---|---|
| `users` | Students. Username-only sign-in for now (no passwords). |
| `subjects` | A student's courses, e.g. "Calculus I". |
| `topics` | Units inside a subject, e.g. "Chain rule". Progress is tracked per topic. |
| `conversations` | Study sessions. Optional `topic_id`; `ended_at` set once reviewed. |
| `messages` | Every user/assistant turn in a session. |
| `documents` | Study material as plain text, optionally attached to a topic. |
| `session_reviews` | One per ended session: model-assessed `understanding` (0-1), student `confidence` (1-5), summary, strengths, gaps. |
| `topic_progress` | Running `mastery` (0-1), session/message counts, last gaps, per student per topic. |

Deleting a user/subject/topic cascades. Deleting a topic keeps its chats and docs but unlinks them.

## How progress works

1. Student ends a session (`POST /api/conversations/<id>/end`, optional `{"confidence": 1-5}`).
2. The model reads the transcript and returns JSON: understanding, summary, strengths, gaps.
3. Session score = 70% model understanding + 30% confidence (either alone if only one exists).
4. Mastery: first session sets it; after that `mastery = 0.6 * old + 0.4 * score` (`MASTERY_WEIGHT` in db.py).
5. Later sessions on that topic tell the tutor the student's mastery and last gaps.

Topic documents are added to the tutor's system prompt, capped at `DOC_CHAR_BUDGET`
characters (default 6000) because of Ollama's small default context window (see devlog.txt).

## API

- `POST /api/users` `{username}` - sign in / create
- `GET|POST /api/users/<uid>/subjects`, `DELETE /api/subjects/<id>`
- `POST /api/subjects/<id>/topics`, `DELETE /api/topics/<id>`
- `GET|POST /api/users/<uid>/conversations`, `GET|DELETE /api/conversations/<id>`
- `POST /api/conversations/<id>/messages` `{content}` - saves both turns
- `POST /api/conversations/<id>/end` `{confidence?}` - review + progress update
- `GET|POST /api/users/<uid>/documents`, `GET|DELETE /api/documents/<id>`
- `GET /api/users/<uid>/progress`
- `POST /api/chat` - old stateless endpoint, still used by eval_tutor.py and chat_cli.py

## Changing the schema later

Add the change to `schema.sql` for fresh databases, bump `SCHEMA_VERSION` in `db.py`, and add an
`if version < N:` migration block in `init_db` so existing databases get upgraded too.

## Tests

`cd backend && python -m pytest tests` (uses a fake model, no Ollama needed).
