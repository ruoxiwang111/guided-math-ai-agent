"""
EQ4 step localisation on D2a (evaluation_plan.md §3.7).

Run from the project root:
    python scripts/eval_step_localisation.py
    python scripts/eval_step_localisation.py --cases eval/diagnostic_cases.json

For every D2a case with a first_invalid_step (the execution mutations), runs
core.math_checker.check_steps on the learner steps, with the question's
standard equation as reference, in two input formats:

    bank     – steps exactly as stored ("2*x + 5 = 25")
    learner  – rewritten the way a student types them ("2x+5＝25", ×, −)

Reports, per format:
    Step-Localisation Accuracy = correct first_invalid_step / all cases
    Valid-step false alarms    = valid lines (before the annotated step) flagged invalid
    Localisation uncertain     = cases returned as uncertain

Writes eval/results/step_localisation_d2a.json. Reference annotations are
read only; nothing is written back to them.

Interpretation (must travel with the numbers)
    The D2a reference first_invalid_step was produced by validate_question_bank.py
    with the same solution-set criterion that math_checker uses. A score on D2a
    therefore shows agreement with that criterion and a working pipeline, not
    independent localisation accuracy. That evidence comes from D2b.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.math_checker import INVALID_FOUND, UNCERTAIN, check_steps  # noqa: E402


def learner_style(step: str) -> str:
    s = re.sub(r"(\d)\*x", r"\1x", step)
    s = re.sub(r"(\d)\*\(", r"\1(", s)
    s = s.replace("*", "×").replace("-", "−").replace("=", "＝").replace(" ", "")
    return s


FORMATS = {"bank": lambda s: s, "learner": learner_style}

INTERPRETATION = (
    "On the 30 annotated D2a execution cases, the deterministic checker's first invalid "
    "step is compared with the reference label, in both bank-format and learner-style input, "
    "where the reference labels were produced by the same solution-set criterion. "
    "The result therefore measures agreement with that criterion and pipeline integrity, "
    "not independent step-localisation accuracy; independent evidence comes from D2b."
)


def run(cases, bank_by_id, fmt):
    rows = []
    for c in cases:
        ref_eq = bank_by_id[c["question_id"]]["equation"]
        steps = [FORMATS[fmt](s) for s in c["learner_response"]["steps"]]
        k = c["first_invalid_step"]
        r = check_steps(steps, reference_equation=ref_eq)
        predicted = r.first_invalid_step if r.status == INVALID_FOUND else None
        rows.append({
            "case_id": c["case_id"],
            "reference_first_invalid_step": k,
            "predicted_first_invalid_step": predicted,
            "status": r.status,
            "reason": r.reason,
            "correct": predicted == k,
            "false_alarm": predicted is not None and predicted < k,
            "uncertain": r.status == UNCERTAIN,
            "valid_lines_checked": k - 1,
            "input_steps": steps,
        })
    n = len(rows)
    valid_lines = sum(r["valid_lines_checked"] for r in rows)
    return {
        "n_cases": n,
        "step_localisation_accuracy": sum(r["correct"] for r in rows) / n if n else None,
        "correct": sum(r["correct"] for r in rows),
        "valid_step_false_alarms": sum(r["false_alarm"] for r in rows),
        "valid_lines_total": valid_lines,
        "localisation_uncertain": sum(r["uncertain"] for r in rows),
        "missed": sum(r["predicted_first_invalid_step"] is None and not r["uncertain"] for r in rows),
        "cases": rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default="eval/diagnostic_cases.json")
    ap.add_argument("--bank", default="data/question_bank.json")
    ap.add_argument("--out", default="eval/results/step_localisation_d2a.json")
    args = ap.parse_args()

    data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    bank = json.loads(Path(args.bank).read_text(encoding="utf-8"))
    bank_by_id = {q["question_id"]: q for q in bank["questions"]}

    cases = [c for c in data["cases"]
             if c.get("source") == "mutation" and c.get("first_invalid_step") is not None]
    if not cases:
        sys.exit("✗ no D2a step-localisation cases found – run scripts/build_d2a.py first")

    results = {fmt: run(cases, bank_by_id, fmt) for fmt in FORMATS}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "dataset": "D2a",
        "metric": "EQ4 step localisation",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "question_bank_version": bank.get("version"),
        "interpretation": INTERPRETATION,
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"D2a step localisation – {len(cases)} execution cases\n")
    print(f"{'format':<9}{'accuracy':>10}{'correct':>9}{'false alarms':>14}{'uncertain':>11}{'missed':>8}")
    for fmt, r in results.items():
        print(f"{fmt:<9}{r['step_localisation_accuracy']:>10.1%}{r['correct']:>6}/{r['n_cases']:<3}"
              f"{r['valid_step_false_alarms']:>8}/{r['valid_lines_total']:<5}"
              f"{r['localisation_uncertain']:>9}{r['missed']:>8}")
    for fmt, r in results.items():
        wrong = [c for c in r["cases"] if not c["correct"]]
        if wrong:
            print(f"\n[{fmt}] not localised correctly:")
            for c in wrong:
                print(f"  {c['case_id']}: reference {c['reference_first_invalid_step']}, "
                      f"predicted {c['predicted_first_invalid_step']} ({c['status']})  {c['input_steps']}")
    print("\nNote: D2a reference labels were produced by the same solution-set criterion as the")
    print("checker, so this is an agreement / pipeline check, not independent accuracy (see D2b).")
    print(f"\n✓ wrote {out}")


if __name__ == "__main__":
    main()