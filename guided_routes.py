"""
guided_routes.py — Flask API for Guided Mode (S1 → S4), registered in app.py:

    from guided_routes import guided_bp
    app.register_blueprint(guided_bp)

Endpoints
    GET  /api/guided/questions          question-bank list for the picker
    POST /api/guided/match              {"text"} → question_id if the text is a bank question
    POST /api/guided/prepare            {"text"} → bank match, or structure extraction for any
                                        one-variable linear word problem (core/structure.py)
    POST /api/guided/start              {"question_id"} → new session + first tutor message
    POST /api/guided/submit             {"session_id", "input": {...}} → tutor messages
    GET  /api/guided/session/<id>       event log + summary (for the learning report / eval)

Input shapes (same as core.state_manager.TutorSession.submit):
    S1  {"type": "s1_choice", "chosen_id": "B"}                  (judged here with s1_options)
        {"type": "s1_text", "text": "..."}                       (judged by the LLM if available)
    S2  {"type": "modelling", "variable_definition": "...", "equation": "..."}
    S3  {"type": "steps", "steps": "one line per step"}          (string or list)
    S4  {"type": "final_answer", "final_answer_text": "...", "verified": bool, "active_verification": bool}
    reflection reply  {"type": "reflection", "text": "..."}

Scope: the 15 question-bank items, plus any problem whose extracted structure is
"consistent" (needs the LLM). Extracted records are cached in memory and saved to
data/extracted/<id>.json for review. Sessions are kept in memory (persistence is P2); each
session's event log is also written to logs/guided/<session_id>.jsonl.
Environment: GUIDED_USE_LLM=0 forces template-only wording and bank-only guidance;
WORDING_MODE = template | cached | live (default cached, see core/llm_client.py).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from collections import OrderedDict
from pathlib import Path

from flask import Blueprint, jsonify, request

from core.llm_client import TutorVoice, default_backend
from core.s1_options import build_s1_item, load_targets, to_submission
from core.state_manager import INPUT_FOR_STATE, TutorSession
from core.structure import OUT_OF_SCOPE, extract_structure, question_id_for

BASE_DIR = Path(__file__).resolve().parent
BANK = json.loads((BASE_DIR / "data" / "question_bank.json").read_text(encoding="utf-8"))
QUESTIONS = {q["question_id"]: q for q in BANK["questions"]}
S1_TARGETS = load_targets(BASE_DIR / "data" / "s1_targets.json")
LOG_DIR = BASE_DIR / "logs" / "guided"
EXTRACT_DIR = BASE_DIR / "data" / "extracted"
MAX_SESSIONS = 200
STATE_LABELS = {"S1": "理解题意", "S2": "设未知数、列方程", "S3": "解方程", "S4": "写答案并检验", "DONE": "完成"}

guided_bp = Blueprint("guided", __name__)

_backend = None if os.environ.get("GUIDED_USE_LLM", "1") == "0" else default_backend()
_sessions: "OrderedDict[str, dict]" = OrderedDict()
_extracted: dict[str, dict] = {}            # question_id → extracted record (usable ones only)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"[\s，,。．.、:：？?！!（）()]", "", text or "")


def _expected_input(session: TutorSession):
    if session.awaiting_reflection:
        return "reflection"
    return INPUT_FOR_STATE.get(session.state)


def _render(voice: TutorVoice, action) -> list[dict]:
    out = []
    while action is not None:
        m = voice.render(action)
        out.append({"role": "tutor", "text": m.text, "kind": action.type, "state": action.state,
                    "hint_level": m.hint_level, "category": m.category, "source": m.source})
        action = action.next_action
    return out


def _payload(sid: str, entry: dict, messages: list[dict]) -> dict:
    s: TutorSession = entry["session"]
    expected = _expected_input(s)
    body = {
        "success": True,
        "session_id": sid,
        "question_id": s.q["question_id"],
        "state": s.state,
        "state_label": STATE_LABELS.get(s.state, s.state),
        "expected_input": expected,
        "messages": messages,
        "done": s.state == "DONE" and not s.awaiting_reflection,
        "follow_ups_used": s.metacognitive_count,
        "follow_up_budget": s.budget,
    }
    if expected == "s1_choice":
        body["s1_item"] = {"prompt": entry["s1_item"]["prompt"],
                           "options": [{"id": o["id"], "text": o["text"]} for o in entry["s1_item"]["options"]]}
    if body["done"]:
        body["summary"] = s.summary()
    return body


def _save_log(sid: str, session: TutorSession):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / f"{sid}.jsonl").write_text(session.events_jsonl(), encoding="utf-8")
    except OSError:
        pass                                           # logging must never break tutoring


def _error(message: str, status: int = 400):
    return jsonify({"success": False, "message": message}), status


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@guided_bp.get("/api/guided/questions")
def list_questions():
    return jsonify({"success": True, "questions": [
        {"question_id": q["question_id"], "difficulty": q["difficulty"], "topic": q["topic"], "text": q["question"]}
        for q in BANK["questions"]]})


@guided_bp.post("/api/guided/match")
def match_question():
    return jsonify({"success": True, "question_id": _bank_match((request.get_json(silent=True) or {}).get("text", ""))})


def _bank_match(text: str):
    t = _clean(text)
    return next((q["question_id"] for q in BANK["questions"] if t and _clean(q["question"]) == t), None)


@guided_bp.post("/api/guided/prepare")
def prepare():
    text = ((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return _error("题目不能为空。")
    qid = _bank_match(text)
    if qid:
        return jsonify({"success": True, "usable": True, "source": "bank", "question_id": qid})

    qid = question_id_for(text)
    if qid in _extracted:
        return jsonify({"success": True, "usable": True, "source": "extracted", "question_id": qid})
    if _backend is None:
        return jsonify({"success": True, "usable": False, "source": "none",
                        "message": "当前没有连接 AI，引导学习只能使用题库中的 15 道题。"})

    ex = extract_structure(text, _backend)
    try:
        EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
        (EXTRACT_DIR / f"{qid}.json").write_text(json.dumps({
            "text": text, "scope": ex.scope, "scope_reason": ex.scope_reason, "consistency": ex.consistency,
            "checks": [c.__dict__ for c in ex.checks], "raw": ex.raw, "independent": ex.independent,
            "question": ex.question, "error": ex.error}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    if ex.usable:
        _extracted[qid] = ex.question
        return jsonify({"success": True, "usable": True, "source": "extracted", "question_id": qid})
    if ex.scope == OUT_OF_SCOPE:
        msg = f"这道题不是一元一次方程应用题（{ex.scope_reason}），引导学习暂时不支持，可以先用“快速解题”。"
    elif ex.scope != "in_scope":
        msg = f"这道题的题意我还不能确定（{ex.scope_reason or ex.error or '信息不完整'}），请检查题目文字后再试。"
    else:
        msg = "我分析这道题时自己核对没有通过，为了不误导你，这道题先用“快速解题”，或者从题库选一道。"
    return jsonify({"success": True, "usable": False, "source": "extracted", "scope": ex.scope,
                    "consistency": ex.consistency, "message": msg})


@guided_bp.post("/api/guided/start")
def start():
    data = request.get_json(silent=True) or {}
    qid = data.get("question_id")
    q = QUESTIONS.get(qid) or _extracted.get(qid)
    if q is None:
        return _error("找不到这道题，请重新输入题目或从题库中选择。")

    targets = S1_TARGETS if qid in QUESTIONS else {qid: q["s1"]}
    sid = uuid.uuid4().hex[:12]
    session = TutorSession(q, session_id=f"anon_{sid}")
    entry = {"session": session, "voice": TutorVoice(_backend, q), "s1_item": build_s1_item(q, targets)}
    _sessions[sid] = entry
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)

    messages = _render(entry["voice"], session.start())
    _save_log(sid, session)
    body = _payload(sid, entry, messages)
    body["question"] = {"question_id": q["question_id"], "text": q["question"], "difficulty": q.get("difficulty"),
                        "source": q.get("source", "bank")}
    body["llm"] = _backend.describe() if _backend else None
    body["wording_mode"] = entry["voice"].mode
    return jsonify(body)


@guided_bp.post("/api/guided/submit")
def submit():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    entry = _sessions.get(sid)
    if entry is None:
        return _error("会话不存在或已过期，请重新开始。", 404)
    session, voice = entry["session"], entry["voice"]
    raw = data.get("input") or {}
    kind = raw.get("type")

    # translate UI inputs into state-manager inputs
    if kind == "s1_choice":
        try:
            response = to_submission(entry["s1_item"], raw.get("chosen_id"))
        except ValueError as exc:
            return _error(str(exc))
    elif kind == "s1_text":
        target = S1_TARGETS[session.q["question_id"]]["target"]
        verdict = voice.classify_s1(session.q["question"], target, raw.get("text", ""))
        if verdict is None:
            return jsonify(_payload(sid, entry, [{
                "role": "tutor", "kind": "evidence_request", "state": session.state, "source": "template",
                "text": "我没能确定你的意思，请从下面的选项中选一个。", "hint_level": None, "category": None}]))
        response = {"type": "s1_choice", "correct": verdict, "chosen_text": raw.get("text", ""), "chosen_source": "free_text"}
    elif kind == "steps" and isinstance(raw.get("steps"), str):
        response = {"type": "steps", "steps": raw["steps"]}
    else:
        response = dict(raw)

    messages = [{"role": "learner", "input": raw}]
    messages += _render(voice, session.submit(response))
    _save_log(sid, session)
    return jsonify(_payload(sid, entry, messages))


@guided_bp.get("/api/guided/session/<sid>")
def session_log(sid):
    entry = _sessions.get(sid)
    if entry is None:
        return _error("会话不存在或已过期。", 404)
    s = entry["session"]
    return jsonify({"success": True, "summary": s.summary(), "events": s.events})