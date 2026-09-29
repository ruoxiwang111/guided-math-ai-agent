"""
D2b — diagnosis → intervention, three core scenarios (template wording, no LLM).

  D2b-1 execution: transposition sign     x - 12 = 8  →  x = 8 - 12
  D2b-2 execution: distribution           2(x + x + 3) = 26  →  2x + x + 3 = 26
  D2b-3 modelling: age relation           3x + 5 = 2x + 5   (should be 2(x + 5))

Pass criteria per scenario: the right error kind at the right place; L1 points in a direction
without the corrected line / equation / answer; each further hint is different and more
specific; the learner stays in the current step after a hint; "看这一步的参考" appears only after
2 tries, shows only the wrong line (S3) and is logged as requested by the learner; after the
fix the session reaches the correct final answer.

The LLM wording of the same actions must be checked live (evaluation_plan: D2b manual review).

Run from the project root:
    python -m pytest tests/test_d2b.py -v
"""
import os

os.environ["GUIDED_USE_LLM"] = "0"

import pytest

from core.llm_client import TutorVoice, check_leakage
from core.state_manager import DONE, HINT, REVEAL, TutorSession
from core.structure import validate_structure


def build(text, qid, **kw):
    raw = {"scope": "in_scope", "alternatives": [], "e4_patterns": [], "s1_intermediate": "",
           "unknown": {"meaning": "", "unit": ""}}
    raw.update(kw)
    q, checks = validate_structure(raw, text)
    assert q is not None, [c for c in checks if not c.ok]
    q["question_id"] = qid
    return q


MONEY = build("小明有一些钱，买一本12元的书后还剩8元。问小明原来有多少钱？", "D2b-1",
              topic="购物与价格问题", variable_definition="设小明原来有x元",
              known_quantities=[{"name": "书价", "value": 12, "unit": "元"}, {"name": "剩下", "value": 8, "unit": "元"}],
              relationship="原有的钱 - 书价 = 剩下的钱", equation="x-12=8",
              answer_parts=[{"label": "", "expression": "x", "unit": "元"}],
              verification_conditions=[{"description": "花12元后剩8元", "lhs": "x-12", "op": "==", "rhs": "8"}],
              s1_target="小明原来有多少钱")
RECT = build("一个长方形的长比宽多3厘米，长方形的周长是26厘米。求这个长方形的长和宽。", "D2b-2",
             topic="几何图形问题-周长", variable_definition="设宽为x厘米，则长为(x+3)厘米",
             known_quantities=[{"name": "长比宽多", "value": 3, "unit": "厘米"}, {"name": "周长", "value": 26, "unit": "厘米"}],
             relationship="2×(长+宽)=周长", equation="2*(x+x+3)=26",
             answer_parts=[{"label": "长", "expression": "x+3", "unit": "厘米"},
                           {"label": "宽", "expression": "x", "unit": "厘米"}],
             verification_conditions=[{"description": "周长26", "lhs": "2*(x+x+3)", "op": "==", "rhs": "26"}],
             s1_target="长和宽")
AGE = build("小明今年的年龄是小红的3倍，5年后小明的年龄是小红的2倍。问小明和小红今年分别多少岁？", "D2b-3",
            topic="年龄问题", variable_definition="设小红今年x岁，则小明今年3x岁",
            known_quantities=[{"name": "今年倍数", "value": 3}, {"name": "5年后倍数", "value": 2},
                              {"name": "年数", "value": 5, "unit": "年"}],
            relationship="5年后小明的年龄 = 2 × 5年后小红的年龄", equation="3*x+5=2*(x+5)",
            answer_parts=[{"label": "小明", "expression": "3*x", "unit": "岁"},
                          {"label": "小红", "expression": "x", "unit": "岁"}],
            verification_conditions=[{"description": "5年后2倍", "lhs": "3*x+5", "op": "==", "rhs": "2*(x+5)"}],
            s1_target="小明和小红今年的年龄")


class Run:
    def __init__(self, q):
        self.q = q
        self.s = TutorSession(q)
        self.v = TutorVoice(None, q, mode="template", target=q["s1"]["target"])
        self.s.start()
        self.s.submit({"type": "s1_choice", "correct": True})

    def send(self, **inp):
        if self.s.awaiting_reflection and inp["type"] != "reflection":
            self.s.submit({"type": "reflection", "text": "ok"})
        n = len(self.s.events)
        a = self.s.submit(inp)
        self.new_events = self.s.events[n:]
        self.text = self.v.render(a).text
        self.leaks = check_leakage(self.text, self.v._spec(a))
        return a

    def diag(self):
        return next(e for e in self.new_events if e["event"] == "diagnosis")


# ---------------------------------------------------------------- D2b-1 移项变号

def test_d2b1_transposition():
    r = Run(MONEY)
    r.send(type="modelling", variable_definition="设小明原来有x元", equation="x-12=8")
    wrong = "x - 12 = 8\nx = 8 - 12"

    a = r.send(type="steps", steps=wrong)
    d = r.diag()
    assert (d["diagnosed_error"], d["rule"], d["first_invalid_step"]) == ("E7", "transposition_sign", 2)
    assert a.type == HINT and a.hint_level == 1 and r.s.state == "S3" and not r.leaks
    first = r.text
    assert "第2行" in first and "20" not in first and "8 + 12" not in first
    assert not r.s.can_reveal()

    a = r.send(type="steps", steps=wrong)
    assert a.hint_level == 2 and r.text != first and "变" in r.text and not r.leaks
    assert r.s.can_reveal()                                          # after 2 tries

    a = r.send(type="reveal_request")
    assert a.type == REVEAL and a.prompt_spec["step_reveal"] and r.s.state == "S3"
    assert "第2行应该是" in r.text
    ev = next(e for e in r.new_events if e["event"] == "reveal_step")
    assert ev["requested_by_learner"] and ev["scope"] == "line" and ev["line_no"] == 2
    assert r.s.summary()["states"]["S3"]["reveal_requested"]

    r.send(type="steps", steps="x - 12 = 8\nx = 20")
    assert r.s.state == "S4"
    r.send(type="final_answer", final_answer_text="20元", verified=True, active_verification=True)
    assert r.s.state == DONE


# ---------------------------------------------------------------- D2b-2 分配律

def test_d2b2_distribution():
    r = Run(RECT)
    r.send(type="modelling", variable_definition="设宽为x厘米，长为x+3厘米", equation="2(x + x + 3) = 26")
    wrong = "2(x + x + 3) = 26\n2x + x + 3 = 26"
    texts = []
    for level in (1, 2, 3):
        a = r.send(type="steps", steps=wrong)
        d = r.diag()
        assert (d["diagnosed_error"], d["rule"], d["first_invalid_step"]) == ("E7", "distribute_first_term_only", 2)
        assert a.type == HINT and a.hint_level == level and r.s.state == "S3" and not r.leaks
        assert "2x + 2x + 6" not in r.text and "4x + 6" not in r.text      # never the corrected line
        texts.append(r.text)
    assert len(set(texts)) == 3                                           # escalates, never repeats
    assert "括号" in texts[1]

    a = r.send(type="reveal_request")
    assert a.prompt_spec["step_reveal"] and "4x + 6 = 26" in r.text and r.s.state == "S3"

    r.send(type="steps", steps="2(x + x + 3) = 26\n2x + 2x + 6 = 26\n4x + 6 = 26\nx = 5")
    assert r.s.state == "S4"
    r.send(type="final_answer", final_answer_text="宽5厘米，长8厘米", verified=True, active_verification=True)
    assert r.s.state == DONE


# ---------------------------------------------------------------- D2b-3 建模错误

def test_d2b3_modelling():
    r = Run(AGE)
    wrong = dict(type="modelling", variable_definition="设小红今年x岁，小明今年3x岁", equation="3x + 5 = 2x + 5")
    texts = []
    for level in (1, 2, 3):
        a = r.send(**wrong)
        d = r.diag()
        assert d["rule"] == "one_side_wrong" and d.get("diagnosed_error") is None   # modelling, not labelled
        assert a.type == HINT and a.hint_level == level and r.s.state == "S2" and not r.leaks
        assert "展开" not in r.text and "去括号" not in r.text and "计算" not in r.text   # not an execution error
        assert "2(x + 5)" not in r.text and "2(x+5)" not in r.text                     # no corrected side
        texts.append(r.text)
    assert "左边" in texts[0] and "3x + 5" in texts[0] and "右边" in texts[0]           # located
    assert "2倍" in texts[1] and "完整的量" in texts[1]                                  # more specific
    assert "5年后小红的年龄" in texts[2]                                                # relationship in words
    assert r.s.records["S2"].errors == []

    a = r.send(type="modelling", variable_definition="设小红今年x岁，小明今年3x岁", equation="3x + 5 = 2(x + 5)")
    assert r.s.state == "S3" and "少了括号" in r.text                                    # reflection names the fix
    r.send(type="reflection", text="2倍要乘整个5年后的年龄")
    r.send(type="steps", steps="3x + 5 = 2x + 10\nx = 5")
    r.send(type="final_answer", final_answer_text="小红5岁，小明15岁", verified=True, active_verification=True)
    assert r.s.state == DONE


def test_located_side_needs_a_matching_side():
    from core.diagnosis import locate_wrong_side
    assert locate_wrong_side("3x = 2x", "3*x+5=2*(x+5)") is None
    side = locate_wrong_side("2x + 5 = 3x + 5", "3*x+5=2*(x+5)")          # sides swapped
    assert side["correct_side_name"] == "右边" and side["missing_brackets"]


@pytest.mark.parametrize("prev,cur,expected", [
    ("x-12=8", "x=8-12", "x = 20"),
    ("2*(x+x+3)=26", "2*x+x+3=26", "4x + 6 = 26"),
    ("4*x+6=26", "4*x=26+6", "4x = 20"),
])
def test_correct_next_line(prev, cur, expected):
    from core.diagnosis import correct_next_line
    assert correct_next_line(prev, cur) == expected
