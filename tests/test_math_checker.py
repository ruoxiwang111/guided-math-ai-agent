"""
Tests for core/math_checker.py  (error_taxonomy.md §10.6)

Run from the project root:
    python -m pytest tests/test_math_checker.py -v
"""
import json
import re
from pathlib import Path

import pytest
from sympy import Rational

from core.math_checker import (
    ALL, ALL_VALID, CHAIN_SEGMENT_MISMATCH, INVALID_FOUND, NO_EQUATION, NONE, OTHER,
    START_DIFFERS, TRANSITION_CHANGES_SOLUTION, UNCERTAIN, UNIQUE,
    check_conditions, check_steps, check_value, equivalent, solution_set,
)

ROOT = Path(__file__).resolve().parents[1]
BANK = json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))
BY_ID = {q["question_id"]: q for q in BANK["questions"]}


# ---------------------------------------------------------------------------
# 1. single equations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("eq, kind, values", [
    ("x+5=20", UNIQUE, {15}),
    ("0.8x=160", UNIQUE, {200}),
    ("12x+30(2-x)=36", UNIQUE, {Rational(4, 3)}),
    ("x(1/6+1/3)=1", UNIQUE, {2}),
    ("x+1=x+1", ALL, set()),
    ("0=0", ALL, set()),
    ("x+1=x+2", NONE, set()),
])
def test_solution_set(eq, kind, values):
    s = solution_set(eq)
    assert s.kind == kind and set(s.values) == values


def test_decimals_are_exact():
    # 0.1 + 0.2 style float noise must not break equality
    assert solution_set("0.1x+0.2x=0.3").values == {1}
    assert equivalent("1.08x=216", "x*1.2*0.9=216")


def test_nonlinear_is_flagged_not_hidden():
    s = solution_set("x*x=4")
    assert s.kind == OTHER and not s.linear
    assert not solution_set("1/(3x)=2").linear


def test_unreadable_equation_returns_none():
    assert solution_set("1/3x=4") is None          # ambiguous
    assert solution_set("2x+=5") is None           # parse error
    assert solution_set("2x+5") is None            # expression, not equation
    assert equivalent("1/3x=4", "x=12") is None


@pytest.mark.parametrize("a, b, same", [
    ("2x+5=25", "x+(x+5)=25", True),
    ("25-x=x+5", "x+(x+5)=25", True),
    ("x+(x-5)=25", "x+(x+5)=25", False),   # same literal as E4-01 mutation, different solution
    ("x=160/0.8", "0.8x=160", True),
])
def test_equivalent(a, b, same):
    assert equivalent(a, b) is same


# ---------------------------------------------------------------------------
# 2. consecutive steps
# ---------------------------------------------------------------------------

def test_valid_working():
    r = check_steps(["x+5=20", "x=20-5", "x=15"])
    assert r.status == ALL_VALID and r.first_invalid_step is None
    assert r.final_value == 15


def test_first_invalid_step_is_located():
    r = check_steps(["x+5=20", "x=20+5", "x=25"])
    assert r.status == INVALID_FOUND
    assert r.first_invalid_step == 2
    assert r.reason == TRANSITION_CHANGES_SOLUTION
    assert r.consistent_after_error is True        # 25 follows correctly from the wrong line


def test_error_then_further_error():
    r = check_steps(["x+5=20", "x=20+5", "x=26"])
    assert r.first_invalid_step == 2
    assert r.consistent_after_error is False


def test_reference_mismatch_on_line_one():
    r = check_steps(["x+(x-5)=25", "2x=30", "x=15"], reference_equation="x+(x+5)=25")
    assert r.first_invalid_step == 1 and r.reason == START_DIFFERS


def test_reference_equivalent_start_is_fine():
    r = check_steps(["2x+5=25", "2x=20", "x=10"], reference_equation="x+(x+5)=25")
    assert r.status == ALL_VALID and r.final_matches_reference is True


def test_final_value_against_reference():
    r = check_steps(["4x=20", "x=6"], reference_equation="2*(x+(x+4))=28")
    assert r.first_invalid_step == 2
    assert r.final_value == 6 and r.final_matches_reference is False


def test_reversed_final_line():
    r = check_steps(["5=x"])
    assert r.final_value == 5


def test_text_lines_are_skipped_and_indexing_is_kept():
    r = check_steps("解：设小华x岁\nx+(x+5)=25\n2x=20\nx=11\n答：小华11岁",
                    reference_equation="x+(x+5)=25")
    assert r.first_invalid_step == 4                # counted over submitted lines
    assert [lc.index for lc in r.lines] == [1, 2, 3, 4, 5]


def test_expression_lines_are_not_compared():
    r = check_steps(["2x+5=25", "25-5", "2x=20", "x=10"])
    assert r.status == ALL_VALID


def test_no_equation():
    assert check_steps(["答：10岁"]).status == NO_EQUATION


# ---------------------------------------------------------------------------
# 3. ambiguity / unreadable input blocks the check (never guessed)
# ---------------------------------------------------------------------------

def test_ambiguous_line_makes_result_uncertain():
    r = check_steps(["1/3x+2=5", "1/3x=3", "x=9"])
    assert r.status == UNCERTAIN and r.blocked_at == 1
    assert r.first_invalid_step is None


def test_unreadable_line_after_error_does_not_hide_error():
    r = check_steps(["x+5=20", "x=25", "x=2#5"])
    assert r.status == INVALID_FOUND and r.first_invalid_step == 2


# ---------------------------------------------------------------------------
# 4. chained equalities
# ---------------------------------------------------------------------------

def test_correct_chain():
    r = check_steps(["2x+6=20", "2x=20-6=14", "x=7"])
    assert r.status == ALL_VALID
    assert r.lines[1].chain_ok is True


def test_wrong_middle_segment_is_found():
    r = check_steps(["2x+6=20", "2x=20-6=15", "x=7.5"])
    assert r.first_invalid_step == 2
    assert r.reason == CHAIN_SEGMENT_MISMATCH


def test_chain_where_outer_equation_is_wrong():
    # 20-6 = 14 is true, but 2x = 14 does not follow from 2x - 6 = 20
    r = check_steps(["2x-6=20", "2x=20-6=14"])
    assert r.first_invalid_step == 2 and r.reason == TRANSITION_CHANGES_SOLUTION


# ---------------------------------------------------------------------------
# 5. answers and verification conditions
# ---------------------------------------------------------------------------

def test_check_value():
    assert check_value(10, "x+(x+5)=25") is True
    assert check_value("4/3", "12*x+30*(2-x)=36") is True
    assert check_value(1.5, "12*x+30*(2-x)=36") is False


def test_conditions_from_bank():
    q = BY_ID["Q06"]
    good = check_conditions(q["verification_conditions"], q["answer"])
    assert all(c.holds for c in good)
    bad = check_conditions(q["verification_conditions"], 25.5)
    assert not all(c.holds for c in bad)       # sum and integer conditions fail


@pytest.mark.parametrize("qid", sorted(BY_ID))
def test_every_bank_answer_satisfies_its_conditions(qid):
    q = BY_ID[qid]
    assert all(c.holds for c in check_conditions(q["verification_conditions"], q["answer"]))


# ---------------------------------------------------------------------------
# 6. all 30 execution mutations – bank format and learner-style format
# ---------------------------------------------------------------------------

def learner_style(step: str) -> str:
    """'2*x + 5 = 25' → '2x＋5＝25'-like text, to exercise the normalizer too."""
    s = re.sub(r"(\d)\*x", r"\1x", step)
    s = re.sub(r"(\d)\*\(", r"\1(", s)
    s = s.replace("*", "×").replace("-", "−").replace(" ", "")
    return s


EXECUTION = [
    (m["id"], q["equation"], m["steps"], m["first_invalid_step"])
    for q in BANK["questions"] for m in q["mutations"] if m["layer"] == "execution"
]


def test_execution_mutation_count():
    assert len(EXECUTION) == 30


@pytest.mark.parametrize("mid, ref, steps, k", EXECUTION, ids=[e[0] for e in EXECUTION])
def test_execution_mutation_bank_format(mid, ref, steps, k):
    r = check_steps(steps, reference_equation=ref)
    assert r.status == INVALID_FOUND and r.first_invalid_step == k


@pytest.mark.parametrize("mid, ref, steps, k", EXECUTION, ids=[e[0] for e in EXECUTION])
def test_execution_mutation_learner_format(mid, ref, steps, k):
    r = check_steps([learner_style(s) for s in steps], reference_equation=ref)
    assert r.status == INVALID_FOUND and r.first_invalid_step == k