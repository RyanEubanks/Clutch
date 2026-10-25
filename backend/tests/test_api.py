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
