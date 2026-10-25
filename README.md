<p align="center">
  <img src="frontend/src/assets/mascot/logo.svg" alt="Clutch" width="320">
</p>

<p align="center">
  <b>A Socratic study tutor that runs on your own computer.</b><br>
  It helps you understand your homework instead of doing it for you.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.15-3776AB?logo=python&logoColor=white" alt="Python 3.15">
  <img src="https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white" alt="Flask 3.1">
  <img src="https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white" alt="SQLite 3">
  <img src="https://img.shields.io/badge/pytest-9.1-0A9EDC?logo=pytest&logoColor=white" alt="pytest 9.1">
  <img src="https://img.shields.io/badge/SymPy-1.14-3B5526?logo=sympy&logoColor=white" alt="SymPy 1.14">
  <br>
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white" alt="Vite 8">
  <img src="https://img.shields.io/badge/Node.js-24-5FA04E?logo=nodedotjs&logoColor=white" alt="Node.js 24">
  <img src="https://img.shields.io/badge/KaTeX-0.19-329894" alt="KaTeX 0.19">
  <br>
  <img src="https://img.shields.io/badge/Ollama-0.40-000000?logo=ollama&logoColor=white" alt="Ollama 0.40">
  <img src="https://img.shields.io/badge/Model-Gemma_4_e2b-4285F4?logo=google&logoColor=white" alt="Gemma 4 e2b">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="MIT License">
</p>

---

## What is Clutch?

Clutch is a homework tutor built on a small AI model ([Gemma 4 e2b](https://ollama.com/library/gemma4))
that runs locally through [Ollama](https://ollama.com), so no student data leaves the computer.
Instead of handing out answers, it teaches the way a good tutor does:

- **Guides, doesn't solve.** Working on a problem gets you one hint or guiding question at a time, even
  if you beg for the answer.
- **Explains concepts.** Ask "What is the chain rule?" and you get a real explanation with a formula and
  an example.
- **Checks your answers.** Propose an answer and it tells you plainly whether it's right. If it isn't,
  it points to the step where you went wrong without giving the answer away.
- **Reads your homework.** Snap a photo of a worksheet and Clutch turns it into editable text, makes a
  study guide, and keeps the chat focused on that material.
- **Tracks progress.** Sessions are saved per subject and topic, with a review at the end and a
  mastery score over time. Each topic's egg hatches as mastery grows.
- **Quizzes and badges.** At 80% mastery a topic's quiz unlocks; pass it (4 of 5) to earn that
  topic's badge. Math answer keys are checked with [SymPy](https://www.sympy.org), so a wrong key
  from the model gets fixed before a student ever sees it.
- **Renders real math.** Equations show up properly typeset with KaTeX.

## How it works

```
React + Vite (frontend)  ──/api──▶  Flask (backend)  ──▶  Ollama running Gemma 4 e2b
     :5173                            :5001                     :11434
                                        │
                                        ├──▶  SQLite (chats, topics, progress, quizzes, badges)
                                        └──▶  SymPy (checks math quiz answers)
```

The tutor's behavior comes from the system prompt in [`backend/app.py`](backend/app.py), and it is
tested by [`backend/eval_tutor.py`](backend/eval_tutor.py). That script pressures the tutor to give
away answers, gives it right and wrong attempts and concept questions, and saves every reply to
`backend/eval_results/` for review. [`backend/eval_quiz.py`](backend/eval_quiz.py) does the same for
quizzes: it has the model write quizzes and reports how often SymPy had to fix its answer key.

## Getting started

You need Python 3.15, Node.js 24 and [Ollama](https://ollama.com). In short:

```bash
ollama pull gemma4:e2b
```

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

```bash
cd frontend && npm install
```

Then run Ollama, the Flask backend (`flask --app app run --port 5001`) and the frontend
(`npm run dev`) in three terminals, and open http://localhost:5173.

Full step-by-step instructions for Windows, including the `.env` file, activating the venv and
troubleshooting, are in [`docs/commands.txt`](docs/commands.txt).

## Project layout

| Path | What's there |
|---|---|
| [`backend/app.py`](backend/app.py) | Flask API and the tutor's system prompt |
| [`backend/db.py`](backend/db.py), [`schema.sql`](backend/schema.sql) | SQLite data layer ([docs](docs/database.md)) |
| [`backend/mathcheck.py`](backend/mathcheck.py) | SymPy checker for math quiz questions |
| [`backend/eval_tutor.py`](backend/eval_tutor.py) | Behavior tests for the tutor |
| [`backend/eval_quiz.py`](backend/eval_quiz.py) | Quiz tests against the real model (answer key accuracy) |
| [`backend/tests/`](backend/tests) | API and math checker tests (`pytest`) |
| [`frontend/src/`](frontend/src) | React app: chat, homework scanner, materials, progress, quizzes |
| [`frontend/src/assets/mascot/`](frontend/src/assets/mascot) | Mother Hen art, eggs and badges ([`generate.py`](frontend/src/assets/mascot/generate.py) makes them) |
| [`docs/`](docs) | Setup commands, database notes, dev log |

## License

[MIT](LICENSE)
