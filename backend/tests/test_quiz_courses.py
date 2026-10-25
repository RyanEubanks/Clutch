"""Quizzes for different kinds of courses: the prompt offers the right task forms, and each
kind of checker is used end to end."""
import json

import db


def mastered_topic(client, model, catalog_id, topic_name):
    user = client.post("/api/users", json={"username": "kris", "password": "pass1234"}).get_json()
    subject = client.post(f"/api/users/{user['id']}/subjects",
                          json={"catalog_id": catalog_id, "topic": topic_name}).get_json()
    topic = subject["topic"]
    model.review = json.dumps({"understanding": 0.95})
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "I get it"})
    client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 5})
    return user, topic


def stored(client, quiz_id):
    conn = db.connect(client.application.config["DATABASE_PATH"])
    quiz = db.get_quiz(conn, quiz_id)
    conn.close()
    return quiz


def test_spanish_quiz_uses_conjugation_tasks(client, model):
    _, topic = mastered_topic(client, model, "spanish-1", "Present tense")
    model.review = json.dumps({"questions": [
        {"op": "conjugate", "verb": "tener", "person": "nosotros", "options": ["tenemos", "tienemos", "tenimos", "tienen"], "answer": 1},
        {"op": "conjugate", "verb": "ser", "person": "yo", "options": ["soy", "eres", "es", "estoy"], "answer": 0},
        {"op": "conjugate", "verb": "poder", "person": "ellos", "options": ["poden", "pueden", "puedan", "podemos"], "answer": 1},
        {"op": "conjugate", "verb": "ir", "person": "tú", "options": ["vas", "va", "voy", "vamos"], "answer": 0},
        {"op": "conjugate", "verb": "hablar", "person": "vosotros", "options": ["habláis", "hablais", "hablan", "hablamos"], "answer": 0},
    ]})
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    prompt = model.calls[-1]["messages"][0]["content"]
    assert "SPANISH CONJUGATION TASK" in prompt and "MATH TASK" not in prompt
    assert all(q["verified"] and q["checked_by"] == "spanish" for q in quiz["questions"])
    assert all("answer" not in q for q in quiz["questions"])
    first = next(q for q in stored(client, quiz["id"])["questions"] if "tener" in q["question"])
    assert first["options"][first["answer"]] == "tenemos"


def test_physics_prompt_lists_the_laws(client, model):
    _, topic = mastered_topic(client, model, "physics", "Energy")
    model.review = json.dumps({"questions": []})
    client.post(f"/api/topics/{topic['id']}/quiz")
    prompt = model.calls[-1]["messages"][0]["content"]
    assert "PHYSICS TASK" in prompt and "kinetic_energy (K kinetic energy" in prompt


def test_geography_quiz_comes_from_the_fact_bank_even_if_the_model_fails(client, model):
    _, topic = mastered_topic(client, model, "geography", "State capitals")
    model.fail = True
    r = client.post(f"/api/topics/{topic['id']}/quiz")
    assert r.status_code == 201
    quiz = r.get_json()
    assert len(quiz["questions"]) == 5
    assert all(q["checked_by"] == "facts" for q in quiz["questions"])
    assert all(q["question"].startswith("What is the capital of") for q in quiz["questions"])


def test_biology_quiz_is_checked_against_notes(client, model):
    user, topic = mastered_topic(client, model, "biology", "Cells and organelles")
    client.post(f"/api/users/{user['id']}/documents", json={
        "title": "Cell notes", "topic_id": topic["id"],
        "content": "Ribosomes build proteins. The nucleus stores the cell's DNA. "
                   "The mitochondria makes energy for the cell."})
    model.review = json.dumps({"questions": [
        {"question": "What do ribosomes do?", "options": ["Build proteins", "Store DNA", "Make energy", "Digest food"],
         "answer": 2, "source": "Ribosomes build proteins."},  # wrong key, fixed from the notes
        {"question": "What stores the cell's DNA?", "options": ["The nucleus", "Ribosomes", "The membrane", "Mitochondria"],
         "answer": 0, "source": "The nucleus stores the cell's DNA."},
        {"question": "What makes energy?", "options": ["Mitochondria", "Nucleus", "Ribosomes", "Membrane"],
         "answer": 0, "source": "Mitochondria are made of sugar."},  # made-up quote: unchecked
        {"question": "Which is a cell part?", "options": ["Golgi body", "Engine", "Wheel", "Battery"], "answer": 0},
        {"question": "Which is bigger?", "options": ["A cell", "An atom", "A proton", "An electron"], "answer": 0},
    ]})
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    prompt = model.calls[-1]["messages"][0]["content"]
    assert '"source"' in prompt and "copied word for word" in prompt
    labels = [q["checked_by"] for q in quiz["questions"]]
    assert labels[:2] == ["notes", "notes"] and labels.count("notes") == 2  # checked first
    full = stored(client, quiz["id"])["questions"]
    ribo = next(q for q in full if "ribosomes" in q["question"])
    assert ribo["options"][ribo["answer"]] == "Build proteins" and ribo["corrected"]
    assert all("source" not in q for q in quiz["questions"])  # hidden until submitted
    answers = [q["answer"] if q["answer"] is not None else 0 for q in full]
    graded = client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": answers}).get_json()
    assert graded["quiz"]["questions"][0]["source"]  # shown after grading


def test_custom_course_quiz_still_offers_math(client, model):
    user = client.post("/api/users", json={"username": "kris", "password": "pass1234"}).get_json()
    s = client.post(f"/api/users/{user['id']}/subjects", json={"name": "My stuff"}).get_json()
    t = client.post(f"/api/subjects/{s['id']}/topics", json={"name": "Things"}).get_json()
    model.review = json.dumps({"understanding": 0.95})
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": t["id"]}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "hi"})
    client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 5})
    model.review = json.dumps({"questions": []})
    client.post(f"/api/topics/{t['id']}/quiz")
    assert "MATH TASK" in model.calls[-1]["messages"][0]["content"]
