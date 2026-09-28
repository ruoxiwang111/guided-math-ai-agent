"""
API tests for guided_routes.py (template-only wording, no network).

Run from the project root:
    python -m pytest tests/test_guided_routes.py -v
"""
import os

os.environ["GUIDED_USE_LLM"] = "0"          # must be set before guided_routes is imported

import pytest
from flask import Flask

import guided_routes
from guided_routes import QUESTIONS, guided_bp


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(guided_routes, "LOG_DIR", tmp_path / "logs")
    app = Flask(__name__)
    app.register_blueprint(guided_bp)
    return app.test_client()


def start(client, qid="Q01"):
    r = client.post("/api/guided/start", json={"question_id": qid})
    assert r.status_code == 200
    return r.get_json()


def send(client, sid, **inp):
    r = client.post("/api/guided/submit", json={"session_id": sid, "input": inp})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_question_list(client):
    qs = client.get("/api/guided/questions").get_json()["questions"]
    assert len(qs) == 15 and {"question_id", "text", "difficulty", "topic"} <= set(qs[0])


def test_match_bank_question(client):
    text = QUESTIONS["Q03"]["question"].replace("。", " 。 ")
    assert client.post("/api/guided/match", json={"text": text}).get_json()["question_id"] == "Q03"
    assert client.post("/api/guided/match", json={"text": "解方程 2x+5=15"}).get_json()["question_id"] is None


def test_start_rejects_non_bank_question(client):
    r = client.post("/api/guided/start", json={"question_id": "Q99"})
    assert r.status_code == 400 and not r.get_json()["success"]


def test_start_returns_s1_item_without_answer_key(client):
    b = start(client)
    assert b["state"] == "S1" and b["expected_input"] == "s1_choice"
    assert len(b["s1_item"]["options"]) == 4
    assert "correct_id" not in b["s1_item"] and all("source" not in o for o in b["s1_item"]["options"])
    assert b["messages"][0]["text"] == "这道题最后要求我们求什么？"


def correct_s1(client, sid):
    item = guided_routes._sessions[sid]["s1_item"]
    return send(client, sid, type="s1_choice", chosen_id=item["correct_id"])


def test_full_session_with_one_error(client, tmp_path):
    b = start(client)
    sid = b["session_id"]
    b = correct_s1(client, sid)
    assert b["state"] == "S2" and b["expected_input"] == "modelling"

    b = send(client, sid, type="modelling", variable_definition="设小华x岁，小明(x-5)岁", equation="x+(x-5)=25")
    hint = b["messages"][-1]
    assert hint["kind"] == "hint" and hint["category"] == "E4" and hint["hint_level"] == 1

    b = send(client, sid, type="modelling", variable_definition="设小华今年x岁，则小明今年(x+5)岁", equation="x+(x+5)=25")
    assert b["expected_input"] == "reflection" and b["messages"][-1]["kind"] == "metacognitive_question"

    b = send(client, sid, type="reflection", text="小明比小华大，所以加5")
    assert b["state"] == "S3" and b["expected_input"] == "steps"

    b = send(client, sid, type="steps", steps="2x+5=25\n2x=20\nx=10")
    assert b["state"] == "S4"

    b = send(client, sid, type="final_answer", final_answer_text="小华10岁，小明15岁",
             verified=True, active_verification=True)
    assert b["done"] and b["summary"]["completed"]
    assert b["summary"]["states"]["S2"]["errors"] == ["E4-01"]
    assert (tmp_path / "logs" / f"{sid}.jsonl").exists()


def test_wrong_s1_choice_gives_e1_hint(client):
    sid = start(client, "Q04")["session_id"]
    item = guided_routes._sessions[sid]["s1_item"]
    wrong = next(o["id"] for o in item["options"] if o["source"] != "target")
    b = send(client, sid, type="s1_choice", chosen_id=wrong)
    assert b["messages"][-1]["category"] == "E1" and b["state"] == "S1"


def test_s1_free_text_without_llm_falls_back_to_choice(client):
    sid = start(client)["session_id"]
    b = send(client, sid, type="s1_text", text="求两个人的年龄")
    assert b["expected_input"] == "s1_choice" and "选项" in b["messages"][-1]["text"]


def test_unknown_session(client):
    r = client.post("/api/guided/submit", json={"session_id": "nope", "input": {}})
    assert r.status_code == 404


def test_session_log_endpoint(client):
    sid = start(client)["session_id"]
    correct_s1(client, sid)
    body = client.get(f"/api/guided/session/{sid}").get_json()
    assert body["summary"]["states"]["S1"]["passed"]
    assert any(e["event"] == "state_transition" for e in body["events"])


def test_ask_teacher_keeps_step(client):
    sid = start(client)["session_id"]
    correct_s1(client, sid)
    b = send(client, sid, type="question", text="设哪个量为x比较好？")
    assert b["state"] == "S2" and b["expected_input"] == "modelling"
    assert b["messages"][-1]["kind"] == "answer_question"


# --- arbitrary questions (structure extraction with a fake LLM) --------------

from tests.test_structure import RAW, SOLVED, TEXT, Fake  # noqa: E402


def test_prepare_bank_question_needs_no_llm(client):
    b = client.post("/api/guided/prepare", json={"text": QUESTIONS["Q05"]["question"]}).get_json()
    assert b["usable"] and b["source"] == "bank" and b["question_id"] == "Q05"


def test_prepare_without_llm_explains_bank_only(client, monkeypatch):
    monkeypatch.setattr(guided_routes, "_backend", None)
    b = client.post("/api/guided/prepare", json={"text": TEXT}).get_json()
    assert not b["usable"] and "题库" in b["message"]


def test_prepare_and_start_extracted_question(client, monkeypatch, tmp_path):
    monkeypatch.setattr(guided_routes, "_backend", Fake(RAW, SOLVED))
    monkeypatch.setattr(guided_routes, "EXTRACT_DIR", tmp_path / "extracted")
    b = client.post("/api/guided/prepare", json={"text": TEXT}).get_json()
    assert b["usable"] and b["source"] == "extracted"
    assert (tmp_path / "extracted" / f"{b['question_id']}.json").exists()

    monkeypatch.setattr(guided_routes, "_backend", None)          # the rest runs on templates
    s = client.post("/api/guided/start", json={"question_id": b["question_id"]}).get_json()
    assert s["question"]["source"] == "extracted" and len(s["s1_item"]["options"]) >= 2
    sid = s["session_id"]
    item = guided_routes._sessions[sid]["s1_item"]
    send(client, sid, type="s1_choice", chosen_id=item["correct_id"])
    r = send(client, sid, type="modelling", variable_definition="设这本书一共有x页", equation="x/3+40+60=x")
    assert r["state"] == "S3"


def test_prepare_out_of_scope(client, monkeypatch, tmp_path):
    monkeypatch.setattr(guided_routes, "_backend", Fake({"scope": "out_of_scope", "scope_reason": "需要一元二次方程"}))
    monkeypatch.setattr(guided_routes, "EXTRACT_DIR", tmp_path)
    b = client.post("/api/guided/prepare", json={"text": "面积是60平方米的长方形，长比宽多4米……"}).get_json()
    assert not b["usable"] and "快速解题" in b["message"]


def test_prepare_inconsistent_extraction_is_refused(client, monkeypatch, tmp_path):
    monkeypatch.setattr(guided_routes, "_backend", Fake(RAW, '{"parts": [{"label": "a", "value": "999"}]}'))
    monkeypatch.setattr(guided_routes, "EXTRACT_DIR", tmp_path)
    b = client.post("/api/guided/prepare", json={"text": TEXT + "（另一版）"}).get_json()
    assert not b["usable"] and "核对没有通过" in b["message"]