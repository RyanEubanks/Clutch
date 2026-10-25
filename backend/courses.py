"""The course catalog: standard courses students can pick, and how far each is verified.

Students can still create any course they like. Picking a catalog course gives them its
usual topics, and tells them how far Mother Hen's answers in it can be trusted.

Verification levels (shown to students, so keep them honest):
  "verified" - the checkers cover the kinds of answers most of the course is made of,
               and it's been tested (backend/tests/, and backend/eval_quiz.py).
  "partial"  - some kinds of answers are checked (listed in "checks"); others aren't
               (listed in "not_checked").
  None       - nothing is checked automatically.
Any course can also get quiz questions checked against the student's own notes (Materials),
see groundcheck.py. "families" says which checkers' question types the quiz prompt offers.
"""
import difflib
import re

QUIZ_ARITHMETIC = "Quiz answer keys for arithmetic are checked by the math engine"
CHAT_ARITHMETIC = "Your answers in chat are checked for arithmetic and simple equations"
QUIZ_ALGEBRA = "Quiz answer keys for equations, evaluating and simplifying are checked"
QUIZ_CALCULUS = "Quiz answer keys for derivatives, integrals and limits are checked"
QUIZ_STATS = ("Quiz answer keys for averages, spread, counting, binomial and normal "
              "probabilities are checked")
QUIZ_GEOMETRY = ("Quiz answer keys for area, perimeter, volume, the Pythagorean theorem, angles "
                 "and distance are checked")
QUIZ_PHYSICS = ("Quiz answer keys for motion, force, energy, momentum, power, circuits, waves, "
                "density and pressure problems are checked, with units")
QUIZ_CHEMISTRY = "Quiz answer keys for molar mass, moles, pH and balancing equations are checked"
QUIZ_SPANISH = "Quiz answer keys for present-tense verb conjugations are checked"
QUIZ_ENGLISH = "Quiz answer keys for irregular verb forms and irregular plurals are checked"
QUIZ_FACTS = "Some quiz questions come from Clutch's fact bank ({}), so their answers are right"
NOTES = "Questions can be checked against your own notes, when you add notes in Materials"

CATALOG = [
    # ---------- math: verified ----------
    {
        "id": "elementary-math", "name": "Elementary Math", "area": "Math", "level": "Grades 1-5",
        "description": "Whole numbers, the four operations, place value, and first fractions.",
        "topics": ["Addition", "Subtraction", "Multiplication", "Division", "Place value",
                   "Fractions", "Word problems"],
        "keywords": ["addition", "add", "adding", "plus", "sum", "subtraction", "subtract",
                     "minus", "multiplication", "multiply", "times tables", "division", "divide",
                     "arithmetic", "counting", "place value", "basic math", "elementary math"],
        "verification": "verified", "checks": [QUIZ_ARITHMETIC, CHAT_ARITHMETIC, NOTES],
        "not_checked": ["Word problems"], "families": ["math"],
    },
    {
        "id": "pre-algebra", "name": "Pre-Algebra", "area": "Math", "level": "Grades 6-8",
        "description": "Integers, fractions and decimals, ratios, order of operations, and "
                       "one-step equations.",
        "topics": ["Integers", "Fractions and decimals", "Ratios and proportions", "Percents",
                   "Order of operations", "Exponents", "One-step equations"],
        "keywords": ["pre-algebra", "prealgebra", "integers", "negative numbers", "decimals",
                     "percent", "percentages", "ratio", "proportion", "order of operations",
                     "pemdas", "exponents", "fractions"],
        "verification": "verified", "checks": [QUIZ_ARITHMETIC, QUIZ_ALGEBRA, CHAT_ARITHMETIC, NOTES],
        "not_checked": ["Word problems"], "families": ["math", "stats"],
    },
    {
        "id": "algebra-1", "name": "Algebra I", "area": "Math", "level": "High school",
        "description": "Linear equations and inequalities, graphing lines, systems, "
                       "polynomials, and factoring.",
        "topics": ["Linear equations", "Inequalities", "Slope and graphing lines",
                   "Systems of equations", "Polynomials", "Factoring", "Quadratic equations"],
        "keywords": ["algebra", "algebra 1", "linear equations", "solving equations", "slope",
                     "inequalities", "systems of equations", "factoring", "polynomials",
                     "quadratics", "quadratic formula"],
        "verification": "verified", "checks": [QUIZ_ALGEBRA, QUIZ_ARITHMETIC, CHAT_ARITHMETIC, NOTES],
        "not_checked": ["Graphing", "Word problems"], "families": ["math"],
    },
    {
        "id": "algebra-2", "name": "Algebra II", "area": "Math", "level": "High school",
        "description": "Functions, quadratics, exponents and logarithms, and rational "
                       "expressions.",
        "topics": ["Functions", "Quadratic functions", "Exponential functions", "Logarithms",
                   "Rational expressions", "Radicals"],
        "keywords": ["algebra 2", "algebra ii", "logarithms", "logs", "exponential functions",
                     "rational expressions", "radicals", "functions", "complex numbers"],
        "verification": "verified", "checks": [QUIZ_ALGEBRA, QUIZ_ARITHMETIC, NOTES],
        "not_checked": ["Graphing", "Word problems"], "families": ["math"],
    },
    {
        "id": "calculus-1", "name": "Calculus I", "area": "Math", "level": "High school / College",
        "description": "Limits, derivatives and their rules, and an introduction to integrals.",
        "topics": ["Limits", "Derivatives", "Chain rule", "Product and quotient rules",
                   "Derivatives of trig functions", "Integrals", "Integration by substitution"],
        "keywords": ["calculus", "calc", "calc 1", "limits", "derivatives", "differentiation",
                     "chain rule", "product rule", "quotient rule", "integrals", "integration",
                     "u-substitution", "antiderivative"],
        "verification": "verified", "checks": [QUIZ_CALCULUS, QUIZ_ALGEBRA, NOTES],
        "not_checked": ["Your calculus answers in chat", "Concept questions"], "families": ["math"],
    },
    # ---------- math and science: not verified yet ----------
    {
        "id": "geometry", "name": "Geometry", "area": "Math", "level": "High school",
        "description": "Shapes, angles, proofs, area and volume, and the Pythagorean theorem.",
        "topics": ["Angles", "Triangles", "Pythagorean theorem", "Area and perimeter",
                   "Volume", "Proofs", "Circles"],
        "keywords": ["geometry", "triangles", "angles", "pythagorean", "proofs", "area",
                     "perimeter", "volume", "circles", "shapes"],
        "verification": "verified", "checks": [QUIZ_GEOMETRY, NOTES],
        "not_checked": ["Proofs"], "families": ["geometry", "math"],
    },
    {
        "id": "statistics", "name": "Statistics", "area": "Math", "level": "High school / College",
        "description": "Data, averages, probability, distributions, and hypothesis tests.",
        "topics": ["Mean, median and mode", "Probability", "Distributions",
                   "Standard deviation", "Hypothesis testing"],
        "keywords": ["statistics", "stats", "probability", "mean", "median", "mode",
                     "standard deviation", "distributions", "hypothesis", "data"],
        "verification": "verified", "checks": [QUIZ_STATS, NOTES],
        "not_checked": ["Hypothesis testing", "Interpreting results"], "families": ["stats", "math"],
    },
    {
        "id": "biology", "name": "Biology", "area": "Science", "level": "High school",
        "description": "Cells, genetics, evolution, ecology, and body systems.",
        "topics": ["Cells and organelles", "Genetics", "DNA", "Evolution", "Ecology",
                   "Photosynthesis", "Body systems"],
        "keywords": ["biology", "bio", "cells", "organelles", "genetics", "dna", "evolution",
                     "ecology", "photosynthesis", "mitosis", "anatomy"],
        "verification": None, "checks": [NOTES],
        "not_checked": ["Facts and concepts (unless checked against your notes)"], "families": [],
    },
    {
        "id": "chemistry", "name": "Chemistry", "area": "Science", "level": "High school",
        "description": "Atoms, the periodic table, bonding, reactions, and stoichiometry.",
        "topics": ["Atoms", "Periodic table", "Chemical bonds", "Reactions",
                   "Stoichiometry", "Acids and bases"],
        "keywords": ["chemistry", "chem", "atoms", "periodic table", "molecules", "bonds",
                     "reactions", "stoichiometry", "moles", "acids", "bases"],
        "verification": "partial", "checks": [QUIZ_CHEMISTRY, NOTES],
        "not_checked": ["Atomic structure", "Bonding", "Concept questions"], "families": ["chemistry"],
    },
    {
        "id": "physics", "name": "Physics", "area": "Science", "level": "High school",
        "description": "Motion, forces, energy, waves, and electricity.",
        "topics": ["Motion", "Newton's laws", "Energy", "Momentum", "Waves", "Electricity"],
        "keywords": ["physics", "motion", "forces", "newton", "energy", "momentum", "waves",
                     "electricity", "velocity", "acceleration", "kinematics"],
        "verification": "verified", "checks": [QUIZ_PHYSICS, NOTES],
        "not_checked": ["Concept questions"], "families": ["physics"],
    },
    # ---------- languages and humanities: not verified ----------
    {
        "id": "spanish-1", "name": "Spanish I", "area": "Languages", "level": "Beginner",
        "description": "Greetings, vocabulary, present tense verbs, and basic conversation.",
        "topics": ["Greetings", "Vocabulary", "Present tense", "Ser vs. estar",
                   "Gender and articles", "Conversation"],
        "keywords": ["spanish", "espanol", "español", "conjugation", "ser", "estar",
                     "spanish vocabulary"],
        "verification": "partial", "checks": [QUIZ_SPANISH, NOTES],
        "not_checked": ["Vocabulary", "Ser vs. estar usage", "Conversation"], "families": ["spanish"],
    },
    {
        "id": "french-1", "name": "French I", "area": "Languages", "level": "Beginner",
        "description": "Greetings, vocabulary, present tense verbs, and basic conversation.",
        "topics": ["Greetings", "Vocabulary", "Present tense", "Gender and articles",
                   "Conversation"],
        "keywords": ["french", "francais", "français", "french vocabulary"],
        "verification": None, "checks": [NOTES],
        "not_checked": ["Everything (unless checked against your notes)"], "families": [],
    },
    {
        "id": "english", "name": "English Language Arts", "area": "English", "level": "High school",
        "description": "Reading comprehension, grammar, essay writing, and literature.",
        "topics": ["Grammar", "Essay writing", "Reading comprehension", "Literary devices",
                   "Poetry"],
        "keywords": ["english", "ela", "grammar", "essay", "writing", "reading", "literature",
                     "poetry", "language arts", "composition"],
        "verification": "partial", "checks": [QUIZ_ENGLISH, NOTES],
        "not_checked": ["Essay writing", "Literary analysis", "Reading questions (unless checked against your notes)"], "families": ["english"],
    },
    {
        "id": "us-history", "name": "U.S. History", "area": "History", "level": "High school",
        "description": "From colonial America through the modern era.",
        "topics": ["Colonial America", "The Revolution", "The Constitution", "Civil War",
                   "Industrial era", "World Wars", "Civil rights"],
        "keywords": ["us history", "american history", "u.s. history", "civil war",
                     "revolution", "constitution", "civil rights"],
        "verification": "partial", "checks": [QUIZ_FACTS.format("presidents, amendments, key dates"), NOTES],
        "not_checked": ["Causes, effects and interpretation"], "families": [],
    },
    {
        "id": "world-history", "name": "World History", "area": "History", "level": "High school",
        "description": "Ancient civilizations through the modern world.",
        "topics": ["Ancient civilizations", "Middle Ages", "Renaissance", "Revolutions",
                   "World Wars", "Cold War"],
        "keywords": ["world history", "history", "ancient", "rome", "greece", "middle ages",
                     "renaissance", "world war", "cold war"],
        "verification": "partial", "checks": [QUIZ_FACTS.format("world capitals, key dates"), NOTES],
        "not_checked": ["Causes, effects and interpretation"], "families": [],
    },
    {
        "id": "geography", "name": "Geography", "area": "Social Studies", "level": "Grades 4-12",
        "description": "Maps, U.S. states and capitals, countries and capitals, and regions.",
        "topics": ["State capitals", "World capitals", "Map skills", "Continents and oceans",
                   "Regions"],
        "keywords": ["geography", "capitals", "state capitals", "world capitals", "maps",
                     "countries", "continents", "map skills"],
        "verification": "partial", "checks": [QUIZ_FACTS.format("state and world capitals"), NOTES],
        "not_checked": ["Physical geography and regions (unless checked against your notes)"],
        "families": [],
    },
    {
        "id": "civics", "name": "Civics & Government", "area": "Social Studies",
        "level": "Grades 7-12",
        "description": "The Constitution, the three branches, rights, and how laws are made.",
        "topics": ["The Constitution", "Branches of government", "Bill of Rights", "Amendments",
                   "Congress", "Presidents"],
        "keywords": ["civics", "government", "us government", "constitution", "branches",
                     "bill of rights", "amendments", "congress", "american government"],
        "verification": "partial",
        "checks": [QUIZ_FACTS.format("branches, Congress, amendments, presidents, founding dates"),
                   NOTES],
        "not_checked": ["Court cases and interpretation (unless checked against your notes)"],
        "families": [],
    },
    {
        "id": "social-studies", "name": "Social Studies", "area": "Social Studies",
        "level": "Grades K-8",
        "description": "Communities, U.S. geography, government basics, and American history.",
        "topics": ["State capitals", "Branches of government", "Presidents", "Map skills",
                   "American Revolution", "Civil War"],
        "keywords": ["social studies", "social science", "communities", "citizenship"],
        "verification": "partial",
        "checks": [QUIZ_FACTS.format("capitals, government, presidents, key dates"), NOTES],
        "not_checked": ["Communities and culture (unless checked against your notes)"],
        "families": [],
    },
    {
        "id": "computer-science", "name": "Intro to Programming", "area": "Computer Science",
        "level": "High school / College",
        "description": "Variables, control flow, functions, and data structures.",
        "topics": ["Variables", "Conditionals", "Loops", "Functions", "Lists and arrays",
                   "Debugging"],
        "keywords": ["programming", "coding", "computer science", "cs", "python", "java",
                     "javascript", "loops", "functions", "code"],
        "verification": None, "checks": [NOTES],
        "not_checked": ["Code and concepts (unless checked against your notes)"], "families": [],
    },
    {
        "id": "economics", "name": "Economics", "area": "Social Science", "level": "High school",
        "description": "Supply and demand, markets, money, and the economy.",
        "topics": ["Supply and demand", "Markets", "Money and banking", "GDP", "Inflation"],
        "keywords": ["economics", "econ", "supply and demand", "markets", "inflation", "gdp",
                     "macroeconomics", "microeconomics"],
        "verification": None, "checks": [NOTES],
        "not_checked": ["Everything (unless checked against your notes)"], "families": [],
    },
    {
        "id": "psychology", "name": "Psychology", "area": "Social Science", "level": "High school",
        "description": "The brain, learning, memory, development, and behavior.",
        "topics": ["The brain", "Learning", "Memory", "Development", "Personality"],
        "keywords": ["psychology", "psych", "brain", "memory", "behavior", "personality"],
        "verification": None, "checks": [NOTES],
        "not_checked": ["Everything (unless checked against your notes)"], "families": [],
    },
]

BY_ID = {c["id"]: c for c in CATALOG}


def get(course_id):
    return BY_ID.get(course_id)


for _c in CATALOG:
    _c["verified"] = _c["verification"] == "verified"  # "✓ Verified" (full)


def public(course):
    """The fields the frontend needs (no keywords)."""
    return {k: course[k] for k in ("id", "name", "area", "level", "description", "topics",
                                   "verification", "verified", "checks", "not_checked")}


def families(course_id):
    """Which checkers' question types to offer in a quiz for this course.
    Custom courses get basic math, like before the catalog existed."""
    course = BY_ID.get(course_id)
    return course["families"] if course else ["math"]


def _norm(text):
    text = str(text).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9ñçéèáíóú+ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def matching_topic(course, query):
    """The catalog topic of `course` that the query names, if any (e.g. 'addition')."""
    q = _norm(query)
    for topic in course["topics"]:
        t = _norm(topic)
        # Exact, or a close typo ("subtracion") that starts the same way ("fractions" is
        # not "reactions").
        if q == t or (q[:2] == t[:2] and difflib.SequenceMatcher(None, q, t).ratio() > 0.88):
            return topic
    return None


def keyword_matches(query, limit=3):
    """Catalog courses that match the query by name, topic or keyword, best first.

    Returns a list of (course, score). Fast and offline, so suggestions still work when
    the model is slow or gives an unusable answer.
    """
    q = _norm(query)
    if not q:
        return []
    words = set(q.split())
    scored = []
    for course in CATALOG:
        name = _norm(course["name"])
        score = 0.0
        if q == name or q == course["id"].replace("-", " "):
            score = 10
        elif matching_topic(course, q):
            score = 8
        else:
            for kw in course["keywords"] + [name]:
                k = _norm(kw)
                if q == k:
                    score = max(score, 7)
                elif f" {k} " in f" {q} ":  # keyword appears in the query
                    score = max(score, 5 + len(k.split()))
                elif len(q) >= 4 and k.startswith(q):  # "multipl" -> "multiplication"
                    score = max(score, 4)
                elif words & set(k.split()) and len(k.split()) == 1:
                    score = max(score, 3)
            # Typos: "subtracion", "calculas"
            for kw in course["keywords"] + [name]:
                k = _norm(kw)
                if q[:2] == k[:2] and difflib.SequenceMatcher(None, q, k).ratio() > 0.85:
                    score = max(score, 4.5)
        if score:
            scored.append((course, score))
    scored.sort(key=lambda cs: -cs[1])
    return scored[:limit]
