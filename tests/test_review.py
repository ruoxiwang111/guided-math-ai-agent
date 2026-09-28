"""
End-of-problem review (core/review.py) and the optional self summary.

Run from the project root:
    python -m pytest tests/test_review.py -v
"""
import json
import os
from pathlib import Path

os.environ["GUIDED_USE_LLM"] = "0"

import pytest
from flask import Flask

import guided_routes
from core.llm_client import TutorVoice
from core.review import build_review
from core.state_manager import SELF_SUMMARY_ACK, UNEXPECTED_INPUT, TutorSession

ROOT = Path(__file__).resolve().parents[1]
BANK = {q["question_id"]: q for q in json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))["questions"]}
Q5 = BANK["Q05"]


def run(q, s2, s3, answer="宽5厘米，长9厘米", verified=False):
    """s2 / s3: lists of attempts; reflections are answered automatically."""
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})

    def reflect():
        if s.awaiting_reflection:
            s.submit({"type": "reflection", "text": "ok"})

    for vd, eq in s2:
        s.submit({"type": "modelling", "variable_definition": vd, "equation": eq})
    reflect()
    for steps in s3:
        s.submit({"type": "steps", "steps": steps})
    reflect()
    s.submit({"type": "final_answer", "final_answer_text": answer, "verified": verified,
              "active_verification": verified})
    reflect()
    return s


def test_clean_run_review():
    s = run(Q5, [("设宽为x厘米", "2(x+x+4)=28")], ["4x+8=28\n4x=20\nx=5"], verified=True)
    r = build_review(s, target="长和宽")
    labels = [p["label"] for p in r["solution_path"]]
    assert labels == ["题目要求", "设未知数", "等量关系", "列方程", "解得", "答"]
    assert r["solution_path"][1]["text"] == "设宽为x厘米"            # the learner's own definition
    assert r["solution_path"][3]["text"] == "2(x+x+4)=28"             # and own equation
    assert r["solution_path"][4]["text"] == "x = 5"
    assert "四个环节都独立完成了！" in r["highlights"]
    assert "没等提醒就主动检验了答案" in r["highlights"]
    assert all(j["status"] == "独立完成" and not j["errors"] for j in r["journey"])
    assert len(r["takeaways"]) == 1 and Q5["relationship"] in r["takeaways"][0]
    assert r["next_time"] == []


def test_errors_become_specific_takeaways():
    s = run(Q5, [("设宽为x厘米", "x+x+4=28"), ("设宽为x厘米", "2(x+x+4)=28")],
            ["4x+8=28\n4x=36\nx=9", "4x+8=28\n4x=20\nx=5"])
    r = build_review(s)
    journey = {j["state"]: j for j in r["journey"]}
    assert journey["S2"]["status"] == "在提示下改正" and "数量关系列错了" in journey["S2"]["errors"][0]
    assert journey["S3"]["errors"] == ["第2行方程变形出错"]
    assert any("移项要变号" in t for t in r["takeaways"])
    assert any("等量关系" in t for t in r["takeaways"])
    assert "写完答案先自己代回原题检查一遍，再提交。" in r["next_time"]
    # no contradiction: stages with errors are never listed as independent
    assert not any("四个环节都独立完成" in h for h in r["highlights"])
    indep = next((h for h in r["highlights"] if h.startswith("独立完成")), "")
    assert "解方程" not in indep and "设未知数" not in indep


def test_revealed_stage_suggests_redo():
    s = TutorSession(Q5)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    for eq in ("x+x+4=28", "x+4=28"):
        s.submit({"type": "modelling", "variable_definition": "设宽为x厘米", "equation": eq})
    s.submit({"type": "reveal_request"})
    s.submit({"type": "steps", "steps": "4x+8=28\n4x=20\nx=5"})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    s.submit({"type": "final_answer", "final_answer_text": "宽5厘米，长9厘米", "verified": True})
    r = build_review(s)
    assert next(j for j in r["journey"] if j["state"] == "S2")["status"] == "主动查看了参考"
    assert any("再独立做一遍" in t for t in r["next_time"])
    path = {p["label"]: p["text"] for p in r["solution_path"]}
    assert path["设未知数"] == Q5["variable_definition"]                  # reference model after reveal


def test_definition_only_is_not_a_modification():
    s = run(Q5, [("设宽为x厘米，长为x+4厘米", ""), ("设宽为x厘米，长为x+4厘米", "2(x+x+4)=28")],
            ["4x+8=28\n4x=20\nx=5"], verified=True)
    assert next(j for j in build_review(s)["journey"] if j["state"] == "S2")["status"] == "独立完成"


def test_self_summary_only_after_done():
    s = TutorSession(Q5)
    s.start()
    assert s.submit({"type": "self_summary", "text": "关键是等量关系"}).type == UNEXPECTED_INPUT
    s = run(Q5, [("设宽为x厘米", "2(x+x+4)=28")], ["4x+8=28\n4x=20\nx=5"], verified=True)
    assert s.submit({"type": "self_summary", "text": "   "}).type == UNEXPECTED_INPUT
    a = s.submit({"type": "self_summary", "text": "周长=(长+宽)×2"})
    assert a.type == SELF_SUMMARY_ACK
    assert TutorVoice(None, Q5, mode="template").render(a).text.startswith("记下了")
    assert s.summary()["self_summary"] == "周长=(长+宽)×2"
    assert build_review(s)["self_summary"] == "周长=(长+宽)×2"


# ---------------------------------------------------------------- API

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(guided_routes, "LOG_DIR", tmp_path / "logs")
    app = Flask(__name__)
    app.register_blueprint(guided_routes.guided_bp)
    return app.test_client()


def _send(client, sid, **inp):
    r = client.post("/api/guided/submit", json={"session_id": sid, "input": inp})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_api_review_and_self_summary(client):
    sid = client.post("/api/guided/start", json={"question_id": "Q05"}).get_json()["session_id"]
    target = next(o for o in guided_routes._sessions[sid]["s1_item"]["options"] if o["source"] == "target")
    b = _send(client, sid, type="s1_choice", chosen_id=target["id"])
    assert "review" not in b
    _send(client, sid, type="modelling", variable_definition="设宽为x厘米", equation="2(x+x+4)=28")
    _send(client, sid, type="steps", steps="4x+8=28\n4x=20\nx=5")
    b = _send(client, sid, type="final_answer", final_answer_text="宽5厘米，长9厘米", verified=True,
              active_verification=True)
    assert b["done"] and b["review"]["solution_path"][0] == {"label": "题目要求", "text": target["text"]}
    b = _send(client, sid, type="self_summary", text="周长=(长+宽)×2")
    assert b["done"] and b["review"]["self_summary"] == "周长=(长+宽)×2"
    assert b["messages"][-1]["kind"] == SELF_SUMMARY_ACK
