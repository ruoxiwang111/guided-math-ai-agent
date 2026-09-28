"""
Tests for core/diagnosis.py  (error_taxonomy.md §9–12)

Run from the project root:
    python -m pytest tests/test_diagnosis.py -v
"""
import json
from pathlib import Path

import pytest

from core.diagnosis import (
    ASK_NOTATION, ASK_ONE_VARIABLE, ASK_REWRITE, ASK_WORKING, DIAGNOSED, INSUFFICIENT, NO_ERROR, UNCERTAIN,
    classify_transition, diagnose_final_answer, diagnose_modelling, diagnose_response,
    diagnose_steps, e4_variants,
)

ROOT = Path(__file__).resolve().parents[1]
BANK = json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))
Q = {q["question_id"]: q for q in BANK["questions"]}
D2A = [c for c in json.loads((ROOT / "eval" / "diagnostic_cases.json").read_text(encoding="utf-8"))["cases"]
       if c.get("source") == "mutation"]


# ---------------------------------------------------------------------------
# E6 / E7 rules on a single transition (§10.8) — normalised input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prev, curr, expected", [
    # E7: transposition without sign change
    ("x+5=12", "x=12+5", "E7"),
    ("2*x+5=25", "2*x=30", "E7"),
    ("3*x+60=4*x+20", "3*x-4*x=60+20", "E7"),
    # E7: wrong inverse operation
    ("3*x=18", "x=18-3", "E7"),
    ("0.8*x=160", "x=160*0.8", "E7"),
    ("x/2=1", "x=1/2", "E7"),
    # E7: operation on one side only
    ("4*x=20", "x=20", "E7"),
    # E7: brackets expanded wrongly
    ("12*x+30*(2-x)=36", "42*x-60=36", "E7"),
    ("3*(x+2)=18", "3*x+2=18", "E7"),
    # E6: valid operation, wrong number
    ("2*x+5=25", "2*x=18", "E6"),
    ("3*x=18", "x=7", "E6"),
    ("2*(x+(x+4))=28", "x+(x+4)=12", "E6"),
    ("x*(1/6+1/3)=1", "x*(1/3)=1", "E6"),
    ("-18*x=-24", "x=3/2", "E6"),
])
def test_classify_transition(prev, curr, expected):
    category, rule = classify_transition(prev, curr)
    assert category == expected, rule


def test_unclassifiable_transition_is_not_forced():
    category, rule = classify_transition("2*x+5=25", "7*x=3")
    assert category is None and rule == "no_rule_matched"


# ---------------------------------------------------------------------------
# S3 — whole working
# ---------------------------------------------------------------------------

def test_valid_working_is_no_error():
    d = diagnose_steps(Q["Q01"], ["x+(x+5)=25", "2x+5=25", "2x=20", "x=10"])
    assert d.status == NO_ERROR


def test_taxonomy_example_10_7():
    # 2x+5=15 / 2x=10 / x=10/2 / x=6  → first invalid line 4, E6
    q = dict(Q["Q01"], equation="2*x+5=15")
    d = diagnose_steps(q, ["2x+5=15", "2x=10", "x=10/2", "x=6"])
    assert d.status == DIAGNOSED and d.primary_error == "E6" and d.first_invalid_step == 4


def test_learner_style_sign_error():
    d = diagnose_steps(Q["Q05"], "2(x+x+4)=28\n4x+8=28\n4x=36\nx=9")
    assert d.primary_error == "E7" and d.first_invalid_step == 3


def test_chain_arithmetic_error_is_e6():
    q = dict(Q["Q01"], equation="2*x+6=20")
    d = diagnose_steps(q, ["2x+6=20", "2x=20-6=15", "x=7.5"])
    assert d.primary_error == "E6" and d.rule == "chain_segment_mismatch"


def test_wrong_first_line_goes_to_modelling():
    d = diagnose_steps(Q["Q01"], ["x+(x-5)=25", "2x=30", "x=15"],
                       variable_definition="设小华今年x岁，小明(x-5)岁")
    assert d.state == "S2" and d.error_subtype == "E4-01" and d.first_invalid_step == 1


def test_ambiguous_line_asks_for_clarification():
    d = diagnose_steps(Q["Q01"], ["1/3x+5=25", "x=60"])
    assert d.status == UNCERTAIN and d.follow_up == ASK_NOTATION


# ---------------------------------------------------------------------------
# S2 — modelling
# ---------------------------------------------------------------------------

def correct_forms():
    for q in BANK["questions"]:
        yield q["question_id"], q["variable_definition"], q["equation"]
        for f in q["accepted_equivalent_forms"]:
            yield q["question_id"], f.get("variable_definition", q["variable_definition"]), f["equation"]


CORRECT = list(correct_forms())


@pytest.mark.parametrize("qid, vd, eq", CORRECT, ids=[f"{c[0]}:{c[2]}" for c in CORRECT])
def test_every_accepted_form_is_no_error(qid, vd, eq):
    """False-positive guard: every correct form, incl. other choices of x."""
    d = diagnose_modelling(Q[qid], eq, vd)
    assert d.status == NO_ERROR, (d.status, d.primary_error, d.evidence)


def test_same_literal_equation_different_definition():
    # x+(x-5)=25 is CORRECT when x is 小明, E4-01 when x is 小华
    assert diagnose_modelling(Q["Q01"], "x+(x-5)=25", "设小明今年x岁，则小华(x-5)岁").status == NO_ERROR
    d = diagnose_modelling(Q["Q01"], "x+(x-5)=25", "设小华今年x岁，小明(x-5)岁")
    assert d.status == DIAGNOSED and d.error_subtype == "E4-01"


@pytest.mark.parametrize("qid", sorted(q for q in Q if Q[q]["e4_patterns"]))
def test_e4_templates_generate_wrong_equations(qid):
    from core.math_checker import equivalent
    for pid, wrong in e4_variants(Q[qid]):
        assert equivalent(wrong, Q[qid]["equation"]) is False, (pid, wrong)


def test_e2_single_clause_definition():
    d = diagnose_modelling(Q["Q13"], "12x+30(2-x)=36", "设乘汽车x小时")
    assert d.status == DIAGNOSED and d.primary_error == "E2"


def test_unknown_wrong_equation_is_uncertain_not_forced():
    d = diagnose_modelling(Q["Q09"], "500x=12000", "设回家用了x分钟")
    assert d.status == UNCERTAIN and "E3" in d.candidates


def test_ambiguous_equation_is_uncertain_and_asks_for_notation():
    d = diagnose_modelling(Q["Q03"], "1/3x=160", "设原价为x元")
    assert d.status == UNCERTAIN and d.evidence_level == "C" and d.follow_up == ASK_NOTATION


def test_unreadable_equation_is_insufficient():
    d = diagnose_modelling(Q["Q03"], "0.8x==160", "设原价为x元")
    assert d.status == INSUFFICIENT and d.evidence_level == "D" and d.follow_up == ASK_REWRITE


# --- two unknowns / outside V1 (never labelled as an error) -----------------

def test_correct_two_variable_system_is_recognised():
    d = diagnose_modelling(Q["Q15"], "x-4=y+4，x+y=56", "设x表示甲")
    assert d.status == INSUFFICIENT and d.primary_error is None
    assert d.rule == "two_variable_system_correct" and d.follow_up == ASK_ONE_VARIABLE
    assert "x = 32" in d.evidence


def test_wrong_two_variable_system_asks_for_one_variable():
    d = diagnose_modelling(Q["Q15"], "x-4=y；x+y=56", "设x表示甲")
    assert d.rule == "two_variable_system_incorrect" and d.primary_error is None


def test_single_equation_with_two_unknowns():
    d = diagnose_modelling(Q["Q15"], "x+y=56", "设x表示甲")
    assert d.follow_up == ASK_ONE_VARIABLE and d.primary_error is None


def test_power_and_missing_equals_sign():
    assert diagnose_modelling(Q["Q05"], "x²+4=28", "设宽x厘米").rule == "power"
    assert diagnose_modelling(Q["Q05"], "2x+8", "设宽x厘米").rule == "no_equals_sign"


# ---------------------------------------------------------------------------
# S4 — final answer only (§10.10)
# ---------------------------------------------------------------------------

def test_final_answer_correct():
    assert diagnose_final_answer(Q["Q01"], "小华10岁，小明15岁").status == NO_ERROR


def test_final_answer_unit_error_is_level_a():
    d = diagnose_final_answer(Q["Q09"], "15小时")
    assert d.primary_error == "E5" and d.evidence_level == "A"


def test_final_answer_matching_e6_is_only_a_candidate():
    d = diagnose_final_answer(Q["Q12"], "小红12岁")
    assert d.status == UNCERTAIN and d.evidence_level == "B" and d.candidates == ["E6"]
    assert d.follow_up == ASK_WORKING


def test_final_answer_unexplained_asks_for_working():
    d = diagnose_final_answer(Q["Q01"], "7岁")                 # no labelled part to compare
    assert d.status == INSUFFICIENT and d.follow_up == ASK_WORKING


def test_final_answer_wrong_part_is_named():
    d = diagnose_final_answer(Q["Q01"], "小华7岁")
    assert d.rule == "answer_part_wrong" and d.details["wrong"] == ["小华"]


# ---------------------------------------------------------------------------
# D2a regression: never a WRONG specific label, in either mode
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["full", "leave_one_out"])
def test_d2a_no_wrong_specific_labels(mode):
    wrong = []
    for c in D2A:
        exclude = c["mutation_id"] if mode == "leave_one_out" else None
        d = diagnose_response(Q[c["question_id"]], c["learner_response"], exclude_mutation=exclude)
        if d.status == DIAGNOSED and d.primary_error != c["primary_error"]:
            wrong.append((c["case_id"], c["primary_error"], d.primary_error))
    assert not wrong


def test_d2a_uncertain_reference_stays_uncertain():
    c = next(c for c in D2A if c["reference_status"] == "uncertain")
    d = diagnose_response(Q[c["question_id"]], c["learner_response"], exclude_mutation=c["mutation_id"])
    assert d.status in (UNCERTAIN, INSUFFICIENT)


# --- final answer, part by part -----------------------------------------------

@pytest.mark.parametrize("text, status, rule", [
    ("甲班32台，乙班22", UNCERTAIN, "answer_part_wrong"),
    ("甲班32台，乙班24", INSUFFICIENT, "answer_unit_missing"),
    ("甲班32台", INSUFFICIENT, "answer_incomplete"),
    ("乙班原来24台，甲班原来32台", NO_ERROR, None),
    ("甲班32千克，乙班24千克", DIAGNOSED, "answer_unit_wrong"),
])
def test_final_answer_parts(text, status, rule):
    d = diagnose_final_answer(Q["Q15"], text)
    assert d.status == status and d.rule == rule and d.primary_error in (None, "E5")


@pytest.mark.parametrize("text, ok", [
    ("每分钟250米", True), ("250米/分钟", True), ("回家每分钟骑250米", True),
    ("250米", False), ("每分钟250千米", False),
])
def test_rate_units_are_compared_as_units(text, ok):
    d = diagnose_final_answer(Q["Q04"], text, exclude_mutation="Q04-E5")
    assert (d.status == NO_ERROR) is ok


def test_single_quantity_answer_may_omit_label():
    q = {"final_answer_text": "这本书一共150页", "mutations": [], "equation": "x/3+40+60=x"}
    assert diagnose_final_answer(q, "150页").status == NO_ERROR
    assert diagnose_final_answer(q, "150千克").primary_error == "E5"