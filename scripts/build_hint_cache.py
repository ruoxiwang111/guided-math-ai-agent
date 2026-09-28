"""
Pre-generate learner-aware hint templates for the question bank (wording mode "cached").

Run from the project root (needs DEEPSEEK_API_KEY):
    python scripts/build_hint_cache.py                    # all questions, only missing entries
    python scripts/build_hint_cache.py --questions Q01,Q05
    python scripts/build_hint_cache.py --overwrite        # regenerate pending entries too
    python scripts/build_hint_cache.py --export-md eval/hint_cache_review.md   # review sheet only

What it generates
    For every bank question × state × error category (× E4 subtype) × hint level 1–3, one
    hint TEMPLATE that may contain slots filled at run time with the learner's own text:
        S2  {learner_equation} {learner_definition} {acknowledge}
        S3  {learner_line} {prev_line} {line_no} {acknowledge}
        S1/S4 {acknowledge}
    Level 4 is not cached (explanations are generated live or taken from the template).

Checks before an entry is stored
    - only slots allowed for its state;
    - filled with a realistic sample (from the bank's own mutation of that category, where
      one exists) and passed through the same leakage check the tutor uses at run time.
    Failed entries are retried once and otherwise skipped (listed at the end).

Review
    Every new entry has review_status = "pending". Set it to "approved" or "rejected" in
    data/hint_cache.json (or edit the text). Rejected entries are never shown; set
    CACHE_REQUIRE_APPROVED=1 to show approved entries only. Approved/edited entries are never
    overwritten by this script.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.llm_client import (  # noqa: E402
    DEFAULT_CACHE, SLOT_RE, LLMError, _template_hint, cache_key, check_leakage, default_backend, fill_slots,
)
from core.state_manager import TutorSession  # noqa: E402

LEVELS = (1, 2, 3)
STATE_SLOTS = {
    "S1": {"acknowledge"},
    "S2": {"learner_equation", "learner_definition", "acknowledge"},
    "S3": {"learner_line", "prev_line", "line_no", "acknowledge"},
    "S4": {"acknowledge"},
}
LEVEL_RULES = {
    1: "等级1：只用一个问题把学生的注意力引到出问题的地方；不给完整方程、不给答案、不给关键中间结果。",
    2: "等级2：用文字点出相关的数量关系或运算规则；不给完整方程、不给答案。",
    3: "等级3：可以指出下一步该做什么运算，但不给运算结果或最终答案。",
}

CACHE_SYSTEM = """你是一名初中数学老师，要为一道题预先写好一条“可复用的提示模板”。
这条模板会在学生犯某一类错误时显示，系统会把花括号里的槽位替换成学生本人写的内容。
要求：
- 1–2 句简体中文，自然、具体，像老师当面说话；要贴合这道题的数量和情境，不要写放在任何题都成立的空话。
- 必须使用至少一个“可用槽位”来引用学生写的内容（S1、S4 可以只用 {acknowledge} 或不用槽位）。
- {acknowledge} 会被替换成对学生做对部分的肯定，放在句首；没有可肯定的内容时它会被去掉，句子仍要通顺。
- 严格遵守提示等级规则；不要出现题目答案的数值；不要引入题目中没有的条件；不要出现数学错误。
只输出 JSON：{"template": "..."}"""


def combos(q):
    out = [("S1", "E1", None)]
    for cat in ("E2", "E3", None):
        out.append(("S2", cat, None))
    for sub in q.get("e4_patterns", []):
        out.append(("S2", "E4", sub))
    out += [("S3", "E6", None), ("S3", "E7", None), ("S4", "E5", None)]
    return [(st, cat, sub, lv) for st, cat, sub in out for lv in LEVELS]


def sample_context(q, state, cat, sub):
    """Realistic learner input for the sample check: the bank's own mutation where possible."""
    muts = [m for m in q["mutations"] if m["error"] == (sub or cat)] or \
           [m for m in q["mutations"] if m["error"].split("-")[0] == cat]
    if state == "S2":
        m = next((m for m in muts if m["layer"] == "modelling"), None)
        eq = m["equation"] if m else "x + 1 = 2"
        vd = (m or {}).get("variable_definition", q["variable_definition"])
        return {"learner_input": {"variable_definition": vd, "equation": eq},
                "learner_equation": eq, "learner_definition": vd, "acknowledge": ["这个设法没问题"]}
    if state == "S3":
        m = next((m for m in muts if m["layer"] == "execution"), None)
        steps = m["steps"] if m else [q["equation"], "x = 1"]
        k = m["first_invalid_step"] if m else 2
        return {"learner_input": {"steps": steps}, "learner_line": steps[k - 1],
                "prev_line": steps[k - 2] if k >= 2 else steps[0], "line_no": k,
                "acknowledge": ["前面几行都是对的"]}
    return {"learner_input": {}, "acknowledge": ["数值算对了"]}


def base_spec(q, level):
    s = TutorSession(q)
    spec = s._spec(level=level)
    spec["relationship"] = q.get("relationship")
    return spec


def validate(template, q, state, cat, sub, level):
    used = set(SLOT_RE.findall(template))
    if not used <= STATE_SLOTS[state]:
        return f"slots not allowed in {state}: {sorted(used - STATE_SLOTS[state])}"
    if state in ("S2", "S3") and not (used - {"acknowledge"}):
        return "does not quote the learner (no learner slot)"
    spec = {**base_spec(q, level), "category": cat, "error_subtype": sub, **sample_context(q, state, cat, sub)}
    filled = fill_slots(template, spec)
    if filled is None:
        return "slot could not be filled with the sample"
    leaks = check_leakage(filled, spec)
    return f"leakage {leaks} in sample: {filled}" if leaks else None


def user_prompt(q, state, cat, sub, level):
    spec = {**base_spec(q, level), "category": cat, "error_subtype": sub}
    return json.dumps({
        "题目": q["question"],
        "标准设法": q["variable_definition"],
        "数量关系": q.get("relationship"),
        "阶段": state,
        "错误类型": cat or "未确定（给中性提示）",
        "E4 细分": sub,
        "提示等级": level,
        "等级规则": LEVEL_RULES[level],
        "可用槽位": sorted(STATE_SLOTS[state]),
        "参考提示（教学意图，不要照抄）": _template_hint(cat, level, {**spec, "first_invalid_step": 2 if state == "S3" else None}),
    }, ensure_ascii=False, indent=2)


def export_md(entries, path):
    lines = ["# Hint cache review", "", "Set review_status in data/hint_cache.json to approved / rejected.", ""]
    for k in sorted(entries):
        e = entries[k]
        lines.append(f"- **{k}** [{e.get('review_status', 'pending')}] {e['text']}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✓ review sheet: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", default=str(ROOT / "data" / "question_bank.json"))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--questions", default="")
    ap.add_argument("--overwrite", action="store_true", help="regenerate pending entries")
    ap.add_argument("--export-md", default="")
    args = ap.parse_args()

    cache_path = Path(args.cache)
    data = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {"version": "1.0", "entries": {}}
    entries = data.setdefault("entries", {})

    if args.export_md and not args.questions and not args.overwrite:
        export_md(entries, args.export_md)
        return

    backend = default_backend()
    if backend is None:
        sys.exit("✗ DEEPSEEK_API_KEY not found (environment or .env) – cannot generate the cache")

    bank = json.loads(Path(args.bank).read_text(encoding="utf-8"))
    wanted = {x.strip() for x in args.questions.split(",") if x.strip()}
    todo = []
    for q in bank["questions"]:
        if wanted and q["question_id"] not in wanted:
            continue
        for state, cat, sub, level in combos(q):
            key = cache_key(q["question_id"], state, cat, sub, level)
            e = entries.get(key)
            if e and (e.get("review_status") in ("approved", "rejected") or e.get("edited") or not args.overwrite):
                continue
            todo.append((q, state, cat, sub, level, key))

    print(f"{len(todo)} entries to generate with {backend.describe()}")
    failed = []
    for i, (q, state, cat, sub, level, key) in enumerate(todo, 1):
        reason = None
        for _ in range(2):
            try:
                template = json.loads(backend.complete(CACHE_SYSTEM, user_prompt(q, state, cat, sub, level)))["template"].strip()
            except (LLMError, json.JSONDecodeError, KeyError, TypeError) as exc:
                reason = f"llm error: {exc}"
                continue
            reason = validate(template, q, state, cat, sub, level)
            if reason is None:
                entries[key] = {"text": template, "review_status": "pending",
                                "model": backend.describe(), "generated": date.today().isoformat()}
                break
        if reason:
            failed.append((key, reason))
        print(f"  [{i}/{len(todo)}] {key} {'✓' if not reason else '✗ ' + reason[:60]}")
        if i % 20 == 0:                                          # save progress
            cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    data["question_bank_version"] = bank.get("version")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ wrote {cache_path}: {len(entries)} entries ({len(todo) - len(failed)} new, {len(failed)} failed)")
    for key, reason in failed:
        print(f"  ✗ {key}: {reason}")
    if args.export_md:
        export_md(entries, args.export_md)


if __name__ == "__main__":
    main()