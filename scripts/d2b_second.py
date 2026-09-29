"""
D2b — second, blind annotator (evaluation_plan §5.1: at least 20% of D2b, blind to the first
annotation and to system outputs; disagreements recorded in eval/annotation_disagreements.md).

Run from the project root, after d2b_import.py:
    python scripts/d2b_second.py export              # eval/d2b_second_annotator.xlsx, a stratified 20% sample
    python scripts/d2b_second.py export --fraction 0.3
    (send the file; the second person fills the label columns; put the returned file back in eval/)
    python scripts/d2b_second.py compare             # agreement + disagreement record

The exported workbook holds only the learner responses: no labels, no evidence, no system output.
`compare` never changes the first annotation. It appends the disagreements to
eval/annotation_disagreements.md, with an empty "resolution" column to fill in after discussion,
and records which cases were second-annotated in eval/d2b_second_annotation.json.
"""
import argparse
import json
import math
import random
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d2b_io as io  # noqa: E402
from d2b_template import build  # noqa: E402

SEED = 20260930
RESPONSE_KEYS = ["case_id", "question_id", "layer", "variable_definition", "equation", "steps", "final_answer_text"]
LABEL_KEYS = ["reference_status", "primary_error", "error_subtype", "secondary_errors", "first_invalid_step",
              "evidence", "note"]
SECOND_COLUMNS = [c for c in io.COLUMNS if c[0] in RESPONSE_KEYS + LABEL_KEYS]

SECOND_GUIDE = [
    ("请你独立标注", ""),
    ("1", "cases 表里每一行是一个初中生对某道题的作答（题目见“题目”表）。前几列是作答，黄色列由你填写。"),
    ("2", "请只根据作答本身判断，不要和第一位标注人商量，也不要运行系统。"),
    ("3", "reference_status：correct（完全正确，等价写法也算）/ incorrect（有明确错误）/ uncertain（两种解释都说得通）/ not_assessable（看不懂）。"),
    ("4", "incorrect 时填 primary_error（E1–E7，定义见下）；有第二个独立错误填 secondary_errors；解方程过程有错时填 first_invalid_step（steps 里第几行，从 1 数）。"),
    ("5", "evidence：作答里哪一处让你这么判断（摘录原文即可）。"),
    ("", ""),
    ("错误类别", ""),
    ("E1", "没读懂题目要求什么（求错了量）"),
    ("E2", "未知数定义不清或前后不一致"),
    ("E3", "数量关系错误"),
    ("E4", "中文表述翻译成数学时的固定错误：比…多/少方向反、增加了20%与增加到120%混淆、打八折当成减0.8、几倍关系写反、少了三分之一写成1/3x 等"),
    ("E5", "单位或数量级错误"),
    ("E6", "算术计算错误"),
    ("E7", "代数变形或符号错误（移项不变号、去括号只乘第一项、只对一边运算等）"),
]


def sample(cases, fraction, seed=SEED):
    n = max(1, math.ceil(fraction * len(cases)))
    by = {}
    for c in sorted(cases, key=lambda c: c["case_id"]):
        by.setdefault(io.stratum(c), []).append(c)
    picked = []
    for name, group in sorted(by.items()):
        random.Random(f"{seed}:{name}").shuffle(group)
        picked += group[:max(1, round(fraction * len(group)))]
    rest = [c for c in cases if c not in picked]
    random.Random(seed).shuffle(rest)
    picked += rest[:max(0, n - len(picked))]
    return sorted(picked, key=lambda c: c["case_id"])


def response_row(c):
    r = c["learner_response"]
    return {"case_id": c["case_id"], "question_id": c["question_id"], "layer": c["layer"],
            "variable_definition": r.get("variable_definition", ""), "equation": r.get("equation", ""),
            "steps": "\n".join(r.get("steps", [])), "final_answer_text": r.get("final_answer_text", "")}


def kappa(a, b):
    """Cohen's kappa for two label lists."""
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def compare(first: dict, second_rows: list[dict]):
    pairs, diffs = [], []
    for r in second_rows:
        f = first.get(r["case_id"])
        if f is None or not r.get("reference_status"):
            continue
        s = {"reference_status": r["reference_status"], "primary_error": r.get("primary_error", "").upper() or None,
             "first_invalid_step": int(r["first_invalid_step"]) if r.get("first_invalid_step", "").isdigit() else None,
             "secondary_errors": io.parse_codes(r.get("secondary_errors", "")), "evidence": r.get("evidence", "")}
        pairs.append((f, s))
        fields = [k for k in ("reference_status", "primary_error", "first_invalid_step") if f.get(k) != s[k]]
        if fields:
            diffs.append((f, s, fields))
    status_a = [f["reference_status"] for f, _ in pairs]
    status_b = [s["reference_status"] for _, s in pairs]
    both_inc = [(f, s) for f, s in pairs if f["reference_status"] == s["reference_status"] == "incorrect"]
    both_step = [(f, s) for f, s in pairs if f.get("first_invalid_step") and s["first_invalid_step"]]
    summary = {
        "n_compared": len(pairs),
        "status_agreement": sum(x == y for x, y in zip(status_a, status_b)) / len(pairs) if pairs else None,
        "status_kappa": kappa(status_a, status_b),
        "n_both_incorrect": len(both_inc),
        "category_agreement": (sum(f["primary_error"] == s["primary_error"] for f, s in both_inc) / len(both_inc)
                               if both_inc else None),
        "category_kappa": kappa([f["primary_error"] for f, _ in both_inc], [s["primary_error"] for _, s in both_inc]),
        "n_both_step": len(both_step),
        "step_agreement": (sum(f["first_invalid_step"] == s["first_invalid_step"] for f, s in both_step) / len(both_step)
                           if both_step else None),
        "n_disagreements": len(diffs),
    }
    return summary, diffs


def fmt(v):
    return "—" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--fraction", type=float, default=0.2)
    e.add_argument("--out", default=str(io.SECOND_WORKBOOK))
    e.add_argument("--force", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("--file", default=str(io.SECOND_WORKBOOK))
    c.add_argument("--annotator", default="second annotator")
    c.add_argument("--record", default=str(io.SECOND_JSON))
    c.add_argument("--disagreements", default=str(io.DISAGREEMENTS_MD))
    for p in (e, c):
        p.add_argument("--cases", default=str(io.CASES_JSON))
    args = ap.parse_args()

    d2b = [x for x in json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
           if x.get("source") == "hand_crafted"]
    if not d2b:
        sys.exit("✗ no D2b cases — run scripts/d2b_import.py first")

    if args.cmd == "export":
        out = Path(args.out)
        if out.exists() and not args.force:
            sys.exit(f"✗ {out} exists (it may hold the second annotator's work). Use --force to replace it.")
        picked = sample(d2b, args.fraction)
        build(out, SECOND_COLUMNS, io.load_bank(), [response_row(x) for x in picked],
              "D2b 第二标注 — 请独立完成", guide=SECOND_GUIDE)
        print(f"✓ wrote {out}: {len(picked)} of {len(d2b)} cases ({len(picked) / len(d2b):.0%}), labels blank")
        print("  send it to the second annotator; when it comes back, put it at the same path and run: "
              "python scripts/d2b_second.py compare")
        return

    rows = io.read_workbook(Path(args.file))
    first = {x["case_id"]: x for x in d2b}
    summary, diffs = compare(first, rows)
    if not summary["n_compared"]:
        sys.exit("✗ no labelled rows found in the second annotator's file")
    print(f"Second annotation: {summary['n_compared']} case(s) compared")
    print(f"  status agreement   {fmt(summary['status_agreement'])}   kappa {fmt(summary['status_kappa'])}")
    print(f"  category agreement {fmt(summary['category_agreement'])}   kappa {fmt(summary['category_kappa'])}"
          f"   (n = {summary['n_both_incorrect']} both incorrect)")
    print(f"  first-step agreement {fmt(summary['step_agreement'])}   (n = {summary['n_both_step']})")
    print(f"  disagreements: {summary['n_disagreements']}")

    labelled = [r for r in rows if r["case_id"] in first and r.get("reference_status")]
    ids = sorted(r["case_id"] for r in labelled)
    record = {"compared_at": datetime.now().isoformat(timespec="seconds"), "annotator": args.annotator,
              "case_ids": ids, "summary": summary,
              "second_labels": {r["case_id"]: {k: r.get(k, "") for k in LABEL_KEYS} for r in labelled}}
    Path(args.record).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"\n## {date.today().isoformat()} — D2b, {args.annotator} ({summary['n_compared']} cases)\n",
             f"Status agreement {fmt(summary['status_agreement'])} (kappa {fmt(summary['status_kappa'])}); "
             f"category agreement {fmt(summary['category_agreement'])} (kappa {fmt(summary['category_kappa'])}); "
             f"first-step agreement {fmt(summary['step_agreement'])}.\n",
             "| Case | Field | First annotator | Second annotator | Resolution |", "| --- | --- | --- | --- | --- |"]
    for f, s, fields in diffs:
        for k in fields:
            lines.append(f"| {f['case_id']} | {k} | {f.get(k)} | {s[k]} |  |")
    if not diffs:
        lines.append("| — | — | no disagreements | | |")
    p = Path(args.disagreements)
    head = "" if p.exists() else ("# Annotation disagreements\n\nRecorded before discussion; the original "
                                  "annotations are kept (evaluation_plan §5.1).\n")
    p.write_text((p.read_text(encoding="utf-8") if p.exists() else head) + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n✓ wrote {Path(args.record).name} and appended {p.name}")
    print("  discuss each disagreement, write the outcome in its Resolution cell; if a first label was wrong, "
          "fix it in d2b_cases.xlsx and import with --allow-relabel")


if __name__ == "__main__":
    main()
