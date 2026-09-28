"""
Build the D1 structure / scope evaluation set (eval/structure_cases.json).

Run from the project root:
    python scripts/build_d1.py
    python scripts/build_d1.py --bank data/question_bank.json \
        --extra eval/d1_extra_cases.json --out eval/structure_cases.json

Composition (evaluation_plan.md §4, D1 = 30 inputs)
  D1-01..15  generated from question_bank.json – never copied by hand, so the
             question text, reference equation, unknown, known quantities,
             relationship and difficulty always match the frozen bank.
  D1-16..25  10 reworded in-scope variants                  (eval/d1_extra_cases.json)
  D1-26..27  2 out-of-scope inputs                           (eval/d1_extra_cases.json)
  D1-28..29  2 uncertain inputs (scope cannot be decided yet) (eval/d1_extra_cases.json)
  D1-30      1 in-scope question that arrives with a wrong learner equation;
             the system must still extract the question's own structure.
             Its reference_structure is hand-written because the learner
             equation and the question structure must be evaluated separately.

What it checks before writing
  - question bank passes validate_question_bank.py
  - 15 / 10 / 5 composition, unique case_id, D1-01..D1-30 in order
  - reference_scope in {in_scope, out_of_scope, uncertain}
  - in-scope cases have a complete reference_structure; others have
    reference_structure = null and a scope_reason
  - based_on refers to an existing question; reworded difficulty = base difficulty
  - every reference equation (and accepted alternative) solves to its answer (SymPy)

Split (evaluation_plan.md §5.2): 10 dev / 20 test, stratified by source,
reproducible with --seed.

Reference annotations are written with review_status = "pending".
"""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import validate_question_bank as vqb  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_COMPOSITION = {
    "question_bank": 15,
    "reworded": 10,
    "with_learner_work": 1,
    "out_of_scope": 2,
    "uncertain": 2,
}

EXPECTED_TOTAL = sum(EXPECTED_COMPOSITION.values())      # 30
DEV_COUNT = 10                                            # evaluation_plan §5.2

SCOPES = {
    "in_scope",
    "out_of_scope",
    "uncertain",
}

EXTRA_SOURCES = {
    "reworded",
    "with_learner_work",
    "out_of_scope",
    "uncertain",
}

IN_SCOPE_SOURCES = {
    "question_bank",
    "reworded",
    "with_learner_work",
}

STRUCTURE_FIELDS = [
    "unknown",
    "known_quantities",
    "relationship",
    "variable_definition",
    "equation",
    "answer",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def fail(msg, errors=None):
    print(f"✗ {msg}")

    for error in errors or []:
        print(
            "  -",
            error,
        )

    print("  Nothing written.")
    sys.exit(1)


def source_group(case):
    return case["source"]


def bank_case(index, q):
    """
    Build one D1 case directly from one question-bank item.

    The index argument is retained for compatibility with the existing
    builder interface. It is not used in the reference structure.
    """

    alternatives = [
        {
            key: form[key]
            for key in (
                "variable_definition",
                "equation",
                "x_value",
            )
            if key in form
        }
        for form in q.get(
            "accepted_equivalent_forms",
            [],
        )
        if "x_value" in form
    ]

    return {
        "case_id": f"D1-{index:02d}",
        "source": "question_bank",
        "question_id": q["question_id"],
        "based_on": q["question_id"],
        "difficulty": q["difficulty"],
        "input_text": q["question"],
        "reference_scope": "in_scope",
        "reference_structure": {
            "unknown": q["unknown"],
            "known_quantities": q["known_quantities"],
            "relationship": q["relationship"],
            "variable_definition": q["variable_definition"],
            "equation": q["equation"],
            "answer": q["answer"],
            "final_answer_text": q["final_answer_text"],
            "accepted_alternatives": alternatives,
        },
        "scope_reason": q.get("scope_note"),
    }


def extra_case(c, bank_by_id):
    """
    Normalise one hand-written case to the D1 schema.

    Hand-written extra cases must provide their own reference_structure
    when they are in scope.

    In particular, 'reference_structure = "from_based_on"' is rejected
    rather than silently copying the parent question's structure. A case
    may use 'based_on' only as provenance while changing its wording,
    quantities, relationships, or equation.
    """

    structure = c.get(
        "reference_structure"
    )

    # ------------------------------------------------------------------
    # Do NOT automatically inherit reference_structure from based_on.
    #
    # A hand-written case may be based on a bank question but still have
    # a different mathematical structure.
    #
    # Example:
    #   D1-30 is based_on Q08 but changes the wording and equation.
    #
    # Silently copying Q08 here would create an incorrect reference.
    # ------------------------------------------------------------------

    if structure == "from_based_on":
        raise ValueError(
            f"{c.get('case_id')}: "
            "reference_structure='from_based_on' "
            "is not allowed for hand-written D1 cases; "
            "provide an explicit reference_structure object."
        )

    case = {
        "case_id": c.get("case_id"),
        "source": c.get("source"),
        "question_id": None,
        "based_on": c.get("based_on"),
        "difficulty": c.get("difficulty"),
        "input_text": c.get("input_text"),
        "reference_scope": c.get(
            "reference_scope"
        ),
        "reference_structure": structure,
        "scope_reason": c.get(
            "scope_reason"
        ),
    }

    if "learner_work" in c:
        case["learner_work"] = c[
            "learner_work"
        ]

    return case


def check_cases(cases, bank_by_id):
    """
    Validate the complete D1 case set.
    """

    errors = []

    # ------------------------------------------------------------------
    # Case IDs
    # ------------------------------------------------------------------

    ids = [
        c["case_id"]
        for c in cases
    ]

    for cid, count in Counter(ids).items():
        if count > 1:
            errors.append(
                f"duplicate case_id {cid}"
            )

    expected_ids = [
        f"D1-{i:02d}"
        for i in range(
            1,
            EXPECTED_TOTAL + 1,
        )
    ]

    if ids != expected_ids:
        errors.append(
            "case_id must run "
            "D1-01..D1-30 in order "
            "(bank cases first, then "
            "d1_extra_cases.json in order)"
        )

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    comp = Counter(
        source_group(c)
        for c in cases
    )

    if dict(comp) != EXPECTED_COMPOSITION:
        errors.append(
            f"composition {dict(comp)} "
            f"!= expected {EXPECTED_COMPOSITION}"
        )

    # ------------------------------------------------------------------
    # Per-case checks
    # ------------------------------------------------------------------

    for c in cases:

        cid = c["case_id"]

        # Source
        if c["source"] not in (
            EXTRA_SOURCES
            | {"question_bank"}
        ):
            errors.append(
                f"{cid}: source "
                f"'{c['source']}' invalid"
            )

        # Scope
        if c["reference_scope"] not in SCOPES:
            errors.append(
                f"{cid}: reference_scope "
                f"'{c['reference_scope']}' "
                f"not in {sorted(SCOPES)}"
            )

        # Input
        if not c.get("input_text"):
            errors.append(
                f"{cid}: input_text is empty"
            )

        # based_on
        if (
            c["based_on"] is not None
            and c["based_on"] not in bank_by_id
        ):
            errors.append(
                f"{cid}: based_on "
                f"'{c['based_on']}' "
                "not in question bank"
            )

        # Expected scope from source
        expected_scope = (
            "in_scope"
            if c["source"]
            in IN_SCOPE_SOURCES
            else c["source"]
        )

        if c["reference_scope"] != expected_scope:
            errors.append(
                f"{cid}: source "
                f"'{c['source']}' "
                "requires reference_scope "
                f"'{expected_scope}', "
                f"found '{c['reference_scope']}'"
            )

        # Learner work
        if (
            c["source"]
            == "with_learner_work"
            and not c.get("learner_work")
        ):
            errors.append(
                f"{cid}: "
                "with_learner_work case "
                "needs learner_work"
            )

        # Reworded / learner-work difficulty
        if c["source"] in (
            "reworded",
            "with_learner_work",
        ):

            base = bank_by_id.get(
                c["based_on"]
            )

            if base is None:
                errors.append(
                    f"{cid}: "
                    "reworded case "
                    "needs based_on"
                )

            elif (
                c["difficulty"]
                != base["difficulty"]
            ):
                errors.append(
                    f"{cid}: difficulty "
                    f"'{c['difficulty']}' "
                    f"!= "
                    f"{c['based_on']} "
                    f"difficulty "
                    f"'{base['difficulty']}'"
                )

        # ------------------------------------------------------------------
        # In-scope structure
        # ------------------------------------------------------------------

        if c["reference_scope"] == "in_scope":

            structure = c[
                "reference_structure"
            ]

            if not isinstance(
                structure,
                dict,
            ):
                errors.append(
                    f"{cid}: in-scope case "
                    "needs reference_structure"
                )
                continue

            for field in STRUCTURE_FIELDS:
                if field not in structure:
                    errors.append(
                        f"{cid}: "
                        "reference_structure "
                        f"missing '{field}'"
                    )

            if (
                "equation" in structure
                and "answer" in structure
            ):
                errors += check_equation(
                    cid,
                    structure["equation"],
                    structure["answer"],
                )

            for alternative in structure.get(
                "accepted_alternatives",
                [],
            ):

                if (
                    "variable_definition"
                    not in alternative
                ):
                    errors.append(
                        f"{cid}: accepted "
                        "alternative needs "
                        "variable_definition"
                    )

                # An alternative without x_value
                # uses the main answer.
                errors += check_equation(
                    cid,
                    alternative.get(
                        "equation",
                        "",
                    ),
                    alternative.get(
                        "x_value",
                        structure.get(
                            "answer"
                        ),
                    ),
                    label="alternative ",
                )

        # ------------------------------------------------------------------
        # Out-of-scope / uncertain
        # ------------------------------------------------------------------

        else:

            if (
                c["reference_structure"]
                is not None
            ):
                errors.append(
                    f"{cid}: "
                    f"{c['reference_scope']} "
                    "case must have "
                    "reference_structure = null"
                )

            if not c.get(
                "scope_reason"
            ):
                errors.append(
                    f"{cid}: "
                    f"{c['reference_scope']} "
                    "case needs scope_reason"
                )

    return errors


def check_equation(
    cid,
    eq,
    answer,
    label="",
):
    """
    Check that an equation solves to the supplied answer.
    """

    if answer is None:
        return [
            f"{cid}: {label}"
            f"equation '{eq}' "
            "has no answer / x_value "
            "to check against"
        ]

    try:
        got = vqb.solve_eq(eq)
        want = vqb.value(answer)

    except Exception as exc:  # noqa: BLE001
        return [
            f"{cid}: cannot parse "
            f"{label}equation '{eq}' "
            f"({exc})"
        ]

    if got != {want}:
        return [
            f"{cid}: {label}"
            f"equation '{eq}' "
            f"gives {got}, "
            f"expected {want}"
        ]

    return []


def assign_split(cases, seed):
    """
    Assign 10 dev / 20 test.

    Split is stratified by source group and reproducible with --seed.
    """

    rng = random.Random(seed)

    groups = defaultdict(list)

    for case in cases:
        groups[
            source_group(case)
        ].append(case)

    # Proportional allocation.
    #
    # 15 / 10 / 5 of 30 -> 5 / 3 / 2 of 10.
    quota = {
        group: round(
            len(members)
            * DEV_COUNT
            / len(cases)
        )
        for group, members
        in groups.items()
    }

    diff = (
        DEV_COUNT
        - sum(quota.values())
    )

    if diff:
        largest = max(
            groups,
            key=lambda group:
            len(groups[group]),
        )

        quota[largest] += diff

    for group, members in groups.items():

        order = members[:]

        rng.shuffle(order)

        dev_ids = {
            case["case_id"]
            for case in order[
                :quota[group]
            ]
        }

        for case in members:
            case["split"] = (
                "dev"
                if case["case_id"]
                in dev_ids
                else "test"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=(
            argparse.RawDescriptionHelpFormatter
        ),
    )

    ap.add_argument(
        "--bank",
        default="data/question_bank.json",
    )

    ap.add_argument(
        "--extra",
        default="eval/d1_extra_cases.json",
    )

    ap.add_argument(
        "--out",
        default="eval/structure_cases.json",
    )

    ap.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    args = ap.parse_args()

    # ------------------------------------------------------------------
    # File existence
    # ------------------------------------------------------------------

    for path in (
        args.bank,
        args.extra,
    ):

        if not Path(path).exists():
            fail(
                f"file not found: {path}"
            )

    # ------------------------------------------------------------------
    # Load JSON
    # ------------------------------------------------------------------

    try:

        bank = load_json(
            args.bank
        )

        extra = load_json(
            args.extra
        )

    except json.JSONDecodeError as exc:

        fail(
            f"invalid JSON: {exc}"
        )

    # ------------------------------------------------------------------
    # 1. Validate question bank
    # ------------------------------------------------------------------

    report = vqb.Report()

    vqb.check_structure(
        bank,
        report,
    )

    if not report.errors:

        vqb.check_counts(
            bank,
            report,
        )

        vqb.check_maths(
            bank,
            report,
        )

    if report.errors:

        fail(
            f"question bank has "
            f"{len(report.errors)} "
            "problem(s); "
            "run "
            "validate_question_bank.py",
            report.errors,
        )

    # ------------------------------------------------------------------
    # Validate extra-case container
    # ------------------------------------------------------------------

    if (
        not isinstance(extra, dict)
        or not isinstance(
            extra.get("cases"),
            list,
        )
    ):
        fail(
            f"{args.extra} must be "
            "a JSON object with "
            "a 'cases' list"
        )

    # ------------------------------------------------------------------
    # 2. Build
    # ------------------------------------------------------------------

    bank_by_id = {
        question["question_id"]:
        question
        for question
        in bank["questions"]
    }

    cases = [
        bank_case(
            index,
            question,
        )
        for index, question
        in enumerate(
            bank["questions"],
            start=1,
        )
    ]

    try:

        cases += [
            extra_case(
                case,
                bank_by_id,
            )
            for case
            in extra["cases"]
        ]

    except ValueError as exc:

        fail(str(exc))

    # ------------------------------------------------------------------
    # 3. Check
    # ------------------------------------------------------------------

    errors = check_cases(
        cases,
        bank_by_id,
    )

    if errors:

        fail(
            f"D1 has "
            f"{len(errors)} "
            "problem(s)",
            errors,
        )

    # ------------------------------------------------------------------
    # 4. Split + annotation status
    # ------------------------------------------------------------------

    assign_split(
        cases,
        args.seed,
    )

    for case in cases:
        case["review_status"] = "pending"

    comp = Counter(
        source_group(case)
        for case in cases
    )

    payload = {
        "version": "1.0",
        "dataset": "D1_structure",
        "generated": date.today().isoformat(),
        "question_bank_version": bank.get(
            "version"
        ),
        "knowledge_point": bank.get(
            "knowledge_point"
        ),
        "total_cases": len(cases),
        "composition": {
            key: comp[key]
            for key
            in EXPECTED_COMPOSITION
        },
        "notes": [
            "D1 测的是系统对【题目】的范围判断和结构提取（EQ1），不含学生作答；学生作答的诊断样本在 diagnostic_cases.json（D2）。",
            "D1-01..15 由 build_d1.py 从 question_bank.json 生成，不要手改；D1-16..30 在 eval/d1_extra_cases.json 中维护。",
            "reference_scope ∈ {in_scope, out_of_scope, uncertain}；out_of_scope / uncertain 的 reference_structure 为 null。",
            "范围判断只看题目本身：学生答案是否正确、是否给出过程，不影响 reference_scope（D1-30 带错误方程但仍为 in_scope）。",
            "Equation correctness：系统方程与 reference_structure.equation 同解，或与某个 accepted_alternatives 在其变量定义下同解，即算正确。",
            "Field accuracy 比较 unknown / known_quantities / relationship 三个字段。",
            "split：10 dev / 20 test，按 source 分层，--seed 可复现（evaluation_plan.md §5.2）。",
            "with_learner_work 的 learner_work 只是输入的一部分，不是参考答案；参考结构来自 based_on 题目。",
            "hand-written in-scope cases must provide their own reference_structure; based_on is provenance only and does not automatically copy the parent structure.",
        ],
        "cases": cases,
    }

    # ------------------------------------------------------------------
    # Write output
    # ------------------------------------------------------------------

    out = Path(
        args.out
    )

    out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    out.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # 5. Summary
    # ------------------------------------------------------------------

    print(
        f"✓ question bank validated "
        f"(version {bank.get('version')})"
    )

    print(
        f"✓ wrote {out}: "
        f"{len(cases)} cases\n"
    )

    print(
        "composition:     ",
        payload["composition"],
    )

    print(
        "reference_scope: ",
        dict(
            Counter(
                case["reference_scope"]
                for case in cases
            )
        ),
    )

    print(
        "difficulty (in-scope):",
        dict(
            Counter(
                case["difficulty"]
                for case in cases
                if case["reference_scope"]
                == "in_scope"
            )
        ),
    )

    print(
        "split:           ",
        dict(
            Counter(
                case["split"]
                for case in cases
            )
        ),
    )

    print(
        "split by source: ",
        {
            group: dict(
                Counter(
                    case["split"]
                    for case in cases
                    if source_group(case)
                    == group
                )
            )
            for group
            in EXPECTED_COMPOSITION
        },
    )


if __name__ == "__main__":
    main()