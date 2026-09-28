"""
Tests for core/llm_client.py — no network: a fake backend stands in for DeepSeek.

Run from the project root:
    python -m pytest tests/test_llm_client.py -v
"""
import json
from pathlib import Path

import pytest

from core.llm_client import HINTS, LLMError, TutorVoice, check_leakage
from core.state_manager import (
    ASK, COMPLETE, EVIDENCE_REQUEST, HINT, METACOGNITIVE, REVEAL, TutorAction, TutorSession,
)

ROOT = Path(__file__).resolve().parents[1]
Q = {q["question_id"]: q for q in json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))["questions"]}


class FakeBackend:
    """Returns queued replies; records prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) and not r.startswith("MSG:") else json.dumps({"message": r[4:]}, ensure_ascii=False)


def hint_action(qid="Q01", level=3, category="E3", state="S2", k=None):
    q = Q[qid]
    forbidden = [] if level >= 4 else ["final_answer"] + (["complete_equation"] if level <= 2 else []) \
        + (["key_intermediate_value"] if level == 1 else [])
    return TutorAction(HINT, state, category=category, hint_level=level, prompt_spec={
        "question_id": qid, "question": q["question"], "learner_variable_definition": q["variable_definition"],
        "reference_answer": str(q["answer"]), "reference_equation": q["equation"],
        "hint_level": level, "must_not_contain": forbidden, "first_invalid_step": k})


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cat", ["E1", "E2", "E3", "E4", "E5", "E6", "E7", None])
@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_category_has_level_1_to_3_templates(cat, level):
    assert HINTS[cat][level]


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_template_mode_never_calls_the_llm(level):
    fake = FakeBackend()
    m = TutorVoice(fake, Q["Q01"], mode="template").render(hint_action(level=level))
    assert m.source == "template" and fake.calls == []


@pytest.mark.parametrize("level", [1, 2])
def test_live_mode_words_low_levels_too(level):
    fake = FakeBackend("MSG:你把两个人的年龄都表示出来了，再想想“和是25”对应哪一部分？")
    m = TutorVoice(fake, Q["Q01"], mode="live").render(hint_action(level=level))
    assert m.source == "llm" and len(fake.calls) == 1


def test_e6_e7_template_names_the_line():
    m = TutorVoice(None, Q["Q05"]).render(hint_action("Q05", level=1, category="E7", state="S3", k=3))
    assert m.text.startswith("看第3行")


def test_e4_level_2_uses_the_phrase_of_the_subtype():
    a = hint_action(level=2, category="E4")
    a.prompt_spec["error_subtype"] = "E4-06"
    assert "打……折" in TutorVoice(None, Q["Q03"]).render(a).text


def test_non_hint_actions_are_templates_in_template_mode():
    v = TutorVoice(FakeBackend(), Q["Q01"], mode="template")
    for a in [TutorAction(ASK, "S2", task="define_x_and_equation"),
              TutorAction(EVIDENCE_REQUEST, "S2", request="clarify_variable_definition"),
              TutorAction(METACOGNITIVE, "S4", task="prompt_verification"),
              TutorAction(COMPLETE, "DONE")]:
        m = v.render(a)
        assert m.source == "template" and m.text


def test_notation_clarification_uses_normaliser_message():
    s = TutorSession(Q["Q01"]); s.start(); s.submit({"type": "s1_choice", "correct": True})
    a = s.submit({"type": "modelling", "variable_definition": "设小华x岁", "equation": "1/3x+5=25"})
    text = TutorVoice(None, Q["Q01"]).render(a).text
    assert "(1/3)×x" in text and "1/(3×x)" in text


# ---------------------------------------------------------------------------
# leakage check (evaluation_plan §3.9.2)
# ---------------------------------------------------------------------------

def spec(qid, level):
    return hint_action(qid, level).prompt_spec


def test_answer_value_is_flagged():
    assert check_leakage("小华应该是10岁。", spec("Q01", 3)) == ["final_answer"]


def test_numbers_from_the_question_are_not_flagged():
    # Q04: answer 250; "10分钟" and "5500米" are given in the question
    assert check_leakage("回家也骑了10分钟，一共5500米。", spec("Q04", 3)) == []


def test_line_numbers_are_not_flagged():
    # Q10 answer is 2; "第2行" is a line reference
    assert check_leakage("看第2行的计算。", spec("Q10", 3)) == []


def test_equivalent_equation_is_flagged_at_level_2():
    assert "complete_equation" in check_leakage("你可以列 2x+5=25 试试。", spec("Q01", 2))


def test_equation_allowed_at_level_3():
    assert check_leakage("可以列 2x+5=25 再解。", spec("Q01", 3)) == []


def test_level_4_has_no_constraints():
    assert check_leakage("x=10，所以小华10岁。", spec("Q01", 4)) == []


# ---------------------------------------------------------------------------
# level 3–4 generation with fallback
# ---------------------------------------------------------------------------

def test_clean_llm_hint_is_used():
    fake = FakeBackend("MSG:把小明和小华的年龄分别用 x 表示出来，再想想“年龄和”对应哪个等式。")
    m = TutorVoice(fake, Q["Q01"]).render(hint_action(level=3))
    assert m.source == "llm" and "年龄和" in m.text and len(fake.calls) == 1


def test_leaking_llm_hint_is_retried_then_replaced():
    fake = FakeBackend("MSG:答案是10岁。", "MSG:小华10岁，小明15岁。")
    m = TutorVoice(fake, Q["Q01"]).render(hint_action(level=3))
    assert m.source == "template_fallback" and m.text == HINTS["E3"][3]
    assert [a["violations"] for a in m.attempts] == [["final_answer"], ["final_answer"]]
    assert m.leakage_violations == []


def test_second_attempt_can_succeed():
    fake = FakeBackend("MSG:答案是10岁。", "MSG:先分别写出两个人的年龄表达式。")
    m = TutorVoice(fake, Q["Q01"]).render(hint_action(level=3))
    assert m.source == "llm" and len(m.attempts) == 1


@pytest.mark.parametrize("reply", ["not json", json.dumps({"text": "x"}), LLMError("timeout")])
def test_bad_llm_output_falls_back(reply):
    m = TutorVoice(FakeBackend(reply, reply), Q["Q01"]).render(hint_action(level=3))
    assert m.source == "template_fallback"


def test_level_4_fallback_includes_relationship():
    m = TutorVoice(None, Q["Q01"]).render(hint_action(level=4))
    assert Q["Q01"]["relationship"] in m.text


def test_prompt_carries_constraints_to_the_llm():
    fake = FakeBackend("MSG:先写出表达式。")
    TutorVoice(fake, Q["Q01"]).render(hint_action(level=3))
    system, user = fake.calls[0]
    assert "must_not_contain" in system and json.loads(user)["must_not_contain"] == ["final_answer"]
    assert json.loads(user)["提示等级"] == 3


def test_reveal_shows_the_step():
    s = TutorSession(Q["Q01"]); s.start(); s.submit({"type": "s1_choice", "correct": True})
    wrong = {"type": "modelling", "variable_definition": "设小华x岁，小明(x-5)岁", "equation": "x+(x-5)=25"}
    for _ in range(4):
        s.submit(wrong)
    a = s.submit(wrong)
    assert a.type == REVEAL
    assert Q["Q01"]["equation"] in TutorVoice(None, Q["Q01"]).render(a).text


# ---------------------------------------------------------------------------
# S1 free text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reply, expected", [
    ('{"matches_target": true}', True), ('{"matches_target": false}', False),
    ('{"matches_target": "unclear"}', None), ("garbage", None), (LLMError("down"), None),
])
def test_classify_s1(reply, expected):
    v = TutorVoice(FakeBackend(reply), Q["Q01"])
    assert v.classify_s1(Q["Q01"]["question"], "小明和小华今年各自的年龄", "求两个人的年龄") is expected


def test_classify_s1_without_backend_returns_none():
    assert TutorVoice(None).classify_s1("题", "目标", "回答") is None


# ---------------------------------------------------------------------------
# full session rendered offline: every message is non-empty and leak-free
# ---------------------------------------------------------------------------

def test_offline_session_renders_every_action():
    q = Q["Q05"]
    s, v = TutorSession(q), TutorVoice(None, q)
    actions = [s.start(), s.submit({"type": "s1_choice", "correct": True})]
    wrong = {"type": "modelling", "variable_definition": "设宽为x厘米，长为(x+4)厘米", "equation": "x+(x+4)=28"}
    actions += [s.submit(wrong) for _ in range(3)]
    actions.append(s.submit({"type": "modelling", "variable_definition": q["variable_definition"], "equation": q["equation"]}))
    for a in actions:
        m = v.render(a)
        assert m.text and m.leakage_violations == []


def test_correct_system_gets_specific_encouraging_message():
    q = Q["Q15"]
    s = TutorSession(q); s.start(); s.submit({"type": "s1_choice", "correct": True})
    a = s.submit({"type": "modelling", "variable_definition": "设x表示甲", "equation": "x-4=y+4，x+y=56"})
    assert a.type == EVIDENCE_REQUEST and s.records["S2"].errors == []
    text = TutorVoice(None, q).render(a).text
    assert "方程组是对的" in text and "只用一个未知数" in text


# --- learner questions -------------------------------------------------------

def _ask(qid, text, final=False):
    q = Q[qid]
    s = TutorSession(q); s.start(); s.submit({"type": "s1_choice", "correct": True})
    if final:
        s.submit({"type": "modelling", "variable_definition": q["variable_definition"], "equation": q["equation"]})
        s.submit({"type": "steps", "steps": [q["equation"], f"x={q['answer']}"]})
        s.submit({"type": "final_answer", "final_answer_text": q["final_answer_text"]})
        return s.submit({"type": "reflection", "text": text})
    return s.submit({"type": "question", "text": text})


def test_verification_question_fallback_lists_conditions():
    a = _ask("Q15", "怎么带回原题检查", final=True)
    text = TutorVoice(None, Q["Q15"]).render(a).text
    assert "代回原题检查" in text and "转移后两班相同" in text and "甲班32台" in text


def test_question_answered_by_llm_when_clean():
    fake = FakeBackend("MSG:可以设人数较少、关系好表示的那个班为 x，再用 x 表示另一个班。")
    m = TutorVoice(fake, Q["Q15"]).render(_ask("Q15", "设哪个量为x比较好？"))
    assert m.source == "llm" and "_chat" not in m.text
    assert "学生的问题" in fake.calls[0][1]


def test_question_answer_that_leaks_is_replaced():
    fake = FakeBackend("MSG:乙班是24台。", "MSG:乙班原来24台。")
    m = TutorVoice(fake, Q["Q15"]).render(_ask("Q15", "乙班多少台？"))
    assert m.source == "template_fallback" and "24" not in m.text


def test_answer_part_message_names_the_part():
    s = TutorSession(Q["Q15"]); s.start(); s.submit({"type": "s1_choice", "correct": True})
    q = Q["Q15"]
    s.submit({"type": "modelling", "variable_definition": q["variable_definition"], "equation": q["equation"]})
    s.submit({"type": "steps", "steps": [q["equation"], "x=24"]})
    a = s.submit({"type": "final_answer", "final_answer_text": "甲班32台，乙班22"})
    text = TutorVoice(None, q).render(a).text
    assert text.startswith("甲班的答案对了") and "乙班再核对一下" in text


def test_reflection_question_is_worded_from_learner_work_in_live_mode():
    q = Q["Q01"]
    s = TutorSession(q); s.start(); s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": "设小华x岁，小明(x-5)岁", "equation": "x+(x-5)=25"})
    a = s.submit({"type": "modelling", "variable_definition": "设小华x岁，则小明(x+5)岁", "equation": "x+(x+5)=25"})
    fake = FakeBackend("MSG:你把小明从 x-5 改成了 x+5，为什么“大5岁”要用加法？")
    m = TutorVoice(fake, q, mode="live").render(a)
    work = json.loads(fake.calls[0][1])["学生最近几次的作答（从早到晚）"]
    assert m.source == "llm" and any("x-5" in (w.get("equation") or "") for w in work)


def test_cached_mode_fills_learner_slots():
    q = Q["Q05"]
    s = TutorSession(q); s.start(); s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": q["variable_definition"], "equation": q["equation"]})
    a = s.submit({"type": "steps", "steps": "4x+8=28\n4x=36\nx=9"})
    cache = {"Q05|S3|E7|-|L1": "{acknowledge}。你从“{prev_line}”写到“{learner_line}”，8 移到右边以后符号有没有变？"}
    m = TutorVoice(None, q, mode="cached", cache=cache).render(a)
    assert m.source == "cache" and "“4x+8=28”写到“4x=36”" in m.text and m.text.startswith("第1行没问题")


def test_cached_entry_with_missing_slot_falls_back():
    cache = {"Q01|S2|E3|-|L3": "你写的“{learner_line}”……"}          # S2 has no learner_line
    m = TutorVoice(None, Q["Q01"], mode="cached", cache=cache).render(hint_action(level=3))
    assert m.source == "template"


def test_cached_entry_that_leaks_is_not_used():
    cache = {"Q01|S2|E3|-|L3": "小华其实是10岁。"}
    m = TutorVoice(None, Q["Q01"], mode="cached", cache=cache).render(hint_action(level=3))
    assert m.source == "template"


def test_quoting_learners_own_equation_is_not_leakage():
    spec = dict(hint_action("Q05", level=1).prompt_spec, learner_input={"steps": "4x+8=28\n4x=36"})
    assert check_leakage("你从 4x+8=28 写到 4x=36", spec) == []
    assert check_leakage("可以列 2(x+x+4)=28", dict(spec, learner_input={})) == ["complete_equation"]


def test_empty_acknowledge_slot_is_dropped():
    from core.llm_client import fill_slots
    assert fill_slots("{acknowledge}。再看看第{line_no}行。", {"line_no": 1, "acknowledge": []}) == "再看看第1行。"