"""
core/review.py — end-of-problem review (总结复盘), built only from the session's own record.

Deterministic, like the rest of the decision layer: every line comes from what the learner
actually did (event log), the accepted model, and the question's structure. No LLM wording,
so the review can never contradict the checker or invent an error that was not diagnosed.

Sections
    solution_path   the whole solution in the learner's own model: 求什么 → 设 → 关系 → 方程 → 解 → 答
    highlights      what went well (independent stages, self-correction, questions, own checking)
    journey         per stage, in plain words: how it went and what went wrong
    takeaways       ≤ 3 points, one per diagnosed error type (the rule where known), else the
                    problem's key relationship
    next_time       concrete habits for the next problem
    self_summary    optional one-sentence summary written by the learner (generation, not reading)

Usage
    review = build_review(session, target="长方形的长和宽")
"""
from __future__ import annotations

import re

STAGE_LABELS = {"S1": "理解题意", "S2": "设未知数、列方程", "S3": "解方程", "S4": "写答案并检验"}

ERROR_PLAIN = {
    "E1": "把要求的量看错了",
    "E2": "设的 x 和方程里的 x 对不上",
    "E3": "数量关系列错了",
    "E4": "关键词（多/少/倍/打折等）翻译错了",
    "E5": "答案的单位或含义不对",
    "E6": "计算出错",
    "E7": "方程变形出错",
}

E4_PHRASES = {
    "E4-01": "“甲比乙多……”", "E4-02": "“甲比乙少……”", "E4-03": "“比原来增加了……%”",
    "E4-04": "“增加到原来的……%”", "E4-05": "“增加到……”", "E4-06": "“打……折”",
    "E4-07": "“甲是乙的……倍”", "E4-08": "“比原来少了几分之几”",
}

E7_RULE_TAKEAWAY = {
    "transposition_sign": "移项要变号：一项从等号一边移到另一边，符号要改变。",
    "operation_on_one_side": "等式两边要做同样的运算，只改一边等式就不成立了。",
    "distribute_first_term_only": "去括号时，括号前的数要乘括号里的每一项。",
    "distribute_second_sign": "括号前是负号时，去括号后括号里每一项都要变号。",
    "distribute_sign_flipped": "括号前是负号时，去括号后括号里每一项都要变号。",
    "add_instead_of_divide": "系数化为 1：ax = b 时两边同时除以 a，得到 x = b ÷ a。",
    "subtract_instead_of_divide": "系数化为 1：ax = b 时两边同时除以 a，得到 x = b ÷ a。",
    "multiply_instead_of_divide": "系数化为 1：ax = b 时两边同时除以 a，得到 x = b ÷ a。",
    "inverted_division": "系数化为 1：ax = b 时 x = b ÷ a，不是 a ÷ b。",
}

# problem type families: used to name the knowledge point and to find a similar problem
TOPIC_FAMILIES = [
    ("年龄问题", ["年龄", "岁"]),
    ("行程问题", ["行程", "路程", "相遇", "追及", "往返", "速度", "航行"]),
    ("工程问题", ["工程", "工作效率", "工作量", "合作", "效率"]),
    ("百分比与折扣问题", ["打折", "折扣", "涨价", "降价", "百分", "利润", "利率", "增长", "优惠", "原价"]),
    ("几何图形问题", ["周长", "面积", "长方形", "正方形", "三角形", "图形"]),
    ("购物与价格问题", ["价格", "购买", "单价", "文具", "买"]),
    ("分配与调配问题", ["分配", "分组", "人数", "调配", "转移", "调运"]),
    ("数字与倍数问题", ["数字", "一个数", "某数", "倍数", "和差"]),
]

WEAK_POINT = {
    "E1": "审题：确定题目要求什么",
    "E2": "设未知数：x 表示的量要清楚",
    "E5": "答案检验：单位和实际意义",
    "E6": "计算的准确性",
}
E7_WEAK_POINT = {
    "transposition_sign": "解方程：移项要变号",
    "operation_on_one_side": "解方程：等式的性质（两边同做）",
    "distribute_first_term_only": "解方程：去括号",
    "distribute_second_sign": "解方程：去括号（括号前是负号）",
    "distribute_sign_flipped": "解方程：去括号（括号前是负号）",
    "add_instead_of_divide": "解方程：系数化为 1",
    "subtract_instead_of_divide": "解方程：系数化为 1",
    "multiply_instead_of_divide": "解方程：系数化为 1",
    "inverted_division": "解方程：系数化为 1",
}
ONE_PROBLEM_NOTE = "只凭这一道题还不能说明这些知识点不熟练；做同类题时如果再出现，才需要重点复习。"


def topic_family(topic: str | None) -> str | None:
    """'往返路程' → '行程问题'; unknown topics are returned as they are."""
    if not topic:
        return None
    for family, words in TOPIC_FAMILIES:
        if any(w in topic for w in words):
            return family
    return topic


def _needs_transposition(eq: str) -> bool:
    """x on both sides, or a constant next to the x terms (0.8*x = 160 needs no 移项)."""
    from sympy import expand, symbols, sympify
    x = symbols("x")
    try:
        lhs, rhs = (expand(sympify(side)) for side in eq.split("="))
    except Exception:  # noqa: BLE001
        return True
    lx, rx = lhs.has(x), rhs.has(x)
    if lx and rx:
        return True
    side = lhs if lx else rhs
    return side.as_independent(x, as_Add=True)[0] != 0


def knowledge_points(q) -> list[str]:
    """What this problem practises (from its structure, not from the learner)."""
    family = topic_family(q.get("topic"))
    eq = str(q.get("equation", ""))
    solving = (["移项"] if _needs_transposition(eq) else []) + \
        (["合并同类项"] if len(re.findall(r"[xX]", eq)) > 1 else [])
    if "(" in eq:
        solving.insert(0, "去括号")
    if "/" in eq or re.search(r"\d\.\d", eq):
        solving.insert(0, "去分母或小数系数")
    solving.append("系数化为 1")
    points = [f"列一元一次方程解应用题（{family}）" if family else "列一元一次方程解应用题",
              f"解一元一次方程：{'、'.join(solving)}"]
    for pid in q.get("e4_patterns") or []:
        if pid in E4_PHRASES:
            points.append(f"关键词转式子：{E4_PHRASES[pid]}")
    return points


def _weak_point(category, subtype, rule, family):
    if category == "E7":
        return E7_WEAK_POINT.get(rule, "解方程：等式变形")
    if category == "E4":
        return f"关键词转式子：{E4_PHRASES[subtype]}" if subtype in E4_PHRASES else "关键词转式子"
    if category == "E3":
        return f"找等量关系（{family}）" if family else "找等量关系"
    return WEAK_POINT.get(category)


SELF_SUMMARY_PROMPT = "最后，用一句话写下：这道题的关键是什么？（写下来比看一遍记得更牢）"


def _pretty(eq) -> str:
    eq = re.sub(r"(\d|\))\s*\*\s*(?=[xX(])", r"\1", str(eq))
    return eq.replace("*", "×")


def _diagnosed_errors(session):
    """[(state, category, subtype, rule, line)] for every DIAGNOSED error, in order."""
    out = []
    for e in session.events:
        if e.get("event") == "diagnosis" and e.get("diagnosis_status") == "diagnosed" and e.get("diagnosed_error"):
            out.append((e["state"], e["diagnosed_error"], e.get("error_subtype"), e.get("rule"),
                        e.get("first_invalid_step")))
    return out


LOCATED_RULES = ("one_side_wrong", "unmatched_relationship")


def _located_errors(session):
    """
    Modelling errors that were located but deliberately not labelled E2/E3/E4 (uncertain).
    They are real mistakes the learner corrected, so the review must mention them too.
    [(state, text)]
    """
    out, seen = [], set()
    for e in session.events:
        if e.get("event") == "diagnosis" and e.get("diagnosis_status") == "uncertain" \
                and e.get("rule") in LOCATED_RULES and e["state"] not in seen:
            seen.add(e["state"])
            d = getattr(session, "_diag_by_state", {}).get(e["state"])
            side = d.details if d is not None and d.rule == "one_side_wrong" else {}
            if side.get("wrong_side_text"):
                text = f"方程{side['wrong_side_name']}“{side['wrong_side_text']}”和题意对不上" + \
                       ("（倍数关系少了括号）" if side.get("missing_brackets") else "")
            else:
                text = "方程和题意对不上"
            out.append((e["state"], text))
    return out


def _takeaway(category, subtype, rule, relationship):
    if category == "E7":
        return E7_RULE_TAKEAWAY.get(rule, "每一步变形都要保证等式两边仍然相等，可以把上一行和这一行都代入同一个数检查。")
    if category == "E4":
        phrase = E4_PHRASES.get(subtype)
        return (f"遇到{phrase}这样的说法，先用自己的话说清楚：谁多谁少、是变化的量还是变化后的量。"
                if phrase else "遇到“多/少/倍/打折”这类关键词，先用自己的话说清楚它的意思，再写成式子。")
    if category == "E3":
        return (f"这道题的等量关系是：{relationship}。先用文字写出关系，再翻译成方程。"
                if relationship else "列方程前先用文字写出“什么等于什么”，再翻译成式子。")
    return {
        "E1": "读题时先圈出最后一句问的是什么，别把已知量当成要求的量。",
        "E2": "设 x 时写清楚它表示题目里的哪个量（带单位），方程里每个 x 都要是这个量。",
        "E5": "写答案时回到题目：问的是什么量、用什么单位、结果合不合实际。",
        "E6": "算完一步，可以把结果代回上一行检查一下。",
    }.get(category)


def _value_of(expr: str, x):
    from sympy import nsimplify
    from core import math_checker as mc
    from core.normalizer import normalize_line
    nl = normalize_line(str(expr))
    if not nl.ok or nl.kind != "expression":
        return None
    v = nsimplify(mc._expr(nl.normalized).subs(mc.X, nsimplify(x, rational=True)), rational=True)
    return str(v) if v.q == 1 else f"{v.p}/{v.q}"


OP_WORD = {"==": "等于", ">": "大于", "<": "小于", ">=": "不小于", "<=": "不大于"}


def verification_walkthrough(q, x) -> list[str]:
    """
    Each condition with x substituted, in words:
      '5年后小明是小红的2倍：3x+5 = 20，2(x+5) = 20，两边相等 ✓'
      '宽为正：x = 5，大于 0 ✓'
    """
    from sympy import S
    if x is None:
        return []
    out = []
    for c in q.get("verification_conditions", []):
        desc, op = c["description"], c.get("op", "==")
        try:
            lv = _value_of(c["lhs"], x)
            rv = _value_of(c.get("rhs", "0"), x) if op != "integer" else None
        except Exception:  # noqa: BLE001
            lv = rv = None
        if lv is None or (op != "integer" and rv is None):
            out.append(desc)
            continue
        left = f"{_pretty(c['lhs'])} = {lv}"
        if op == "integer":
            ok = S(lv).is_integer
            out.append(f"{desc}：{left}，是整数 {'✓' if ok else '✗'}")
            continue
        ok = {"==": S(lv) == S(rv), ">": S(lv) > S(rv), "<": S(lv) < S(rv),
              ">=": S(lv) >= S(rv), "<=": S(lv) <= S(rv)}[op]
        rhs_expr = _pretty(c.get("rhs", ""))
        mark = "✓" if ok else "✗"
        if rhs_expr.replace(" ", "") == str(rv):              # right side is just a number
            out.append(f"{desc}：{left}，{OP_WORD[op]} {rv} {mark}")
        elif op == "==":
            out.append(f"{desc}：{left}，{rhs_expr} = {rv}，两边相等 {mark}")
        else:
            out.append(f"{desc}：{left}，{rhs_expr} = {rv}，{lv} {op} {rv} {mark}")
    return out


def _stage_status(rec) -> str:
    if rec.revealed:
        return "主动查看了参考" if getattr(rec, "reveal_requested", False) else "看了参考步骤"
    if rec.errors:
        return "在提示下改正"
    if rec.max_hint_level > 0:
        return "在提示下完成"
    return "独立完成"          # clarification requests (e.g. "写出方程") are not hints


def build_review(session, target: str | None = None) -> dict:
    q = session.q
    recs = session.records
    errors = _diagnosed_errors(session)
    located = _located_errors(session)
    relationship = q.get("relationship")

    # ---- the whole solution, in the learner's accepted model
    x_val = session.final_x if session.final_x is not None else session.model.get("answer")
    equation = session.model.get("learner_equation") or _pretty(session.model["equation"])
    s4 = recs["S4"]
    answers = [e["response"].get("final_answer_text") for e in session.events
               if e.get("event") == "learner_response" and e.get("state") == "S4"]
    answer = answers[-1] if answers and s4.passed and not s4.revealed else q.get("final_answer_text")
    solution_path = [
        {"label": "题目要求", "text": target} if target else None,
        {"label": "设未知数", "text": session.model["variable_definition"]},
        {"label": "等量关系", "text": relationship} if relationship else None,
        {"label": "列方程", "text": equation},
        {"label": "解得", "text": f"x = {x_val}"},
        {"label": "答", "text": answer},
    ]
    solution_path = [p for p in solution_path if p and p["text"]]

    # ---- how each stage went
    journey = []
    for s, label in STAGE_LABELS.items():
        rec = recs[s]
        stage_errors = [(c, sub, rule, line) for st, c, sub, rule, line in errors if st == s]
        detail = []
        for c, _sub, _rule, line in stage_errors:
            where = f"第{line}行" if line else ""
            detail.append(f"{where}{ERROR_PLAIN.get(c, c)}")
        detail += [text for st, text in located if st == s]
        journey.append({"state": s, "label": label, "status": _stage_status(rec),
                        "attempts": rec.attempts, "max_hint_level": rec.max_hint_level,
                        "errors": list(dict.fromkeys(detail))})

    # ---- what went well
    highlights = []
    # "独立完成" here means no error, no hint, nothing revealed. (StateRecord.independent also
    # allows one level-1 hint, V1_design §24 — right for mastery, but reads as a contradiction
    # next to "在提示下改正" in a review shown to the learner.)
    independent = [STAGE_LABELS[s] for s in STAGE_LABELS
                   if recs[s].passed and not recs[s].revealed and not recs[s].errors and recs[s].max_hint_level == 0
                   and not any(st == s for st, _ in located)]
    if len(independent) == 4:
        highlights.append("四个环节都独立完成了！")
    elif independent:
        highlights.append(f"独立完成：{'、'.join(independent)}")
    corrected = [STAGE_LABELS[s] for s in STAGE_LABELS
                 if (recs[s].errors or any(st == s for st, _ in located)) and recs[s].passed and not recs[s].revealed]
    if corrected:
        highlights.append(f"出错后在提示下自己改正了：{'、'.join(corrected)}")
    active = any(e.get("active_verification") for e in session.events if e.get("event") == "verification")
    if active:
        highlights.append("没等提醒就主动检验了答案")
    if session.learner_questions:
        highlights.append(f"遇到不懂主动提问了 {session.learner_questions} 次")

    # ---- takeaways: one per distinct diagnosed error type, else the key relationship
    takeaways, seen = [], set()
    for _st, c, sub, rule, _line in errors:
        key = (c, rule if c == "E7" else sub if c == "E4" else None)
        if key in seen:
            continue
        seen.add(key)
        t = _takeaway(c, sub, rule, relationship)
        if t and t not in takeaways:
            takeaways.append(t)
    if located:
        t = _takeaway("E3", None, None, relationship)
        if t and t not in takeaways:
            takeaways.append(t)
    if not takeaways and relationship:
        takeaways.append(f"这类题的关键是找准等量关系：{relationship}。")
    takeaways = takeaways[:3]

    # ---- knowledge points of the problem, and the ones THIS attempt showed trouble with
    family = topic_family(q.get("topic"))
    weak = []
    for _st, c, sub, rule, _line in errors:
        w = _weak_point(c, sub, rule, family)
        if w and w not in weak:
            weak.append(w)
    if located:
        w = _weak_point("E3", None, None, family)
        if w not in weak:
            weak.append(w)

    # ---- next time
    next_time = []
    revealed = [STAGE_LABELS[s] for s in STAGE_LABELS if recs[s].revealed]
    if revealed:
        next_time.append(f"{'、'.join(revealed)}看了参考，建议过一两天不看提示，把这道题再独立做一遍。")
    if not active:
        next_time.append("写完答案先自己代回原题检查一遍，再提交。")
    if any(recs[s].max_hint_level >= 3 for s in STAGE_LABELS) and not revealed:
        next_time.append("这道题用到了较多提示，可以找一道同类型的题再练一次。")

    return {
        "question_id": q["question_id"],
        "solution_path": solution_path,
        "topic_family": family,
        "knowledge_points": knowledge_points(q),
        "weak_points": weak,
        "weak_points_note": ONE_PROBLEM_NOTE if weak else None,
        "highlights": highlights,
        "journey": journey,
        "takeaways": takeaways,
        "next_time": next_time,
        "self_summary_prompt": SELF_SUMMARY_PROMPT,
        "self_summary": getattr(session, "self_summary", None),
    }
