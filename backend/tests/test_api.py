import json

import app as app_module
import db


def setup_topic(client, username="alex"):
    user = client.post("/api/users", json={"username": username}).get_json()
    subject = client.post(f"/api/users/{user['id']}/subjects", json={"name": "Calculus"}).get_json()
    topic = client.post(
        f"/api/subjects/{subject['id']}/topics",
        json={"name": "Chain rule", "description": "Derivatives of compositions"},
    ).get_json()
    return user, subject, topic


def test_login_is_idempotent_and_case_insensitive(client):
    a = client.post("/api/users", json={"username": "Alex"}).get_json()
    b = client.post("/api/users", json={"username": "alex"}).get_json()
    assert a["id"] == b["id"]
    assert client.post("/api/users", json={}).status_code == 400


def test_subjects_and_topics_nest(client):
    user, subject, topic = setup_topic(client)
    subjects = client.get(f"/api/users/{user['id']}/subjects").get_json()
    assert subjects[0]["name"] == "Calculus"
    assert subjects[0]["topics"][0]["name"] == "Chain rule"
    dup = client.post(f"/api/users/{user['id']}/subjects", json={"name": "Calculus"})
    assert dup.status_code == 409


def test_messages_are_saved_and_history_is_sent(client, model):
    user, _, topic = setup_topic(client)
    convo = client.post(
        f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}
    ).get_json()

    r = client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "How do I differentiate (x^2+1)^3?"})
    assert r.status_code == 200
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "Is it 3(x^2+1)^2?"})

    full = client.get(f"/api/conversations/{convo['id']}").get_json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant", "user", "assistant"]
    assert full["title"].startswith("How do I differentiate")

    last_prompt = model.calls[-1]["messages"]
    assert last_prompt[0]["role"] == "system"
    assert "Calculus / Chain rule" in last_prompt[0]["content"]
    assert len(last_prompt) == 4  # system + 3 prior/current messages


def test_failed_model_call_does_not_keep_the_message(client, model):
    user, _, _ = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={}).get_json()
    model.fail = True
    r = client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "hi"})
    assert r.status_code == 502
    assert client.get(f"/api/conversations/{convo['id']}").get_json()["messages"] == []


def test_topic_documents_go_into_the_prompt(client, model):
    user, _, topic = setup_topic(client)
    client.post(
        f"/api/users/{user['id']}/documents",
        json={"title": "Lecture 4", "content": "d/dx f(g(x)) = f'(g(x)) g'(x)", "topic_id": topic["id"]},
    )
    docs = client.get(f"/api/users/{user['id']}/documents").get_json()
    assert docs[0]["title"] == "Lecture 4" and "content" not in docs[0]

    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "help"})
    assert "Lecture 4" in model.calls[-1]["messages"][0]["content"]


def test_document_budget_is_respected(client, model, monkeypatch):
    monkeypatch.setattr(app_module, "DOC_CHAR_BUDGET", 50)
    user, _, topic = setup_topic(client)
    client.post(f"/api/users/{user['id']}/documents",
                json={"title": "Big", "content": "x" * 500, "topic_id": topic["id"]})
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "help"})
    assert "x" * 51 not in model.calls[-1]["messages"][0]["content"]


def test_ending_session_updates_progress(client, model):
    user, _, topic = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "help me"})

    r = client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 5})
    data = r.get_json()
    assert r.status_code == 200
    assert data["review"]["understanding"] == 0.8
    assert data["review"]["gaps"] == "Forgot the inner derivative"
    # 0.7 * 0.8 + 0.3 * 1.0
    assert abs(data["progress"]["mastery"] - 0.86) < 1e-6
    assert data["progress"]["sessions_count"] == 1

    # Ending the same session again re-scores it but doesn't double count.
    again = client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 5}).get_json()
    assert again["progress"]["sessions_count"] == 1

    # A second, weaker session pulls mastery down.
    model.review = '{"understanding": 0.2, "gaps": "Everything"}'
    convo2 = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo2['id']}/messages", json={"content": "lost"})
    p = client.post(f"/api/conversations/{convo2['id']}/end", json={}).get_json()["progress"]
    assert p["sessions_count"] == 2
    assert p["mastery"] < 0.86

    overview = client.get(f"/api/users/{user['id']}/progress").get_json()
    assert overview[0]["topic_name"] == "Chain rule"
    assert overview[0]["last_gaps"] == "Everything"

    # The tutor now knows about the student's progress.
    convo3 = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo3['id']}/messages", json={"content": "again"})
    assert "Last time they struggled with: Everything" in model.calls[-1]["messages"][0]["content"]


def test_review_survives_bad_model_output(client, model):
    user, _, topic = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "hi"})
    model.review = "sorry, I can't do JSON"
    data = client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 3}).get_json()
    assert data["review"]["understanding"] is None
    assert data["progress"]["mastery"] == 0.5  # confidence 3 of 5 only


def test_invalid_confidence_rejected(client):
    user, _, topic = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "hi"})
    assert client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 9}).status_code == 400


def test_cannot_use_another_users_topic(client):
    _, _, topic = setup_topic(client, "alex")
    other = client.post("/api/users", json={"username": "sam"}).get_json()
    r = client.post(f"/api/users/{other['id']}/conversations", json={"topic_id": topic["id"]})
    assert r.status_code == 404


def test_deleting_subject_cascades(client, tmp_path):
    user, subject, topic = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.delete(f"/api/subjects/{subject['id']}")
    assert client.get(f"/api/users/{user['id']}/subjects").get_json() == []
    # The chat survives, just without a topic.
    assert client.get(f"/api/conversations/{convo['id']}").get_json()["topic_id"] is None


def test_stateless_chat_still_works(client, model):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.get_json()["reply"] == model.reply


def test_parse_review_handles_wrapped_json():
    out = app_module.parse_review('Here you go:\n```json\n{"understanding": 1.7, "gaps": ["a", "b"]}\n```')
    assert out["understanding"] == 1.0
    assert out["gaps"] == "a; b"


def test_session_score():
    assert db.session_score(None, None) is None
    assert db.session_score(0.5, None) == 0.5
    assert db.session_score(None, 1) == 0.0


def test_homework_reaches_saved_chat_prompt(client, model):
    user, _, topic = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages",
                json={"content": "help with 1", "homework": "1. Differentiate $x^3$"})
    system = model.calls[-1]["messages"][0]["content"]
    assert "<homework>\n1. Differentiate $x^3$\n</homework>" in system
    assert "Calculus / Chain rule" in system


def test_stateless_chat_with_homework(client, model):
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "homework": "2. Integrate x"})
    assert "2. Integrate x" in model.calls[-1]["messages"][0]["content"]


def test_homework_read_and_study_guide(client, model):
    model.reply = "1. $x^2$"
    r = client.post("/api/homework/read", json={"images": ["data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"]})
    assert r.get_json()["text"] == "1. $x^2$\n\n1. $x^2$"
    assert model.calls[-1]["temperature"] == 0
    assert client.post("/api/homework/read", json={}).status_code == 400
    g = client.post("/api/homework/study-guide", json={"homework": "1. $x^2$"})
    assert g.get_json()["guide"] == "1. $x^2$"


# ---------- quizzes & badges ----------

QUIZ_JSON = json.dumps({"questions": [
    {"question": f"Q{i}: d/dx of $x^{i}$?", "options": [f"{i}x^{i-1}", "x", "0", f"x^{i}"],
     "answer": 0, "explanation": "Power rule."}
    for i in range(2, 7)
]})


def master_topic(client, model, understanding=0.95):
    """Create a topic and a reviewed session that pushes mastery past the unlock line."""
    user, _, topic = setup_topic(client)
    model.review = json.dumps({"understanding": understanding, "gaps": "none"})
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "I get it"})
    end = client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 5}).get_json()
    return user, topic, end


def correct_answers(client, quiz_id):
    """Look up the right option for each question straight from the database."""
    conn = db.connect(client.application.config["DATABASE_PATH"])
    quiz = db.get_quiz(conn, quiz_id)
    conn.close()
    return [q["answer"] for q in quiz["questions"]]


def test_quiz_locked_until_mastery(client, model):
    user, topic, end = master_topic(client, model, understanding=0.3)
    assert end["quiz_unlocked"] is False
    r = client.post(f"/api/topics/{topic['id']}/quiz")
    assert r.status_code == 403
    rows = client.get(f"/api/users/{user['id']}/progress").get_json()
    assert rows[0]["quiz_unlocked"] is False and rows[0]["quiz_unlock_at"] == 0.8


def test_quiz_hides_answers_and_awards_badge(client, model):
    user, topic, end = master_topic(client, model)
    assert end["quiz_unlocked"] is True

    model.review = QUIZ_JSON  # json_mode calls get this reply
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    assert len(quiz["questions"]) == 5 and quiz["needed"] == 4
    assert all("answer" not in q and "explanation" not in q for q in quiz["questions"])
    assert "Chain rule" in model.calls[-1]["messages"][0]["content"]

    # Asking again returns the same open quiz instead of writing a new one.
    n_calls = len(model.calls)
    again = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    assert again["id"] == quiz["id"] and len(model.calls) == n_calls

    answers = correct_answers(client, quiz["id"])
    answers[0] = (answers[0] + 1) % 4  # one wrong: 4/5 still passes
    r = client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": answers}).get_json()
    assert r["quiz"]["score"] == 4 and r["quiz"]["passed"] is True
    assert r["new_badge"] is True and r["needed"] == 4
    assert r["quiz"]["questions"][0]["explanation"] == "Power rule."

    assert client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": answers}).status_code == 409
    badges = client.get(f"/api/users/{user['id']}/badges").get_json()
    assert badges[0]["topic_name"] == "Chain rule" and badges[0]["score"] == 4
    rows = client.get(f"/api/users/{user['id']}/progress").get_json()
    assert rows[0]["badge_earned_at"] is not None
    # Once the badge is earned, ending sessions no longer nags about the quiz.
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "more"})
    model.review = json.dumps({"understanding": 0.9})
    end = client.post(f"/api/conversations/{convo['id']}/end", json={}).get_json()
    assert end["quiz_unlocked"] is False and end["has_badge"] is True


def test_failed_quiz_gives_no_badge_and_allows_retry(client, model):
    user, topic, _ = master_topic(client, model)
    model.review = QUIZ_JSON
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    wrong = [(a + 1) % 4 for a in correct_answers(client, quiz["id"])]
    r = client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": wrong}).get_json()
    assert r["quiz"]["passed"] is False and r["new_badge"] is False and r["badge"] is None
    retry = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    assert retry["id"] != quiz["id"]


def test_quiz_submit_validates_answers(client, model):
    _, topic, _ = master_topic(client, model)
    model.review = QUIZ_JSON
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    for bad in ([0, 1], [0, 1, 2, 3, 9], "abc", None):
        assert client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": bad}).status_code == 400


def test_bad_quiz_output_retries_then_errors(client, model):
    _, topic, _ = master_topic(client, model)
    model.review = "not json at all"
    n = len(model.calls)
    r = client.post(f"/api/topics/{topic['id']}/quiz")
    assert r.status_code == 502 and len(model.calls) - n == 2


def test_parse_quiz_normalizes_and_shuffles():
    raw = json.dumps({"questions": [
        {"question": "2+2?", "options": ["3", "4", "5", "6"], "answer": "B", "explanation": "x"},
        {"question": "3+3?", "options": ["6", "7", "8", "9"], "answer": "6"},
        {"question": "bad", "options": ["1", "2"], "answer": 0},
    ]})
    out = app_module.parse_quiz(raw, 2)
    assert [q["options"][q["answer"]] for q in out] == ["4", "6"]
    assert app_module.parse_quiz(raw, 3) == []  # not enough valid questions


MATH_QUIZ = json.dumps({"questions": [
    # Model's key is wrong here (says 1); the checker should fix it to 12(3x+1)^3.
    {"op": "diff", "expr": "(3*x+1)**4", "options": ["12*(3*x+1)**3", "4*(3*x+1)**3",
     "12*x*(3*x+1)**3", "(3*x+1)**3"], "answer": 1, "explanation": "wrong"},
    {"op": "limit", "expr": "(x**2-1)/(x-1)", "at": "1", "options": ["0", "2", "1", "oo"], "answer": 0},
    {"op": "evaluate", "expr": "x**2", "at": "3", "options": ["6", "9", "3", "12"], "answer": 1},
    {"op": "diff", "expr": "foo(x)", "options": ["1", "2", "3", "4"], "answer": 0},  # dropped
    {"op": "integrate", "expr": "cos(x)", "options": ["sin(x)", "-sin(x)", "cos(x)", "x*sin(x)"], "answer": 0},
    {"question": "What does the chain rule differentiate?", "options": ["Sums", "Compositions",
     "Products", "Quotients"], "answer": 1, "explanation": "Functions inside functions."},
    {"op": "solve", "expr": "2*x + 1 = 7", "options": ["x = 3", "x = 4", "x = -3", "x = 6"], "answer": 0},
]})


def test_math_quiz_is_checked_and_keys_fixed(client, model):
    user, topic, _ = master_topic(client, model)
    model.review = MATH_QUIZ
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    qs = quiz["questions"]
    assert len(qs) == 5
    assert all(q["verified"] for q in qs)  # verified ones are preferred over the concept one
    assert not any("foo" in q["question"] for q in qs)

    conn = db.connect(client.application.config["DATABASE_PATH"])
    stored = db.get_quiz(conn, quiz["id"])["questions"]
    conn.close()
    first = stored[0]
    assert first["options"][first["answer"]] == r"$12 \left(3 x + 1\right)^{3}$"
    assert first["corrected"] is True
    limit_q = next(q for q in stored if "lim" in q["question"])
    assert limit_q["options"][limit_q["answer"]] == "$2$"


def test_quiz_prompt_keeps_json_examples_intact(client, model):
    _, topic, _ = master_topic(client, model)
    model.review = MATH_QUIZ
    client.post(f"/api/topics/{topic['id']}/quiz")
    prompt = model.calls[-1]["messages"][0]["content"]
    assert '{"op": "diff", "expr": "(3*x+1)**4"' in prompt
    assert "Write a 7-question" in prompt and "Topic: Chain rule" in prompt
