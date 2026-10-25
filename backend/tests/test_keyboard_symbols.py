"""Symbols the symbol keyboard (and phone keyboards) type must be read correctly by the
math checker: a √ it skipped used to make "√(16) + 1 = 5" be checked as "(16) + 1 = 5"."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mathcheck as m  # noqa: E402


@pytest.mark.parametrize("answer, correct", [
    ("√(16) + 1 = 5", True),
    ("√(16) + 1 = 6", False),
    ("√16 = 4", True),
    ("√ 9 = 3", True),
    ("√(√(16)) = 2", True),
    ("√(9 + 16) = 5", True),
    ("3² + 4² = 25", True),
    ("3² + 4² = 24", False),
    ("10⁻¹ = 0.1", True),
    ("6 × 7 = 42", True),
    ("12 ÷ 4 = 3", True),
    ("7 − 2 = 5", True),
])
def test_keyboard_symbols_are_checked_whole(answer, correct):
    claims = m.find_claims(answer)["claims"]
    assert len(claims) == 1 and claims[0]["correct"] is correct


@pytest.mark.parametrize("half_typed", ["is it √(", "what is √", "√( = 4"])
def test_half_typed_roots_are_left_alone(half_typed):
    assert m.find_claims(half_typed)["claims"] == []


def test_parse_reads_roots_and_superscripts():
    assert str(m.parse("√(x) + x²")) == "sqrt(x) + x**2"
    assert str(m.parse("√(√(x))")) == "x**(1/4)"
