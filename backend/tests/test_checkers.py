"""Tests for the subject checkers: statistics, geometry, physics, chemistry, Spanish,
English, the fact bank, and checking against notes. Expected answers are textbook values."""
import pytest

import factbank
import groundcheck
import langcheck
import mathcheck as m
import sciencecheck
import valuecheck


def check(**task):
    return m.check_question(task)


def key(result):
    return result["options"][result["answer"]]


# ---------- statistics ----------

@pytest.mark.parametrize("task, expected", [
    (dict(op="mean", data=[3, 5, 7, 7, 9], options=["6.2", "7", "5", "6"]), "6.2"),
    (dict(op="median", data=[4, 1, 9, 6], options=["5", "6", "4", "5.5"]), "5"),
    (dict(op="mode", data=[2, 3, 3, 4], options=["3", "2", "4", "12"]), "3"),
    (dict(op="range", data=[2, 9, 4], options=["7", "5", "9", "2"]), "7"),
    (dict(op="stdev", data=[2, 4, 4, 4, 5, 5, 7, 9], options=["2", "2.14", "4", "5"]), "2"),
    (dict(op="stdev", data=[2, 4, 4, 4, 5, 5, 7, 9], sample=True, options=["2", "2.14", "4", "5"]), "2.14"),
    (dict(op="combinations", n=5, k=2, options=["10", "20", "25", "5"]), "10"),
    (dict(op="permutations", n=5, k=2, options=["10", "20", "25", "5"]), "20"),
    (dict(op="binomial", n=3, k=1, p="0.5", options=["0.375", "0.5", "0.125", "0.25"]), "0.375"),
    (dict(op="normal", mean=0, sd=1, lower=-1, upper=1, options=["0.6827", "0.95", "0.5", "0.34"]), "0.6827"),
    (dict(op="normal", mean=100, sd=15, upper=130, options=["0.9772", "0.8413", "0.5", "0.0228"]), "0.9772"),
    (dict(op="zscore", x=130, mean=100, sd=15, options=["2", "1.5", "-2", "30"]), "2"),
])
def test_statistics(task, expected):
    for claimed in range(4):  # whatever the model claimed, the key ends up right
        assert key(check(**task, answer=claimed)) == expected


def test_whole_number_option_is_exact_next_to_decimals():
    # "6" must not count as a rounded 6.2 when another option shows decimals.
    r = check(op="mean", data=[3, 5, 7, 7, 9], options=["6.2", "7", "5", "6"], answer=3)
    assert key(r) == "6.2" and r["corrected"]


def test_mode_must_be_unique():
    with pytest.raises(m.MathError):
        check(op="mode", data=[1, 1, 2, 2], options=["1", "2", "3", "4"], answer=0)


# ---------- geometry ----------

@pytest.mark.parametrize("task, expected", [
    (dict(op="area", shape="circle", r=5, unit="cm", options=["25pi", "10pi", "5pi", "50pi"]), "25pi"),
    (dict(op="area", shape="circle", d=10, options=["78.54", "31.42", "314.16", "15.71"]), "78.54"),
    (dict(op="area", shape="triangle", b=6, h=4, options=["12", "24", "10", "6"]), "12"),
    (dict(op="area", shape="trapezoid", a=3, b=5, h=4, options=["16", "32", "15", "60"]), "16"),
    (dict(op="perimeter", shape="rectangle", l=3, w=4, options=["14", "12", "7", "24"]), "14"),
    (dict(op="perimeter", shape="circle", r=1, options=["6.28", "3.14", "12.57", "1"]), "6.28"),
    (dict(op="volume", shape="cylinder", r=2, h=5, options=["20pi", "10pi", "40pi", "5pi"]), "20pi"),
    (dict(op="volume", shape="sphere", r=3, options=["36pi", "27pi", "12pi", "9pi"]), "36pi"),
    (dict(op="hypotenuse", a=5, b=12, options=["13", "17", "7", "60"]), "13"),
    (dict(op="leg", c=10, a=6, options=["8", "4", "16", "12"]), "8"),
    (dict(op="missing_angle", angles=[50, 60], options=["70", "80", "110", "90"]), "70"),
    (dict(op="angle_sum", sides=6, options=["720", "540", "1080", "360"]), "720"),
    (dict(op="regular_angle", sides=6, options=["120", "60", "108", "135"]), "120"),
    (dict(op="distance", points=[[1, 2], [4, 6]], options=["5", "7", "25", "3"]), "5"),
])
def test_geometry(task, expected):
    assert key(check(**task, answer=0 if task["options"][0] != expected else 1)) == expected


def test_exact_and_decimal_duplicates_are_dropped():
    # 25pi and 78.54 are the same area, so two options would be "correct".
    with pytest.raises(m.MathError):
        check(op="area", shape="circle", r=5, options=["25pi", "10pi", "78.54", "5pi"], answer=0)


def test_geometry_rejects_impossible_shapes():
    with pytest.raises(m.MathError):
        check(op="perimeter", shape="triangle", a=1, b=2, c=10, options=["13", "1", "2", "3"], answer=0)


# ---------- physics ----------

def physics(law, given, find, unit, options, answer=0):
    return check(op="physics", law=law, given=given, find=find, unit=unit, options=options, answer=answer)


def test_physics_answers_with_units():
    assert key(physics("kinetic_energy", {"m": "2 kg", "v": "3 m/s"}, "K", "J",
                       ["9 J", "6 J", "18 J", "3 J"], 1)) == "9 J"
    assert key(physics("speed", {"d": "100 m", "t": "20 s"}, "v", "km/h",
                       ["18 km/h", "5 km/h", "2000 km/h", "50 km/h"])) == "18 km/h"
    assert key(physics("force", {"m": "1500 g", "a": "2 m/s^2"}, "F", "N",
                       ["3 N", "3000 N", "750 N", "1.5 N"])) == "3 N"
    assert key(physics("ohms_law", {"I": "2 A", "R": "5 ohm"}, "V", "V",
                       ["10 V", "7 V", "2.5 V", "3 V"])) == "10 V"
    assert key(physics("velocity_squared", {"u": "0 m/s", "a": "9.8 m/s^2", "d": "20 m"}, "v", "m/s",
                       ["19.8 m/s", "196 m/s", "14 m/s", "9.8 m/s"])) == "19.8 m/s"
    assert key(physics("density", {"m": "10 g", "V": "2 mL"}, "r", "g/mL",
                       ["5 g/mL", "20 g/mL", "0.2 g/mL", "12 g/mL"])) == "5 g/mL"


def test_physics_unit_mismatch_is_not_correct():
    r = physics("kinetic_energy", {"m": "2 kg", "v": "3 m/s"}, "K", "J", ["9 kJ", "6 J", "18 J", "3 J"], 0)
    assert r["corrected"] and key(r) == "9 J"  # "9 kJ" is not 9 J
    # An equivalent value in another unit of the right kind does count.
    r = physics("kinetic_energy", {"m": "2 kg", "v": "300 m/s"}, "K", "J", ["90 kJ", "6 J", "18 J", "3 J"], 0)
    assert key(r) == "90 kJ" and not r["corrected"]


@pytest.mark.parametrize("bad", [
    dict(law="kinetic_energy", given={"m": "2 kg", "v": "3 kg"}, find="K", unit="J"),     # v in kg
    dict(law="kinetic_energy", given={"m": "2 kg"}, find="K", unit="J"),                  # missing v
    dict(law="kinetic_energy", given={"m": "2 kg", "v": "3 m/s"}, find="K", unit="m"),     # wrong unit
    dict(law="teleport", given={}, find="x", unit="m"),
    dict(law="speed", given={"d": "100 parsecs", "t": "2 s"}, find="v", unit="m/s"),
])
def test_physics_rejects_bad_tasks(bad):
    with pytest.raises(m.MathError):
        check(op="physics", options=["1 J", "2 J", "3 J", "4 J"], answer=0, **bad)


def test_every_law_solves_for_every_variable():
    """Each law can be asked for any of its variables (with some sensible set of values)."""
    import itertools
    si = {sciencecheck._dims(L=1, T=-1): "m/s", sciencecheck._dims(L=1, T=-2): "m/s^2",
          sciencecheck._dims(M=1, L=1, T=-1): "kg*m/s", sciencecheck._dims(M=1, L=-3): "kg/m^3",
          sciencecheck._dims(L=2): "m^2", sciencecheck._dims(L=3): "m^3"}
    for unit, (factor, dims) in sciencecheck.UNITS.items():
        if factor == 1:
            si.setdefault(dims, unit)
    for name, law in sciencecheck.LAWS.items():
        for find in law["vars"]:
            others = [v for v in law["vars"] if v != find]
            solved = False
            for values in itertools.product([1, 4, 30], repeat=len(others)):
                given = {v: f"{x} {si[law['vars'][v][1]]}" for v, x in zip(others, values)}
                try:
                    task = valuecheck.BUILDERS["physics"](
                        {"law": name, "given": given, "find": find, "unit": si[law["vars"][find][1]]})
                except m.MathError:
                    continue
                assert task.truth > 0
                solved = True
                break
            assert solved, (name, find)


# ---------- chemistry ----------

@pytest.mark.parametrize("formula, expected", [
    ("H2O", 18.015), ("NaCl", 58.44), ("CO2", 44.009), ("H2SO4", 98.072),
    ("Ca(OH)2", 74.092), ("Al2(SO4)3", 342.14), ("C6H12O6", 180.156), ("CuSO4·5H2O", 249.68),
])
def test_molar_masses(formula, expected):
    assert abs(float(sciencecheck.molar_mass(formula)) - expected) < 0.02


def test_molar_mass_rounding_differences_are_tolerated():
    # 98.08 is the common textbook value; our table gives 98.072.
    assert key(check(op="molar_mass", formula="H2SO4", answer=1,
                     options=["98.08 g/mol", "96.06 g/mol", "49.04 g/mol", "100.1 g/mol"])) == "98.08 g/mol"


@pytest.mark.parametrize("equation, coeffs", [
    ("H2 + O2 -> H2O", [2, 1, 2]),
    ("CH4 + O2 -> CO2 + H2O", [1, 2, 1, 2]),
    ("Fe + O2 -> Fe2O3", [4, 3, 2]),
    ("C3H8 + O2 -> CO2 + H2O", [1, 5, 3, 4]),
    ("Al + HCl -> AlCl3 + H2", [2, 6, 2, 3]),
])
def test_balancing(equation, coeffs):
    assert sciencecheck.balance(equation)[2] == coeffs


def test_balance_question_accepts_equation_options():
    r = check(op="balance", equation="CH4 + O2 -> CO2 + H2O", answer=1,
              options=["CH4 + 2O2 -> CO2 + 2H2O", "CH4 + O2 -> CO2 + H2O",
                       "2CH4 + O2 -> 2CO2 + H2O", "CH4 + 3O2 -> CO2 + 2H2O"])
    assert r["answer"] == 0 and r["corrected"]


def test_ph():
    assert key(check(op="ph", h="1e-3", options=["3", "-3", "11", "0.001"], answer=1)) == "3"
    assert key(check(op="ph", ph=4, options=["0.0001 M", "4 M", "10000 M", "0.004 M"], answer=1)) == "0.0001 M"


def test_unknown_elements_are_refused():
    with pytest.raises(m.MathError):
        sciencecheck.molar_mass("Xx2O")


# ---------- Spanish ----------

@pytest.mark.parametrize("verb, forms", [
    ("hablar", "hablo hablas habla hablamos habláis hablan"),
    ("comer", "como comes come comemos coméis comen"),
    ("vivir", "vivo vives vive vivimos vivís viven"),
    ("ser", "soy eres es somos sois son"),
    ("estar", "estoy estás está estamos estáis están"),
    ("ir", "voy vas va vamos vais van"),
    ("tener", "tengo tienes tiene tenemos tenéis tienen"),
    ("pensar", "pienso piensas piensa pensamos pensáis piensan"),
    ("preferir", "prefiero prefieres prefiere preferimos preferís prefieren"),
    ("poder", "puedo puedes puede podemos podéis pueden"),
    ("recordar", "recuerdo recuerdas recuerda recordamos recordáis recuerdan"),
    ("pedir", "pido pides pide pedimos pedís piden"),
    ("jugar", "juego juegas juega jugamos jugáis juegan"),
    ("hacer", "hago haces hace hacemos hacéis hacen"),
    ("conocer", "conozco conoces conoce conocemos conocéis conocen"),
    ("construir", "construyo construyes construye construimos construís construyen"),
    ("seguir", "sigo sigues sigue seguimos seguís siguen"),
    ("saber", "sé sabes sabe sabemos sabéis saben"),
])
def test_spanish_conjugations(verb, forms):
    assert langcheck.conjugate(verb) == forms.split()


def test_spanish_question_fixes_key_and_accents_matter():
    r = check(op="conjugate", verb="estar", person="ellos", answer=0,
              options=["estan", "estamos", "son", "estás"])
    assert key(r) == "están" and r["corrected"]  # "estan" without the accent is misspelled
    r = check(op="conjugate", verb="tener", person="nosotros", answer=1,
              options=["nosotros tenemos", "tienemos", "tenimos", "tienen"])
    assert r["answer"] == 0


def test_spanish_unknown_verbs_and_other_tenses_are_not_guessed():
    with pytest.raises(m.MathError):
        check(op="conjugate", verb="florecer", person="yo", options=["a", "b", "c", "d"], answer=0)
    with pytest.raises(m.MathError):
        check(op="conjugate", verb="hablar", person="yo", tense="preterite", options=["a", "b", "c", "d"], answer=0)


# ---------- English ----------

def test_english_verbs_and_plurals():
    assert key(check(op="english_verb", verb="swim", form="past", answer=1,
                     options=["swam", "swum", "swimmed", "swims"])) == "swam"
    assert key(check(op="english_verb", verb="get", form="past_participle", answer=1,
                     options=["gotten", "getted", "goted", "gat"])) == "gotten"
    assert key(check(op="plural", noun="mouse", answer=0,
                     options=["mouses", "mice", "meese", "mices"])) == "mice"
    with pytest.raises(m.MathError):  # regular nouns aren't in the table: not guessed
        check(op="plural", noun="computer", options=["computers", "a", "b", "c"], answer=0)


# ---------- fact bank ----------

def test_fact_bank_is_consistent():
    assert len(factbank.STATE_CAPITALS) == 50
    assert len(factbank.PRESIDENTS) == 45 and factbank.PRESIDENTS[15] == "Abraham Lincoln"
    assert factbank.PRESIDENTS[21] == factbank.PRESIDENTS[23] == "Grover Cleveland"
    for kind in ["state_capitals", "world_capitals", "presidents", "amendments", "government", "dates"]:
        import random
        rng = random.Random(0)
        for _ in range(60):
            q = factbank._make(kind, rng)
            assert len(q["options"]) == 4 and len(set(q["options"])) == 4, q
            assert 0 <= q["answer"] < 4 and q["verified"] and q["checked_by"] == "facts"


def test_fact_questions_are_right():
    qs = factbank.questions_for("geography", "State capitals", 20, seed=3)
    for q in qs:
        state = q["question"].removeprefix("What is the capital of ").rstrip("?")
        assert q["options"][q["answer"]] == factbank.STATE_CAPITALS[state]
    years = factbank.questions_for("us-history", "Civil War", 3, seed=1)
    assert {q["options"][q["answer"]] for q in years} <= {"1861", "1863", "1865"}


def test_fact_bank_only_covers_what_it_knows():
    assert factbank.questions_for("us-history", "Industrial era", 5) == []
    assert factbank.questions_for("biology", "Cells", 5) == []
    assert all("state" not in q["question"].lower() or "united states" in q["question"].lower()
               for q in factbank.questions_for("geography", "World capitals", 10, seed=1))


# ---------- notes ----------

NOTES = """# Cells
The mitochondria is the powerhouse of the cell: it makes energy (ATP) through cellular respiration.
**Ribosomes** build proteins. The nucleus stores the cell's DNA and controls its activities."""


def test_notes_check_confirms_and_fixes_keys():
    q = {"question": "What do ribosomes do?", "options": ["Build proteins", "Store DNA", "Make energy",
         "Digest food"], "source": "Ribosomes build proteins."}
    assert groundcheck.check_grounded({**q, "answer": 0}, NOTES)["corrected"] is False
    fixed = groundcheck.check_grounded({**q, "answer": 2}, NOTES)
    assert fixed["answer"] == 0 and fixed["corrected"] and fixed["checked_by"] == "notes"


@pytest.mark.parametrize("source", [
    "Ribosomes digest food for the cell.",    # not in the notes
    "The nucleus stores the cell's RNA.",      # one word changed
    "",                                        # no source
])
def test_notes_check_refuses_made_up_quotes(source):
    q = {"question": "What do ribosomes do?", "options": ["Build proteins", "Store DNA", "Make energy",
         "Digest food"], "answer": 0, "source": source}
    with pytest.raises(m.MathError):
        groundcheck.check_grounded(q, NOTES)


def test_notes_check_tolerates_punctuation():
    assert groundcheck.find_in_notes("The nucleus stores the cells DNA, and controls its activities", NOTES)
