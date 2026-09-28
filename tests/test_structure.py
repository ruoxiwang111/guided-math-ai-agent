"""
Tests for core/structure.py — structure extraction for arbitrary linear word problems.
A fake backend stands in for the LLM; everything numeric is checked by code.

Run from the project root:
    python -m pytest tests/test_structure.py -v
"""
import copy
import json

import pytest

from core.s1_options import build_s1_item, to_submission
from core.state_manager import ASK, COMPLETE, S3, S4, TutorSession
from core.structure import CONSISTENT, INCONSISTENT, OUT_OF_SCOPE, UNCERTAIN, extract_structure, question_id_for

TEXT = "一本书，小明第一天看了全书的1/3，第二天看了40页，还剩60页没看。这本书一共多少页？"
RAW = {
    "scope": "in_scope", "scope_reason": "一元一次方程应用题", "topic": "分数应用",
    "unknown": {"meaning": "全书页数", "unit": "页"},
    "variable_definition": "设这本书一共有x页",
    "known_quantities": [{"name": "第一天看的比例", "value": "1/3"},
                         {"name": "第二天页数", "value": 40, "unit": "页"},
                         {"name": "剩余页数", "value": 60, "unit": "页"}],
    "relationship": "第一天 + 第二天 + 剩下 = 全书",
    "equation": "x/3 + 40 + 60 = x",
    "answer_parts": [{"label": "这本书一共", "expression": "x", "unit": "页"}],
    "verification_conditions": [
        {"description": "三部分之和等于全书", "lhs": "x/3+40+60", "op": "==", "rhs": "x"},
        {"description": "第一天页数为整数", "lhs": "x/3", "op": "integer", "rhs": "0"}],
    "alternatives": [{"variable_definition": "设第一天看了x页，则全书3x页", "equation": "x+40+60=3*x",
                      "x_expression": "x/3"}],
    "e4_patterns": [], "s1_target": "这本书的总页数", "s1_intermediate": "第一天看了多少页",
}
SOLVED = '{"parts": [{"label": "总页数", "value": "150"}]}'


class Fake:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def describe(self):
        return {"backend": "fake"}

    def complete(self, system, user):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


def extract(raw=RAW, solved=SOLVED):
    return extract_structure(TEXT, Fake(raw, solved))


# ---------------------------------------------------------------------------

def test_consistent_extraction_builds_a_bank_style_record():
    ex = extract()
    assert ex.usable and ex.consistency == CONSISTENT
    q = ex.question
    assert q["question_id"] == question_id_for(TEXT) and q["source"] == "extracted"
    assert q["equation"] == "x/3+40+60=x" and q["answer"] == "150"
    assert q["final_answer_text"] == "这本书一共150页"
    assert q["accepted_equivalent_forms"][0]["x_value"] == "50"
    assert all(c["ok"] for c in q["extraction"]["checks"])


def test_answer_is_computed_by_code_not_taken_from_llm():
    raw = copy.deepcopy(RAW)
    raw["answer_parts"] = [{"label": "第一天看了", "expression": "x/3", "unit": "页"},
                           {"label": "一共", "expression": "x", "unit": "页"}]
    ex = extract(raw, '{"parts": [{"label": "a", "value": "50"}, {"label": "b", "value": "150"}]}')
    assert ex.question["final_answer_text"] == "第一天看了50页，一共150页"


def test_independent_disagreement_is_inconsistent():
    ex = extract(solved='{"parts": [{"label": "总页数", "value": "180"}]}')
    assert ex.consistency == INCONSISTENT and not ex.usable


def test_missing_independent_solution_is_uncertain():
    ex = extract_structure(TEXT, Fake(RAW, RuntimeError("timeout")))
    assert ex.consistency == UNCERTAIN and not ex.usable


def test_wrong_equation_fails_conditions():
    raw = dict(RAW, equation="x/3 + 40 = x")               # forgot the remaining 60 pages
    ex = extract(raw)
    assert ex.consistency == INCONSISTENT
    assert any(c.name == "conditions_hold" and not c.ok for c in ex.checks)


@pytest.mark.parametrize("eq", ["x*(x+4) = 60", "x + y = 5", "2x+1"])
def test_non_linear_or_unreadable_equation_is_rejected(eq):
    ex = extract(dict(RAW, equation=eq))
    assert ex.consistency == INCONSISTENT and ex.question is None


def test_out_of_scope_is_reported_without_validation():
    fake = Fake({"scope": "out_of_scope", "scope_reason": "需要一元二次方程"})
    ex = extract_structure("面积是60的长方形……", fake)
    assert ex.scope == OUT_OF_SCOPE and fake.calls == 1 and not ex.usable


def test_bad_alternative_and_unknown_e4_are_dropped():
    raw = copy.deepcopy(RAW)
    raw["alternatives"].append({"variable_definition": "设剩下x页", "equation": "x+1=3", "x_expression": "60"})
    raw["e4_patterns"] = ["E4-06", "E9-99"]                  # no 0.8*x in this equation, unknown id
    q = extract(raw).question
    assert len(q["accepted_equivalent_forms"]) == 1 and q["e4_patterns"] == []


def test_no_backend_means_bank_only():
    ex = extract_structure(TEXT, None)
    assert not ex.usable and "question-bank" in ex.error


# ---------------------------------------------------------------------------
# the whole guided pipeline runs on an extracted record
# ---------------------------------------------------------------------------

def test_guided_session_on_extracted_question():
    q = extract().question
    item = build_s1_item(q, {q["question_id"]: q["s1"]})
    s = TutorSession(q)
    s.start()
    assert s.submit(to_submission(item, item["correct_id"])).task == "define_x_and_equation"

    # alternative choice of unknown is accepted, S3 checked against it
    a = s.submit({"type": "modelling", "variable_definition": "设第一天看了x页，则全书3x页", "equation": "x+40+60=3x"})
    assert a.state == S3
    assert s.submit({"type": "steps", "steps": "100=2x\nx=50"}).state == S4

    a = s.submit({"type": "final_answer", "final_answer_text": "150页", "verified": True})
    assert a.type == COMPLETE


def test_guided_session_diagnoses_errors_on_extracted_question():
    q = extract().question
    s = TutorSession(q)
    s.start(); s.submit({"type": "s1_choice", "correct": True})
    a = s.submit({"type": "modelling", "variable_definition": "设这本书一共有x页", "equation": "x/3+40+60=x"})
    assert a.type == ASK and a.state == S3
    a = s.submit({"type": "steps", "steps": "x/3+100=x\n100=2x/3\nx=100*3/2\nx=160"})
    assert a.category == "E6" and a.hint_level == 1