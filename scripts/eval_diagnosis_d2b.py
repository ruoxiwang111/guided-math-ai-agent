"""
EQ2 / EQ3 / EQ4 on D2b — the hand-crafted, independently annotated diagnostic set
(evaluation_plan.md §3.2–3.7, §5; headline results come from the D2b TEST split only).

Run from the project root, after d2b_import.py and after the annotations are committed:
    python scripts/eval_diagnosis_d2b.py                 # test split (the headline result)
    python scripts/eval_diagnosis_d2b.py --split dev     # development split, for tuning rules
    python scripts/eval_diagnosis_d2b.py --split all

Metrics (canonical definitions, §3)
    Coverage               reference-incorrect cases given a specific E1–E7 / reference-incorrect cases
    Conditional accuracy   specific diagnoses with the right primary category / specific diagnoses
    Uncertainty approp.    reference-uncertain cases returned uncertain / insufficient_evidence
    FPR                    reference-correct cases given any E1–E7 / reference-correct cases
                           (correct cases returned uncertain are reported separately, not as FP)
    Step localisation      line-by-line execution-error cases with an annotated first invalid step:
                           right step / wrong step / localisation uncertain, plus valid-step false alarms
    Confusion matrix       raw counts, rows = reference, columns = system output

The diagnosis is deterministic (no LLM), so one run is enough. The test split refuses to run while
any of its cases is not `reviewed` (the dataset is not frozen yet) unless --allow-pending, and the
result then says frozen = false.

Outputs eval/results/diagnosis_d2b/<timestamp>/summary.json and cases.csv (for error analysis).
"""
import argparse
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from core.diagnosis import DIAGNOSED, INSUFFICIENT, UNCERTAIN, diagnose_response, diagnose_steps  # noqa: E402

import d2b_io as io  # noqa: E402

OUT_COLS = io.CATS + ["no_error_detected", "uncertain", "insufficient_evidence"]
ROW_LABELS = io.CATS + ["correct", "uncertain", "not_assessable"]
TARGETS = {"fpr": 0.05, "step_localisation": 0.80, "conditional_accuracy": 0.75, "coverage": 0.60}


def diagnose(question, case):
    resp = case["learner_response"]
    if case["layer"] == "execution":
        return diagnose_steps(question, resp["steps"], resp.get("variable_definition"),
                              start_equation=resp.get("equation"))
    return diagnose_response(question, resp)


def reference_label(c):
    if c["reference_status"] == "incorrect":
        return c["primary_error"] or "incorrect_unlabelled"
    return c["reference_status"]


def evaluate(cases, bank):
    rows = []
    for c in cases:
        d = diagnose(bank[c["question_id"]], c)
        rows.append({
            "case_id": c["case_id"], "question_id": c["question_id"], "layer": c["layer"], "split": c["split"],
            "reference_status": c["reference_status"], "reference": reference_label(c),
            "reference_step": c["first_invalid_step"], "tags": ";".join(c["tags"]),
            "status": d.status, "output": d.primary_error if d.status == DIAGNOSED else d.status,
            "system_step": d.first_invalid_step, "rule": d.rule, "candidates": ";".join(d.candidates or []),
            "evidence_level": d.evidence_level, "system_evidence": d.evidence,
            "reference_evidence": c.get("evidence"), "response_origin": c.get("response_origin", ""),
        })

    inc = [r for r in rows if r["reference_status"] == "incorrect"]
    unc = [r for r in rows if r["reference_status"] == "uncertain"]
    cor = [r for r in rows if r["reference_status"] == "correct"]
    na = [r for r in rows if r["reference_status"] == "not_assessable"]
    specific = [r for r in inc if r["status"] == DIAGNOSED]
    right = [r for r in specific if r["output"] == r["reference"]]
    held = (UNCERTAIN, INSUFFICIENT)

    loc = [r for r in inc if r["layer"] == "execution" and r["reference_step"]]
    loc_right = [r for r in loc if r["system_step"] == r["reference_step"]]
    loc_wrong = [r for r in loc if r["system_step"] and r["system_step"] != r["reference_step"]]
    loc_unc = [r for r in loc if not r["system_step"]]
    early = [r for r in loc_wrong if r["system_step"] < r["reference_step"]]
    correct_lines = [r for r in cor if r["layer"] == "execution"]
    correct_flagged = [r for r in correct_lines if r["system_step"] or r["status"] == DIAGNOSED]

    confusion = defaultdict(Counter)
    for r in rows:
        confusion[r["reference"]][r["output"]] += 1

    by_layer = {}
    for layer in io.LAYERS:
        li = [r for r in inc if r["layer"] == layer]
        ls = [r for r in li if r["status"] == DIAGNOSED]
        by_layer[layer] = {"n_incorrect": len(li), "coverage": rate(len(ls), len(li)),
                           "conditional_accuracy": rate(sum(r["output"] == r["reference"] for r in ls), len(ls))}

    by_origin = {}
    for origin in sorted({r["response_origin"] for r in rows}):
        o = [r for r in rows if r["response_origin"] == origin]
        oi = [r for r in o if r["reference_status"] == "incorrect"]
        os_ = [r for r in oi if r["status"] == DIAGNOSED]
        oc = [r for r in o if r["reference_status"] == "correct"]
        by_origin[origin or "unknown"] = {
            "n": len(o), "coverage": rate(len(os_), len(oi)),
            "conditional_accuracy": rate(sum(r["output"] == r["reference"] for r in os_), len(os_)),
            "fpr": rate(sum(r["status"] == DIAGNOSED for r in oc), len(oc))}

    return {
        "n_cases": len(rows),
        "n": {"incorrect": len(inc), "correct": len(cor), "uncertain": len(unc), "not_assessable": len(na)},
        "coverage": rate(len(specific), len(inc)),
        "conditional_accuracy": rate(len(right), len(specific)),
        "wrong_specific_diagnoses": len(specific) - len(right),
        "uncertainty_appropriateness": rate(sum(r["status"] in held for r in unc), len(unc)),
        "fpr": rate(sum(r["status"] == DIAGNOSED for r in cor), len(cor)),
        "correct_returned_uncertain": sum(r["status"] in held for r in cor),
        "not_assessable_outputs": dict(Counter(r["output"] for r in na)),
        "step_localisation": {
            "n": len(loc), "accuracy": rate(len(loc_right), len(loc)),
            "right_step": len(loc_right), "wrong_step": len(loc_wrong), "uncertain": len(loc_unc),
            "valid_step_false_alarms": len(early) + len(correct_flagged),
            "valid_step_false_alarms_detail": {"flagged_before_annotated_step": len(early),
                                               "correct_line_by_line_flagged": len(correct_flagged)},
        },
        "by_layer": by_layer,
        "by_origin": by_origin,
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
        "cases": rows,
    }


def rate(a, b):
    return a / b if b else None


def pct(v):
    return "—" if v is None else f"{v:.1%}"


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["test", "dev", "all"], default="test")
    ap.add_argument("--cases", default=str(io.CASES_JSON))
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "results" / "diagnosis_d2b"))
    ap.add_argument("--allow-pending", action="store_true", help="run on cases not yet reviewed (result not frozen)")
    args = ap.parse_args()

    bank = io.load_bank()
    all_d2b = [c for c in json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
               if c.get("source") == "hand_crafted"]
    if not all_d2b:
        sys.exit("✗ no D2b cases — fill eval/d2b_cases.xlsx and run scripts/d2b_import.py first")
    cases = all_d2b if args.split == "all" else [c for c in all_d2b if c["split"] == args.split]
    pending = [c["case_id"] for c in cases if c.get("review_status") not in ("reviewed", "adjudicated")]
    if pending and args.split != "dev" and not args.allow_pending:
        sys.exit(f"✗ {len(pending)} case(s) not reviewed yet ({', '.join(pending[:5])}{' …' if len(pending) > 5 else ''}).\n"
                 "  The test set must be frozen before it is run (evaluation_plan §5.1). "
                 "Use --allow-pending only for a trial run.")
    dirty = git("status", "--porcelain", "--", "eval/diagnostic_cases.json", "core")
    frozen = not pending and not dirty

    result = evaluate(cases, bank)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out_dir) / f"{stamp}-{args.split}"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"dataset": "D2b", "split": args.split, "run_at": datetime.now().isoformat(timespec="seconds"),
            "commit": git("rev-parse", "--short", "HEAD"), "uncommitted_changes": dirty.splitlines(),
            "frozen": frozen, "pending_cases": pending}
    summary = {k: v for k, v in result.items() if k != "cases"}
    (out / "summary.json").write_text(json.dumps({**meta, "results": summary}, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    with (out / "cases.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(result["cases"][0]))
        w.writeheader()
        w.writerows(result["cases"])

    r = result
    print(f"D2b diagnosis — split {args.split}, {r['n_cases']} cases "
          f"({r['n']['incorrect']} incorrect, {r['n']['correct']} correct, {r['n']['uncertain']} uncertain, "
          f"{r['n']['not_assessable']} not assessable); commit {meta['commit'] or '?'}; "
          f"{'FROZEN' if frozen else 'NOT FROZEN — trial run'}\n")
    sl = r["step_localisation"]
    print(f"  coverage               {pct(r['coverage']):>7}   (target ≥ {TARGETS['coverage']:.0%})")
    print(f"  conditional accuracy   {pct(r['conditional_accuracy']):>7}   (target ≥ {TARGETS['conditional_accuracy']:.0%})"
          f"   wrong labels: {r['wrong_specific_diagnoses']}")
    print(f"  FPR                    {pct(r['fpr']):>7}   (target ≤ {TARGETS['fpr']:.0%})"
          f"   correct returned uncertain: {r['correct_returned_uncertain']}")
    print(f"  uncertainty approp.    {pct(r['uncertainty_appropriateness']):>7}")
    print(f"  step localisation      {pct(sl['accuracy']):>7}   (target ≥ {TARGETS['step_localisation']:.0%})"
          f"   n={sl['n']}: right {sl['right_step']}, wrong {sl['wrong_step']}, uncertain {sl['uncertain']};"
          f" valid-step false alarms {sl['valid_step_false_alarms']}")
    print("\n  by layer:")
    for layer, v in r["by_layer"].items():
        print(f"    {layer:<10} n={v['n_incorrect']:<3} coverage {pct(v['coverage']):>7}   cond. acc. {pct(v['conditional_accuracy']):>7}")
    print("\n  by response origin:")
    for origin, v in r["by_origin"].items():
        print(f"    {origin:<19} n={v['n']:<3} coverage {pct(v['coverage']):>7}   cond. acc. {pct(v['conditional_accuracy']):>7}"
              f"   FPR {pct(v['fpr']):>7}")
    print("\n  confusion matrix (rows = reference, cols = system output, raw counts):")
    cm = r["confusion_matrix"]
    cols = [c for c in OUT_COLS if any(c in row for row in cm.values())]
    short = {"no_error_detected": "no_err", "uncertain": "unc", "insufficient_evidence": "insuff"}
    print("    " + " " * 16 + "".join(f"{short.get(c, c):>8}" for c in cols))
    for ref in ROW_LABELS + sorted(k for k in cm if k not in ROW_LABELS):
        if ref in cm:
            print(f"    {ref:<16}" + "".join(f"{cm[ref].get(c, 0) or '.':>8}" for c in cols))
    print(f"\n✓ wrote {out}")


if __name__ == "__main__":
    main()
