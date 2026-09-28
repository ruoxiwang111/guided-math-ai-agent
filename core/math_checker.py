"""
core/math_checker.py — deterministic maths checks on normalised learner input.

Implements error_taxonomy.md §10.6 (compare consecutive equations) on top of
core/normalizer.py. It answers only mathematical questions:

    - What is the solution set of this equation?
    - Is this line equivalent to the previous one (same solution set)?
    - Where is the first line that changes the solution set?
    - In a chain  a = b = c,  are the middle segments actually equal?
    - Does a value satisfy the question's verification conditions?

It never assigns E1–E7. That is diagnosis.py's job; this module only returns
the evidence (which line, which kind of inconsistency).

Public API
    solution_set(equation)                     -> SolutionSet
    equivalent(eq_a, eq_b)                     -> bool | None
    check_steps(steps, reference_equation=None) -> StepCheck
    check_value(value, reference_equation)     -> bool | None
    check_conditions(conditions, value)        -> list[ConditionResult]
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sympy import FiniteSet, S, Symbol, nsimplify, solveset, together, fraction, Poly
from sympy.parsing.sympy_parser import parse_expr, rationalize, standard_transformations

from core.normalizer import EMPTY, EQUATION, EXPRESSION, NOT_MATH, OK, NormalizedLine, normalize_line, normalize_steps

X = Symbol("x")
TRANSFORMS = standard_transformations + (rationalize,)   # 0.8 → 4/5, exact arithmetic

# solution-set kinds
UNIQUE = "unique"          # exactly one solution (the normal linear case)
ALL = "all"                # identity, e.g. 0 = 0
NONE = "none"              # contradiction, e.g. 0 = 5
OTHER = "other"            # anything else (non-linear, several solutions)

# overall StepCheck status
ALL_VALID = "all_valid"
INVALID_FOUND = "invalid_step_found"
UNCERTAIN = "uncertain"            # an unreadable / ambiguous line blocks the check
NO_EQUATION = "no_equation"

# reasons for a line being the first invalid step
START_DIFFERS = "start_differs_from_reference"
TRANSITION_CHANGES_SOLUTION = "transition_changes_solution"
CHAIN_SEGMENT_MISMATCH = "chain_segment_mismatch"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SolutionSet:
    kind: str
    values: frozenset = frozenset()
    linear: bool = True

    def __str__(self):
        if self.kind == UNIQUE:
            return f"{{x = {next(iter(self.values))}}}"
        return {ALL: "all x", NONE: "no solution"}.get(self.kind, str(set(self.values)) or self.kind)


@dataclass
class LineCheck:
    index: int                       # 1-based position in the learner's working
    original: str
    normalized: str | None
    status: str                      # normalizer status
    solutions: SolutionSet | None = None
    equivalent_to_previous: bool | None = None   # vs previous equation line (or reference for line 1)
    chain_ok: bool | None = None
    note: str | None = None


@dataclass
class StepCheck:
    status: str
    lines: list[LineCheck] = field(default_factory=list)
    first_invalid_step: int | None = None        # 1-based, over ALL submitted lines
    reason: str | None = None
    blocked_at: int | None = None                # line that stopped the check (ambiguous / unreadable)
    reference_solutions: SolutionSet | None = None
    final_value: object = None                   # x value if the last equation line is "x = c"
    final_matches_reference: bool | None = None
    consistent_after_error: bool | None = None   # later lines follow the wrong line correctly

    def summary(self) -> str:
        if self.status == INVALID_FOUND:
            return f"first invalid step: line {self.first_invalid_step} ({self.reason})"
        if self.status == UNCERTAIN:
            return f"uncertain: line {self.blocked_at} cannot be read safely"
        return self.status


@dataclass
class ConditionResult:
    description: str
    holds: bool | None


# ---------------------------------------------------------------------------
# Parsing and solving
# ---------------------------------------------------------------------------

def _expr(text: str):
    return parse_expr(text, local_dict={"x": X}, transformations=TRANSFORMS)


def _sides(normalized: str):
    lhs, rhs = normalized.split("=")
    return _expr(lhs), _expr(rhs)


def _solution_set_from_sides(lhs, rhs) -> SolutionSet:
    diff = together(lhs - rhs)
    num, den = fraction(diff)
    linear = True
    if den.has(X):
        linear = False
    else:
        try:
            linear = Poly(num, X).degree() <= 1
        except Exception:  # noqa: BLE001
            linear = False

    sol = solveset(lhs - rhs, X, domain=S.Reals)
    if sol == S.Reals:
        return SolutionSet(ALL, linear=linear)
    if sol == S.EmptySet:
        return SolutionSet(NONE, linear=linear)
    if isinstance(sol, FiniteSet):
        vals = frozenset(nsimplify(v, rational=True) for v in sol)
        return SolutionSet(UNIQUE if len(vals) == 1 else OTHER, vals, linear=linear)
    return SolutionSet(OTHER, linear=linear)


def solution_set(equation: str | NormalizedLine) -> SolutionSet | None:
    """Solution set of one equation. Returns None if the line cannot be read safely."""
    line = equation if isinstance(equation, NormalizedLine) else normalize_line(equation)
    if line.status != OK or line.kind != EQUATION:
        return None
    return _solution_set_from_sides(*_sides(line.normalized))


def equivalent(eq_a, eq_b) -> bool | None:
    """Same solution set? None if either side cannot be read."""
    a, b = solution_set(eq_a), solution_set(eq_b)
    if a is None or b is None:
        return None
    return _same(a, b)


def _same(a: SolutionSet, b: SolutionSet) -> bool:
    return a.kind == b.kind and a.values == b.values


def _chain_ok(line: NormalizedLine) -> tuple[bool, str | None]:
    """For a = b = c, every segment after the first must equal the next one."""
    parts = [_expr(p) for p in line.chain_parts]
    for i in range(1, len(parts) - 1):
        if (parts[i] - parts[i + 1]).simplify() != 0:
            return False, f"'{line.chain_parts[i]}' ≠ '{line.chain_parts[i + 1]}'"
    return True, None


def _final_value(line: NormalizedLine):
    """x value if the line has the form  x = c  or  c = x."""
    lhs, rhs = _sides(line.normalized)
    if lhs == X and not rhs.has(X):
        return nsimplify(rhs, rational=True)
    if rhs == X and not lhs.has(X):
        return nsimplify(lhs, rational=True)
    return None


# ---------------------------------------------------------------------------
# Step checking
# ---------------------------------------------------------------------------

def check_steps(steps, reference_equation: str | None = None) -> StepCheck:
    """
    Check ordered working line by line.

    steps: a string (split into lines) or a list of lines.
    reference_equation: the question's standard equation. When given, line 1 must
        be equivalent to it; otherwise line 1 is taken as the learner's starting point.

    Words-only lines (解/答/设 …) and empty lines are skipped. An ambiguous or
    unreadable line before the first invalid step makes the result UNCERTAIN –
    the checker never guesses (error_taxonomy.md §10.2, §10.5).
    """
    normalized = normalize_steps(steps)
    result = StepCheck(status=NO_EQUATION)

    ref_set = solution_set(reference_equation) if reference_equation else None
    result.reference_solutions = ref_set

    previous: SolutionSet | None = ref_set
    first_equation_seen = False
    wrong_line_set: SolutionSet | None = None
    consistent_after = None

    for i, nl in enumerate(normalized, start=1):
        lc = LineCheck(index=i, original=nl.original, normalized=nl.normalized, status=nl.status)
        result.lines.append(lc)

        if nl.status in (NOT_MATH, EMPTY):
            continue
        if nl.status != OK:
            lc.note = "; ".join(x.message for x in nl.issues)
            if result.first_invalid_step is None:
                result.status = UNCERTAIN
                result.blocked_at = i
                return result
            continue
        if nl.kind == EXPRESSION:
            lc.note = "expression line (no '='), not compared"
            continue

        sol = _solution_set_from_sides(*_sides(nl.normalized))
        lc.solutions = sol
        if not sol.linear:
            lc.note = "non-linear in x (outside V1); compared by solution set only"

        chain_ok, chain_msg = (True, None)
        if nl.chain_parts:
            chain_ok, chain_msg = _chain_ok(nl)
            lc.chain_ok = chain_ok

        if previous is None:                      # no reference: first equation is the start
            lc.equivalent_to_previous = None
        else:
            lc.equivalent_to_previous = _same(sol, previous)

        if result.first_invalid_step is None:
            if not chain_ok:
                result.first_invalid_step, result.reason = i, CHAIN_SEGMENT_MISMATCH
                lc.note = chain_msg
                wrong_line_set = sol
            elif lc.equivalent_to_previous is False:
                result.first_invalid_step = i
                result.reason = START_DIFFERS if not first_equation_seen else TRANSITION_CHANGES_SOLUTION
                wrong_line_set = sol
        else:
            # after the error: does the learner continue correctly from the wrong line?
            same_as_wrong = _same(sol, wrong_line_set)
            consistent_after = same_as_wrong if consistent_after is None else (consistent_after and same_as_wrong)
            wrong_line_set = sol

        previous = sol
        first_equation_seen = True

    equation_lines = [lc for lc, nl in zip(result.lines, normalized) if lc.solutions is not None]
    if not equation_lines:
        result.status = NO_EQUATION
        return result

    last = normalized[equation_lines[-1].index - 1]
    result.final_value = _final_value(last)
    if ref_set is not None and ref_set.kind == UNIQUE and result.final_value is not None:
        result.final_matches_reference = result.final_value in ref_set.values

    result.consistent_after_error = consistent_after
    result.status = INVALID_FOUND if result.first_invalid_step else ALL_VALID
    return result


# ---------------------------------------------------------------------------
# Answers and verification conditions
# ---------------------------------------------------------------------------

def check_value(value, reference_equation: str) -> bool | None:
    """Does x = value satisfy the reference equation?"""
    ref = solution_set(reference_equation)
    if ref is None:
        return None
    v = nsimplify(S(value), rational=True)
    if ref.kind == ALL:
        return True
    return v in ref.values


def check_conditions(conditions: list[dict], value) -> list[ConditionResult]:
    """Evaluate question-bank verification_conditions at x = value."""
    v = nsimplify(S(value), rational=True)
    out = []
    for c in conditions:
        try:
            lhs = _expr(c["lhs"]).subs(X, v)
            if c["op"] == "integer":
                holds = bool(lhs.is_integer)
            else:
                rhs = _expr(c["rhs"]).subs(X, v)
                holds = bool({"==": lhs == rhs, ">": lhs > rhs, "<": lhs < rhs,
                              ">=": lhs >= rhs, "<=": lhs <= rhs}[c["op"]])
        except Exception:  # noqa: BLE001
            holds = None
        out.append(ConditionResult(c.get("description", ""), holds))
    return out