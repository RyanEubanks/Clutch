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
- First work the problem out yourself, step by step, and decide if their answer is correct. \
Equivalent forms count as correct (for example 6x(x^2+1)^2 and 3(x^2+1)^2 * 2x).
- If it is correct: start your reply by saying so clearly ("Yes, that's right."), explain in \
one or two sentences why it works, and STOP giving hints. Then ask one question that deepens \
understanding, or offer a similar practice problem.
- If it is wrong: do not reveal the correct answer. Point to the step where the reasoning \
went off, with one small hint.

Hints are only for a student who has not reached the answer yet. Once they have it, \
confirm it.
""")


@app.get("/api/health")
def health():
    return jsonify(status="ok", model=MODEL)


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify(error="messages is required"), 400

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            temperature=0.2,
        )
    except Exception as exc:
        return jsonify(error=f"Model request failed: {exc}"), 502

    return jsonify(reply=resp.choices[0].message.content)