"""Check quiz questions whose answer is a computed number: statistics, geometry, and the
science checkers in sciencecheck.py.

Same idea as mathcheck.py: the model describes the problem as a task (an "op" plus its
numbers), we compute the true answer, compare every option, fix a wrong key, and write the
question text ourselves from the same numbers, so what the student sees is what was checked.

Options may be rounded ("78.54", "0.68", "68%", "6.02e23") and may carry units
("78.54 cm^2", "300 J"). A rounded option counts as right when it's the true answer rounded
to the number of decimal places it shows. Exact options ("25 pi", "sqrt(2)", "3/4") are
compared exactly.
"""
import re

import sympy as sp

import mathcheck as mc
from mathcheck import MathError

BUILDERS = {}  # op -> function(task) -> Task


class Task:
    """A computed question: the text to show, the true value, and how to show/compare it."""

    def __init__(self, question, truth, unit=None, checked_by="math", unit_check=None,
                 exact=False):
        self.question = question
        self.truth = sp.nsimplify(truth) if exact else truth
        self.unit = unit  # shown after numbers, e.g. "cm^2" or "J"
        self.checked_by = checked_by
        # unit_check(option_unit_text) -> factor to convert the option into self.unit's
        # terms, or None if the option's unit is wrong. None means units are ignored.
        self.unit_check = unit_check
        self.exact = exact  # answers are exact (counts, fractions): no rounding allowed


def op(name):
    def register(fn):
        BUILDERS[name] = fn
        return fn
    return register


# ---------- reading numbers from options ----------

def _prep(text):
    text = str(text).strip().strip("$").strip()
    text = text.replace("\\pi", "pi").replace("π", "pi").replace("\\times", "*").replace("×", "*")
    text = text.replace("\\cdot", "*").replace("−", "-").replace("\\%", "%").replace(",", "")
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", text)
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", text)
    text = re.sub(r"\\(text|mathrm)\{([^{}]*)\}", r" \2", text)
    text = text.replace("{", "").replace("}", "")
    # 6.02e23 / 1.2E-3 -> *10**(...) (before splitting numbers from unit letters)
    text = re.sub(r"(\d)[eE]([+-]?\d+)", r"\1*10^(\2)", text)
    # "5cm" -> "5 cm", but keep "25pi", "2sqrt(3)"
    text = re.sub(r"(\d)(?!pi\b|sqrt)([A-Za-zµΩ°])", r"\1 \2", text)
    return re.sub(r"\s+", " ", text).strip()


def read_number(text):
    """'78.54 cm^2' -> (value, tolerance, 'cm^2'). Tolerance is half a unit in the last
    decimal place shown (0 for exact forms like 3/4 or 25 pi)."""
    raw = _prep(text)
    percent = raw.endswith("%")
    raw = raw.rstrip("%").strip()
    tokens = raw.split(" ")
    for k in range(len(tokens), 0, -1):
        head, unit = " ".join(tokens[:k]), " ".join(tokens[k:]).strip()
        try:
            value = mc.parse(head)
        except MathError:
            continue
        if not value.is_number:
            continue
        if re.search(r"pi|sqrt|/", head) or not re.search(r"\.", head) and "10^" not in head:
            tol = 0 if re.search(r"pi|sqrt|/", head) else 0.5
        else:
            mantissa = re.match(r"\s*-?\d*\.?(\d*)", head)
            decimals = len(mantissa.group(1)) if mantissa else 0
            exp = re.search(r"10\^\(?([+-]?\d+)\)?", head)
            tol = 0.5 * 10 ** (-decimals) * (10 ** int(exp.group(1)) if exp else 1)
        if percent:
            value, tol = value / 100, tol / 100
        return value, tol, unit
    raise MathError(f"option is not a number: {text!r}")


def _close(value, tol, truth, exact):
    try:
        v, t = complex(sp.N(value, 30)), complex(sp.N(truth, 30))
    except (TypeError, ValueError):
        return False
    if exact or tol == 0:
        return abs(v - t) <= 1e-9 * (1 + abs(t))
    return abs(v - t) <= tol * (1 + 1e-9) + 1e-12 * abs(t)


def _is_exact(value):
    """Integers, simple fractions, and forms with pi or roots are shown exactly."""
    if value.is_Rational:
        return value.q < 1000
    return value.has(sp.pi) or any(isinstance(a, sp.Pow) and not a.exp.is_Integer
                                   for a in sp.preorder_traversal(value))


def _show(value, task, decimals):
    if task.exact or _is_exact(value):
        text = str(value) if value.is_Integer else f"${sp.latex(sp.nsimplify(value))}$"
    else:
        text = f"{float(value):.{decimals}f}"
    return f"{text} {task.unit}" if task.unit else text


def check_value_task(q):
    """Verify a computed-number question. Same result shape as mathcheck.check_question."""
    task = BUILDERS[str(q.get("op")).strip().lower()](q)
    raw_options = q.get("options") or []
    if len(raw_options) != 4:
        raise MathError("need exactly 4 options")
    parsed = [list(read_number(o)) for o in raw_options]
    # A whole number like "6" only counts as "rounded" when every option is a whole
    # number. Next to "6.2", a bare "6" means exactly 6.
    wholes = [i for i, o in enumerate(raw_options) if parsed[i][1] == 0.5]
    if len(wholes) < 4:
        for i in wholes:
            parsed[i][1] = 0

    def matches(i, value):
        v, tol, unit = parsed[i]
        if task.unit_check is not None:
            factor = task.unit_check(unit)
            if factor is None:
                return False  # wrong unit, e.g. "300 kJ" when the answer is 300 J
            v, tol = v * factor, tol * factor
        rel = getattr(task, "min_rel_tol", 0)
        if rel and not task.exact:
            tol = max(tol, rel * abs(float(sp.N(value))))
        return _close(v, tol, value, task.exact)

    claimed = mc._claimed_index(q.get("answer"))
    right = [i for i in range(4) if matches(i, task.truth)]
    if len(right) > 1:
        raise MathError("more than one option is correct")
    for i in range(4):
        for j in range(i + 1, 4):
            if parsed[i][0] == parsed[j][0] and parsed[i][2] == parsed[j][2]:
                raise MathError("two options are the same")

    shown = [str(o).strip() for o in raw_options]
    if right:
        answer = right[0]
    else:
        answer = claimed if claimed is not None else 0
        decimals = max((len(m.group(1)) for o in raw_options
                        if (m := re.search(r"\.(\d+)", str(o)))), default=2)
        shown[answer] = _show(task.truth, task, decimals)
    corrected = answer != claimed or not right
    explanation = str(q.get("explanation") or "").strip()
    if corrected or not explanation:
        explanation = (f"Mother Hen double-checked this with a calculator: the correct answer "
                       f"is {shown[answer]}.")
    return {
        "question": task.question,
        "options": shown,
        "answer": answer,
        "explanation": explanation,
        "verified": True,
        "corrected": corrected,
        "model_said": shown[claimed] if (corrected and claimed is not None and right) else (
            str(raw_options[claimed]).strip() if corrected and claimed is not None else None),
        "checked_by": task.checked_by,
    }


# ---------- shared helpers for builders ----------

def num(task, key, positive=False):
    value = task.get(key)
    if value is None or value == "":
        raise MathError(f"missing {key!r}")
    value = mc.parse(_prep(value)) if not isinstance(value, (int, float)) else sp.nsimplify(value)
    if not value.is_number:
        raise MathError(f"{key!r} must be a number")
    if positive and not value > 0:
        raise MathError(f"{key!r} must be positive")
    return value


def data_list(task):
    data = task.get("data")
    if isinstance(data, str):
        data = [d for d in re.split(r"[,\s;]+", data) if d]
    if not isinstance(data, list) or not 2 <= len(data) <= 40:
        raise MathError("data must be a list of 2 to 40 numbers")
    values = [mc.parse(_prep(d)) if not isinstance(d, (int, float)) else sp.nsimplify(d) for d in data]
    if not all(v.is_number and v.is_real for v in values):
        raise MathError("data must be numbers")
    return values


def show(value):
    """A number for question text: 7, 2.5, 3/4."""
    value = sp.nsimplify(value)
    if value.is_Integer:
        return str(value)
    if value.is_Rational and value.q <= 100:
        return f"{value.p}/{value.q}"
    return f"{float(value):g}"


def _int(task, key, lo=0, hi=1000):
    value = num(task, key)
    if not value.is_Integer or not lo <= value <= hi:
        raise MathError(f"{key!r} must be a whole number from {lo} to {hi}")
    return int(value)


# ---------- statistics ----------

STAT_NAMES = {"mean": "mean", "median": "median", "mode": "mode", "range": "range",
              "variance": "variance", "stdev": "standard deviation"}


def _stat(name):
    def build(task):
        data = data_list(task)
        shown = ", ".join(show(v) for v in data)
        sample = bool(task.get("sample"))
        label = STAT_NAMES[name]
        if name in ("variance", "stdev"):
            label = ("sample " if sample else "population ") + label
        n = len(data)
        mean = sum(data) / n
        if name == "mean":
            truth = mean
        elif name == "median":
            s = sorted(data)
            truth = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
        elif name == "mode":
            counts = {}
            for v in data:
                counts[v] = counts.get(v, 0) + 1
            top = max(counts.values())
            modes = [v for v, c in counts.items() if c == top]
            if top == 1 or len(modes) != 1:
                raise MathError("data needs exactly one mode")
            truth = modes[0]
        elif name == "range":
            truth = max(data) - min(data)
        else:
            if sample and n < 2:
                raise MathError("need 2+ values")
            var = sum((v - mean) ** 2 for v in data) / (n - 1 if sample else n)
            truth = var if name == "variance" else sp.sqrt(var)
        return Task(f"Find the {label} of the data set: {shown}.", truth)
    return build


for _name in STAT_NAMES:
    BUILDERS[_name] = _stat(_name)


@op("combinations")
def _combinations(task):
    n, k = _int(task, "n", 0, 100), _int(task, "k", 0, 100)
    if k > n:
        raise MathError("k > n")
    return Task(f"How many ways can you choose {k} items from {n} different items, "
                f"if order doesn't matter?", sp.binomial(n, k), exact=True)


@op("permutations")
def _permutations(task):
    n, k = _int(task, "n", 0, 100), _int(task, "k", 0, 100)
    if k > n:
        raise MathError("k > n")
    return Task(f"How many ways can you arrange {k} items chosen from {n} different items, "
                f"if order matters?", sp.ff(n, k), exact=True)


@op("binomial")
def _binomial(task):
    n, k = _int(task, "n", 1, 100), _int(task, "k", 0, 100)
    p = num(task, "p")
    if k > n or not 0 < p < 1:
        raise MathError("need 0 <= k <= n and 0 < p < 1")
    return Task(f"In {n} independent trials, each with probability {show(p)} of success, what "
                f"is the probability of exactly {k} successes?",
                sp.binomial(n, k) * p ** k * (1 - p) ** (n - k))


@op("normal")
def _normal(task):
    mu, sd = num(task, "mean"), num(task, "sd", positive=True)
    lo, hi = task.get("lower"), task.get("upper")
    if lo in (None, "") and hi in (None, ""):
        raise MathError("normal needs lower and/or upper")
    cdf = lambda x: (1 + sp.erf((x - mu) / (sd * sp.sqrt(2)))) / 2
    if lo in (None, ""):
        b = num(task, "upper")
        truth, event = cdf(b), f"X < {show(b)}"
    elif hi in (None, ""):
        a = num(task, "lower")
        truth, event = 1 - cdf(a), f"X > {show(a)}"
    else:
        a, b = num(task, "lower"), num(task, "upper")
        if not a < b:
            raise MathError("lower must be below upper")
        truth, event = cdf(b) - cdf(a), f"{show(a)} < X < {show(b)}"
    return Task(f"X is normally distributed with mean {show(mu)} and standard deviation "
                f"{show(sd)}. Find P({event}).", truth)


@op("zscore")
def _zscore(task):
    x, mu, sd = num(task, "x"), num(task, "mean"), num(task, "sd", positive=True)
    return Task(f"Find the z-score of {show(x)} in a distribution with mean {show(mu)} and "
                f"standard deviation {show(sd)}.", (x - mu) / sd)


# ---------- geometry ----------

def _len_unit(task):
    unit = str(task.get("unit") or "").strip()
    if unit and not re.fullmatch(r"[A-Za-z]{1,5}", unit):
        raise MathError("bad unit")
    return unit


def _with(value, unit):
    return f"{show(value)} {unit}".strip()


def _radius(task):
    if task.get("r") not in (None, ""):
        return num(task, "r", positive=True), "radius", num(task, "r")
    d = num(task, "d", positive=True)
    return d / 2, "diameter", d


SHAPES = {"rectangle", "square", "triangle", "circle", "trapezoid", "parallelogram"}


@op("area")
def _area(task):
    shape, u = str(task.get("shape") or "").lower(), _len_unit(task)
    sq = f"{u}^2" if u else None
    if shape == "square":
        s = num(task, "s", positive=True)
        return Task(f"Find the area of a square with side {_with(s, u)}.", s ** 2, sq)
    if shape == "rectangle":
        length, w = num(task, "l", positive=True), num(task, "w", positive=True)
        return Task(f"Find the area of a rectangle that is {_with(length, u)} by {_with(w, u)}.",
                    length * w, sq)
    if shape == "triangle":
        b, h = num(task, "b", positive=True), num(task, "h", positive=True)
        return Task(f"Find the area of a triangle with base {_with(b, u)} and height {_with(h, u)}.",
                    b * h / 2, sq)
    if shape == "parallelogram":
        b, h = num(task, "b", positive=True), num(task, "h", positive=True)
        return Task(f"Find the area of a parallelogram with base {_with(b, u)} and height "
                    f"{_with(h, u)}.", b * h, sq)
    if shape == "trapezoid":
        a, b, h = (num(task, k, positive=True) for k in ("a", "b", "h"))
        return Task(f"Find the area of a trapezoid with parallel sides {_with(a, u)} and "
                    f"{_with(b, u)} and height {_with(h, u)}.", (a + b) * h / 2, sq)
    if shape == "circle":
        r, given, value = _radius(task)
        return Task(f"Find the area of a circle with {given} {_with(value, u)}.", sp.pi * r ** 2, sq)
    raise MathError(f"area: unknown shape {shape!r}")


@op("perimeter")
def _perimeter(task):
    shape, u = str(task.get("shape") or "").lower(), _len_unit(task)
    if shape == "square":
        s = num(task, "s", positive=True)
        return Task(f"Find the perimeter of a square with side {_with(s, u)}.", 4 * s, u or None)
    if shape == "rectangle":
        length, w = num(task, "l", positive=True), num(task, "w", positive=True)
        return Task(f"Find the perimeter of a rectangle that is {_with(length, u)} by "
                    f"{_with(w, u)}.", 2 * (length + w), u or None)
    if shape == "triangle":
        a, b, c = (num(task, k, positive=True) for k in ("a", "b", "c"))
        if not (a + b > c and a + c > b and b + c > a):
            raise MathError("not a triangle")
        return Task(f"Find the perimeter of a triangle with sides {_with(a, u)}, {_with(b, u)} "
                    f"and {_with(c, u)}.", a + b + c, u or None)
    if shape == "circle":
        r, given, value = _radius(task)
        return Task(f"Find the circumference of a circle with {given} {_with(value, u)}.",
                    2 * sp.pi * r, u or None)
    raise MathError(f"perimeter: unknown shape {shape!r}")


@op("volume")
def _volume(task):
    shape, u = str(task.get("shape") or "").lower(), _len_unit(task)
    cu = f"{u}^3" if u else None
    if shape == "cube":
        s = num(task, "s", positive=True)
        return Task(f"Find the volume of a cube with side {_with(s, u)}.", s ** 3, cu)
    if shape in ("box", "rectangular prism", "prism"):
        length, w, h = (num(task, k, positive=True) for k in ("l", "w", "h"))
        return Task(f"Find the volume of a rectangular prism that is {_with(length, u)} by "
                    f"{_with(w, u)} by {_with(h, u)}.", length * w * h, cu)
    if shape == "cylinder":
        r, given, value = _radius(task)
        h = num(task, "h", positive=True)
        return Task(f"Find the volume of a cylinder with {given} {_with(value, u)} and height "
                    f"{_with(h, u)}.", sp.pi * r ** 2 * h, cu)
    if shape == "sphere":
        r, given, value = _radius(task)
        return Task(f"Find the volume of a sphere with {given} {_with(value, u)}.",
                    sp.Rational(4, 3) * sp.pi * r ** 3, cu)
    if shape == "cone":
        r, given, value = _radius(task)
        h = num(task, "h", positive=True)
        return Task(f"Find the volume of a cone with {given} {_with(value, u)} and height "
                    f"{_with(h, u)}.", sp.pi * r ** 2 * h / 3, cu)
    raise MathError(f"volume: unknown shape {shape!r}")


@op("hypotenuse")
def _hypotenuse(task):
    a, b, u = num(task, "a", positive=True), num(task, "b", positive=True), _len_unit(task)
    return Task(f"A right triangle has legs {_with(a, u)} and {_with(b, u)}. How long is the "
                f"hypotenuse?", sp.sqrt(a ** 2 + b ** 2), u or None)


@op("leg")
def _leg(task):
    c, a, u = num(task, "c", positive=True), num(task, "a", positive=True), _len_unit(task)
    if not c > a:
        raise MathError("hypotenuse must be the longest side")
    return Task(f"A right triangle has hypotenuse {_with(c, u)} and one leg {_with(a, u)}. How "
                f"long is the other leg?", sp.sqrt(c ** 2 - a ** 2), u or None)


@op("missing_angle")
def _missing_angle(task):
    angles = task.get("angles")
    if not isinstance(angles, list) or len(angles) != 2:
        raise MathError("missing_angle needs two angles")
    a, b = (num({"v": x}, "v", positive=True) for x in angles)
    if not a + b < 180:
        raise MathError("angles too big")
    return Task(f"Two angles of a triangle are {show(a)}° and {show(b)}°. What is the third "
                f"angle, in degrees?", 180 - a - b)


@op("angle_sum")
def _angle_sum(task):
    n = _int(task, "sides", 3, 100)
    return Task(f"What is the sum of the interior angles of a polygon with {n} sides, in "
                f"degrees?", (n - 2) * 180, exact=True)


@op("regular_angle")
def _regular_angle(task):
    n = _int(task, "sides", 3, 100)
    return Task(f"What is each interior angle of a regular polygon with {n} sides, in degrees?",
                sp.Rational((n - 2) * 180, n))


@op("distance")
def _distance(task):
    pts = task.get("points")
    if not (isinstance(pts, list) and len(pts) == 2 and all(isinstance(p, list) and len(p) == 2 for p in pts)):
        raise MathError("distance needs points [[x1, y1], [x2, y2]]")
    (x1, y1), (x2, y2) = [[num({"v": v}, "v") for v in p] for p in pts]
    return Task(f"Find the distance between ({show(x1)}, {show(y1)}) and ({show(x2)}, {show(y2)}).",
                sp.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))
