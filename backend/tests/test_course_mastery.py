"""Course mastery (the average over a course's topics) and the course trophy (every topic's
badge, at least COURSE_TROPHY_MIN_TOPICS topics)."""
import json
import sqlite3

import db


def sign_up(client, username="kris"):
    return client.post("/api/users", json={"username": username, "password": "pass1234"}).get_json()


def add_course(client, user, catalog_id, topics):
    """A catalog course with these topics. Returns (subject, {topic name: id})."""
    subject = client.post(f"/api/users/{user['id']}/subjects",
                          json={"catalog_id": catalog_id, "topic": topics[0]}).get_json()
    ids = {topics[0]: subject["topic"]["id"]}
    for name in topics[1:]:
        ids[name] = client.post(f"/api/subjects/{subject['id']}/topics", json={"name": name}).get_json()["id"]
    return subject, ids


def study(client, model, user, topic_id, understanding=0.95):
    model.review = json.dumps({"understanding": understanding})
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic_id}).get_json()
    client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "I get it"})
    client.post(f"/api/conversations/{convo['id']}/end", json={"confidence": 5})


def give_badge(client, user, topic_id):
    conn = db.connect(client.application.config["DATABASE_PATH"])
    conn.execute("INSERT INTO badges (user_id, topic_id) VALUES (?, ?)", (user["id"], topic_id))
    conn.commit()
    conn.close()


def pass_quiz(client, model, user, topic_id):
    """Study the topic to quiz level, then take its (fact bank) quiz and get everything right."""
    study(client, model, user, topic_id)
    model.fail = True  # geography quizzes come from the fact bank, no model needed
    quiz = client.post(f"/api/topics/{topic_id}/quiz").get_json()
    model.fail = False
    conn = db.connect(client.application.config["DATABASE_PATH"])
    answers = [q["answer"] for q in db.get_quiz(conn, quiz["id"])["questions"]]
    conn.close()
    return client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": answers}).get_json()


def course_of(client, user, subject_id):
    return next(s for s in client.get(f"/api/users/{user['id']}/subjects").get_json() if s["id"] == subject_id)


def test_course_mastery_averages_every_topic_counting_unstudied_as_zero(client, model):
    user = sign_up(client)
    subject, ids = add_course(client, user, "geography", ["State capitals", "World capitals", "Continents"])
    study(client, model, user, ids["State capitals"])
    progress = client.get(f"/api/users/{user['id']}/progress").get_json()
    topic_mastery = next(p["mastery"] for p in progress if p["topic_id"] == ids["State capitals"])
    course = course_of(client, user, subject["id"])["course_progress"]
    assert course["topics"] == 3 and course["studied"] == 1 and course["badges"] == 0
    assert abs(course["mastery"] - topic_mastery / 3) < 1e-9
    assert course["trophy_earned_at"] is None and course["min_topics"] == 3


def test_last_badge_in_a_course_wins_the_trophy_once(client, model):
    user = sign_up(client)
    subject, ids = add_course(client, user, "geography", ["State capitals", "World capitals", "Continents"])
    give_badge(client, user, ids["World capitals"])
    give_badge(client, user, ids["Continents"])

    result = pass_quiz(client, model, user, ids["State capitals"])
    assert result["quiz"]["passed"] and result["new_badge"]
    assert result["new_course_trophy"] is True
    assert result["course"]["name"] == "Geography" and result["course"]["badges"] == 3
    assert result["course"]["trophy_earned_at"]
    assert course_of(client, user, subject["id"])["course_progress"]["trophy_earned_at"]
    trophies = client.get(f"/api/users/{user['id']}/trophies").get_json()
    assert [(t["subject_name"], t["topics"]) for t in trophies] == [("Geography", 3)]

    again = pass_quiz(client, model, user, ids["State capitals"])
    assert again["quiz"]["passed"] and again["new_course_trophy"] is False

    # Adding a topic later doesn't take the trophy away
    client.post(f"/api/subjects/{subject['id']}/topics", json={"name": "Rivers"})
    course = course_of(client, user, subject["id"])["course_progress"]
    assert course["topics"] == 4 and course["trophy_earned_at"]


def test_a_course_needs_enough_topics_for_a_trophy(client, model):
    user = sign_up(client)
    subject, ids = add_course(client, user, "geography", ["State capitals", "World capitals"])
    give_badge(client, user, ids["World capitals"])
    result = pass_quiz(client, model, user, ids["State capitals"])
    assert result["new_badge"] and result["new_course_trophy"] is False
    assert result["course"]["badges"] == 2 and result["course"]["topics"] == 2
    assert client.get(f"/api/users/{user['id']}/trophies").get_json() == []


def test_failing_the_last_quiz_wins_nothing(client, model):
    user = sign_up(client)
    _, ids = add_course(client, user, "geography", ["State capitals", "World capitals", "Continents"])
    give_badge(client, user, ids["World capitals"])
    give_badge(client, user, ids["Continents"])
    study(client, model, user, ids["State capitals"])
    model.fail = True
    quiz = client.post(f"/api/topics/{ids['State capitals']}/quiz").get_json()
    conn = db.connect(client.application.config["DATABASE_PATH"])
    wrong = [(q["answer"] + 1) % 4 for q in db.get_quiz(conn, quiz["id"])["questions"]]
    conn.close()
    result = client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": wrong}).get_json()
    assert not result["quiz"]["passed"] and result["new_course_trophy"] is False


def test_deleting_the_only_topic_without_a_badge_completes_the_course(client, model):
    user = sign_up(client)
    subject, ids = add_course(client, user, "geography", ["State capitals", "World capitals", "Continents", "Rivers"])
    for name in ("State capitals", "World capitals", "Continents"):
        give_badge(client, user, ids[name])
    assert not course_of(client, user, subject["id"])["course_progress"]["trophy_earned_at"]
    client.delete(f"/api/topics/{ids['Rivers']}")
    assert course_of(client, user, subject["id"])["course_progress"]["trophy_earned_at"]


def test_trophies_are_private(client, model):
    owner = sign_up(client, "kris")
    client.delete("/api/session")
    sign_up(client, "ryan")
    assert client.get(f"/api/users/{owner['id']}/trophies").status_code == 404


def test_a_version_6_database_gets_the_trophy_table(tmp_path):
    path = tmp_path / "old.db"
    conn = db.connect(path)
    db.init_db(conn)
    conn.execute("DROP TABLE course_badges")
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    db.init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION == 7
    assert conn.execute("SELECT COUNT(*) FROM course_badges").fetchone()[0] == 0
    conn.close()
    sqlite3.connect(path).close()
