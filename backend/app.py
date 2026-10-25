import json
import os
import re
import sqlite3

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from openai import OpenAI

import db

load_dotenv()

MODEL = os.getenv("MODEL_NAME")
client = OpenAI(base_url=os.getenv("MODEL_BASE_URL"), api_key="local")

# Ollama runs models with a small context window by default (see docs/devlog.txt),
# so cap how much study material goes into each prompt. Raise this once num_ctx is raised.
DOC_CHAR_BUDGET = int(os.getenv("DOC_CHAR_BUDGET", "6000"))

SYSTEM_PROMPT = (
    "You are a Socratic tutor. Help the student learn; do not give the final "
    "answer or a full worked solution, even if asked. Ask one short guiding "
    "question at a time, or give a small hint."
)

REVIEW_PROMPT = (
    "You are reviewing a tutoring session. Judge how well the STUDENT understood the "
    "material, based only on what the student wrote (not the tutor). Reply with JSON only, "
    'in this exact shape: {"understanding": <number from 0 to 1>, '
    '"summary": "<one sentence on what was studied>", '
    '"strengths": "<what the student did well>", '
    '"gaps": "<what the student still needs to work on>"}'
)


def complete(messages, json_mode=False):
    """Send messages to the model and return the reply text."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = client.chat.completions.create(model=MODEL, messages=messages, **kwargs)
    return resp.choices[0].message.content


def build_system_prompt(conn, convo):
    """The base tutor prompt, plus what we know about this topic and student."""
    parts = [SYSTEM_PROMPT]
    if convo["topic_id"] is None:
        return SYSTEM_PROMPT
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


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = db_path or db.db_path()

    conn = db.connect(app.config["DATABASE_PATH"])
    db.init_db(conn)
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
        return jsonify(status="ok", model=MODEL)

    @app.post("/api/chat")
    def chat():
        """Stateless chat (nothing saved). Kept for eval_tutor.py and chat_cli.py."""
        messages = body().get("messages", [])
        if not messages:
            return jsonify(error="messages is required"), 400
        try:
            reply = complete([{"role": "system", "content": SYSTEM_PROMPT}, *messages])
        except Exception as exc:
            return jsonify(error=f"Model request failed: {exc}"), 502
        return jsonify(reply=reply)

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
        return jsonify(db.list_subjects_with_topics(get_db(), user_id))

    @app.post("/api/users/<int:user_id>/subjects")
    def create_subject(user_id):
        name = (body().get("name") or "").strip()
        if not name:
            return jsonify(error="name is required"), 400
        if not db.get_user(get_db(), user_id):
            return not_found("User")
        return jsonify(db.create_subject(get_db(), user_id, name)), 201

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
        """Save the student's message, ask the tutor, save and return the reply."""
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
            reply = complete([{"role": "system", "content": build_system_prompt(conn, convo)}, *history])
        except Exception as exc:
            db.delete_message(conn, user_msg["id"])  # so a retry doesn't duplicate it
            return jsonify(error=f"Model request failed: {exc}"), 502

        assistant_msg = db.add_message(conn, conversation_id, "assistant", reply)
        return jsonify(
            user_message=user_msg,
            assistant_message=assistant_msg,
            conversation=db.get_conversation(conn, conversation_id),
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
            raw = complete(
                [{"role": "system", "content": REVIEW_PROMPT},
                 {"role": "user", "content": transcript}],
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
        return jsonify(review=saved, progress=progress)

    # ---------- documents ----------

    @app.get("/api/users/<int:user_id>/documents")
    def list_documents(user_id):
        return jsonify(db.list_documents(get_db(), user_id))

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
        return jsonify(db.progress_overview(get_db(), user_id))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(port=5001, debug=True)
