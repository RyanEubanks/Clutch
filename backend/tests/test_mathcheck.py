import pytest

import mathcheck as m

DIFF_OPTIONS = ["12*(3*x+1)**3", "4*(3*x+1)**3", "12*x*(3*x+1)**3", "(3*x+1)**3"]


def check(**task):
    return m.check_question(task)


def test_correct_key_is_kept():
    r = check(op="diff", expr="(3x+1)^4", options=DIFF_OPTIONS, answer=0, explanation="Chain rule.")
    assert r["answer"] == 0 and r["corrected"] is False and r["verified"] is True
    assert r["explanation"] == "Chain rule."
    assert r["question"] == r"Find $\frac{d}{dx}\left[\left(3 x + 1\right)^{4}\right]$."


def test_wrong_key_is_fixed():
    r = check(op="diff", expr="(3*x+1)**4", options=DIFF_OPTIONS, answer=1, explanation="Wrong!")
    assert r["answer"] == 0 and r["corrected"] is True
    assert "double-checked" in r["explanation"]  # the model's explanation is dropped


def test_true_answer_inserted_when_no_option_is_right():
    r = check(op="diff", expr="sin(x**2)", answer=2,
              options=["cos(x**2)", "2*cos(x)", "x*cos(x**2)", "-2*x*sin(x**2)"])
    assert r["answer"] == 2 and r["options"][2] == r"$2 x \cos{\left(x^{2} \right)}$"


def test_limit_zero_over_zero_is_not_zero():
    # The classic mistake Ryan's tutor prompt warns about.
    r = check(op="limit", expr="(x**2-1)/(x-1)", at="1", options=["0", "2", "1", "oo"], answer=0)
    assert r["options"][r["answer"]] == "$2$" and r["corrected"] is True


def test_integral_ignores_constant_and_letter_answers():
    r = check(op="integrate", expr="2*x*exp(x**2)", answer="A",
              options=["exp(x**2) + C", "2*exp(x**2)", "x**2*exp(x**2)", "exp(2*x)"])
    assert r["answer"] == 0 and not r["corrected"]
    assert r["options"][0] == "$e^{x^{2}} + C$"


def test_antiderivatives_differing_by_constant_count_as_duplicates():
    with pytest.raises(m.MathError):
        check(op="integrate", expr="2*x", answer=0, options=["x**2", "x**2 + 5", "2*x**2", "x"])


def test_definite_evaluate_solve_simplify():
    assert check(op="definite", expr="x**2", lower="0", upper="3",
                 options=["27", "9", "3", "6"], answer=1)["answer"] == 1
    assert check(op="evaluate", expr="x**2 + 2*x", at="3",
                 options=["9", "12", "15", "18"], answer=2)["answer"] == 2
    r = check(op="solve", expr="x**2 - 4*x + 3 = 0", answer=1,
              options=["x = 1, x = 3", "x = -1, x = -3", "x = 3", "x = 0, x = 4"])
    assert r["answer"] == 0 and r["options"][0] == "$x = 1$ or $x = 3$"
    assert check(op="simplify", expr="(x+1)**2", answer=0,
                 options=["x**2+2*x+1", "x**2+1", "x**2+x+1", "2*x+1"])["answer"] == 0


def test_two_correct_options_are_rejected():
    with pytest.raises(m.MathError):
        check(op="diff", expr="x**3", options=["3*x**2", "3x^2", "x**2", "3*x"], answer=0)


@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi')",
    "x.__class__",
    "open('secrets')",
    "lambda: 1",
    "x" * 200,
    "\\frac{1}{x}",
    "foo(x)",
])
def test_unsafe_or_unknown_input_is_refused(expr):
    with pytest.raises(m.MathError):
        m.parse(expr)


def test_bad_tasks_are_refused():
    for task in [
        dict(op="teleport", expr="x", options=DIFF_OPTIONS, answer=0),
        dict(op="diff", expr="x**2", options=["2*x", "x"], answer=0),
        dict(op="limit", expr="1/x", at="0", options=["0", "1", "oo", "-oo"], answer=2),  # no limit
    ]:
        with pytest.raises(m.MathError):
            m.check_question(task)


def test_check_questions_runs_in_workers_and_reports_errors():
    good = dict(op="diff", expr="x**2", options=["2*x", "x", "2", "x**2"], answer=0)
    bad = dict(op="diff", expr="foo(x)", options=["1", "2", "3", "4"], answer=0)
    (r1, e1), (r2, e2) = m.check_questions([good, bad])
    assert r1["answer"] == 0 and e1 is None
    assert r2 is None and "unknown name" in e2


def test_timeout_drops_question_and_recovers():
    q = dict(op="diff", expr="x**2", options=["2*x", "x", "2", "x**2"], answer=0)
    m.check_questions([q])  # warm up the pool
    (r, err), = m.check_questions([q], timeout=0.000001)
    assert r is None and err == "timed out"
    (r, err), = m.check_questions([q])  # a fresh pool works again
    assert r["answer"] == 0


def test_negative_values_are_checked():
    # These pairs agree for every positive x, so positive-only spot checks call them equal.
    assert not m.equivalent(m.parse("abs(x)"), m.parse("x"))
    assert not m.equivalent(m.parse("sqrt(x**2)"), m.parse("x"))
    assert not m.equivalent(m.parse("log(x**2)"), m.parse("2*log(x)"))
    assert m.equivalent(m.parse("(x+1)**2"), m.parse("x**2 + 2*x + 1"))


def test_sqrt_x_squared_is_not_x():
    r = check(op="simplify", expr="sqrt(x**2)", options=["x", "x**2", "-x", "2*x"], answer=0)
    assert r["corrected"] is True and r["model_said"] == "$x$"
    assert r["options"][r["answer"]] == r"$\left|{x}\right|$"
    assert r["question"] == r"Which expression is equivalent to $\sqrt{x^{2}}$?"  # shown as written


def test_log_abs_x_is_an_antiderivative_of_one_over_x():
    r = check(op="integrate", expr="1/x", options=["log(abs(x))", "-1/x**2", "x", "exp(x)"], answer=0)
    assert r["answer"] == 0 and not r["corrected"] and r["model_said"] is None


def test_bars_mean_absolute_value():
    assert m.equivalent(m.parse("ln|x|"), m.parse("log(abs(x))"))
    r = check(op="integrate", expr="1/x", options=["ln|x| + C", "-1/x**2", "x", "exp(x)"], answer=0)
    assert r["answer"] == 0 and not r["corrected"]
    with pytest.raises(m.MathError):
        m.parse("|x")  # unmatched bar is still refused
