import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

MODEL = os.getenv("MODEL_NAME")
client = OpenAI(base_url=os.getenv("MODEL_BASE_URL"), api_key="local")

SYSTEM_PROMPT = (
    "You are a Socratic tutor. Help the student learn; do not give the final "
    "answer or a full worked solution, even if asked. Ask one short guiding "
    "question at a time, or give a small hint."
)


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
        )
    except Exception as exc:
        return jsonify(error=f"Model request failed: {exc}"), 502

    return jsonify(reply=resp.choices[0].message.content)