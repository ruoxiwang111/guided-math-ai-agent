"""
core/diagnosis.py — maths evidence → E1–E7 diagnosis with evidence level.

Implements error_taxonomy.md §9 (decision procedure), §10.7–10.10, §11, §12.
Uses core.math_checker for every mathematical judgement; this module only
decides what the evidence means.

Three entry points, one per kind of learner response:

    diagnose_modelling(question, equation, variable_definition=None)   # S2
    diagnose_steps(question, steps, variable_definition=None)          # S3
    diagnose_final_answer(question, final_answer_text)                 # S4 / answer only

and diagnose_response(question, response) which picks the right one from a
D2-style learner_response dict.

How categories are decided
  S2  learner equation + variable definition
      - which quantity does x stand for? (standard definition or an accepted
        alternative; deterministic text match, see _quantity / resolve_definition)
      - equivalent to the matching reference            → no_error_detected
      - equivalent to a bank modelling mutation         → that category (Level A)
      - equivalent to a reference for a DIFFERENT x     → E2 (Level A)
      - otherwise: wrong relationship                   → E3, or uncertain E3/E4
        when the question contains a closed-list E4 phrase (§3 E3/E4 boundary)
  S3  ordered working
      - line 1 not equivalent to the reference          → treat line 1 as S2
      - first invalid transition classified by RULES, not by mutation lookup:
          matches a buggy algebraic operation           → E7
          same form as a correct step, one number off   → E6
          otherwise                                     → uncertain (E6/E7)
  S4  final answer only (§10.10)
      - E1 / E5 visible in the answer itself            → Level A
      - matches another mutation's result               → Level B, uncertain
      - otherwise                                       → insufficient_evidence, ask for working

Limitations (reported, not hidden)
  - variable-definition matching is a deterministic string heuristic; the LLM
    layer may later assist, but must not override the checker (§16).
  - E6/E7 rules cover the transformations listed in §10.8; anything else is
    returned as uncertain rather than forced into a category (§10.9).
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

from sympy import Add, Mul, Number, Poly, S, nsimplify
from sympy.parsing.sympy_parser import parse_expr

from core import math_checker as mc
from core.normalizer import OK, normalize_line, split_steps

# statuses (error_taxonomy.md §9 step 5)
DIAGNOSED = "diagnosed"
UNCERTAIN = "uncertain"
NO_ERROR = "no_error_detected"
INSUFFICIENT = "insufficient_evidence"

# follow-up actions (evidence collection, not metacognitive follow-ups — §9 step 7)
ASK_WORKING = "request_working"
ASK_DEFINITION = "clarify_variable_definition"
ASK_NOTATION = "clarify_notation"
ASK_DISCRIMINATING = "ask_discriminating_question"
ASK_ONE_VARIABLE = "use_one_variable"          # learner used two unknowns (e.g. a system in x, y)
ASK_REWRITE = "rewrite_expression"             # unreadable or outside V1 (e.g. x²)
ASK_RECHECK_PART = "recheck_answer_part"       # one quantity in the final answer is wrong
ASK_ADD_UNIT = "add_unit"                      # right numbers, unit missing
ASK_COMPLETE_ANSWER = "complete_answer"        # some asked quantity is missing
ASK_EQUATION = "write_equation"                # definition written and fine, equation still missing

ANSWER_LEVEL_A = {"E1", "E5"}


@dataclass
class Diagnosis:
    status: str
    state: str                                   # S2 / S3 / S4
    primary_error: str | None = None             # E1–E7 (subtype collapsed)
    error_subtype: str | None = None             # e.g. "E4-01"
    candidates: list[str] = field(default_factory=list)
    evidence_level: str | None = None            # A / B / C / D
    evidence: str = ""
    first_invalid_step: int | None = None
    matched_mutation: str | None = None
    rule: str | None = None                      # which rule produced the label
    follow_up: str | None = None
    recommended_hint_level: int | None = None
    notes: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)  # structured facts for wording (e.g. which answer part is wrong)


def _collapse(err):
    return err.split("-")[0] if err else None


def _diagnosed(state, err, evidence, **kw):
    return Diagnosis(status=DIAGNOSED, state=state, primary_error=_collapse(err),
                     error_subtype=err if err and "-" in err else None,
                     candidates=[_collapse(err)], evidence_level="A", evidence=evidence,
                     recommended_hint_level=1, **kw)


# ---------------------------------------------------------------------------
# Variable definitions (deterministic heuristic)
# ---------------------------------------------------------------------------

UNIT_WORDS = ["平方厘米", "平方米", "厘米", "千米", "米", "分钟", "小时", "天", "元", "岁", "人", "台", "本", "支", "千克"]
FILLER = ["今年", "现在", "原来", "的", "年龄", "岁数", "数量", "价格", "人数", "时间", "有", "一支", "一本", "一个", "每", "需要", "用了", "用"]


def _quantity(definition: str | None) -> str | None:
    """'设小华今年x岁，则小明…' → '小华';  '设x为妈妈5年后的年龄' → '妈妈5年后'."""
    if not definition:
        return None
    t = re.split(r"[，,；;。]|则", definition)[0]
    t = re.sub(r"^\s*(解\s*[:：])?\s*设", "", t)
    m = re.match(r"^\s*[xX]\s*(为|是|表示)(.+)$", t)
    if m:                                    # 设x为妈妈5年后的年龄
        t = m.group(2)
    elif re.search(r"[xX]", t):              # 设小华今年x岁 / 设合作x天完成
        before, after = re.split(r"[xX]", t, maxsplit=1)
        before = re.sub(r"(为|是)\s*$", "", before)
        for w in UNIT_WORDS:                 # drop the unit right after x
            if after.startswith(w):
                after = after[len(w):]
                break
        t = before + after
    for w in FILLER:
        t = t.replace(w, "")
    t = re.sub(r"[\s()（）]", "", t)
    return t or None


def _lcs(a: str, b: str) -> int:
    best = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a) + 1):
            if a[i:j] in b:
                best = max(best, j - i)
    return best


def _similarity(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return _lcs(a, b) / max(len(a), len(b))


def _references(question):
    """Standard + accepted alternatives with their own variable definition."""
    refs = [{"label": "standard", "variable_definition": question["variable_definition"],
             "equation": question["equation"], "answer": question["answer"]}]
    for i, f in enumerate(question.get("accepted_equivalent_forms", [])):
        if "variable_definition" in f:
            refs.append({"label": f"alternative{i}", "variable_definition": f["variable_definition"],
                         "equation": f["equation"], "answer": f.get("x_value", question["answer"])})
    return refs


def _match_definition(definition, candidates, key="variable_definition"):
    """Best-matching candidate by quantity; None if unclear (no unique match ≥ 0.5)."""
    q = _quantity(definition)
    if q is None:
        return None
    scored = sorted(((_similarity(q, _quantity(c[key])), i) for i, c in enumerate(candidates)), reverse=True)
    if not scored or scored[0][0] < 0.5:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return candidates[scored[0][1]]


# unit families: a definition is only *incompatible* with a reference when its unit
# clearly belongs to a different family ("设甲走了x千米" vs a time unknown)
UNIT_FAMILY = {
    "time": ["小时", "分钟", "秒", "天", "周", "个月", "时间"],
    "length": ["平方厘米", "平方米", "厘米", "毫米", "千米", "公里", "米", "路程", "距离"],
    "age": ["岁", "年龄"],
    "money": ["元", "价格", "钱"],
    "mass": ["千克", "公斤", "克", "吨"],
    "people": ["人", "名"],
}


def _unit_family(definition):
    """Family of the unit written right after x (or named after '表示/为'); None if none is given."""
    if not definition:
        return None
    first = re.split(r"[，,；;。]|则", definition)[0]
    parts = re.split(r"[xX]", first, maxsplit=1)
    if len(parts) < 2:
        return None
    after = re.sub(r"^\s*(为|是|表示)", "", parts[1])
    best = None
    for fam, words in UNIT_FAMILY.items():
        for w in words:
            i = after.find(w)
            if i >= 0 and (best is None or i < best[0]):
                best = (i, fam)
    return best[1] if best else None


def resolve_definition(definition, refs):
    """
    Which reference model the learner's definition refers to.
    1. a clear quantity match (_match_definition), else
    2. the ONLY reference whose unit family is compatible with the definition — a vague
       but non-contradicting definition ("设x小时相遇", "设x表示相遇时间") must not block
       a learner whose equation is right.
    Returns (ref | None, how) with how ∈ {"match", "compatible", None}.
    """
    ref = _match_definition(definition, refs)
    if ref is not None:
        return ref, "match"
    if not definition or not re.search(r"[xX]", definition):
        return None, None
    fam = _unit_family(definition)
    compatible = [r for r in refs
                  if fam is None or _unit_family(r["variable_definition"]) in (None, fam)]
    if len(compatible) == 1:
        return compatible[0], "compatible"
    return None, None


# ---------------------------------------------------------------------------
# E4 closed-list templates (error_taxonomy.md §4.2, §12.1 "predefined E4
# phrase-pattern errors") — applied to the question's standard equation.
# Only patterns listed in question["e4_patterns"] are used (§4.3.1).
# ---------------------------------------------------------------------------

NUM = r"\d+(?:\.\d+)?"


def _flip_signs(eq):
    """E4-01 / E4-02: reverse the comparison  x+k ↔ x-k  (each occurrence)."""
    out = []
    for m in re.finditer(rf"x\s*([+-])\s*({NUM})(?![\d.]|\s*\*?\s*[xX(])", eq):   # a constant, not k*x
        flipped = "-" if m.group(1) == "+" else "+"
        out.append(eq[:m.start()] + f"x {flipped} {m.group(2)}" + eq[m.end():])
    return out


def _discount_as_subtraction(eq):
    """E4-06: 0.8*x → (x - 0.8)."""
    return [re.sub(rf"(0\.\d+)\s*\*\s*x", r"(x - \1)", eq, count=1)] if re.search(r"0\.\d+\s*\*\s*x", eq) else []


def _increase_as_part(eq):
    """E4-03 / E4-04: 1.2*x → 0.2*x  and  x*1.2 → x*0.2."""
    out = []
    for pat, rep_ in ((rf"1\.(\d+)\s*\*\s*x", r"0.\1*x"), (rf"x\s*\*\s*1\.(\d+)", r"x*0.\1")):
        if re.search(pat, eq):
            out.append(re.sub(pat, rep_, eq, count=1))
    return out


def _multiple_reversed(eq):
    """E4-07: k*x ↔ x/k."""
    return [re.sub(rf"(?<![\d.])(\d+)\s*\*\s*x", r"x/\1", eq, count=1)] if re.search(r"\d\s*\*\s*x", eq) else []


def _removed_instead_of_left(eq):
    """E4-08: (2/3)*x → (1/3)*x."""
    return [eq.replace("2/3", "1/3")] if "2/3" in eq else []


E4_TEMPLATES = {
    "E4-01": _flip_signs, "E4-02": _flip_signs,
    "E4-03": _increase_as_part, "E4-04": _increase_as_part,
    "E4-06": _discount_as_subtraction,
    "E4-07": _multiple_reversed, "E4-08": _removed_instead_of_left,
}


def e4_variants(question):
    """[(pattern_id, wrong_equation)] generated from the standard equation."""
    out = []
    for pid in question.get("e4_patterns", []):
        fn = E4_TEMPLATES.get(pid)
        if fn:
            out += [(pid, v) for v in fn(question["equation"])]
    return out


def _defines_second_quantity(definition):
    """'设小华x岁，小明为(x-5)岁' → True;  '设乘汽车x小时' → False."""
    parts = [p for p in re.split(r"[，,；;]|则", definition or "") if p.strip()]
    return len(parts) > 1 and any("x" in p or "X" in p for p in parts[1:])


# ---------------------------------------------------------------------------
# S2 — modelling
# ---------------------------------------------------------------------------

def _unreadable(nl, state, question=None, text="", variable_definition=None) -> Diagnosis:
    """Evidence request that matches WHY the input could not be checked (never an error label)."""
    codes = nl.issue_codes()
    msg = "; ".join(i.message for i in nl.issues)
    if nl.status == "ambiguous":
        return Diagnosis(status=UNCERTAIN, state=state, evidence_level="C",
                         evidence=f"写法有歧义：{msg}", follow_up=ASK_NOTATION)
    if "multiple_variables" in codes:
        if question is not None:
            sys_d = _check_system(question, text, variable_definition)
            if sys_d is not None:
                return sys_d
        return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D", rule="two_unknowns",
                         evidence="用了两个未知数；V1 要求只用一个未知数 x 列一元一次方程", follow_up=ASK_ONE_VARIABLE)
    rule = "power" if "power" in codes else "unreadable"
    return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D", rule=rule,
                     evidence=f"式子无法检查：{msg}", follow_up=ASK_REWRITE)


SYSTEM_SPLIT_RE = re.compile(r"[，,；;]|且")


def _parse_two_unknowns(part: str):
    from core.normalizer import _to_ascii
    t = _to_ascii(part).strip().rstrip("。.")
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"(\d)([a-zA-Z(])", r"\1*\2", t)
    t = re.sub(r"\)([a-zA-Z\d(])", r")*\1", t)
    t = re.sub(r"([a-zA-Z])\(", r"\1*(", t)
    lhs, rhs = t.split("=")
    return parse_expr(lhs) - parse_expr(rhs)


def _check_system(question, text, variable_definition=None):
    """
    A two-unknown linear system (e.g. 'x-4=y+4，x+y=56'). Solve it; if its x matches the
    reference for the learner's meaning of x, the modelling is right but not yet in the
    one-variable form V1 asks for. Returns None if the text is not such a system.
    """
    from sympy import linsolve, symbols as _symbols
    parts = [p for p in SYSTEM_SPLIT_RE.split(text or "") if "=" in p]
    if len(parts) < 2:
        return None
    try:
        exprs = [_parse_two_unknowns(p) for p in parts]
    except Exception:  # noqa: BLE001
        return None
    syms = sorted(set().union(*(e.free_symbols for e in exprs)), key=lambda v: (v.name != "x", v.name))
    if len(syms) != 2 or any(Poly(e, *syms).total_degree() > 1 for e in exprs):
        return None
    sol = list(linsolve(exprs, *syms))
    if len(sol) != 1 or any(v.free_symbols for v in sol[0]):
        return None
    values = {str(sym): nsimplify(v, rational=True) for sym, v in zip(syms, sol[0])}
    refs = _references(question)
    ref = resolve_definition(variable_definition, refs)[0] if variable_definition else None
    x_val = values.get("x", next(iter(values.values())))
    targets = [ref] if ref else refs
    correct = any(nsimplify(S(r["answer"]), rational=True) == x_val for r in targets)
    shown = "，".join(f"{k} = {v}" for k, v in values.items())
    if correct:
        return Diagnosis(status=INSUFFICIENT, state="S2", evidence_level="A", rule="two_variable_system_correct",
                         evidence=f"二元一次方程组是正确的（{shown}），但这一步要求只用一个未知数",
                         follow_up=ASK_ONE_VARIABLE, notes=["方程组正确，不计为错误"])
    return Diagnosis(status=INSUFFICIENT, state="S2", evidence_level="C", rule="two_variable_system_incorrect",
                     evidence=f"方程组的解（{shown}）与题意不符；需要改成只含 x 的一元一次方程再判断",
                     follow_up=ASK_ONE_VARIABLE)


def diagnose_modelling(question, equation, variable_definition=None, exclude_mutation=None) -> Diagnosis:
    state = "S2"
    if not (equation or "").strip():
        # the learner wrote only "设……" so far: check that part and ask for the equation
        if not (variable_definition or "").strip():
            return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D", rule="nothing_written",
                             evidence="还没有写设法和方程", follow_up=ASK_WORKING)
        ref, _how = resolve_definition(variable_definition, _references(question))
        if ref is None:
            return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D", rule="definition_only_unclear",
                             evidence="只写了设法，而且看不出 x 表示题目中的哪个量", follow_up=ASK_DEFINITION)
        return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D", rule="definition_only_ok",
                         evidence="设法合理，还没有列方程", follow_up=ASK_EQUATION,
                         details={"ref": ref["label"], "defines_relation": _defines_second_quantity(variable_definition)})
    nl = normalize_line(equation)
    if nl.status != OK or nl.kind != "equation":
        if nl.status == OK:            # an expression without "="
            return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D", rule="no_equals_sign",
                             evidence="这不是方程（没有等号）", follow_up=ASK_REWRITE)
        return _unreadable(nl, state, question, equation, variable_definition)

    refs = _references(question)
    notes = []
    if variable_definition is None:
        variable_definition = question["variable_definition"]
        notes.append("未提供变量定义，按题目标准定义处理")
    ref, how = resolve_definition(variable_definition, refs)
    if how == "compatible":
        notes.append("变量定义不够具体，但与这个量不矛盾，按它理解")

    learner_set = mc.solution_set(equation)
    if not learner_set.linear:
        return Diagnosis(status=UNCERTAIN, state=state, evidence_level="C",
                         evidence="方程不是一次方程，超出 V1 自动判断范围", notes=notes)

    # 1. correct?
    if ref is not None and mc.equivalent(equation, ref["equation"]):
        return Diagnosis(status=NO_ERROR, state=state, evidence_level="A",
                         evidence=f"与{'标准' if ref['label'] == 'standard' else '另一种正确'}方程同解（x = {ref['answer']}）",
                         notes=notes, details={"ref": ref["label"], "definition_match": how})

    # 2. matches a known modelling mutation whose definition fits the learner's
    mutations = [m for m in question["mutations"] if m["layer"] == "modelling" and m["id"] != exclude_mutation]
    for m in mutations:
        m_def = m.get("variable_definition", question["variable_definition"])
        same_def = (_similarity(_quantity(variable_definition), _quantity(m_def)) >= 0.5
                    or (ref is not None and m_def == ref["variable_definition"]))
        if same_def and mc.equivalent(equation, m["equation"]):
            return _diagnosed(state, m["error"], f"方程与已知错误模式 {m['id']} 同解：{m['description']}",
                              matched_mutation=m["id"], rule="mutation_match", notes=notes)

    # 3. closed-list E4 pattern generated from the standard equation
    if ref is not None and ref["label"] == "standard":
        for pid, wrong in e4_variants(question):
            if mc.equivalent(equation, wrong):
                return _diagnosed(state, pid, f"方程符合 {pid} 的翻译错误模式（{wrong}）",
                                  rule="e4_template", notes=notes)

    # 4. correct equation for a different meaning of x → E2,
    #    but only when the learner defined x alone (otherwise the definition itself
    #    fixes the relationship and the mismatch is a relationship error)
    for other in refs:
        if other is not ref and mc.equivalent(equation, other["equation"]):
            if _defines_second_quantity(variable_definition):
                break
            if ref is None:
                return Diagnosis(status=UNCERTAIN, state=state, candidates=["E2"], evidence_level="C",
                                 evidence=f"方程对应“{other['variable_definition']}”，但变量定义不清楚",
                                 follow_up=ASK_DEFINITION, notes=notes)
            return _diagnosed(state, "E2",
                              f"方程对应“{other['variable_definition']}”，与学生写的“{variable_definition}”不一致",
                              rule="equation_fits_other_definition", notes=notes)

    if ref is None:
        return Diagnosis(status=UNCERTAIN, state=state, candidates=["E2", "E3"], evidence_level="C",
                         evidence="变量定义与题目中的量对不上，无法判断方程错在哪里",
                         follow_up=ASK_DEFINITION, notes=notes)

    # 5. no known pattern: the equation is wrong, but the deterministic layer
    #    cannot tell WHICH relationship is wrong → uncertain, never a forced label.
    #    It can still say WHERE: one side may equal a side of the reference equation.
    cands = ["E3"] + (["E4"] if question.get("e4_patterns") else []) + ["E2"]
    side = locate_wrong_side(equation, ref["equation"])
    if side:
        evidence = f"方程{side['correct_side_name']}“{side['correct_side_text']}”与题意一致，" \
                   f"{side['wrong_side_name']}“{side['wrong_side_text']}”与题目中的量对不上" + \
                   ("（像是少了括号：倍数只乘了其中一项）" if side.get("missing_brackets") else "")
        return Diagnosis(status=UNCERTAIN, state=state, candidates=cands, evidence_level="C", details=side,
                         evidence=evidence, follow_up=ASK_DISCRIMINATING, rule="one_side_wrong", notes=notes)
    return Diagnosis(status=UNCERTAIN, state=state, candidates=cands, evidence_level="C",
                     evidence="变量定义能对应到题目中的量，但方程与题意不符，且不符合任何已知错误模式",
                     follow_up=ASK_DISCRIMINATING, rule="unmatched_relationship", notes=notes)


def locate_wrong_side(learner_eq: str, reference_eq: str) -> dict | None:
    """
    3x+5 = 2x+5  vs  3x+5 = 2(x+5)  →  the left side matches, the right side does not, and the
    right side is the reference side with its brackets dropped (k·(p+q) written as k·p+q).
    Sides are compared as expressions (sympy), in both orientations. None if no side matches.
    """
    nl = normalize_line(learner_eq)
    if not nl.ok or nl.kind != "equation":
        return None
    try:
        l_raw = [p.strip() for p in re.split(r"[=＝]", learner_eq, maxsplit=1)]
        ll, lr = mc._sides(nl.normalized)
        rl, rr = mc._sides(reference_eq)
        ref_raw = _raw_sides(reference_eq)
    except Exception:  # noqa: BLE001
        return None
    same = lambda a, b: (a - b).expand() == 0  # noqa: E731
    for (ok_i, bad_i), (ref_ok, ref_bad, ref_bad_raw) in (
            ((0, 1), (rl, rr, ref_raw[1])), ((0, 1), (rr, rl, ref_raw[0])),
            ((1, 0), (rr, rl, ref_raw[0])), ((1, 0), (rl, rr, ref_raw[1]))):
        learner_ok, learner_bad = (ll, lr) if ok_i == 0 else (lr, ll)
        if same(learner_ok, ref_ok) and not same(learner_bad, ref_bad):
            names = ("左边", "右边")
            out = {"correct_side_name": names[ok_i], "wrong_side_name": names[bad_i],
                   "correct_side_text": l_raw[ok_i], "wrong_side_text": l_raw[bad_i]}
            k = _dropped_brackets(ref_bad_raw, learner_bad)
            if k is not None:
                out.update(missing_brackets=True, bracket_factor=str(k))
            return out
    return None


def _dropped_brackets(ref_side_raw, learner_side):
    """k·(p+q) in the reference side written as k·p + q by the learner → k, else None."""
    for node in ref_side_raw.atoms(Mul):
        nums = [f for f in node.args if isinstance(f, Number)]
        adds = [f for f in node.args if isinstance(f, Add)]
        if len(nums) == 1 and len(adds) == 1:
            k, inner = nums[0], adds[0]
            terms = list(inner.args)
            wrong = ref_side_raw.xreplace({node: k * terms[0] + Add(*terms[1:])}).doit()
            if (wrong - learner_side).expand() == 0:
                return nsimplify(k, rational=True)
    return None


def correct_next_line(prev_norm: str, curr_norm: str) -> str | None:
    """
    The correct line the learner was most likely aiming for: among the correct transformations
    of the previous line, the one closest to what they wrote (x = 8-12 → x = 20;
    2x+x+3 = 26 → 4x + 6 = 26). Used for the learner-requested step reference in S3.
    """
    try:
        target = _canon(curr_norm)
        forms = _correct_forms(prev_norm)
    except Exception:  # noqa: BLE001
        return None
    if not forms:
        return None
    best = min(forms, key=lambda f: (sum(u != v for u, v in zip(f, target)),
                                     sum(abs(u - v) for u, v in zip(f, target))))
    return render_form(best)


def render_form(form) -> str:
    """(a, b, c, d) → 'a·x + b = c·x + d' in written form (4x + 6 = 26, x = 20)."""
    def side(a, b):
        parts = []
        if a != 0:
            parts.append("x" if a == 1 else "-x" if a == -1 else f"{_fmt_num(a)}x")
        if b != 0 or not parts:
            if parts:
                parts.append(f"- {_fmt_num(-b)}" if b < 0 else f"+ {_fmt_num(b)}")
            else:
                parts.append(_fmt_num(b))
        return " ".join(parts)
    a, b, c, d = form
    return f"{side(a, b)} = {side(c, d)}"


def _fmt_num(v):
    v = nsimplify(v, rational=True)
    return str(v) if v.q == 1 else f"{v.p}/{v.q}"


# ---------------------------------------------------------------------------
# S3 — E6 / E7 rules on the first invalid transition
# ---------------------------------------------------------------------------

def _raw_sides(normalized: str):
    """Sides parsed WITHOUT evaluation, so 2*(x+4) keeps its brackets."""
    return tuple(parse_expr(p, local_dict={"x": mc.X}, transformations=mc.TRANSFORMS, evaluate=False)
                 for p in normalized.split("="))


def _canon(normalized: str):
    """'lhs=rhs' → (a, b, c, d) with lhs = a·x + b, rhs = c·x + d (exact)."""
    return _canon_sides(*mc._sides(normalized))


def _canon_sides(lhs, rhs):
    out = []
    for side in (lhs, rhs):
        p = Poly(side.expand(), mc.X)
        if p.degree() > 1:
            raise ValueError("non-linear")
        coeffs = p.all_coeffs()
        a, b = (coeffs if len(coeffs) == 2 else [S(0)] + coeffs)
        out += [nsimplify(a, rational=True), nsimplify(b, rational=True)]
    return tuple(out)


def _numeric_factors(normalized: str):
    ks = set()
    for side in _raw_sides(normalized):
        for node in [side, *side.atoms(Mul)]:
            if isinstance(node, Mul):
                for f in node.args:
                    if isinstance(f, Number) and f not in (0, 1, -1):
                        ks.add(nsimplify(f, rational=True))
    return ks


def _moves(a, b, c, d):
    """All correct ways to regroup x-terms / constants between the two sides."""
    xs = [(a, c), (a - c, 0), (0, c - a)]
    cs = [(b, d), (b - d, 0), (0, d - b)]
    return [(xa, cb, xc, cd) for (xa, xc), (cb, cd) in itertools.product(xs, cs)]


def _scaled(form, ks):
    a, b, c, d = form
    out = {form}
    extra = {k for k in (a, c) if k not in (0, 1)} | set(ks)
    for k in extra:
        if k != 0:
            out.add((a / k, b / k, c / k, d / k))
    return out


def _with_swaps(forms):
    return set(forms) | {(c, d, a, b) for a, b, c, d in forms}


def _correct_forms(prev_norm):
    a, b, c, d = _canon(prev_norm)
    ks = _numeric_factors(prev_norm)
    forms = set()
    for f in _moves(a, b, c, d):
        forms |= _scaled(f, ks)
    return _with_swaps(forms)


def _buggy_forms(prev_norm):
    """Canonical forms produced by the E7 operations of §7 / §10.8."""
    a, b, c, d = _canon(prev_norm)
    bugs = {}

    # transposition without sign change (any combination with ≥ 1 unflipped move)
    x_opts = [("keep", (a, c)), ("x→L ok", (a - c, 0)), ("x→R ok", (0, c - a))]
    if c != 0:
        x_opts.append(("x→L unflipped", (a + c, 0)))
    if a != 0:
        x_opts.append(("x→R unflipped", (0, c + a)))
    c_opts = [("keep", (b, d)), ("c→L ok", (b - d, 0)), ("c→R ok", (0, d - b))]
    if d != 0:
        c_opts.append(("c→L unflipped", (b + d, 0)))
    if b != 0:
        c_opts.append(("c→R unflipped", (0, d + b)))
    for (xn, (xa, xc)), (cn, (cb, cd)) in itertools.product(x_opts, c_opts):
        if "unflipped" in xn or "unflipped" in cn:
            form = (xa, cb, xc, cd)
            bugs[form] = "transposition_sign"
            # learner may also divide by the x coefficient in the same line
            for k in (xa, xc):
                if k not in (0, 1):
                    bugs.setdefault((xa / k, cb / k, xc / k, cd / k), "transposition_sign")

    # k·x = d  solved with the wrong inverse operation
    for (k, const, x_left) in ((a, d, True), (c, b, False)):
        other_x = c if x_left else a
        other_c = b if x_left else d
        if k not in (0, 1) and other_x == 0 and other_c == 0:
            for val, name in ((const - k, "subtract_instead_of_divide"), (const + k, "add_instead_of_divide"),
                              (const * k, "multiply_instead_of_divide"), (k / const if const else None, "inverted_division")):
                if val is not None:
                    bugs.setdefault((S(1), S(0), S(0), val), name)

    # operation applied to only one side / one term (divide by the x coefficient)
    for k in {a, c} - {0, 1}:
        for mask in itertools.product((True, False), repeat=4):
            if all(mask) or not any(mask):
                continue
            form = tuple(v / k if m else v for v, m in zip((a, b, c, d), mask))
            bugs.setdefault(form, "operation_on_one_side")

    return bugs


def _distribution_bugs(prev_norm):
    """k·(p + q) expanded wrongly: only first term multiplied, or all signs flipped."""
    bugs = {}
    lhs, rhs = _raw_sides(prev_norm)
    for side_idx, side in enumerate((lhs, rhs)):
        for node in side.atoms(Mul):
            nums = [f for f in node.args if isinstance(f, Number)]
            adds = [f for f in node.args if isinstance(f, Add)]
            if len(nums) == 1 and len(adds) == 1:
                k, inner = nums[0], adds[0]
                terms = list(inner.args)
                variants = {
                    "distribute_first_term_only": k * terms[0] + Add(*terms[1:]),
                    "distribute_sign_flipped": -k * inner,
                    "distribute_second_sign": k * terms[0] - k * Add(*terms[1:]),
                }
                for name, repl in variants.items():
                    new = side.xreplace({node: repl})
                    pair = (new, rhs) if side_idx == 0 else (lhs, new)
                    try:
                        form = _canon_sides(pair[0].doit(), pair[1].doit())
                    except Exception:  # noqa: BLE001
                        continue
                    bugs.setdefault(form, name)
    return bugs


def _differs_in_one(f, g):
    zero_pattern_same = all((u == 0) == (v == 0) for u, v in zip(f, g))
    return zero_pattern_same and sum(u != v for u, v in zip(f, g)) == 1


def classify_transition(prev_norm: str, curr_norm: str):
    """
    Return (category | None, rule) for an invalid transition prev → curr.
    category is 'E7', 'E6' or None (uncertain).
    """
    try:
        curr = _canon(curr_norm)
        _canon(prev_norm)
    except Exception:  # noqa: BLE001
        return None, "non_linear_or_unparseable"

    bugs = _buggy_forms(prev_norm)
    bugs.update(_distribution_bugs(prev_norm))
    for form, name in list(bugs.items()):
        bugs.setdefault((form[2], form[3], form[0], form[1]), name)       # swapped sides
    if curr in bugs:
        return "E7", bugs[curr]

    for good in _correct_forms(prev_norm):
        if _differs_in_one(curr, good):
            return "E6", "one_number_off_from_valid_step"
    return None, "no_rule_matched"


def diagnose_steps(question, steps, variable_definition=None, start_equation=None) -> Diagnosis:
    """
    start_equation: the equation the learner already set up in S2 (their own wording). When the
    working does not begin with it, the first line is checked as a STEP from it — e.g. going from
    3x+5=2(x+5) straight to 3x+5=2x+5 is a bracket-expansion error on line 1, not a new equation.
    Line numbers always refer to the lines the learner submitted.
    """
    state = "S3"
    r = mc.check_steps(steps, reference_equation=question["equation"])
    offset, start_line = 0, None
    if start_equation and r.status == mc.INVALID_FOUND and r.reason == mc.START_DIFFERS:
        lines = split_steps(steps) if isinstance(steps, str) else list(steps)
        r = mc.check_steps([start_equation] + lines, reference_equation=question["equation"])
        offset, start_line = 1, start_equation

    if r.status == mc.UNCERTAIN:
        line = r.lines[r.blocked_at - 1]
        d = _unreadable(normalize_line(line.original), state)
        d.evidence = f"第{r.blocked_at - offset}行：{d.evidence}"
        return d
    if r.status == mc.NO_EQUATION:
        return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D",
                         evidence="没有可检查的方程", follow_up=ASK_WORKING)
    if r.status == mc.ALL_VALID:
        note = [] if r.final_matches_reference else ["每一步都等价，但还没有写出 x = … 的结果"]
        if offset:
            note.append("学生没有重抄方程，第一行直接从列好的方程往下算")
        return Diagnosis(status=NO_ERROR, state=state, evidence_level="A",
                         evidence="每一步变形都保持解不变", notes=note)

    k = r.first_invalid_step
    line = r.lines[k - 1]
    shown = k - offset                                  # the learner's own line number

    if r.reason == mc.START_DIFFERS:
        d = diagnose_modelling(question, line.original, variable_definition)
        d.first_invalid_step = shown
        d.notes.append("第一行方程与题目的标准方程不等价，按建模（S2）诊断")
        return d

    if r.reason == mc.CHAIN_SEGMENT_MISMATCH:
        return _diagnosed(state, "E6", f"第{shown}行连等式中间一段算错：{line.note}",
                          first_invalid_step=shown, rule="chain_segment_mismatch")

    prev_index, prev = next((i, lc) for i, lc in reversed(list(enumerate(r.lines[:k - 1])))
                            if lc.solutions is not None)
    from_start = offset == 1 and prev_index == 0
    details = {"prev_line": prev.original, "from_start_equation": from_start}
    category, rule = classify_transition(prev.normalized, line.normalized)
    notes = []
    if r.consistent_after_error is False:
        notes.append("出错之后还有不一致的步骤，可能有第二处错误（未单独诊断）")
    src = f"学生列好的方程“{start_line}”" if from_start else f"上一行“{prev.original}”"
    evidence = f"第{shown}行“{line.original}”不再与{src}同解"
    if category is None:
        return Diagnosis(status=UNCERTAIN, state=state, candidates=["E6", "E7"], evidence_level="C",
                         evidence=evidence + "；无法判断是计算错误还是变形错误", details=details,
                         first_invalid_step=shown, rule=rule, follow_up=ASK_DISCRIMINATING, notes=notes)
    d = _diagnosed(state, category, evidence + f"（{rule}）", first_invalid_step=shown, rule=rule, notes=notes)
    d.details = details
    return d


# ---------------------------------------------------------------------------
# S4 — final answer only (§10.10)
# ---------------------------------------------------------------------------

def _clean(text):
    return re.sub(r"[\s，,。．.、:：]", "", text or "")


NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:/\d+)?")


def _numbers(text):
    return [nsimplify(S(n), rational=True) for n in NUM_RE.findall(text or "")]


def _final_value_of(m, question):
    if m["layer"] == "execution":
        r = mc.check_steps(m["steps"])
        return r.final_value
    if m["layer"] == "modelling":
        s = mc.solution_set(m["equation"])
        return next(iter(s.values)) if s and s.kind == mc.UNIQUE else None
    return None


# units are a closed list (+ the question's own units): the text after a unit is NOT part
# of it — "4小时后甲乙两人相遇" is 4 小时, not 4 "小时后甲乙两人相遇"
ANSWER_UNITS = [
    "平方厘米", "平方分米", "平方千米", "平方米", "立方厘米", "立方米", "毫升", "公顷",
    "千米", "公里", "厘米", "分米", "毫米", "米", "个小时", "小时", "分钟", "秒", "天", "周", "个月", "月", "年",
    "岁", "元", "角", "千克", "公斤", "克", "吨", "斤", "升", "亩",
    "人", "名", "台", "本", "支", "页", "个", "件", "辆", "瓶", "张", "次", "箱", "袋", "盒", "棵", "只",
    "头", "块", "条", "份", "套", "双", "道", "间", "包", "杯", "场", "组", "段", "行", "位", "分", "度", "倍",
]
UNIT_ALIASES = {"个小时": "小时", "公里": "千米", "公斤": "千克"}


def _part_re(extra_units=()):
    units = sorted(set(ANSWER_UNITS) | {u for u in extra_units if u}, key=len, reverse=True)
    alt = "|".join(re.escape(u) for u in units)
    return re.compile(rf"([\u4e00-\u9fff]+)?(-?\d+(?:\.\d+)?(?:/\d+)?)\s*((?:{alt})(?:/(?:{alt}))?)?")


PART_RE = _part_re()


RATE_RE = re.compile(r"每(分钟|小时|秒|天|周|月|年|千克|公斤|千米|公里|米|人|个|本|支|件|台|次|页)")


def _canon_unit(label: str, unit: str) -> tuple[str, str]:
    """'每分钟' + '米' and '' + '米/分钟' are the same rate unit → ('', '米/分钟')."""
    m = RATE_RE.search(label)
    if m:
        return label[:m.start()] + label[m.end():], f"{unit}/{m.group(1)}"
    return label, unit


def _question_units(question):
    """Units the question's own answer uses (extracted records carry answer_parts)."""
    out = []
    for p in (question or {}).get("answer_parts", []) or []:
        out += [u for u in re.split(r"/", p.get("unit") or "") if u]
    return tuple(out)


def _answer_parts(text, units=()):
    """'甲班32台，乙班24台' → [('甲班', 32, '台'), ('乙班', 24, '台')]; '每分钟250米' → [('', 250, '米/分钟')]."""
    out = []
    for label, num, unit in (_part_re(units) if units else PART_RE).findall(text or ""):
        unit = "/".join(UNIT_ALIASES.get(u, u) for u in unit.split("/")) if unit else ""
        label, unit = _canon_unit(label or "", unit)
        out.append((label, nsimplify(S(num), rational=True), unit))
    return out


LABEL_FILLER = re.compile(r"今年|现在|原来|的|年龄|岁数|是|有|共|分别|数量|人数|价格|单价|长度|一共|各")


def _label_key(label: str) -> str:
    return LABEL_FILLER.sub("", label or "")


def _compare_parts(question, text):
    """
    Compare a final answer part by part against the reference final_answer_text,
    matching parts by their label (甲班 / 乙班 / 宽 / 长 …). Returns None when the
    reference has no labelled parts or none of them can be matched.
    """
    units = _question_units(question)
    ref = [p for p in _answer_parts(question["final_answer_text"], units) if p[0]]
    learner = _answer_parts(text, units)
    if not ref or not learner:
        return None
    ref_labels = {p[0] for p in ref}

    def find(label):
        if len(ref) == 1 and len(learner) == 1:
            return learner[0]                         # single asked quantity: label may be omitted
        exact = [p for p in learner if p[0] == label]
        if exact:
            return exact[0]
        loose = [p for p in learner if p[0] and label in p[0] and p[0] not in ref_labels]
        if loose:
            return loose[0]
        # "小红今年" ↔ "小红今年的年龄": compare the labels without filler words
        key = _label_key(label)
        fuzzy = [p for p in learner if p[0] and _label_key(p[0])
                 and (key in _label_key(p[0]) or _label_key(p[0]) in key)]
        return fuzzy[0] if len(fuzzy) == 1 else None

    result = {"right": [], "wrong": [], "unit_missing": [], "unit_wrong": [], "missing": []}
    matched = 0
    for label, num, unit in ref:
        p = find(label)
        if p is None:
            result["missing"].append(label)
            continue
        matched += 1
        if p[1] != num:
            result["wrong"].append(label)
        elif not unit:                              # the asked quantity has no unit ("求这个数")
            result["right"].append(label)
        elif not p[2]:
            result["unit_missing"].append(label)
        elif p[2] != unit:
            result["unit_wrong"].append(label)
        else:
            result["right"].append(label)
    return result if matched else None


def diagnose_final_answer(question, final_answer_text, exclude_mutation=None) -> Diagnosis:
    state = "S4"
    if not _clean(final_answer_text):
        return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="D",
                         evidence="没有答案", follow_up=ASK_WORKING)

    if _clean(final_answer_text) == _clean(question["final_answer_text"]):
        return Diagnosis(status=NO_ERROR, state=state, evidence_level="A", evidence="最终答案与参考答案一致")

    for m in question["mutations"]:
        if m["id"] == exclude_mutation:
            continue
        if m["layer"] == "answer" and _clean(m["final_answer_text"]) == _clean(final_answer_text):
            if _collapse(m["error"]) in ANSWER_LEVEL_A:
                return _diagnosed(state, m["error"], f"最终答案与已知错误 {m['id']} 一致：{m['description']}",
                                  matched_mutation=m["id"], rule="answer_pattern_visible")
            return Diagnosis(status=UNCERTAIN, state=state, candidates=[_collapse(m["error"])],
                             evidence_level="B", matched_mutation=m["id"], follow_up=ASK_WORKING,
                             evidence=f"答案与已知错误 {m['id']} 的结果一致，但看不到过程，不能确诊")

    parts = _compare_parts(question, final_answer_text)
    if parts is not None:
        if parts["wrong"]:
            ok = f"{'、'.join(parts['right'])}对了；" if parts["right"] else ""
            return Diagnosis(status=UNCERTAIN, state=state, candidates=["E6", "E1"], evidence_level="C",
                             rule="answer_part_wrong", follow_up=ASK_RECHECK_PART, details=parts,
                             evidence=f"{ok}{'、'.join(parts['wrong'])}的数值不对")
        if parts["unit_wrong"]:
            return _diagnosed(state, "E5", f"{'、'.join(parts['unit_wrong'])}的单位与题目不一致",
                              rule="answer_unit_wrong", details=parts)
        if parts["unit_missing"]:
            return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="A", rule="answer_unit_missing",
                             follow_up=ASK_ADD_UNIT, details=parts,
                             evidence=f"数值都对，{'、'.join(parts['unit_missing'])}后面缺少单位")
        if parts["missing"]:
            return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="A", rule="answer_incomplete",
                             follow_up=ASK_COMPLETE_ANSWER, details=parts,
                             evidence=f"还缺少{'、'.join(parts['missing'])}")
        return Diagnosis(status=NO_ERROR, state=state, evidence_level="A", evidence="各部分数值和单位都正确")

    learner_nums, ref_nums = _numbers(final_answer_text), _numbers(question["final_answer_text"])
    if learner_nums and sorted(learner_nums) == sorted(ref_nums):
        qu = _question_units(question)
        units = lambda t: sorted(u for _, _, u in _answer_parts(t, qu))  # noqa: E731
        if units(final_answer_text) == units(question["final_answer_text"]):
            return Diagnosis(status=NO_ERROR, state=state, evidence_level="A", evidence="数值和单位都正确")
        return _diagnosed(state, "E5", "数值正确，但单位或表述与题目要求不符", rule="numbers_right_unit_wrong")

    # every number written is a correct part, but some asked parts are missing ("小红今年5岁")
    ref_parts = _answer_parts(question["final_answer_text"], _question_units(question))
    if learner_nums and len(ref_parts) > 1 and set(learner_nums) < {p[1] for p in ref_parts}:
        missing = [p[0] or "另一个量" for p in ref_parts if p[1] not in learner_nums]
        right = [p[0] for p in ref_parts if p[1] in learner_nums and p[0]]
        return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="A", rule="answer_incomplete",
                         follow_up=ASK_COMPLETE_ANSWER, evidence=f"写对的部分正确，但还缺少{'、'.join(missing)}",
                         details={"right": right, "wrong": [], "unit_missing": [], "unit_wrong": [],
                                  "missing": missing})

    candidates = []
    for m in question["mutations"]:
        if m["id"] == exclude_mutation:
            continue
        v = _final_value_of(m, question)
        if v is not None and v in learner_nums:
            candidates.append((_collapse(m["error"]), m["id"]))
    if candidates:
        cats = sorted({c for c, _ in candidates})
        return Diagnosis(status=UNCERTAIN, state=state, candidates=cats, evidence_level="B",
                         matched_mutation=candidates[0][1] if len(candidates) == 1 else None,
                         follow_up=ASK_WORKING,
                         evidence=f"答案与已知错误结果一致（{', '.join(i for _, i in candidates)}），需要看过程")

    if any(mc.check_value(v, question["equation"]) for v in learner_nums):
        return Diagnosis(status=UNCERTAIN, state=state, evidence_level="C", follow_up=ASK_WORKING,
                         evidence="x 的值正确，但最终答案的表述与参考不一致，需要确认")
    return Diagnosis(status=INSUFFICIENT, state=state, evidence_level="C", follow_up=ASK_WORKING,
                     evidence="答案不正确，但只有最终答案，无法判断原因")


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------

def diagnose_response(question, response: dict, exclude_mutation=None) -> Diagnosis:
    """response: {"variable_definition"?, "equation"} | {"steps": [...]} | {"final_answer_text"}."""
    vd = response.get("variable_definition")
    if response.get("steps"):
        return diagnose_steps(question, response["steps"], vd)
    if response.get("equation"):
        return diagnose_modelling(question, response["equation"], vd, exclude_mutation=exclude_mutation)
    if "final_answer_text" in response:
        return diagnose_final_answer(question, response["final_answer_text"], exclude_mutation=exclude_mutation)
    return Diagnosis(status=INSUFFICIENT, state="S1", evidence_level="D",
                     evidence="没有可诊断的内容", follow_up=ASK_WORKING)
