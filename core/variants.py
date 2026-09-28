"""
core/variants.py — "练一道同类题" after a finished problem.

Order
    1. the question bank: another item of the same problem-type family (core/review.topic_family),
       not done yet in this browser session — teacher-reviewed, no LLM needed
    2. otherwise a NEW problem written by the LLM, and then treated exactly like any photographed
       problem: structure extraction + SymPy checks + an independent solve must agree
       (core/structure.extract_structure). It is only offered when that is "consistent" AND its
       type family matches the original. The generator never grades anything.

Public API
    bank_similar(question, bank_questions, exclude=())      -> dict | None
    generate_similar(question, backend, max_tries=2)          -> (Extraction | None, [attempt logs])
"""
from __future__ import annotations

import json

from core.review import topic_family
from core.structure import extract_structure

VARIANT_PROMPT_VERSION = "variant-v1"

VARIANT_SYSTEM = """你是初中数学老师，要为学生出一道“同类题”用来巩固。
要求：
- 与原题属于同一类型（数量关系的结构相同），但换一个生活情境和人物，换掉所有数字；
- 只用一个未知数、列一元一次方程就能解；题目信息完整、没有歧义、只问一个问题（可以要求写出几个相关的量）；
- 数字简单，答案是正整数或简单的小数，并且符合实际（人数、件数是整数，价格、路程为正数）；
- 不要给出答案、方程或提示。
只输出 JSON：{"question": "题目文字", "topic": "题型（例如 行程问题-相遇）"}"""


def bank_similar(question: dict, bank_questions, exclude=()) -> dict | None:
    """Another bank item of the same family; prefers the same difficulty. None if there is none."""
    family = topic_family(question.get("topic"))
    if not family:
        return None
    skip = set(exclude) | {question.get("question_id")}
    same = [q for q in bank_questions if q["question_id"] not in skip and topic_family(q.get("topic")) == family]
    if not same:
        return None
    same.sort(key=lambda q: (q.get("difficulty") != question.get("difficulty"), q["question_id"]))
    return same[0]


def generate_similar(question: dict, backend, max_tries: int = 2):
    """
    Returns (usable Extraction | None, attempts). Each attempt records the generated text and
    why it was rejected, so bad generations are visible in data/extracted/ for review.
    """
    attempts = []
    if backend is None:
        return None, [{"error": "no LLM backend"}]
    family = topic_family(question.get("topic"))
    for _ in range(max_tries):
        try:
            gen = json.loads(backend.complete(VARIANT_SYSTEM, json.dumps(
                {"原题": question["question"], "原题题型": question.get("topic") or family},
                ensure_ascii=False)))
            text = (gen.get("question") or "").strip()
        except Exception as exc:  # noqa: BLE001
            attempts.append({"error": f"generation failed: {exc}"})
            continue
        if not text or text == question["question"].strip():
            attempts.append({"text": text, "rejected": "empty or identical to the original"})
            continue
        ex = extract_structure(text, backend)
        new_family = topic_family((ex.question or {}).get("topic") or gen.get("topic"))
        if not ex.usable:
            attempts.append({"text": text, "rejected": f"not guidable (scope={ex.scope}, consistency={ex.consistency})"})
            continue
        if family and new_family != family:
            attempts.append({"text": text, "rejected": f"different type: {new_family} ≠ {family}"})
            continue
        ex.question["source"] = "generated"
        ex.question["generated_from"] = question.get("question_id")
        ex.question["extraction"]["variant_prompt_version"] = VARIANT_PROMPT_VERSION
        attempts.append({"text": text, "accepted": True})
        return ex, attempts
    return None, attempts
