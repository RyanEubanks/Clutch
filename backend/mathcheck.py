"""Check math quiz questions with SymPy, so answer keys are actually right.

The model describes each math question as a task SymPy can compute, e.g.
    {"op": "diff", "expr": "(3*x+1)**4", "options": ["12*(3*x+1)**3", ...], "answer": 0}
We compute the true answer ourselves, test every option against it, fix the answer
key if the model got it wrong, and render the question and options as LaTeX from
the same expressions we checked, so what the student sees matches what was verified.

Model output is untrusted text, so expressions are whitelisted before parsing
(parse_expr uses eval under the hood), and every check runs in a worker process
with a time limit, because some SymPy calls can run for a very long time.
"""
import os
import random
import re
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

CHECK_TIMEOUT = float(os.getenv("MATHCHECK_TIMEOUT", "8"))  # seconds per question
MAX_LEN = 160

OPS = {"diff", "integrate", "definite", "limit", "evaluate", "simplify", "solve"}

FUNCS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sec": sp.sec, "csc": sp.csc, "cot": sp.cot,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "arcsin": sp.asin, "arccos": sp.acos,
    "arctan": sp.atan, "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "exp": sp.exp, "log": sp.log, "ln": sp.log, "sqrt": sp.sqrt, "abs": sp.Abs, "Abs": sp.Abs,
    "pi": sp.pi, "e": sp.E, "E": sp.E, "oo": sp.oo, "inf": sp.oo, "infinity": sp.oo,
}
# Single letters are variables, except e (Euler's number). Real-valued keeps sqrt/log tidy.
VARS = {c: sp.Symbol(c, real=True) for c in "abcdfghkmnpqrstuvwxyz"}
LOCALS = {**VARS, **FUNCS}
GLOBALS = {
    "__builtins__": {},
    **{name: getattr(sp, name) for name in ("Integer", "Float", "Rational", "Symbol", "Function", "Add", "Mul", "Pow")},
}
TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)
SAFE = re.compile(r"^[0-9A-Za-z+\-*/^().,= ]+$")


class MathError(ValueError):
    """The expression can't be parsed or checked safely."""


# ---------- parsing ----------

def clean(text):
    text = str(text).strip().strip("$").strip()
    text = text.replace("−", "-").replace("·", "*").replace("×", "*").replace("π", "pi")
    # Models often write absolute value as |x| (e.g. ln|x|): turn innermost |...| into abs(...).
    for _ in range(3):
        text = re.sub(r"\|([^|]+)\|", r"(abs(\1))", text)
    return re.sub(r"\s+", " ", text)


def parse(text, evaluate=True):
    """Parse one expression from model output, refusing anything not on the whitelist.

    evaluate=False keeps the expression as written (for displaying a question), so e.g.
    sqrt(x**2) isn't shown already simplified to |x|.
    """
    text = clean(text)
    if not text or len(text) > MAX_LEN or not SAFE.match(text) or "__" in text:
        raise MathError(f"unsafe or empty expression: {text!r}")
    for word in re.findall(r"[A-Za-z]+", text):
        if word not in LOCALS:
            raise MathError(f"unknown name {word!r} in {text!r}")
    try:
        expr = parse_expr(text, local_dict=dict(LOCALS), global_dict=dict(GLOBALS),
                          transformations=TRANSFORMS, evaluate=evaluate)
    except Exception as exc:  # SymPy raises many exception types for bad input
        raise MathError(f"could not parse {text!r}: {exc}") from exc
    if not isinstance(expr, sp.Expr):
        raise MathError(f"not an expression: {text!r}")
    return expr


def parse_equation(text):
    """'x**2 = 4' -> x**2 - 4. A bare expression means expression = 0."""
    parts = clean(text).split("=")
    if len(parts) == 1:
        return parse(parts[0])
    if len(parts) != 2:
        raise MathError(f"bad equation: {text!r}")
    return parse(parts[0]) - parse(parts[1])


def parse_solutions(text):
    """'x = 1, x = 3' or '1, 3' or '{1, 3}' -> a list of values."""
    text = clean(text).strip("{}[]")
    if re.search(r"no (real )?solution", text, re.I):
        return []
    values = []
    for part in text.replace(" or ", ",").replace(" and ", ",").split(","):
        part = re.sub(r"^\s*[a-z]\s*=", "", part.strip())
        if part:
            values.append(parse(part))
    if not values:
        raise MathError(f"no solutions in {text!r}")
    return values


def strip_constant(text):
    """Remove a trailing '+ C' so integral options parse."""
    return re.sub(r"\+\s*C\s*$", "", clean(text)).strip()


# ---------- comparing ----------

def _num(value):
    value = complex(sp.N(value, 30))
    if value != value or abs(value) == float("inf"):  # NaN / inf
        raise ValueError
    return value


def _sample(rng):
    """A test value in [-2.7, -0.3] or [0.3, 2.7]: both signs, away from 0.

    Negative values matter: x and |x|, or sqrt(x**2) and x, agree for every positive x.
    """
    return sp.Rational(rng.randint(30, 270), 100) * rng.choice((1, -1))


def equivalent(a, b):
    """True if a and b are the same expression. Numeric spot checks first, then simplify."""
    diff = a - b
    if diff == 0:
        return True
    symbols = sorted(diff.free_symbols, key=str)
    rng = random.Random(1234)
    close = tried = 0
    for _ in range(16):
        point = {s: _sample(rng) for s in symbols}
        try:
            d, ref = _num(diff.subs(point)), _num(b.subs(point))
        except (ValueError, TypeError, ZeroDivisionError):
            continue
        tried += 1
        if abs(d) > 1e-8 * (1 + abs(ref)):
            return False
        close += 1
        if close >= 6:
            return True
    if tried < 3:  # too few usable points to trust the spot checks
        try:
            return sp.simplify(diff) == 0
        except Exception:
            return False
    return close == tried


def same_number(a, b):
    if a.has(sp.oo, sp.zoo) or b.has(sp.oo, sp.zoo):
        return a == b  # oo, -oo compare structurally; oo - oo would be nan
    try:
        x, y = _num(a), _num(b)
    except (ValueError, TypeError):
        return False
    return abs(x - y) <= 1e-8 * (1 + abs(y))


def same_solutions(a, b):
    if len(a) != len(b):
        return False
    remaining = list(b)
    for v in a:
        match = next((w for w in remaining if same_number(v, w)), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


# ---------- tasks ----------

def tex(expr):
    return sp.latex(expr)


def tex_as_written(text):
    """LaTeX for an expression in the order it was written, without simplifying it.

    Plain-number products use a times sign: "(3+4)*2" -> (3 + 4) \\times 2, not "(3 + 4) 2".
    """
    expr = parse(text, evaluate=False)
    return sp.latex(expr, order="none", mul_symbol="times" if not expr.free_symbols else None)


def var_of(task, expr):
    name = str(task.get("var") or "").strip()
    if name:
        if name not in VARS:
            raise MathError(f"bad variable {name!r}")
        return VARS[name]
    free = sorted(expr.free_symbols, key=str)
    return free[0] if free else VARS["x"]


def build(task):
    if str(task.get("op") or "").strip().lower() not in OPS:
        raise MathError(f"unknown op {task.get('op')!r}")
    return _build(task)


def _build(task):
    """Describe a task: (question_tex, truth, parse_option, same, render_option).

    same(a, b) says whether two answers count as the same answer for this kind of task.
    """
    op = str(task.get("op") or "").strip().lower()
    if op not in OPS:
        raise MathError(f"unknown op {op!r}")

    if op == "solve":
        eq = parse_equation(task.get("expr"))
        x = var_of(task, eq)
        truth = [s for s in sp.solve(eq, x) if s.is_real is not False]
        lhs, _, rhs = clean(task.get("expr")).partition("=")
        shown = f"{tex(parse(lhs))} = {tex(parse(rhs)) if rhs else 0}"
        question = f"Solve ${shown}$ for ${tex(x)}$."
        render = lambda vals: (" or ".join(f"${tex(x)} = {tex(v)}$" for v in vals)
                               if vals else "No real solution")
        return question, truth, parse_solutions, same_solutions, render

    expr = parse(task.get("expr"))
    x = var_of(task, expr)
    render = lambda e: f"${tex(e)}$"

    if op == "diff":
        question = f"Find $\\frac{{d}}{{d{tex(x)}}}\\left[{tex(expr)}\\right]$."
        return question, sp.diff(expr, x), parse, equivalent, render

    if op == "integrate":
        question = f"Find $\\int {tex(expr)}\\,d{tex(x)}$."
        truth = sp.integrate(expr, x)
        if truth.has(sp.Integral):
            raise MathError("SymPy could not integrate this")
        # Antiderivatives that differ by a constant are the same answer: compare derivatives.
        same = lambda a, b: equivalent(sp.diff(a, x), sp.diff(b, x))
        return (question, truth, lambda t: parse(strip_constant(t)), same,
                lambda e: f"${tex(e)} + C$")

    if op == "definite":
        lo, hi = parse(task.get("lower")), parse(task.get("upper"))
        question = f"Evaluate $\\int_{{{tex(lo)}}}^{{{tex(hi)}}} {tex(expr)}\\,d{tex(x)}$."
        truth = sp.integrate(expr, (x, lo, hi))
        if truth.has(sp.Integral):
            raise MathError("SymPy could not integrate this")
        return question, truth, parse, same_number, render

    if op == "limit":
        at = parse(task.get("at"))
        question = f"Find $\\lim_{{{tex(x)} \\to {tex(at)}}} {tex(expr)}$."
        # Two-sided unless approaching infinity; SymPy defaults to the right-hand limit.
        try:
            truth = sp.limit(expr, x, at, dir="+-") if at.is_finite else sp.limit(expr, x, at)
        except ValueError as exc:  # left and right limits differ
            raise MathError(f"limit does not exist: {exc}") from exc
        if truth.has(sp.Limit) or truth == sp.zoo or isinstance(truth, sp.AccumBounds):
            raise MathError("limit does not exist or could not be computed")
        return question, truth, parse, same_number, render

    if op == "evaluate":
        # Show the expression as written: evaluated, "45 + 23" would display as "68".
        shown = tex_as_written(task.get("expr"))
        if task.get("at") not in (None, ""):
            at = parse(task.get("at"))
            question = f"Evaluate ${shown}$ at ${tex(x)} = {tex(at)}$."
            truth = expr.subs(x, at)
        else:
            question = f"Evaluate ${shown}$."
            truth = expr
        truth = sp.simplify(truth)
        if not truth.is_number:
            raise MathError("evaluate needs a number")
        return question, truth, parse, same_number, render

    # simplify: which option is equivalent to the expression? Show it as written.
    question = f"Which expression is equivalent to ${tex_as_written(task.get('expr'))}$?"
    return question, expr, parse, equivalent, render


def _claimed_index(claimed):
    """The model's "answer" as an option index 0-3 (accepts 2, "2", "C"), or None."""
    if isinstance(claimed, str) and claimed.strip().isdigit():
        claimed = int(claimed.strip())
    if isinstance(claimed, str) and len(claimed.strip()) == 1 and claimed.strip().upper() in "ABCD":
        claimed = "ABCD".index(claimed.strip().upper())
    if not isinstance(claimed, int) or isinstance(claimed, bool) or not 0 <= claimed < 4:
        return None
    return claimed


def checker_for(op):
    """Which checker handles an op: 'math' (this file), 'value' (valuecheck: statistics,
    geometry, physics, chemistry) or 'text' (langcheck: Spanish, English). None if unknown."""
    import langcheck  # noqa: F401  (imported here: those modules import this one)
    import sciencecheck  # noqa: F401
    import valuecheck
    op = str(op or "").strip().lower()
    if op in OPS:
        return "math"
    if op in valuecheck.BUILDERS:
        return "value"
    if op in langcheck.BUILDERS:
        return "text"
    return None


def check_question(q):
    """Verify one task-style question. Returns a clean question dict, or raises MathError.

    Result keys: question, options, answer, explanation, verified (True), corrected,
    model_said, checked_by.
    """
    kind = checker_for(q.get("op"))
    if kind == "value":
        import valuecheck
        return valuecheck.check_value_task(q)
    if kind == "text":
        import langcheck
        return langcheck.check_text_task(q)
    question, truth, parse_option, same, render = build(q)
    raw_options = q.get("options") or []
    if len(raw_options) != 4:
        raise MathError("need exactly 4 options")
    options = [parse_option(o) for o in raw_options]

    claimed = _claimed_index(q.get("answer"))

    right = [i for i, o in enumerate(options) if _safe(same, o, truth)]
    if len(right) > 1:
        raise MathError("more than one option is correct")
    if right:
        answer = right[0]
    else:
        # No option is right: put the true answer where the model said the answer was.
        answer = claimed if claimed is not None else 0
        options[answer] = truth

    # Distractors must be genuinely different from each other.
    for i in range(4):
        for j in range(i + 1, 4):
            if _safe(same, options[i], options[j]):
                raise MathError("two options are the same")

    corrected = answer != claimed or not right
    model_said = render(parse_option(raw_options[claimed])) if (corrected and claimed is not None) else None
    explanation = str(q.get("explanation") or "").strip()
    if corrected or not explanation:
        explanation = (f"Mother Hen double-checked this with a math engine: "
                       f"the correct answer is {render(truth)}.")
    return {
        "question": question,
        "options": [render(o) for o in options],
        "answer": answer,
        "explanation": explanation,
        "verified": True,
        "corrected": corrected,
        "model_said": model_said,  # what the model marked correct, when it was wrong
        "checked_by": "math",
    }


# ---------- arithmetic written as a plain-text question ----------
# Small models often write "What is 12 + 7?" as an ordinary question with number options
# instead of a checkable task. These helpers find the arithmetic in the question text.

NUMBER = r"-?\d+(?:\.\d+)?"
WORD_OPS = [
    (rf"\b(?:sum|total) of ({NUMBER}) and ({NUMBER})", "({0}) + ({1})"),
    (rf"\badd ({NUMBER}) (?:and|to) ({NUMBER})", "({0}) + ({1})"),
    (rf"\bproduct of ({NUMBER}) and ({NUMBER})", "({0}) * ({1})"),
    (rf"\bdifference (?:between|of) ({NUMBER}) and ({NUMBER})", "({0}) - ({1})"),
    (rf"\bsubtract ({NUMBER}) from ({NUMBER})", "({1}) - ({0})"),
    (rf"\bquotient of ({NUMBER}) and ({NUMBER})", "({0}) / ({1})"),
    (rf"\b({NUMBER}) (?:plus|added to) ({NUMBER})", "({0}) + ({1})"),
    (rf"\b({NUMBER}) minus ({NUMBER})", "({0}) - ({1})"),
    (rf"\b({NUMBER}) times ({NUMBER})", "({0}) * ({1})"),
    (rf"\b({NUMBER}) divided by ({NUMBER})", "({0}) / ({1})"),
]
# A run of numbers joined by + - * / ^ (and parentheses), e.g. "45 + 23" or "(3 + 4) * 2".
ARITH = re.compile(r"[\d(][\d\s.()+\-*/^?]*[+\-*/^][\d\s.()+\-*/^?]*[\d)?]")
BLANKS = re.compile(r"\\text\{\s*\?\s*\}|\\square|\\_+|_{2,}|\?|□|\[\s*\]")


def _plain_math(text):
    """Turn LaTeX-ish question text into plain arithmetic symbols."""
    text = str(text).replace("\t" + "ext{", "\\text{")  # "\text" mangled into tab + "ext" by JSON
    text = text.replace("$", " ")
    for old, new in (("\\times", "*"), ("\\cdot", "*"), ("\\div", "/"), ("×", "*"),
                     ("÷", "/"), ("−", "-"), ("\\left", ""), ("\\right", ""), (",", "")):
        text = text.replace(old, new)
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", text)
    return BLANKS.sub("?", text)


# One side of a simple equation: numbers, operators, and lone single letters (x, n, ...).
EQ_SIDE = r"((?:[\d.()+\-*/^\s?]|(?<![A-Za-z])[a-df-z](?![A-Za-z]))+)"
EQUATION = re.compile(EQ_SIDE + "=" + EQ_SIDE)


def find_arithmetic(question):
    """The single arithmetic task in a question, as (kind, expression text), or None.

    kind is "value" (compute it) or "blank" (solve "8 + ? = 15" or "7 + x = 12" for
    the one unknown; the unknown is rewritten as "?").
    """
    text = _plain_math(question)
    for eq in EQUATION.finditer(text):
        lhs, rhs = (side.strip().strip(".;:").strip() for side in eq.groups())
        both = f"{lhs} = {rhs}"
        letters = set(re.findall(r"[a-z]", both))
        unknowns = both.count("?") + len(letters)
        if not lhs or not rhs or not re.search(r"\d", both) or unknowns == 0:
            continue
        if both.count("?") == 1 and not letters:
            return "blank", both
        if not both.count("?") and len(letters) == 1:
            return "blank", re.sub(r"[a-z]", "?", both)
    low = text.lower()
    found = {tmpl.format(*m.groups()) for pattern, tmpl in WORD_OPS for m in re.finditer(pattern, low)}
    for m in ARITH.finditer(text):
        candidate = m.group(0).strip().rstrip("?.;: ").strip()
        if "?" in candidate or re.search(r"\d{4}-\d{1,2}", candidate):  # blanks, or dates
            continue
        found.add(candidate)
    found = {f for f in found if re.search(r"\d", f)}
    if len(found) != 1:
        return None  # nothing, or more than one candidate: too ambiguous to check
    return "value", found.pop()


NUMBER_OPTION = re.compile(
    r"\$?\s*(?:[a-df-z]\s*=\s*)?(-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?)\s*\$?(?:\s+[A-Za-z]+){0,2}\s*\.?")


def _number_option(text):
    """'8', '-3.5', '3/4', '$12$', 'x = 5' or '17 apples' -> a number. Anything else is refused."""
    match = NUMBER_OPTION.fullmatch(str(text).strip())
    if not match:
        raise MathError(f"option is not a plain number: {text!r}")
    return parse(match.group(1))


def check_arithmetic(q):
    """Verify a plain-text question whose options are numbers and whose text contains one
    explicit arithmetic task. Returns a question dict like check_question, or raises MathError
    (meaning: leave the question unchecked)."""
    raw_options = q.get("options") or []
    if len(raw_options) != 4:
        raise MathError("need exactly 4 options")
    options = [_number_option(o) for o in raw_options]
    task = find_arithmetic(q.get("question") or "")
    if task is None:
        raise MathError("no single arithmetic expression in the question")
    kind, text = task
    if kind == "blank":
        lhs, rhs = text.replace("?", "b").split("=")
        blank = VARS["b"]
        solutions = sp.solve(parse(lhs) - parse(rhs), blank)
        if len(solutions) != 1:
            raise MathError("the blank doesn't have exactly one answer")
        truth = solutions[0]
    else:
        truth = parse(text)
    truth = sp.nsimplify(truth) if truth.is_number else truth
    if not truth.is_number:
        raise MathError("not a number")

    claimed = q.get("answer") if isinstance(q.get("answer"), int) else None
    right = [i for i, o in enumerate(options) if same_number(o, truth)]
    if len(right) > 1:
        raise MathError("more than one option is correct")
    for i in range(4):
        for j in range(i + 1, 4):
            if same_number(options[i], options[j]):
                raise MathError("two options are the same")
    shown = [str(o).strip() for o in raw_options]
    if right:
        answer = right[0]
    else:
        answer = claimed if claimed is not None and 0 <= claimed < 4 else 0
        shown[answer] = str(truth) if truth.is_Integer else f"${tex(truth)}$"
    corrected = answer != claimed or not right
    model_said = shown_text = None
    if corrected and claimed is not None and 0 <= claimed < 4:
        model_said = str(raw_options[claimed]).strip()
    explanation = str(q.get("explanation") or "").strip()
    if corrected or not explanation:
        shown_text = shown[answer]
        explanation = (f"Mother Hen double-checked this with a math engine: "
                       f"the correct answer is {shown_text}.")
    return {
        "question": q.get("question"),
        "options": shown,
        "answer": answer,
        "explanation": explanation,
        "verified": True,
        "corrected": corrected,
        "model_said": model_said,
        "checked_by": "math",
    }


def _check_arithmetic_safely(q):
    try:
        return check_arithmetic(q), None
    except MathError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _safe(same, a, b):
    try:
        return bool(same(a, b))
    except Exception:
        return False


def _check_safely(q):
    """Worker entry point: never raise, so the pool stays healthy."""
    try:
        return check_question(q), None
    except MathError as exc:
        return None, str(exc)
    except Exception as exc:  # anything else SymPy throws
        return None, f"{type(exc).__name__}: {exc}"


# ---------- running checks with a time limit ----------

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=2)
    return _pool


def _reset_pool():
    """Kill the workers after a timeout; a stuck SymPy call can't be cancelled otherwise."""
    global _pool
    if _pool is not None:
        for proc in list(getattr(_pool, "_processes", {}).values()):
            proc.terminate()
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def check_questions(questions, timeout=None, arithmetic=False):
    """Check many questions in worker processes. Returns [(result or None, error or None)].

    arithmetic=True checks plain-text questions with number options (check_arithmetic)
    instead of task-style math questions (check_question).
    """
    timeout = CHECK_TIMEOUT if timeout is None else timeout
    pool = _get_pool()
    worker = _check_arithmetic_safely if arithmetic else _check_safely
    futures = [pool.submit(worker, q) for q in questions]
    results = []
    timed_out = False
    for f in futures:
        try:
            results.append(f.result(timeout=timeout))
        except FutureTimeout:
            timed_out = True
            results.append((None, "timed out"))
        except Exception as exc:  # worker crashed
            results.append((None, f"worker failed: {exc}"))
    if timed_out:
        _reset_pool()
    return results


# ---------- checking a student's answer in chat ----------
# Before the tutor replies, find any arithmetic answer the student just gave and
# compute whether it's right, so the tutor doesn't have to do the math itself.

BARE_ANSWER = re.compile(
    r"\s*(?:=|is it|it's|it is|its|i got|i get|so it's|so|the answer is|answer:?)?\s*"
    r"(?:[a-df-z]\s*=\s*)?(-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?)\s*[?.!]*\s*", re.I)


def _claim(lhs, rhs):
    """A dict describing the claim lhs = rhs, or None if either side isn't a number."""
    left, right = parse(lhs), parse(rhs)
    if not (left.is_number and right.is_number):
        return None
    return {
        "shown": f"{lhs} = {rhs}",
        "tex": f"{tex_as_written(lhs)} = {tex_as_written(rhs)}",
        "problem_tex": tex_as_written(lhs),
        "correct": same_number(left, right),
    }


def _task_claim(task, answer):
    """Turn a task found by find_arithmetic plus the student's number into a claim."""
    kind, text = task
    if kind == "value":
        return _claim(text, answer)
    lhs, rhs = text.replace("?", "b").split("=")
    solutions = sp.solve(parse(lhs) - parse(rhs), VARS["b"])
    if len(solutions) != 1:
        return None
    shown_problem = text.replace("?", "x")
    return {
        "shown": f"{shown_problem}, so x = {answer}",
        "tex": f"x = {tex_as_written(answer)}",
        "problem_tex": " = ".join(tex_as_written(s) for s in shown_problem.split("=")),
        "correct": same_number(parse(answer), solutions[0]),
    }


def find_claims(student, history=()):
    """Arithmetic answers in the student's latest message, checked.

    Returns {"claims": [...], "posed": problem text or None}. A claim is either written
    out in full ("7 - 2 = 5", "3 + 4 is 7") or a bare answer ("= 1", "5", "x = 5") to the
    one arithmetic problem in the tutor's last message (or the student's own last
    problem). "posed" is set when the student just wrote a problem with no answer ("5-4").
    """
    text = _plain_math(student)
    # "3 + 4 is 7" / "equals 7" -> "3 + 4 = 7"
    text = re.sub(r"(\d\)?)\s+(?:equals|is equal to|is|makes|gives)\s+(?=-?\d)", r"\1 = ", text, flags=re.I)
    claims = []
    for eq in EQUATION.finditer(text):
        lhs, rhs = (side.strip().strip(".;:!").strip() for side in eq.groups())
        if not lhs or not rhs or "?" in lhs + rhs or re.search(r"[a-z]", lhs + rhs):
            continue
        if not re.search(r"[+\-*/^]", lhs.lstrip("-")) and not re.search(r"[+\-*/^]", rhs.lstrip("-")):
            continue  # "5 = 5": nothing to compute
        if re.search(r"[+\-*/^]", rhs.lstrip("-")) and not re.search(r"[+\-*/^]", lhs.lstrip("-")):
            lhs, rhs = rhs, lhs  # "5 = 7 - 2"
        try:
            claim = _claim(lhs, rhs)
        except MathError:
            continue
        if claim:
            claims.append(claim)
    if claims:
        return {"claims": claims, "posed": None}

    bare = BARE_ANSWER.fullmatch(str(student))
    if bare:
        answer = bare.group(1).replace(" ", "")
        earlier = [m for m in reversed(list(history)) if m.get("role") == "assistant"][:1]
        earlier += [m for m in reversed(list(history)) if m.get("role") == "user"]
        for message in earlier:
            task = find_arithmetic(message.get("content") or "")
            if task:
                try:
                    claim = _task_claim(task, answer)
                except MathError:
                    claim = None
                if claim:
                    return {"claims": [claim], "posed": None}
                break
        return {"claims": [], "posed": None}

    # A problem with no answer ("5-4", "what is 12 + 7?"): the student wants help with it.
    words = re.sub(r"[\d\s.()+\-*/^?=]", " ", text).split()
    task = find_arithmetic(text)
    if task and task[0] == "value" and "=" not in text and len(words) <= 4:
        return {"claims": [], "posed": task[1]}
    return {"claims": [], "posed": None}


def _claims_safely(args):
    try:
        return find_claims(*args), None
    except Exception as exc:  # never let checking break the chat
        return {"claims": [], "posed": None}, f"{type(exc).__name__}: {exc}"


def check_chat_answer(student, history=(), timeout=None):
    """find_claims in a worker process with a time limit. Never raises."""
    timeout = CHECK_TIMEOUT if timeout is None else timeout
    pool = _get_pool()
    history = [{"role": m.get("role"), "content": m.get("content")} for m in history][-6:]
    future = pool.submit(_claims_safely, (student, history))
    try:
        result, _error = future.result(timeout=timeout)
        return result
    except FutureTimeout:
        _reset_pool()
    except Exception:
        pass
    return {"claims": [], "posed": None}
