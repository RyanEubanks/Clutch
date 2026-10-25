"""Re-check saved quizzes, fix wrong answer keys, and regrade them.

Use this when quizzes were written before a checker fix (or while SymPy wasn't
installed), or to correct a key by hand. It changes nothing unless you pass --apply,
and --apply saves a backup of the database first.

Usage (from backend/, with the venv active; Flask can keep running):
    python regrade_quizzes.py                       # preview the changes only
    python regrade_quizzes.py --apply               # back up, then save the fixes
    python regrade_quizzes.py --set 4:5=C           # also set quiz 4, question 5's key to C
    python regrade_quizzes.py --set 4:5=C --apply   # (--set can be repeated)

Question numbers (1-5) and option letters (A-D) are the ones shown in the quiz.

What happens to each question that wasn't already math-checked:
  - The arithmetic checker finds the right option -> the key points to it.
  - No option is right, quiz not submitted yet   -> the right answer replaces the bad option.
  - No option is right, quiz already submitted   -> the question is voided: everyone gets
                                                    credit, since no right answer was offered.
Submitted quizzes are then rescored from the answers the student actually gave, and a
badge is awarded (dated when the quiz was submitted) if the new score passes.
Badges are never taken away; if a score drops below passing it is only reported.
"""
import argparse
import json
import math
import re
import sqlite3
import sys
from datetime import datetime

import app  # same settings, database path and checker as the running app
import db

LETTERS = "ABCD"


def parse_overrides(values):
    """['4:5=C'] -> {(4, 4): 2}  (quiz id, 0-based question, 0-based option)."""
    overrides = {}
    for value in values or []:
        m = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*=\s*([A-Da-d])\s*", value)
        if not m:
            raise SystemExit(f"--set {value!r}: use QUIZ:QUESTION=LETTER, e.g. 4:5=C")
        overrides[(int(m.group(1)), int(m.group(2)) - 1)] = LETTERS.index(m.group(3).upper())
    return overrides


def plan_quiz(quiz, overrides, checked):
    """Work out the fixed questions and new score for one quiz. Returns (questions, notes)."""
    submitted = quiz["submitted_at"] is not None
    questions = [dict(q) for q in quiz["questions"]]
    notes = []
    for i, q in enumerate(questions):
        label = f"Q{i + 1}"
        old = q.get("answer")
        old_text = q["options"][old] if isinstance(old, int) else "(none)"

        if (quiz["id"], i) in overrides:
            new = overrides[(quiz["id"], i)]
            q.update(answer=new, key_set_by_hand=True, voided=False)
            notes.append(f"{label} key set by hand: {old_text} -> {q['options'][new]}")
            continue
        if q.get("verified") or q.get("voided"):
            continue

        result, error = checked.get((quiz["id"], i), (None, "not checked"))
        if result is None:
            if q.get("numeric", app.numeric_options(q["options"])):
                notes.append(f"{label} UNCHECKED number question, review by hand "
                             f"(key {old_text}): {q['question'][:70]}")
            continue
        same_options = result["options"] == [str(o).strip() for o in q["options"]]
        if same_options:
            q.update(answer=result["answer"], verified=True, corrected=result["corrected"],
                     explanation=result["explanation"])
            if result["answer"] != old:
                notes.append(f"{label} key fixed: {old_text} -> {q['options'][result['answer']]}"
                             f"  ({q['question'][:60]})")
        elif not submitted:
            q.update(result)
            q["numeric"] = True
            notes.append(f"{label} no option was right; replaced it with "
                         f"{result['options'][result['answer']]}  ({q['question'][:60]})")
        else:
            truth = result["options"][result["answer"]]
            q.update(voided=True, answer=None, verified=True,
                     explanation=f"None of the options was right (the answer is {truth}), "
                                 f"so everyone gets credit for this question.")
            notes.append(f"{label} VOIDED: no option was right (answer is {truth}); "
                         f"everyone gets credit  ({q['question'][:60]})")
    return questions, notes


def score(questions, answers):
    return sum(1 for q, a in zip(questions, answers) if q.get("voided") or a == q.get("answer"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="save the changes (after a backup)")
    parser.add_argument("--set", action="append", metavar="QUIZ:QUESTION=LETTER",
                        help="set an answer key by hand, e.g. 4:5=C (repeatable)")
    args = parser.parse_args()
    overrides = parse_overrides(args.set)

    if app.mathcheck is None:
        print("WARNING: sympy is not installed, so only --set fixes can be made. "
              "Run: pip install -r requirements.txt\n")

    path = db.db_path()
    conn = db.connect(path)
    db.init_db(conn)
    quizzes = [db.get_quiz(conn, r["id"]) for r in conn.execute("SELECT id FROM quizzes ORDER BY id")]
    by_id = {q["id"]: q for q in quizzes}
    for (qid, i), option in overrides.items():
        if qid not in by_id:
            raise SystemExit(f"--set: there is no quiz {qid}")
        if not 0 <= i < len(by_id[qid]["questions"]):
            raise SystemExit(f"--set: quiz {qid} has no question {i + 1}")
        if option >= len(by_id[qid]["questions"][i]["options"]):
            raise SystemExit(f"--set: quiz {qid} question {i + 1} has no option {LETTERS[option]}")

    # Check every unchecked question with number options in one batch (worker processes).
    to_check = [(q["id"], i, question) for q in quizzes for i, question in enumerate(q["questions"])
                if not question.get("verified") and not question.get("voided")
                and isinstance(question.get("answer"), int)]
    results = (app.mathcheck.check_questions([c[2] for c in to_check], arithmetic=True)
               if app.mathcheck and to_check else [])
    checked = {(qid, i): r for (qid, i, _), r in zip(to_check, results)}

    needed_fraction = app.QUIZ_PASS_FRACTION
    changes = []
    awarded = set()  # (user, topic) badges awarded in this run
    print(f"Database: {path}\n")
    for quiz in quizzes:
        questions, notes = plan_quiz(quiz, overrides, checked)
        submitted = quiz["submitted_at"] is not None
        needed = math.ceil(needed_fraction * quiz["total"] - 1e-9)
        new_score = score(questions, quiz["answers"]) if submitted else None
        new_passed = submitted and new_score >= needed
        header = (f"Quiz {quiz['id']} [{quiz['topic_name']}] "
                  + (f"score {quiz['score']}/{quiz['total']}" if submitted else "not submitted yet"))
        if new_score is not None and new_score != quiz["score"]:
            header += f" -> {new_score}/{quiz['total']}"
            header += " (PASS)" if new_passed else " (not passing)"
        print(header)
        for note in notes:
            print("   " + note)
        badge = db.get_badge(conn, quiz["user_id"], quiz["topic_id"])
        who = (quiz["user_id"], quiz["topic_id"])
        award = bool(new_passed and badge is None and who not in awarded)
        if award:
            awarded.add(who)
            print(f"   -> earns the {quiz['topic_name']} badge")
        if submitted and quiz["passed"] and not new_passed:
            print("   note: this quiz no longer passes; its badge (if any) is kept")
        if not notes and not award:
            print("   no changes")
        if questions != quiz["questions"] or new_score != quiz["score"] or award:
            changes.append((quiz, questions, new_score, new_passed, award))
        print()

    if not changes:
        print("Nothing to change.")
        return
    if not args.apply:
        print(f"{len(changes)} quiz(zes) would change. Nothing was saved. "
              f"Run again with --apply to save (a backup is made first).")
        return

    backup = path.with_name(f"{path.stem}-backup-{datetime.now():%Y%m%d-%H%M%S}{path.suffix}")
    with sqlite3.connect(backup) as dest:
        conn.backup(dest)
    print(f"Backup saved: {backup}")
    with conn:  # one transaction: all changes or none
        for quiz, questions, new_score, new_passed, award in changes:
            conn.execute("UPDATE quizzes SET questions_json = ? WHERE id = ?",
                         (json.dumps(questions), quiz["id"]))
            if new_score is not None:
                conn.execute("UPDATE quizzes SET score = ?, passed = ? WHERE id = ?",
                             (new_score, int(new_passed), quiz["id"]))
            if award:
                conn.execute(
                    "INSERT OR IGNORE INTO badges (user_id, topic_id, quiz_id, earned_at) VALUES (?, ?, ?, ?)",
                    (quiz["user_id"], quiz["topic_id"], quiz["id"], quiz["submitted_at"]))
    print(f"Saved changes to {len(changes)} quiz(zes).")
    # A new badge can complete a course
    for quiz, *_rest, award in changes:
        topic = db.get_topic(conn, quiz["topic_id"]) if award else None
        if topic and db.award_course_trophy(conn, quiz["user_id"], topic["subject_id"]):
            print(f"   -> {topic['subject_name']} earns its course trophy")


if __name__ == "__main__":
    sys.exit(main())
