"""Physics and chemistry checkers for quiz questions.

Physics: the model picks a law from LAWS (a fixed list of standard formulas) and gives the
known values with units. We solve the law for the unknown, with unit conversion and a
dimension check, and write the question text from the law. The model never supplies a
formula, because a wrong formula would make a wrong answer look verified.

Chemistry: molar mass, grams <-> moles, pH, and balancing equations, using standard
atomic weights (IUPAC abridged values).
"""
import re
from fractions import Fraction

import sympy as sp

import langcheck
import mathcheck as mc
import valuecheck as vc
from mathcheck import MathError

# ---------- units: a small SI system (factor to SI, dimensions as kg, m, s, A) ----------

_D = {"M": (1, 0, 0, 0), "L": (0, 1, 0, 0), "T": (0, 0, 1, 0), "I": (0, 0, 0, 1)}


def _dims(**powers):
    out = [0, 0, 0, 0]
    for base, p in powers.items():
        out = [o + p * d for o, d in zip(out, _D[base])]
    return tuple(out)


LENGTH, TIME, MASS, CURRENT = _dims(L=1), _dims(T=1), _dims(M=1), _dims(I=1)
UNITS = {
    "m": (1, LENGTH), "cm": (Fraction(1, 100), LENGTH), "mm": (Fraction(1, 1000), LENGTH),
    "km": (1000, LENGTH),
    "s": (1, TIME), "ms": (Fraction(1, 1000), TIME), "min": (60, TIME), "h": (3600, TIME),
    "hr": (3600, TIME),
    "kg": (1, MASS), "g": (Fraction(1, 1000), MASS),
    "N": (1, _dims(M=1, L=1, T=-2)), "J": (1, _dims(M=1, L=2, T=-2)),
    "kJ": (1000, _dims(M=1, L=2, T=-2)), "W": (1, _dims(M=1, L=2, T=-3)),
    "kW": (1000, _dims(M=1, L=2, T=-3)), "A": (1, CURRENT), "mA": (Fraction(1, 1000), CURRENT),
    "V": (1, _dims(M=1, L=2, T=-3, I=-1)), "ohm": (1, _dims(M=1, L=2, T=-3, I=-2)),
    "Ω": (1, _dims(M=1, L=2, T=-3, I=-2)), "Hz": (1, _dims(T=-1)), "kHz": (1000, _dims(T=-1)),
    "Pa": (1, _dims(M=1, L=-1, T=-2)), "kPa": (1000, _dims(M=1, L=-1, T=-2)),
    "L": (Fraction(1, 1000), _dims(L=3)), "mL": (Fraction(1, 10 ** 6), _dims(L=3)),
}


def parse_unit(text):
    """'m/s^2', 'kg*m/s', 'km/h', 'g/cm³', 'N·s' -> (factor to SI, dimensions)."""
    text = str(text or "").strip().replace("²", "^2").replace("³", "^3").replace("·", "*")
    text = {"ohms": "ohm", "sec": "s", "secs": "s", "seconds": "s", "meters": "m"}.get(text, text)
    if not text:
        raise MathError("missing unit")
    if not re.fullmatch(r"[A-Za-zΩ0-9*/^ \-]+", text):
        raise MathError(f"bad unit {text!r}")
    num, _, den = text.partition("/")
    factor, dims = Fraction(1), [0, 0, 0, 0]
    for part, sign in ((num, 1), (den, -1)):
        for token in re.split(r"[* ]+", part.strip()):
            if not token:
                continue
            m = re.fullmatch(r"([A-Za-zΩ]+)(?:\^(-?\d))?", token)
            if not m or m.group(1) not in UNITS:
                raise MathError(f"unknown unit {token!r}")
            f, d = UNITS[m.group(1)]
            power = sign * int(m.group(2) or 1)
            factor *= Fraction(f) ** power
            dims = [x + power * y for x, y in zip(dims, d)]
    return factor, tuple(dims)


def quantity(text):
    """'9.8 m/s^2' -> (value in SI as a sympy number, dimensions, 'm/s^2', shown text)."""
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(.*?)\s*", str(text))
    if not m:
        raise MathError(f"bad quantity {text!r}")
    factor, dims = parse_unit(m.group(2))
    value = sp.nsimplify(m.group(1), rational=True)
    return value * sp.Rational(factor.numerator, factor.denominator), dims, m.group(2), \
        f"{m.group(1)} {pretty_unit(m.group(2))}"


def pretty_unit(unit):
    return str(unit).replace("^2", "²").replace("^3", "³").replace("*", "·")


def sci(value):
    """0.001 -> '1 × 10⁻³', 0.25 -> '0.25'."""
    v = float(value)
    if v == 0 or 0.01 <= abs(v) < 10000:
        return f"{v:g}"
    mantissa, exp = f"{v:e}".split("e")
    mantissa = mantissa.rstrip("0").rstrip(".")
    sup = str(int(exp)).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
    return f"{mantissa} × 10{sup}"


# ---------- physics laws ----------
# Each variable: symbol name -> (what it is, its dimensions). Equation as text in those names.

def _var(desc, **dims):
    return desc, _dims(**dims) if dims else (0, 0, 0, 0)


LAWS = {
    "speed": {"eq": "d - v*t", "vars": {"d": _var("distance", L=1), "v": _var("speed", L=1, T=-1),
                                       "t": _var("time", T=1)}},
    "velocity": {"eq": "v - (u + a*t)", "vars": {"v": _var("final velocity", L=1, T=-1),
                 "u": _var("initial velocity", L=1, T=-1), "a": _var("acceleration", L=1, T=-2),
                 "t": _var("time", T=1)}},
    "displacement": {"eq": "d - (u*t + a*t**2/2)", "vars": {"d": _var("displacement", L=1),
                     "u": _var("initial velocity", L=1, T=-1),
                     "a": _var("acceleration", L=1, T=-2), "t": _var("time", T=1)}},
    "velocity_squared": {"eq": "v**2 - (u**2 + 2*a*d)", "vars": {
        "v": _var("final speed", L=1, T=-1), "u": _var("initial speed", L=1, T=-1),
        "a": _var("acceleration", L=1, T=-2), "d": _var("distance", L=1)}},
    "force": {"eq": "F - m*a", "vars": {"F": _var("net force", M=1, L=1, T=-2),
              "m": _var("mass", M=1), "a": _var("acceleration", L=1, T=-2)}},
    "weight": {"eq": "W - m*g", "vars": {"W": _var("weight", M=1, L=1, T=-2),
               "m": _var("mass", M=1), "g": _var("gravitational acceleration", L=1, T=-2)}},
    "work": {"eq": "W - F*d", "vars": {"W": _var("work done", M=1, L=2, T=-2),
             "F": _var("force", M=1, L=1, T=-2), "d": _var("distance", L=1)}},
    "kinetic_energy": {"eq": "K - m*v**2/2", "vars": {"K": _var("kinetic energy", M=1, L=2, T=-2),
                       "m": _var("mass", M=1), "v": _var("speed", L=1, T=-1)}},
    "potential_energy": {"eq": "U - m*g*h", "vars": {
        "U": _var("gravitational potential energy", M=1, L=2, T=-2), "m": _var("mass", M=1),
        "g": _var("gravitational acceleration", L=1, T=-2), "h": _var("height", L=1)}},
    "momentum": {"eq": "p - m*v", "vars": {"p": _var("momentum", M=1, L=1, T=-1),
                 "m": _var("mass", M=1), "v": _var("velocity", L=1, T=-1)}},
    "power": {"eq": "P - W/t", "vars": {"P": _var("power", M=1, L=2, T=-3),
              "W": _var("work done", M=1, L=2, T=-2), "t": _var("time", T=1)}},
    "ohms_law": {"eq": "V - I*R", "vars": {"V": _var("voltage", M=1, L=2, T=-3, I=-1),
                 "I": _var("current", I=1), "R": _var("resistance", M=1, L=2, T=-3, I=-2)}},
    "electric_power": {"eq": "P - V*I", "vars": {"P": _var("power", M=1, L=2, T=-3),
                       "V": _var("voltage", M=1, L=2, T=-3, I=-1), "I": _var("current", I=1)}},
    "wave_speed": {"eq": "v - f*w", "vars": {"v": _var("wave speed", L=1, T=-1),
                   "f": _var("frequency", T=-1), "w": _var("wavelength", L=1)}},
    "density": {"eq": "r - m/V", "vars": {"r": _var("density", M=1, L=-3), "m": _var("mass", M=1),
                "V": _var("volume", L=3)}},
    "pressure": {"eq": "P - F/A", "vars": {"P": _var("pressure", M=1, L=-1, T=-2),
                 "F": _var("force", M=1, L=1, T=-2), "A": _var("area", L=2)}},
}


@vc.op("physics")
def _physics(task):
    law = LAWS.get(str(task.get("law") or "").strip().lower())
    if not law:
        raise MathError(f"unknown law {task.get('law')!r}")
    find = str(task.get("find") or "").strip()
    if find not in law["vars"]:
        raise MathError(f"find must be one of {sorted(law['vars'])}")
    given = task.get("given")
    if not isinstance(given, dict) or set(given) != set(law["vars"]) - {find}:
        raise MathError(f"given must have exactly {sorted(set(law['vars']) - {find})}")
    symbols = {name: sp.Symbol(name, positive=True) for name in law["vars"]}
    eq = sp.sympify(law["eq"], locals=symbols)
    values, shown = {}, []
    for name, text in given.items():
        value, dims, _unit, display = quantity(text)
        if dims != law["vars"][name][1]:
            raise MathError(f"{name} has the wrong units: {text!r}")
        values[symbols[name]] = value
        shown.append(f"{law['vars'][name][0]} = {display}")
    solutions = [s for s in sp.solve(eq.subs(values), symbols[find]) if s.is_real and s > 0]
    if len(solutions) != 1:
        raise MathError("the law doesn't give one positive answer")
    want_unit = str(task.get("unit") or "").strip()
    factor, dims = parse_unit(want_unit)
    if dims != law["vars"][find][1]:
        raise MathError(f"unit {want_unit!r} doesn't fit {law['vars'][find][0]}")
    truth = solutions[0] / sp.Rational(factor.numerator, factor.denominator)

    def unit_check(option_unit):
        if not option_unit.strip():
            return 1  # bare number: read it in the unit the question asks for
        try:
            f, d = parse_unit(option_unit)
        except MathError:
            return None
        if d != dims:
            return None
        return sp.Rational(f.numerator, f.denominator) / sp.Rational(factor.numerator, factor.denominator)

    givens = ", ".join(shown[:-1]) + (" and " if len(shown) > 1 else "") + shown[-1]
    return vc.Task(f"Given {givens}, find the {law['vars'][find][0]} in {pretty_unit(want_unit)}.", truth,
                   unit=want_unit, checked_by="science", unit_check=unit_check)


# ---------- chemistry ----------

ATOMIC_WEIGHTS = {
    "H": 1.008, "He": 4.0026, "Li": 6.94, "Be": 9.0122, "B": 10.81, "C": 12.011, "N": 14.007,
    "O": 15.999, "F": 18.998, "Ne": 20.180, "Na": 22.990, "Mg": 24.305, "Al": 26.982,
    "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45, "Ar": 39.95, "K": 39.098, "Ca": 40.078,
    "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845,
    "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Ga": 69.723, "Ge": 72.630,
    "As": 74.922, "Se": 78.971, "Br": 79.904, "Kr": 83.798, "Rb": 85.468, "Sr": 87.62,
    "Ag": 107.87, "Sn": 118.71, "I": 126.90, "Cs": 132.91, "Ba": 137.33, "Pt": 195.08,
    "Au": 196.97, "Hg": 200.59, "Pb": 207.2,
}
# Textbooks round atomic weights differently (S = 32.06 or 32.065), so allow this much
# relative difference on top of the rounding an option shows.
CHEM_REL_TOL = 3e-4


def parse_formula(formula):
    """'Al2(SO4)3' -> {'Al': 2, 'S': 3, 'O': 12}. Also 'CuSO4·5H2O' hydrates."""
    text = str(formula or "").strip().replace(" ", "")
    text = text.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    if not text or len(text) > 40 or not re.fullmatch(r"[A-Za-z0-9()·*.]+", text):
        raise MathError(f"bad formula {formula!r}")
    total = {}
    for part in re.split(r"[·*.]", text):
        m = re.match(r"(\d*)(.*)", part)
        mult, body = int(m.group(1) or 1), m.group(2)
        for el, n in _parse_group(body).items():
            total[el] = total.get(el, 0) + mult * n
    return total


def _parse_group(text):
    stack, i = [{}], 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            stack.append({})
            i += 1
        elif ch == ")":
            m = re.match(r"\)(\d*)", text[i:])
            group = stack.pop()
            if not stack:
                raise MathError("unbalanced parentheses")
            for el, n in group.items():
                stack[-1][el] = stack[-1].get(el, 0) + n * int(m.group(1) or 1)
            i += len(m.group(0))
        else:
            m = re.match(r"([A-Z][a-z]?)(\d*)", text[i:])
            if not m:
                raise MathError(f"bad formula near {text[i:]!r}")
            el = m.group(1)
            if el not in ATOMIC_WEIGHTS:
                raise MathError(f"unknown element {el!r}")
            stack[-1][el] = stack[-1].get(el, 0) + int(m.group(2) or 1)
            i += len(m.group(0))
    if len(stack) != 1:
        raise MathError("unbalanced parentheses")
    return stack[0]


def molar_mass(formula):
    counts = parse_formula(formula)
    return sum(sp.nsimplify(str(ATOMIC_WEIGHTS[el])) * n for el, n in counts.items())


def pretty_formula(formula):
    return re.sub(r"(?<=[A-Za-z)])(\d+)", lambda m: m.group(1).translate(
        str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")), str(formula).strip())


def _chem_task(question, truth, unit):
    task = vc.Task(question, truth, unit=unit, checked_by="science")
    task.min_rel_tol = CHEM_REL_TOL
    return task


@vc.op("molar_mass")
def _molar_mass(task):
    f = task.get("formula")
    return _chem_task(f"What is the molar mass of {pretty_formula(f)}, in g/mol?",
                      molar_mass(f), "g/mol")


@vc.op("moles")
def _moles(task):
    f, grams = task.get("formula"), vc.num(task, "grams", positive=True)
    return _chem_task(f"How many moles are in {vc.show(grams)} g of {pretty_formula(f)}?",
                      grams / molar_mass(f), "mol")


@vc.op("grams")
def _grams(task):
    f, moles = task.get("formula"), vc.num(task, "moles", positive=True)
    return _chem_task(f"What is the mass of {vc.show(moles)} mol of {pretty_formula(f)}, in grams?",
                      moles * molar_mass(f), "g")


@vc.op("ph")
def _ph(task):
    if task.get("h") not in (None, ""):
        h = vc.num(task, "h", positive=True)
        return vc.Task(f"What is the pH of a solution with [H⁺] = {sci(h)} M?",
                       -sp.log(h, 10), checked_by="science")
    ph = vc.num(task, "ph")
    if not 0 <= ph <= 14:
        raise MathError("pH must be 0-14")
    return vc.Task(f"A solution has pH {vc.show(ph)}. What is [H⁺], in mol/L?", 10 ** (-ph),
                   unit="M", checked_by="science")


# Balancing equations: the answer is a list of the smallest whole-number coefficients.

def _species(side):
    out = []
    for term in side.split("+"):
        term = term.strip()
        if not term:
            raise MathError("empty term")
        m = re.fullmatch(r"(\d*)\s*(.+)", term)
        out.append(m.group(2))
    return out


def balance(equation):
    """'H2 + O2 -> H2O' -> (reactants, products, [2, 1, 2])."""
    text = str(equation or "").replace("→", "->").replace("=", "->")
    if text.count("->") != 1:
        raise MathError("equation needs one ->")
    left, right = (_species(s) for s in text.split("->"))
    species = left + right
    elements = sorted({el for s in species for el in parse_formula(s)})
    matrix = sp.Matrix([[parse_formula(s).get(el, 0) * (1 if i < len(left) else -1)
                         for i, s in enumerate(species)] for el in elements])
    null = matrix.nullspace()
    if len(null) != 1:
        raise MathError("equation can't be balanced uniquely")
    vec = null[0]
    lcm = sp.ilcm(*[term.q for term in vec])
    coeffs = [int(term * lcm) for term in vec]
    if any(c == 0 for c in coeffs):
        raise MathError("a species drops out")
    if coeffs[0] < 0:
        coeffs = [-c for c in coeffs]
    if any(c < 0 for c in coeffs):
        raise MathError("can't balance with positive coefficients")
    g = sp.igcd(*coeffs)
    return left, right, [c // g for c in coeffs]


def _coeff_option(text, left, right):
    """'2, 1, 2' or '2H2 + O2 -> 2H2O' -> '2,1,2'."""
    text = str(text).replace("→", "->")
    if "->" in text:
        l2, r2 = text.split("->")
        terms = [t.strip() for t in l2.split("+")] + [t.strip() for t in r2.split("+")]
        coeffs, names = [], []
        for t in terms:
            m = re.fullmatch(r"(\d*)\s*(.+)", t)
            coeffs.append(int(m.group(1) or 1))
            names.append(m.group(2).strip())
        if names != left + right:
            return "?" + text  # a different equation
        return ",".join(map(str, coeffs))
    nums = re.findall(r"\d+", text)
    return ",".join(nums)


@langcheck.op("balance")
def _balance(task):
    left, right, coeffs = balance(task.get("equation"))
    eq = " + ".join(map(pretty_formula, left)) + " → " + " + ".join(map(pretty_formula, right))
    truth = ",".join(map(str, coeffs))
    return langcheck.TextTask(
        f"Balance this equation: {eq}. Which smallest whole-number coefficients, in order, "
        f"balance it?",
        accepted={truth},
        normalize=lambda t: _coeff_option(t, left, right),
        display=", ".join(map(str, coeffs)),
        checked_by="science",
    )
