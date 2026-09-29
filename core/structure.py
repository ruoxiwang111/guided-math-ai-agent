"""
core/structure.py — turn ANY one-variable linear word problem into a question-bank record,
so the whole guided pipeline (S1–S4, diagnosis, hints) runs on it unchanged.

V1_design §6–9 (scope detection, structured representation, consistency checking):

    problem text
      │ ① LLM: scope + structure (JSON)            – language understanding only
      │ ② code: normalise, solve with SymPy         – the equation must be linear with one solution
      │ ③ code: answer parts computed from x         – the final answer is never LLM arithmetic
      │ ④ code: verification conditions at x         – every stated condition must hold
      │ ⑤ code: alternative definitions checked      – each alternative solves to its own x value
      │ ⑥ LLM: independent solution (no structure)   – must give the same numbers
      ▼
    consistency = consistent | uncertain | inconsistent
    Guided Mode is offered only for "consistent" records. "consistent" still does not
    guarantee the problem was understood correctly (V1_design §10) – that is what the
    consistent-but-wrong rate on D1 measures.

Public API
    extract_structure(text, backend) -> Extraction
    validate_structure(raw)          -> (question_record | None, checks)
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from sympy import S, nsimplify

from core import math_checker as mc
from core.diagnosis import E4_TEMPLATES, e4_variants
from core.normalizer import normalize_line

PROMPT_VERSION = "structure-v1"
CLOSED_E4 = {
    "E4-01": "甲比乙多……", "E4-02": "甲比乙少……", "E4-03": "比原来增加了……%", "E4-04": "增加到原来的……%",
    "E4-05": "增加到……", "E4-06": "打……折", "E4-07": "甲是乙的……倍", "E4-08": "比原来少了几分之几",
}

CONSISTENT, UNCERTAIN, INCONSISTENT = "consistent", "uncertain", "inconsistent"
IN_SCOPE, OUT_OF_SCOPE = "in_scope", "out_of_scope"

EXTRACT_SYSTEM = """你是初中数学教研员。把一道应用题整理成结构化数据，供程序检查学生的解题过程。
只处理“用一个未知数、列一元一次方程就能解”的应用题；否则 scope 填 out_of_scope（需要二次方程、不等式、
方程组才能解、函数、几何证明等）或 uncertain（题意不完整、有歧义、一次给了多道题）。
规则：
- 所有式子用 SymPy 写法：乘号写 *，分数写 a/b，百分数写成小数或分数，未知数统一为 x。
- equation 必须只含 x、是一次方程，且与 variable_definition 一致。
- answer_parts：题目要求写出的每个量，用关于 x 的表达式表示（例如 x、56 - x、x/4），带标签和单位。
  不要自己算数值，程序会代入计算。
- verification_conditions：把答案代回题目要成立的条件，用关于 x 的式子写，op 取 ==、>、<、>=、<=、integer。
- alternatives：学生可能选择的另一种设法（设另一个量为 x），给出它的 variable_definition、equation，
  以及“这个新 x 等于原来哪个量”的表达式 x_expression（用原来的 x 表示）。没有就给空列表。
- e4_patterns：题目中出现的下列固定表述编号（没有就给空列表）：""" + \
    "；".join(f"{k} {v}" for k, v in CLOSED_E4.items()) + """。
- s1_target：题目最后要求的是什么（名词短语）；s1_intermediate：解题中容易被误当成答案的一个中间量。
只输出 JSON：
{"scope": "in_scope|out_of_scope|uncertain", "scope_reason": "...", "topic": "...",
 "unknown": {"meaning": "...", "unit": "..."}, "variable_definition": "设……为x……，则……",
 "known_quantities": [{"name": "...", "value": 数或"分数字符串", "unit": "..."}],
 "relationship": "用文字写数量关系", "equation": "...",
 "answer_parts": [{"label": "...", "expression": "...", "unit": "..."}],
 "verification_conditions": [{"description": "...", "lhs": "...", "op": "==", "rhs": "..."}],
 "alternatives": [{"variable_definition": "...", "equation": "...", "x_expression": "..."}],
 "e4_patterns": [], "s1_target": "...", "s1_intermediate": "..."}"""

SOLVE_SYSTEM = """独立解下面这道数学应用题。只给出题目要求的每个量的最终数值（分数写成 a/b），不要解释。
只输出 JSON：{"parts": [{"label": "...", "value": "..."}]}"""


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Extraction:
    text: str
    scope: str
    scope_reason: str = ""
    consistency: str | None = None
    question: dict | None = None
    checks: list = field(default_factory=list)
    raw: dict | None = None
    independent: dict | None = None
    error: str | None = None

    @property
    def usable(self) -> bool:
        return self.scope == IN_SCOPE and self.consistency == CONSISTENT and self.question is not None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def question_id_for(text: str) -> str:
    clean = re.sub(r"\s+", "", text or "")
    return "U-" + hashlib.sha1(clean.encode("utf-8")).hexdigest()[:8]


def _num(v):
    return nsimplify(S(str(v)), rational=True)


def _fmt(v) -> str:
    v = nsimplify(v, rational=True)
    return str(v) if v.q == 1 else f"{v.p}/{v.q}"


def _eval_at(expr_text: str, xv):
    nl = normalize_line(expr_text)
    if not nl.ok or nl.kind != "expression":
        raise ValueError(f"cannot read expression {expr_text!r}")
    return nsimplify(mc._expr(nl.normalized).subs(mc.X, xv), rational=True)


CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_int(t: str):
    """'十二' → 12, '三十五' → 35, '一百二十' → 120, '八' → 8 (simple forms up to 999)."""
    if not t or any(ch not in CN_DIGITS and ch not in "十百" for ch in t):
        return None
    total, cur = 0, 0
    for ch in t:
        if ch in CN_DIGITS:
            cur = CN_DIGITS[ch]
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
    return total + cur


def numbers_in_text(text: str) -> set:
    """Numbers a problem states, in any usual form: 36, 1.5, 3/4, 20%, 八折, 百分之二十, 三分之一, 一半, 十二."""
    out = set()
    t = text or ""
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*/\s*(\d+)", t):
        out.add(nsimplify(S(m.group(1)) / S(m.group(2)), rational=True))
    for m in re.finditer(r"\d+(?:\.\d+)?", t):
        out.add(nsimplify(S(m.group()), rational=True))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*[%％]", t):
        out.add(nsimplify(S(m.group(1)) / 100, rational=True))
    for m in re.finditer(r"([一二两三四五六七八九十百]+)分之([一二两三四五六七八九十百]+)", t):
        a, b = _cn_int(m.group(1)), _cn_int(m.group(2))
        if a and b is not None:
            out.add(nsimplify(S(b) / S(a), rational=True))
    for m in re.finditer(r"百分之([一二两三四五六七八九十百]+)", t):
        v = _cn_int(m.group(1))
        if v is not None:
            out |= {S(v), nsimplify(S(v) / 100, rational=True)}
    for m in re.finditer(r"([一二三四五六七八九])([一二三四五六七八九])?折", t):
        first, second = CN_DIGITS[m.group(1)], CN_DIGITS.get(m.group(2) or "")
        out.add(nsimplify(S(first * 10 + second) / 100 if second is not None else S(first) / 10, rational=True))
    for m in re.finditer(r"(\d)(\d)?\s*折", t):
        out.add(nsimplify(S(m.group(1) + (m.group(2) or "")) / (100 if m.group(2) else 10), rational=True))
    for m in re.finditer(r"[零〇一二两三四五六七八九十百]+", t):
        v = _cn_int(m.group())
        if v is not None:
            out.add(S(v))
    if "半" in t:
        out.add(S(1) / 2)
    return out


def _grounded(value, in_text: set) -> bool:
    try:
        v = _num(value)
    except Exception:  # noqa: BLE001
        return False
    return v in in_text or v * 100 in in_text or v / 100 in in_text


def _is_number(v) -> bool:
    try:
        n = nsimplify(S(str(v).replace("％", "%").rstrip("%")), rational=True)
    except Exception:  # noqa: BLE001
        return False
    return not n.free_symbols and n.is_number


def _sympy_eq(text: str) -> str | None:
    nl = normalize_line(text)
    return nl.normalized if nl.ok and nl.kind == "equation" else None


# ---------------------------------------------------------------------------
# validation (pure code, no LLM)
# ---------------------------------------------------------------------------

def validate_structure(raw: dict, text: str = "") -> tuple[dict | None, list[Check]]:
    checks: list[Check] = []

    def add(name, ok, detail=""):
        checks.append(Check(name, bool(ok), detail))
        return ok

    eq = _sympy_eq(raw.get("equation", ""))
    if not add("equation_readable", eq, raw.get("equation", "")):
        return None, checks
    sol = mc.solution_set(eq)
    if not add("equation_linear_unique", sol and sol.linear and sol.kind == mc.UNIQUE, str(sol)):
        return None, checks
    x_val = next(iter(sol.values))

    # answer parts computed from x (never LLM arithmetic)
    parts = []
    try:
        for p in raw.get("answer_parts") or []:
            parts.append({"label": p.get("label", ""), "value": _eval_at(p["expression"], x_val),
                          "unit": p.get("unit", "")})
    except (ValueError, KeyError, TypeError) as exc:
        add("answer_parts_computable", False, str(exc))
        return None, checks
    add("answer_parts_computable", parts, f"{len(parts)} part(s)")
    if not parts:
        return None, checks
    final_answer_text = "，".join(f"{p['label']}{_fmt(p['value'])}{p['unit']}" for p in parts)

    # verification conditions must hold at the solution
    conds = []
    for c in raw.get("verification_conditions") or []:
        if not isinstance(c, dict):
            continue
        if {"description", "lhs", "op"} <= set(c) and c["op"] in ("==", ">", "<", ">=", "<=", "integer"):
            conds.append({k: c[k] for k in ("description", "lhs", "op", "rhs") if k in c})
    results = mc.check_conditions(conds, x_val) if conds else []
    failed = [r.description for r in results if r.holds is not True]
    add("conditions_hold", conds and not failed, "；".join(failed) or f"{len(conds)} condition(s)")
    if failed or not conds:
        return None, checks

    # alternative definitions: keep only those that are mathematically consistent
    alts = []
    for a in raw.get("alternatives") or []:
        aeq = _sympy_eq(a.get("equation", ""))
        try:
            target = _eval_at(a.get("x_expression", ""), x_val)
        except ValueError:
            continue
        asol = mc.solution_set(aeq) if aeq else None
        if asol and asol.kind == mc.UNIQUE and target in asol.values and a.get("variable_definition"):
            alts.append({"variable_definition": a["variable_definition"], "equation": aeq, "x_value": _fmt(target)})
    add("alternatives_checked", True, f"{len(alts)} kept of {len(raw.get('alternatives') or [])}")

    # closed-list E4 patterns: keep only those whose template actually applies
    record_stub = {"equation": eq, "e4_patterns": [p for p in raw.get("e4_patterns") or [] if p in E4_TEMPLATES]}
    e4 = sorted({pid for pid, _ in e4_variants(record_stub)})

    # a known quantity is a NUMBER given in the problem; "小明今年的年龄：3*x" is not one
    known, dropped = [], []
    for k in raw.get("known_quantities") or []:
        if not (isinstance(k, dict) and "name" in k and "value" in k):
            continue
        if _is_number(k["value"]):
            known.append({"name": k["name"], "value": k["value"], **({"unit": k["unit"]} if k.get("unit") else {})})
        else:
            dropped.append(f"{k['name']}={k['value']}")
    add("known_quantities_numeric", True, f"dropped {dropped}" if dropped else f"{len(known)} kept")

    # every known quantity must come from the problem text — an LLM that invents numbers for an
    # incomplete problem ("小明有一些钱，买东西后还剩一些钱") must not produce a "verified" structure
    if text:
        in_text = numbers_in_text(text)
        invented = [f"{k['name']}={k['value']}" for k in known if not _grounded(k["value"], in_text)]
        if not add("known_quantities_grounded", bool(known) and not invented,
                   f"not in the problem text: {invented}" if invented else
                   ("no known quantity" if not known else f"{len(known)} found in the text")):
            return None, checks

    record = {
        "question_id": question_id_for(text),
        "source": "extracted",
        "difficulty": None,
        "topic": raw.get("topic", ""),
        "question": text,
        "known_quantities": known,
        "unknown": {"symbol": "x", "meaning": (raw.get("unknown") or {}).get("meaning", ""),
                    "unit": (raw.get("unknown") or {}).get("unit", "")},
        "variable_definition": raw.get("variable_definition", ""),
        "relationship": raw.get("relationship", ""),
        "equation": eq,
        "answer": _fmt(x_val),
        "final_answer_text": final_answer_text,
        "answer_parts": [{"label": p["label"], "value": _fmt(p["value"]), "unit": p["unit"]} for p in parts],
        "e4_patterns": e4,
        "accepted_equivalent_forms": alts,
        "verification_conditions": conds,
        "mutations": [],
        "s1": {"target": raw.get("s1_target") or "题目最后问的量", "intermediate": raw.get("s1_intermediate") or ""},
    }
    return record, checks


def _independent_agrees(record: dict, independent: dict | None) -> tuple[bool | None, str]:
    """Compare the independent LLM solution with the computed answer parts (as number multisets)."""
    if not independent:
        return None, "no independent solution"
    try:
        theirs = sorted(_num(p["value"]) for p in independent.get("parts", []))
    except Exception:  # noqa: BLE001
        return None, "independent solution unreadable"
    ours = sorted(_num(p["value"]) for p in record["answer_parts"])
    if not theirs:
        return None, "independent solution empty"
    agrees = set(ours) <= set(theirs) or set(theirs) <= set(ours)
    return agrees, f"computed {[_fmt(v) for v in ours]} vs independent {[_fmt(v) for v in theirs]}"


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """你是初中数学老师。学生看了你对一道应用题已知条件的理解后，说你读错了。请只根据原题文字判断学生的说法对不对。
- learner_right：原题文字支持学生的说法（你之前的理解确实有误）；
- learner_wrong：原题文字和学生的说法不一致（学生记错或看错了）；
- unclear：原题文字无法判断，或学生说的与已知条件无关。
quote 必须从原题中逐字摘录相关的那一句或那一段（不能改写）。reply 用一两句话对学生说明，learner_wrong 时要引用原文指出差别。
只输出 JSON：{"verdict": "learner_right|learner_wrong|unclear", "quote": "原题原文", "reply": "..."}"""

LEARNER_RIGHT, LEARNER_WRONG, JUDGE_UNCLEAR = "learner_right", "learner_wrong", "unclear"


def _squash(t: str) -> str:
    return re.sub(r"[\s，,。．.、:：；;？?！!“”\"'（）()]", "", t or "")


def judge_correction(text: str, understanding: list[str], note: str, backend) -> dict:
    """
    Is the learner's correction supported by the problem text? The verdict "learner_wrong" is only
    kept when its quote really appears in the problem (whitespace/punctuation aside) — the system
    never tells a learner they are wrong without the words of the problem to show it.
    """
    out = {"verdict": JUDGE_UNCLEAR, "quote": "", "reply": ""}
    if backend is None or not note:
        return out
    try:
        raw = json.loads(backend.complete(JUDGE_SYSTEM, json.dumps(
            {"原题": text, "你之前读到的已知条件": understanding, "学生的说法": note}, ensure_ascii=False)))
    except Exception:  # noqa: BLE001
        return out
    verdict = raw.get("verdict") if raw.get("verdict") in (LEARNER_RIGHT, LEARNER_WRONG, JUDGE_UNCLEAR) else JUDGE_UNCLEAR
    quote, reply = str(raw.get("quote") or ""), str(raw.get("reply") or "")
    quote_ok = bool(_squash(quote)) and _squash(quote) in _squash(text)
    if verdict == LEARNER_WRONG and not quote_ok:
        verdict = JUDGE_UNCLEAR                      # no verbatim evidence → do not claim the learner is wrong
    out.update(verdict=verdict, quote=quote if quote_ok else "", reply=reply)
    return out


def extract_structure(text: str, backend, learner_note: str | None = None) -> Extraction:
    """
    learner_note: the learner's correction after seeing "我读到的已知条件" (e.g. "乙每小时走6千米").
    It is passed to the extraction only. The independent solve still sees the problem text alone,
    so a wrong correction produces a structure the independent solution disagrees with, and the
    problem is not guided — the learner cannot talk the system into a wrong reading.
    """
    text = (text or "").strip()
    if backend is None:
        return Extraction(text, scope=UNCERTAIN, error="no LLM backend: only question-bank items can be guided")
    payload = {"题目": text}
    if learner_note:
        payload["学生对题意的说明"] = (f"学生认为你上次读错了题：{learner_note}。请对照原题重新读一遍；"
                                 "学生的说法不一定对，一切以原题文字为准。")
    try:
        raw = json.loads(backend.complete(EXTRACT_SYSTEM, json.dumps(payload, ensure_ascii=False)))
    except Exception as exc:  # noqa: BLE001
        return Extraction(text, scope=UNCERTAIN, error=f"extraction failed: {exc}")

    scope = raw.get("scope") if raw.get("scope") in (IN_SCOPE, OUT_OF_SCOPE, UNCERTAIN) else UNCERTAIN
    ex = Extraction(text, scope=scope, scope_reason=raw.get("scope_reason", ""), raw=raw)
    if scope != IN_SCOPE:
        return ex

    record, checks = validate_structure(raw, text)
    ex.checks = checks
    if record is None:
        ex.consistency = INCONSISTENT
        return ex

    try:
        ex.independent = json.loads(backend.complete(SOLVE_SYSTEM, text))
    except Exception:  # noqa: BLE001
        ex.independent = None
    agrees, detail = _independent_agrees(record, ex.independent)
    ex.checks.append(Check("independent_solution_agrees", agrees is True, detail))

    ex.consistency = CONSISTENT if agrees else (INCONSISTENT if agrees is False else UNCERTAIN)
    describe = getattr(backend, "describe", lambda: {})()
    record["extraction"] = {"consistency": ex.consistency, "prompt_version": PROMPT_VERSION, "model": describe,
                            "checks": [c.__dict__ for c in ex.checks], "learner_note": learner_note}
    ex.question = record
    return ex
