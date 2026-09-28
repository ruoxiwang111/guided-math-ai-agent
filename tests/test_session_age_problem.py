"""
Regression tests from live testing on 2026-09-28 (age problem, DeepSeek live):

  小明今年的年龄是小红的3倍，5年后小明的年龄是小红的2倍。问小明和小红今年分别多少岁？

  1. a discriminating question could not be answered in words (only the equation form)
  2. S3 line 1 "3x+5=2x+5" (from 3x+5=2(x+5)) was treated as a new equation → "你还没有写出方程"
  3. the reflection question asked about "5年后" although the fix was 去括号
  4. "为什么" to a reflection → the LLM's answer quoting the learner's own equation was rejected as
     leakage, and the fallback printed the S4 task; "我不知道" skipped the reason entirely
  5. "小红今年5岁" (one of two parts) → asked for working instead of naming the missing part

Run from the project root:
    python -m pytest tests/test_session_age_problem.py -v
"""
import json
import os

os.environ["GUIDED_USE_LLM"] = "0"

import pytest
from flask import Flask

import guided_routes
from core import diagnosis as dx
from core.llm_client import TutorVoice, check_leakage
from core.review import verification_walkthrough
from core.state_manager import (
    ANSWER_QUESTION, ASK, EVIDENCE_REQUEST, EXPLANATION_FOLLOW_UP, HINT, METACOGNITIVE, REFLECTION_FEEDBACK,
    UNEXPECTED_INPUT, TutorSession, asks_for_the_reason,
)
from core.structure import validate_structure

TEXT = "小明今年的年龄是小红的3倍，5年后小明的年龄是小红的2倍。问小明和小红今年分别多少岁？"
RAW = {
    "scope": "in_scope", "topic": "年龄问题", "unknown": {"meaning": "小红今年的年龄", "unit": "岁"},
    "variable_definition": "设小红今年x岁，则小明今年3x岁",
    "known_quantities": [{"name": "小明年龄与小红的倍数关系", "value": 3},
                         {"name": "5年后的时间", "value": 5, "unit": "年"},
                         {"name": "5年后小明年龄是小红的倍数", "value": 2}],
    "relationship": "5年后小明的年龄 = 2 × 5年后小红的年龄", "equation": "3*x+5=2*(x+5)",
    "answer_parts": [{"label": "小明今年的年龄", "expression": "3*x", "unit": "岁"},
                     {"label": "小红今年的年龄", "expression": "x", "unit": "岁"}],
    "verification_conditions": [{"description": "5年后小明是小红的2倍", "lhs": "3*x+5", "op": "==", "rhs": "2*(x+5)"}],
    "alternatives": [], "e4_patterns": [], "s1_target": "小明和小红今年的年龄", "s1_intermediate": "5年后小红的年龄",
}
DEF = "设小红今年x岁"


@pytest.fixture()
def q():
    rec, checks = validate_structure(RAW, TEXT)
    assert rec is not None, [c for c in checks if not c.ok]
    rec["question_id"] = "U-age"
    return rec


def voice(q, backend=None, mode="template"):
    return TutorVoice(backend, q, mode=mode, target=q["s1"]["target"])


def to_s3(q):
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": DEF, "equation": "3x+5=2(x+5)"})
    assert s.state == "S3"
    return s


def reflection_after_s3_fix(q):
    s = to_s3(q)
    s.submit({"type": "steps", "steps": "3x+5=2(x+5)\n3x + 5 = 2x + 5\nx = 5"})
    a = s.submit({"type": "steps", "steps": "3x+5=2(x+5)\n3x + 5 = 2x + 10\nx = 5"})
    assert a.type == METACOGNITIVE and s.awaiting_reflection and s.state == "S4"
    return s, a


# ---------------------------------------------------------------- 1. answering in words

def test_discriminating_question_can_be_answered_in_words(q):
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    a = s.submit({"type": "modelling", "variable_definition": DEF, "equation": "3x+5=2x"})
    assert a.type == EVIDENCE_REQUEST and a.request == dx.ASK_DISCRIMINATING and s.awaiting_explanation
    text = voice(q).render(a).text
    assert "用文字" in text and "修改" in text                    # says how to answer
    level_before = s.records["S2"].max_hint_level
    f = s.submit({"type": "explanation", "text": "3x+5是小明5年后的年龄，2x是小红5年后年龄的2倍"})
    assert f.type == EXPLANATION_FOLLOW_UP and s.state == "S2" and not s.awaiting_explanation
    assert s.records["S2"].max_hint_level == level_before and s.records["S2"].errors == []
    assert "complete_equation" in f.prompt_spec["must_not_contain"]
    assert "修改" in voice(q).render(f).text
    assert s.submit({"type": "modelling", "variable_definition": DEF, "equation": "3x+5=2(x+5)"}).type in (ASK, METACOGNITIVE)


def test_explanation_only_in_s2_s3(q):
    s = TutorSession(q)
    s.start()
    assert s.submit({"type": "explanation", "text": "……"}).type == UNEXPECTED_INPUT


def test_explanation_follow_up_llm_path(q):
    class Fake:
        def describe(self):
            return {}

        def complete(self, system, user):
            assert "学生对自己式子的解释" in user
            return json.dumps({"message": "你说2x是小红5年后年龄的2倍——5年后小红是多少岁，用x怎么表示？改一改再提交。"},
                              ensure_ascii=False)
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": DEF, "equation": "3x+5=2x"})
    f = s.submit({"type": "explanation", "text": "2x是小红5年后年龄的2倍"})
    m = voice(q, Fake(), mode="live").render(f)
    assert m.source == "llm" and "5年后小红" in m.text


# ---------------------------------------------------------------- 2. S3 line 1 from the S2 equation

def test_line1_is_a_step_from_the_learners_equation(q):
    s = to_s3(q)
    a = s.submit({"type": "steps", "steps": "3x + 5 = 2x + 5\nx = 5"})
    assert a.type == HINT and a.category == "E7" and a.prompt_spec["first_invalid_step"] == 1
    assert a.prompt_spec["prev_line"] == "3x+5=2(x+5)" and a.prompt_spec["from_start_equation"]
    text = voice(q).render(a).text
    assert "第1行" in text and "你列的方程“3x+5=2(x+5)”" in text and "还没有写出方程" not in text


def test_working_without_repeating_the_equation_is_fine(q):
    s = to_s3(q)
    a = s.submit({"type": "steps", "steps": "3x+5=2x+10\nx=5"})
    assert s.state == "S4" and s.final_x == 5
    assert a.type in (ASK, METACOGNITIVE)


def test_line_numbers_still_refer_to_submitted_lines(q):
    d = dx.diagnose_steps(q, "3x+5=2x+10\n3x-2x=10+5\nx=15", start_equation="3x+5=2(x+5)")
    assert d.primary_error == "E7" and d.first_invalid_step == 2 and d.rule == "transposition_sign"
    assert d.details["from_start_equation"] is False and d.details["prev_line"] == "3x+5=2x+10"


def test_without_start_equation_behaviour_is_unchanged(q):
    """The D2a evaluation calls diagnose_steps without a start equation."""
    d = dx.diagnose_steps(q, "3x + 5 = 2x + 5\nx = 5")
    assert d.first_invalid_step == 1 and d.primary_error != "E7"


def test_e7_level2_hint_names_the_rule(q):
    s = to_s3(q)
    s.submit({"type": "steps", "steps": "3x+5=2(x+5)\n3x + 5 = 2x + 5\nx = 5"})
    a = s.submit({"type": "steps", "steps": "3x+5=2(x+5)\n3x + 5 = 2x + 5\nx = 0"})
    assert a.hint_level == 2 and "括号前的数要乘括号里的每一项" in voice(q).render(a).text


# ---------------------------------------------------------------- 3. reflection aims at the real fix

def test_reflection_question_names_the_corrected_error(q):
    s, a = reflection_after_s3_fix(q)
    assert a.prompt_spec["corrected_error"] == "解方程：去括号"
    text = voice(q).render(a).text
    assert "去括号" in text and "5年后" not in text


# ---------------------------------------------------------------- 4. "为什么" / "不知道"

@pytest.mark.parametrize("reply", ["为什么", "我不知道", "不懂", "？", "不清楚诶", "不会"])
def test_dont_know_gets_the_reason_then_moves_on(q, reply):
    s, _ = reflection_after_s3_fix(q)
    fb = s.submit({"type": "reflection", "text": reply})
    assert fb.type == REFLECTION_FEEDBACK and fb.task == "explain" and not s.awaiting_reflection
    text = voice(q).render(fb).text
    assert "括号前的数要乘括号里的每一项" in text
    assert fb.next_action.type == ASK and fb.next_action.state == "S4"


def test_specific_question_is_answered_and_reflection_stays_open(q):
    s, _ = reflection_after_s3_fix(q)
    a = s.submit({"type": "reflection", "text": "为什么2要乘5呢，括号外面的数不是只乘x吗"})
    assert a.type == ANSWER_QUESTION and s.awaiting_reflection
    assert a.prompt_spec["reason"].startswith("去括号时")
    assert "要点是" in voice(q).render(a).text                    # fallback answers the reflection, not S4


def test_real_reply_gets_feedback(q):
    s, _ = reflection_after_s3_fix(q)
    fb = s.submit({"type": "reflection", "text": "因为2要乘括号里的x和5"})
    assert fb.type == REFLECTION_FEEDBACK and fb.task == "feedback"
    assert "要点是" in voice(q).render(fb).text


def test_asks_for_the_reason_classifier():
    assert asks_for_the_reason("为什么") and asks_for_the_reason("我不知道") and asks_for_the_reason("")
    assert not asks_for_the_reason("因为2要乘括号里的每一项")
    assert not asks_for_the_reason("为什么2要乘5呢，括号外面的数不是只乘x吗")


def test_verification_reflection_explains_with_values(q):
    s = to_s3(q)
    s.submit({"type": "steps", "steps": "3x+5=2x+10\nx=5"})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    a = s.submit({"type": "final_answer", "final_answer_text": "小明15岁，小红5岁", "verified": False})
    assert a.type == METACOGNITIVE and a.task == "prompt_verification"
    fb = s.submit({"type": "reflection", "text": "不知道怎么检查"})
    text = voice(q).render(fb).text
    assert "3x+5 = 20" in text and "两边相等" in text


def test_walkthrough_values(q):
    assert verification_walkthrough(q, 5) == ["5年后小明是小红的2倍：3x+5 = 20，2(x+5) = 20，两边相等 ✓"]
    assert verification_walkthrough(q, 4)[0].endswith("✗")


# ---------------------------------------------------------------- leakage after the learner produced it

def test_nothing_the_learner_already_wrote_counts_as_leakage(q):
    s, _ = reflection_after_s3_fix(q)
    a = s.submit({"type": "reflection", "text": "为什么2要乘5呢，括号外面的数不是只乘x吗"})
    assert a.prompt_spec["must_not_contain"] == []                 # S2 and S3 are passed
    spec = dict(a.prompt_spec, must_not_contain=["final_answer", "complete_equation"])
    assert check_leakage("因为 2(x+5) = 2x+10，所以 3x+5=2x+10，x=5", spec) == []   # all written by the learner


def test_equation_still_protected_before_s2(q):
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    a = s.submit({"type": "modelling", "variable_definition": DEF, "equation": "3x+5=2x"})
    assert "complete_equation" in a.prompt_spec["must_not_contain"]
    assert check_leakage("可以列 3x+5=2(x+5)", a.prompt_spec) == ["complete_equation"]


def test_llm_answer_quoting_learner_equation_is_used(q):
    class Fake:
        def describe(self):
            return {}

        def complete(self, system, user):
            return json.dumps({"message": "因为 2(x+5) 是 2 个 (x+5)，2 要乘 x 也要乘 5，所以是 3x+5=2x+10。"},
                              ensure_ascii=False)
    s, _ = reflection_after_s3_fix(q)
    a = s.submit({"type": "reflection", "text": "为什么2要乘5呢，括号外面的数不是只乘x吗"})
    m = voice(q, Fake(), mode="live").render(a)
    assert m.source == "llm" and "2x+10" in m.text


# ---------------------------------------------------------------- 5. half an answer

@pytest.mark.parametrize("ans", ["小红今年5岁", "小红5岁", "5岁"])
def test_half_answer_names_the_missing_part(q, ans):
    d = dx.diagnose_final_answer(q, ans)
    assert d.rule == "answer_incomplete" and d.details["missing"] == ["小明今年的年龄"]


def test_half_answer_wording(q):
    s = to_s3(q)
    s.submit({"type": "steps", "steps": "3x+5=2x+10\nx=5"})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    a = s.submit({"type": "final_answer", "final_answer_text": "小红今年5岁"})
    text = voice(q).render(a).text
    assert "还要写出小明今年的年龄" in text and "写对了" in text and "解题步骤" not in text


@pytest.mark.parametrize("ans", ["小明15岁，小红5岁", "小明今年15岁，小红今年5岁", "小红5岁，小明15岁"])
def test_full_answers_pass(q, ans):
    assert dx.diagnose_final_answer(q, ans).status == dx.NO_ERROR


def test_wrong_number_is_not_called_incomplete(q):
    assert dx.diagnose_final_answer(q, "小红今年6岁").rule != "answer_incomplete"


# ---------------------------------------------------------------- API

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(guided_routes, "LOG_DIR", tmp_path / "logs")
    app = Flask(__name__)
    app.register_blueprint(guided_routes.guided_bp)
    return app.test_client()


def test_api_explanation_flow(client):
    sid = client.post("/api/guided/start", json={"question_id": "Q01"}).get_json()["session_id"]
    send = lambda **i: client.post("/api/guided/submit", json={"session_id": sid, "input": i}).get_json()
    send(type="s1_choice", chosen_id=next(o["id"] for o in guided_routes._sessions[sid]["s1_item"]["options"]
                                          if o["source"] == "target"))
    b = send(type="modelling", variable_definition="设小华x岁", equation="x+3=25")
    assert b["awaiting_explanation"] is True
    b = send(type="explanation", text="x是小华，另一个x是小明")
    assert b["messages"][-1]["kind"] == EXPLANATION_FOLLOW_UP and b["awaiting_explanation"] is False
    assert b["state"] == "S2" and b["expected_input"] == "modelling"
