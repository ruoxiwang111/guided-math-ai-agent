"""
Regression tests from live testing (相遇 problem, 2026-09-28):

  * a vague but non-contradicting definition ("设x小时相遇", "设x表示相遇时间") must not
    block a learner whose equation is right
  * writing only "设……" first is a normal step: acknowledge it, ask for the equation
  * "5x-4x=36" is not an E4-01 sign flip (the template must only flip x ± constant)
  * "4小时后甲乙两人相遇" is 4 小时 — the unit is a closed list, not every trailing character
  * after 2 tries at a step the learner may choose to see that step (recorded as requested)

Run from the project root:
    python -m pytest tests/test_learner_flexibility.py -v
"""
import json
import os
from pathlib import Path

os.environ["GUIDED_USE_LLM"] = "0"

import pytest
from flask import Flask

import guided_routes
from core import diagnosis as dx
from core.llm_client import TutorVoice
from core.state_manager import REVEAL, TutorSession
from core.structure import validate_structure

ROOT = Path(__file__).resolve().parents[1]
BANK = {q["question_id"]: q for q in json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))["questions"]}

MEET_TEXT = "甲、乙两人从相距36千米的两地同时出发相向而行，甲每小时走5千米，乙每小时走4千米，几小时后两人相遇？"
MEET_RAW = {
    "scope": "in_scope",
    "unknown": {"symbol": "x", "meaning": "两人相遇所用的时间", "unit": "小时"},
    "variable_definition": "设经过x小时两人相遇",
    "known_quantities": [{"name": "两地距离", "value": "36", "unit": "千米"},
                         {"name": "甲的速度", "value": "5", "unit": "千米/小时"},
                         {"name": "乙的速度", "value": "4", "unit": "千米/小时"}],
    "relationship": "甲走的路程+乙走的路程=两地距离",
    "equation": "5x+4x=36",
    "answer_parts": [{"label": "", "expression": "x", "unit": "小时"}],
    "verification_conditions": [{"description": "两人路程和等于36千米", "lhs": "5*x+4*x", "op": "==", "rhs": "36"},
                                {"description": "时间为正", "lhs": "x", "op": ">", "rhs": "0"}],
    "alternatives": [], "e4_patterns": ["E4-01"],
    "s1_target": "相遇所用的时间", "s1_intermediate": "甲走的路程",
}


@pytest.fixture()
def meet():
    q, checks = validate_structure(MEET_RAW, MEET_TEXT)
    assert q is not None and all(c.ok for c in checks)
    q["question_id"] = "U-meet"
    return q


# ---------------------------------------------------------------- definitions

@pytest.mark.parametrize("vd", ["设x小时相遇", "设x小时候相遇", "设x表示相遇时间", "设x表示相遇小时",
                                "设两人x小时后相遇", "设相遇时间为x小时"])
def test_vague_but_compatible_definition_accepts_correct_equation(meet, vd):
    d = dx.diagnose_modelling(meet, "5x+4x=36", vd)
    assert d.status == dx.NO_ERROR
    assert d.details["ref"] == "standard"


def test_definition_with_a_different_unit_is_not_forced(meet):
    """'设甲走了x千米' is a distance: it must not be read as the time unknown."""
    ref, how = dx.resolve_definition("设甲走了x千米", dx._references(meet))
    assert ref is None and how is None
    d = dx.diagnose_modelling(meet, "5x+4x=36", "设甲走了x千米")
    assert d.status != dx.NO_ERROR


def test_ambiguous_bank_definition_still_asks(meet):
    """Two compatible readings (小华 / 小明, both 岁): no silent fallback."""
    ref, _ = dx.resolve_definition("设x岁", dx._references(BANK["Q01"]))
    assert ref is None


def test_clear_bank_alternative_still_matches():
    ref, how = dx.resolve_definition("设小明今年x岁", dx._references(BANK["Q01"]))
    assert ref["label"] != "standard" and how == "match"


def test_wrong_sign_between_x_terms_is_not_e4(meet):
    d = dx.diagnose_modelling(meet, "5x-4x=36", "设x小时相遇")
    assert d.primary_error is None and d.status == dx.UNCERTAIN
    assert d.rule == "unmatched_relationship"


def test_e4_flip_still_applies_to_constants():
    assert dx._flip_signs("x + 4 = 10") == ["x - 4 = 10"]
    assert dx._flip_signs("5*x + 4*x = 36") == []


def test_definition_only_is_acknowledged(meet):
    d = dx.diagnose_modelling(meet, "", "设x小时后两人相遇")
    assert d.status == dx.INSUFFICIENT and d.rule == "definition_only_ok" and d.follow_up == dx.ASK_EQUATION
    d = dx.diagnose_modelling(BANK["Q05"], "", "设宽为x厘米，长为x+4厘米")
    assert d.rule == "definition_only_ok" and d.details["defines_relation"] is True


def test_definition_only_unclear_and_nothing(meet):
    assert dx.diagnose_modelling(meet, "", "设甲走了x千米").rule == "definition_only_unclear"
    assert dx.diagnose_modelling(meet, "", "").rule == "nothing_written"


def test_definition_only_wording_quotes_learner(meet):
    s = TutorSession(BANK["Q05"])
    v = TutorVoice(None, BANK["Q05"], mode="template")
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    a = s.submit({"type": "modelling", "variable_definition": "设宽为x厘米，长为x+4厘米", "equation": ""})
    text = v.render(a).text
    assert "设宽为x厘米，长为x+4厘米" in text and "另一个量也已经用 x 表示" in text
    assert s.state == "S2" and s.records["S2"].failed_attempts == 0
    a = s.submit({"type": "modelling", "variable_definition": "设宽为x厘米，长为x+4厘米", "equation": "2(x+x+4)=28"})
    assert s.state == "S3"


# ---------------------------------------------------------------- final answer

@pytest.mark.parametrize("ans", ["4小时后甲乙两人相遇", "4小时甲乙两人相遇", "经过4小时两人相遇", "4个小时", "4小时"])
def test_answer_sentence_after_unit(meet, ans):
    assert dx.diagnose_final_answer(meet, ans).status == dx.NO_ERROR


def test_answer_parts_units_are_closed_list():
    assert dx._answer_parts("4小时后甲乙两人相遇") == [("", 4, "小时")]
    assert dx._answer_parts("甲班32台，乙班24台") == [("甲班", 32, "台"), ("乙班", 24, "台")]
    assert dx._answer_parts("每分钟250米") == [("", 250, "米/分钟")]
    assert dx._answer_parts("走了3公里") == [("走了", 3, "千米")]


def test_question_specific_unit_is_recognised():
    q = {"answer_parts": [{"unit": "株"}]}
    assert dx._answer_parts("种了12株树苗", dx._question_units(q)) == [("种了", 12, "株")]


def test_wrong_answer_still_wrong(meet):
    assert dx.diagnose_final_answer(meet, "5小时后两人相遇").status != dx.NO_ERROR


# ---------------------------------------------------------------- whole session

def test_screenshot_session_now_passes(meet):
    s = TutorSession(meet)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": "设x小时候相遇", "equation": "5x-4x=36"})
    s.submit({"type": "modelling", "variable_definition": "设x表示相遇时间", "equation": "5x+4x=36"})
    assert s.state == "S3"
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "两个人走的路程要加起来"})
    s.submit({"type": "steps", "steps": "9x=36\nx=4"})
    s.submit({"type": "final_answer", "final_answer_text": "4小时后甲乙两人相遇", "verified": True})
    assert s.state == "DONE"


# ---------------------------------------------------------------- learner-requested reveal

def test_reveal_only_after_two_attempts():
    s = TutorSession(BANK["Q05"])
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    assert not s.can_reveal()
    a = s.submit({"type": "reveal_request"})
    assert a.type != REVEAL and s.state == "S2"
    s.submit({"type": "modelling", "variable_definition": "设宽为x厘米", "equation": "x+x+4=28"})
    assert not s.can_reveal()
    s.submit({"type": "modelling", "variable_definition": "设宽为x厘米", "equation": "x+4=28"})
    assert s.can_reveal()


def test_reveal_request_shows_step_and_moves_on():
    q = BANK["Q05"]
    s = TutorSession(q)
    v = TutorVoice(None, q, mode="template")
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    for eq in ("x+x+4=28", "x+4=28"):
        s.submit({"type": "modelling", "variable_definition": "设宽为x厘米", "equation": eq})
    a = s.submit({"type": "reveal_request"})
    assert a.type == REVEAL and s.state == "S3"
    assert v.render(a).text.startswith("好的，这一步给你看参考。")
    summary = s.summary()["states"]["S2"]
    assert summary["revealed"] and summary["reveal_requested"]
    assert not s.records["S2"].independent
    assert any(e["event"] == "reveal_step" and e["requested_by_learner"] for e in s.events)


def test_reveal_in_s3_lets_s4_check_conditions():
    q = BANK["Q05"]
    s = TutorSession(q)
    s.start()
    s.submit({"type": "s1_choice", "correct": True})
    s.submit({"type": "modelling", "variable_definition": q["variable_definition"], "equation": q["equation"]})
    if s.awaiting_reflection:
        s.submit({"type": "reflection", "text": "ok"})
    for steps in ("4x+8=28\nx=6", "4x=20\nx=4"):
        s.submit({"type": "steps", "steps": steps})
    s.submit({"type": "reveal_request"})
    assert s.state == "S4" and s.final_x == q["answer"]


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


def test_api_can_reveal_and_reveal_request(client):
    body = client.post("/api/guided/start", json={"question_id": "Q05"}).get_json()
    sid = body["session_id"]
    assert body["can_reveal"] is False
    b = _send(client, sid, type="s1_choice", chosen_id=next(
        o["id"] for o in guided_routes._sessions[sid]["s1_item"]["options"] if o["source"] == "target"))
    assert b["state"] == "S2" and b["can_reveal"] is False
    _send(client, sid, type="modelling", variable_definition="设宽为x厘米", equation="x+x+4=28")
    b = _send(client, sid, type="modelling", variable_definition="设宽为x厘米", equation="x+4=28")
    assert b["can_reveal"] is True
    b = _send(client, sid, type="reveal_request")
    assert b["state"] == "S3" and any(m.get("kind") == "reveal_step" for m in b["messages"])


def test_api_definition_only(client):
    body = client.post("/api/guided/start", json={"question_id": "Q05"}).get_json()
    sid = body["session_id"]
    _send(client, sid, type="s1_choice", chosen_id=next(
        o["id"] for o in guided_routes._sessions[sid]["s1_item"]["options"] if o["source"] == "target"))
    b = _send(client, sid, type="modelling", variable_definition="设宽为x厘米，长为x+4厘米", equation="")
    assert b["state"] == "S2" and "设法可以" in b["messages"][-1]["text"]


# ---------------------------------------------------------------- command-line runner

def test_run_agent_demo_completes():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_agent.py"), "--demo", "--mode", "template"],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "✓ Session complete" in r.stdout
    assert "rule=definition_only_ok" in r.stdout and "S2 → S3" in r.stdout


def test_reveal_equation_is_written_form():
    from core.llm_client import _pretty
    assert _pretty("2*(x + (x + 4)) = 28") == "2(x + (x + 4)) = 28"
    assert _pretty("5*x + 4*x = 36") == "5x + 4x = 36"
