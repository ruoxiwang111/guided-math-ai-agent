"""
EQ2 diagnosis on D2a (evaluation_plan.md §3.2–3.6).

Run from the project root:
    python scripts/eval_diagnosis_d2a.py

Two modes, reported separately:

  full           – the bank's modelling mutations are available to the matcher.
                   Modelling cases can then match THEMSELVES, so this mode only
                   checks integration; it is not evidence of diagnostic skill.
  leave_one_out  – when diagnosing a case, its own mutation is removed from the
                   matcher. Modelling and answer cases must then be caught by
                   the general rules (E4 closed-list templates, E2 rule, unit
                   rule) or be returned as uncertain. Execution cases (E6/E7)
                   never use the mutation list, so they are identical in both
                   modes.

Metrics (canonical definitions, evaluation_plan.md §3):
  Coverage              = reference-incorrect cases given a specific category / reference-incorrect cases
  Conditional Accuracy  = specific diagnoses with the right primary category / all specific diagnoses
  Uncertainty Approp.   = reference-uncertain cases returned uncertain/insufficient / reference-uncertain cases
  Confusion matrix      = reference label × system output

Writes eval/results/diagnosis_d2a.json. Reference annotations are read only.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.diagnosis import DIAGNOSED, diagnose_response  # noqa: E402

CATS = [f"E{i}" for i in range(1, 8)]
OUT_COLS = CATS + ["no_error_detected", "uncertain", "insufficient_evidence"]


def output_label(d):
    return d.primary_error if d.status == DIAGNOSED else d.status


def evaluate(cases, bank, mode):
    rows = []
    for c in cases:
        q = bank[c["question_id"]]
        exclude = c["mutation_id"] if mode == "leave_one_out" else None
        d = diagnose_response(q, c["learner_response"], exclude_mutation=exclude)
        rows.append({
            "case_id": c["case_id"], "layer": c["layer"],
            "reference_status": c["reference_status"],
            "reference": c["primary_error"] if c["reference_status"] == "incorrect" else c["reference_status"],
            "status": d.status, "output": output_label(d), "candidates": d.candidates,
            "evidence_level": d.evidence_level, "rule": d.rule, "evidence": d.evidence,
            "first_invalid_step": d.first_invalid_step,
        })

    inc = [r for r in rows if r["reference_status"] == "incorrect"]
    unc = [r for r in rows if r["reference_status"] == "uncertain"]
    specific = [r for r in inc if r["status"] == DIAGNOSED]
    correct = [r for r in specific if r["output"] == r["reference"]]

    confusion = defaultdict(Counter)
    for r in rows:
        confusion[r["reference"]][r["output"]] += 1

    by_layer = {}
    for layer in ("modelling", "execution", "answer"):
        li = [r for r in inc if r["layer"] == layer]
        ls = [r for r in li if r["status"] == DIAGNOSED]
        by_layer[layer] = {
            "n_incorrect": len(li),
            "coverage": len(ls) / len(li) if li else None,
            "conditional_accuracy": sum(r["output"] == r["reference"] for r in ls) / len(ls) if ls else None,
        }

    return {
        "n_cases": len(rows),
        "n_reference_incorrect": len(inc),
        "n_reference_uncertain": len(unc),
        "coverage": len(specific) / len(inc) if inc else None,
        "conditional_accuracy": len(correct) / len(specific) if specific else None,
        "wrong_specific_diagnoses": len(specific) - len(correct),
        "uncertainty_appropriateness": (sum(r["status"] in ("uncertain", "insufficient_evidence") for r in unc) / len(unc)) if unc else None,
        "by_layer": by_layer,
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
        "cases": rows,
    }


def pct(v):
    return "—" if v is None else f"{v:.1%}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default="eval/diagnostic_cases.json")
    ap.add_argument("--bank", default="data/question_bank.json")
    ap.add_argument("--out", default="eval/results/diagnosis_d2a.json")
    args = ap.parse_args()

    bank_json = json.loads(Path(args.bank).read_text(encoding="utf-8"))
    bank = {q["question_id"]: q for q in bank_json["questions"]}
    cases = [c for c in json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
             if c.get("source") == "mutation"]
    if not cases:
        sys.exit("✗ no D2a cases – run scripts/build_d2a.py first")

    results = {mode: evaluate(cases, bank, mode) for mode in ("full", "leave_one_out")}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "dataset": "D2a", "metric": "EQ2 diagnosis",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "question_bank_version": bank_json.get("version"),
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"D2a diagnosis – {len(cases)} cases "
          f"({results['full']['n_reference_incorrect']} incorrect, {results['full']['n_reference_uncertain']} uncertain)\n")
    print(f"{'mode':<15}{'coverage':>10}{'cond. acc.':>12}{'wrong labels':>14}{'uncert. approp.':>17}")
    for mode, r in results.items():
        print(f"{mode:<15}{pct(r['coverage']):>10}{pct(r['conditional_accuracy']):>12}"
              f"{r['wrong_specific_diagnoses']:>14}{pct(r['uncertainty_appropriateness']):>17}")

    print("\nleave_one_out by layer:")
    for layer, v in results["leave_one_out"]["by_layer"].items():
        print(f"  {layer:<10} n={v['n_incorrect']:<3} coverage {pct(v['coverage']):>7}   cond. acc. {pct(v['conditional_accuracy']):>7}")

    print("\nleave_one_out confusion matrix (rows = reference, cols = output):")
    cm = results["leave_one_out"]["confusion_matrix"]
    cols = [c for c in OUT_COLS if any(c in row for row in cm.values())]
    short = {"no_error_detected": "no_err", "uncertain": "unc", "insufficient_evidence": "insuff"}
    print("  " + " " * 10 + "".join(f"{short.get(c, c):>8}" for c in cols))
    for ref in CATS + ["uncertain"]:
        if ref in cm:
            print(f"  {ref:<10}" + "".join(f"{cm[ref].get(c, 0) or '.':>8}" for c in cols))
    print(f"\n✓ wrote {out}")


if __name__ == "__main__":
    main()