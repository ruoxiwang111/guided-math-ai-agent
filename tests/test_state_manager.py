"""
Tests for core/state_manager.py  (V1_design §11.2, §12, §20–24; error_taxonomy §9, §18)

Run from the project root:
    python -m pytest tests/test_state_manager.py -v
"""
import json
from pathlib import Path

import pytest

from core.state_manager import (
    ASK, COMPLETE, DONE, EVIDENCE_REQUEST, HINT, METACOGNITIVE, REFLECTION_FEEDBACK, REVEAL, S1, S2, S3, S4,
    UNEXPECTED_INPUT, TutorSession,
)

ROOT = Path(__file__).resolve().parents[1]
Q = {q["question_id"]: q for q in json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))["questions"]}

S1_OK = {"type": "s1_choice", "correct": True}
S2_OK = {"type": "modelling", "variable_definition": "设小华今年x岁，则小明今年(x+5)岁", "equation": "x+(x+5)=25"}
S2_E4 = {"type": "modelling", "variable_definition": "设小华x岁，小明(x-5)岁", "equation": "x+(x-5)=25"}
S3_OK = {"type": "steps", "steps": ["2x+5=25", "2x=20", "x=10"]}
S3_E7 = {"type": "steps", "steps": ["2x+5=25", "2x=30", "x=15"]}
S4_OK = {"type": "final_answer", "final_answer_text": "小华10岁，小明15岁", "verified": True}


def session(qid="Q01", **kw):
    s = TutorSession(Q[qid], **kw)
    s.start()
    return s


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------

def test_clean_run_goes_s1_to_done_without_follow_ups():
    s = TutorSession(Q["Q01"])
    a = s.start()
    assert (a.type, a.state) == (ASK, S1)
    assert s.submit(S1_OK).state == S2
    assert s.submit(S2_OK).state == S3                 # no error → no reflection question
    assert s.submit(S3_OK).state == S4
    a = s.submit(S4_OK)
    assert a.type == COMPLETE and s.state == DONE
    assert s.metacognitive_count == 0 and s.evidence_request_count == 0
    assert all(r["independent"] for r in s.summary()["states"].values())


# ---------------------------------------------------------------------------
# hints and escalation (§20)
# ---------------------------------------------------------------------------

def test_diagnosed_error_gives_level_1_hint_with_category():
    s = session()
    s.submit(S1_OK)
    a = s.submit(S2_E4)
    assert a.type == HINT and a.category == "E4" and a.error_subtype == "E4-01" and a.hint_level == 1
    assert s.state == S2                                  # stays in the state


def test_hint_level_escalates_then_reveals():
    s = session()
    s.submit(S1_OK)
    levels = [s.submit(S2_E4).hint_level for _ in range(4)]
    assert levels == [1, 2, 3, 4]
    a = s.submit(S2_E4)
    assert a.type == REVEAL and a.next_action.state == S3
    assert s.state == S3
    rec = s.summary()["states"]["S2"]
    assert rec["revealed"] and not rec["independent"]


def test_hint_level_resets_in_next_state():
    s = session()
    s.submit(S1_OK)
    s.submit(S2_E4); s.submit(S2_E4)                     # levels 1, 2
    s.submit(S2_OK)
    s.submit({"type": "reflection", "text": "…"})
    a = s.submit(S3_E7)
    assert a.type == HINT and a.category == "E7" and a.hint_level == 1


def test_prompt_spec_carries_leakage_constraints():
    s = session()
    s.submit(S1_OK)
    spec = s.submit(S2_E4).prompt_spec
    assert spec["hint_level"] == 1
    assert {"final_answer", "complete_equation", "key_intermediate_value"} <= set(spec["must_not_contain"])
    assert spec["reference_answer"] == "10"


# ---------------------------------------------------------------------------
# evidence requests vs metacognitive budget (taxonomy §9 step 7, §18; V1_design §21)
# ---------------------------------------------------------------------------

def test_ambiguous_notation_is_evidence_request_not_budget():
    s = session()
    s.submit(S1_OK)
    a = s.submit({"type": "modelling", "variable_definition": "设小华x岁", "equation": "1/3x+5=25"})
    assert a.type == EVIDENCE_REQUEST and a.request == "clarify_notation"
    assert not a.counts_toward_budget and s.metacognitive_count == 0


def test_evidence_requests_are_capped_then_neutral_hint():
    s = session()
    s.submit(S1_OK)
    bad = {"type": "modelling", "variable_definition": "设小华x岁", "equation": "1/3x+5=25"}
    assert s.submit(bad).type == EVIDENCE_REQUEST
    assert s.submit(bad).type == EVIDENCE_REQUEST
    a = s.submit(bad)
    assert a.type == HINT and a.category is None       # never claims an error it cannot support


def test_reflection_after_corrected_error_counts_toward_budget():
    s = session()
    s.submit(S1_OK)
    s.submit(S2_E4)
    a = s.submit(S2_OK)
    assert a.type == METACOGNITIVE and a.counts_toward_budget and s.metacognitive_count == 1
    fb = s.submit({"type": "reflection", "text": "小明比小华大，所以是 x+5"})
    assert fb.type == REFLECTION_FEEDBACK and fb.task == "feedback"   # the reply gets a response first
    assert (fb.next_action.type, fb.next_action.state) == (ASK, S3)


def test_budget_keeps_a_slot_for_verification():
    s = session()
    s.submit(S1_OK)
    s.submit(S2_E4); s.submit(S2_OK)                   # reflection 1
    s.submit({"type": "reflection", "text": "…"})
    s.submit(S3_E7); a = s.submit(S3_OK)               # no reflection: slot reserved
    assert (a.type, a.state) == (ASK, S4)
    a = s.submit({"type": "final_answer", "final_answer_text": "小华10岁，小明15岁"})
    assert a.type == METACOGNITIVE and a.task == "prompt_verification"
    assert s.metacognitive_count == 2


@pytest.mark.parametrize("budget", [0, 1, 2])
def test_budget_is_never_exceeded(budget):
    s = session(metacognitive_budget=budget)
    s.submit(S1_OK)
    s.submit(S2_E4)
    s.submit(S2_OK)
    s.submit({"type": "reflection", "text": "…"})
    s.submit(S3_E7)
    s.submit(S3_OK)
    s.submit({"type": "reflection", "text": "…"})
    s.submit({"type": "final_answer", "final_answer_text": "小华10岁，小明15岁"})
    assert s.metacognitive_count <= budget


def test_active_verification_skips_verification_prompt():
    s = session()
    s.submit(S1_OK); s.submit(S2_OK); s.submit(S3_OK)
    a = s.submit({"type": "final_answer", "final_answer_text": "小华10岁，小明15岁",
                  "active_verification": True})
    assert a.type == COMPLETE and s.summary()["active_verification"] is True


# ---------------------------------------------------------------------------
# alternative definition carries into S3 (no false error)
# ---------------------------------------------------------------------------

def test_alternative_definition_is_checked_against_learner_model():
    s = session()
    s.submit(S1_OK)
    a = s.submit({"type": "modelling", "variable_definition": "设小明今年x岁，则小华(x-5)岁",
                  "equation": "x+(x-5)=25"})
    assert a.state == S3 and s.summary()["accepted_model"] == "alternative"
    a = s.submit({"type": "steps", "steps": ["2x-5=25", "2x=30", "x=15"]})
    assert (a.type, a.state) == (ASK, S4)


# ---------------------------------------------------------------------------
# S1, S3 incomplete, S4 checks
# ---------------------------------------------------------------------------

def test_s1_wrong_target_is_e1_hint():
    s = session()
    a = s.submit({"type": "s1_choice", "correct": False})
    assert a.type == HINT and a.category == "E1"


def test_s3_unfinished_working_asks_to_continue():
    s = session()
    s.submit(S1_OK); s.submit(S2_OK)
    a = s.submit({"type": "steps", "steps": ["2x+5=25", "2x=20"]})
    assert a.type == EVIDENCE_REQUEST and a.request == "continue_solving"


def test_s4_unit_error():
    s = session("Q09")
    s.submit(S1_OK)
    s.submit({"type": "modelling", "variable_definition": "设回家用了x分钟", "equation": "500*12+400x=12000"})
    s.submit({"type": "steps", "steps": ["6000+400x=12000", "400x=6000", "x=15"]})
    a = s.submit({"type": "final_answer", "final_answer_text": "15小时", "verified": True})
    assert a.type == HINT and a.category == "E5"


# ---------------------------------------------------------------------------
# robustness and logging
# ---------------------------------------------------------------------------

def test_wrong_input_type_is_not_a_learner_error():
    s = session()
    a = s.submit(S3_OK)                                 # steps while in S1
    assert a.type == UNEXPECTED_INPUT and s.state == S1
    assert s.records[S1].attempts == 0


def test_reflection_without_open_question_is_rejected():
    s = session()
    assert s.submit({"type": "reflection", "text": "…"}).type == UNEXPECTED_INPUT


def test_event_log_fields():
    s = session()
    s.submit(S1_OK); s.submit(S2_E4)
    hint = next(e for e in s.events if e["event"] == "hint")
    for key in ("session_id", "question_id", "state", "diagnosed_error", "diagnosis_status",
                "hint_level", "follow_up_count", "evidence_request_count", "timestamp"):
        assert key in hint
    assert json.loads(s.events_jsonl().splitlines()[0])["event"] == "session_start"


@pytest.mark.parametrize("qid", sorted(Q))
def test_every_question_can_be_completed_with_its_standard_solution(qid):
    q = Q[qid]
    s = TutorSession(q)
    s.start()
    s.submit(S1_OK)
    assert s.submit({"type": "modelling", "variable_definition": q["variable_definition"],
                     "equation": q["equation"]}).state == S3
    a = s.submit({"type": "steps", "steps": [q["equation"], f"x={q['answer']}"]})
    assert a.state == S4, a
    a = s.submit({"type": "final_answer", "final_answer_text": q["final_answer_text"], "verified": True})
    assert a.type == COMPLETE, a


# ---------------------------------------------------------------------------
# learner questions (help-seeking) and part-by-part answer checks
# ---------------------------------------------------------------------------

from core.state_manager import ANSWER_QUESTION, looks_like_question  # noqa: E402


def to_s4(qid="Q15"):
    q = Q[qid]
    s = TutorSession(q); s.start(); s.submit(S1_OK)
    s.submit({"type": "modelling", "variable_definition": q["variable_definition"], "equation": q["equation"]})
    s.submit({"type": "steps", "steps": [q["equation"], f"x={q['answer']}"]})
    assert s.state == S4
    return s


def test_question_does_not_change_state_or_budget():
    s = session()
    s.submit(S1_OK)
    a = s.submit({"type": "question", "text": "设哪个量为x比较好？"})
    assert a.type == ANSWER_QUESTION and s.state == S2
    assert s.metacognitive_count == 0 and s.records[S2].attempts == 0
    assert a.prompt_spec["must_not_contain"]                      # still restricted in S2
    assert s.summary()["learner_questions"] == 1


def test_question_during_reflection_keeps_it_open():
    s = to_s4()
    a = s.submit({"type": "final_answer", "final_answer_text": "甲班32台，乙班24台"})
    assert a.type == METACOGNITIVE
    a = s.submit({"type": "reflection", "text": "怎么带回原题检查"})
    assert a.type == ANSWER_QUESTION and s.awaiting_reflection
    assert a.prompt_spec["must_not_contain"] == []                # answer already correct
    fb = s.submit({"type": "reflection", "text": "28=28，都对"})
    assert fb.type == REFLECTION_FEEDBACK and fb.next_action.type == COMPLETE


def test_one_wrong_part_is_named_not_request_for_working():
    s = to_s4()
    a = s.submit({"type": "final_answer", "final_answer_text": "甲班32台，乙班22"})
    assert a.type == EVIDENCE_REQUEST and a.request == "recheck_answer_part"
    assert a.diagnosis["details"]["right"] == ["甲班"] and a.diagnosis["details"]["wrong"] == ["乙班"]


def test_missing_unit_is_not_an_error():
    s = to_s4()
    a = s.submit({"type": "final_answer", "final_answer_text": "甲班32台，乙班24"})
    assert a.request == "add_unit" and s.records[S4].errors == []


@pytest.mark.parametrize("text, is_q", [("怎么带回原题检查", True), ("为什么要乘2", True), ("这是什么意思？", True),
                                        ("周长要乘2", False), ("32-4=28", False)])
def test_looks_like_question(text, is_q):
    assert looks_like_question(text) is is_q