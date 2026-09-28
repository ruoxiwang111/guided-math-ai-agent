"""
Regression tests from live testing on 2026-09-28 (Q01, DeepSeek live):

  1. After "我不确定" in S1 the LLM hint said "你已经设好小华x岁、小明(x+5)岁了" — the reference
     setup was passed to the LLM as "the learner's definition" and was not leak-checked.
  2. "不知道" typed as the definition got the same clarification twice; "设小红的年龄为x" (no 小红
     in the problem) too.
  3. A hint that asks the learner something ("这两个 x 分别代表谁的年龄？") could not be answered in
     words — only the definition/equation form was shown.

Run from the project root:
    python -m pytest tests/test_session_q01_help.py -v
"""
import json
import os
from pathlib import Path

os.environ["GUIDED_USE_LLM"] = "0"

import pytest

from core.llm_client import TutorVoice, check_leakage
from core.s1_options import build_s1_item, load_targets, to_submission
from core.state_manager import EVIDENCE_REQUEST, HINT, REVEAL, TutorSession

ROOT = Path(__file__).resolve().parents[1]
Q = {q["question_id"]: q for q in json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))["questions"]}
Q01 = Q["Q01"]
TARGETS = load_targets()
ITEM = build_s1_item(Q01, TARGETS)
LEAKED = "没关系，不确定很正常。你已经设好小华x岁、小明(x+5)岁了，这一步很好；先看看题目最后一句，它问的是谁的年龄呢？"


def voice(backend=None, mode="template"):
    return TutorVoice(backend, Q01, mode=mode, target=TARGETS["Q01"]["target"],
                      s1_options=[o["text"] for o in ITEM["options"]])


class Says:
    def __init__(self, text):
        self.text = text

    def describe(self):
        return {}

    def complete(self, system, user):
        return json.dumps({"message": self.text}, ensure_ascii=False)


def at_s2():
    s = TutorSession(Q01)
    s.start()
    s.submit(to_submission(ITEM, ITEM["correct_id"]))
    assert s.state == "S2"
    return s


# ---------------------------------------------------------------- 1. S1 must not see or say the setup

def test_s1_spec_has_no_learner_definition_and_protects_the_model():
    s = TutorSession(Q01)
    s.start()
    a = s.submit(to_submission(ITEM, "U"))
    assert a.prompt_spec["learner_variable_definition"] is None
    assert {"reference_model", "s1_target"} <= set(a.prompt_spec["must_not_contain"])
    assert "x+5" in a.prompt_spec["reference_expressions"]


def test_live_leak_is_caught_and_replaced():
    s = TutorSession(Q01)
    s.start()
    a = s.submit(to_submission(ITEM, "U"))
    v = voice(Says(LEAKED), mode="live")
    assert "reference_model" in check_leakage(LEAKED, v._spec(a))
    m = v.render(a)
    assert m.source == "template_fallback" and "x+5" not in m.text


def test_naming_the_right_option_is_caught():
    s = TutorSession(Q01)
    s.start()
    a = s.submit(to_submission(ITEM, "U"))
    v = voice(Says(f"答案是{TARGETS['Q01']['target']}。"), mode="live")
    assert v.render(a).source == "template_fallback"


def test_s1_hint_prompt_gets_the_options():
    s = TutorSession(Q01)
    s.start()
    a = s.submit(to_submission(ITEM, "U"))
    assert voice()._spec(a)["s1_options"] == [o["text"] for o in ITEM["options"]]


def test_learner_written_expression_is_not_a_leak():
    s = at_s2()
    s.submit({"type": "modelling", "variable_definition": "设小华x岁，小明x+5岁", "equation": "x+x+5=30"})
    a = s.submit({"type": "modelling", "variable_definition": "设小华x岁，小明x+5岁", "equation": "x+x+5=30"})
    assert "reference_model" not in check_leakage("你写的小明 x+5 岁是对的", voice()._spec(a))


def test_protection_ends_after_s2():
    s = at_s2()
    a = s.submit({"type": "modelling", "variable_definition": Q01["variable_definition"], "equation": Q01["equation"]})
    assert "reference_model" not in (a.prompt_spec.get("must_not_contain") or [])


# ---------------------------------------------------------------- 2. 不知道 and unclear definitions

def test_dont_know_in_s2_is_help_not_error():
    s = at_s2()
    a = s.submit({"type": "modelling", "variable_definition": "不知道", "equation": ""})
    assert a.type == HINT and a.hint_level == 1 and a.category is None and s.records["S2"].errors == []
    text = voice().render(a).text
    assert text.startswith("没关系") and TARGETS["Q01"]["target"] in text and "x+5" not in text
    a = s.submit({"type": "modelling", "variable_definition": "不知道", "equation": ""})
    assert a.hint_level == 2 and "用 x 把另一个量也表示出来" in voice().render(a).text


def test_dont_know_in_s3_and_s4():
    s = at_s2()
    s.submit({"type": "modelling", "variable_definition": Q01["variable_definition"], "equation": Q01["equation"]})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    a = s.submit({"type": "steps", "steps": "不会"})
    assert a.type == HINT and "去括号" in voice().render(a).text
    s.submit({"type": "steps", "steps": "2x+5=25\n2x=20\nx=10"})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    a = s.submit({"type": "final_answer", "final_answer_text": "不知道"})
    assert a.type == HINT and TARGETS["Q01"]["target"] in voice().render(a).text


def test_work_is_never_taken_for_a_help_request():
    assert not TutorSession._is_help_request({"variable_definition": "设小华x岁", "equation": ""})
    assert not TutorSession._is_help_request({"steps": "x=5"})
    assert not TutorSession._is_help_request({"final_answer_text": "小华10岁"})
    assert TutorSession._is_help_request({"final_answer_text": "不会"})


def test_name_not_in_the_problem():
    s = at_s2()
    a = s.submit({"type": "modelling", "variable_definition": "设小红的年龄为x", "equation": ""})
    assert a.type == EVIDENCE_REQUEST and "题目里没有“小红”" in voice().render(a).text


def test_second_unclear_definition_is_more_specific():
    s = at_s2()
    first = voice().render(s.submit({"type": "modelling", "variable_definition": "设年龄为x", "equation": ""})).text
    second = voice().render(s.submit({"type": "modelling", "variable_definition": "设年龄为x", "equation": ""})).text
    assert first != second and TARGETS["Q01"]["target"] in second


def test_reveal_after_help_shows_the_reference_setup():
    s = at_s2()
    for _ in range(4):
        s.submit({"type": "modelling", "variable_definition": "不知道", "equation": ""})
    a = s.submit({"type": "modelling", "variable_definition": "不知道", "equation": ""})
    assert a.type == REVEAL and Q01["variable_definition"] in voice().render(a).text


# ---------------------------------------------------------------- 3. every hint in S2/S3 can be answered in words

def test_words_box_after_any_hint_in_s2():
    s = at_s2()
    a = s.submit({"type": "modelling", "variable_definition": "设小明的年龄为x", "equation": "x+x=25"})
    assert a.type in (HINT, EVIDENCE_REQUEST) and s.awaiting_explanation


def test_no_words_box_in_s1_or_s4():
    s = TutorSession(Q01)
    s.start()
    s.submit(to_submission(ITEM, "U"))
    assert not s.awaiting_explanation
