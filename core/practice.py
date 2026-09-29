"""
core/practice.py — independent attempts without any feedback (D3 learning / transfer tests).

The learner writes the whole solution at once (definition, equation, steps, final answer); the
system gives NO hint while they work. Afterwards every layer is diagnosed separately, with the
same deterministic diagnosis as Guided Mode:

    modelling   the equation against the reference model(s)           diagnose_modelling
    execution   the steps against the learner's OWN equation          diagnose_steps
                (a wrong equation solved correctly is a modelling error only)
    answer      the final answer against the reference answer        diagnose_final_answer

Nothing here is LLM output, so a D3 result can be traced back to the rule that produced it.

Public API
    grade_attempt(question, definition, equation, steps, final_answer) -> dict
"""
from __future__ import annotations

from core import diagnosis as dx
from core import math_checker as mc
from core.normalizer import normalize_line


def _error(layer, d, **extra):
    return {"layer": layer, "status": d.status, "category": d.primary_error, "subtype": d.error_subtype,
            "rule": d.rule, "candidates": d.candidates, "line": d.first_invalid_step, "evidence": d.evidence,
            **extra}


def grade_attempt(question: dict, definition: str, equation: str, steps: str, final_answer: str) -> dict:
    definition, equation = (definition or "").strip(), (equation or "").strip()
    steps, final_answer = (steps or "").strip(), (final_answer or "").strip()
    errors = []

    # ---- modelling
    if equation:
        dm = dx.diagnose_modelling(question, equation, definition or None)
        model_correct = dm.status == dx.NO_ERROR
        if not model_correct:
            errors.append(_error("modelling", dm, **({"side": dm.details} if dm.rule == "one_side_wrong" else {})))
    else:
        dm, model_correct = None, False
        errors.append({"layer": "modelling", "status": dx.INSUFFICIENT, "category": None, "rule": "no_equation"})

    # ---- execution, against the learner's own equation
    nl = normalize_line(equation) if equation else None
    own = nl.normalized if nl is not None and nl.ok and nl.kind == "equation" else None
    execution_correct, final_value = None, None
    if steps and own:
        own_solutions = mc.solution_set(own)
        view = dict(question, equation=own, answer=str(next(iter(own_solutions.values)))
                    if own_solutions and own_solutions.kind == mc.UNIQUE else question["answer"])
        de = dx.diagnose_steps(view, steps, definition or None, start_equation=equation)
        execution_correct = de.status == dx.NO_ERROR
        if execution_correct:
            lines = steps.splitlines()
            check = mc.check_steps(steps, reference_equation=own)
            if check.status != mc.ALL_VALID:
                check = mc.check_steps([equation] + lines, reference_equation=own)
            final_value = check.final_value
            if not check.final_matches_reference:
                execution_correct = False
                errors.append({"layer": "execution", "status": dx.INSUFFICIENT, "category": None,
                               "rule": "not_solved_to_x"})
        else:
            errors.append(_error("execution", de))
    elif not steps:
        errors.append({"layer": "execution", "status": dx.INSUFFICIENT, "category": None, "rule": "no_steps"})

    # ---- final answer
    if final_answer:
        da = dx.diagnose_final_answer(question, final_answer)
        answer_correct = da.status == dx.NO_ERROR
        if not answer_correct:
            errors.append(_error("answer", da))
    else:
        answer_correct = False
        errors.append({"layer": "answer", "status": dx.INSUFFICIENT, "category": None, "rule": "no_answer"})

    return {
        "model_correct": model_correct,
        "execution_correct": execution_correct,
        "answer_correct": answer_correct,
        "fully_correct": bool(model_correct and execution_correct and answer_correct),
        "final_value": str(final_value) if final_value is not None else None,
        "errors": errors,
        "error_types": sorted({e["category"] for e in errors if e.get("category")}),
        "error_rules": sorted({e["rule"] for e in errors if e.get("rule")}),
    }


LAYER_NAMES = {"modelling": "列方程", "execution": "解方程", "answer": "写答案"}
RULE_WORDS = {
    "transposition_sign": "移项没有变号", "distribute_first_term_only": "去括号时只乘了第一项",
    "distribute_second_sign": "去括号时符号出错", "distribute_sign_flipped": "去括号时符号出错",
    "operation_on_one_side": "只对等式一边做了运算", "add_instead_of_divide": "系数化为 1 用错了运算",
    "subtract_instead_of_divide": "系数化为 1 用错了运算", "multiply_instead_of_divide": "系数化为 1 用错了运算",
    "inverted_division": "系数化为 1 时除反了", "one_side_wrong": "方程有一边和题意对不上",
    "unmatched_relationship": "方程和题意对不上", "no_equation": "没有写方程", "no_steps": "没有写解方程过程",
    "no_answer": "没有写最终答案", "not_solved_to_x": "还没有解出 x",
    "answer_incomplete": "答案少写了一部分", "answer_unit_missing": "答案少了单位",
}


def learner_view(result: dict) -> list[str]:
    """Plain-language lines for the learner after submitting (no hints, only what went wrong where)."""
    out = [f"列方程：{'✓' if result['model_correct'] else '✗'}",
           f"解方程：{'✓' if result['execution_correct'] else ('—' if result['execution_correct'] is None else '✗')}",
           f"写答案：{'✓' if result['answer_correct'] else '✗'}"]
    for e in result["errors"]:
        word = RULE_WORDS.get(e.get("rule"))
        if word:
            where = f"第{e['line']}行" if e.get("line") else ""
            out.append(f"· {LAYER_NAMES.get(e['layer'], e['layer'])}{('（' + where + '）') if where else ''}：{word}")
    return out
