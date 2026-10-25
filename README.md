<p align="center">
  <img src="frontend/src/assets/mascot/logo.svg" alt="Clutch" width="320">
</p>

<p align="center">
  <b>A Socratic study tutor that runs on your own computer.</b><br>
  It helps you understand your homework instead of doing it for you.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white" alt="Flask 3.1">
  <img src="https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white" alt="SQLite 3">
  <img src="https://img.shields.io/badge/pytest-9.1-0A9EDC?logo=pytest&logoColor=white" alt="pytest 9.1">
  <img src="https://img.shields.io/badge/SymPy-1.14-3B5526?logo=sympy&logoColor=white" alt="SymPy 1.14">
  <br>
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white" alt="Vite 8">
  <img src="https://img.shields.io/badge/Node.js-20.19+-5FA04E?logo=nodedotjs&logoColor=white" alt="Node.js 20.19+">
  <img src="https://img.shields.io/badge/KaTeX-0.16-329894" alt="KaTeX 0.16">
  <br>
  <img src="https://img.shields.io/badge/Ollama-0.40-000000?logo=ollama&logoColor=white" alt="Ollama 0.40">
  <img src="https://img.shields.io/badge/Model-Gemma_4_e2b-4285F4?logo=google&logoColor=white" alt="Gemma 4 e2b">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="MIT License">
</p>

---

## What is Clutch?

Clutch is a homework tutor built on a small AI model ([Gemma 4 e2b](https://ai.google.dev/gemma/docs/core))
that runs locally through [Ollama](https://ollama.com), so no student data leaves the computer.
Mother Hen, its mascot, teaches the way a good tutor does instead of handing out answers:

- **Guides, doesn't solve.** Working on a problem gets you one hint or guiding question at a time, even
  if you beg for the answer.
- **Explains concepts.** Ask "What is the chain rule?" and you get a real explanation with a formula and
  an example.
- **Checks your answers.** Propose an answer and it tells you plainly whether it's right. Math in the
  chat is checked with [SymPy](https://www.sympy.org), so the tutor doesn't say "Not quite" to a
  correct answer. A symbol keyboard under the chat box (math, calculus, chemistry, Spanish, ...)
  makes answers easy to type.
- **Reads your homework.** Snap a photo of a worksheet and Clutch turns it into editable text, makes a
  study guide, and keeps the chat focused on that material. Save it to Materials to keep it.
- **Records lectures.** Record a class with your microphone. Clutch transcribes it on your own
  computer as it goes, then turns the transcript into organized notes with the math typeset.
- **Any course, honestly labeled.** Type any course ("my times tables homework") and Clutch suggests
  matching standard courses (21 of them, from Elementary Math to Psychology). Each shows how much of
  it Clutch can check: **✓ Verified**, **Partly verified** or **Not verified**, with the details.
- **Checked quizzes.** At 80% mastery a topic's quiz unlocks; pass it (4 of 5) to earn the topic's
  badge. Answer keys are checked before a student sees them: SymPy for math, built-in calculators for
  statistics, geometry, physics and chemistry, tables for Spanish and English, a fact bank for social
  studies, the student's own notes, and free textbooks. Each question says how it was checked.
- **Free textbooks.** Courses with a free [OpenStax](https://openstax.org) book (Biology, U.S. History,
  Chemistry, Psychology, ...) offer it with one click. Then quizzes use the book's own review questions,
  and Mother Hen reads the relevant pages when she helps you, with the book credited.
- **Tracks progress.** Sessions are saved per course and topic, with a review at the end. Each topic's
  egg hatches as mastery grows, and earning every topic badge in a course wins its course trophy.
- **Plans your studying.** The Planner holds exams and homework and schedules reviews by spaced
  repetition, aiming for each exam.
- **Private profiles.** Each student signs in with a password; the demo profile, Alex, needs none.

## System requirements

Clutch runs entirely on one computer. The AI model is the heavy part: it needs about 7 GB of memory
while it's loaded, so memory matters more than anything else.

| | Minimum | Recommended |
|---|---|---|
| **Memory (RAM)** | 8 GB (close other apps; replies are slower) | 16 GB or more |
| **Processor / GPU** | Any 64-bit CPU (Intel Macs run the model on the CPU only: slow) | Apple silicon (M1 or newer), or an NVIDIA/AMD GPU with 8 GB+ of memory |
| **Disk space** | 12 GB free (the model is a 7.2 GB download; Ollama itself takes up to 4 GB) | 20 GB free (room for all the textbooks and backups) |
| **Operating system** | macOS 14 Sonoma, Windows 10 22H2, or a recent 64-bit Linux | The latest macOS or Windows 11 |
| **Python** | 3.11 | 3.12 or newer |
| **Node.js** | 20.19 or 22.13 | 24 LTS |
| **Ollama** | A version with Gemma 4 support (0.20 or newer) | The latest |
| **Browser** | A current Chrome, Edge, Safari or Firefox | The latest version of any of them |
| **Internet** | Only for installing, and once per textbook | Same: everything else works offline |
| **Optional** | git, to download OpenStax textbooks | |

Notes:

- The Python minimum comes from the pinned packages in `backend/requirements.txt` (some need 3.11);
  the Node.js minimum from Vite 8 and ESLint 10. The memory figures are for `gemma4:e2b`, the
  default model. A bigger Gemma 4 model gives better answers but needs more memory (see
  [`docs/devlog.txt`](docs/devlog.txt), OPEN-02).
- Lecture recording needs a microphone and uses the browser's audio worklets; scanning homework
  needs a camera or photos.
- To check a computer, run `python check_setup.py` in `backend/`. It compares the computer with
  this table, checks that Ollama is running with the model downloaded, and says what to fix.

## How it works

```
React + Vite (frontend)  ──/api──▶  Flask (backend)  ──▶  Ollama running Gemma 4 e2b
     :5173                            :5001                     :11434
                                        │
                                        ├──▶  SQLite: profiles, chats, topics, progress,
                                        │     quizzes, badges, trophies, planner (user_data/clutch.db)
                                        ├──▶  Answer checkers: SymPy, calculators, tables,
                                        │     fact bank, notes check
                                        └──▶  OpenStax textbooks, searchable (user_data/textbooks.db)
```

The tutor's behavior comes from the system prompt in [`backend/app.py`](backend/app.py), and it is
tested by [`backend/eval_tutor.py`](backend/eval_tutor.py). That script pressures the tutor to give
away answers, gives it right and wrong attempts and concept questions, and saves every reply to
`backend/eval_results/` for review. [`backend/eval_quiz.py`](backend/eval_quiz.py) does the same for
quizzes: it has the model write quizzes and reports how often the checkers had to fix its answer key.

## Getting started

Install [Ollama](https://ollama.com), Python 3.11+ and Node.js 20.19+ (see
[System requirements](#system-requirements)), then:

```bash
ollama pull gemma4:e2b

cd backend
cp .env.example .env                 # Windows: copy .env.example .env
python3 -m venv .venv                # Windows: python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python check_setup.py                # optional: checks everything above

cd ../frontend
npm install
```

Then run Ollama, the Flask backend (`flask --app app run --port 5001` in `backend/`, with the venv
active) and the frontend (`npm run dev` in `frontend/`) in three terminals, and open
http://localhost:5173. Sign in as **Alex** to see the demo, or make your own profile.

Optional: add free textbooks from a course's card on the Progress page, or with
`python import_openstax.py biology` (internet needed once per book).

Full step-by-step instructions, including troubleshooting, are in
[`docs/commands.txt`](docs/commands.txt).

## Running the tests

```bash
cd backend
python -m pytest tests               # uses a fake model: no Ollama needed
cd ../frontend && npm run lint
```

## Project layout

| Path | What's there |
|---|---|
| [`backend/app.py`](backend/app.py) | Flask API, sign-in, and the tutor's and quiz writer's prompts |
| [`backend/db.py`](backend/db.py), [`schema.sql`](backend/schema.sql) | SQLite data layer and migrations ([docs](docs/database.md)) |
| [`backend/courses.py`](backend/courses.py) | Course catalog, verification levels and course suggestions |
| [`backend/mathcheck.py`](backend/mathcheck.py) | SymPy checker for math quiz questions and answers in chat |
| [`backend/valuecheck.py`](backend/valuecheck.py), [`sciencecheck.py`](backend/sciencecheck.py) | Statistics and geometry; physics (with units) and chemistry |
| [`backend/langcheck.py`](backend/langcheck.py), [`factbank.py`](backend/factbank.py), [`groundcheck.py`](backend/groundcheck.py) | Spanish/English tables, social studies facts, the notes check |
| [`backend/textbooks.py`](backend/textbooks.py), [`import_openstax.py`](backend/import_openstax.py) | OpenStax textbook import, search and quiz questions |
| [`backend/planner.py`](backend/planner.py) | Spaced repetition and exam readiness |
| [`backend/demo.py`](backend/demo.py) | The Alex demo profile |
| [`backend/check_setup.py`](backend/check_setup.py) | Checks a computer against the system requirements |
| [`backend/eval_tutor.py`](backend/eval_tutor.py), [`eval_quiz.py`](backend/eval_quiz.py) | Tests against the real model (tutor behavior, quiz answer keys) |
| [`backend/regrade_quizzes.py`](backend/regrade_quizzes.py) | Re-checks saved quizzes and fixes wrong answer keys |
| [`backend/tests/`](backend/tests) | API, checker, planner and textbook tests (`pytest`) |
| [`frontend/src/`](frontend/src) | React app: study chat, planner, homework scanner, materials, progress, quizzes |
| [`frontend/src/assets/mascot/`](frontend/src/assets/mascot) | Mother Hen art, eggs, badges and trophies ([`generate.py`](frontend/src/assets/mascot/generate.py) makes them) |
| [`docs/`](docs) | Setup commands, database notes, dev log |

Student data lives in `backend/user_data/` (ignored by git), on the student's own computer.

## License

Clutch is [MIT](LICENSE) licensed. Textbooks imported from [OpenStax](https://openstax.org) keep
their own licenses (most are CC BY-NC-SA 4.0, Physics is CC BY 4.0): they're free for non-commercial
use with credit, which Clutch shows wherever a book is used. Book content is never stored in git.
