"""
Tests for core/normalizer.py  (error_taxonomy.md §10.3–10.5)

Run from the project root:
    python -m pytest tests/test_normalizer.py -v
"""
import json
from pathlib import Path

import pytest
from sympy import Eq, Symbol, nsimplify, solve
from sympy.parsing.sympy_parser import parse_expr

from core.normalizer import (
    AMBIGUOUS, EMPTY, EQUATION, EXPRESSION, NOT_MATH, OK, PARSE_ERROR, UNSUPPORTED,
    normalize_line, normalize_steps, split_steps,
)

ROOT = Path(__file__).resolve().parents[1]
BANK = json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))
x = Symbol("x")


def solutions(eq):
    lhs, rhs = eq.split("=")
    p = lambda s: nsimplify(parse_expr(s, local_dict={"x": x}), rational=True)  # noqa: E731
    return {nsimplify(v, rational=True) for v in solve(Eq(p(lhs), p(rhs)), x)}


# ---------------------------------------------------------------------------
# §10.3 supported notation → OK
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    # full-width symbols
    ("２ｘ＋５＝１５", "2*x+5=15"),
    ("2x－6＝42", "2*x-6=42"),
    ("（x＋4）×2＝28", "(x+4)*2=28"),
    # multiplication / division symbols
    ("2 × (x + 3) = 14", "2*(x+3)=14"),
    ("2x·3=12", "2*x*3=12"),
    ("18÷3=x", "18/3=x"),
    ("3x−4=11", "3*x-4=11"),                   # U+2212 minus
    # implicit multiplication
    ("2x+5=15", "2*x+5=15"),
    ("3(x+1)=12", "3*(x+1)=12"),
    ("0.8(x-10)=190", "0.8*(x-10)=190"),
    ("(x+1)(2)=8", "(x+1)*(2)=8"),
    # brackets used in textbooks / Challenge AI text
    ("2[x+(x+4)]=28", "2*(x+(x+4))=28"),
    ("2【x+(x+4)】=28", "2*(x+(x+4))=28"),
    # explicit fractions are fine
    ("(1/3)x=4", "(1/3)*x=4"),
    ("x/3=4", "x/3=4"),
    ("1/(3x)=2", "1/(3*x)=2"),
    ("2x/3=4", "2*x/3=4"),
    # percent
    ("20%x=6", "(20/100)*x=6"),
    ("x(1+20%)=180", "x*(1+(20/100))=180"),
    # decimals
    ("1.2x=180", "1.2*x=180"),
    # leading words and trailing units
    ("解：2x+5=15", "2*x+5=15"),
    ("所以 x = 5", "x=5"),
    ("∴ x = 13", "x=13"),
    ("移项得 2x=10", "2*x=10"),
    ("x=5元", "x=5"),
    ("x=24（人）", "x=24"),
    ("x=5cm", "x=5"),
    ("x = 250。", "x=250"),
    # already in SymPy form (question bank)
    ("x*(1/6 + 1/3) = 1", "x*(1/6+1/3)=1"),
])
def test_supported_notation(raw, expected):
    r = normalize_line(raw)
    assert r.status == OK, (raw, r.status, r.issue_codes())
    assert r.normalized == expected
    assert r.kind == EQUATION
    assert r.original == raw                      # §10.5.1 original preserved


def test_unit_is_recorded():
    r = normalize_line("x = 5元")
    assert r.unit == "元"


def test_expression_and_number():
    assert normalize_line("2x+5").kind == EXPRESSION
    r = normalize_line("15")
    assert r.status == OK and r.kind == EXPRESSION and r.normalized == "15"


def test_other_single_variable_is_renamed_and_recorded():
    r = normalize_line("2y+1=5")
    assert r.status == OK and r.normalized == "2*x+1=5"
    assert "variable_renamed" in r.issue_codes()


# ---------------------------------------------------------------------------
# §10.4 ambiguous input → never guessed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "1/3x+2=5",
    "1/3 x = 4",
    "2/3x=6",
    "1/2(x+1)=3",
    "(x+1)/2x=3",
    "x2=4",          # x×2 or x²?
    "3x2=6",
])
def test_ambiguous_is_not_resolved(raw):
    r = normalize_line(raw)
    assert r.status == AMBIGUOUS
    assert r.normalized is None                   # nothing for the checker to judge


def test_ambiguous_fraction_message_matches_taxonomy():
    msg = normalize_line("1/3x+2=5").issues[0].message
    assert "(1/3)×x" in msg and "1/(3×x)" in msg and "括号" in msg


# ---------------------------------------------------------------------------
# outside V1 / unreadable / not maths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, code", [
    ("x²=4", "power"),
    ("x^2+1=5", "power"),
    ("x**2=9", "power"),
    ("x+y=3", "multiple_variables"),
])
def test_unsupported(raw, code):
    r = normalize_line(raw)
    assert r.status == UNSUPPORTED and code in r.issue_codes()


@pytest.mark.parametrize("raw", ["2x+=5", "=5", "2x=", "(2x+1=5", "2x+1)=5", "2x+5=15#"])
def test_parse_error_is_not_a_learner_error(raw):
    r = normalize_line(raw)
    assert r.status == PARSE_ERROR
    assert r.normalized is None


@pytest.mark.parametrize("raw, code", [
    ("答：小华10岁，小明15岁", "answer_sentence"),
    ("设小华今年x岁", "variable_definition"),
    ("解：设小华今年x岁", "variable_definition"),   # found by test_math_checker
])
def test_not_math(raw, code):
    r = normalize_line(raw)
    assert r.status == NOT_MATH and code in r.issue_codes()


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty(raw):
    assert normalize_line(raw).status == EMPTY


# ---------------------------------------------------------------------------
# chained equalities
# ---------------------------------------------------------------------------

def test_chained_equality_keeps_all_parts():
    r = normalize_line("2x = 20 − 6 = 14")
    assert r.status == OK
    assert r.normalized == "2*x=14"
    assert r.chain_parts == ["2*x", "20-6", "14"]
    assert "chained_equality" in r.issue_codes()


# ---------------------------------------------------------------------------
# multi-line working
# ---------------------------------------------------------------------------

def test_split_steps():
    text = "解：2(x+x+4)=28\n4x+8=28，4x=20；x=5。"
    assert split_steps(text) == ["解：2(x+x+4)=28", "4x+8=28", "4x=20", "x=5"]


def test_normalize_steps_from_text_and_list():
    from_text = [r.normalized for r in normalize_steps("4x+8=28\n4x=20\nx=5")]
    from_list = [r.normalized for r in normalize_steps(["4x+8=28", "4x=20", "x=5"])]
    assert from_text == from_list == ["4*x+8=28", "4*x=20", "x=5"]


# ---------------------------------------------------------------------------
# meaning preservation on every equation in the frozen question bank (§10.5.3)
# ---------------------------------------------------------------------------

def bank_equations():
    for q in BANK["questions"]:
        qid = q["question_id"]
        yield f"{qid}:equation", q["equation"]
        for i, f in enumerate(q["accepted_equivalent_forms"]):
            yield f"{qid}:form{i}", f["equation"]
        for m in q["mutations"]:
            if m["layer"] == "modelling":
                yield m["id"], m["equation"]
            elif m["layer"] == "execution":
                for i, step in enumerate(m["steps"], 1):
                    yield f"{m['id']}:line{i}", step


BANK_EQUATIONS = list(bank_equations())


@pytest.mark.parametrize("label, eq", BANK_EQUATIONS, ids=[b[0] for b in BANK_EQUATIONS])
def test_bank_equation_meaning_preserved(label, eq):
    r = normalize_line(eq)
    assert r.status == OK, (label, r.issue_codes())
    assert solutions(r.normalized) == solutions(eq)


def test_bank_equation_count():
    # 15 standard + 40 accepted forms + 28 modelling + all execution lines
    assert len(BANK_EQUATIONS) > 150


# ---------------------------------------------------------------------------
# learner-style rewrites of bank equations keep their meaning
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("learner, bank", [
    ("x+(x+5)=25", "x + (x + 5) = 25"),
    ("0.8x=160", "0.8*x = 160"),
    ("300×10+10x=5500", "300*10 + 10*x = 5500"),
    ("2(x+x+4)=28", "2*(x + (x + 4)) = 28"),
    ("x＋(x－6)＝42", "x + (x - 6) = 42"),
    ("x(1+20%)=180", "1.2*x = 180"),
    ("0.8x－10＝190", "0.8*x - 10 = 190"),
    ("500×12+400x=12000", "500*12 + 400*x = 12000"),
    ("x(1/6+1/3)=1", "x*(1/6 + 1/3) = 1"),
    ("2(x+2)+3x=29", "2*(x + 2) + 3*x = 29"),
    ("x/4+5=(x+5)/3", "x/4 + 5 = (x + 5)/3"),
    ("12x+30(2−x)=36", "12*x + 30*(2 - x) = 36"),
    ("x×1.2×0.9=216", "x*1.2*0.9 = 216"),
    ("56−x−4=x+4", "56 - x - 4 = x + 4"),
])
def test_learner_style_matches_bank(learner, bank):
    r = normalize_line(learner)
    assert r.status == OK, r.issue_codes()
    assert solutions(r.normalized) == solutions(bank)


def test_full_width_decimal_point_is_not_a_line_break():
    assert [r.normalized for r in normalize_steps("０．８x＝160\nx＝200")] == ["0.8*x=160", "x=200"]