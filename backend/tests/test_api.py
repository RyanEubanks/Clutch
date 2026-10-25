import json

import app as app_module
import db


PASSWORD = "pass1234"


def sign_up(client, username, password=PASSWORD):
    """Make a profile; this also signs the test client in as it."""
    r = client.post("/api/users", json={"username": username, "password": password})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def sign_in(client, username, password=PASSWORD):
    r = client.post("/api/session", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def setup_topic(client, username="alex"):
    user = sign_up(client, username)
    subject = client.post(f"/api/users/{user['id']}/subjects", json={"name": "Calculus"}).get_json()
    topic = client.post(
        f"/api/subjects/{subject['id']}/topics",
        json={"name": "Chain rule", "description": "Derivatives of compositions"},
    ).get_json()
    return user, subject, topic


def test_sign_up_sign_in_and_names_are_case_insensitive(client):
    user = sign_up(client, "Alex")
    assert "password_hash" not in user and user["has_password"] and not user["is_demo"]
    assert client.get("/api/session").get_json()["id"] == user["id"]
    assert client.post("/api/users", json={"username": "alex", "password": "other1"}).status_code == 409
    assert client.post("/api/users", json={"username": "sam", "password": "abc"}).status_code == 400
    assert client.post("/api/users", json={"password": PASSWORD}).status_code == 400

    client.delete("/api/session")
    assert client.get("/api/session").status_code == 401
    assert client.post("/api/session", json={"username": "ALEX", "password": "nope"}).status_code == 401
    assert client.post("/api/session", json={"username": "nobody", "password": PASSWORD}).status_code == 404
    assert sign_in(client, "ALEX")["id"] == user["id"]


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


def test_document_search_and_grouping_fields(client, model):
    user, _, topic = setup_topic(client)
    url = f"/api/users/{user['id']}/documents"
    client.post(url, json={"title": "Lecture 4", "content": "Intro.\nThe chain rule: f'(g(x)) g'(x)",
                           "topic_id": topic["id"]})
    client.post(url, json={"title": "Chain rule worksheet", "content": "1. Differentiate sin(5x)"})
    client.post(url, json={"title": "Limits", "content": "100% of 0/0 forms need work"})

    docs = client.get(url).get_json()
    assert len(docs) == 3 and all("snippet" not in d and "content" not in d for d in docs)
    lecture = next(d for d in docs if d["title"] == "Lecture 4")
    assert lecture["subject_name"] == "Calculus" and lecture["topic_name"] == "Chain rule"

    # Title and content matches, case-insensitive; content hits come with a snippet
    hits = {d["title"]: d for d in client.get(url, query_string={"q": "CHAIN RULE"}).get_json()}
    assert set(hits) == {"Lecture 4", "Chain rule worksheet"}
    assert "chain rule" in hits["Lecture 4"]["snippet"].lower()
    assert hits["Chain rule worksheet"]["snippet"] is None

    # LIKE wildcards in the query are treated as plain text
    assert [d["title"] for d in client.get(url, query_string={"q": "100%"}).get_json()] == ["Limits"]
    assert client.get(url, query_string={"q": "_"}).get_json() == []


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
    other = sign_up(client, "sam")
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
    assert "homework problems" in model.calls[-1]["messages"][0]["content"][1]["text"]

    # Notes use their own prompt, which keeps headings instead of numbering problems
    client.post("/api/homework/read", json={"images": ["data:image/jpeg;base64,AAA"], "kind": "notes"})
    assert "Transcribe the notes" in model.calls[-1]["messages"][0]["content"][1]["text"]
    bad = client.post("/api/homework/read", json={"images": ["data:image/jpeg;base64,AAA"], "kind": "essay"})
    assert bad.status_code == 400

    g = client.post("/api/homework/study-guide", json={"homework": "1. $x^2$"})
    assert g.get_json()["guide"] == "1. $x^2$"


# ---------- lecture recording ----------

def wav_b64(seconds=1.0, rate=16000):
    import base64, io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return base64.b64encode(buf.getvalue()).decode()


def test_lecture_transcribe(client, model):
    model.reply = "  The integral of u dv equals uv minus the integral of v du.  "
    r = client.post("/api/lecture/transcribe", json={"audio": "data:audio/wav;base64," + wav_b64()})
    assert r.status_code == 200
    assert r.get_json()["text"] == "The integral of u dv equals uv minus the integral of v du."
    content = model.calls[-1]["messages"][0]["content"]
    assert content[0]["type"] == "input_audio" and content[0]["input_audio"]["format"] == "wav"
    assert model.calls[-1]["temperature"] == 0

    assert client.post("/api/lecture/transcribe", json={}).status_code == 400
    assert client.post("/api/lecture/transcribe", json={"audio": "not base64!"}).status_code == 400
    not_wav = __import__("base64").b64encode(b"just some bytes here").decode()
    assert client.post("/api/lecture/transcribe", json={"audio": not_wav}).status_code == 400
    too_long = client.post("/api/lecture/transcribe", json={"audio": wav_b64(seconds=120)})
    assert too_long.status_code == 413


def test_lecture_notes_are_made_in_parts(client, model, monkeypatch):
    monkeypatch.setattr(app_module, "LECTURE_PART_CHARS", 100)
    model.reply = "## Notes"
    transcript = "\n\n".join(f"Sentence number {i} about integration by parts." for i in range(8))
    r = client.post("/api/lecture/notes", json={"transcript": transcript})
    data = r.get_json()
    assert r.status_code == 200 and data["parts"] > 1
    assert data["notes"] == "\n\n".join(["## Notes"] * data["parts"])
    prompts = [c["messages"][0]["content"] for c in model.calls[-data["parts"]:]]
    assert "one-line title" in prompts[0] and "do not add a # title" in prompts[1]
    assert all(len(p.split("Transcript (part")[1]) < 100 + 40 for p in prompts)
    assert client.post("/api/lecture/notes", json={"transcript": "  "}).status_code == 400


def test_events_crud_and_validation(client, model):
    user, subject, topic = setup_topic(client)
    url = f"/api/users/{user['id']}/events"
    r = client.post(url, json={"kind": "exam", "title": " Midterm ", "date": "2026-11-12", "time": "09:30",
                               "subject_id": subject["id"], "topic_ids": [topic["id"]], "notes": "Room 4"})
    assert r.status_code == 201
    exam = r.get_json()
    assert exam["title"] == "Midterm" and exam["topic_ids"] == [topic["id"]]
    assert exam["subject_name"] == "Calculus" and exam["done"] is False

    hw = client.post(url, json={"kind": "homework", "title": "Set 4", "date": "2026-11-05"}).get_json()
    assert [e["title"] for e in client.get(url).get_json()] == ["Set 4", "Midterm"]  # by date
    assert [e["title"] for e in client.get(url, query_string={"from": "2026-11-06"}).get_json()] == ["Midterm"]

    done = client.patch(f"/api/events/{hw['id']}", json={"done": True}).get_json()
    assert done["done"] is True and done["title"] == "Set 4"
    moved = client.patch(f"/api/events/{exam['id']}", json={"date": "2026-11-14", "topic_ids": []}).get_json()
    assert moved["date"] == "2026-11-14" and moved["topic_ids"] == [] and moved["time"] == "09:30"

    for bad in ({"kind": "party", "title": "x", "date": "2026-11-01"}, {"kind": "exam", "title": " ", "date": "2026-11-01"},
                {"kind": "exam", "title": "x", "date": "11/01/2026"},
                {"kind": "exam", "title": "x", "date": "2026-11-01", "time": "9am"},
                {"kind": "exam", "title": "x", "date": "2026-11-01", "topic_ids": [9999]}):
        assert client.post(url, json=bad).status_code == 400, bad

    # Another student's topic can't be attached
    _, _, other_topic = setup_topic(client, username="sam")
    sign_in(client, "alex")
    assert client.patch(f"/api/events/{exam['id']}", json={"topic_ids": [other_topic["id"]]}).status_code == 400

    assert client.delete(f"/api/events/{hw['id']}").status_code == 204
    assert client.patch(f"/api/events/{hw['id']}", json={"done": False}).status_code == 404


def test_planner_endpoint(client, model):
    user, _, topic = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "help"})
    client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 3})
    today = __import__("datetime").date.today()
    exam_day = (today + __import__("datetime").timedelta(days=5)).isoformat()
    client.post(f"/api/users/{user['id']}/events",
                json={"kind": "exam", "title": "Unit test", "date": exam_day, "topic_ids": [topic["id"]]})

    r = client.get(f"/api/users/{user['id']}/planner", query_string={"today": today.isoformat(), "tz": 0})
    data = r.get_json()
    assert r.status_code == 200 and data["today"] == today.isoformat()
    item = (data["due"] + data["upcoming"])[0]
    assert item["topic_id"] == topic["id"] and item["test"]["title"] == "Unit test"
    assert item["test"]["days_left"] == 5
    mastery = client.get(f"/api/users/{user['id']}/progress").get_json()[0]["mastery"]
    assert data["tests"][0]["readiness"] == round(mastery, 3) > 0
    m = data["metrics"]
    assert m["streak"] == 1 and m["studied_today"] and m["week"]["sessions"] == 1
    assert client.get(f"/api/users/{user['id']}/planner", query_string={"today": "soon"}).status_code == 400


def test_split_transcript_keeps_everything():
    text = "First paragraph. " * 30 + "\n\n" + "Short one.\n\n" + "x" * 250
    parts = app_module.split_transcript(text, 120)
    assert all(len(p) <= 120 for p in parts)
    assert "".join(parts).replace("\n", "").replace(" ", "") == text.replace("\n", "").replace(" ", "")


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


def test_quiz_report_explains_every_question():
    report = []
    app_module.quiz_questions_from(MATH_QUIZ, report=report)
    statuses = [e["status"] for e in report]
    assert len(report) == 7
    assert statuses.count("dropped") == 1 and "unknown name" in report[3]["error"]
    assert report[0]["status"] == "corrected" and report[0]["result"]["model_said"] == r"$4 \left(3 x + 1\right)^{3}$"
    assert report[5]["kind"] == "concept" and report[5]["status"] == "unchecked"
    bad = []
    assert app_module.quiz_questions_from("not json", report=bad) == []
    assert bad[0]["status"] == "bad_json"


def test_real_addition_quiz_keys_get_fixed():
    """Replay the 15 real (and partly wrong) questions Gemma wrote for 'Addition'."""
    from pathlib import Path
    data = json.loads((Path(__file__).parent / "addition_quiz_questions.json").read_text())
    report = []
    questions = app_module.quiz_questions_from(json.dumps({"questions": data["questions"]}), report=report)
    assert len(questions) == 15
    fixed = [e for e in report if e["status"] == "corrected"]
    assert len(fixed) == 6
    for e in fixed + [e for e in report if e["status"] == "checked"]:
        q = e["result"]
        assert q["verified"] is True
    keys = {e["raw"]["question"]: e["result"]["options"][e["result"]["answer"]]
            for e in report if e["status"] in ("checked", "corrected")}
    assert keys["Calculate the total: $45 + 23$."] == "68"
    assert keys["What is the result of 12 + 7?"] == "19"
    assert keys["What is the result of $38 + 14$?"] == "52"
    # The word problems can't be checked; they stay unchecked and are flagged as numeric.
    word = [e for e in report if e["status"] == "unchecked" and "apples" in e["raw"]["question"]]
    assert len(word) == 2 and all(e["result"]["numeric"] for e in word)


def test_checked_questions_first_unchecked_numbers_last(client, model):
    _, topic, _ = master_topic(client, model)
    model.review = json.dumps({"questions": [
        {"question": "If you have 3 apples and buy 2 more, how many?", "options": ["7", "8", "5", "6"], "answer": 3},
        {"question": "What is addition?", "options": ["Combining", "Splitting", "Sharing", "Halving"], "answer": 0},
        {"question": "What is 12 + 7?", "options": ["19", "21", "18", "20"], "answer": 1},
        {"op": "evaluate", "expr": "45 + 23", "options": ["68", "78", "58", "67"], "answer": 0},
        {"question": "What is the commutative property?", "options": ["a+b=b+a", "a+0=a", "a(b+c)=ab+ac", "a-a=0"], "answer": 0},
        {"question": "What is the sum of 5 and 3?", "options": ["7", "6", "8", "9"], "answer": 0},
        {"question": "If you have 12 apples and get 5 more, how many?", "options": ["16", "15", "18", "17"], "answer": 3},
    ]})
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    assert quiz["math_checker"] is True
    assert [q["verified"] for q in quiz["questions"]] == [True, True, True, False, False]
    assert not any("apples" in q["question"] for q in quiz["questions"])  # unchecked numbers dropped first


def test_health_reports_math_checker(client):
    assert client.get("/api/health").get_json()["math_checker"] is True


# ---------- checking student answers in chat ----------

class ScriptedModel:
    """Returns the given replies in order (the last one repeats), and records prompts."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, messages, temperature=0.2, json_mode=False):
        self.calls.append(messages)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def chat(client, monkeypatch, model, *student_messages):
    monkeypatch.setattr(app_module, "ask_model", model)
    user = sign_up(client, "kris")
    convo = client.post(f"/api/users/{user['id']}/conversations", json={}).get_json()
    out = None
    for text in student_messages:
        out = client.post(f"/api/conversations/{convo['id']}/messages", json={"content": text}).get_json()
    return out


def test_correct_answer_marked_wrong_gets_fixed(client, monkeypatch):
    # Real session: the tutor answered "7 - 2 = 5" with "Not quite."
    model = ScriptedModel("Not quite. Let's look closely at $7 - 2$.")
    out = chat(client, monkeypatch, model, "7 - 2 = 5")
    assert "7 - 2 = 5 is CORRECT" in model.calls[0][0]["content"]
    assert len(model.calls) == 2  # one retry
    assert "math engine checked this" in model.calls[1][-1]["content"]
    reply = out["assistant_message"]["content"]
    assert reply.startswith("Yes, that's right: $7 - 2 = 5$")  # fallback after the retry also failed
    assert out["math_check"][0]["correct"] is True


def test_retry_reply_is_used_when_it_gets_the_verdict_right(client, monkeypatch):
    model = ScriptedModel("Not quite.", "Yes, that's right. 2 - 3 is -1 because you go below zero.")
    out = chat(client, monkeypatch, model, "2-3=-1")
    assert out["assistant_message"]["content"].startswith("Yes, that's right. 2 - 3 is -1")


def test_right_verdict_needs_no_retry(client, monkeypatch):
    model = ScriptedModel("Yes, that's right. Subtracting 4 from 7 leaves 3.")
    chat(client, monkeypatch, model, "7-4=3")
    assert len(model.calls) == 1


def test_wrong_answer_confirmed_by_tutor_gets_fixed_without_leaking(client, monkeypatch):
    model = ScriptedModel("Yes, that's right!")
    out = chat(client, monkeypatch, model, "7 - 2 = 6")
    assert "7 - 2 = 6 is WRONG" in model.calls[0][0]["content"]
    reply = out["assistant_message"]["content"]
    assert reply.startswith("Not quite.") and "5" not in reply


def test_bare_answer_is_checked_against_the_tutors_question(client, monkeypatch):
    # Real session: "5-4", then the tutor asked about it, then the student said "= 1".
    model = ScriptedModel(
        "What happens when you take away 4 from 5?",
        "Not quite.",  # wrong verdict for "= 1"
        "Yes, that's right. 5 take away 4 leaves 1.",
    )
    out = chat(client, monkeypatch, model, "5-4", "= 1")
    assert "wrote the problem 5-4 without an answer" in model.calls[0][0]["content"]
    assert "5-4 = 1 is CORRECT" in model.calls[1][0]["content"]
    assert out["assistant_message"]["content"].startswith("Yes, that's right. 5 take away 4")


def test_non_math_messages_get_no_math_check(client, monkeypatch):
    model = ScriptedModel("Subtraction means taking away. What do you think 5 - 2 is?")
    out = chat(client, monkeypatch, model, "Losing value")
    assert "MATH ENGINE CHECK" not in model.calls[0][0]["content"]
    assert out["math_check"] == [] and len(model.calls) == 1


def test_stateless_chat_checks_answers_too(client, monkeypatch):
    model = ScriptedModel("Not quite.")
    monkeypatch.setattr(app_module, "ask_model", model)
    r = client.post("/api/chat", json={"messages": [
        {"role": "user", "content": "How do I find the limit of (x^2 - 9)/(x - 3) as x approaches 3?"},
        {"role": "assistant", "content": "Try factoring the top."},
        {"role": "user", "content": "I got 6 = 3 + 3"},
    ]}).get_json()
    assert r["reply"].startswith("Yes, that's right")


def test_verdict_detection():
    assert app_module.verdict("Yes, that's right.") is True
    assert app_module.verdict("  Not quite. Look again.") is False
    assert app_module.verdict("What do you think?") is None


# ---------- privacy between profiles ----------

def test_data_needs_sign_in_but_stateless_endpoints_stay_open(client, model):
    user, _, topic = setup_topic(client)
    client.delete("/api/session")
    for url in (f"/api/users/{user['id']}/subjects", f"/api/users/{user['id']}/documents",
                f"/api/users/{user['id']}/planner", f"/api/users/{user['id']}/events"):
        assert client.get(url).status_code == 401, url
    assert client.post(f"/api/topics/{topic['id']}/quiz").status_code == 401
    # Nothing saved, so no sign-in needed (eval_tutor.py and chat_cli.py rely on this)
    assert client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 200
    assert client.get("/api/health").status_code == 200


def test_one_profile_cannot_read_or_change_anothers_data(client, model):
    alex, subject, topic = setup_topic(client, "alex")
    doc = client.post(f"/api/users/{alex['id']}/documents",
                      json={"title": "Private notes", "content": "my notes"}).get_json()
    convo = client.post(f"/api/users/{alex['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    event = client.post(f"/api/users/{alex['id']}/events",
                        json={"kind": "exam", "title": "Midterm", "date": "2026-11-12"}).get_json()

    sign_up(client, "sam")
    for method, url in [
        ("get", f"/api/users/{alex['id']}"), ("get", f"/api/users/{alex['id']}/documents"),
        ("get", f"/api/users/{alex['id']}/conversations"), ("get", f"/api/users/{alex['id']}/planner"),
        ("get", f"/api/documents/{doc['id']}"), ("delete", f"/api/documents/{doc['id']}"),
        ("get", f"/api/conversations/{convo['id']}"), ("delete", f"/api/conversations/{convo['id']}"),
        ("post", f"/api/conversations/{convo['id']}/messages"), ("patch", f"/api/events/{event['id']}"),
        ("delete", f"/api/subjects/{subject['id']}"), ("post", f"/api/topics/{topic['id']}/quiz"),
    ]:
        r = getattr(client, method)(url, json={"content": "x", "done": True})
        assert r.status_code == 404, (method, url, r.status_code)  # looks missing, so ids can't be probed

    sign_in(client, "alex")  # all still there
    assert client.get(f"/api/documents/{doc['id']}").get_json()["content"] == "my notes"
    assert client.get(f"/api/conversations/{convo['id']}").status_code == 200
    assert client.get(f"/api/users/{alex['id']}/subjects").get_json()[0]["name"] == "Calculus"


def test_profile_from_before_passwords_must_set_one(client, tmp_path):
    conn = db.connect(tmp_path / "test.db")
    old = db.create_user(conn, "ry", None)  # as profiles made before passwords existed
    conn.close()
    profiles = client.get("/api/profiles").get_json()
    assert profiles == [{**old, "has_password": False}] and "password_hash" not in profiles[0]

    r = client.post("/api/session", json={"username": "ry", "password": ""})
    assert r.status_code == 409 and r.get_json()["needs_password"]
    assert client.post("/api/session", json={"username": "ry", "new_password": "ab"}).status_code == 400
    assert client.post("/api/session", json={"username": "ry", "new_password": "secret1"}).status_code == 200
    client.delete("/api/session")
    # From now on it's an ordinary password
    assert client.post("/api/session", json={"username": "ry", "new_password": "hijack"}).status_code == 401
    assert sign_in(client, "ry", "secret1")["has_password"]


def test_demo_profile_is_rebuilt_on_every_sign_in(tmp_path, model):
    flask_app = app_module.create_app(tmp_path / "demo.db", demo_account=True)
    client = flask_app.test_client()
    alex = client.get("/api/profiles").get_json()[0]
    assert alex["username"] == "alex" and alex["is_demo"] and not alex["has_password"]

    def snapshot():
        return {
            "subjects": [s["name"] for s in client.get(f"/api/users/{alex['id']}/subjects").get_json()],
            "chats": len(client.get(f"/api/users/{alex['id']}/conversations").get_json()),
            "docs": len(client.get(f"/api/users/{alex['id']}/documents").get_json()),
        }

    assert client.post("/api/session", json={"username": "alex"}).status_code == 200  # no password
    first = snapshot()
    assert first == {"subjects": ["Calculus I", "Linear Algebra"], "chats": 6, "docs": 4}
    calc, linalg = client.get(f"/api/users/{alex['id']}/subjects").get_json()
    assert calc["catalog_id"] == "calculus-1" and linalg["catalog_id"] is None  # verified + custom
    plan = client.get(f"/api/users/{alex['id']}/planner").get_json()
    assert plan["due"] and plan["tests"][0]["title"] == "Calculus Midterm 2" and plan["tests"][0]["days_left"] == 6
    assert plan["metrics"]["streak"] >= 4

    # Changes made during a demo are gone after the next sign-in
    client.post(f"/api/users/{alex['id']}/subjects", json={"name": "Chemistry"})
    client.post(f"/api/users/{alex['id']}/documents", json={"title": "scratch", "content": "x"})
    assert client.post("/api/session", json={"username": "alex"}).status_code == 200
    assert snapshot() == first

    # A real profile is never touched by the demo
    sam = sign_up(client, "sam")
    client.post(f"/api/users/{sam['id']}/subjects", json={"name": "Biology"})
    client.post("/api/session", json={"username": "alex"})
    sign_in(client, "sam")
    assert [s["name"] for s in client.get(f"/api/users/{sam['id']}/subjects").get_json()] == ["Biology"]


# ---------- forgot password ----------

def test_recovery_code_resets_a_forgotten_password(client):
    code = client.post("/api/users", json={"username": "ry", "password": PASSWORD}).get_json()["recovery_code"]
    assert len(code) == 14 and code.count("-") == 2
    assert client.get("/api/session").get_json()["has_recovery"]
    assert "recovery_code" not in client.get("/api/session").get_json()  # shown once, never again
    client.delete("/api/session")

    url = "/api/session/recover"
    assert client.post(url, json={"username": "ry", "recovery_code": "AAAA-BBBB-CCCC",
                                  "new_password": "newpass1"}).status_code == 401
    assert client.post(url, json={"username": "ry", "recovery_code": code,
                                  "new_password": "ab"}).status_code == 400
    # Typed lowercase without dashes still works
    r = client.post(url, json={"username": "ry", "recovery_code": code.replace("-", "").lower(),
                               "new_password": "newpass1"})
    assert r.status_code == 200
    second_code = r.get_json()["recovery_code"]
    assert second_code != code and client.get("/api/session").status_code == 200

    client.delete("/api/session")
    assert client.post("/api/session", json={"username": "ry", "password": PASSWORD}).status_code == 401
    sign_in(client, "ry", "newpass1")
    client.delete("/api/session")
    # A code works once
    assert client.post(url, json={"username": "ry", "recovery_code": code,
                                  "new_password": "again12"}).status_code == 401


def test_first_password_also_gives_a_recovery_code_and_profiles_without_one_get_the_command(client, tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.create_user(conn, "old", None)
    db.create_user(conn, "nocode", __import__("werkzeug.security").security.generate_password_hash(PASSWORD))
    conn.close()
    r = client.post("/api/session", json={"username": "old", "new_password": "secret1"})
    assert r.status_code == 200 and r.get_json()["recovery_code"]
    client.delete("/api/session")

    r = client.post("/api/session/recover", json={"username": "nocode", "recovery_code": "x", "new_password": "secret1"})
    assert r.status_code == 409 and r.get_json()["no_recovery_code"]
    assert "flask --app app reset-password nocode" in r.get_json()["error"]


def test_reset_password_terminal_command(tmp_path, model):
    flask_app = app_module.create_app(tmp_path / "cli.db", demo_account=True)
    client = flask_app.test_client()
    sign_up(client, "ry")
    runner = flask_app.test_cli_runner()
    result = runner.invoke(args=["reset-password", "ry"], input="fresh123\nfresh123\n")
    assert result.exit_code == 0 and "New recovery code" in result.output
    client.delete("/api/session")
    sign_in(client, "ry", "fresh123")
    assert runner.invoke(args=["reset-password", "nobody"], input="x\nx\n").exit_code != 0
    assert runner.invoke(args=["reset-password", "alex"], input="x\nx\n").exit_code != 0  # the demo


# ---------- re-reviewing a session ----------

def review_json(understanding):
    return json.dumps({"understanding": understanding, "summary": "s", "strengths": "a", "gaps": "g"})


def end_session(client, model, user, topic, understanding, confidence=None, convo=None):
    """Study (or reuse) a session and end it with the model rating `understanding`."""
    if convo is None:
        convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
        client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "help"})
    model.review = review_json(understanding)
    body = {} if confidence is None else {"confidence": confidence}
    assert client.post(f"/api/conversations/{convo['id']}/end", json=body).status_code == 200
    return convo


def mastery_and_sessions(client, user):
    row = client.get(f"/api/users/{user['id']}/progress").get_json()[0]
    return row["mastery"], row["sessions_count"]


def test_review_again_replaces_the_sessions_share_instead_of_blending_twice(client, model):
    user, _, topic = setup_topic(client)
    first = end_session(client, model, user, topic, 0.5)
    second = end_session(client, model, user, topic, 0.9)
    assert mastery_and_sessions(client, user) == (0.66, 2)  # 0.6*0.5 + 0.4*0.9

    # Review the latest session again with a lower score: as if it had scored that all along
    end_session(client, model, user, topic, 0.4, convo=second)
    mastery, sessions = mastery_and_sessions(client, user)
    assert sessions == 2 and abs(mastery - (0.6 * 0.5 + 0.4 * 0.4)) < 1e-4

    # Re-review the FIRST session after a later one: its share (it set mastery, then one blend) is 0.6
    end_session(client, model, user, topic, 1.0, convo=first)
    mastery, sessions = mastery_and_sessions(client, user)
    assert sessions == 2 and abs(mastery - (0.6 * 1.0 + 0.4 * 0.4)) < 1e-4

    # Reviewing again with the same rating changes nothing (the old bug nudged it every time)
    end_session(client, model, user, topic, 1.0, convo=first)
    end_session(client, model, user, topic, 1.0, convo=first)
    assert abs(mastery_and_sessions(client, user)[0] - (0.6 * 1.0 + 0.4 * 0.4)) < 1e-4


def test_review_again_counts_confidence_too(client, model):
    user, _, topic = setup_topic(client)
    convo = end_session(client, model, user, topic, 0.8, confidence=1)  # 0.7*0.8 + 0.3*0 = 0.56
    assert abs(mastery_and_sessions(client, user)[0] - 0.56) < 1e-4
    end_session(client, model, user, topic, 0.8, confidence=5, convo=convo)  # 0.7*0.8 + 0.3*1 = 0.86
    assert abs(mastery_and_sessions(client, user)[0] - 0.86) < 1e-4


def test_review_math_in_latex_survives_json(client, model):
    user, _, topic = setup_topic(client)
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "help"})
    # The model forgot to escape its backslashes, as small models often do
    model.review = r'{"understanding": 0.9, "summary": "Found $\frac{d}{dx}\sin(x^2) = 2x\cos(x^2)$", "strengths": "Used $\times$ correctly", "gaps": "none"}'
    review = client.post(f"/api/conversations/{convo['id']}/end", json={}).get_json()["review"]
    assert review["summary"] == r"Found $\frac{d}{dx}\sin(x^2) = 2x\cos(x^2)$"
    assert review["strengths"] == r"Used $\times$ correctly" and review["understanding"] == 0.9
