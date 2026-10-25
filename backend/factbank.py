"""A small bank of social studies facts, used to write quiz questions that are correct by
construction: the question, the right answer, and the wrong options all come from here,
not from the model.

Only stable, unambiguous facts belong here (no contested capitals, no "current" office
holders). Keep entries sourced from standard references when adding more.
"""
import random

STATE_CAPITALS = {
    "Alabama": "Montgomery", "Alaska": "Juneau", "Arizona": "Phoenix", "Arkansas": "Little Rock",
    "California": "Sacramento", "Colorado": "Denver", "Connecticut": "Hartford",
    "Delaware": "Dover", "Florida": "Tallahassee", "Georgia": "Atlanta", "Hawaii": "Honolulu",
    "Idaho": "Boise", "Illinois": "Springfield", "Indiana": "Indianapolis", "Iowa": "Des Moines",
    "Kansas": "Topeka", "Kentucky": "Frankfort", "Louisiana": "Baton Rouge", "Maine": "Augusta",
    "Maryland": "Annapolis", "Massachusetts": "Boston", "Michigan": "Lansing",
    "Minnesota": "Saint Paul", "Mississippi": "Jackson", "Missouri": "Jefferson City",
    "Montana": "Helena", "Nebraska": "Lincoln", "Nevada": "Carson City",
    "New Hampshire": "Concord", "New Jersey": "Trenton", "New Mexico": "Santa Fe",
    "New York": "Albany", "North Carolina": "Raleigh", "North Dakota": "Bismarck",
    "Ohio": "Columbus", "Oklahoma": "Oklahoma City", "Oregon": "Salem",
    "Pennsylvania": "Harrisburg", "Rhode Island": "Providence", "South Carolina": "Columbia",
    "South Dakota": "Pierre", "Tennessee": "Nashville", "Texas": "Austin",
    "Utah": "Salt Lake City", "Vermont": "Montpelier", "Virginia": "Richmond",
    "Washington": "Olympia", "West Virginia": "Charleston", "Wisconsin": "Madison",
    "Wyoming": "Cheyenne",
}

# Countries whose capital is settled and single (South Africa, Indonesia, etc. left out).
WORLD_CAPITALS = {
    "France": "Paris", "Germany": "Berlin", "Italy": "Rome", "Spain": "Madrid",
    "Portugal": "Lisbon", "the United Kingdom": "London", "Ireland": "Dublin",
    "the Netherlands": "Amsterdam", "Belgium": "Brussels", "Switzerland": "Bern",
    "Austria": "Vienna", "Poland": "Warsaw", "Greece": "Athens", "Sweden": "Stockholm",
    "Norway": "Oslo", "Finland": "Helsinki", "Denmark": "Copenhagen", "Russia": "Moscow",
    "Ukraine": "Kyiv", "Turkey": "Ankara", "Egypt": "Cairo", "Kenya": "Nairobi",
    "Nigeria": "Abuja", "Morocco": "Rabat", "Ethiopia": "Addis Ababa", "China": "Beijing",
    "Japan": "Tokyo", "South Korea": "Seoul", "India": "New Delhi", "Pakistan": "Islamabad",
    "Thailand": "Bangkok", "Vietnam": "Hanoi", "the Philippines": "Manila",
    "Australia": "Canberra", "New Zealand": "Wellington", "Canada": "Ottawa",
    "Mexico": "Mexico City", "Brazil": "Brasília", "Argentina": "Buenos Aires",
    "Chile": "Santiago", "Peru": "Lima", "Colombia": "Bogotá", "Cuba": "Havana",
    "Saudi Arabia": "Riyadh", "Iran": "Tehran", "Iraq": "Baghdad",
}

# Presidents 1-45 (number -> name). Not asked about more recent terms.
PRESIDENTS = [
    "George Washington", "John Adams", "Thomas Jefferson", "James Madison", "James Monroe",
    "John Quincy Adams", "Andrew Jackson", "Martin Van Buren", "William Henry Harrison",
    "John Tyler", "James K. Polk", "Zachary Taylor", "Millard Fillmore", "Franklin Pierce",
    "James Buchanan", "Abraham Lincoln", "Andrew Johnson", "Ulysses S. Grant",
    "Rutherford B. Hayes", "James A. Garfield", "Chester A. Arthur", "Grover Cleveland",
    "Benjamin Harrison", "Grover Cleveland", "William McKinley", "Theodore Roosevelt",
    "William Howard Taft", "Woodrow Wilson", "Warren G. Harding", "Calvin Coolidge",
    "Herbert Hoover", "Franklin D. Roosevelt", "Harry S. Truman", "Dwight D. Eisenhower",
    "John F. Kennedy", "Lyndon B. Johnson", "Richard Nixon", "Gerald Ford", "Jimmy Carter",
    "Ronald Reagan", "George H. W. Bush", "Bill Clinton", "George W. Bush", "Barack Obama",
    "Donald Trump",
]

AMENDMENTS = {
    1: "protects freedom of speech, religion, the press, assembly and petition",
    2: "protects the right to keep and bear arms",
    4: "protects against unreasonable searches and seizures",
    5: "protects against being forced to testify against yourself",
    6: "guarantees the right to a speedy and public trial",
    8: "forbids cruel and unusual punishment",
    13: "abolished slavery",
    14: "guarantees citizenship and equal protection of the laws",
    15: "protects the right to vote regardless of race",
    19: "gave women the right to vote",
    26: "lowered the voting age to 18",
}

# question -> right answer; wrong answers come from the other entries' answers.
GOVERNMENT = [
    ("Which part of the U.S. government makes federal laws?", "Congress"),
    ("Which part of the U.S. government enforces federal laws?", "the President"),
    ("Which part of the U.S. government interprets federal laws?", "the Supreme Court"),
    ("Who is commander in chief of the U.S. military?", "the President"),
    ("Who confirms the President's nominees to the Supreme Court?", "the Senate"),
    ("Which part of Congress has 435 voting members?", "the House of Representatives"),
]
GOVERNMENT_EXTRA = ["the Cabinet", "the Governor", "the Vice President"]
GOVERNMENT_NUMBERS = [
    ("How many senators does each state have?", 2),
    ("How many voting members are in the U.S. House of Representatives?", 435),
    ("How many years is a U.S. senator's term?", 6),
    ("How many years is a U.S. representative's term?", 2),
    ("How many years is a U.S. president's term?", 4),
    ("How many justices serve on the U.S. Supreme Court?", 9),
    ("How many senators are in the U.S. Senate?", 100),
]

# (question wording, statement, year, tags). Tags decide which topics a fact is used for.
DATES = [
    ("did Columbus first reach the Americas", "Columbus first reached the Americas", 1492,
     {"exploration"}),
    ("was the Declaration of Independence adopted", "The Declaration of Independence was adopted",
     1776, {"revolution", "independence", "constitution"}),
    ("was the U.S. Constitution signed", "The U.S. Constitution was signed", 1787,
     {"constitution", "government", "founding"}),
    ("was the Bill of Rights ratified", "The Bill of Rights was ratified", 1791,
     {"constitution", "bill of rights", "government"}),
    ("did the U.S. make the Louisiana Purchase", "The U.S. made the Louisiana Purchase", 1803,
     {"expansion"}),
    ("did the U.S. Civil War begin", "The U.S. Civil War began", 1861, {"civil war", "slavery"}),
    ("was the Emancipation Proclamation issued", "The Emancipation Proclamation was issued",
     1863, {"civil war", "slavery"}),
    ("did the U.S. Civil War end", "The U.S. Civil War ended", 1865,
     {"civil war", "slavery", "reconstruction"}),
    ("did World War I begin", "World War I began", 1914, {"world war"}),
    ("did World War I end", "World War I ended", 1918, {"world war"}),
    ("did the stock market crash that started the Great Depression",
     "The stock market crashed, starting the Great Depression,", 1929, {"depression", "economy"}),
    ("did Japan attack Pearl Harbor", "Japan attacked Pearl Harbor", 1941, {"world war"}),
    ("did World War II end", "World War II ended", 1945, {"world war"}),
    ("did the Supreme Court decide Brown v. Board of Education",
     "The Supreme Court decided Brown v. Board of Education", 1954, {"civil rights"}),
    ("was the Civil Rights Act signed", "The Civil Rights Act was signed", 1964, {"civil rights"}),
    ("did astronauts first land on the Moon", "Astronauts first landed on the Moon", 1969,
     {"space", "cold war"}),
    ("did the Berlin Wall fall", "The Berlin Wall fell", 1989, {"cold war"}),
    ("was the Magna Carta sealed", "The Magna Carta was sealed", 1215,
     {"middle ages", "government"}),
    ("did the French Revolution begin", "The French Revolution began", 1789,
     {"revolution", "revolutions"}),
    ("did the Russian Revolution take place", "The Russian Revolution took place", 1917,
     {"revolution", "revolutions"}),
    ("was the United Nations founded", "The United Nations was founded", 1945,
     {"world war", "cold war"}),
]

# Which kinds of fact go with which topic words.
TOPIC_WORDS = {
    "state_capitals": {"state capitals", "capitals", "states", "us geography", "u.s. geography",
                       "united states geography", "map skills"},
    "world_capitals": {"world capitals", "capitals", "countries", "world geography", "geography",
                       "continents", "map skills"},
    "presidents": {"presidents", "presidency", "executive branch", "us presidents"},
    "amendments": {"amendments", "bill of rights", "constitution", "rights", "civil rights"},
    "government": {"government", "branches", "branches of government", "congress", "civics",
                   "the constitution", "constitution", "checks and balances", "federal government"},
}
# Course -> the fact kinds it uses when a topic doesn't name one (dates are matched by tag).
COURSE_FACTS = {
    "us-history": ["presidents", "amendments", "dates"],
    "world-history": ["world_capitals", "dates"],
    "geography": ["state_capitals", "world_capitals"],
    "civics": ["government", "amendments", "presidents"],
    "social-studies": ["state_capitals", "government", "presidents", "dates"],
}


def _ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _choice_question(question, right, wrong_pool, rng, explanation):
    wrong = rng.sample(sorted(set(wrong_pool) - {right}), 3)
    options = wrong + [right]
    rng.shuffle(options)
    return {"question": question, "options": options, "answer": options.index(right),
            "explanation": explanation, "verified": True, "corrected": False,
            "model_said": None, "checked_by": "facts"}


def _year_options(year, rng):
    offsets = rng.sample([-20, -12, -8, -5, -3, -2, 2, 3, 5, 8, 12, 20], 3)
    return [str(year + o) for o in offsets] + [str(year)]


def _make(kind, rng, tags=None):
    if kind == "state_capitals":
        state = rng.choice(sorted(STATE_CAPITALS))
        return _choice_question(f"What is the capital of {state}?", STATE_CAPITALS[state],
                                STATE_CAPITALS.values(), rng,
                                f"The capital of {state} is {STATE_CAPITALS[state]}.")
    if kind == "world_capitals":
        country = rng.choice(sorted(WORLD_CAPITALS))
        return _choice_question(f"What is the capital of {country}?", WORLD_CAPITALS[country],
                                WORLD_CAPITALS.values(), rng,
                                f"The capital of {country} is {WORLD_CAPITALS[country]}.")
    if kind == "presidents":
        n = rng.randint(1, len(PRESIDENTS))
        name = PRESIDENTS[n - 1]
        nearby = [p for i, p in enumerate(PRESIDENTS, 1) if abs(i - n) <= 8 and p != name]
        return _choice_question(f"Who was the {_ordinal(n)} president of the United States?",
                                name, nearby, rng,
                                f"{name} was the {_ordinal(n)} president.")
    if kind == "amendments":
        number = rng.choice(sorted(AMENDMENTS))
        right = f"the {_ordinal(number)} Amendment"
        pool = [f"the {_ordinal(k)} Amendment" for k in AMENDMENTS]
        return _choice_question(f"Which amendment {AMENDMENTS[number]}?", right, pool, rng,
                                f"The {_ordinal(number)} Amendment {AMENDMENTS[number]}.")
    if kind == "government":
        if rng.random() < 0.5:
            question, answer = rng.choice(GOVERNMENT)
            pool = [a for _, a in GOVERNMENT] + GOVERNMENT_EXTRA
            return _choice_question(question, answer, pool, rng, f"The answer is {answer}.")
        question, answer = rng.choice(GOVERNMENT_NUMBERS)
        pool = {str(n) for _, n in GOVERNMENT_NUMBERS} | {"3", "8", "50", "538"}
        return _choice_question(question, str(answer), pool, rng, f"The answer is {answer}.")
    if kind == "dates":
        facts = [d for d in DATES if not tags or d[3] & tags]
        if not facts:
            return None
        asked, statement, year, _ = rng.choice(facts)
        options = _year_options(year, rng)
        rng.shuffle(options)
        return {"question": f"In what year {asked}?", "options": options,
                "answer": options.index(str(year)),
                "explanation": f"{statement} in {year}.", "verified": True,
                "corrected": False, "model_said": None, "checked_by": "facts"}
    raise ValueError(kind)


def kinds_for(course_id, topic):
    """The fact kinds that fit a topic, plus date tags. ([], None) if nothing fits."""
    t = str(topic or "").strip().lower()
    kinds = [k for k, words in TOPIC_WORDS.items() if t in words or any(w in t for w in words if len(w) > 6)]
    # "State capitals" means U.S. states; "world capitals" or "countries" means the world.
    if "state" in t and "world_capitals" in kinds and "world" not in t:
        kinds.remove("world_capitals")
    if ("world" in t or "countr" in t) and "state_capitals" in kinds and "state" not in t:
        kinds.remove("state_capitals")
    tags = {tag for *_, ts in DATES for tag in ts if tag in t}
    if tags:
        kinds.append("dates")
    if not kinds and course_id == "social-studies":
        kinds = list(COURSE_FACTS["social-studies"])
    return kinds, (tags or None)


def questions_for(course_id, topic, n, seed=None):
    """Up to n verified questions for a topic (fewer, or none, if the bank doesn't cover it)."""
    kinds, tags = kinds_for(course_id, topic)
    if not kinds:
        return []
    rng = random.Random(seed)
    out, seen = [], set()
    for _ in range(n * 6):
        if len(out) == n:
            break
        q = _make(rng.choice(kinds), rng, tags)
        if q and q["question"] not in seen:
            seen.add(q["question"])
            out.append(q)
    return out
