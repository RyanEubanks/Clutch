import base64
import binascii
import json
import math
import os
import random
import re
import sqlite3
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from openai import OpenAI

import courses
import db
import factbank
import groundcheck
import planner

try:
    import mathcheck  # SymPy answer checking for math quiz questions
except ImportError:  # sympy not installed yet: run pip install -r requirements.txt
    mathcheck = None
    print("WARNING: sympy is not installed, so math quiz questions can't be checked. "
          "Run: pip install -r requirements.txt")

load_dotenv()

MODEL = os.getenv("MODEL_NAME")
client = OpenAI(base_url=os.getenv("MODEL_BASE_URL"), api_key="local")

# Ollama runs models with a small context window by default (see docs/devlog.txt),
# so cap how much study material goes into each prompt. Raise this once num_ctx is raised.
DOC_CHAR_BUDGET = int(os.getenv("DOC_CHAR_BUDGET", "6000"))

# Mastery quizzes: unlock at this topic mastery, pass with this fraction correct.
QUIZ_UNLOCK_MASTERY = float(os.getenv("QUIZ_UNLOCK_MASTERY", "0.8"))
QUIZ_PASS_FRACTION = float(os.getenv("QUIZ_PASS_FRACTION", "0.8"))
QUIZ_QUESTIONS = int(os.getenv("QUIZ_QUESTIONS", "5"))

#
#SYSTEM_PROMPT = (
#    "You are a Socratic tutor. Help the student learn; do not give the final "
#    "answer or a full worked solution, even if asked. Ask one short guiding "
#    "question at a time, or give a small hint."
#)

SYSTEM_PROMPT = ("""You are a Socratic tutor. Help the student learn; do not solve the \
problem for them.

Every student message is one of three kinds. Decide which kind it is before you reply, \
checking them in this order:

1. ANSWER: the student proposes an answer to a problem. This counts even when it is phrased \
as a question, for example "Is it 7/8?", "Is it e^(x^2) + C?", "I got x = 5, is that right?" \
or "So it's 60 km/h?".
- First work the problem out yourself, step by step, and get the correct answer. Then compare \
it with the student's answer. Never say an answer is correct unless it matches the answer you \
worked out. Equivalent forms count as correct (for example 6x(x^2+1)^2 and 3(x^2+1)^2 * 2x, \
or e^(x^2) + C written as e^{x^2} + C).
- If it is correct: start your reply with "Yes, that's right." Explain in one or two \
sentences why it works. Do not give any more hints or steps for that problem. Then ask one \
question that deepens understanding, or offer a similar practice problem. A correct answer is \
correct even if the student did not show their work; never call it wrong for that.
- If it is wrong: start your reply with "Not quite." Do not reveal the correct answer. Point \
to the step where the reasoning went off, with one small hint.

2. CONCEPT QUESTION: the student asks about a concept, definition, notation, or why a method \
works, for example "What is the chain rule?" or "What does the C mean?".
- Answer it directly. Explain the idea clearly in a few sentences, with the formula if there \
is one and a small example that is NOT one of the problems they are working on.
- Then ask one short question to check they understood.
- Do not answer a concept question with only a question back. Explaining ideas is how you \
help; what you hold back is the answer to the specific problem they are solving.
- If they ask a concept question about a problem they are working on, explain the concept, \
but do not apply it all the way to their problem.

3. WORKING ON A PROBLEM: the student asks how to solve a specific problem, or asks for the \
answer, and has not given an answer yet.
- Do not give the final answer or a full worked solution, even if asked.
- Ask one short guiding question at a time, or give one small hint.

Watch for answers that sound reasonable but are wrong. For example, getting 0/0 when you plug \
a number into a limit does NOT mean the limit is 0; 0/0 means the expression must be \
simplified first. A student who says "the limit is 0 because I got 0/0" is wrong.

Hints are only for a student who has not reached the answer yet. Once they have it, \
confirm it.

Write math in LaTeX: $...$ for math inside a sentence and $$...$$ for math on its own line.
""")

HOMEWORK_CONTEXT = """

The student uploaded this homework and is working on it:
<homework>
{homework}
</homework>

Keep the conversation on this material. If the student asks about something unrelated, \
gently bring them back to the homework. The rules above apply to every homework problem: \
do not give their final answers or full solutions."""

READ_PROMPT = """Transcribe the homework problems in this image exactly as written.
- Number each problem the way the page does (or 1, 2, 3... if it has no numbers).
- Write math in LaTeX: $...$ inside a sentence, $$...$$ on its own line.
- Include instructions such as "Show your work" or "Round to two decimals".
- Do not solve anything or add comments.
- If part of the page is unreadable, write [unclear] there."""

NOTES_READ_PROMPT = """Transcribe the notes in this image exactly as written, in Markdown.
- Keep the structure: titles and section names as headings (# or ##), lists as bullet points, \
numbered steps and problems as numbered lists.
- Write math in LaTeX: $...$ inside a sentence, $$...$$ on its own line.
- For a drawing, graph or diagram, write one short line describing it, like \
[Diagram: parabola opening up with vertex at (0, 1)].
- Do not add explanations, corrections or anything that is not on the page.
- If part of the page is unreadable, write [unclear] there."""

READ_PROMPTS = {"homework": READ_PROMPT, "notes": NOTES_READ_PROMPT}

# ---------- lecture recording ----------

# Gemma ignores audio after about 30 seconds, so the browser sends shorter pieces.
MAX_AUDIO_BYTES = 3_000_000  # ~90 s of 16 kHz mono WAV; real pieces are under 30 s
# Each part of a transcript is turned into notes separately so prompts fit the context window.
LECTURE_PART_CHARS = int(os.getenv("LECTURE_PART_CHARS", "4000"))

TRANSCRIBE_PROMPT = """Transcribe this audio exactly, word for word, with normal punctuation. \
Output only the transcript. If there is no speech, output nothing."""

LECTURE_NOTES_PROMPT = """Turn this part of a lecture transcript into clear study notes in Markdown.
- Use ## headings for each topic the lecturer covers, and bullet points for the key ideas.
- Write every formula in LaTeX: $...$ inside a sentence, $$...$$ on its own line. Spoken math \
becomes symbols, for example "the integral of u d v" becomes $\\int u \\, dv$.
- The transcript comes from speech recognition, so fix words that were clearly misheard when \
the right word is obvious from context (for example "lay" for the acronym LIATE). Do not add \
facts, examples or explanations that the lecturer did not say.
- Keep definitions, worked examples, and anything the lecturer says is important, on the exam, \
or for homework.
- Leave out filler, greetings and repetition.
- {position}
- Output only the notes.

Transcript (part {part} of {total}):
{transcript}"""


def split_transcript(text, max_chars):
    """Split text into parts of at most max_chars, at paragraph or sentence breaks."""
    pieces = []
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        while len(para) > max_chars:
            cut = para.rfind(". ", 0, max_chars)
            cut = cut + 1 if cut > max_chars // 2 else max_chars
            pieces.append(para[:cut].strip())
            para = para[cut:].strip()
        pieces.append(para)
    parts, current = [], ""
    for piece in pieces:
        if current and len(current) + 2 + len(piece) > max_chars:
            parts.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    return parts + [current] if current else parts

STUDY_GUIDE_PROMPT = """Make a study guide for the material in this homework. Use Markdown \
with these sections:

## Topics
The topics the homework covers, as a short list.

## Key ideas
A short, plain explanation of each idea the student needs.

## Formulas
The formulas and rules they will use, in LaTeX.

## Worked example
Solve ONE new problem that is similar to the homework but not one of its problems, step by step.

## Practice problems
Three new problems like the homework, then their final answers under "Answers".

Do not solve the homework problems themselves. Write math in LaTeX: $...$ inside a sentence \
and $$...$$ on its own line.

Homework:
{homework}"""

REVIEW_PROMPT = (
    "You are reviewing a tutoring session. Judge how well the STUDENT understood the "
    "material, based only on what the student wrote (not the tutor). Reply with JSON only, "
    'in this exact shape: {"understanding": <number from 0 to 1>, '
    '"summary": "<one sentence on what was studied>", '
    '"strengths": "<what the student did well>", '
    '"gaps": "<what the student still needs to work on>"}'
)


QUIZ_HEAD = """Write a {n}-question multiple-choice quiz that checks whether a student has \
mastered this topic.

Subject: {subject}
Topic: {topic}
{description}{material}
Write each question in ONE of the forms below. Prefer the TASK forms whenever the topic allows:
the app computes their answers itself, so they are always right. Do NOT write question text
for TASK forms; the app writes it.
"""

QUIZ_SECTIONS = {
    "math": """
MATH TASK: any calculation, including plain arithmetic like 45 + 23 (derivatives, integrals,
limits, solving equations, arithmetic, evaluating or simplifying expressions), like this:
{"op": "diff", "expr": "(3*x+1)**4", "var": "x", "options": ["12*(3*x+1)**3", "4*(3*x+1)**3", \
"12*x*(3*x+1)**3", "(3*x+1)**3"], "answer": 0, "explanation": "Chain rule: 4(3x+1)^3 times 3."}
"op" is one of:
- "diff": derivative of expr
- "integrate": indefinite integral of expr
- "definite": integral of expr from "lower" to "upper" (add those two fields)
- "limit": limit of expr as var approaches "at" (add the "at" field)
- "evaluate": the value of expr, at var = "at" if you add an "at" field. Use this for
  arithmetic: {"op": "evaluate", "expr": "45 + 23", "options": ["68", "78", "58", "67"], "answer": 0}
- "simplify": which option is equivalent to expr
- "solve": solve the equation in expr, e.g. "x**2 - 4 = 0"; options look like "x = 2, x = -2"
Write expr and EVERY option in Python/SymPy syntax: * to multiply, ** for powers, sqrt(), exp(),
log(), sin(), cos(), pi. No LaTeX and no $ signs in math tasks.
""",
    "stats": """
STATISTICS TASK, like this:
{"op": "mean", "data": [3, 5, 7, 7, 9], "options": ["6.2", "7", "5", "6.5"], "answer": 0}
"op" is one of: "mean", "median", "mode", "range", "variance", "stdev" (with "data"; add
"sample": true for the sample variance or standard deviation); "combinations" or
"permutations" (add "n" and "k"); "binomial" (add "n", "k", "p": the chance of exactly k
successes in n trials); "normal" (add "mean", "sd", and "lower" and/or "upper");
"zscore" (add "x", "mean", "sd"). Options are numbers.
""",
    "geometry": """
GEOMETRY TASK, like this:
{"op": "area", "shape": "circle", "r": 5, "unit": "cm", "options": ["25pi", "10pi", "5pi", \
"50pi"], "answer": 0}
- "area": shape "square" (s), "rectangle" (l, w), "triangle" (b, h), "parallelogram" (b, h),
  "trapezoid" (a, b, h), "circle" (r or d)
- "perimeter": "square" (s), "rectangle" (l, w), "triangle" (a, b, c), "circle" (r or d)
- "volume": "cube" (s), "box" (l, w, h), "cylinder" (r, h), "sphere" (r), "cone" (r, h)
- "hypotenuse" (a, b); "leg" (c = hypotenuse, a = the known leg); "missing_angle" ("angles":
  two angles of a triangle); "angle_sum" or "regular_angle" ("sides"); "distance"
  ("points": [[x1, y1], [x2, y2]])
"unit" is optional (cm, m, in, ft). Options are numbers, and may use pi.
""",
    "physics": None,  # filled in from sciencecheck.LAWS below
    "chemistry": """
CHEMISTRY TASK, like this:
{"op": "molar_mass", "formula": "H2SO4", "options": ["98.08 g/mol", "96.06 g/mol", \
"49.04 g/mol", "100.1 g/mol"], "answer": 0}
"op" is one of: "molar_mass" (formula); "moles" (formula, grams); "grams" (formula, moles);
"ph" ("h" = [H+] in mol/L, or "ph" to ask for [H+]); "balance" ("equation" like
"CH4 + O2 -> CO2 + H2O"; options are coefficient lists like "1, 2, 1, 2").
""",
    "spanish": """
SPANISH CONJUGATION TASK (present tense only), like this:
{"op": "conjugate", "verb": "tener", "person": "nosotros", "tense": "present", \
"options": ["tenemos", "tienemos", "tenimos", "tienen"], "answer": 0}
"person" is one of: yo, tú, él, nosotros, vosotros, ellos. Use common verbs.
""",
    "english": """
ENGLISH TASK, like this:
{"op": "english_verb", "verb": "swim", "form": "past", "options": ["swam", "swum", \
"swimmed", "swims"], "answer": 0}
Ops: "english_verb" (an irregular verb; "form" is "past" or "past_participle") and "plural"
(an irregular noun, e.g. {"op": "plural", "noun": "mouse", ...}).
""",
}

QUIZ_CONCEPT = """
CONCEPT: a question about an idea, definition, fact, or reasoning:
{"question": "...", "options": ["...", "...", "...", "..."], "answer": 1, "explanation": "..."}
Write any math in concept questions in LaTeX: $...$.
"""
QUIZ_CONCEPT_SOURCE = """For every CONCEPT question, also add "source": the exact sentence from the
student's material that shows the answer, copied word for word. The app checks it.
"""
QUIZ_TAIL = """
Rules:
- Every question has exactly 4 different options and exactly one correct option.
- Wrong options should be mistakes a student might really make.
- "answer" is the index (0-3) of the correct option.
- "explanation" says in one or two sentences why the correct option is right.

Reply with JSON only, in this shape: {"questions": [ ...questions... ]}"""


def _physics_section():
    import sciencecheck
    laws = "\n".join(
        f"- {name} (" + ", ".join(f"{v} {desc}" for v, (desc, _) in law["vars"].items()) + ")"
        for name, law in sciencecheck.LAWS.items())
    return f"""
PHYSICS TASK (the app solves it with units; give no formula), like this:
{{"op": "physics", "law": "kinetic_energy", "given": {{"m": "2 kg", "v": "3 m/s"}}, "find": "K", \
"unit": "J", "options": ["9 J", "6 J", "18 J", "3 J"], "answer": 0}}
"law" is one of these (its variables in parentheses). "given" has every variable except
"find", each with a unit (m, cm, km, s, min, h, kg, g, N, J, kJ, W, A, V, ohm, Hz, Pa, L,
m/s, km/h, m/s^2, kg/m^3, m^2, m^3). Use g = "9.8 m/s^2" for gravity.
{laws}
"""


def build_quiz_prompt(families, has_material, **fields):
    """The quiz prompt with only the TASK forms this course uses (shorter prompts work
    better with a small model)."""
    parts = [QUIZ_HEAD]
    for family in families:
        if mathcheck is None:
            break  # nothing can check tasks without SymPy
        parts.append(_physics_section() if family == "physics" else QUIZ_SECTIONS[family])
    parts.append(QUIZ_CONCEPT)
    if has_material:
        parts.append(QUIZ_CONCEPT_SOURCE)
    parts.append(QUIZ_TAIL)
    return quiz_prompt(template="".join(parts), **fields)


def quiz_prompt(template=None, **fields):
    # Plain replace instead of str.format, so the JSON examples' braces stay as they are.
    prompt = template or QUIZ_HEAD + QUIZ_SECTIONS["math"] + QUIZ_CONCEPT + QUIZ_TAIL
    for key, value in fields.items():
        prompt = prompt.replace("{" + key + "}", str(value))
    return prompt


COURSE_MATCH_PROMPT = """A student wants to add a course called: "{query}"

Here are the standard courses (id: name, area, level; usual topics):
{catalog}

Which standard courses best fit what the student typed? Rules:
- Pick at most 3, best first. Only use ids from the list. If nothing fits, return none.
- If what they typed is a topic INSIDE a course (like "Addition" inside Elementary Math,
  or "Chain rule" inside Calculus I), set "as_topic" to true for that course.
- "why" is one short sentence for the student.

Reply with JSON only: {{"matches": [{{"id": "...", "as_topic": true, "why": "..."}}]}}"""


def ask_model(messages, temperature=0.2, json_mode=False):
    """Send messages to the model and return the reply text."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=temperature, **kwargs
    )
    return resp.choices[0].message.content


def math_facts(check):
    """Extra system-prompt lines with the math engine's verdict on the student's answer."""
    lines = []
    for c in check["claims"]:
        if c["correct"]:
            lines.append(f"- The student's answer {c['shown']} is CORRECT.")
        else:
            lines.append(f"- The student's answer {c['shown']} is WRONG. "
                         f"Do not tell them the correct value.")
    if check.get("posed"):
        lines.append(f"- The student wrote the problem {check['posed']} without an answer. "
                     f"They want help with it: treat it as WORKING ON A PROBLEM, and do not "
                     f"say \"Not quite.\"")
    if not lines:
        return ""
    return ("\n\nMATH ENGINE CHECK. This was computed exactly by a calculator. Trust it over your "
            "own arithmetic and never contradict it:\n" + "\n".join(lines) +
            "\nFollow your rules for answers: if an answer is correct, start your reply with "
            "\"Yes, that's right.\" If it is wrong, start with \"Not quite.\"")


def verdict(reply):
    """True if the reply confirms the answer, False if it rejects it, None if neither."""
    start = (reply or "").strip().lower()
    if start.startswith(("yes", "correct", "that's right", "that is right", "exactly", "right")):
        return True
    if start.startswith(("not quite", "no,", "no.", "not exactly", "incorrect", "that's not")):
        return False
    return None


def tutor_reply(system, history):
    """Ask the tutor for its next reply, with the student's math answer checked first.

    history ends with the student's newest message. If the student gave exactly one
    answer and the tutor's verdict contradicts the math engine, ask once more; if it is
    still wrong, send a short reply with the right verdict instead.
    Returns (reply, check).
    """
    student = history[-1]["content"] if history and history[-1].get("role") == "user" else ""
    check = (mathcheck.check_chat_answer(student, history[:-1])
             if (mathcheck and student) else {"claims": [], "posed": None})
    facts = math_facts(check)
    messages = [{"role": "system", "content": system + facts}, *history]
    reply = ask_model(messages)

    if len(check["claims"]) != 1:
        return reply, check
    claim = check["claims"][0]

    def contradicts(text):
        v = verdict(text)
        return v is False if claim["correct"] else v is True

    def unconfirmed(text):
        return claim["correct"] and verdict(text) is not True

    if contradicts(reply) or unconfirmed(reply):
        if claim["correct"]:
            fix = ('the answer {} is CORRECT. Rewrite your reply so it starts with '
                   '"Yes, that\'s right."').format(claim["shown"])
        else:
            fix = ('the answer {} is WRONG. Rewrite your reply so it starts with '
                   '"Not quite." and do not reveal the correct value.').format(claim["shown"])
        retry = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": f"(Note from the app, not the student: the math engine checked this: {fix})"},
        ]
        reply = ask_model(retry)
        if contradicts(reply) or unconfirmed(reply):
            if claim["correct"]:
                reply = (f"Yes, that's right: ${claim['tex']}$. Nice work! "
                         f"Want to try another one?")
            else:
                reply = (f"Not quite. Take another look at ${claim['problem_tex']}$ and work it "
                         f"out step by step. What do you get?")
    return reply, check


def with_homework(system, homework):
    homework = (homework or "").strip()
    return system + HOMEWORK_CONTEXT.format(homework=homework) if homework else system


def build_system_prompt(conn, convo, homework=None):
    """The base tutor prompt, plus homework, topic, progress and study material."""
    parts = [with_homework(SYSTEM_PROMPT, homework)]
    if convo["topic_id"] is None:
        return parts[0]
    topic = db.get_topic(conn, convo["topic_id"])
    parts.append(f"\nThe student is studying: {topic['subject_name']} / {topic['name']}.")
    if topic["description"]:
        parts.append(f"Topic notes: {topic['description']}")

    progress = db.get_topic_progress(conn, convo["user_id"], convo["topic_id"])
    if progress and progress["sessions_count"]:
        parts.append(
            f"Their estimated mastery of this topic is {progress['mastery']:.0%} "
            f"after {progress['sessions_count']} session(s)."
        )
        if progress["last_gaps"]:
            parts.append(f"Last time they struggled with: {progress['last_gaps']}")

    budget = DOC_CHAR_BUDGET
    excerpts = []
    for doc in db.topic_documents(conn, convo["topic_id"]):
        if budget <= 0:
            break
        text = doc["content"][:budget]
        budget -= len(text)
        excerpts.append(f"--- {doc['title']} ---\n{text}")
    if excerpts:
        parts.append(
            "\nThe student's own study material is below. Use it to ground your questions "
            "and hints, and point them back to it, but still do not give final answers.\n\n"
            + "\n\n".join(excerpts)
        )
    return "\n".join(parts)


def parse_review(text):
    """Pull the review fields out of the model's reply, tolerating messy output."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        data = {}
    try:
        understanding = min(1.0, max(0.0, float(data.get("understanding"))))
    except (TypeError, ValueError):
        understanding = None

    def text_field(key):
        value = data.get(key)
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value)
        return str(value).strip() if value else None

    return {
        "understanding": understanding,
        "summary": text_field("summary"),
        "strengths": text_field("strengths"),
        "gaps": text_field("gaps"),
    }


def shuffle_options(q):
    """Shuffle so the correct option isn't always in the same spot."""
    order = random.sample(range(4), 4)
    return {**q, "options": [q["options"][i] for i in order], "answer": order.index(q["answer"])}


def quiz_questions_from(text, report=None, material=None):
    """Every usable question in the model's reply.

    Math questions (with an "op") are checked with SymPy: the answer key is fixed if the
    model got it wrong, and questions SymPy can't verify are dropped. Concept questions
    can't be checked by a computer, so they pass through with verified=False.

    With `material` (the topic's notes), concept questions that quote a "source" sentence
    are checked against the notes (groundcheck.py).

    If `report` is a list, one entry per question the model wrote is appended to it
    (used by eval_quiz.py to measure how the checker handles real model output).
    """
    def note(**entry):
        if report is not None:
            report.append(entry)

    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        note(kind="reply", status="bad_json", error="reply was not valid JSON")
        return []
    items = [q for q in data.get("questions") or [] if isinstance(q, dict)]
    if not items:
        note(kind="reply", status="bad_json", error="no questions in the reply")

    math_items = [q for q in items if q.get("op")]
    checked = mathcheck.check_questions(math_items) if (mathcheck and math_items) else []
    math_results = iter(checked)

    # Plain-text questions with number options ("What is 12 + 7?") often hide arithmetic:
    # check those too, when the question spells the arithmetic out.
    concepts = {i: parse_concept(q) for i, q in enumerate(items) if not q.get("op")}
    numeric = {i: c for i, c in concepts.items() if c and c["numeric"]}
    arith = (mathcheck.check_questions(list(numeric.values()), arithmetic=True)
             if (mathcheck and numeric) else [])
    arith_results = dict(zip(numeric, arith))

    questions = []
    for i, q in enumerate(items):
        if q.get("op"):
            result, error = next(math_results, (None, "sympy not installed"))
            if result:
                questions.append(shuffle_options(result))
                note(kind="math", op=q.get("op"), raw=q,
                     status="corrected" if result["corrected"] else "checked", result=result)
            else:
                note(kind="math", op=q.get("op"), raw=q, status="dropped", error=error)
            continue
        concept = concepts[i]
        result, error = arith_results.get(i, (None, None))
        if not result and concept and material and q.get("source"):
            try:
                result = groundcheck.check_grounded({**q, **concept}, material)
                note(kind="notes", raw=q, status="corrected" if result["corrected"] else "checked",
                     result=result)
                questions.append(shuffle_options(result))
                continue
            except groundcheck.MathError as exc:
                error = str(exc)
        if result:
            result["numeric"] = True
            questions.append(shuffle_options(result))
            note(kind="math", op="arithmetic (in question text)", raw=q,
                 status="corrected" if result["corrected"] else "checked", result=result)
        elif concept:
            questions.append(shuffle_options(concept))
            note(kind="concept", raw=q, status="unchecked", result=concept, error=error)
        else:
            note(kind="concept", raw=q, status="dropped", error="not 4 distinct options with a valid answer")
    return questions


def parse_quiz(text, expected):
    """Exactly `expected` questions from one reply, or [] if there aren't enough."""
    questions = quiz_questions_from(text)
    return questions[:expected] if len(questions) >= expected else []


def parse_concept(q):
    """Validate a concept (non-math) question. Returns None if it's unusable."""
    options = [str(o).strip() for o in q.get("options") or [] if str(o).strip()]
    answer = q.get("answer")
    # Accept an index, a letter ("B"), or the option text itself.
    if isinstance(answer, str):
        a = answer.strip()
        if a in options:
            answer = options.index(a)
        elif len(a) == 1 and a.upper() in "ABCD":
            answer = "ABCD".index(a.upper())
        elif a.isdigit():
            answer = int(a)
    question = str(q.get("question") or "").strip()
    if (not question or len(options) != 4 or len(set(options)) != 4
            or not isinstance(answer, int) or not 0 <= answer < 4):
        return None
    return {
        "question": question,
        "options": options,
        "answer": answer,
        "explanation": str(q.get("explanation") or "").strip(),
        "verified": False,
        # Number answers are where small models slip most, so unchecked ones rank last.
        "numeric": numeric_options(options),
    }


def numeric_options(options):
    """True if every option is a plain number like '7', '3/4' or '13 apples'."""
    return all(re.fullmatch(r"\$?\s*-?[\d.,/\s]+\$?(\s+[A-Za-z]+){0,2}\.?", str(o).strip())
               for o in options)


def public_quiz(quiz):
    """Hide answers and explanations until the quiz has been submitted."""
    quiz = {**quiz, "needed": math.ceil(QUIZ_PASS_FRACTION * quiz["total"] - 1e-9),
            "math_checker": mathcheck is not None}
    if quiz["submitted_at"] is None:
        # Answers, explanations and note quotes stay hidden until the quiz is submitted.
        quiz = {**quiz, "questions": [
            {"question": q["question"], "options": q["options"], "verified": q.get("verified", False),
             "checked_by": q.get("checked_by") if q.get("verified") else None}
            for q in quiz["questions"]
        ]}
    return quiz


def quiz_unlocked(progress):
    return bool(progress and progress["sessions_count"]
                and progress["mastery"] >= QUIZ_UNLOCK_MASTERY)


def with_course(subject):
    """Add the catalog course (or None) and whether it's verified to a subject dict."""
    course = courses.get(subject.get("catalog_id"))
    subject["course"] = courses.public(course) if course else None
    subject["verified"] = bool(course and course["verified"])
    subject["verification"] = course["verification"] if course else None
    return subject


def suggest_courses(query):
    """Catalog courses for what a student typed, best first.

    Combines Gemma (understands "times tables" means multiplication) with a keyword
    match (fast, and still works if the model is slow or returns something unusable).
    Exact name/topic keyword hits go first, since they're certain.
    """
    keyword = courses.keyword_matches(query, limit=5)
    model_picks, source = [], "keywords"
    catalog = "\n".join(
        f"- {c['id']}: {c['name']}, {c['area']}, {c['level']}; {', '.join(c['topics'])}"
        for c in courses.CATALOG
    )
    try:
        raw = ask_model([{"role": "user", "content": COURSE_MATCH_PROMPT.format(
            query=query.replace('"', "'"), catalog=catalog)}], temperature=0, json_mode=True)
        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        data = json.loads(match.group(0)) if match else {}
        for m in data.get("matches") or []:
            if isinstance(m, dict) and courses.get(str(m.get("id"))):
                model_picks.append(m)
        source = "model+keywords"
    except Exception:  # model offline, slow, or not JSON: keyword matches still work
        pass

    ordered, why = [], {}
    for course, score in keyword:
        if score >= 8:
            ordered.append(course["id"])
    for m in model_picks:
        ordered.append(m["id"])
        why.setdefault(m["id"], str(m.get("why") or "").strip())
    ordered += [course["id"] for course, _ in keyword]
    model_topic = {m["id"] for m in model_picks if m.get("as_topic") is True}

    suggestions, seen = [], set()
    for course_id in ordered:
        if course_id in seen:
            continue
        seen.add(course_id)
        course = courses.get(course_id)
        is_course = courses._norm(query) == courses._norm(course["name"])
        topic = courses.matching_topic(course, query)
        as_topic = not is_course and (topic is not None or course_id in model_topic)
        suggestions.append({
            "course": courses.public(course),
            "as_topic": as_topic,
            "topic": (topic or query.strip()) if as_topic else None,
            "why": why.get(course_id) or (
                f"{topic} is a topic in {course['name']}." if topic else
                f"Matches \"{query.strip()}\"."),
        })
        if len(suggestions) == 3:
            break
    return suggestions, source


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = db_path or db.db_path()

    conn = db.connect(app.config["DATABASE_PATH"])
    db.init_db(conn)
    # Courses named exactly like a standard course ("Elementary Math") get linked to it.
    db.link_catalog_names(conn, {c["name"].lower(): c["id"] for c in courses.CATALOG})
    conn.close()

    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DATABASE_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(exc):
        return jsonify(error=f"Conflict: {exc}"), 409

    def body():
        return request.get_json(silent=True) or {}

    def not_found(what):
        return jsonify(error=f"{what} not found"), 404

    # ---------- health & stateless chat ----------

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", model=MODEL, math_checker=mathcheck is not None)

    @app.post("/api/chat")
    def chat():
        """Stateless chat (nothing saved). Used by eval_tutor.py and chat_cli.py."""
        data = body()
        messages = data.get("messages", [])
        if not messages:
            return jsonify(error="messages is required"), 400
        system = with_homework(SYSTEM_PROMPT, data.get("homework"))
        try:
            reply, _check = tutor_reply(system, messages)
        except Exception as exc:
            return jsonify(error=f"Model request failed: {exc}"), 502
        return jsonify(reply=reply)

    # ---------- homework scanning ----------

    @app.post("/api/homework/read")
    def read_homework():
        """Turn photos of homework or notes (base64 data URLs) into text the student can edit.

        Body: {"images": [...], "kind": "homework" | "notes"}  (kind defaults to homework)
        """
        images = body().get("images", [])
        if not images:
            return jsonify(error="images is required"), 400
        prompt = READ_PROMPTS.get(body().get("kind") or "homework")
        if not prompt:
            return jsonify(error="kind must be homework or notes"), 400

        pages = []
        try:
            # One request per page keeps each image's prompt small for the e2b model
            for image in images:
                pages.append(ask_model(
                    [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                    temperature=0,
                ))
        except Exception as exc:
            return jsonify(error=f"Model request failed: {exc}"), 502

        return jsonify(text="\n\n".join(pages))

    @app.post("/api/lecture/transcribe")
    def transcribe_lecture():
        """Transcribe one short piece of a lecture recording.

        Body: {"audio": "<base64 WAV>"} (a data: URL prefix is fine). Pieces should be under
        30 seconds; the browser recorder cuts them at quiet moments.
        """
        audio = (body().get("audio") or "").split(",")[-1]
        try:
            raw = base64.b64decode(audio, validate=True)
        except (binascii.Error, ValueError):
            return jsonify(error="audio must be base64-encoded WAV"), 400
        if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
            return jsonify(error="audio must be base64-encoded WAV"), 400
        if len(raw) > MAX_AUDIO_BYTES:
            return jsonify(error="audio piece is too long; send under 30 seconds at a time"), 413

        try:
            text = ask_model(
                [{
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": {"data": audio, "format": "wav"}},
                        {"type": "text", "text": TRANSCRIBE_PROMPT},
                    ],
                }],
                temperature=0,
            )
        except Exception as exc:
            return jsonify(error=f"Model request failed: {exc}"), 502
        return jsonify(text=(text or "").strip())

    @app.post("/api/lecture/notes")
    def lecture_notes():
        """Turn a lecture transcript into Markdown study notes, one part at a time."""
        transcript = (body().get("transcript") or "").strip()
        if not transcript:
            return jsonify(error="transcript is required"), 400

        parts = split_transcript(transcript, LECTURE_PART_CHARS)
        notes = []
        try:
            for i, part in enumerate(parts, start=1):
                position = (
                    "Start with a one-line title for the lecture, like # Integration by parts."
                    if i == 1
                    else "This continues earlier notes, so do not add a # title."
                )
                notes.append(ask_model([{
                    "role": "user",
                    "content": LECTURE_NOTES_PROMPT.format(
                        position=position, part=i, total=len(parts), transcript=part
                    ),
                }]).strip())
        except Exception as exc:
            return jsonify(error=f"Model request failed: {exc}"), 502
        return jsonify(notes="\n\n".join(notes), parts=len(parts))

    @app.post("/api/homework/study-guide")
    def study_guide():
        homework = (body().get("homework") or "").strip()
        if not homework:
            return jsonify(error="homework is required"), 400

        try:
            guide = ask_model([{"role": "user", "content": STUDY_GUIDE_PROMPT.format(homework=homework)}])
        except Exception as exc:
            return jsonify(error=f"Model request failed: {exc}"), 502

        return jsonify(guide=guide)

    # ---------- users ----------

    @app.post("/api/users")
    def login():
        """Sign in by username, creating the user the first time. No passwords yet."""
        username = (body().get("username") or "").strip()
        if not username:
            return jsonify(error="username is required"), 400
        return jsonify(db.get_or_create_user(get_db(), username, body().get("display_name")))

    @app.get("/api/users/<int:user_id>")
    def get_user(user_id):
        user = db.get_user(get_db(), user_id)
        return jsonify(user) if user else not_found("User")

    # ---------- subjects & topics ----------

    @app.get("/api/users/<int:user_id>/subjects")
    def list_subjects(user_id):
        return jsonify([with_course(s) for s in db.list_subjects_with_topics(get_db(), user_id)])

    @app.post("/api/users/<int:user_id>/subjects")
    def create_subject(user_id):
        """Body: {"name": "..."} for a custom course, or {"catalog_id": "...", "topic": "..."}
        to add a standard course (its name comes from the catalog). "topic" is optional and
        is added inside the course; if the student already has that course, the topic is
        added to it instead of creating a duplicate."""
        conn = get_db()
        if not db.get_user(conn, user_id):
            return not_found("User")
        data = body()
        catalog_id = data.get("catalog_id")
        course = courses.get(catalog_id) if catalog_id else None
        if catalog_id and not course:
            return jsonify(error="unknown catalog course"), 400
        name = course["name"] if course else (data.get("name") or "").strip()
        if not name:
            return jsonify(error="name is required"), 400

        subject = db.find_subject(conn, user_id, name) if course else None
        created = subject is None
        if created:
            subject = db.create_subject(conn, user_id, name, catalog_id)
        elif course and subject.get("catalog_id") != catalog_id:
            subject = db.set_subject_catalog(conn, subject["id"], catalog_id)

        topic = None
        topic_name = (data.get("topic") or "").strip()
        if topic_name:
            topic = db.find_topic(conn, subject["id"], topic_name) or db.create_topic(
                conn, subject["id"], topic_name)
        return jsonify(with_course(subject) | {"topic": topic, "created": created}), (201 if created else 200)

    # ---------- course catalog ----------

    @app.get("/api/courses")
    def list_courses():
        return jsonify([courses.public(c) for c in courses.CATALOG])

    @app.post("/api/courses/suggest")
    def suggest():
        """Body: {"query": "what the student typed"}. Returns standard courses that fit."""
        query = (body().get("query") or "").strip()
        if not query:
            return jsonify(error="query is required"), 400
        if len(query) > 120:
            return jsonify(error="query is too long"), 400
        suggestions, source = suggest_courses(query)
        return jsonify(query=query, suggestions=suggestions, source=source)

    @app.patch("/api/subjects/<int:subject_id>")
    def link_subject(subject_id):
        """Body: {"catalog_id": "..." or null}. Links a course to a standard course (it keeps
        its own name), or unlinks it."""
        conn = get_db()
        if not db.get_subject(conn, subject_id):
            return not_found("Subject")
        catalog_id = body().get("catalog_id")
        if catalog_id is not None and not courses.get(catalog_id):
            return jsonify(error="unknown catalog course"), 400
        return jsonify(with_course(db.set_subject_catalog(conn, subject_id, catalog_id)))

    @app.delete("/api/subjects/<int:subject_id>")
    def delete_subject(subject_id):
        db.delete_subject(get_db(), subject_id)
        return "", 204

    @app.post("/api/subjects/<int:subject_id>/topics")
    def create_topic(subject_id):
        name = (body().get("name") or "").strip()
        if not name:
            return jsonify(error="name is required"), 400
        if not db.get_subject(get_db(), subject_id):
            return not_found("Subject")
        return jsonify(db.create_topic(get_db(), subject_id, name, body().get("description"))), 201

    @app.delete("/api/topics/<int:topic_id>")
    def delete_topic(topic_id):
        db.delete_topic(get_db(), topic_id)
        return "", 204

    # ---------- conversations ----------

    @app.get("/api/users/<int:user_id>/conversations")
    def list_conversations(user_id):
        return jsonify(db.list_conversations(get_db(), user_id))

    @app.post("/api/users/<int:user_id>/conversations")
    def create_conversation(user_id):
        conn = get_db()
        if not db.get_user(conn, user_id):
            return not_found("User")
        topic_id = body().get("topic_id")
        if topic_id is not None:
            topic = db.get_topic(conn, topic_id)
            if not topic or topic["user_id"] != user_id:
                return not_found("Topic")
        return jsonify(db.create_conversation(conn, user_id, topic_id, body().get("title"))), 201

    @app.get("/api/conversations/<int:conversation_id>")
    def get_conversation(conversation_id):
        conn = get_db()
        convo = db.get_conversation(conn, conversation_id)
        if not convo:
            return not_found("Conversation")
        convo["messages"] = db.get_messages(conn, conversation_id)
        convo["review"] = db.get_review(conn, conversation_id)
        return jsonify(convo)

    @app.delete("/api/conversations/<int:conversation_id>")
    def delete_conversation(conversation_id):
        db.delete_conversation(get_db(), conversation_id)
        return "", 204

    @app.post("/api/conversations/<int:conversation_id>/messages")
    def send_message(conversation_id):
        """Save the student's message, ask the tutor, save and return the reply.

        Body: {"content": "...", "homework": "..."}  (homework text is optional)
        """
        conn = get_db()
        convo = db.get_conversation(conn, conversation_id)
        if not convo:
            return not_found("Conversation")
        content = (body().get("content") or "").strip()
        if not content:
            return jsonify(error="content is required"), 400

        user_msg = db.add_message(conn, conversation_id, "user", content)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in db.get_messages(conn, conversation_id)
        ]
        try:
            system = build_system_prompt(conn, convo, body().get("homework"))
            reply, check = tutor_reply(system, history)
        except Exception as exc:
            db.delete_message(conn, user_msg["id"])  # so a retry doesn't duplicate it
            return jsonify(error=f"Model request failed: {exc}"), 502

        assistant_msg = db.add_message(conn, conversation_id, "assistant", reply)
        return jsonify(
            user_message=user_msg,
            assistant_message=assistant_msg,
            conversation=db.get_conversation(conn, conversation_id),
            math_check=check["claims"],  # what the math engine found in the student's message
        )

    @app.post("/api/conversations/<int:conversation_id>/end")
    def end_conversation(conversation_id):
        """Review the session and update the student's progress on the topic.

        Body: {"confidence": 1-5}  (optional self-rating)
        """
        conn = get_db()
        convo = db.get_conversation(conn, conversation_id)
        if not convo:
            return not_found("Conversation")
        messages = db.get_messages(conn, conversation_id)
        if not any(m["role"] == "user" for m in messages):
            return jsonify(error="Nothing to review yet"), 400

        confidence = body().get("confidence")
        if confidence is not None:
            try:
                confidence = int(confidence)
            except (TypeError, ValueError):
                confidence = 0
            if not 1 <= confidence <= 5:
                return jsonify(error="confidence must be 1-5"), 400

        transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        try:
            raw = ask_model(
                [{"role": "system", "content": REVIEW_PROMPT},
                 {"role": "user", "content": transcript}],
                temperature=0,
                json_mode=True,
            )
            review = parse_review(raw)
        except Exception:
            # The model being down shouldn't block saving the student's own rating.
            review = parse_review("")

        saved = db.save_session_review(conn, conversation_id, confidence=confidence, **review)
        progress = (
            db.get_topic_progress(conn, convo["user_id"], convo["topic_id"])
            if convo["topic_id"] else None
        )
        has_badge = bool(convo["topic_id"]) and db.get_badge(conn, convo["user_id"], convo["topic_id"]) is not None
        return jsonify(
            review=saved,
            progress=progress,
            quiz_unlocked=quiz_unlocked(progress) and not has_badge,
            has_badge=has_badge,
        )

    # ---------- documents ----------

    @app.get("/api/users/<int:user_id>/documents")
    def list_documents(user_id):
        """Optional ?q= searches titles and content."""
        return jsonify(db.list_documents(get_db(), user_id, request.args.get("q")))

    @app.post("/api/users/<int:user_id>/documents")
    def create_document(user_id):
        data = body()
        title = (data.get("title") or "").strip()
        content = data.get("content") or ""
        if not title or not content.strip():
            return jsonify(error="title and content are required"), 400
        conn = get_db()
        if not db.get_user(conn, user_id):
            return not_found("User")
        topic_id = data.get("topic_id")
        if topic_id is not None:
            topic = db.get_topic(conn, topic_id)
            if not topic or topic["user_id"] != user_id:
                return not_found("Topic")
        return jsonify(db.create_document(conn, user_id, title, content, topic_id)), 201

    @app.get("/api/documents/<int:document_id>")
    def get_document(document_id):
        doc = db.get_document(get_db(), document_id)
        return jsonify(doc) if doc else not_found("Document")

    @app.delete("/api/documents/<int:document_id>")
    def delete_document(document_id):
        db.delete_document(get_db(), document_id)
        return "", 204

    # ---------- progress ----------

    @app.get("/api/users/<int:user_id>/progress")
    def progress(user_id):
        rows = db.progress_overview(get_db(), user_id)
        for r in rows:
            r["quiz_unlocked"] = quiz_unlocked(r)
            r["quiz_unlock_at"] = QUIZ_UNLOCK_MASTERY
            course = courses.get(r.get("catalog_id"))
            r["verified"] = bool(course and course["verified"])
        return jsonify(rows)

    # ---------- planner: calendar events, spaced repetition, metrics ----------

    def event_fields(data, user_id, partial=False):
        """Validate event fields from a request body. Returns (fields, topic_ids, error)."""
        conn = get_db()
        fields = {}
        if not partial or "kind" in data:
            if data.get("kind") not in db.EVENT_KINDS:
                return None, None, f"kind must be one of {', '.join(db.EVENT_KINDS)}"
            fields["kind"] = data["kind"]
        if not partial or "title" in data:
            title = (data.get("title") or "").strip()
            if not title:
                return None, None, "title is required"
            fields["title"] = title
        if not partial or "date" in data:
            try:
                fields["date"] = date.fromisoformat(data.get("date") or "").isoformat()
            except ValueError:
                return None, None, "date must be YYYY-MM-DD"
        if "time" in data:
            t = data.get("time") or None
            if t and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
                return None, None, "time must be HH:MM"
            fields["time"] = t
        if "notes" in data:
            fields["notes"] = (data.get("notes") or "").strip() or None
        if "done" in data:
            fields["done"] = bool(data["done"])
        if "subject_id" in data:
            sid = data.get("subject_id")
            if sid is not None:
                subject = db.get_subject(conn, sid)
                if not subject or subject["user_id"] != user_id:
                    return None, None, "subject not found"
            fields["subject_id"] = sid
        topic_ids = None
        if "topic_ids" in data:
            topic_ids = []
            for tid in data.get("topic_ids") or []:
                topic = db.get_topic(conn, tid)
                if not topic or topic["user_id"] != user_id:
                    return None, None, "topic not found"
                topic_ids.append(tid)
        return fields, topic_ids, None

    @app.get("/api/users/<int:user_id>/events")
    def list_events(user_id):
        """Optional ?from=YYYY-MM-DD&to=YYYY-MM-DD (inclusive)."""
        return jsonify(db.list_events(get_db(), user_id, request.args.get("from"), request.args.get("to")))

    @app.post("/api/users/<int:user_id>/events")
    def create_event(user_id):
        if not db.get_user(get_db(), user_id):
            return not_found("User")
        fields, topic_ids, error = event_fields(body(), user_id)
        if error:
            return jsonify(error=error), 400
        return jsonify(db.create_event(get_db(), user_id, topic_ids=topic_ids or [], **fields)), 201

    @app.patch("/api/events/<int:event_id>")
    def update_event(event_id):
        event = db.get_event(get_db(), event_id)
        if not event:
            return not_found("Event")
        fields, topic_ids, error = event_fields(body(), event["user_id"], partial=True)
        if error:
            return jsonify(error=error), 400
        return jsonify(db.update_event(get_db(), event_id, fields, topic_ids))

    @app.delete("/api/events/<int:event_id>")
    def delete_event(event_id):
        db.delete_event(get_db(), event_id)
        return "", 204

    @app.get("/api/users/<int:user_id>/planner")
    def study_planner(user_id):
        """Today's reviews, exam readiness and study metrics.

        ?today=YYYY-MM-DD and ?tz=<Date.getTimezoneOffset()> come from the browser, so "today"
        and the streak follow the student's own clock rather than the server's (UTC) one.
        """
        try:
            today = date.fromisoformat(request.args.get("today") or date.today().isoformat())
            tz = int(request.args.get("tz") or 0)
        except ValueError:
            return jsonify(error="today must be YYYY-MM-DD and tz a number of minutes"), 400
        conn = get_db()
        topics = db.progress_overview(conn, user_id)
        for t in topics:
            t["quiz_unlocked"] = quiz_unlocked(t) and not t["badge_earned_at"]
        events = db.list_events(conn, user_id, start=today.isoformat())
        since = (datetime.combine(today, datetime.min.time())
                 - timedelta(days=planner.ACTIVITY_DAYS + 1)).strftime("%Y-%m-%d %H:%M:%S")
        plan = planner.schedule(topics, events, today, tz)
        return jsonify(
            today=today.isoformat(),
            due=[p for p in plan if p["due_today"]],
            upcoming=[p for p in plan if not p["due_today"]],
            tests=planner.readiness(events, topics, today),
            metrics=planner.metrics(
                db.study_activity(conn, user_id, since), db.quizzes_since(conn, user_id, since),
                topics, today, tz,
            ),
        )

    # ---------- quizzes & badges ----------

    @app.post("/api/topics/<int:topic_id>/quiz")
    def start_quiz(topic_id):
        """Return the student's open quiz for this topic, or write a new one."""
        conn = get_db()
        topic = db.get_topic(conn, topic_id)
        if not topic:
            return not_found("Topic")
        user_id = topic["user_id"]
        if not quiz_unlocked(db.get_topic_progress(conn, user_id, topic_id)):
            return jsonify(
                error=f"The quiz unlocks at {QUIZ_UNLOCK_MASTERY:.0%} mastery. Keep studying!"
            ), 403

        existing = db.open_quiz(conn, user_id, topic_id)
        if existing:
            return jsonify(public_quiz(existing))

        material, notes = "", ""
        docs = db.topic_documents(conn, topic_id)
        if docs:
            notes = "\n\n".join(d["content"] for d in docs)[:DOC_CHAR_BUDGET]
            material = f"\nBase the questions on the student's study material:\n<material>\n{notes}\n</material>\n"
        prompt = build_quiz_prompt(
            courses.families(topic["catalog_id"]),
            bool(notes),
            # Ask for a couple extra, since questions that fail the checks are dropped.
            n=QUIZ_QUESTIONS + 2,
            subject=topic["subject_name"],
            topic=topic["name"],
            description=f"About this topic: {topic['description']}\n" if topic["description"] else "",
            material=material,
        )
        # Fact-bank questions (social studies) are right by construction.
        facts = factbank.questions_for(topic["catalog_id"], topic["name"], QUIZ_QUESTIONS)
        questions, seen = [], set()
        model_error = None
        try:
            # Small models sometimes return broken JSON or uncheckable math, so keep
            # collecting good questions over up to two attempts.
            for _ in range(2):
                raw = ask_model([{"role": "user", "content": prompt}], temperature=0.4, json_mode=True)
                for q in quiz_questions_from(raw, material=notes or None):
                    if q["question"] not in seen:
                        seen.add(q["question"])
                        questions.append(q)
                if sum(q["verified"] for q in questions) + len(facts) >= QUIZ_QUESTIONS:
                    break
        except Exception as exc:
            model_error = exc
        if model_error and len(facts) < QUIZ_QUESTIONS:
            return jsonify(error=f"Model request failed: {model_error}"), 502
        # Checked questions first (the model's, then fact-bank ones), then unchecked ones;
        # unchecked number questions go last.
        checked = [q for q in questions if q["verified"]]
        unchecked = sorted((q for q in questions if not q["verified"]),
                           key=lambda q: 1 if q.get("numeric") else 0)
        questions = (checked + [f for f in facts if f["question"] not in seen] + unchecked)[:QUIZ_QUESTIONS]
        if len(questions) < QUIZ_QUESTIONS:
            return jsonify(error="Mother Hen couldn't write a quiz this time. Please try again."), 502

        quiz = db.create_quiz(conn, user_id, topic_id, questions)
        return jsonify(public_quiz(quiz)), 201

    @app.get("/api/quizzes/<int:quiz_id>")
    def get_quiz(quiz_id):
        quiz = db.get_quiz(get_db(), quiz_id)
        return jsonify(public_quiz(quiz)) if quiz else not_found("Quiz")

    @app.post("/api/quizzes/<int:quiz_id>/submit")
    def submit_quiz(quiz_id):
        """Body: {"answers": [option index per question]}. Grades and awards the badge."""
        conn = get_db()
        quiz = db.get_quiz(conn, quiz_id)
        if not quiz:
            return not_found("Quiz")
        if quiz["submitted_at"] is not None:
            return jsonify(error="This quiz was already submitted"), 409
        answers = body().get("answers")
        if (not isinstance(answers, list) or len(answers) != quiz["total"]
                or not all(isinstance(a, int) and 0 <= a < 4 for a in answers)):
            return jsonify(error=f"answers must be {quiz['total']} option indexes (0-3)"), 400

        graded, new_badge = db.submit_quiz(conn, quiz_id, answers, QUIZ_PASS_FRACTION)
        return jsonify(
            quiz=graded,
            new_badge=new_badge,
            badge=db.get_badge(conn, graded["user_id"], graded["topic_id"]),
            needed=math.ceil(QUIZ_PASS_FRACTION * graded["total"] - 1e-9),
        )

    @app.get("/api/users/<int:user_id>/badges")
    def list_badges(user_id):
        return jsonify(db.list_badges(get_db(), user_id))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(port=5001, debug=True)
