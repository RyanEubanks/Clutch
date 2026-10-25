# Clutch database

SQLite, stdlib `sqlite3`, no extra installs. The file lives at `backend/user_data/clutch.db`
(git-ignored) and is created on first start. Override with `DATABASE_PATH` in `.env`.
Schema: `backend/schema.sql`. Data access: `backend/db.py`.

## Tables

| Table | What it holds |
|---|---|
| `users` | Profiles on this computer: `password_hash` (Werkzeug scrypt; NULL until a pre-password profile sets one), `recovery_hash` (one-time code for a forgotten password, hashed the same way) and `is_demo`. |
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

## Profiles, sign-in and the demo

- The sign-in screen lists every profile on the computer (`GET /api/profiles`: names only).
  Each profile has a password, so others using the same computer can't open its notes.
- Signing in sets a signed, HttpOnly session cookie that ends when the browser closes. The key is
  `SECRET_KEY` in `.env`, or `backend/user_data/secret_key`, made on first start (git-ignored).
- Every data endpoint needs a sign-in (401 otherwise), and a check in `require_sign_in` (app.py)
  looks up the owner of each id in the URL (`db.OWNER_QUERIES`). Someone else's row answers 404,
  the same as a missing one. Endpoints that store nothing stay open: `/api/chat`, scanning,
  lecture transcription and notes, so `eval_tutor.py` and `chat_cli.py` still work.
- Profiles made before passwords existed choose one the first time they sign in.
- Forgot password: whenever a password is set (new profile, first password, reset), the student is
  shown a one-time recovery code (`XXXX-XXXX-XXXX`, no look-alike characters) to write down. It
  resets the password once and is replaced by a new code. Lost that too: someone with access to
  the computer runs `flask --app app reset-password <name>` in `backend/` (it prompts for the
  new password and prints a new code). That needs the same access that can read the database
  file, so it opens no new way in.
- **Alex** (`username = alex`, `is_demo = 1`, no password) is the demo. `backend/demo.py`
  rebuilds Alex's data on every sign-in, dated from today: a 4-day streak ending yesterday,
  reviews due, a midterm in 6 days, 6 past sessions, 4 materials and a badge. It never
  touches another profile. Tests run with `create_app(..., demo_account=False)`.

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
Importing a course's OpenStax textbook (below) adds its review questions and glossary, so a
not-verified course (Biology, Economics, Psychology, Programming) becomes partly verified.

### How answers are checked

| Checker | File | Covers | How |
|---|---|---|---|
| Math | `mathcheck.py` | derivatives, integrals, limits, equations, simplifying, arithmetic | SymPy computes the answer |
| Numbers | `valuecheck.py` | statistics (mean ... normal probabilities), geometry (area, volume, Pythagoras, angles, distance) | computed; rounded options are fine ("78.54", "68%") |
| Science | `sciencecheck.py` | physics (a fixed list of 16 standard laws, with units), chemistry (molar mass, moles, pH, balancing) | the model only picks the law and values, never the formula; units are converted and checked |
| Language | `langcheck.py` | Spanish present-tense conjugations, English irregular verbs and plurals | tables; words not in the tables are left unchecked, never guessed |
| Fact bank | `factbank.py` | state and world capitals, presidents 1-45, amendments, Congress and the branches, key dates | questions are generated from the facts, so they're right by construction |
| Notes | `groundcheck.py` | any course with notes in Materials | the model must quote the sentence its answer comes from; the quote must be in the notes and support the keyed option |
| Textbook | `textbooks.py` | courses with an imported OpenStax book | the book's own multiple-choice review questions (official answer keys) and glossary terms; right by construction |

In every case the app writes the question text from what it checked, fixes a wrong key,
and drops questions it can't verify. Quizzes use checked questions first; each question
shows how it was checked. The quiz prompt only offers the question forms a course uses
(`families` in courses.py), which keeps it short for the small model.

To verify a new course: add a checker (or facts) for its answer types, add tests, run
`eval_quiz.py` on its topics, then set `verification`, `checks`, `not_checked` and
`families` in courses.py.

Existing courses whose name exactly matches a standard course are linked on startup; others can
be linked with "find a matching course" (`PATCH /api/subjects/<id>`), keeping their own name.

## Textbooks (OpenStax)

Free OpenStax textbooks can be imported with `python import_openstax.py <course>` (see
`docs/commands.txt`). They live in their own database, `backend/user_data/textbooks.db`
(`TEXTBOOK_DB_PATH` to move it), separate from student data, so it can be deleted and rebuilt.
`textbooks.BOOKS` maps each catalog course to its book(s) (Biology -> Biology 2e, U.S. History,
Chemistry 2e, Calculus Volume 1, ...).

Students can also import from the app: a course with a book that isn't imported shows a
"Free textbook available" card on the Progress page (`textbook_import.available` on the
course). "Import it" calls `POST /api/textbooks/import`, which downloads in a background
thread; the page polls `GET /api/textbooks/import/<course_id>` (`running` / `done` / `failed`
with a message) and refreshes when it's done. "Not now" hides the card in that browser.
Set `ALLOW_TEXTBOOK_IMPORT=0` to turn in-app imports off.

The importer downloads a book's source (CNXML from `github.com/openstax/osbooks-*`, text only)
and stores:

| Table | What |
|---|---|
| `books` | slug, course, title, license (read from the book's own files), link |
| `sections` | number ("10.2", or none for a chapter introduction), chapter, title, in book order |
| `passages` | ~900-character chunks of text under a heading; searched with SQLite FTS5 (`passages_fts`), falling back to LIKE without FTS5 |
| `questions` | multiple-choice review questions with exactly 4 options and an answer letter; ones that point at a figure or table are skipped |
| `terms` | glossary terms and meanings |

How the app uses a book (all offline, a few milliseconds each):

- **Quizzes**: for the topic, pick the chapter that teaches it (a chapter title naming the
  topic, then the chapter whose glossary defines it, then the best-matching passages), and use
  its review questions plus a glossary question or two. These go first. When the book and fact
  bank give enough questions, the model isn't asked at all. A topic the book doesn't cover
  gets no textbook questions.
- **Tutor chat**: the 2-3 passages that best match the student's message (preferring the
  topic's chapter) go into the prompt after their notes, within `DOC_CHAR_BUDGET` and at most
  `TEXTBOOK_CHAR_BUDGET` (default 2500) characters. The reply returns `textbook_sources`.
- **Courses**: `textbooks` on each course and an extra line in `checks`.

Licensing: most OpenStax books are CC BY-NC-SA 4.0 (Physics is CC BY 4.0): free for
non-commercial use, with credit. Clutch shows the book title, license and a link wherever it
uses one (chat credit bar, quiz question sources). Book content is never committed to git.

## API

- `GET /api/profiles` - profiles for the sign-in screen (no data, no hashes)
- `POST /api/users` `{username, password}` - new profile (password 4+ characters); signs in
- `POST /api/session` `{username, password}` (or `{username, new_password}` for a pre-password profile) - sign in; `GET /api/session` - who's signed in; `DELETE /api/session` - sign out
- `POST /api/session/recover` `{username, recovery_code, new_password}` - forgot password; signs in and returns a new `recovery_code`
- `GET|POST /api/users/<uid>/subjects`, `DELETE /api/subjects/<id>`
- `POST /api/subjects/<id>/topics`, `DELETE /api/topics/<id>`
- `GET|POST /api/users/<uid>/conversations`, `GET|DELETE /api/conversations/<id>`
- `POST /api/conversations/<id>/messages` `{content, homework?}` - saves both turns; scanned homework text is added to the prompt like in `/api/chat`
- `POST /api/conversations/<id>/end` `{confidence?}` - review + progress update
- `GET|POST /api/users/<uid>/documents`, `GET|DELETE /api/documents/<id>`
- `GET /api/courses`, `POST /api/courses/suggest` `{query}` - catalog, and matches for what a student typed
- `GET /api/textbooks` - imported OpenStax books with license and credit line (no sign-in needed)
- `POST /api/textbooks/import` `{course_id}` - start downloading a course's book(s) (202); `GET /api/textbooks/import/<course_id>` - `{available, state, error}`
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
`tests/test_textbooks.py` builds a tiny made-up book, so no download is needed.

## Frontend files

`App.jsx` (sign-in, sidebar, tabs), `Chat.jsx` (saved study sessions + end-of-session review),
`Homework.jsx` (scan homework), `Materials.jsx`, `Progress.jsx`, `Meter.jsx`, `Markdown.jsx`, `api.js`.
`SymbolKeyboard.jsx` + `keyboards.js`: the symbol keyboard under the chat box (math, calculus,
linear algebra, geometry, statistics, physics, chemistry, Spanish, French, German), picked from
the session's topic or the chat so far. Keys type `^` for powers and `× ÷ − √ π`, which
`mathcheck.py` reads (it turns `√(...)` and `x²` into forms it can check).
Homework text is still kept in the browser only; saving it to the database is a possible next step.
