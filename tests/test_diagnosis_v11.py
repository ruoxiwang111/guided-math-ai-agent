"""
V1.1 rules, tuned on the D2b DEV split only (docs/D2B_RESULTS.md): sign flip of one term is E7,
a unit scale that contradicts the numbers is E5, an unknown defined as another kind of quantity
than the equation uses is E2 — and the guards that keep correct work from being flagged.
"""
import json
from pathlib import Path

from core.diagnosis import DIAGNOSED, NO_ERROR, classify_transition, diagnose_modelling, diagnose_steps

ROOT = Path(__file__).resolve().parents[1]
Q = {q["question_id"]: q for q in json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))["questions"]}


def test_sign_flip_of_one_term_is_e7_but_a_wrong_number_stays_e6():
    assert classify_transition("2*x+5=25", "2*x-5=25") == ("E7", "sign_flip_one_term")
    assert classify_transition("2*x+5=25", "2*x=21")[0] == "E6"        # 25-5 mis-subtracted: a number is off


def test_sign_flip_in_a_line_by_line_solution():
    d = diagnose_steps(Q["Q04"], ["3000-10x=5500", "-10x=5500+3000", "-10x=8500", "x=850"],
                       start_equation="300×10＋10x＝5500")
    assert d.status == DIAGNOSED and d.primary_error == "E7" and d.first_invalid_step == 1


def test_unit_scale_mismatch_is_e5():
    d = diagnose_modelling(Q["Q04"], "300×10+10x=5500", "设小明回家时每分钟骑x千米")
    assert d.status == DIAGNOSED and d.primary_error == "E5" and d.rule == "unit_scale_mismatch"


def test_same_unit_is_not_flagged():
    d = diagnose_modelling(Q["Q04"], "300×10+10x=5500", "设小明回家时每分钟骑x米")
    assert d.status == NO_ERROR
    d = diagnose_modelling(Q["Q09"], "500*12+400x=12000", "设回家用了x分钟")
    assert d.status == NO_ERROR


def test_definition_of_another_kind_of_quantity_is_e2():
    d = diagnose_modelling(Q["Q09"], "500×12+400x=12000", "设小王回家时的速度为x米/分钟")
    assert d.status == DIAGNOSED and d.primary_error == "E2" and d.evidence_level == "B"


def test_vague_or_consistent_definitions_are_not_flagged():
    assert diagnose_modelling(Q["Q09"], "500×12+400x=12000", "设回家用了x").status == NO_ERROR
    assert diagnose_modelling(Q["Q01"], "x+(x+5)=25", "设小华今年x岁，小明今年y岁。").status == NO_ERROR
    assert diagnose_modelling(Q["Q02"], "x+(x+12)=28", "设笔的价格为x元，笔记本的价格为y元。").status == NO_ERROR
