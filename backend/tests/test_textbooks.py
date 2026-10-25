"""OpenStax textbooks: importing a book's source files, searching it, and using it in quizzes
and chat. Uses a tiny made-up book laid out like a real osbooks-* repo (no download)."""
import json

import pytest

import app as app_module
import db
import textbooks

NS = 'xmlns="http://cnx.rice.edu/cnxml"'


def mcq(stem, options, letter, link=""):
    items = "".join(f"<item>{o}</item>" for o in options)
    return (f'<exercise><problem><para>{stem}{link}</para><list number-style="lower-alpha">{items}</list>'
            f"</problem><solution><para>{letter}</para></solution></exercise>")


def term(word, meaning):
    return f"<definition><term>{word}</term><meaning>{meaning}</meaning></definition>"


MODULES = {
    "m1": ("Introduction", "<para>Cells come from other cells. This chapter is about how one cell becomes two "
                           "and how the process is controlled.</para>", "", ""),
    "m2": ("Cell Division", "<para>Before a cell divides it copies its DNA. Each chromosome then has two "
                            "sister chromatids joined at the centromere.</para>",
           mcq("Sister chromatids are joined at the", ["centromere", "nucleolus", "ribosome", "cell wall"], "a")
           + mcq("Which structure is labeled B?", ["nucleus", "spindle", "cytoplasm", "membrane"], "b",
                 link='<link target-id="fig-ch10_01"/>')
           + mcq("The cell's genome is stored mostly in the", ["nucleus", "lysosome", "vacuole", "spindle",
                                                                "golgi"], "a"),
           term("centromere", "the region where sister chromatids are joined")
           + term("chromatid", "one of two identical copies of a duplicated chromosome")),
    "m3": ("The Cell Cycle", "<section><title>Mitosis</title><para>During mitosis the duplicated chromosomes "
                             "line up and the spindle pulls the sister chromatids to opposite poles, so each "
                             "new nucleus gets one full set of chromosomes.</para></section>"
                             "<para>Cytokinesis then splits the cytoplasm into two daughter cells.</para>",
           mcq("During which phase do chromosomes line up in the middle of the cell?",
               ["metaphase", "anaphase", "telophase", "interphase"], "a")
           + mcq("Cytokinesis divides the", ["cytoplasm", "nucleus", "DNA", "centromere"], "a")
           + mcq("Interphase is the stage when a cell", ["grows and copies its DNA", "splits in two",
                                                          "forms a spindle", "dissolves its nucleus"], "a"),
           term("mitosis", "the division of the nucleus that gives each daughter cell the same chromosomes")
           + term("cytokinesis", "the division of the cytoplasm that makes two daughter cells")
           + term("interphase", "the stage of the cell cycle in which the cell grows and copies its DNA")),
    "m4": ("Introduction", "<para>Meiosis makes sperm and egg cells. Unlike mitosis, mitosis, mitosis, it "
                           "halves the number of chromosomes, which mitosis does not.</para>", "", ""),
    "m5": ("The Process of Meiosis", "<para>Meiosis has two rounds of division and produces four cells, "
                                     "each with half the chromosomes of the parent cell.</para>",
           mcq("How many cells does meiosis produce?", ["four", "two", "one", "eight"], "a"),
           term("meiosis", "cell division that halves the number of chromosomes")),
    "m6": ("Introduction", "<para>Ecology studies how living things interact with each other and with water, "
                           "air and soil in their environment.</para>", "", ""),
}


def mastered_topic(client, model, catalog_id, topic_name):
    """A signed-in student with a topic at quiz-ready mastery."""
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


def module_xml(title, content, exercises, glossary):
    gloss = f"<glossary>{glossary}</glossary>" if glossary else ""
    return (f"<document {NS}><title>{title}</title><content>{content}{exercises}</content>{gloss}</document>")


def make_repo(root, license_path="by-nc-sa/4.0"):
    repo = root / "osbooks-biology-bundle"
    (repo / "META-INF").mkdir(parents=True)
    (repo / "collections").mkdir()
    (repo / "META-INF" / "books.xml").write_text(
        '<container xmlns="https://openstax.org/namespaces/book-container" version="1">'
        '<book slug="biology-2e" href="../collections/biology-2e.collection.xml"/></container>')

    def chapter(title, modules):
        mods = "".join(f'<col:module document="{m}"/>' for m in modules)
        return f"<col:subcollection><md:title>{title}</md:title><col:content>{mods}</col:content></col:subcollection>"

    (repo / "collections" / "biology-2e.collection.xml").write_text(
        '<col:collection xmlns="http://cnx.rice.edu/collxml" xmlns:md="http://cnx.rice.edu/mdml" '
        'xmlns:col="http://cnx.rice.edu/collxml"><metadata><md:title>Biology 2e</md:title>'
        f'<md:license url="http://creativecommons.org/licenses/{license_path}/">CC</md:license></metadata>'
        '<col:content><col:module document="m0"/>'  # preface, outside any chapter
        + chapter("Cell Reproduction", ["m1", "m2", "m3"])
        + chapter("Meiosis and Sexual Reproduction", ["m4", "m5"])
        + chapter("Ecology and the Biosphere", ["m6"])
        + "</col:content></col:collection>")
    for module, parts in MODULES.items():
        (repo / "modules" / module).mkdir(parents=True)
        (repo / "modules" / module / "index.cnxml").write_text(module_xml(*parts))
    return repo


@pytest.fixture
def book_db(tmp_path, monkeypatch):
    """A textbook database with the made-up Biology 2e imported."""
    path = tmp_path / "textbooks.db"
    monkeypatch.setenv("TEXTBOOK_DB_PATH", str(path))
    conn = textbooks.connect()
    textbooks.store_book(conn, textbooks.read_book(make_repo(tmp_path), "biology-2e"))
    yield conn
    conn.close()


def test_reading_a_book_numbers_sections_and_keeps_the_license(tmp_path):
    book = textbooks.read_book(make_repo(tmp_path), "biology-2e")
    assert book["title"] == "Biology 2e" and book["license"] == "CC BY-NC-SA 4.0"
    assert book["url"] == "https://openstax.org/books/biology-2e"
    numbers = [(s["number"], s["chapter"], s["title"]) for s in book["sections"]]
    assert numbers == [
        (None, "Cell Reproduction", "Introduction"), ("1.1", "Cell Reproduction", "Cell Division"),
        ("1.2", "Cell Reproduction", "The Cell Cycle"),
        (None, "Meiosis and Sexual Reproduction", "Introduction"),
        ("2.1", "Meiosis and Sexual Reproduction", "The Process of Meiosis"),
        (None, "Ecology and the Biosphere", "Introduction"),
    ]
    division = book["sections"][1]
    # The figure question and the 5-option one are skipped: they can't be shown as asked.
    assert division["questions"] == [("Sister chromatids are joined at the",
                                      ["centromere", "nucleolus", "ribosome", "cell wall"], 0)]
    assert ("centromere", "the region where sister chromatids are joined") in division["terms"]
    assert all("Sister chromatids are joined at the" not in text for _, text in division["passages"])


def test_cc_by_license_is_read_from_the_book(tmp_path):
    assert textbooks.read_book(make_repo(tmp_path, "by/4.0"), "biology-2e")["license"] == "CC BY 4.0"


def test_search_finds_the_topic_and_ignores_unrelated_queries(book_db):
    hits = textbooks.search(book_db, ["biology-2e"], "mitosis spindle")
    assert hits and hits[0]["label"] == "1.2 The Cell Cycle" and hits[0]["heading"] == "Mitosis"
    assert textbooks.search(book_db, ["biology-2e"], "Underwater basket weaving") == []
    assert textbooks.search(book_db, ["other-book"], "mitosis") == []


def test_quiz_comes_from_the_chapter_that_teaches_the_topic(book_db):
    # The meiosis intro says "mitosis" more often, but mitosis is taught (and defined) in Cell Reproduction.
    assert textbooks.best_chapters(book_db, ["biology-2e"], "Mitosis")[0] == ("biology-2e", "Cell Reproduction")
    qs = textbooks.quiz_questions(book_db, ["biology-2e"], "Mitosis", 5, seed=3)
    assert len(qs) == 5 and all(q["checked_by"] == "textbook" and q["verified"] for q in qs)
    assert all(q["source"].startswith("OpenStax Biology 2e, section ") for q in qs)
    assert all(q["source_license"] == "CC BY-NC-SA 4.0" for q in qs)
    keys = {q["question"]: q["options"][q["answer"]] for q in qs}
    if "Cytokinesis divides the" in keys:
        assert keys["Cytokinesis divides the"] == "cytoplasm"
    for q in qs:
        if q["question"].startswith("Which term means"):
            assert "glossary" in q["explanation"] and len(set(q["options"])) == 4
    assert textbooks.quiz_questions(book_db, ["biology-2e"], "Underwater basket weaving", 5) == []


def test_biology_quiz_uses_the_textbook_without_asking_the_model(client, model, book_db):
    _, topic = mastered_topic(client, model, "biology", "Mitosis")
    calls = len(model.calls)
    r = client.post(f"/api/topics/{topic['id']}/quiz")
    assert r.status_code == 201
    quiz = r.get_json()
    assert len(model.calls) == calls  # no model call: every question came from the book
    assert all(q["checked_by"] == "textbook" for q in quiz["questions"])
    assert all("source" not in q and "answer" not in q for q in quiz["questions"])
    saved = stored(client, quiz["id"])["questions"]
    assert all(q["source_url"] == "https://openstax.org/books/biology-2e" for q in saved)


def test_textbook_questions_go_first_and_the_model_fills_the_rest(client, model, book_db, monkeypatch):
    monkeypatch.setattr(app_module, "QUIZ_QUESTIONS", 8)
    _, topic = mastered_topic(client, model, "biology", "Meiosis")
    model.review = json.dumps({"questions": [
        {"question": f"Made-up question {i}?", "options": ["w", "x", "y", "z"], "answer": 0}
        for i in range(8)]})
    quiz = client.post(f"/api/topics/{topic['id']}/quiz").get_json()
    kinds = [q["checked_by"] for q in quiz["questions"]]
    n_book = kinds.count("textbook")
    assert n_book >= 1 and kinds[:n_book] == ["textbook"] * n_book
    assert len(kinds) == 8 and None in kinds  # the rest are the model's (unchecked) questions


def test_chat_gets_matching_passages_with_their_section(client, model, book_db):
    user, topic = mastered_topic(client, model, "biology", "Mitosis")
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    r = client.post(f"/api/conversations/{convo['id']}/messages",
                    json={"content": "What does the spindle do?"}).get_json()
    system = model.calls[-1]["messages"][0]["content"]
    assert "Biology 2e (OpenStax), section 1.2 The Cell Cycle" in system
    assert "spindle pulls the sister chromatids" in system
    assert r["textbook_sources"][0] == {"book": "Biology 2e", "section": "1.2 The Cell Cycle",
                                        "license": "CC BY-NC-SA 4.0", "slug": "biology-2e",
                                        "url": "https://openstax.org/books/biology-2e"}
    books = client.get(f"/api/conversations/{convo['id']}").get_json()["textbooks"]
    assert [b["title"] for b in books] == ["Biology 2e"]
    assert "by OpenStax (CC BY-NC-SA 4.0)" in books[0]["attribution"]


def test_notes_come_before_the_textbook_in_the_budget(client, model, book_db, monkeypatch):
    monkeypatch.setattr(app_module, "DOC_CHAR_BUDGET", 400)
    user, topic = mastered_topic(client, model, "biology", "Mitosis")
    client.post(f"/api/users/{user['id']}/documents",
                json={"title": "My notes", "content": "x" * 400, "topic_id": topic["id"]})
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    r = client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "spindle?"}).get_json()
    assert "OpenStax" not in model.calls[-1]["messages"][0]["content"]
    assert r["textbook_sources"] == []


def test_an_imported_book_makes_a_course_partly_verified(client, book_db):
    biology = next(c for c in client.get("/api/courses").get_json() if c["id"] == "biology")
    assert biology["verification"] == "partial"
    assert any("Biology 2e (OpenStax, CC BY-NC-SA 4.0)" in c for c in biology["checks"])
    assert biology["textbooks"][0]["slug"] == "biology-2e"
    algebra = next(c for c in client.get("/api/courses").get_json() if c["id"] == "algebra-1")
    assert algebra["verification"] == "verified" and algebra["textbooks"] == []
    listed = client.get("/api/textbooks").get_json()  # open: no sign-in needed
    assert [b["slug"] for b in listed] == ["biology-2e"] and listed[0]["counts"]["questions"] == 5


def test_everything_works_without_a_textbook_database(client, model, tmp_path, monkeypatch):
    monkeypatch.setenv("TEXTBOOK_DB_PATH", str(tmp_path / "missing" / "textbooks.db"))
    assert client.get("/api/textbooks").get_json() == []
    biology = next(c for c in client.get("/api/courses").get_json() if c["id"] == "biology")
    assert biology["verification"] is None and biology["textbooks"] == []
    user, topic = mastered_topic(client, model, "biology", "Mitosis")
    convo = client.post(f"/api/users/{user['id']}/conversations", json={"topic_id": topic["id"]}).get_json()
    r = client.post(f"/api/conversations/{convo['id']}/messages", json={"content": "Hi"}).get_json()
    assert r["textbook_sources"] == []
    assert not (tmp_path / "missing").exists()  # the app never creates the textbook database


# ---------- importing from the app ----------

@pytest.fixture
def importer(tmp_path, monkeypatch):
    """No textbook database yet, and a fake download that returns the made-up book."""
    monkeypatch.setenv("TEXTBOOK_DB_PATH", str(tmp_path / "textbooks.db"))
    monkeypatch.setattr(app_module, "_imports", {})
    repo = make_repo(tmp_path)
    downloads = []

    def fake_download(name, log=print):
        downloads.append(name)
        return repo

    monkeypatch.setattr(textbooks, "download", fake_download)
    return downloads


def wait_for_import(course_id):
    app_module._import_threads[course_id].join(timeout=10)


def course_card(client, user, catalog_id):
    return next(s for s in client.get(f"/api/users/{user['id']}/subjects").get_json()
                if s["catalog_id"] == catalog_id)


def test_a_course_with_a_book_offers_it_and_one_click_imports_it(client, model, importer):
    user, _ = mastered_topic(client, model, "biology", "Mitosis")
    card = course_card(client, user, "biology")
    assert card["course"]["textbook_import"] == {
        "available": [{"slug": "biology-2e", "title": "Biology 2e"}], "state": None, "error": None}
    assert card["verification"] is None

    r = client.post("/api/textbooks/import", json={"course_id": "biology"})
    assert r.status_code == 202 and r.get_json()["state"] == "running"
    wait_for_import("biology")
    assert importer == ["osbooks-biology-bundle"]
    assert client.get("/api/textbooks/import/biology").get_json() == {
        "available": [], "state": "done", "error": None}

    card = course_card(client, user, "biology")  # no restart needed
    assert card["verification"] == "partial"
    assert [b["slug"] for b in card["course"]["textbooks"]] == ["biology-2e"]
    assert card["course"]["textbook_import"]["available"] == []
    # Asking again doesn't download again.
    again = client.post("/api/textbooks/import", json={"course_id": "biology"})
    assert again.status_code == 200 and again.get_json()["state"] == "done" and importer == ["osbooks-biology-bundle"]


def test_a_failed_download_is_reported_and_can_be_retried(client, model, importer, monkeypatch):
    def offline(name, log=print):
        raise textbooks.ImportFailed("Download failed. Check the internet connection and try again.")

    monkeypatch.setattr(textbooks, "download", offline)
    user, _ = mastered_topic(client, model, "biology", "Mitosis")
    client.post("/api/textbooks/import", json={"course_id": "biology"})
    wait_for_import("biology")
    status = client.get("/api/textbooks/import/biology").get_json()
    assert status["state"] == "failed" and "internet" in status["error"]
    assert status["available"] == [{"slug": "biology-2e", "title": "Biology 2e"}]  # still offered
    assert course_card(client, user, "biology")["course"]["textbook_import"]["state"] == "failed"


def test_courses_without_a_book_offer_nothing_and_bad_requests_are_refused(client, model, importer):
    user, _ = mastered_topic(client, model, "spanish-1", "Present tense")
    assert course_card(client, user, "spanish-1")["course"]["textbook_import"]["available"] == []
    assert client.post("/api/textbooks/import", json={"course_id": "spanish-1"}).status_code == 404
    assert client.post("/api/textbooks/import", json={"course_id": "../../etc"}).status_code == 404
    assert client.get("/api/textbooks/import/nope").status_code == 404
    client.delete("/api/session")
    assert client.post("/api/textbooks/import", json={"course_id": "biology"}).status_code == 401
    assert importer == []


def test_in_app_import_can_be_turned_off(client, model, importer, monkeypatch):
    monkeypatch.setattr(app_module, "ALLOW_TEXTBOOK_IMPORT", False)
    user, _ = mastered_topic(client, model, "biology", "Mitosis")
    assert course_card(client, user, "biology")["course"]["textbook_import"]["available"] == []
    assert client.post("/api/textbooks/import", json={"course_id": "biology"}).status_code == 403
    assert importer == []


def test_command_line_import_from_a_downloaded_repo(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TEXTBOOK_DB_PATH", str(tmp_path / "cli.db"))
    conn = textbooks.connect()
    counts = textbooks.import_book(conn, "biology", "osbooks-biology-bundle", "biology-2e",
                                   source=make_repo(tmp_path))
    assert counts["questions"] == 5 and textbooks.books_for_course(conn, "biology")[0]["title"] == "Biology 2e"
    assert "5 review questions" in capsys.readouterr().out
    conn.close()
