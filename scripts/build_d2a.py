"""
Build the D2a mutation-generated diagnostic set from data/question_bank.json.

Run from the project root:
    python scripts/build_d2a.py
    python scripts/build_d2a.py --bank data/question_bank.json --out eval/diagnostic_cases.json
    python scripts/build_d2a.py --dev-ratio 0.3
    python scripts/build_d2a.py --dev-ratio 0.3 --seed 42

What it does
  1. Validates question_bank.json before building. Stops if the bank has errors.
  2. Turns every mutation (65 in V1.3) into one D2a diagnostic case.
  3. Applies the integration rules from the evaluation audit:
       - E4 subtypes are collapsed for scoring:
         primary_error = "E4"
         original label is retained in error_subtype.
       - Modelling mutations without variable_definition inherit the
         question's own variable_definition.
       - Mutations whose equation equals the standard equation
         (e.g. Q13-E2) are flagged because the error is visible only
         through the variable definition.
  4. Reference labels by layer:
       modelling  -> S2, Level A, incorrect / diagnosed
       execution  -> S3, Level A, incorrect / diagnosed
                     first_invalid_step is retained
       answer     -> S4
                     E1/E5 are directly visible in the final answer
                     -> Level A
                     other answer-only errors (e.g. Q12-E6b)
                     -> Level B, uncertain
  5. Preserves existing hand-crafted D2b cases in the output file.
     Only cases with source = "mutation" are regenerated.
  6. By default all D2a cases are assigned to test (--dev-ratio 0).
     This is a project default for D2a; evaluation_plan.md §5.2 should state it.
     --dev-ratio optionally creates a stratified dev/test split.

Reference annotations are written with review_status = "pending".
The researcher should review them once before the first headline test run.
"""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Import validator from the same scripts directory
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import validate_question_bank as vqb  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE = {
    "modelling": "S2",
    "execution": "S3",
    "answer": "S4",
}

ANSWER_LEVEL_A = {
    "E1",
    "E5",
}

DEFAULT_HINT_LEVEL = 1

VALID_LAYERS = set(STATE)

# Expected V1.3 counts.
# The mutation total is shared with validate_question_bank.py so that the two
# scripts cannot drift apart. The other two are D2a-specific.
EXPECTED_MUTATIONS = vqb.EXPECTED_MUTATIONS      # 65
EXPECTED_STEP_CASES = 30                         # execution mutations
EXPECTED_INHERITED_VD = 19                       # modelling mutations w/o variable_definition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def norm(text):
    """
    Normalise the bank's SymPy-style strings for lightweight comparison.

    The validator uses the same whitespace-only normalisation rule.
    This is NOT a mathematical equivalence checker.
    """
    return text.replace(" ", "")


def build_case(q, m):
    """
    Convert one question-bank mutation into one D2a diagnostic case.
    """
    layer = m["layer"]
    err = m["error"]

    if layer not in VALID_LAYERS:
        raise ValueError(
            f"Unsupported mutation layer '{layer}' in mutation {m.get('id')}"
        )

    category = vqb.collapse(err)

    case = {
        "case_id": f"D2a-{m['id']}",
        "question_id": q["question_id"],
        "mutation_id": m["id"],
        "source": "mutation",
        "split": "test",
        "layer": layer,
        "state": STATE[layer],
        "difficulty": q["difficulty"],
    }

    notes = []

    # -----------------------------------------------------------------------
    # Modelling mutations
    # -----------------------------------------------------------------------

    if layer == "modelling":
        mutation_vd = m.get("variable_definition")

        if mutation_vd:
            variable_definition = mutation_vd
            variable_definition_source = "mutation"
        else:
            variable_definition = q["variable_definition"]
            variable_definition_source = "question_default"

        case["variable_definition_source"] = variable_definition_source

        case["learner_response"] = {
            "variable_definition": variable_definition,
            "equation": m["equation"],
        }

        case["normalized_response"] = {
            "variable_definition": variable_definition,
            "equation": norm(m["equation"]),
        }

        evidence = (
            f"{m['description']}；方程 {m['equation']}"
        )

        # Special case such as Q13-E2:
        # equation is identical to the standard equation, so the
        # diagnostic signal is the variable definition.
        if vqb.same_equation(m["equation"], q["equation"]):
            notes.append(
                "方程与标准方程相同，错误只能从变量定义看出"
            )
            evidence = (
                f"{m['description']}；变量定义：{variable_definition}"
            )

        first_invalid = None

    # -----------------------------------------------------------------------
    # Execution mutations
    # -----------------------------------------------------------------------

    elif layer == "execution":
        case["variable_definition_source"] = "question_default"

        case["learner_response"] = {
            "variable_definition": q["variable_definition"],
            "steps": m["steps"],
        }

        case["normalized_response"] = {
            "variable_definition": q["variable_definition"],
            "steps": [norm(step) for step in m["steps"]],
        }

        first_invalid = m["first_invalid_step"]

        if not isinstance(first_invalid, int):
            raise ValueError(
                f"Execution mutation {m['id']} has invalid "
                f"first_invalid_step: {first_invalid!r}"
            )

        if not 1 <= first_invalid <= len(m["steps"]):
            raise ValueError(
                f"Execution mutation {m['id']} has first_invalid_step="
                f"{first_invalid}, but only {len(m['steps'])} steps exist."
            )

        k = first_invalid

        if k > 1:
            evidence = (
                f"第{k}行 '{m['steps'][k - 1]}'"
                f"（上一行 '{m['steps'][k - 2]}'）："
                f"{m['description']}"
            )
        else:
            evidence = (
                f"第1行 '{m['steps'][0]}'："
                f"{m['description']}"
            )

    # -----------------------------------------------------------------------
    # Answer mutations
    # -----------------------------------------------------------------------

    else:
        case["learner_response"] = {
            "final_answer_text": m["final_answer_text"],
        }

        case["normalized_response"] = {
            "final_answer_text": m["final_answer_text"].strip(),
        }

        evidence = (
            f"最终答案“{m['final_answer_text']}”："
            f"{m['description']}"
        )

        first_invalid = None

    # -----------------------------------------------------------------------
    # Reference annotation
    # -----------------------------------------------------------------------

    # Modelling and execution errors are visible in the response itself.
    #
    # For answer-only cases:
    #   E1/E5 -> directly visible in final answer -> Level A
    #   others -> reasoning is unavailable -> Level B / uncertain
    level_a = (
        layer != "answer"
        or category in ANSWER_LEVEL_A
    )

    if level_a:
        case.update(
            {
                "reference_status": "incorrect",
                "primary_error": category,
                "error_subtype": (
                    err if err != category else None
                ),
                "candidate_errors": [category],
                "evidence_level": "A",
                "diagnosis_status": "diagnosed",
                "recommended_hint_level": DEFAULT_HINT_LEVEL,
            }
        )

    else:
        notes.append(
            "只有最终答案，推理不可见；"
            "参考标注为 uncertain（Level B）"
        )

        case.update(
            {
                "reference_status": "uncertain",
                "primary_error": None,
                "error_subtype": None,
                "candidate_errors": [category],
                "evidence_level": "B",
                "diagnosis_status": "uncertain",
                "recommended_hint_level": None,
            }
        )

    # -----------------------------------------------------------------------
    # Shared annotation fields
    # -----------------------------------------------------------------------

    case.update(
        {
            "secondary_errors": [],
            "evidence": evidence,
            "first_invalid_step": first_invalid,
            "annotation_note": ";".join(notes) if notes else None,
            "review_status": "pending",
        }
    )

    return case


def assign_split(cases, dev_ratio, seed):
    """
    Stratified dev/test split by primary_error.

    Uncertain cases form their own stratum.

    The default evaluation plan keeps D2a entirely in test, so this function
    is only used when --dev-ratio > 0.
    """
    if not 0.0 <= dev_ratio < 1.0:
        raise ValueError(
            f"--dev-ratio must be >= 0 and < 1.0; got {dev_ratio}"
        )

    rng = random.Random(seed)

    strata = defaultdict(list)

    for case in cases:
        stratum = case["primary_error"] or "uncertain"
        strata[stratum].append(case)

    for group in strata.values():
        rng.shuffle(group)

        n_dev = round(len(group) * dev_ratio)

        for index, case in enumerate(group):
            case["split"] = (
                "dev" if index < n_dev else "test"
            )


def load_json(path):
    """
    Read UTF-8 JSON from disk.
    """
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def validate_bank(bank):
    """
    Run the same validation logic used by validate_question_bank.py.

    Returns the validator report.
    """
    report = vqb.Report()

    vqb.check_structure(bank, report)

    if not report.errors:
        vqb.check_counts(bank, report)
        vqb.check_maths(bank, report)

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--bank",
        default="data/question_bank.json",
        help="Path to the question bank JSON.",
    )

    parser.add_argument(
        "--out",
        default="eval/diagnostic_cases.json",
        help="Output path for the combined D2a/D2b diagnostic set.",
    )

    parser.add_argument(
        "--dev-ratio",
        type=float,
        default=0.0,
        help=(
            "Share of D2a cases assigned to dev. "
            "Default 0.0 keeps all D2a cases in test "
            "(project default for D2a; see evaluation_plan.md §5.2)."
        ),
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible stratified splitting.",
    )

    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Argument validation
    # -----------------------------------------------------------------------

    if not 0.0 <= args.dev_ratio < 1.0:
        print(
            f"✗ --dev-ratio must be >= 0 and < 1.0; "
            f"got {args.dev_ratio}"
        )
        sys.exit(1)

    bank_path = Path(args.bank)
    out_path = Path(args.out)

    if not bank_path.exists():
        print(f"✗ question bank not found: {bank_path}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 1. Validate question bank
    # -----------------------------------------------------------------------

    try:
        bank = load_json(bank_path)
    except json.JSONDecodeError as exc:
        print(f"✗ invalid JSON in {bank_path}: {exc}")
        sys.exit(1)

    report = validate_bank(bank)

    if report.errors:
        print(
            f"✗ question bank has {len(report.errors)} problem(s); "
            "run validate_question_bank.py. Nothing written."
        )

        for error in report.errors:
            print("  -", error)

        sys.exit(1)

    print(
        f"✓ question bank validated: "
        f"{bank_path} (version {bank.get('version')})"
    )

    # -----------------------------------------------------------------------
    # 2–4. Build all D2a mutation cases
    # -----------------------------------------------------------------------

    try:
        d2a = [
            build_case(question, mutation)
            for question in bank["questions"]
            for mutation in question["mutations"]
        ]
    except (KeyError, ValueError, TypeError) as exc:
        print(f"✗ failed while building D2a cases: {exc}")
        sys.exit(1)

    # Safety check: V1.3 should produce exactly 65 cases.
    mutation_count = sum(
        len(question["mutations"])
        for question in bank["questions"]
    )

    if len(d2a) != mutation_count:
        print(
            f"✗ D2a case count mismatch: "
            f"expected {mutation_count}, generated {len(d2a)}"
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Optional dev/test split
    # -----------------------------------------------------------------------

    if args.dev_ratio > 0:
        assign_split(
            d2a,
            args.dev_ratio,
            args.seed,
        )

    # -----------------------------------------------------------------------
    # 5. Preserve existing D2b hand-crafted cases
    # -----------------------------------------------------------------------

    kept = []

    if out_path.exists():
        try:
            old = load_json(out_path)
        except json.JSONDecodeError as exc:
            print(
                f"✗ existing output is invalid JSON: "
                f"{out_path}: {exc}"
            )
            print(
                "  No output was written. Fix or remove the existing file "
                "before rebuilding."
            )
            sys.exit(1)

        if not isinstance(old, dict):
            print(
                f"✗ existing output must be a JSON object "
                f"with a 'cases' list: {out_path}"
            )
            print(
                "  No output was written. Fix or remove the existing file "
                "before rebuilding."
            )
            sys.exit(1)

        old_cases = old.get("cases", [])

        if not isinstance(old_cases, list) or not all(
            isinstance(case, dict) for case in old_cases
        ):
            print(
                f"✗ existing output field 'cases' must be a list "
                f"of objects: {out_path}"
            )
            print(
                "  No output was written. Fix or remove the existing file "
                "before rebuilding."
            )
            sys.exit(1)

        kept = [
            case
            for case in old_cases
            if case.get("source") != "mutation"
        ]

    # -----------------------------------------------------------------------
    # Duplicate case IDs
    # -----------------------------------------------------------------------

    all_cases = d2a + kept

    case_ids = Counter(
        case.get("case_id")
        for case in all_cases
    )

    duplicate_ids = [
        case_id
        for case_id, count in case_ids.items()
        if count > 1
    ]

    if duplicate_ids:
        print(
            f"✗ duplicate case_id detected: {duplicate_ids}"
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 6. Write output
    # -----------------------------------------------------------------------

    payload = {
        "version": "1.0",
        "generated": date.today().isoformat(),
        "question_bank_version": bank.get("version"),
        "notes": [
            (
                "D2a = source 'mutation'（本脚本生成，"
                "重跑会覆盖）；D2b = source 'hand_crafted' "
                "（手工标注，重跑时保留）。"
            ),
            (
                "primary_error 已合并子类型（E4-01 → E4）；"
                "原始标签保留在 error_subtype。"
            ),
            (
                "reference_status = uncertain 的样本不计入 "
                "Coverage 分母，计入 Uncertainty Appropriateness。"
            ),
            (
                "默认 D2a 全部为 test；如需开发集，使用 "
                "--dev-ratio，并固定 --seed 以保证可复现。"
            ),
        ],
        "cases": all_cases,
    }

    out_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    out_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------

    print()
    print(
        f"✓ wrote {out_path}: "
        f"{len(d2a)} D2a cases + "
        f"{len(kept)} kept D2b cases"
    )
    print()

    print(
        "D2a by layer:           ",
        dict(
            Counter(
                case["layer"]
                for case in d2a
            )
        ),
    )

    print(
        "D2a by reference_status:",
        dict(
            Counter(
                case["reference_status"]
                for case in d2a
            )
        ),
    )

    print(
        "D2a by primary_error:   ",
        {
            key: value
            for key, value in sorted(
                Counter(
                    case["primary_error"] or "uncertain"
                    for case in d2a
                ).items()
            )
        },
    )

    print(
        "D2a by evidence_level:  ",
        dict(
            Counter(
                case["evidence_level"]
                for case in d2a
            )
        ),
    )

    print(
        "D2a by split:           ",
        dict(
            Counter(
                case["split"]
                for case in d2a
            )
        ),
    )

    print(
        "Step-localisation cases:",
        sum(
            case["first_invalid_step"] is not None
            for case in d2a
        ),
    )

    defaulted = [
        case["mutation_id"]
        for case in d2a
        if (
            case.get("variable_definition_source")
            == "question_default"
            and case["layer"] == "modelling"
        )
    ]

    print(
        "Modelling cases using the question's "
        f"variable_definition: {len(defaulted)}"
    )

    if defaulted:
        print(
            "  inherited from question:",
            ", ".join(defaulted),
        )

    special_cases = [
        case
        for case in d2a
        if case.get("annotation_note")
    ]

    if special_cases:
        print()

        for case in special_cases:
            print(
                f"  note {case['case_id']}: "
                f"{case['annotation_note']}"
            )

    print()

    # -----------------------------------------------------------------------
    # Final sanity checks
    # -----------------------------------------------------------------------

    if len(d2a) != EXPECTED_MUTATIONS:
        print(
            f"⚠ Warning: V1.3 expected {EXPECTED_MUTATIONS} "
            f"mutation cases, but generated {len(d2a)}."
        )
    else:
        print(
            f"✓ D2a mutation count confirmed: {EXPECTED_MUTATIONS}"
        )

    step_cases = sum(
        case["first_invalid_step"] is not None
        for case in d2a
    )

    if step_cases != EXPECTED_STEP_CASES:
        print(
            f"⚠ Warning: expected {EXPECTED_STEP_CASES} "
            f"step-localisation cases, found {step_cases}."
        )
    else:
        print(
            f"✓ D2a step-localisation count confirmed: "
            f"{EXPECTED_STEP_CASES}"
        )

    inherited_count = len(defaulted)

    if inherited_count != EXPECTED_INHERITED_VD:
        print(
            f"⚠ Warning: expected {EXPECTED_INHERITED_VD} modelling "
            f"cases to inherit variable_definition, "
            f"found {inherited_count}."
        )
    else:
        print(
            f"✓ modelling variable_definition inheritance confirmed: "
            f"{EXPECTED_INHERITED_VD}"
        )


if __name__ == "__main__":
    main()