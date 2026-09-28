"""
Validate data/question_bank.json (V1.3) before it is used by the app
or the evaluation.

Run from the project root:

    python scripts/validate_question_bank.py

Or provide an explicit question-bank path:

    python scripts/validate_question_bank.py path/to/bank.json

Checks
------
A. Structure
   - Required fields on every question, mutation, and Challenge AI item
   - Legal values for difficulty / layer / error / v1_set_role
   - Valid verification-condition operators
   - Valid execution first_invalid_step
   - No leftover challenge_ai.role field

B. Counts
   - 15 questions
   - Difficulty: Easy 5 / Medium 7 / Hard 3
   - 65 mutations
   - Unique question IDs and mutation IDs
   - Challenge AI: 9 incorrect / 6 correct
   - Q14 must be correct

C. Maths
   - Standard equation -> expected answer
   - Accepted equivalent forms -> expected answer
   - Verification conditions hold at the expected answer
   - Modelling mutations do not accidentally reproduce the correct answer
     unless the error is purely in variable_definition
   - Execution mutations remain valid before first_invalid_step and become
     invalid at first_invalid_step
   - Challenge AI correct x_value -> expected answer
   - Challenge AI incorrect version must not end with the correct final answer

D. Evaluation readiness
   - Mutation counts by layer
   - Error-category distribution with E4 subtypes collapsed to E4
   - D2a step-localisation count
   - Modelling mutations missing variable_definition
   - Modelling mutations whose equation is identical to the standard equation
   - E4 subtype coverage

Problems in A-C are ERRORS and cause exit code 1.
Items in D are NOTES unless they indicate a real structural/math problem.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from sympy import Eq, S, nsimplify, solve, symbols
from sympy.parsing.sympy_parser import parse_expr


# ============================================================================
# Expected V1.3 set
# ============================================================================

EXPECTED_QUESTIONS = 15

EXPECTED_DIFFICULTY = {
    "easy": 5,
    "medium": 7,
    "hard": 3,
}

EXPECTED_MUTATIONS = 65

EXPECTED_CHALLENGE = {
    "incorrect": 9,
    "correct": 6,
}

FIXED_ROLES = {
    "Q14": "correct",
}


# ============================================================================
# Required fields
# ============================================================================

QUESTION_FIELDS = [
    "question_id",
    "difficulty",
    "topic",
    "question",
    "known_quantities",
    "unknown",
    "variable_definition",
    "relationship",
    "equation",
    "answer",
    "final_answer_text",
    "e4_patterns",
    "accepted_equivalent_forms",
    "verification_conditions",
    "mutations",
    "challenge_ai",
]


MUTATION_FIELDS = {
    "modelling": [
        "id",
        "layer",
        "error",
        "description",
        "equation",
    ],
    "execution": [
        "id",
        "layer",
        "error",
        "description",
        "steps",
        "first_invalid_step",
    ],
    "answer": [
        "id",
        "layer",
        "error",
        "description",
        "final_answer_text",
    ],
}


# E1-E7 are primary categories.
# E4-01 ... E4-08 are E4 subtypes.
ERROR_RE = re.compile(r"^E[1-7]$|^E4-0[1-8]$")

CONDITION_OPS = {
    "==",
    ">",
    "<",
    ">=",
    "<=",
    "integer",
}


# ============================================================================
# SymPy setup
# ============================================================================

x = symbols("x")

LOCALS = {
    "x": x,
}


# ============================================================================
# Utility helpers
# ============================================================================

def expr(value_text):
    """
    Convert an expression string into an exact SymPy expression.

    Examples:
        "2*x + 5"
        "1/3"
        "0.8*x"
    """
    return nsimplify(
        parse_expr(
            str(value_text),
            local_dict=LOCALS,
        ),
        rational=True,
    )


def solve_eq(eq_str):
    """
    Solve an equation of the form:

        lhs = rhs

    and return the solution set as exact SymPy values.
    """
    if eq_str.count("=") != 1:
        raise ValueError(
            f"expected exactly one '=' in {eq_str!r}"
        )

    lhs, rhs = eq_str.split("=")

    equation = Eq(
        expr(lhs),
        expr(rhs),
    )

    return {
        nsimplify(v, rational=True)
        for v in solve(equation, x)
    }


def value(v):
    """
    Convert a stored numeric value into an exact SymPy value.
    """
    return nsimplify(
        S(v),
        rational=True,
    )


def check_condition(cond, xv):
    """
    Evaluate a verification condition at x = xv.
    """

    op = cond["op"]

    if op == "integer":
        result = expr(cond["lhs"]).subs(x, xv)

        return bool(result.is_integer)

    lhs = expr(cond["lhs"]).subs(x, xv)
    rhs = expr(cond["rhs"]).subs(x, xv)

    comparisons = {
        "==": lhs == rhs,
        ">": lhs > rhs,
        "<": lhs < rhs,
        ">=": lhs >= rhs,
        "<=": lhs <= rhs,
    }

    return bool(comparisons[op])


def same_equation(a, b):
    """
    Compare equations after removing whitespace.

    This intentionally does NOT perform algebraic normalization.
    It is used to detect cases where the mutation literally reuses
    the same equation string as the standard question.
    """
    return (
        str(a).replace(" ", "")
        == str(b).replace(" ", "")
    )


def collapse(error):
    """
    Collapse E4 subtypes to the primary E4 category.

    Examples:
        E4-01 -> E4
        E4-06 -> E4
        E3    -> E3
    """
    return str(error).split("-")[0]


def question_id_from_mutation(mutation_id):
    """
    Extract the parent question ID.

    Example:
        Q13-E2-01 -> Q13
    """
    return str(mutation_id).split("-")[0]


# ============================================================================
# Report
# ============================================================================

class Report:
    def __init__(self):
        self.errors = []
        self.notes = []

    def err(self, message):
        self.errors.append(message)

    def note(self, message):
        self.notes.append(message)


# ============================================================================
# A. Structure checks
# ============================================================================

def check_structure(bank, report):
    """
    Validate the shape and legal values of the question bank.
    """

    if "questions" not in bank:
        report.err("top-level field 'questions' is missing")
        return

    if not isinstance(bank["questions"], list):
        report.err("top-level field 'questions' must be a list")
        return

    for question in bank["questions"]:

        qid = question.get("question_id", "?")

        # ------------------------------------------------------------------
        # Question fields
        # ------------------------------------------------------------------

        for field in QUESTION_FIELDS:
            if field not in question:
                report.err(
                    f"{qid}: missing field '{field}'"
                )

        # ------------------------------------------------------------------
        # Difficulty
        # ------------------------------------------------------------------

        if question.get("difficulty") not in EXPECTED_DIFFICULTY:
            report.err(
                f"{qid}: difficulty "
                f"'{question.get('difficulty')}' "
                f"not in {list(EXPECTED_DIFFICULTY)}"
            )

        # ------------------------------------------------------------------
        # E4 patterns
        # ------------------------------------------------------------------

        for pattern in question.get("e4_patterns", []):
            if not re.match(r"^E4-0[1-8]$", str(pattern)):
                report.err(
                    f"{qid}: e4_patterns entry "
                    f"'{pattern}' is not E4-01..E4-08"
                )

        # ------------------------------------------------------------------
        # Verification conditions
        # ------------------------------------------------------------------

        conditions = question.get(
            "verification_conditions",
            [],
        )

        if not isinstance(conditions, list):
            report.err(
                f"{qid}: verification_conditions must be a list"
            )
        else:
            for condition in conditions:

                for field in (
                    "description",
                    "lhs",
                    "op",
                ):
                    if field not in condition:
                        report.err(
                            f"{qid}: verification condition "
                            f"missing '{field}'"
                        )

                if condition.get("op") not in CONDITION_OPS:
                    report.err(
                        f"{qid}: verification op "
                        f"'{condition.get('op')}' not allowed"
                    )

                if (
                    condition.get("op") != "integer"
                    and "rhs" not in condition
                ):
                    report.err(
                        f"{qid}: verification condition "
                        f"'{condition.get('description')}' "
                        f"missing 'rhs'"
                    )

        # ------------------------------------------------------------------
        # Mutations
        # ------------------------------------------------------------------

        mutations = question.get("mutations", [])

        if not isinstance(mutations, list):
            report.err(
                f"{qid}: mutations must be a list"
            )
            mutations = []

        for mutation in mutations:

            mid = mutation.get("id", "?")
            layer = mutation.get("layer")

            if layer not in MUTATION_FIELDS:
                report.err(
                    f"{mid}: layer '{layer}' "
                    f"not in {list(MUTATION_FIELDS)}"
                )
                continue

            # Required fields by layer
            for field in MUTATION_FIELDS[layer]:
                if field not in mutation:
                    report.err(
                        f"{mid}: {layer} mutation "
                        f"missing '{field}'"
                    )

            # Error type
            if not ERROR_RE.match(
                str(mutation.get("error", ""))
            ):
                report.err(
                    f"{mid}: error "
                    f"'{mutation.get('error')}' "
                    f"is not E1-E7 / E4-0x"
                )

            # Mutation ID must begin with parent question ID
            if not str(mid).startswith(f"{qid}-"):
                report.err(
                    f"{mid}: id does not start "
                    f"with '{qid}-'"
                )

            # Execution mutation checks
            if layer == "execution":

                steps = mutation.get("steps", [])
                first_invalid_step = mutation.get(
                    "first_invalid_step"
                )

                if not isinstance(steps, list):
                    report.err(
                        f"{mid}: execution 'steps' "
                        f"must be a list"
                    )
                    continue

                if (
                    not isinstance(
                        first_invalid_step,
                        int,
                    )
                    or not (
                        1
                        <= first_invalid_step
                        <= len(steps)
                    )
                ):
                    report.err(
                        f"{mid}: first_invalid_step "
                        f"{first_invalid_step} "
                        f"out of range "
                        f"1..{len(steps)}"
                    )

        # ------------------------------------------------------------------
        # Challenge AI
        # ------------------------------------------------------------------

        challenge_ai = question.get(
            "challenge_ai",
            {},
        )

        if not isinstance(challenge_ai, dict):
            report.err(
                f"{qid}: challenge_ai must be an object"
            )
            continue

        # Old field must not remain
        if "role" in challenge_ai:
            report.err(
                f"{qid}: challenge_ai still has old "
                f"field 'role' "
                f"(use 'v1_set_role')"
            )

        # New fixed role
        if (
            challenge_ai.get("v1_set_role")
            not in EXPECTED_CHALLENGE
        ):
            report.err(
                f"{qid}: challenge_ai.v1_set_role "
                f"'{challenge_ai.get('v1_set_role')}' "
                f"invalid"
            )

        # Correct version is required for every question
        correct = challenge_ai.get(
            "correct",
            {},
        )

        if not isinstance(correct, dict):
            report.err(
                f"{qid}: challenge_ai.correct "
                f"must be an object"
            )
        else:
            for field in (
                "text",
                "x_value",
            ):
                if field not in correct:
                    report.err(
                        f"{qid}: challenge_ai.correct "
                        f"missing '{field}'"
                    )

        # Incorrect version is required only when the fixed role
        # is incorrect.
        if (
            challenge_ai.get("v1_set_role")
            == "incorrect"
        ):
            incorrect = challenge_ai.get(
                "incorrect",
                {},
            )

            if not isinstance(incorrect, dict):
                report.err(
                    f"{qid}: challenge_ai.incorrect "
                    f"must be an object"
                )
            else:
                for field in (
                    "text",
                    "error",
                    "final_answer_text",
                ):
                    if field not in incorrect:
                        report.err(
                            f"{qid}: challenge_ai.incorrect "
                            f"missing '{field}'"
                        )

                if (
                    "error" in incorrect
                    and not ERROR_RE.match(
                        str(incorrect["error"])
                    )
                ):
                    report.err(
                        f"{qid}: "
                        f"challenge_ai.incorrect.error "
                        f"'{incorrect['error']}' invalid"
                    )


# ============================================================================
# B. Count checks
# ============================================================================

def check_counts(bank, report):
    """
    Validate fixed V1.3 counts and uniqueness constraints.
    """

    questions = bank["questions"]

    # ------------------------------------------------------------------
    # Question count
    # ------------------------------------------------------------------

    if len(questions) != EXPECTED_QUESTIONS:
        report.err(
            f"expected {EXPECTED_QUESTIONS} questions, "
            f"found {len(questions)}"
        )

    # ------------------------------------------------------------------
    # Question IDs
    # ------------------------------------------------------------------

    question_ids = [
        q["question_id"]
        for q in questions
    ]

    for qid, count in Counter(
        question_ids
    ).items():
        if count > 1:
            report.err(
                f"duplicate question_id {qid}"
            )

    # ------------------------------------------------------------------
    # Difficulty distribution
    # ------------------------------------------------------------------

    difficulty = Counter(
        q["difficulty"]
        for q in questions
    )

    if dict(difficulty) != EXPECTED_DIFFICULTY:
        report.err(
            f"difficulty {dict(difficulty)} "
            f"!= expected {EXPECTED_DIFFICULTY}"
        )

    # ------------------------------------------------------------------
    # Mutation count
    # ------------------------------------------------------------------

    mutations = [
        mutation
        for question in questions
        for mutation in question.get(
            "mutations",
            [],
        )
    ]

    if len(mutations) != EXPECTED_MUTATIONS:
        report.err(
            f"expected {EXPECTED_MUTATIONS} mutations, "
            f"found {len(mutations)}"
        )

    # ------------------------------------------------------------------
    # Mutation IDs
    # ------------------------------------------------------------------

    for mid, count in Counter(
        mutation["id"]
        for mutation in mutations
    ).items():
        if count > 1:
            report.err(
                f"duplicate mutation id {mid}"
            )

    # ------------------------------------------------------------------
    # Challenge AI role distribution
    # ------------------------------------------------------------------

    roles = Counter(
        q["challenge_ai"].get(
            "v1_set_role"
        )
        for q in questions
    )

    if dict(roles) != EXPECTED_CHALLENGE:
        report.err(
            f"Challenge AI roles "
            f"{dict(roles)} "
            f"!= expected {EXPECTED_CHALLENGE}"
        )

    # ------------------------------------------------------------------
    # Fixed question role(s)
    # ------------------------------------------------------------------

    by_id = {
        q["question_id"]: q
        for q in questions
    }

    for qid, expected_role in FIXED_ROLES.items():

        actual_role = (
            by_id
            .get(qid, {})
            .get("challenge_ai", {})
            .get("v1_set_role")
        )

        if actual_role != expected_role:
            report.err(
                f"{qid}: v1_set_role should be "
                f"'{expected_role}', "
                f"found '{actual_role}'"
            )


# ============================================================================
# C. Mathematical checks
# ============================================================================

def check_maths(bank, report):
    """
    Validate equations, answers, conditions, mutations,
    and Challenge AI values.
    """

    for question in bank["questions"]:

        qid = question["question_id"]

        # ------------------------------------------------------------------
        # Standard equation and answer
        # ------------------------------------------------------------------

        try:
            expected_answer = value(
                question["answer"]
            )

            standard_solution = solve_eq(
                question["equation"]
            )

        except Exception as exc:
            report.err(
                f"{qid}: cannot parse standard "
                f"equation/answer ({exc})"
            )
            continue

        if standard_solution != {
            expected_answer
        }:
            report.err(
                f"{qid}: standard equation gives "
                f"{standard_solution}, "
                f"expected {expected_answer}"
            )

        # ------------------------------------------------------------------
        # Accepted equivalent forms
        # ------------------------------------------------------------------

        for form in question.get(
            "accepted_equivalent_forms",
            [],
        ):

            try:
                target = value(
                    form.get(
                        "x_value",
                        question["answer"],
                    )
                )

                obtained = solve_eq(
                    form["equation"]
                )

                if obtained != {target}:
                    report.err(
                        f"{qid}: accepted form "
                        f"'{form['equation']}' "
                        f"gives {obtained}, "
                        f"expected {target}"
                    )

                # If an accepted form explicitly changes x_value,
                # it must explain what x means.
                if (
                    "x_value" in form
                    and "variable_definition"
                    not in form
                ):
                    report.err(
                        f"{qid}: accepted form with "
                        f"x_value needs its own "
                        f"variable_definition"
                    )

            except Exception as exc:
                report.err(
                    f"{qid}: cannot parse accepted "
                    f"form {form} ({exc})"
                )

        # ------------------------------------------------------------------
        # Verification conditions
        # ------------------------------------------------------------------

        for condition in question.get(
            "verification_conditions",
            [],
        ):

            try:
                if not check_condition(
                    condition,
                    expected_answer,
                ):
                    report.err(
                        f"{qid}: verification "
                        f"'{condition['description']}' "
                        f"fails at x={expected_answer}"
                    )

            except Exception as exc:
                report.err(
                    f"{qid}: cannot evaluate "
                    f"verification "
                    f"'{condition.get('description')}' "
                    f"({exc})"
                )

        # ------------------------------------------------------------------
        # Mutations
        # ------------------------------------------------------------------

        for mutation in question.get(
            "mutations",
            [],
        ):

            mid = mutation["id"]
            layer = mutation["layer"]

            try:

                # ==========================================================
                # Modelling mutation
                # ==========================================================

                if layer == "modelling":

                    mutation_solution = solve_eq(
                        mutation["equation"]
                    )

                    equation_is_identical = same_equation(
                        mutation["equation"],
                        question["equation"],
                    )

                    if equation_is_identical:

                        # Important special case:
                        #
                        # Some modelling mutations intentionally use
                        # exactly the same equation as the standard one,
                        # but redefine what x represents.
                        #
                        # Example:
                        # Q13-E2
                        #
                        # Therefore this is NOT automatically an error.
                        if (
                            "variable_definition"
                            not in mutation
                        ):
                            report.err(
                                f"{mid}: equation equals "
                                f"the standard one but "
                                f"no variable_definition "
                                f"to show the error"
                            )

                    elif mutation_solution == {
                        expected_answer
                    }:
                        report.err(
                            f"{mid}: modelling mutation "
                            f"still yields the correct "
                            f"answer"
                        )

                    # A modelling mutation with no mathematical
                    # solution can still be useful as a diagnostic
                    # case, so this is only a note.
                    if not mutation_solution:
                        report.note(
                            f"{mid}: no solution - "
                            f"usable as a diagnostic case only"
                        )

                # ==========================================================
                # Execution mutation
                # ==========================================================

                elif layer == "execution":

                    steps = mutation["steps"]
                    first_invalid_step = mutation[
                        "first_invalid_step"
                    ]

                    # The first line should represent the original
                    # problem equation, or at least have the same
                    # correct solution.
                    if (
                        not same_equation(
                            steps[0],
                            question["equation"],
                        )
                        and solve_eq(steps[0])
                        != {expected_answer}
                    ):
                        report.err(
                            f"{mid}: first line "
                            f"'{steps[0]}' "
                            f"is not a valid starting "
                            f"equation"
                        )

                    # Every step before first_invalid_step must still
                    # preserve the correct solution.
                    for index in range(
                        first_invalid_step - 1
                    ):

                        step_solution = solve_eq(
                            steps[index]
                        )

                        if step_solution != {
                            expected_answer
                        }:
                            report.err(
                                f"{mid}: line "
                                f"{index + 1} "
                                f"'{steps[index]}' "
                                f"should be valid "
                                f"but gives "
                                f"{step_solution}"
                            )

                    # The first invalid step must actually change
                    # the solution.
                    invalid_step_solution = solve_eq(
                        steps[first_invalid_step - 1]
                    )

                    if invalid_step_solution == {
                        expected_answer
                    }:
                        report.err(
                            f"{mid}: line "
                            f"{first_invalid_step} "
                            f"'{steps[first_invalid_step - 1]}' "
                            f"should be the first "
                            f"invalid step but is valid"
                        )

                # ==========================================================
                # Answer mutation
                # ==========================================================

                elif layer == "answer":

                    if (
                        mutation[
                            "final_answer_text"
                        ].strip()
                        == question[
                            "final_answer_text"
                        ].strip()
                    ):
                        report.err(
                            f"{mid}: answer mutation "
                            f"is identical to the "
                            f"correct final answer"
                        )

            except Exception as exc:
                report.err(
                    f"{mid}: cannot parse ({exc})"
                )

        # ------------------------------------------------------------------
        # Challenge AI
        # ------------------------------------------------------------------

        challenge_ai = question.get(
            "challenge_ai",
            {},
        )

        correct = challenge_ai.get(
            "correct",
            {},
        )

        if "x_value" in correct:

            try:
                challenge_answer = value(
                    correct["x_value"]
                )

                if challenge_answer != expected_answer:
                    report.err(
                        f"{qid}: Challenge AI correct "
                        f"x_value "
                        f"{correct['x_value']} "
                        f"!= answer "
                        f"{expected_answer}"
                    )

            except Exception as exc:
                report.err(
                    f"{qid}: cannot parse Challenge AI "
                    f"correct x_value "
                    f"'{correct.get('x_value')}' "
                    f"({exc})"
                )

        # Important:
        # Only questions whose V1 role is "incorrect" need
        # an incorrect Challenge AI final-answer check.
        incorrect = challenge_ai.get(
            "incorrect",
            {},
        )

        if (
            challenge_ai.get("v1_set_role")
            == "incorrect"
            and incorrect.get(
                "final_answer_text",
                "",
            ).strip()
            == question[
                "final_answer_text"
            ].strip()
        ):
            report.err(
                f"{qid}: Challenge AI incorrect "
                f"version reaches the correct "
                f"final answer"
            )


# ============================================================================
# D. Evaluation-readiness notes
# ============================================================================

def eval_readiness(bank, report):
    """
    Print information that will be useful when constructing D2a
    and the later evaluation sets.
    """

    questions = bank["questions"]

    mutations = [
        mutation
        for question in questions
        for mutation in question.get(
            "mutations",
            [],
        )
    ]

    # ------------------------------------------------------------------
    # Layer distribution
    # ------------------------------------------------------------------

    layers = Counter(
        mutation["layer"]
        for mutation in mutations
    )

    print(
        "Mutations by layer:   ",
        dict(sorted(layers.items())),
    )

    # ------------------------------------------------------------------
    # Error distribution
    #
    # E4-01 ... E4-08 are collapsed into E4.
    # ------------------------------------------------------------------

    categories = Counter(
        collapse(mutation["error"])
        for mutation in mutations
    )

    category_output = {
        f"E{i}": categories.get(
            f"E{i}",
            0,
        )
        for i in range(1, 8)
    }

    print(
        "Mutations by category:",
        category_output,
    )

    missing_categories = [
        f"E{i}"
        for i in range(1, 8)
        if categories.get(
            f"E{i}",
            0,
        ) == 0
    ]

    if missing_categories:
        report.err(
            f"no mutation covers "
            f"{missing_categories}"
        )

    # ------------------------------------------------------------------
    # Challenge AI incorrect error types
    #
    # Q14 is correct and therefore excluded.
    # ------------------------------------------------------------------

    challenge_ai_errors = Counter(
        question["challenge_ai"][
            "incorrect"
        ]["error"]
        for question in questions
        if question[
            "challenge_ai"
        ].get("v1_set_role")
        == "incorrect"
    )

    print(
        "Challenge AI incorrect error types:",
        dict(sorted(
            challenge_ai_errors.items()
        )),
    )

    # ------------------------------------------------------------------
    # D2a step-localisation count
    #
    # Only execution mutations have first_invalid_step.
    # Therefore this should be 30 in V1.3.
    # ------------------------------------------------------------------

    execution_count = layers.get(
        "execution",
        0,
    )

    print(
        "D2a step-localisation cases "
        "(execution mutations):",
        execution_count,
    )

    # ------------------------------------------------------------------
    # Modelling mutations missing variable_definition
    #
    # This is intentionally NOT an error.
    #
    # build_d2a.py will inherit the parent question's
    # variable_definition.
    # ------------------------------------------------------------------

    missing_variable_definition = [
        mutation["id"]
        for mutation in mutations
        if (
            mutation["layer"] == "modelling"
            and "variable_definition"
            not in mutation
        )
    ]

    if missing_variable_definition:

        report.note(
            f"{len(missing_variable_definition)} "
            f"modelling mutations have no "
            f"variable_definition - "
            f"build_d2a.py should default them "
            f"to the question's own definition: "
            f"{', '.join(missing_variable_definition)}"
        )

    # ------------------------------------------------------------------
    # Modelling mutations with exactly the same equation string
    #
    # These are cases where the modelling error is represented
    # by a variable-definition mismatch rather than an equation
    # mismatch.
    # ------------------------------------------------------------------

    by_id = {
        question["question_id"]: question
        for question in questions
    }

    same_equation_mutations = []

    for mutation in mutations:

        if mutation["layer"] != "modelling":
            continue

        parent_qid = question_id_from_mutation(
            mutation["id"]
        )

        parent_question = by_id.get(
            parent_qid
        )

        if parent_question is None:
            continue

        if same_equation(
            mutation["equation"],
            parent_question["equation"],
        ):
            same_equation_mutations.append(
                mutation["id"]
            )

    if same_equation_mutations:

        report.note(
            "equation identical to standard - "
            "diagnosable only from "
            "variable_definition: "
            + ", ".join(
                same_equation_mutations
            )
        )

    # ------------------------------------------------------------------
    # E4 subtype coverage
    # ------------------------------------------------------------------

    subtypes = sorted(
        {
            mutation["error"]
            for mutation in mutations
            if str(mutation["error"]).startswith(
                "E4-"
            )
        }
    )

    if subtypes:

        report.note(
            "subtypes present "
            f"({', '.join(subtypes)}) - "
            "collapse to E4 for the "
            "confusion matrix"
        )


# ============================================================================
# Final reporting
# ============================================================================

def finish(report, question_count):
    """
    Print notes and errors, then return an exit status.
    """

    if report.notes:

        print("\nNotes (not errors):")

        for note in report.notes:
            print(
                "  ·",
                note,
            )

    if report.errors:

        print(
            f"\n✗ {len(report.errors)} problem(s):"
        )

        for error in report.errors:
            print(
                "  -",
                error,
            )

        sys.exit(1)

    print(
        f"\n✓ All {question_count} "
        f"questions passed."
    )


# ============================================================================
# Main
# ============================================================================

def main(path):
    """
    Load the question bank and run all checks.
    """

    path = Path(path)

    if not path.exists():
        print(
            f"✗ File not found: {path}"
        )
        sys.exit(1)

    try:
        bank = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        print(
            f"✗ Invalid JSON in {path}: "
            f"{exc}"
        )
        sys.exit(1)
    except OSError as exc:
        print(
            f"✗ Cannot read {path}: "
            f"{exc}"
        )
        sys.exit(1)

    if not isinstance(bank, dict):
        print(
            "✗ Question bank root must be "
            "a JSON object."
        )
        sys.exit(1)

    print(
        f"Validating {path} "
        f"(version {bank.get('version', '?')})\n"
    )

    report = Report()

    # Structure must be valid before counts/maths can safely assume
    # the expected fields exist.
    check_structure(
        bank,
        report,
    )

    if report.errors:
        finish(
            report,
            len(bank.get("questions", [])),
        )
        return

    check_counts(
        bank,
        report,
    )

    check_maths(
        bank,
        report,
    )

    eval_readiness(
        bank,
        report,
    )

    finish(
        report,
        len(bank["questions"]),
    )


# ============================================================================
# CLI entry point
# ============================================================================

if __name__ == "__main__":
    main(
        sys.argv[1]
        if len(sys.argv) > 1
        else "data/question_bank.json"
    )