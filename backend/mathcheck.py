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


def var_of(task, expr):
    name = str(task.get("var") or "").strip()
    if name:
        if name not in VARS:
            raise MathError(f"bad variable {name!r}")
        return VARS[name]
    free = sorted(expr.free_symbols, key=str)
    return free[0] if free else VARS["x"]


def build(task):
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
        if task.get("at") not in (None, ""):
            at = parse(task.get("at"))
            question = f"Evaluate ${tex(expr)}$ at ${tex(x)} = {tex(at)}$."
            truth = expr.subs(x, at)
        else:
            question = f"Evaluate ${tex(expr)}$."
            truth = expr
        truth = sp.simplify(truth)
        if not truth.is_number:
            raise MathError("evaluate needs a number")
        return question, truth, parse, same_number, render

    # simplify: which option is equivalent to the expression? Show it as written.
    question = f"Which expression is equivalent to ${tex(parse(task.get('expr'), evaluate=False))}$?"
    return question, expr, parse, equivalent, render


def check_question(q):
    """Verify one math question. Returns a clean question dict, or raises MathError.

    Result keys: question, options, answer, explanation, verified (True), corrected.
    """
    question, truth, parse_option, same, render = build(q)
    raw_options = q.get("options") or []
    if len(raw_options) != 4:
        raise MathError("need exactly 4 options")
    options = [parse_option(o) for o in raw_options]

    claimed = q.get("answer")
    if isinstance(claimed, str) and claimed.strip().isdigit():
        claimed = int(claimed.strip())
    if isinstance(claimed, str) and len(claimed.strip()) == 1 and claimed.strip().upper() in "ABCD":
        claimed = "ABCD".index(claimed.strip().upper())
    if not isinstance(claimed, int) or not 0 <= claimed < 4:
        claimed = None

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
    }


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


def check_questions(questions, timeout=None):
    """Check many questions in worker processes. Returns [(result or None, error or None)]."""
    timeout = CHECK_TIMEOUT if timeout is None else timeout
    pool = _get_pool()
    futures = [pool.submit(_check_safely, q) for q in questions]
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
