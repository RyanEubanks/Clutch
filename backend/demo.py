"""The demo profile, Alex: a calculus student six days before a midterm.

Signing in as Alex wipes Alex's data and builds it again, with every date relative to today,
so each demo (and each recording take) starts the same: a 4-day study streak ending yesterday,
reviews due today, a midterm in 6 days, and a library of notes, lectures and a scanned page.
Only the profile flagged is_demo is ever touched here.
"""
from datetime import date, datetime, timedelta, timezone

import courses
import db

DEMO_USERNAME = "alex"
DEMO_NAME = "Alex"


def ensure_demo_user(conn):
    """Create the demo profile if it's missing. A real profile already named alex is left alone."""
    row = db.find_user_login(conn, DEMO_USERNAME)
    if row is None:
        db.create_user(conn, DEMO_USERNAME, None, DEMO_NAME, is_demo=True)
    elif not row["is_demo"]:
        print(f'NOTE: a profile named "{DEMO_USERNAME}" already exists, so there is no demo profile.')


def _ts(days_ago, hour=19, minute=0):
    """A UTC timestamp `days_ago` days back, at a local evening hour, as SQLite stores them."""
    local = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(days=days_ago)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _day(days_from_today):
    return (date.today() + timedelta(days=days_from_today)).isoformat()


SUBJECTS = {
    "Calculus I": {
        "Chain rule": "Derivatives of composite functions",
        "Limits": "Limits, indeterminate forms and continuity",
        "Integration by parts": "Integrating products of functions",
        "Derivatives": "Power, product and quotient rules",
    },
    "Linear Algebra": {
        "Eigenvalues": "Eigenvalues and eigenvectors of 2x2 and 3x3 matrices",
        "Determinants": "Computing determinants and what they mean",
    },
}

# topic: (mastery, sessions, days since last studied, last gaps)
PROGRESS = {
    "Chain rule": (0.82, 4, 2, "Sometimes forgets to multiply by the inner derivative with trig functions"),
    "Limits": (0.45, 2, 6, "Treats 0/0 as an answer instead of a sign to simplify"),
    "Integration by parts": (0.30, 1, 1, "Unsure how to choose u; skipped the minus sign once"),
    "Derivatives": (0.93, 6, 9, None),
    "Eigenvalues": (0.55, 3, 3, "Sets up det(A - λI) correctly but makes arithmetic slips solving it"),
}

# Study sessions: (days ago, topic, title, confidence 1-5, review, messages as (role, text))
SESSIONS = [
    (1, "Integration by parts", "Integrating x times e^x", 2,
     (0.35, "Worked through ∫x e^x dx with heavy guidance.",
      "Recognized the integrand is a product", "Choosing u; dropped the minus sign in uv − ∫v du"),
     [("user", "How do I integrate $x e^x$?"),
      ("assistant", "Good one to practice. It's a product of two functions, so integration by parts fits:\n\n$$\\int u\\,dv = uv - \\int v\\,du$$\n\nWhich of the two, $x$ or $e^x$, gets simpler when you differentiate it?"),
      ("user", "x? its derivative is 1"),
      ("assistant", "Exactly. So let $u = x$ and $dv = e^x\\,dx$. What are $du$ and $v$?"),
      ("user", "du = dx and v = e^x so the answer is x e^x + e^x + C"),
      ("assistant", "Not quite. You found $u$, $v$ and $du$ correctly. Look at the formula again: what sign sits in front of $\\int v\\,du$?")]),
    (2, "Chain rule", "Derivative of sin(x^2)", 4,
     (0.85, "Applied the chain rule to sin(x²) and (3x² − 2)⁴ correctly.",
      "Identifies outer and inner functions quickly", "Slowed down on nested trig functions"),
     [("user", "Is the derivative of $\\sin(x^2)$ just $\\cos(x^2)$?"),
      ("assistant", "Not quite. $\\cos(x^2)$ is the derivative of the outer function. With the chain rule you also multiply by something. What is it?"),
      ("user", "the derivative of the inside, so 2x. cos(x^2) * 2x"),
      ("assistant", "Yes, that's right. The chain rule multiplies the outer derivative by the inner one:\n\n$$\\frac{d}{dx}\\sin(x^2) = 2x\\cos(x^2)$$\n\nTry one more: what's the derivative of $(3x^2 - 2)^4$?")]),
    (3, "Eigenvalues", "Eigenvalues of a 2x2 matrix", 3,
     (0.6, "Found the characteristic equation for a 2×2 matrix.",
      "Knows to solve det(A − λI) = 0", "Arithmetic slips when expanding (2 − λ)²"),
     [("user", "How do I find the eigenvalues of [[2,1],[1,2]]?"),
      ("assistant", "Eigenvalues $\\lambda$ satisfy $\\det(A - \\lambda I) = 0$. Can you write out $A - \\lambda I$ for this matrix?"),
      ("user", "[[2-λ, 1],[1, 2-λ]]"),
      ("assistant", "Right. Now take its determinant and set it equal to zero. What equation do you get?")]),
    (4, "Limits", "Limit of (x^2-9)/(x-3)", 2,
     (0.4, "Practiced limits with an indeterminate form.",
      "Tried direct substitution first", "Treated 0/0 as the answer"),
     [("user", "Is the limit of (x^2-9)/(x-3) as x→3 equal to 0? I got 0/0"),
      ("assistant", "Not quite. Getting $\\frac{0}{0}$ doesn't mean the limit is 0; it means the expression has to be simplified first. Can you factor the numerator $x^2 - 9$?")]),
    (9, "Derivatives", "Quotient rule practice", 5,
     (0.95, "Used the quotient rule fluently on three problems.",
      "Fast and accurate with the quotient rule", None),
     [("user", "Is the derivative of x^2/(x+1) equal to (x^2+2x)/(x+1)^2?"),
      ("assistant", "Yes, that's right. The quotient rule gives $\\frac{2x(x+1) - x^2}{(x+1)^2}$, which simplifies to what you wrote. Ready for a harder one?")]),
    (15, "Chain rule", "What is the chain rule?", 3,
     (0.7, "Learned what the chain rule is and when to use it.",
      "Asked good conceptual questions", "Still practicing spotting composite functions"),
     [("user", "What is the chain rule?"),
      ("assistant", "The chain rule finds the derivative of a function inside another function:\n\n$$\\frac{d}{dx}\\left[f(g(x))\\right] = f'(g(x))\\cdot g'(x)$$\n\nFor $y = (x^2 + 1)^3$, the outer function is $u^3$ and the inner is $x^2 + 1$. Which part would you differentiate first?")]),
]

DOCUMENTS = [
    ("Lecture 7: The chain rule", "Chain rule", 8, r"""# Lecture 7: The chain rule

## Idea
If $y = f(u)$ and $u = g(x)$, then $y$ depends on $x$ through $u$.

$$\frac{dy}{dx} = \frac{dy}{du} \cdot \frac{du}{dx}$$

## Function notation
$$\frac{d}{dx}\left[f(g(x))\right] = f'(g(x)) \cdot g'(x)$$

## Example
For $y = \sin(x^2)$: outer $\sin(u)$, inner $u = x^2$, so $y' = \cos(x^2) \cdot 2x$.

## Common mistakes
- Forgetting the inner derivative $g'(x)$
- Differentiating the inside twice
"""),
    ("Lecture 9: Integration by parts", "Integration by parts", 1, r"""# Integration by Parts

## The formula
- Write this down, it will be on the exam:
$$\int u \, dv = uv - \int v \, du$$

## Choosing $u$
- Use **LIATE**: Logs, Inverse trig, Algebraic, Trig, Exponential
- Pick $u$ from whichever comes first in the list

## Worked example
- Integrate $x e^x$: $u = x$, $dv = e^x \, dx$, so $du = dx$ and $v = e^x$
$$\int x e^x \, dx = x e^x - \int e^x \, dx = x e^x - e^x + C$$

## Common mistakes
- Forgetting the minus sign in the middle of the formula
- Dropping the $+C$ at the end

## Homework
- Problems 1 through 12 on page 240

## Full transcript

Okay everyone, let's get started. Today we're covering integration by parts. The main formula is the integral of u dv equals uv minus the integral of v du. Write that down, it will be on the exam.

So how do you choose u? Use the acronym LIATE: logs, inverse trig, algebraic, trig, and exponential. Pick u from whichever comes first in that list.

Let's do an example. Integrate x times e to the x. Here u is x, because algebraic comes before exponential. So du is dx, and v is e to the x. Plugging in, we get x e to the x minus the integral of e to the x dx, which is x e to the x minus e to the x, plus C.

Two common mistakes. First, forgetting the minus sign in the middle of the formula. Second, dropping the plus C at the end. Next time we'll look at the tabular method. For homework, do problems one through twelve on page two forty.
"""),
    ("Limits review sheet", "Limits", 12, r"""# Limits review

## Indeterminate forms
Plugging in and getting $\frac{0}{0}$ means simplify first: factor, cancel, or rationalize.

## Example
$$\lim_{x \to 2} \frac{x^2 - 4}{x - 2} = \lim_{x \to 2} (x + 2) = 4$$

## Squeeze theorem
If $g(x) \le f(x) \le h(x)$ near $a$ and both outer limits are $L$, then $\lim_{x \to a} f(x) = L$.
"""),
    ("Calculus 1 - Homework 4: Derivatives", "Derivatives", 5, r"""Calculus 1 - Homework 4: Derivatives

Show your work.

1. Find the derivative of $f(x) = (3x^2 - 2)^4$
2. Find $dy/dx$ if $y = \sin(5x)$
3. Differentiate $g(x) = x^2 \cdot e^x$
4. Find the slope of the tangent line to $y = x^3 - 4x$ at $x = 2$
"""),
]


def reset_demo(conn, user_id):
    """Wipe the demo profile's data and build it again for today. Refuses any other profile."""
    if not conn.execute("SELECT is_demo FROM users WHERE id = ?", (user_id,)).fetchone()[0]:
        raise ValueError("reset_demo only runs on the demo profile")
    with conn:
        for table in ("events", "documents", "conversations", "quizzes", "badges", "topic_progress", "subjects"):
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        _build(conn, user_id)


def _build(conn, user_id):
    subject_ids, topic_ids = {}, {}
    # Courses named like a standard catalog course get linked to it, as for any student
    # (Calculus I is verified; Linear Algebra isn't in the catalog, so it stays custom)
    catalog = {c["name"].lower(): c["id"] for c in courses.CATALOG}
    for subject, topics in SUBJECTS.items():
        subject_ids[subject] = conn.execute(
            "INSERT INTO subjects (user_id, name, catalog_id, created_at) VALUES (?, ?, ?, ?)",
            (user_id, subject, catalog.get(subject.lower()), _ts(30)),
        ).lastrowid
        for name, description in topics.items():
            topic_ids[name] = conn.execute(
                "INSERT INTO topics (subject_id, name, description, created_at) VALUES (?, ?, ?, ?)",
                (subject_ids[subject], name, description, _ts(30)),
            ).lastrowid

    for name, (mastery, sessions, ago, gaps) in PROGRESS.items():
        conn.execute(
            """INSERT INTO topic_progress (user_id, topic_id, mastery, sessions_count, messages_count,
                                           last_gaps, last_studied_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, topic_ids[name], mastery, sessions, sessions * 6, gaps, _ts(ago, 20), _ts(ago, 20)),
        )
    # Derivatives is mastered: its quiz was passed, so it has a badge
    conn.execute("INSERT INTO badges (user_id, topic_id, earned_at) VALUES (?, ?, ?)",
                 (user_id, topic_ids["Derivatives"], _ts(9, 21)))

    for ago, topic, title, confidence, (understanding, summary, strengths, gaps), messages in SESSIONS:
        convo = conn.execute(
            """INSERT INTO conversations (user_id, topic_id, title, created_at, updated_at, ended_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, topic_ids[topic], title, _ts(ago, 19), _ts(ago, 19, 30), _ts(ago, 19, 35)),
        ).lastrowid
        for i, (role, text) in enumerate(messages):
            conn.execute("INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                         (convo, role, text, _ts(ago, 19, 2 + i * 3)))
        conn.execute(
            """INSERT INTO session_reviews (conversation_id, topic_id, understanding, confidence,
                                            summary, strengths, gaps, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (convo, topic_ids[topic], understanding, confidence, summary, strengths, gaps, _ts(ago, 19, 35)),
        )

    for title, topic, ago, content in DOCUMENTS:
        conn.execute(
            "INSERT INTO documents (user_id, topic_id, title, content, char_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, topic_ids[topic], title, content, len(content), _ts(ago, 17)),
        )

    calc, linalg = subject_ids["Calculus I"], subject_ids["Linear Algebra"]
    events = [
        ("exam", "Calculus Midterm 2", 6, "09:30", calc, ["Chain rule", "Limits", "Integration by parts"],
         "Room 214. Bring a calculator.", False),
        ("quiz", "Eigenvalues quiz", 9, "13:00", linalg, ["Eigenvalues", "Determinants"], None, False),
        ("homework", "Problem set 7", 1, "23:59", calc, [], "Problems 1-12, page 240", False),
        ("homework", "LA worksheet 4", 4, None, linalg, [], None, False),
        ("other", "Study group", 3, "18:00", None, [], "Library, 2nd floor", False),
        ("homework", "Problem set 6", -2, None, calc, [], None, True),
    ]
    for kind, title, days, time, subject, topics, notes, done in events:
        event = conn.execute(
            """INSERT INTO events (user_id, subject_id, kind, title, date, time, notes, done, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, subject, kind, title, _day(days), time, notes, 1 if done else 0, _ts(10)),
        ).lastrowid
        conn.executemany("INSERT INTO event_topics (event_id, topic_id) VALUES (?, ?)",
                         [(event, topic_ids[t]) for t in topics])
