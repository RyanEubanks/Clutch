import json
import sys

import pytest

import app as app_module
import db
import regrade_quizzes as rq


def make_quiz(conn, questions, answers=None):
    user = db.get_or_create_user(conn, "kris")
    subject = db.create_subject(conn, user["id"], f"Math {len(questions)}{answers}")
    topic = db.create_topic(conn, subject["id"], "Addition")
    quiz = db.create_quiz(conn, user["id"], topic["id"], questions)
    if answers is not None:
        db.submit_quiz(conn, quiz["id"], answers, app_module.QUIZ_PASS_FRACTION)
    return db.get_quiz(conn, quiz["id"]), user, topic


def concept(question, options, answer):
    return {"question": question, "options": options, "answer": answer, "explanation": "", "verified": False}


WRONG_KEYS = [
    concept("What is the sum of 5 and 3?", ["7", "6", "8", "9"], 0),          # right: C
    concept("Calculate the total: $45 + 23$.", ["78", "67", "77", "68"], 0),  # right: D
    concept("What is addition?", ["Combining", "Splitting", "Sharing", "Halving"], 0),
    concept("If you have 8 apples and buy 5 more, how many?", ["10", "12", "13", "15"], 1),  # right: C
    concept("What is 12 + 7?", ["20", "21", "22", "23"], 1),                  # no right option
]


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = tmp_path / "clutch.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    c = db.connect(path)
    db.init_db(c)
    yield c
    c.close()


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["regrade_quizzes.py", *argv])
    rq.main()


def test_preview_changes_nothing(conn, monkeypatch, capsys):
    quiz, _, _ = make_quiz(conn, WRONG_KEYS, answers=[2, 3, 0, 2, 0])
    run(monkeypatch)
    out = capsys.readouterr().out
    assert "Nothing was saved" in out and "key fixed: 7 -> 8" in out
    assert "UNCHECKED number question" in out and "VOIDED" in out
    assert db.get_quiz(conn, quiz["id"])["score"] == quiz["score"]


def test_apply_fixes_keys_voids_rescores_and_awards_badge(conn, monkeypatch, capsys, tmp_path):
    # Student gave the truly right answers, but the bad keys scored them 1/5.
    quiz, user, topic = make_quiz(conn, WRONG_KEYS, answers=[2, 3, 0, 2, 0])
    assert quiz["score"] == 1 and quiz["passed"] is False
    run(monkeypatch, "--set", f"{quiz['id']}:4=C", "--apply")
    out = capsys.readouterr().out
    assert "Backup saved" in out and list(tmp_path.glob("clutch-backup-*.db"))

    fixed = db.get_quiz(conn, quiz["id"])
    qs = fixed["questions"]
    assert qs[0]["answer"] == 2 and qs[1]["answer"] == 3 and qs[0]["verified"]
    assert qs[3]["answer"] == 2 and qs[3]["key_set_by_hand"] is True
    assert qs[4]["voided"] is True and qs[4]["answer"] is None
    assert fixed["score"] == 5 and fixed["passed"] is True
    badge = db.get_badge(conn, user["id"], topic["id"])
    assert badge and badge["quiz_id"] == quiz["id"] and badge["earned_at"] == fixed["submitted_at"]

    # Running again finds nothing new to do.
    run(monkeypatch)
    assert "Nothing to change" in capsys.readouterr().out


def test_open_quiz_gets_the_right_answer_put_in(conn, monkeypatch):
    quiz, _, _ = make_quiz(conn, WRONG_KEYS)  # not submitted
    run(monkeypatch, "--apply")
    q = db.get_quiz(conn, quiz["id"])["questions"][4]
    assert q["options"][q["answer"]] == "19" and not q.get("voided")


def test_bad_set_arguments_are_refused(conn, monkeypatch):
    quiz, _, _ = make_quiz(conn, WRONG_KEYS, answers=[0, 0, 0, 0, 0])
    for bad in ["nonsense", f"{quiz['id']}:9=A", "999:1=A", f"{quiz['id']}:1=E"]:
        with pytest.raises(SystemExit):
            run(monkeypatch, "--set", bad)


def test_badges_are_never_taken_away(conn, monkeypatch, capsys):
    good = [concept("What is the sum of 1 and 1?", ["2", "3", "4", "5"], 1)] * 1 + [
        concept(f"What is addition {i}?", ["Combining", "Splitting", "Sharing", "Halving"], 0) for i in range(4)]
    quiz, user, topic = make_quiz(conn, good, answers=[1, 0, 0, 0, 0])  # 5/5 with the wrong key
    assert db.get_badge(conn, user["id"], topic["id"])
    run(monkeypatch, "--apply")
    out = capsys.readouterr().out
    assert "4/5" in out
    assert db.get_badge(conn, user["id"], topic["id"])  # still there
