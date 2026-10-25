import json
import sqlite3

import courses
import db


# ---------- the catalog itself ----------

def test_catalog_is_well_formed():
    ids = [c["id"] for c in courses.CATALOG]
    assert len(ids) == len(set(ids))
    for c in courses.CATALOG:
        assert c["name"] and c["topics"] and c["keywords"] and c["description"]
        assert c["verification"] in ("verified", "partial", None), c["id"]
        assert c["verified"] == (c["verification"] == "verified")
        # Every course says honestly what is NOT checked.
        assert c["not_checked"], c["id"]
        # Only verified/partial courses may claim checks beyond "against your notes".
        extra = [x for x in c["checks"] if x != courses.NOTES]
        assert bool(extra) == (c["verification"] is not None), c["id"]


def test_verification_levels():
    level = {c["id"]: c["verification"] for c in courses.CATALOG}
    assert {k for k, v in level.items() if v == "verified"} == {
        "elementary-math", "pre-algebra", "algebra-1", "algebra-2", "calculus-1",
        "geometry", "statistics", "physics"}
    assert {k for k, v in level.items() if v == "partial"} == {
        "chemistry", "spanish-1", "english", "us-history", "world-history", "geography",
        "civics", "social-studies"}
    assert level["biology"] is None and level["french-1"] is None


def test_course_families_exist():
    import app as app_module
    for c in courses.CATALOG:
        for fam in c["families"]:
            assert fam in app_module.QUIZ_SECTIONS, (c["id"], fam)
    assert courses.families(None) == ["math"]  # custom courses: same as before


def test_keyword_matches():
    def top(q):
        m = courses.keyword_matches(q)
        return m[0][0]["id"] if m else None
    assert top("Addition") == "elementary-math"
    assert top("subtracion") == "elementary-math"  # typo
    assert top("Spanish") == "spanish-1"
    assert top("chain rule") == "calculus-1"
    assert top("Mitosis") == "biology"
    assert top("Underwater basket weaving") is None
    # "fractions" must not pull in Chemistry just because it looks like "reactions"
    assert "chemistry" not in [c["id"] for c, _ in courses.keyword_matches("fractions")]


def test_matching_topic():
    assert courses.matching_topic(courses.get("elementary-math"), "addition") == "Addition"
    assert courses.matching_topic(courses.get("elementary-math"), "Spanish") is None


# ---------- suggestions ----------

def test_suggest_addition_offers_elementary_math_as_topic(client, model):
    model.review = json.dumps({"matches": [
        {"id": "elementary-math", "as_topic": True, "why": "Addition is part of Elementary Math."},
        {"id": "made-up-course", "as_topic": False, "why": "nope"},  # ignored: not in catalog
    ]})
    r = client.post("/api/courses/suggest", json={"query": "Addition"}).get_json()
    first = r["suggestions"][0]
    assert first["course"]["id"] == "elementary-math" and first["course"]["verified"] is True
    assert first["as_topic"] is True and first["topic"] == "Addition"
    assert all(s["course"]["id"] != "made-up-course" for s in r["suggestions"])
    assert r["source"] == "model+keywords"
    prompt = model.calls[-1]["messages"][0]["content"]
    assert '"Addition"' in prompt and "elementary-math: Elementary Math" in prompt


def test_suggest_uses_the_model_for_things_keywords_miss(client, model):
    model.review = json.dumps({"matches": [{"id": "elementary-math", "as_topic": True,
                                            "why": "Times tables are multiplication."}]})
    r = client.post("/api/courses/suggest", json={"query": "my times table homework"}).get_json()
    assert r["suggestions"][0]["course"]["id"] == "elementary-math"
    assert r["suggestions"][0]["why"] == "Times tables are multiplication."


def test_suggest_falls_back_to_keywords_when_the_model_fails(client, model):
    model.fail = True
    r = client.post("/api/courses/suggest", json={"query": "Spanish"}).get_json()
    assert r["source"] == "keywords"
    first = r["suggestions"][0]
    assert first["course"]["id"] == "spanish-1" and first["course"]["verified"] is False
    assert first["as_topic"] is False


def test_suggest_nothing_for_unknown_courses(client, model):
    model.review = json.dumps({"matches": []})
    r = client.post("/api/courses/suggest", json={"query": "Underwater basket weaving"}).get_json()
    assert r["suggestions"] == []
    assert client.post("/api/courses/suggest", json={}).status_code == 400


# ---------- creating subjects from the catalog ----------

def login(client):
    return client.post("/api/users", json={"username": "kris"}).get_json()


def test_create_catalog_course_with_topic_and_reuse_it(client):
    user = login(client)
    r = client.post(f"/api/users/{user['id']}/subjects",
                    json={"catalog_id": "elementary-math", "topic": "Addition"})
    assert r.status_code == 201
    s = r.get_json()
    assert s["name"] == "Elementary Math" and s["verified"] is True and s["topic"]["name"] == "Addition"
    # Adding "Subtraction" through the same course reuses it instead of a 409 duplicate.
    r2 = client.post(f"/api/users/{user['id']}/subjects",
                     json={"catalog_id": "elementary-math", "topic": "Subtraction"})
    assert r2.status_code == 200 and r2.get_json()["id"] == s["id"]
    # And the same topic again doesn't duplicate it.
    client.post(f"/api/users/{user['id']}/subjects", json={"catalog_id": "elementary-math", "topic": "addition"})
    subjects = client.get(f"/api/users/{user['id']}/subjects").get_json()
    assert len(subjects) == 1
    assert sorted(t["name"] for t in subjects[0]["topics"]) == ["Addition", "Subtraction"]
    assert subjects[0]["course"]["checks"]


def test_custom_course_is_not_verified(client):
    user = login(client)
    s = client.post(f"/api/users/{user['id']}/subjects", json={"name": "Underwater basket weaving"}).get_json()
    assert s["verified"] is False and s["course"] is None
    assert client.post(f"/api/users/{user['id']}/subjects", json={"catalog_id": "nope"}).status_code == 400


def test_progress_rows_say_if_verified(client):
    user = login(client)
    client.post(f"/api/users/{user['id']}/subjects", json={"catalog_id": "calculus-1", "topic": "Limits"})
    s = client.post(f"/api/users/{user['id']}/subjects", json={"name": "Spanish stuff"}).get_json()
    client.post(f"/api/subjects/{s['id']}/topics", json={"name": "Verbs"})
    rows = {r["topic_name"]: r for r in client.get(f"/api/users/{user['id']}/progress").get_json()}
    assert rows["Limits"]["verified"] is True and rows["Verbs"]["verified"] is False


# ---------- migration ----------

def test_v3_database_gets_catalog_id_column(tmp_path):
    """A database from before v4 (no catalog_id) is upgraded in place, keeping its data."""
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                            display_name TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE subjects (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id)
                               ON DELETE CASCADE, name TEXT NOT NULL,
                               created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE (user_id, name));
        INSERT INTO users (username) VALUES ('kris');
        INSERT INTO subjects (user_id, name) VALUES (1, 'Addition');
        PRAGMA user_version = 3;
    """)
    old.close()
    conn = db.connect(path)
    db.init_db(conn)
    assert "catalog_id" in db._columns(conn, "subjects")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    row = conn.execute("SELECT name, catalog_id FROM subjects").fetchone()
    assert tuple(row) == ("Addition", None)
    db.init_db(conn)  # running again is harmless


def test_existing_courses_with_catalog_names_get_linked(tmp_path):
    import app as app_module
    path = tmp_path / "c.db"
    conn = db.connect(path); db.init_db(conn)
    user = db.get_or_create_user(conn, "kris")
    db.create_subject(conn, user["id"], "elementary math")
    db.create_subject(conn, user["id"], "Calculus")  # not an exact name: left alone
    conn.close()
    app_module.create_app(path)
    conn = db.connect(path)
    links = dict(conn.execute("SELECT name, catalog_id FROM subjects").fetchall())
    assert links == {"elementary math": "elementary-math", "Calculus": None}


def test_link_and_unlink_a_course(client):
    user = login(client)
    s = client.post(f"/api/users/{user['id']}/subjects", json={"name": "Calculus"}).get_json()
    linked = client.patch(f"/api/subjects/{s['id']}", json={"catalog_id": "calculus-1"}).get_json()
    assert linked["name"] == "Calculus" and linked["verified"] is True
    assert linked["course"]["name"] == "Calculus I"
    unlinked = client.patch(f"/api/subjects/{s['id']}", json={"catalog_id": None}).get_json()
    assert unlinked["verified"] is False
    assert client.patch(f"/api/subjects/{s['id']}", json={"catalog_id": "nope"}).status_code == 400
