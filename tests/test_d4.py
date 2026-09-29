"""
D4 — end-to-end flows through the API, with a controllable fake LLM backend.

  D4-1  normal flow: read → confirm → guided (one modelling error) → solve → answer → verification
        reflection → review built from the real record → a verified similar problem
  D4-2  reading not verified: out of scope (said by the LLM, or a quadratic the LLM wrongly calls
        linear), incomplete problem (said by the LLM, or numbers the LLM invents) → never guided
  D4-3  the learner challenges the reading with a wrong claim → the text wins, nothing unverified
        gets in, the verified reading is kept, the normal flow continues
  D4-4  similar problem: verified → offered; unverified → refused and logged; service down →
        a message, no crash, the finished session untouched

The fake backend makes the LLM's mistakes and failures reproducible; the quality of the real
model's reading, judging and wording is checked separately with live runs.

Run from the project root:
    python -m pytest tests/test_d4.py -v
"""
import json
import os

os.environ["GUIDED_USE_LLM"] = "0"

import pytest
from flask import Flask

import guided_routes
from core.structure import EXTRACT_SYSTEM, JUDGE_SYSTEM, SOLVE_SYSTEM
from core.variants import VARIANT_SYSTEM


def raw(**kw):
    base = {"scope": "in_scope", "scope_reason": "", "alternatives": [], "e4_patterns": [],
            "unknown": {"meaning": "", "unit": ""}, "s1_intermediate": ""}
    base.update(kw)
    return base


NUM = "一个数的3倍比这个数大16，求这个数。"
NUM_RAW = raw(topic="数字问题-倍数关系", variable_definition="设这个数为x",
              known_quantities=[{"name": "倍数", "value": 3}, {"name": "相差", "value": 16}],
              relationship="这个数的3倍 - 这个数 = 16", equation="3*x-x=16",
              answer_parts=[{"label": "这个数", "expression": "x", "unit": ""}],
              verification_conditions=[{"description": "3倍比这个数大16", "lhs": "3*x-x", "op": "==", "rhs": "16"}],
              s1_target="这个数是多少", s1_intermediate="这个数的3倍")
NUM_VAR = "一个数的5倍比这个数大24，求这个数。"
NUM_VAR_RAW = dict(NUM_RAW, known_quantities=[{"name": "倍数", "value": 5}, {"name": "相差", "value": 24}],
                   relationship="这个数的5倍 - 这个数 = 24", equation="5*x-x=24",
                   verification_conditions=[{"description": "5倍比这个数大24", "lhs": "5*x-x", "op": "==", "rhs": "24"}])

SQUARE = "一个数的平方等于25，求这个数。"
VAGUE = "小明有一些钱，买东西后还剩一些钱，求小明原来有多少钱。"
RECT = "一个长方形的长比宽多3厘米，周长是26厘米，求长和宽。"


def rect_raw(diff=3):
    return raw(topic="几何图形问题-周长", variable_definition=f"设宽为x厘米，则长为(x+{diff})厘米",
               known_quantities=[{"name": "长比宽多", "value": diff, "unit": "厘米"},
                                 {"name": "周长", "value": 26, "unit": "厘米"}],
               relationship="2×(长+宽)=周长", equation=f"2*(x+x+{diff})=26",
               answer_parts=[{"label": "长", "expression": f"x+{diff}", "unit": "厘米"},
                             {"label": "宽", "expression": "x", "unit": "厘米"}],
               verification_conditions=[{"description": "周长26", "lhs": f"2*(x+x+{diff})", "op": "==", "rhs": "26"}],
               s1_target="长和宽")


class Fake:
    """Scripted LLM. `script` maps (system prompt kind, problem text) to a reply or an exception."""

    def __init__(self, extract=None, solve=None, judge=None, variant=None):
        self.extract, self.solve, self.judge, self.variant = extract or {}, solve or {}, judge, variant
        self.calls = []

    def describe(self):
        return {"backend": "fake"}

    def complete(self, system, user):
        if system == EXTRACT_SYSTEM:
            payload = json.loads(user)
            key = (payload["题目"], bool(payload.get("学生对题意的说明")))
            self.calls.append(("extract",) + key)
            out = self.extract.get(key, self.extract.get((payload["题目"], False)))
        elif system == SOLVE_SYSTEM:
            self.calls.append(("solve", user))
            out = self.solve.get(user)
        elif system == JUDGE_SYSTEM:
            self.calls.append(("judge",))
            out = self.judge
        elif system == VARIANT_SYSTEM:
            self.calls.append(("variant",))
            out = self.variant
        else:                                               # tutor wording: the service is down
            raise ConnectionResetError("tutor wording unavailable")
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(guided_routes, "LOG_DIR", tmp_path / "guided")
    monkeypatch.setattr(guided_routes, "EXTRACT_DIR", tmp_path / "extracted")
    monkeypatch.setattr(guided_routes, "_extracted", {})
    monkeypatch.setattr(guided_routes, "_corrections", {})
    app = Flask(__name__)
    app.register_blueprint(guided_routes.guided_bp)
    c = app.test_client()

    def post(url, **body):
        r = c.post(url, json=body)
        assert r.status_code == 200, (url, r.status_code, r.get_data(as_text=True)[:300])
        return r.get_json()

    post.client, post.tmp = c, tmp_path
    return post


def use(monkeypatch, backend):
    monkeypatch.setattr(guided_routes, "_backend", backend)
    return backend


def guided(api, qid):
    b = api("/api/guided/start", question_id=qid, understanding_confirmed=True, learner_id="L-d4")
    sid = b["session_id"]
    target = next(o["id"] for o in guided_routes._sessions[sid]["s1_item"]["options"] if o["source"] == "target")
    return sid, (lambda **i: api("/api/guided/submit", session_id=sid, input=i)), target


def tutor_texts(b):
    return [m["text"] for m in b["messages"] if m["role"] == "tutor"]


# ================================================================ D4-1

def test_d4_1_normal_flow(api, monkeypatch):
    fake = use(monkeypatch, Fake(extract={(NUM, False): NUM_RAW, (NUM_VAR, False): NUM_VAR_RAW},
                                 solve={NUM: {"parts": [{"label": "x", "value": "8"}]},
                                        NUM_VAR: {"parts": [{"label": "x", "value": "6"}]}},
                                 variant={"question": NUM_VAR, "topic": "数字问题"}))
    # read + verify before any guidance
    prep = api("/api/guided/prepare", text=NUM)
    assert prep["usable"] and prep["understanding"]["known_quantities"] == ["倍数：3", "相差：16"]
    assert ("solve", NUM) in fake.calls                                  # independent solve happened
    record = json.loads((api.tmp / "extracted" / f"{prep['question_id']}.json").read_text(encoding="utf-8"))
    assert record["consistency"] == "consistent"

    sid, send, target = guided(api, prep["question_id"])
    send(type="s1_choice", chosen_id=target)

    # one modelling error: located, not called a calculation error, nothing leaked
    b = send(type="modelling", variable_definition="设这个数为x", equation="3x + x = 16")
    hint = tutor_texts(b)[-1]
    assert b["state"] == "S2" and b["messages"][-1]["kind"] == "hint" and b["awaiting_explanation"]
    assert "左边" in hint and "3x + x" in hint
    assert "3x - x" not in hint and "3x-x" not in hint and "8" not in hint and "计算" not in hint

    b = send(type="modelling", variable_definition="设这个数为x", equation="3x - x = 16")
    assert b["state"] == "S3"
    send(type="reflection", text="比这个数大16是说它们的差是16")
    b = send(type="steps", steps="2x = 16\nx = 8")
    assert b["state"] == "S4"
    b = send(type="final_answer", final_answer_text="这个数是8", verified=False)   # no unit asked
    assert b["state"] == "DONE" and b["messages"][-1]["kind"] == "metacognitive_question"
    b = send(type="reflection", text="3×8=24，24-8=16")
    assert b["done"]
    assert any("3x-x = 16" in t and "✓" in t for t in tutor_texts(b))     # walkthrough with the real values

    # the review is built from what actually happened
    r = b["review"]
    s2 = next(j for j in r["journey"] if j["state"] == "S2")
    assert s2["status"] == "在提示下完成" and s2["errors"] == ["方程左边“3x + x”和题意对不上"]
    assert r["weak_points"] == ["找等量关系（数字与倍数问题）"]
    assert {p["label"]: p["text"] for p in r["solution_path"]}["列方程"] == "3x - x = 16"   # the learner's own
    assert any("出错后在提示下自己改正" in h for h in r["highlights"])

    # a similar problem: generated, verified, same type
    sim = api("/api/guided/similar", session_id=sid)
    assert sim["usable"] and sim["source"] == "generated" and sim["text"] == NUM_VAR
    assert sim["understanding"]["known_quantities"] == ["倍数：5", "相差：24"]
    assert ("solve", NUM_VAR) in fake.calls


# ================================================================ D4-2

def _refused(api, text):
    prep = api("/api/guided/prepare", text=text)
    assert prep["usable"] is False and "question_id" not in prep
    qid = guided_routes.question_id_for(text)
    r = api.client.post("/api/guided/start", json={"question_id": qid})
    assert r.status_code == 400                                          # cannot be started either
    log = json.loads((api.tmp / "extracted" / f"{qid}.json").read_text(encoding="utf-8"))
    return prep, log


def test_d4_2_out_of_scope_said_by_the_model(api, monkeypatch):
    use(monkeypatch, Fake(extract={(SQUARE, False): {"scope": "out_of_scope",
                                                      "scope_reason": "需要解二次方程，有两个解"}}))
    prep, log = _refused(api, SQUARE)
    assert "不是一元一次方程应用题" in prep["message"] and log["scope"] == "out_of_scope"
    assert log["scope_reason"] == "需要解二次方程，有两个解"


def test_d4_2_quadratic_wrongly_called_linear(api, monkeypatch):
    bad = raw(topic="数字问题", variable_definition="设这个数为x", known_quantities=[{"name": "平方", "value": 25}],
              relationship="x的平方=25", equation="x**2=25",
              answer_parts=[{"label": "", "expression": "x", "unit": ""}],
              verification_conditions=[{"description": "平方是25", "lhs": "x**2", "op": "==", "rhs": "25"}],
              s1_target="这个数")
    use(monkeypatch, Fake(extract={(SQUARE, False): bad}, solve={SQUARE: {"parts": [{"label": "x", "value": "5"}]}}))
    prep, log = _refused(api, SQUARE)
    assert log["consistency"] == "inconsistent"
    assert any(c["name"] in ("equation_readable", "equation_linear_unique") and not c["ok"] for c in log["checks"])


def test_d4_2_incomplete_problem_said_by_the_model(api, monkeypatch):
    use(monkeypatch, Fake(extract={(VAGUE, False): {"scope": "uncertain", "scope_reason": "没有给出具体金额"}}))
    prep, log = _refused(api, VAGUE)
    assert "还不能确定" in prep["message"] and "没有给出具体金额" in prep["message"]


def test_d4_2_invented_numbers_are_caught(api, monkeypatch):
    """The model invents 10 元 / 5 元 and 'verifies' them with a matching independent solve."""
    invented = raw(topic="购物与价格问题", variable_definition="设小明原来有x元",
                   known_quantities=[{"name": "花费", "value": 10, "unit": "元"},
                                     {"name": "剩下", "value": 5, "unit": "元"}],
                   relationship="原有-花费=剩下", equation="x-10=5",
                   answer_parts=[{"label": "", "expression": "x", "unit": "元"}],
                   verification_conditions=[{"description": "剩5元", "lhs": "x-10", "op": "==", "rhs": "5"}],
                   s1_target="原来有多少钱")
    use(monkeypatch, Fake(extract={(VAGUE, False): invented}, solve={VAGUE: {"parts": [{"label": "x", "value": "15"}]}}))
    prep, log = _refused(api, VAGUE)
    check = next(c for c in log["checks"] if c["name"] == "known_quantities_grounded")
    assert not check["ok"] and "花费=10" in check["detail"]


# ================================================================ D4-3

def test_d4_3_wrong_challenge_then_normal_flow(api, monkeypatch):
    fake = use(monkeypatch, Fake(
        extract={(RECT, False): rect_raw(3), (RECT, True): rect_raw(5)},          # a re-read would follow the note
        solve={RECT: {"parts": [{"label": "长", "value": "8"}, {"label": "宽", "value": "5"}]}},
        judge={"verdict": "learner_right", "quote": "长比宽多3厘米", "reply": "你说得对。"}))  # the judge errs too
    prep = api("/api/guided/prepare", text=RECT)
    qid, first = prep["question_id"], prep["understanding"]
    assert "长比宽多：3 厘米" in first["known_quantities"]

    b = api("/api/guided/prepare", text=RECT, correction="我觉得题目应该是长比宽多5厘米，而不是3厘米。")
    # even with a wrong judge verdict, the re-read (5 cm) fails against the independent solve of the TEXT
    assert ("extract", RECT, True) in fake.calls
    assert b["usable"] and b["correction_rejected"] and b["understanding"] == first
    kept = guided_routes._extracted[qid]["equation"].replace(" ", "")
    assert "x+3" in kept and "x+5" not in kept                              # the 5 cm claim never got in
    corr_log = (api.tmp / "extracted" / f"{qid}.corrections.jsonl").read_text(encoding="utf-8")
    assert "长比宽多5厘米" in corr_log
    reread = json.loads((api.tmp / "extracted" / f"{qid}.json").read_text(encoding="utf-8"))
    assert reread["learner_note"] and reread["consistency"] == "inconsistent"   # the re-read and its failure are logged

    # the normal flow on the original problem
    sid, send, target = guided(api, qid)
    send(type="s1_choice", chosen_id=target)
    assert send(type="modelling", variable_definition="设宽为x厘米，长为(x+3)厘米", equation="2(x+x+3)=26")["state"] == "S3"
    assert send(type="steps", steps="4x+6=26\n4x=20\nx=5")["state"] == "S4"
    b = send(type="final_answer", final_answer_text="宽5厘米，长8厘米", verified=True, active_verification=True)
    assert b["done"] and {p["label"]: p["text"] for p in b["review"]["solution_path"]}["解得"] == "x = 5"


def test_d4_3_wrong_challenge_judged_wrong(api, monkeypatch):
    fake = use(monkeypatch, Fake(
        extract={(RECT, False): rect_raw(3)},
        solve={RECT: {"parts": [{"label": "长", "value": "8"}, {"label": "宽", "value": "5"}]}},
        judge={"verdict": "learner_wrong", "quote": "长方形的长比宽多3厘米",
               "reply": "原题写的是“长比宽多3厘米”，不是5厘米，所以我没有改。"}))
    api("/api/guided/prepare", text=RECT)
    b = api("/api/guided/prepare", text=RECT, correction="应该是多5厘米")
    assert b["correction_rejected"] and "3厘米" in b["message"] and b["quote"] == "长方形的长比宽多3厘米"
    assert [c for c in fake.calls if c[0] == "extract"] == [("extract", RECT, False)]   # nothing re-read


# ================================================================ D4-4

def _finished_number_session(api):
    prep = api("/api/guided/prepare", text=NUM)
    sid, send, target = guided(api, prep["question_id"])
    send(type="s1_choice", chosen_id=target)
    send(type="modelling", variable_definition="设这个数为x", equation="3x-x=16")
    send(type="steps", steps="2x=16\nx=8")
    b = send(type="final_answer", final_answer_text="这个数是8", verified=True, active_verification=True)
    assert b["done"]
    return sid


BASE = dict(extract={(NUM, False): NUM_RAW}, solve={NUM: {"parts": [{"label": "x", "value": "8"}]}})


def test_d4_4_a_verified_generation_is_offered(api, monkeypatch):
    use(monkeypatch, Fake(extract={**BASE["extract"], (NUM_VAR, False): NUM_VAR_RAW},
                          solve={**BASE["solve"], NUM_VAR: {"parts": [{"label": "x", "value": "6"}]}},
                          variant={"question": NUM_VAR, "topic": "数字问题"}))
    sid = _finished_number_session(api)
    sim = api("/api/guided/similar", session_id=sid)
    assert sim["usable"] and sim["source"] == "generated"
    log = json.loads((api.tmp / "extracted" / f"{sim['question_id']}.json").read_text(encoding="utf-8"))
    assert log["consistency"] == "consistent" and log["generated_from"] == guided_routes.question_id_for(NUM)


def test_d4_4_b_an_unverified_generation_is_refused_and_logged(api, monkeypatch):
    broken = dict(NUM_VAR_RAW, equation="5*x-x=20")                    # does not match its own conditions
    use(monkeypatch, Fake(extract={**BASE["extract"], (NUM_VAR, False): broken},
                          solve={**BASE["solve"], NUM_VAR: {"parts": [{"label": "x", "value": "6"}]}},
                          variant={"question": NUM_VAR, "topic": "数字问题"}))
    sid = _finished_number_session(api)
    sim = api("/api/guided/similar", session_id=sid)
    assert sim["usable"] is False and "没能出一道经过核对的同类题" in sim["message"]
    assert guided_routes.question_id_for(NUM_VAR) not in guided_routes._extracted
    rejected = list((api.tmp / "extracted").glob("variants-rejected-*.json"))
    assert rejected and all("rejected" in a for a in json.loads(rejected[0].read_text(encoding="utf-8"))["attempts"])


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), ConnectionResetError("reset"), "not json at all"])
def test_d4_4_c_service_failure_degrades_safely(api, monkeypatch, failure):
    use(monkeypatch, Fake(extract=BASE["extract"], solve=BASE["solve"], variant=failure))
    sid = _finished_number_session(api)
    before = api.client.get(f"/api/guided/session/{sid}").get_json()["summary"]
    sim = api("/api/guided/similar", session_id=sid)
    assert sim["usable"] is False and sim["message"]
    after = api.client.get(f"/api/guided/session/{sid}").get_json()["summary"]
    assert before == after and after["completed"]                        # the finished session is untouched


def test_tutor_wording_failure_never_crashes(api, monkeypatch):
    """Every tutor-wording call of the fake raises: each turn still answers with a template."""
    use(monkeypatch, Fake(**BASE))
    prep = api("/api/guided/prepare", text=NUM)
    sid, send, target = guided(api, prep["question_id"])
    send(type="s1_choice", chosen_id="U")                                 # hint → LLM → exception → template
    b = send(type="s1_choice", chosen_id=target)
    b = send(type="modelling", variable_definition="设这个数为x", equation="3x + x = 16")
    assert b["messages"][-1]["source"] in ("template", "template_fallback")
    b = send(type="question", text="为什么不能用加法？")
    assert b["messages"][-1]["source"] in ("template", "template_fallback")
