# Clutch database

SQLite, stdlib `sqlite3`, no extra installs. The file lives at `backend/user_data/clutch.db`
(git-ignored) and is created on first start. Override with `DATABASE_PATH` in `.env`.
Schema: `backend/schema.sql`. Data access: `backend/db.py`.

## Tables

| Table | What it holds |
|---|---|
| `users` | Students. Username-only sign-in for now (no passwords). |
| `subjects` | A student's courses, e.g. "Calculus I". `catalog_id` (v4) links one to a standard course in `courses.py`; NULL = custom course. |
| `topics` | Units inside a subject, e.g. "Chain rule". Progress is tracked per topic. |
| `conversations` | Study sessions. Optional `topic_id`; `ended_at` set once reviewed. |
| `messages` | Every user/assistant turn in a session. |
| `documents` | Study material as plain text, optionally attached to a topic. |
| `session_reviews` | One per ended session: model-assessed `understanding` (0-1), student `confidence` (1-5), summary, strengths, gaps. |
| `topic_progress` | Running `mastery` (0-1), session/message counts, last gaps, per student per topic. |
| `quizzes` | Mastery quizzes: questions with answers (hidden from the API until submitted), the student's answers, score, passed. |
| `badges` | One per student per topic, earned by passing that topic's quiz. |
| `events` | Calendar dates: `kind` exam/quiz/homework/other, title, local `date` (YYYY-MM-DD) and optional `time`, optional subject, notes, `done`. |
| `event_topics` | The topics an exam or quiz covers. |

Deleting a user/subject/topic cascades. Deleting a topic keeps its chats and docs but unlinks them.

## How progress works

1. Student ends a session (`POST /api/conversations/<id>/end`, optional `{"confidence": 1-5}`).
2. The model reads the transcript and returns JSON: understanding, summary, strengths, gaps.
3. Session score = 70% model understanding + 30% confidence (either alone if only one exists).
4. Mastery: first session sets it; after that `mastery = 0.6 * old + 0.4 * score` (`MASTERY_WEIGHT` in db.py).
5. Later sessions on that topic tell the tutor the student's mastery and last gaps.

Topic documents are added to the tutor's system prompt, capped at `DOC_CHAR_BUDGET`
characters (default 6000) because of Ollama's small default context window (see devlog.txt).

## Quizzes and badges

- A topic's quiz unlocks when mastery reaches `QUIZ_UNLOCK_MASTERY` (default 0.8, same point the egg hatches).
- The model writes `QUIZ_QUESTIONS` (default 5) multiple-choice questions from the topic and its documents.
  Bad JSON gets one retry. Options are shuffled so the right answer isn't always A.
- Answers stay on the server until the quiz is submitted. Passing needs `QUIZ_PASS_FRACTION` (default 0.8, so 4/5).
- Math questions are checked with SymPy (`backend/mathcheck.py`). The model describes each one as a
  task (`diff`, `integrate`, `definite`, `limit`, `evaluate`, `simplify`, `solve`) with options in SymPy
  syntax. SymPy computes the true answer, fixes a wrong answer key, inserts the real answer if no option
  is right, and drops questions it can't parse or that have two equivalent options. The question and
  options shown to the student are rendered from the same checked expressions. Concept questions can't
  be machine-checked; checked ones are preferred and show a "math-checked" tag in the quiz.
  Expressions are whitelisted before parsing, and each check runs in a worker process with a time
  limit (`MATHCHECK_TIMEOUT`, default 8 seconds).
- Passing awards the badge; failing allows a fresh quiz. Asking for a quiz while one is still open returns that one.
- All three settings can be overridden in `.env`.

## Planner (spaced repetition)

`backend/planner.py`, pure functions behind `GET /api/users/<uid>/planner`:

- After n reviews a topic comes back after `BASE_INTERVALS[n]` days (1, 2, 4, 7, 12, 20, 30),
  scaled by `0.5 + mastery`, so weak topics return sooner and strong ones later.
- If an upcoming exam or quiz covers the topic: no gap longer than a third of the time left,
  always a review the day before, and in the last 3 days every topic under 85% mastery is daily.
- Today's list is ranked by exam closeness, weakness and how overdue each topic is; each item
  carries plain-language reasons. Exam readiness = average mastery of the topics it covers.
- Metrics: streak (days with a student message, counting back from today or yesterday), the
  last 28 days of activity, this week's sessions and quizzes, average mastery.
- The browser sends `today` and `tz` (`Date.getTimezoneOffset()`), so days follow the
  student's clock; SQLite timestamps are UTC.

## Course catalog and verification

`backend/courses.py` lists standard courses (Elementary Math, Algebra I, Calculus I, Spanish I,
Biology, ...) with their usual topics. Students can add any course; when they type one, the app
suggests matching standard courses (`POST /api/courses/suggest`). Gemma reads the catalog and
picks the best fits ("my times table homework" -> Elementary Math), and a keyword match runs
alongside so suggestions still work if the model is slow or answers badly. If what they typed
is a topic inside a course ("Addition"), choosing that course adds it as a topic there.

Each catalog course has a verification level, shown to students as a chip, with lists of
what is and isn't checked (`checks`, `not_checked`):

- **✓ Verified**: the checkers cover the kinds of answers most of the course is made of.
  Elementary Math, Pre-Algebra, Algebra I and II, Calculus I, Geometry, Statistics, Physics.
- **◐ Partly verified**: some kinds of answers are checked. Chemistry, Spanish I, English,
  U.S. History, World History, Geography, Civics & Government, Social Studies.
- **Not verified**: Biology, French, Programming, Economics, Psychology, and custom courses.

Any course's quiz questions can also be checked against the student's own notes.

### How answers are checked

| Checker | File | Covers | How |
|---|---|---|---|
| Math | `mathcheck.py` | derivatives, integrals, limits, equations, simplifying, arithmetic | SymPy computes the answer |
| Numbers | `valuecheck.py` | statistics (mean ... normal probabilities), geometry (area, volume, Pythagoras, angles, distance) | computed; rounded options are fine ("78.54", "68%") |
| Science | `sciencecheck.py` | physics (a fixed list of 16 standard laws, with units), chemistry (molar mass, moles, pH, balancing) | the model only picks the law and values, never the formula; units are converted and checked |
| Language | `langcheck.py` | Spanish present-tense conjugations, English irregular verbs and plurals | tables; words not in the tables are left unchecked, never guessed |
| Fact bank | `factbank.py` | state and world capitals, presidents 1-45, amendments, Congress and the branches, key dates | questions are generated from the facts, so they're right by construction |
| Notes | `groundcheck.py` | any course with notes in Materials | the model must quote the sentence its answer comes from; the quote must be in the notes and support the keyed option |

In every case the app writes the question text from what it checked, fixes a wrong key,
and drops questions it can't verify. Quizzes use checked questions first; each question
shows how it was checked. The quiz prompt only offers the question forms a course uses
(`families` in courses.py), which keeps it short for the small model.

To verify a new course: add a checker (or facts) for its answer types, add tests, run
`eval_quiz.py` on its topics, then set `verification`, `checks`, `not_checked` and
`families` in courses.py.

Existing courses whose name exactly matches a standard course are linked on startup; others can
be linked with "find a matching course" (`PATCH /api/subjects/<id>`), keeping their own name.

## API

- `POST /api/users` `{username}` - sign in / create
- `GET|POST /api/users/<uid>/subjects`, `DELETE /api/subjects/<id>`
- `POST /api/subjects/<id>/topics`, `DELETE /api/topics/<id>`
- `GET|POST /api/users/<uid>/conversations`, `GET|DELETE /api/conversations/<id>`
- `POST /api/conversations/<id>/messages` `{content, homework?}` - saves both turns; scanned homework text is added to the prompt like in `/api/chat`
- `POST /api/conversations/<id>/end` `{confidence?}` - review + progress update
- `GET|POST /api/users/<uid>/documents`, `GET|DELETE /api/documents/<id>`
- `GET /api/courses`, `POST /api/courses/suggest` `{query}` - catalog, and matches for what a student typed
- `POST /api/users/<uid>/subjects` `{name}` (custom) or `{catalog_id, topic?}` (standard course, optional topic inside; reuses the course if the student already has it)
- `PATCH /api/subjects/<id>` `{catalog_id or null}` - link a custom course to a standard one
- `GET /api/users/<uid>/progress` - includes `quiz_unlocked` and `badge_earned_at` per topic
- `POST /api/topics/<id>/quiz` - get the open quiz or write a new one (403 until unlocked)
- `GET /api/quizzes/<id>`, `POST /api/quizzes/<id>/submit` `{answers: [0-3, ...]}` - grade + award badge
- `GET /api/users/<uid>/badges`
- `POST /api/chat` `{messages, homework?}` - stateless (nothing saved), used by eval_tutor.py and chat_cli.py
- `POST /api/homework/read` `{images, kind?}` (`homework` or `notes`), `POST /api/homework/study-guide` `{homework}` - scanning (not stored)
- `GET /api/users/<uid>/documents?q=` - search titles and text; matches in the text come with a `snippet`
- `POST /api/lecture/transcribe` `{audio}` (base64 WAV, under 30 s), `POST /api/lecture/notes` `{transcript}` - lecture recording
- `GET|POST /api/users/<uid>/events` (`?from=&to=`), `PATCH|DELETE /api/events/<id>` - calendar; `topic_ids` for exams and quizzes
- `GET /api/users/<uid>/planner?today=YYYY-MM-DD&tz=<minutes>` - `due`, `upcoming`, `tests` (readiness), `metrics`

## Changing the schema later

Add the change to `schema.sql` for fresh databases, bump `SCHEMA_VERSION` in `db.py`, and add an
`if version < N:` migration block in `init_db` so existing databases get upgraded too.
New tables (like v2's quizzes and badges) need no migration block: `schema.sql` creates them on startup.

## Tests

`cd backend && python -m pytest tests` (uses a fake model, no Ollama needed). Needs `pip install -r requirements.txt` for SymPy.

## Frontend files

`App.jsx` (sign-in, sidebar, tabs), `Chat.jsx` (saved study sessions + end-of-session review),
`Homework.jsx` (scan homework), `Materials.jsx`, `Progress.jsx`, `Meter.jsx`, `Markdown.jsx`, `api.js`.
Homework text is still kept in the browser only; saving it to the database is a possible next step.
