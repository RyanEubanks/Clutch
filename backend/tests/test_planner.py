import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import planner as p  # noqa: E402

TODAY = date(2026, 3, 10)


def topic(tid, mastery=0.5, sessions=1, last_days_ago=None, name=None):
    last = None
    if last_days_ago is not None:
        last = f"{(TODAY - timedelta(days=last_days_ago)).isoformat()} 15:00:00"
    return {"topic_id": tid, "topic_name": name or f"T{tid}", "subject_name": "Calc",
            "mastery": mastery, "sessions_count": sessions, "last_studied_at": last}


def exam(eid, days_from_now, topic_ids, kind="exam", done=False):
    return {"id": eid, "kind": kind, "title": f"Exam {eid}", "time": None, "done": done,
            "date": (TODAY + timedelta(days=days_from_now)).isoformat(), "topic_ids": topic_ids}


def plan_for(topics, events=()):
    return {x["topic_id"]: x for x in p.schedule(topics, list(events), TODAY)}


def test_intervals_grow_with_reviews_and_mastery():
    assert [p.interval_days(0.5, n) for n in range(1, 8)] == p.BASE_INTERVALS
    assert p.interval_days(0.0, 4) < p.interval_days(0.5, 4) < p.interval_days(1.0, 4)
    assert p.interval_days(0.0, 1) == 1  # never less than a day


def test_new_topics_are_due_but_behind_real_reviews():
    plan = p.schedule([topic(1, mastery=0, sessions=0), topic(2, mastery=0.6, sessions=2, last_days_ago=5)],
                      [], TODAY)
    assert [x["topic_id"] for x in plan if x["due_today"]] == [2, 1]
    assert plan[1]["reasons"][0] == "Not studied yet"


def test_strong_recent_topic_waits_without_an_exam():
    t = plan_for([topic(1, mastery=0.9, sessions=5, last_days_ago=2)])[1]
    assert not t["due_today"]
    assert t["due"] == (TODAY - timedelta(days=2) + timedelta(days=p.interval_days(0.9, 5))).isoformat()


def test_exam_shortens_the_gap_to_a_third_of_the_time_left():
    # Studied today, exam in 12 days: without the exam the next review would be weeks away
    t = plan_for([topic(1, mastery=0.9, sessions=5, last_days_ago=0)], [exam(9, 12, [1])])[1]
    assert t["due"] == (TODAY + timedelta(days=4)).isoformat()
    assert t["reasons"][0] == "Exam in 12 days: Exam 9"


def test_always_a_review_the_day_before_the_exam():
    # Gap cap from 9 days ago allows today+?; the day-before rule wins when it's sooner
    t = plan_for([topic(1, mastery=0.95, sessions=6, last_days_ago=1)], [exam(9, 2, [1])])[1]
    assert t["due"] <= (TODAY + timedelta(days=1)).isoformat()


def test_final_stretch_reviews_unmastered_topics_daily():
    plan = plan_for(
        [topic(1, mastery=0.5, sessions=3, last_days_ago=1), topic(2, mastery=0.9, sessions=6, last_days_ago=1),
         topic(3, mastery=0.5, sessions=3, last_days_ago=0)],
        [exam(9, 3, [1, 2, 3])],
    )
    assert plan[1]["due_today"]          # weak, exam in 3 days
    assert not plan[2]["due_today"]      # already mastered
    assert not plan[3]["due_today"]      # weak, but studied today


def test_exam_topics_outrank_others_and_closer_exams_rank_higher():
    plan = p.schedule(
        [topic(1, mastery=0.5, sessions=2, last_days_ago=9), topic(2, mastery=0.5, sessions=2, last_days_ago=9),
         topic(3, mastery=0.5, sessions=2, last_days_ago=9)],
        [exam(8, 10, [2]), exam(9, 2, [3])], TODAY,
    )
    assert [x["topic_id"] for x in plan] == [3, 2, 1]


def test_past_and_done_tests_are_ignored():
    t = plan_for([topic(1, mastery=0.9, sessions=5, last_days_ago=0)],
                 [exam(8, -1, [1]), exam(9, 5, [1], done=True), exam(7, 5, [1], kind="homework")])[1]
    assert t["test"] is None


def test_timezone_shifts_last_studied_to_the_local_day():
    # 01:30 UTC on the 10th is still the evening of the 9th in New York (UTC-4: tz=240)
    t = {**topic(1), "last_studied_at": "2026-03-10 01:30:00"}
    assert p.schedule([t], [], TODAY, tz_minutes=240)[0]["last_studied"] == "2026-03-09"
    assert p.schedule([t], [], TODAY, tz_minutes=0)[0]["last_studied"] == "2026-03-10"


def test_readiness_and_risk():
    topics = [topic(1, mastery=0.2), topic(2, mastery=0.6), topic(3, mastery=0.9)]
    soon, empty, later = p.readiness(  # soonest first
        [exam(1, 3, [1, 2]), exam(2, 20, [1, 2]), exam(3, 4, [], kind="quiz")], topics, TODAY,
    )
    assert soon["readiness"] == 0.4 and soon["at_risk"] and soon["days_left"] == 3
    assert [t["topic_id"] for t in soon["topics"]] == [1, 2]  # weakest first
    assert not later["at_risk"]  # same readiness, but there's time
    assert empty["readiness"] is None and not empty["at_risk"]


def test_metrics_streak_activity_and_week():
    def msg(days_ago, convo=1, hour=15):
        return {"created_at": f"{(TODAY - timedelta(days=days_ago)).isoformat()} {hour:02d}:00:00",
                "topic_id": 1, "conversation_id": convo}

    activity = [msg(0), msg(0, convo=2), msg(1), msg(2), msg(4)]
    m = p.metrics(activity, [{"topic_id": 1, "passed": 1, "submitted_at": f"{TODAY} 10:00:00"}],
                  [topic(1, mastery=0.9, sessions=3), topic(2, mastery=0.4, sessions=1), topic(3, sessions=0)],
                  TODAY)
    assert m["streak"] == 3 and m["studied_today"]
    assert len(m["activity"]) == p.ACTIVITY_DAYS and m["activity"][-1] == {
        "date": TODAY.isoformat(), "messages": 2, "sessions": 2}
    assert m["active_days"] == 4
    # TODAY (2026-03-10) is a Tuesday, so this week is Monday the 9th and today
    assert m["week"] == {"sessions": 2, "messages": 3, "quizzes_taken": 1, "quizzes_passed": 1}
    assert m["average_mastery"] == 0.65 and m["topics_mastered"] == 1 and m["topics_studied"] == 2


def test_streak_survives_until_end_of_today():
    m = p.metrics([{"created_at": f"{TODAY - timedelta(days=1)} 12:00:00", "topic_id": None,
                    "conversation_id": 1}], [], [], TODAY)
    assert m["streak"] == 1 and not m["studied_today"]
    assert p.metrics([], [], [], TODAY)["streak"] == 0
