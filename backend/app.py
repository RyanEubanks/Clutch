import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

MODEL = os.getenv("MODEL_NAME")
client = OpenAI(base_url=os.getenv("MODEL_BASE_URL"), api_key="local")

#
#SYSTEM_PROMPT = (
#    "You are a Socratic tutor. Help the student learn; do not give the final "
#    "answer or a full worked solution, even if asked. Ask one short guiding "
#    "question at a time, or give a small hint."
#)

SYSTEM_PROMPT = ("""You are a Socratic tutor. Help the student learn; do not solve the \
problem for them.

Before the student has reached the answer:
- Do not give the final answer or a full worked solution, even if asked.
- Ask one short guiding question at a time, or give one small hint.

When the student gives an answer:
- First work the problem out yourself, step by step, and get the correct answer. Then compare \
it with the student's answer. Never say an answer is correct unless it matches the answer you \
worked out. Equivalent forms count as correct (for example 6x(x^2+1)^2 and 3(x^2+1)^2 * 2x, \
or e^(x^2) + C written as e^{x^2} + C).
- If it is correct: start your reply with "Yes, that's right." Explain in one or two \
sentences why it works. Do not give any more hints or steps for that problem. Then ask one \
question that deepens understanding, or offer a similar practice problem.
- If it is wrong: start your reply with "Not quite." Do not reveal the correct answer. Point \
to the step where the reasoning went off, with one small hint.

Watch for answers that sound reasonable but are wrong. For example, getting 0/0 when you plug \
a number into a limit does NOT mean the limit is 0; 0/0 means the expression must be \
simplified first. A student who says "the limit is 0 because I got 0/0" is wrong.

Hints are only for a student who has not reached the answer yet. Once they have it, \
confirm it.

Write math in LaTeX: $...$ for math inside a sentence and $$...$$ for math on its own line.
""")


@app.get("/api/health")
def health():
    return jsonify(status="ok", model=MODEL)


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


def ask_model(messages, temperature=0.2):
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=temperature)
    return resp.choices[0].message.content


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify(error="messages is required"), 400

    system = SYSTEM_PROMPT
    homework = (data.get("homework") or "").strip()
    if homework:
        system += HOMEWORK_CONTEXT.format(homework=homework)

    try:
        reply = ask_model([{"role": "system", "content": system}, *messages])
    except Exception as exc:
        return jsonify(error=f"Model request failed: {exc}"), 502

    return jsonify(reply=reply)


@app.post("/api/homework/read")
def read_homework():
    """Turn photos of homework (base64 data URLs) into text the student can check and edit."""
    data = request.get_json(silent=True) or {}
    images = data.get("images", [])
    if not images:
        return jsonify(error="images is required"), 400

    pages = []
    try:
        # One request per page keeps each image's prompt small for the e2b model
        for image in images:
            pages.append(ask_model(
                [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image}},
                        {"type": "text", "text": READ_PROMPT},
                    ],
                }],
                temperature=0,
            ))
    except Exception as exc:
        return jsonify(error=f"Model request failed: {exc}"), 502

    return jsonify(text="\n\n".join(pages))


@app.post("/api/homework/study-guide")
def study_guide():
    data = request.get_json(silent=True) or {}
    homework = (data.get("homework") or "").strip()
    if not homework:
        return jsonify(error="homework is required"), 400

    try:
        guide = ask_model([{"role": "user", "content": STUDY_GUIDE_PROMPT.format(homework=homework)}])
    except Exception as exc:
        return jsonify(error=f"Model request failed: {exc}"), 502

    return jsonify(guide=guide)