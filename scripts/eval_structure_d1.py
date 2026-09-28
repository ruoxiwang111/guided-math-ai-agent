"""
EQ1 structure extraction on D1 (evaluation_plan.md §3.8, §6.4).

Run from the project root (needs DEEPSEEK_API_KEY):
    python scripts/eval_structure_d1.py                      # test split, 3 runs
    python scripts/eval_structure_d1.py --split dev --runs 1 # tune prompts on dev only
    python scripts/eval_structure_d1.py --oracle             # sanity check of the scorer (no LLM)

System decision per input (core/structure.py):
    in_scope      extraction usable (scope in_scope AND consistency == consistent)
    out_of_scope  the LLM judged it out of scope
    uncertain     anything else (uncertain scope, or structure not consistent)

Metrics
    Scope accuracy          decision == reference_scope, over all inputs
    Equation correctness    over reference-in-scope inputs: the extracted equation has the same
                            solution set as the reference equation or one accepted alternative
                            (no usable structure counts as incorrect)
    Field accuracy          unknown (quantity match) and known quantities (same set of values),
                            over reference-in-scope inputs with a structure. The relationship field
                            is exported for manual review and not scored automatically.
    Consistent-but-wrong    among inputs the system marked consistent: equation NOT correct
                            (the limitation in V1_design §10 — must always be reported)

LLM components run --runs times (evaluation_plan §5.3); mean / min / max are reported.
Outputs: eval/results/structure_d1/<run_id>/ (config.json, outputs_run<k>.json, summary.json).
"""
import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import math_checker as mc  # noqa: E402
from core.diagnosis import _quantity, _similarity  # noqa: E402
from core.structure import CONSISTENT, IN_SCOPE, OUT_OF_SCOPE, PROMPT_VERSION, extract_structure  # noqa: E402


def decision(ex) -> str:
    if ex.scope == IN_SCOPE and ex.consistency == CONSISTENT and ex.question:
        return "in_scope"
    if ex.scope == OUT_OF_SCOPE:
        return "out_of_scope"
    return "uncertain"


def equation_correct(system_eq, ref) -> bool:
    if not system_eq or not ref:
        return False
    candidates = [ref["equation"]] + [a["equation"] for a in ref.get("accepted_alternatives", [])]
    return any(mc.equivalent(system_eq, c) is True for c in candidates)


def known_values(items):
    out = set()
    for k in items or []:
        try:
            out.add(mc.nsimplify(mc.S(str(k["value"])), rational=True))
        except Exception:  # noqa: BLE001
            pass
    return out


def score_case(case, ex):
    ref = case["reference_structure"]
    sys_q = ex.question
    row = {"case_id": case["case_id"], "reference_scope": case["reference_scope"], "decision": decision(ex),
           "llm_scope": ex.scope, "consistency": ex.consistency,
           "system_equation": sys_q["equation"] if sys_q else None,
           "system_final_answer": sys_q["final_answer_text"] if sys_q else None,
           "system_relationship": sys_q["relationship"] if sys_q else None,
           "reference_relationship": ref["relationship"] if ref else None,
           "failed_checks": [c.name for c in ex.checks if not c.ok], "error": ex.error}
    row["scope_correct"] = row["decision"] == case["reference_scope"]
    if case["reference_scope"] == "in_scope":
        row["equation_correct"] = equation_correct(row["system_equation"], ref)
        if sys_q:
            meaning = lambda m: _quantity(f"设x为{m}")  # noqa: E731  (same filler rules for both sides)
            row["unknown_correct"] = (
                _similarity(meaning(sys_q["unknown"]["meaning"]), meaning(ref["unknown"]["meaning"])) >= 0.5
                or _similarity(_quantity(sys_q["variable_definition"]), _quantity(ref["variable_definition"])) >= 0.5
                or any(_similarity(_quantity(sys_q["variable_definition"]), _quantity(a["variable_definition"])) >= 0.5
                       for a in ref.get("accepted_alternatives", [])))
            row["known_correct"] = known_values(sys_q["known_quantities"]) == known_values(ref["known_quantities"])
    if row["decision"] == "in_scope":
        row["consistent_but_wrong"] = not row.get("equation_correct", False)
    return row


def summarise(rows):
    def rate(xs):
        xs = [x for x in xs if x is not None]
        return (sum(xs) / len(xs)) if xs else None
    in_scope = [r for r in rows if r["reference_scope"] == "in_scope"]
    with_struct = [r for r in in_scope if "known_correct" in r]
    consistent = [r for r in rows if r["decision"] == "in_scope"]
    fields = [r["unknown_correct"] for r in with_struct] + [r["known_correct"] for r in with_struct]
    return {
        "n_inputs": len(rows),
        "scope_accuracy": rate([r["scope_correct"] for r in rows]),
        "equation_correctness": rate([r["equation_correct"] for r in in_scope]),
        "field_accuracy_unknown_known": rate(fields),
        "consistent_but_wrong_rate": rate([r["consistent_but_wrong"] for r in consistent]),
        "n_reference_in_scope": len(in_scope),
        "n_marked_consistent": len(consistent),
    }


class OracleBackend:
    """Returns the reference structure itself – checks the scorer, not the model."""

    def __init__(self, cases):
        self.by_text = {c["input_text"]: c for c in cases}
        self._last = None

    def describe(self):
        return {"backend": "oracle"}

    def complete(self, system, user):
        if "独立解" in system:
            ref = self._last["reference_structure"]
            return json.dumps({"parts": [{"label": "x", "value": str(ref["answer"])}]})
        case = self.by_text[json.loads(user)["题目"]]
        self._last = case
        ref = case["reference_structure"]
        if case["reference_scope"] != "in_scope":
            return json.dumps({"scope": case["reference_scope"], "scope_reason": case.get("scope_reason", "")})
        return json.dumps({
            "scope": "in_scope", "unknown": ref["unknown"], "variable_definition": ref["variable_definition"],
            "known_quantities": ref["known_quantities"], "relationship": ref["relationship"],
            "equation": ref["equation"], "answer_parts": [{"label": "", "expression": "x", "unit": ""}],
            "verification_conditions": [{"description": "方程成立", "lhs": ref["equation"].split("=")[0],
                                         "op": "==", "rhs": ref["equation"].split("=")[1]}],
            "alternatives": [], "e4_patterns": [], "s1_target": "t", "s1_intermediate": "i",
        }, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default=str(ROOT / "eval" / "structure_cases.json"))
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--oracle", action="store_true")
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "results" / "structure_d1"))
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    if args.split != "all":
        cases = [c for c in cases if c["split"] == args.split]

    if args.oracle:
        backend, runs = OracleBackend(cases), 1
    else:
        from core.llm_client import default_backend
        backend, runs = default_backend(), args.runs
        if backend is None:
            sys.exit("✗ DEEPSEEK_API_KEY not found – use --oracle to check the scorer without an LLM")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + ("-oracle" if args.oracle else "")
    out = Path(args.out_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps({
        "run_id": run_id, "split": args.split, "runs": runs, "n_cases": len(cases),
        "prompt_version": PROMPT_VERSION, "backend": backend.describe()}, ensure_ascii=False, indent=2), encoding="utf-8")

    summaries = []
    for k in range(1, runs + 1):
        rows = []
        for c in cases:
            rows.append(score_case(c, extract_structure(c["input_text"], backend)))
            print(f"  run {k} {c['case_id']}: {rows[-1]['decision']:<13} eq={rows[-1].get('equation_correct')}")
        summaries.append(summarise(rows))
        (out / f"outputs_run{k}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str),
                                                 encoding="utf-8")

    keys = ["scope_accuracy", "equation_correctness", "field_accuracy_unknown_known", "consistent_but_wrong_rate"]
    agg = {}
    for key in keys:
        vals = [s[key] for s in summaries if s[key] is not None]
        agg[key] = {"mean": statistics.mean(vals) if vals else None,
                    "min": min(vals) if vals else None, "max": max(vals) if vals else None}
    (out / "summary.json").write_text(json.dumps({"per_run": summaries, "aggregate": agg}, ensure_ascii=False, indent=2),
                                      encoding="utf-8")

    print(f"\nD1 structure ({args.split}, n={len(cases)}, runs={runs})")
    for key in keys:
        a = agg[key]
        fmt = lambda v: "—" if v is None else f"{v:.1%}"  # noqa: E731
        print(f"  {key:<30} mean {fmt(a['mean'])}   min {fmt(a['min'])}   max {fmt(a['max'])}")
    print("  relationship field: exported for manual review (system_relationship vs reference_relationship)")
    print(f"\n✓ wrote {out}")


if __name__ == "__main__":
    main()