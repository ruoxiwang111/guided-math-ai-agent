"""
Learner corrections of "我读到的已知条件" (live test 2026-09-28, age problem):

  the learner deliberately claimed "5年后小明的年龄是小红的3倍" (the text says 2倍).
  Before: the system silently re-read the problem, showed "小明今年的年龄：3*x 岁" as a known
  condition, and offered no way on after two corrections.
  Now:  1. the claim is judged against the problem text, with a VERBATIM quote as evidence;
           wrong → said so, quoting the text, nothing re-read;
        2. known quantities must be numbers (no expressions in x);
        3. "the text itself is wrong" is handled by editing the problem text (a new problem).

Run from the project root:
    python -m pytest tests/test_correction_judge.py -v
"""
import json
import os

os.environ["GUIDED_USE_LLM"] = "0"

import pytest
from flask import Flask

import guided_routes
from core.structure import (
    EXTRACT_SYSTEM, JUDGE_SYSTEM, JUDGE_UNCLEAR, LEARNER_RIGHT, LEARNER_WRONG, SOLVE_SYSTEM, judge_correction,
    validate_structure,
)

TEXT = "小明今年的年龄是小红的3倍，5年后小明的年龄是小红的2倍。问小明和小红今年分别多少岁？"


def raw(known=None):
    return {
        "scope": "in_scope", "topic": "年龄问题", "unknown": {"meaning": "小红今年的年龄", "unit": "岁"},
        "variable_definition": "设小红今年x岁，则小明今年3x岁",
        "known_quantities": known or [{"name": "今年的倍数", "value": 3, "unit": "倍"},
                                      {"name": "5年后的倍数", "value": 2, "unit": "倍"},
                                      {"name": "时间间隔", "value": 5, "unit": "年"}],
        "relationship": "5年后小明的年龄 = 2 × 5年后小红的年龄", "equation": "3*x+5=2*(x+5)",
        "answer_parts": [{"label": "小明今年的年龄", "expression": "3*x", "unit": "岁"},
                         {"label": "小红今年的年龄", "expression": "x", "unit": "岁"}],
        "verification_conditions": [{"description": "5年后2倍", "lhs": "3*x+5", "op": "==", "rhs": "2*(x+5)"}],
        "alternatives": [], "e4_patterns": [], "s1_target": "小明和小红今年的年龄", "s1_intermediate": "",
    }


class Judge:
    """Fake LLM: the judge answer is configurable; extraction and solving are correct."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.extractions = 0

    def describe(self):
        return {}

    def complete(self, system, user):
        if system == JUDGE_SYSTEM:
            return json.dumps(self.verdict, ensure_ascii=False)
        if system == SOLVE_SYSTEM:
            return json.dumps({"parts": [{"label": "小明", "value": "15"}, {"label": "小红", "value": "5"}]})
        assert system == EXTRACT_SYSTEM
        self.extractions += 1
        return json.dumps(raw(), ensure_ascii=False)


WRONG = {"verdict": LEARNER_WRONG, "quote": "5年后小明的年龄是小红的2倍",
         "reply": "原题写的是“5年后小明的年龄是小红的2倍”，不是3倍，所以我没有改。"}


# ---------------------------------------------------------------- known quantities are numbers

def test_expressions_are_not_known_quantities():
    rec, checks = validate_structure(raw([{"name": "小明今年的年龄", "value": "3*x", "unit": "岁"},
                                          {"name": "5年后的时间", "value": 5, "unit": "年"},
                                          {"name": "倍数", "value": 2}]), TEXT)
    assert [k["name"] for k in rec["known_quantities"]] == ["5年后的时间", "倍数"]
    c = next(c for c in checks if c.name == "known_quantities_numeric")
    assert "小明今年的年龄=3*x" in c.detail


# ---------------------------------------------------------------- the judge

def test_wrong_claim_with_verbatim_quote():
    v = judge_correction(TEXT, ["5年后的倍数：2 倍"], "应该是5年后3倍", Judge(WRONG))
    assert v["verdict"] == LEARNER_WRONG and v["quote"] == WRONG["quote"]


def test_wrong_claim_without_real_quote_is_not_asserted():
    fake = dict(WRONG, quote="5年后小明的年龄是小红的4倍")         # not in the problem text
    v = judge_correction(TEXT, [], "应该是3倍", Judge(fake))
    assert v["verdict"] == JUDGE_UNCLEAR and v["quote"] == ""


def test_quote_matching_ignores_punctuation_and_spaces():
    fake = dict(WRONG, quote="5年后 小明的年龄是小红的2倍。")
    assert judge_correction(TEXT, [], "3倍", Judge(fake))["verdict"] == LEARNER_WRONG


def test_garbage_or_no_backend_is_unclear():
    assert judge_correction(TEXT, [], "x", None)["verdict"] == JUDGE_UNCLEAR

    class Bad:
        def complete(self, s, u):
            return "not json"
    assert judge_correction(TEXT, [], "x", Bad())["verdict"] == JUDGE_UNCLEAR


# ---------------------------------------------------------------- API

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(guided_routes, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(guided_routes, "EXTRACT_DIR", tmp_path / "extracted")
    monkeypatch.setattr(guided_routes, "_extracted", {})
    monkeypatch.setattr(guided_routes, "_corrections", {})
    app = Flask(__name__)
    app.register_blueprint(guided_routes.guided_bp)
    return app.test_client()


def post(client, **body):
    r = client.post("/api/guided/prepare", json=body)
    assert r.status_code == 200
    return r.get_json()


def test_wrong_correction_is_explained_not_applied(client, monkeypatch, tmp_path):
    fake = Judge(WRONG)
    monkeypatch.setattr(guided_routes, "_backend", fake)
    first = post(client, text=TEXT)
    assert fake.extractions == 1
    b = post(client, text=TEXT, correction="我觉得题目应该是5年后小明的年龄是小红的3倍")
    assert b["usable"] and b["correction_rejected"] and "2倍" in b["message"] and b["quote"] == WRONG["quote"]
    assert fake.extractions == 1                                    # nothing re-read
    assert b["understanding"] == first["understanding"]             # the reading is unchanged
    assert b["corrections"] == 1 and b["can_correct"] is True
    log = (tmp_path / "extracted" / f"{b['question_id']}.corrections.jsonl").read_text(encoding="utf-8")
    assert LEARNER_WRONG in log


def test_right_correction_rereads(client, monkeypatch):
    fake = Judge({"verdict": LEARNER_RIGHT, "quote": "小明今年的年龄是小红的3倍", "reply": "你说得对。"})
    monkeypatch.setattr(guided_routes, "_backend", fake)
    post(client, text=TEXT)
    b = post(client, text=TEXT, correction="今年是3倍，你漏了")
    assert b["usable"] and not b.get("correction_rejected") and fake.extractions == 2


def test_edited_text_is_a_new_problem(client, monkeypatch):
    monkeypatch.setattr(guided_routes, "_backend", Judge(WRONG))
    a = post(client, text=TEXT)
    b = post(client, text=TEXT.replace("2倍", "2倍。"))                # any edit → a new question id
    assert a["question_id"] != b["question_id"] and b["corrections"] == 0
