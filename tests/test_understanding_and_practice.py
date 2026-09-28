"""
S1 "我不确定", the understanding check before guiding an extracted problem, knowledge points
in the review, and "练一道同类题".

The LLM is replaced by a fake backend so the safety properties can be tested offline:
  * a learner correction only reaches the extraction; the independent solve sees the problem
    text alone → a WRONG correction ends in "not guidable", never in a wrong structure
  * a generated similar problem is guided only if it passes the same checks as any photo

Run from the project root:
    python -m pytest tests/test_understanding_and_practice.py -v
"""
import json
import os
from pathlib import Path

os.environ["GUIDED_USE_LLM"] = "0"

import pytest
from flask import Flask

import guided_routes
from core.llm_client import TutorVoice
from core.review import build_review, knowledge_points, topic_family
from core.s1_options import build_s1_item, load_targets, to_submission
from core.state_manager import HINT, TutorSession
from core.structure import EXTRACT_SYSTEM, SOLVE_SYSTEM
from core.variants import VARIANT_SYSTEM, bank_similar, generate_similar

ROOT = Path(__file__).resolve().parents[1]
BANK = json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))["questions"]
BY_ID = {q["question_id"]: q for q in BANK}

MEET = "甲、乙两人从相距36千米的两地同时出发相向而行，甲每小时走5千米，乙每小时走4千米，几小时后两人相遇？"


def meet_raw(speed_b=4, known_b_name="乙的速度"):
    return {
        "scope": "in_scope", "scope_reason": "", "topic": "行程问题-相遇",
        "unknown": {"meaning": "相遇时间", "unit": "小时"}, "variable_definition": "设经过x小时两人相遇",
        "known_quantities": [{"name": "两地距离", "value": 36, "unit": "千米"},
                             {"name": "甲的速度", "value": 5, "unit": "千米/小时"},
                             {"name": known_b_name, "value": speed_b, "unit": "千米/小时"}],
        "relationship": "甲走的路程+乙走的路程=36", "equation": f"5*x+{speed_b}*x=36",
        "answer_parts": [{"label": "", "expression": "x", "unit": "小时"}],
        "verification_conditions": [{"description": "路程和为36", "lhs": f"5*x+{speed_b}*x", "op": "==", "rhs": "36"}],
        "alternatives": [], "e4_patterns": [], "s1_target": "相遇所用的时间", "s1_intermediate": "甲走的路程",
    }


class FakeBackend:
    """Extraction follows the learner note if it names a speed; the independent solve never sees it."""

    def __init__(self, first_raw=None, variant_text=None, variant_raw=None):
        self.first_raw = first_raw or meet_raw()
        self.variant_text = variant_text
        self.variant_raw = variant_raw
        self.calls = []

    def describe(self):
        return {"backend": "fake"}

    def complete(self, system, user):
        self.calls.append(system[:10])
        if system == VARIANT_SYSTEM:
            return json.dumps({"question": self.variant_text, "topic": "行程问题-相遇"}, ensure_ascii=False)
        if system == SOLVE_SYSTEM:
            if self.variant_text and user == self.variant_text:
                return json.dumps({"parts": [{"label": "x", "value": "3"}]})
            return json.dumps({"parts": [{"label": "x", "value": "4"}]})      # the true answer of MEET
        payload = json.loads(user)
        if self.variant_text and payload["题目"] == self.variant_text:
            return json.dumps(self.variant_raw, ensure_ascii=False)
        note = payload.get("学生对题意的说明", "")
        if "6千米" in note:
            return json.dumps(meet_raw(speed_b=6), ensure_ascii=False)        # follows a WRONG correction
        if note:
            return json.dumps(meet_raw(), ensure_ascii=False)                 # corrected reading
        return json.dumps(self.first_raw, ensure_ascii=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(guided_routes, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(guided_routes, "EXTRACT_DIR", tmp_path / "extracted")
    monkeypatch.setattr(guided_routes, "_extracted", {})
    monkeypatch.setattr(guided_routes, "_corrections", {})
    app = Flask(__name__)
    app.register_blueprint(guided_routes.guided_bp)
    return app.test_client()


def post(client, url, **body):
    r = client.post(url, json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ---------------------------------------------------------------- S1 我不确定

def test_unsure_option_is_separate_and_not_an_error():
    q = BY_ID["Q05"]
    targets = load_targets()
    item = build_s1_item(q, targets)
    assert len(item["options"]) == 4 and item["unsure_option"]["text"] == "我不确定"
    sub = to_submission(item, "U")
    assert sub["unsure"] and not sub["correct"]
    s = TutorSession(q)
    s.start()
    a = s.submit(sub)
    assert a.type == HINT and a.category is None and s.state == "S1"
    assert s.records["S1"].errors == []
    text = TutorVoice(None, q, mode="template", target=targets["Q05"]["target"]).render(a).text
    assert text.startswith("没关系") and "最后一句" in text
    s.submit(to_submission(item, item["correct_id"]))
    assert s.state == "S2"
    assert next(j for j in build_review(s)["journey"] if j["state"] == "S1")["status"] == "在提示下完成"


def test_unsure_via_api(client):
    b = post(client, "/api/guided/start", question_id="Q05")
    assert b["s1_item"]["unsure"] == {"id": "U", "text": "我不确定"}
    b = post(client, "/api/guided/submit", session_id=b["session_id"], input={"type": "s1_choice", "chosen_id": "U"})
    assert b["state"] == "S1" and b["messages"][-1]["kind"] == "hint"


def test_s1_reveal_names_the_target():
    q = BY_ID["Q05"]
    targets = load_targets()
    item = build_s1_item(q, targets)
    s = TutorSession(q)
    v = TutorVoice(None, q, mode="template", target=targets["Q05"]["target"])
    s.start()
    for _ in range(5):
        a = s.submit(to_submission(item, "U"))
    assert a.type == "reveal_step" and targets["Q05"]["target"] in v.render(a).text


# ---------------------------------------------------------------- understanding check

def test_prepare_shows_known_conditions_only(client, monkeypatch):
    monkeypatch.setattr(guided_routes, "_backend", FakeBackend())
    b = post(client, "/api/guided/prepare", text=MEET)
    assert b["usable"] and b["source"] == "extracted"
    ks = b["understanding"]["known_quantities"]
    assert ks == ["两地距离：36 千米", "甲的速度：5 千米/小时", "乙的速度：4 千米/小时"]
    shown = json.dumps(b["understanding"], ensure_ascii=False)
    assert "相遇所用的时间" not in shown and "5*x" not in shown          # no target, no equation


def test_bank_question_needs_no_confirmation(client):
    b = post(client, "/api/guided/prepare", text=BY_ID["Q05"]["question"])
    assert b["source"] == "bank" and "understanding" not in b


def test_correction_rereads(client, monkeypatch):
    fake = FakeBackend(first_raw=meet_raw(known_b_name="甲乙速度差"))       # a misnamed condition
    monkeypatch.setattr(guided_routes, "_backend", fake)
    b = post(client, "/api/guided/prepare", text=MEET)
    assert "甲乙速度差：4 千米/小时" in b["understanding"]["known_quantities"]
    b = post(client, "/api/guided/prepare", text=MEET, correction="4千米/小时是乙的速度")
    assert b["usable"] and "乙的速度：4 千米/小时" in b["understanding"]["known_quantities"]
    assert b["corrections"] == 1
    s = post(client, "/api/guided/start", question_id=b["question_id"], understanding_confirmed=True)
    sess = guided_routes._sessions[s["session_id"]]["session"]
    assert sess.understanding == {"confirmed": True, "corrections": 1, "notes": ["4千米/小时是乙的速度"]}
    assert any(e["event"] == "understanding_check" for e in sess.events)


def test_wrong_correction_cannot_change_the_problem(client, monkeypatch):
    """The learner claims 6 km/h; extraction follows, the independent solve (text only) says 4 → not guided."""
    monkeypatch.setattr(guided_routes, "_backend", FakeBackend())
    b = post(client, "/api/guided/prepare", text=MEET)
    qid = b["question_id"]
    b = post(client, "/api/guided/prepare", text=MEET, correction="乙每小时走6千米")
    assert b["usable"] is False and "核对没有通过" in b["message"]
    assert qid not in guided_routes._extracted


def test_corrections_are_capped(client, monkeypatch):
    monkeypatch.setattr(guided_routes, "_backend", FakeBackend())
    post(client, "/api/guided/prepare", text=MEET)
    post(client, "/api/guided/prepare", text=MEET, correction="第一次说明")
    b = post(client, "/api/guided/prepare", text=MEET, correction="第二次说明")
    assert b["usable"] and b["can_correct"] is False
    b = post(client, "/api/guided/prepare", text=MEET, correction="第三次说明")
    assert b["usable"] is False


# ---------------------------------------------------------------- knowledge points

def test_topic_families():
    assert topic_family("往返路程") == "行程问题"
    assert topic_family("行程问题-相遇") == "行程问题"
    assert topic_family("打折求原价") == "百分比与折扣问题"
    assert topic_family("长方形周长") == "几何图形问题"
    assert topic_family("某种新题型") == "某种新题型"
    assert topic_family(None) is None


def test_knowledge_points_follow_the_equation():
    assert knowledge_points(BY_ID["Q03"])[1] == "解一元一次方程：去分母或小数系数、系数化为 1"   # 0.8x = 160
    assert "去括号" in knowledge_points(BY_ID["Q05"])[1] and "合并同类项" in knowledge_points(BY_ID["Q05"])[1]
    assert knowledge_points(BY_ID["Q05"])[0] == "列一元一次方程解应用题（几何图形问题）"


def test_weak_points_only_from_this_attempt():
    q = BY_ID["Q05"]
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": "设宽为x厘米", "equation": "2(x+x+4)=28"})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    s.submit({"type": "steps", "steps": "4x+8=28\n4x=36\nx=9"})
    s.submit({"type": "steps", "steps": "4x+8=28\n4x=20\nx=5"})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    s.submit({"type": "final_answer", "final_answer_text": "宽5厘米，长9厘米", "verified": True})
    r = build_review(s)
    assert r["weak_points"] == ["解方程：移项要变号"]
    assert "还不能说明" in r["weak_points_note"]
    assert r["topic_family"] == "几何图形问题"


def test_clean_run_has_no_weak_points():
    q = BY_ID["Q01"]
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": q["variable_definition"], "equation": q["equation"]})
    r = build_review(s)
    assert r["weak_points"] == [] and r["weak_points_note"] is None


# ---------------------------------------------------------------- 练一道同类题

def test_bank_similar_prefers_same_family():
    assert bank_similar(BY_ID["Q01"], BANK)["question_id"] == "Q12"                  # 年龄
    assert bank_similar(BY_ID["Q04"], BANK)["question_id"] == "Q09"                  # 行程, same difficulty first
    assert bank_similar(BY_ID["Q04"], BANK, exclude=["Q09"])["question_id"] == "Q13"
    assert bank_similar(BY_ID["Q05"], BANK) is None                                  # the only 周长 item


VARIANT = "小明和小红从相距24千米的两地同时出发相向而行，小明每小时走5千米，小红每小时走3千米，几小时后相遇？"


def variant_raw():
    r = meet_raw()
    r.update(known_quantities=[{"name": "距离", "value": 24, "unit": "千米"}], equation="5*x+3*x=24",
             verification_conditions=[{"description": "路程和", "lhs": "5*x+3*x", "op": "==", "rhs": "24"}])
    return r


def test_generate_similar_is_verified():
    fake = FakeBackend(variant_text=VARIANT, variant_raw=variant_raw())
    q = dict(BY_ID["Q04"], topic="行程问题-相遇")
    ex, attempts = generate_similar(q, fake)
    assert ex is not None and ex.usable and ex.question["source"] == "generated"
    assert ex.question["answer"] == "3" and attempts[-1]["accepted"]


def test_generate_similar_rejects_unverified():
    bad = variant_raw()
    bad["equation"] = "5*x+3*x=32"                   # its own conditions / the independent solve disagree
    fake = FakeBackend(variant_text=VARIANT, variant_raw=bad)
    ex, attempts = generate_similar(dict(BY_ID["Q04"], topic="行程问题"), fake, max_tries=2)
    assert ex is None and len(attempts) == 2 and all("rejected" in a for a in attempts)


def test_generate_similar_rejects_other_type():
    other = variant_raw()
    other["topic"] = "工程问题"
    fake = FakeBackend(variant_text=VARIANT, variant_raw=other)
    ex, attempts = generate_similar(dict(BY_ID["Q04"], topic="行程问题"), fake, max_tries=1)
    assert ex is None and "different type" in attempts[0]["rejected"]


def test_similar_api_bank_then_generated(client, monkeypatch):
    sid = post(client, "/api/guided/start", question_id="Q01")["session_id"]
    b = post(client, "/api/guided/similar", session_id=sid, exclude=["Q01"])
    assert b["usable"] and b["source"] == "bank" and b["question_id"] == "Q12"

    sid = post(client, "/api/guided/start", question_id="Q05")["session_id"]
    b = post(client, "/api/guided/similar", session_id=sid)
    assert b["usable"] is False and "连接 AI" in b["message"]                        # no backend, no bank match

    fake = FakeBackend(variant_text=VARIANT, variant_raw=dict(variant_raw(), topic="几何图形问题-周长"))
    monkeypatch.setattr(guided_routes, "_backend", fake)
    b = post(client, "/api/guided/similar", session_id=sid)
    assert b["usable"] and b["source"] == "generated" and b["understanding"]["known_quantities"]
    s = post(client, "/api/guided/start", question_id=b["question_id"], understanding_confirmed=True)
    assert s["question"]["text"] == VARIANT
