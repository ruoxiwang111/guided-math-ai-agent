"""
D2b — check the annotation workbook and import it into eval/diagnostic_cases.json
(evaluation_plan §4.2–4.3, §5.1–5.2).

Run from the project root:
    python scripts/d2b_import.py --check      # validate + composition report, writes nothing
    python scripts/d2b_import.py              # validate, assign dev/test, write the cases

What it does
    1. validates every row (errors stop the import; warnings are printed for you to look at);
    2. reports the §4.2 composition requirements (40–60 cases, ≥5 per E1–E7, 20–30% correct, …);
    3. assigns the 30/70 dev/test split, stratified by primary category, with a fixed seed.
       A case keeps the split it already had, so adding cases later never moves old ones;
    4. replaces the hand-crafted cases in eval/diagnostic_cases.json. D2a (source = mutation)
       is left exactly as it is.

Freezing (§5.1): once a case is `reviewed` and imported, its reference labels may change only to
correct a documented annotation error:
    python scripts/d2b_import.py --allow-relabel "D2b-014: step 3 not 2, miscounted"
which is appended to eval/annotation_corrections.md.

Reference labels come only from the workbook; this script never runs the diagnosis.
"""
import argparse
import json
import math
import random
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d2b_io as io  # noqa: E402

SEED = 20260930
DEV_RATIO = 0.3


def composition(cases: list[dict], second_ids: set) -> list[tuple[bool, str]]:
    n = len(cases)
    prim = Counter(c["primary_error"] for c in cases if c["reference_status"] == "incorrect")
    status = Counter(c["reference_status"] for c in cases)
    tags = Counter(t for c in cases for t in c["tags"])
    correct = status["correct"]
    answer_wrong = sum(c["layer"] == "answer" and c["reference_status"] != "correct" for c in cases)
    correct_answer_only = sum(c["layer"] == "answer" and c["reference_status"] == "correct" for c in cases)
    multi = sum(bool(c["secondary_errors"]) for c in cases)
    line_by_line = sum(c["layer"] == "execution" and c["first_invalid_step"] is not None for c in cases)
    second = len(second_ids & {c["case_id"] for c in cases})
    share = correct / n if n else 0
    out = [(40 <= n <= 60, f"total cases: {n} (need 40–60)")]
    for e in io.CATS:
        out.append((prim[e] >= 5, f"{e}: {prim[e]} (need ≥5)"))
    out += [
        (0.2 <= share <= 0.3, f"reference-correct: {correct} = {share:.0%} (need 20–30%)"),
        (tags["equivalent_equation"] >= 1, f"  of which equivalent equations (tag equivalent_equation): {tags['equivalent_equation']}"),
        (tags["alt_definition"] >= 1, f"  alternative definitions (tag alt_definition): {tags['alt_definition']}"),
        (tags["alt_working"] >= 1, f"  alternative working (tag alt_working): {tags['alt_working']}"),
        (correct_answer_only >= 1, f"  correct final-answer-only: {correct_answer_only}"),
        (status["uncertain"] >= 5, f"reference-uncertain: {status['uncertain']} (need ≥5)"),
        (tags["ambiguous_notation"] >= 3, f"ambiguous notation (tag ambiguous_notation): {tags['ambiguous_notation']} (need ≥3)"),
        (answer_wrong >= 5, f"final-answer-only, not correct: {answer_wrong} (need ≥5)"),
        (multi >= 5, f"multi-error (secondary_errors): {multi} (need ≥5)"),
        (line_by_line >= 10, f"line-by-line with first_invalid_step: {line_by_line} (need ≥10)"),
        (n and second >= math.ceil(0.2 * n), f"second-annotated: {second} (need ≥{math.ceil(0.2 * n) if n else 0}, 20%)"),
        (all(c["review_status"] in ("reviewed", "adjudicated") for c in cases),
         f"reviewed: {sum(c['review_status'] in ('reviewed', 'adjudicated') for c in cases)}/{n} (all needed before freezing)"),
    ]
    return out


def assign_splits(cases: list[dict], previous: dict, seed: int = SEED, dev_ratio: float = DEV_RATIO) -> None:
    """Stratified 30/70; cases already split keep their split."""
    by = {}
    for c in cases:
        by.setdefault(io.stratum(c), []).append(c)
    for name, group in sorted(by.items()):
        kept = [c for c in group if c["case_id"] in previous]
        for c in kept:
            c["split"] = previous[c["case_id"]]
        new = sorted((c for c in group if c["case_id"] not in previous), key=lambda c: c["case_id"])
        random.Random(f"{seed}:{name}").shuffle(new)
        want_dev = round(dev_ratio * len(group)) - sum(c["split"] == "dev" for c in kept)
        for i, c in enumerate(new):
            c["split"] = "dev" if i < max(want_dev, 0) else "test"


def relabelled(old: dict, new: dict) -> list[str]:
    return [f for f in io.REFERENCE_FIELDS if old.get(f) != new.get(f)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workbook", default=str(io.WORKBOOK))
    ap.add_argument("--cases", default=str(io.CASES_JSON))
    ap.add_argument("--second", default=str(io.SECOND_JSON))
    ap.add_argument("--corrections", default=str(io.CORRECTIONS_MD))
    ap.add_argument("--check", action="store_true", help="validate and report only; write nothing")
    ap.add_argument("--allow-relabel", metavar="REASON", help="permit label changes to reviewed cases, with a reason")
    args = ap.parse_args()

    bank = io.load_bank()
    rows = io.read_workbook(Path(args.workbook))
    errors, warnings = io.validate(rows, bank)
    print(f"D2b workbook: {len(rows)} filled row(s)")
    for w in warnings:
        print(f"  ! {w}")
    for e in errors:
        print(f"  ✗ {e}")

    data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    old = {c["case_id"]: c for c in data["cases"] if c.get("source") == "hand_crafted"}
    cases = [io.to_record(r, split="") for r in rows] if not errors else []
    second_path = Path(args.second)
    second_ids = set(json.loads(second_path.read_text(encoding="utf-8")).get("case_ids", [])) \
        if second_path.exists() else set()

    frozen_changes, removed = [], []
    if not errors:
        if cases:
            print("\nComposition (evaluation_plan §4.2):")
            for ok, line in composition(cases, second_ids):
                print(f"  {'✓' if ok else '✗'} {line}")
        for c in cases:
            prev = old.get(c["case_id"])
            if prev and prev.get("review_status") in ("reviewed", "adjudicated"):
                fields = relabelled(prev, c)
                if fields:
                    frozen_changes.append((c["case_id"], fields, prev))
        removed = [cid for cid, c in old.items() if c.get("review_status") in ("reviewed", "adjudicated")
                   and cid not in {x["case_id"] for x in cases}]
        if (frozen_changes or removed) and not args.allow_relabel:
            for cid, fields, _ in frozen_changes:
                errors.append(f"{cid}: reference labels {fields} changed after the case was reviewed")
            for cid in removed:
                errors.append(f"{cid}: a reviewed case was removed from the workbook")
            errors.append("frozen labels change only for a documented annotation error: "
                          "re-run with --allow-relabel \"<case id: reason>\"")
            for e in errors[-(len(frozen_changes) + len(removed) + 1):]:
                print(f"  ✗ {e}")

    if errors:
        sys.exit(f"\n✗ {len(errors)} error(s) — nothing written. Fix the workbook and run again.")
    if args.check:
        print("\n✓ check only — nothing written")
        return

    assign_splits(cases, {cid: c["split"] for cid, c in old.items() if c.get("split")})
    if args.allow_relabel and (frozen_changes or removed):
        lines = [f"\n## {date.today().isoformat()} — {args.allow_relabel}\n"]
        for cid, fields, prev in frozen_changes:
            new = next(c for c in cases if c["case_id"] == cid)
            for f in fields:
                lines.append(f"- {cid} `{f}`: {prev.get(f)!r} → {new.get(f)!r}")
        lines += [f"- {cid}: removed" for cid in removed]
        p = Path(args.corrections)
        head = "" if p.exists() else "# D2b annotation corrections\n\nChanges to reviewed reference labels (evaluation_plan §5.1).\n"
        p.write_text((p.read_text(encoding="utf-8") if p.exists() else head) + "\n".join(lines) + "\n", encoding="utf-8")
        print(f"  logged the relabel in {p.name}")

    data["cases"] = [c for c in data["cases"] if c.get("source") != "hand_crafted"] + cases
    Path(args.cases).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    split = Counter(c["split"] for c in cases)
    print(f"\n✓ wrote {len(cases)} D2b case(s) to {Path(args.cases).name}: {split['dev']} dev, {split['test']} test"
          f" (D2a untouched: {sum(c.get('source') == 'mutation' for c in data['cases'])} cases)")


if __name__ == "__main__":
    main()
