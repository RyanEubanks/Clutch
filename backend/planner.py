"""Study planner: exam-aware spaced repetition, exam readiness and study metrics.

Pure functions over rows from db.py, so they're easy to test. Dates are the student's local
dates (datetime.date); timestamps stored by SQLite are UTC and get shifted by tz_minutes
(JavaScript's Date.getTimezoneOffset(): minutes to add to local time to get UTC).

Spaced repetition, per topic:
- After each review a topic comes back after BASE_INTERVALS days (1, 2, 4, 7, ...), stretched
  for strong topics and shrunk for weak ones (mastery 0 halves the gap, mastery 1 makes it 1.5x).
- If an exam or quiz covers the topic, no gap is longer than a third of the time left, there's
  always a review the day before, and in the last FINAL_STRETCH_DAYS days every topic not yet
  mastered comes up daily.
"""
from datetime import date, datetime, timedelta

BASE_INTERVALS = [1, 2, 4, 7, 12, 20, 30]  # days until the next review, after n reviews
FINAL_STRETCH_DAYS = 3
MASTERED = 0.85  # topics at or above this skip the daily final-stretch reviews
AT_RISK_DAYS = 7
AT_RISK_READINESS = 0.6
ACTIVITY_DAYS = 28
TESTS = ("exam", "quiz")


def parse_day(text):
    return date.fromisoformat(text)


def local_date(utc_text, tz_minutes=0):
    """SQLite 'YYYY-MM-DD HH:MM:SS' (UTC) -> the student's local date."""
    if not utc_text:
        return None
    return (datetime.fromisoformat(utc_text) - timedelta(minutes=tz_minutes)).date()


def interval_days(mastery, reviews):
    base = BASE_INTERVALS[min(max(reviews - 1, 0), len(BASE_INTERVALS) - 1)]
    return max(1, round(base * (0.5 + mastery)))


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _when(days):
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"


def upcoming_tests(events, today):
    """Exams and quizzes from today on, soonest first."""
    return sorted(
        (e for e in events if e["kind"] in TESTS and not e["done"] and parse_day(e["date"]) >= today),
        key=lambda e: e["date"],
    )


def schedule(topics, events, today, tz_minutes=0):
    """When each topic should next be reviewed, and why. Soonest and most urgent first."""
    tests = upcoming_tests(events, today)
    plan = []
    for t in topics:
        mastery = t["mastery"] or 0
        reviews = t["sessions_count"] or 0
        last = local_date(t["last_studied_at"], tz_minutes)
        test = next((e for e in tests if t["topic_id"] in e["topic_ids"]), None)
        days_left = (parse_day(test["date"]) - today).days if test else None
        reasons = []

        if last is None:
            due = today
            reasons.append("Not studied yet")
        else:
            due = last + timedelta(days=interval_days(mastery, reviews))
            ago = (today - last).days
            reasons.append("Studied today" if ago == 0 else f"Last studied {_plural(ago, 'day')} ago")

        if test and last is not None:
            exam_day = parse_day(test["date"])
            if days_left > FINAL_STRETCH_DAYS:
                # Fit reviews in before the exam: no gap longer than a third of the time left
                due = min(due, last + timedelta(days=max(1, (exam_day - last).days // 3)))
            elif mastery < MASTERED and last < today:
                due = min(due, today)  # final stretch: daily until mastered (keeps overdue days)
            if last < exam_day - timedelta(days=1):
                due = min(due, exam_day - timedelta(days=1))  # always review the day before
        if test:
            reasons.insert(0, f"{test['kind'].capitalize()} {_when(days_left)}: {test['title']}")

        overdue = (today - due).days
        if overdue > 0:
            reasons.append(f"Review was due {_plural(overdue, 'day')} ago")
        reasons.append(f"Mastery {round(mastery * 100)}%")

        priority = (1 - mastery) * 3 + min(max(overdue, 0), 7) * 0.5
        if test:
            priority += 2 + 10 / (days_left + 1)  # any coming test matters; close ones most
        elif last is None:
            priority -= 1  # new topics with no exam yet can wait behind real reviews

        plan.append({
            "topic_id": t["topic_id"],
            "topic_name": t["topic_name"],
            "subject_name": t["subject_name"],
            "mastery": mastery,
            "sessions_count": reviews,
            "quiz_unlocked": bool(t.get("quiz_unlocked")),
            "has_badge": bool(t.get("badge_earned_at")),
            "last_studied": last.isoformat() if last else None,
            "due": due.isoformat(),
            "due_today": due <= today,
            "test": {
                "id": test["id"], "kind": test["kind"], "title": test["title"],
                "date": test["date"], "days_left": days_left,
            } if test else None,
            "priority": round(priority, 3),
            "reasons": reasons,
        })
    return sorted(plan, key=lambda p: (not p["due_today"], p["due"] if not p["due_today"] else "",
                                       -p["priority"]))


def readiness(events, topics, today):
    """For each upcoming exam or quiz: how ready the student is, weakest topics first."""
    by_id = {t["topic_id"]: t for t in topics}
    out = []
    for e in upcoming_tests(events, today):
        covered = [by_id[i] for i in e["topic_ids"] if i in by_id]
        score = sum(t["mastery"] or 0 for t in covered) / len(covered) if covered else None
        days_left = (parse_day(e["date"]) - today).days
        out.append({
            "id": e["id"], "kind": e["kind"], "title": e["title"], "date": e["date"],
            "time": e["time"], "subject_name": e.get("subject_name"), "days_left": days_left,
            "readiness": None if score is None else round(score, 3),
            "at_risk": score is not None and days_left <= AT_RISK_DAYS and score < AT_RISK_READINESS,
            "topics": sorted(
                ({"topic_id": t["topic_id"], "topic_name": t["topic_name"], "mastery": t["mastery"] or 0}
                 for t in covered),
                key=lambda t: t["mastery"],
            ),
        })
    return out


def metrics(activity, quizzes, topics, today, tz_minutes=0):
    """Streak, the last ACTIVITY_DAYS days of activity, this week's totals and mastery."""
    per_day = {}
    sessions_per_day = {}
    for m in activity:
        d = local_date(m["created_at"], tz_minutes)
        per_day[d] = per_day.get(d, 0) + 1
        sessions_per_day.setdefault(d, set()).add(m["conversation_id"])

    days = [today - timedelta(days=i) for i in range(ACTIVITY_DAYS - 1, -1, -1)]
    # A streak survives until the end of today, so count back from yesterday if needed
    streak, d = 0, today if per_day.get(today) else today - timedelta(days=1)
    while per_day.get(d):
        streak += 1
        d -= timedelta(days=1)

    week_start = today - timedelta(days=today.weekday())  # Monday
    this_week = [d for d in per_day if week_start <= d <= today]
    week_quizzes = [q for q in quizzes if local_date(q["submitted_at"], tz_minutes) >= week_start]
    studied = [t for t in topics if (t["sessions_count"] or 0) > 0]
    return {
        "streak": streak,
        "studied_today": bool(per_day.get(today)),
        "activity": [{"date": d.isoformat(), "messages": per_day.get(d, 0),
                      "sessions": len(sessions_per_day.get(d, ()))} for d in days],
        "active_days": sum(1 for d in days if per_day.get(d)),
        "week": {
            "sessions": len(set().union(*(sessions_per_day[d] for d in this_week))) if this_week else 0,
            "messages": sum(per_day[d] for d in this_week),
            "quizzes_taken": len(week_quizzes),
            "quizzes_passed": sum(1 for q in week_quizzes if q["passed"]),
        },
        "average_mastery": round(sum(t["mastery"] or 0 for t in studied) / len(studied), 3) if studied else None,
        "topics_total": len(topics),
        "topics_studied": len(studied),
        "topics_mastered": sum(1 for t in topics if (t["mastery"] or 0) >= MASTERED),
    }
