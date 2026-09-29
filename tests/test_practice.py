"""
D3 support: independent attempts without feedback, learner ids, and the D3 report.

Run from the project root:
    python -m pytest tests/test_practice.py -v
"""
import json
import os
import sys
from pathlib import Path

os.environ["GUIDED_USE_LLM"] = "0"

import pytest
from flask import Flask

import guided_routes
from core.practice import grade_attempt, learner_view
from core.structure import validate_structure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import d3_report  # noqa: E402


def build(text, qid, **kw):
    raw = {"scope": "in_scope", "alternatives": [], "e4_patterns": [], "s1_intermediate": "",
           "unknown": {"meaning": "", "unit": ""}}
    raw.update(kw)
    q, checks = validate_structure(raw, text)
    assert q is not None, [c for c in checks if not c.ok]
    q["question_id"] = qid
    return q


MONEY2 = build("小华有一些钱，买了一本15元的书后，还剩25元。问小华原来有多少钱？", "D3-1",
               topic="购物与价格问题", variable_definition="设小华原来有x元",
               known_quantities=[{"name": "书价", "value": 15, "unit": "元"}], relationship="原有 - 书价 = 剩下",
               equation="x-15=25", answer_parts=[{"label": "", "expression": "x", "unit": "元"}],
               verification_conditions=[{"description": "剩25元", "lhs": "x-15", "op": "==", "rhs": "25"}],
               s1_target="小华原来有多少钱")
AGE2 = build("小丽今年的年龄是小华的2倍。4年后，小丽的年龄比小华大8岁。问小丽和小华今年分别多少岁？", "D3-2",
             topic="年龄问题", variable_definition="设小华今年x岁，则小丽今年2x岁",
             known_quantities=[{"name": "倍数", "value": 2}, {"name": "年数", "value": 4, "unit": "年"},
                               {"name": "年龄差", "value": 8, "unit": "岁"}],
             relationship="4年后小丽的年龄 - 4年后小华的年龄 = 8", equation="(2*x+4)-(x+4)=8",
             answer_parts=[{"label": "小丽", "expression": "2*x", "unit": "岁"},
                           {"label": "小华", "expression": "x", "unit": "岁"}],
             verification_conditions=[{"description": "4年后相差8岁", "lhs": "(2*x+4)-(x+4)", "op": "==", "rhs": "8"}],
             s1_target="小丽和小华今年的年龄")


# ---------------------------------------------------------------- grading

def test_correct_attempt():
    r = grade_attempt(MONEY2, "设小华原来有x元", "x-15=25", "x=25+15\nx=40", "40元")
    assert r["fully_correct"] and r["errors"] == []


def test_same_error_as_before_is_found():
    r = grade_attempt(MONEY2, "设小华原来有x元", "x-15=25", "x=25-15\nx=10", "10元")
    assert r["model_correct"] and r["execution_correct"] is False and not r["answer_correct"]
    e = next(e for e in r["errors"] if e["layer"] == "execution")
    assert (e["category"], e["rule"], e["line"]) == ("E7", "transposition_sign", 1)
    assert "移项没有变号" in "".join(learner_view(r))


def test_execution_is_judged_on_the_learners_own_equation():
    """A wrong equation solved correctly is a modelling error only."""
    r = grade_attempt(MONEY2, "设x元", "x+15=25", "x=25-15\nx=10", "10元")
    assert r["model_correct"] is False and r["execution_correct"] is True


@pytest.mark.parametrize("eq,steps", [("(2x+4)-(x+4)=8", "2x+4-x-4=8\nx=8"),
                                      ("2x-x=8", "x=8"),                  # sees the difference never changes
                                      ("2x+4=x+4+8", "x=8")])
def test_transfer_problem_accepts_any_equivalent_model(eq, steps):
    r = grade_attempt(AGE2, "设小华今年x岁，小丽2x岁", eq, steps, "小丽16岁，小华8岁")
    assert r["fully_correct"]


def test_transfer_problem_wrong_model():
    r = grade_attempt(AGE2, "设小华今年x岁，小丽2x岁", "2x+4=2(x+4)", "2x+4=2x+8\n4=8", "无解")
    assert not r["model_correct"] and not r["answer_correct"]
    assert any(e["layer"] == "modelling" for e in r["errors"])


def test_empty_fields_are_named():
    r = grade_attempt(MONEY2, "", "", "", "40元")
    assert {"no_equation", "no_steps"} <= set(r["error_rules"]) and r["answer_correct"]


# ---------------------------------------------------------------- API + report

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(guided_routes, "LOG_DIR", tmp_path / "guided")
    monkeypatch.setattr(guided_routes, "PRACTICE_DIR", tmp_path / "practice")
    monkeypatch.setattr(guided_routes, "_extracted", {"D3-1": MONEY2, "D3-2": AGE2})
    app = Flask(__name__)
    app.register_blueprint(guided_routes.guided_bp)
    c = app.test_client()
    c.tmp = tmp_path
    return c


def post(c, url, **body):
    r = c.post(url, json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_practice_flow_is_logged(client):
    pid = post(client, "/api/practice/start", question_id="D3-1", learner_id="L-abc123")["practice_id"]
    b = post(client, "/api/practice/submit", practice_id=pid, variable_definition="设x元", equation="x-15=25",
             steps="x=40", final_answer_text="40元", verified=True)
    assert b["result"]["fully_correct"] and b["duration_seconds"] >= 0 and not b["help_requested"]
    rec = json.loads((client.tmp / "practice" / f"{pid}.json").read_text(encoding="utf-8"))
    assert rec["learner_id"] == "L-abc123" and rec["answer"]["equation"] == "x-15=25" and rec["result"]["fully_correct"]
    assert client.post("/api/practice/submit", json={"practice_id": pid}).status_code == 400   # only once


def test_help_is_recorded(client):
    pid = post(client, "/api/practice/start", question_id="D3-1", learner_id="L-abc123")["practice_id"]
    assert post(client, "/api/practice/help", practice_id=pid)["question_id"] == "D3-1"
    rec = json.loads((client.tmp / "practice" / f"{pid}.json").read_text(encoding="utf-8"))
    assert rec["help_requested"] and rec["help_requested_at"]


def test_bad_learner_id_is_dropped(client):
    pid = post(client, "/api/practice/start", question_id="D3-1", learner_id="<script>")["practice_id"]
    rec = json.loads((client.tmp / "practice" / f"{pid}.json").read_text(encoding="utf-8"))
    assert rec["learner_id"] is None


def test_report_finds_a_repeated_error(client):
    """Guided session with a sign error, then an independent attempt with the same error."""
    b = post(client, "/api/guided/start", question_id="Q04", learner_id="L-aaa111")
    sid = b["session_id"]
    send = lambda **i: post(client, "/api/guided/submit", session_id=sid, input=i)  # noqa: E731
    q4 = guided_routes.QUESTIONS["Q04"]
    target = next(o["id"] for o in guided_routes._sessions[sid]["s1_item"]["options"] if o["source"] == "target")
    send(type="s1_choice", chosen_id=target)
    send(type="modelling", variable_definition=q4["variable_definition"], equation=q4["equation"])
    if guided_routes._sessions[sid]["session"].awaiting_reflection:
        send(type="reflection", text="ok")
    send(type="steps", steps="3000+10x=5500\n10x=5500+3000")             # transposition sign

    pid = post(client, "/api/practice/start", question_id="D3-1", learner_id="L-aaa111")["practice_id"]
    post(client, "/api/practice/submit", practice_id=pid, variable_definition="设x元", equation="x-15=25",
         steps="x=25-15\nx=10", final_answer_text="10元")
    pid2 = post(client, "/api/practice/start", question_id="D3-1", learner_id="L-bbb222")["practice_id"]
    post(client, "/api/practice/submit", practice_id=pid2, variable_definition="设x元", equation="x-15=25",
         steps="x=40", final_answer_text="40元")

    table = d3_report.rows(d3_report.load_guided(client.tmp / "guided"),
                           d3_report.load_practice(client.tmp / "practice"))
    a = next(r for r in table if r["learner_id"] == "L-aaa111")
    assert a["earlier_guided_sessions"] == 1 and "E7:transposition_sign" in a["earlier_errors"]
    assert a["repeated_errors"] == "E7:transposition_sign" and a["transfer"] == "repeated earlier error"
    assert a["independent"] is False and a["help_requested"] is False
    b = next(r for r in table if r["learner_id"] == "L-bbb222")
    assert b["independent"] and b["transfer"] == "—"                       # no earlier session to compare


def test_report_script_runs(tmp_path):
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "d3_report.py"),
                        "--guided-dir", str(tmp_path), "--practice-dir", str(tmp_path), "--out-dir", str(tmp_path / "out")],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "D3 attempts: 0" in r.stdout
