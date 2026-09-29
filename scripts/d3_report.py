"""
D3 — learning / transfer report from the logs (evaluation_plan: D3).

For every independent attempt (logs/practice/*.json) it reports the five D3 measures:

    1. independent        fully correct AND no help requested
    2. correct            final answer correct (and model / execution separately)
    3. repeated error     an error type (category, or the E7 rule) this learner already made in an
                          EARLIER guided session (logs/guided/*.jsonl, same learner_id) shows up again
    4. duration           seconds from start to submit
    5. help requested     the learner pressed "我需要帮助"

Learners are linked only by the anonymous learner_id chosen in the browser. Attempts without a
learner_id are reported but cannot be linked to earlier guided sessions.

Run from the project root:
    python scripts/d3_report.py                       # all attempts
    python scripts/d3_report.py --learner L-3f2a9c    # one learner
Outputs eval/results/d3/d3_report.csv and d3_report.json.

Note: this measures the attempts that were made. Whether it is evidence of learning depends on
who made them — attempts by the developer or by someone who already knows the method are a
functional check only (see evaluation_plan: D3 needs real learners).
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def error_keys(category, rule):
    """E7 errors are compared by rule (移项 vs 去括号 are different skills); others by category."""
    if category == "E7" and rule:
        return {f"E7:{rule}"}
    return {category} if category else set()


def load_guided(log_dir: Path):
    """[{learner_id, started, question_id, errors:set, hints, revealed}] per guided session."""
    out = []
    for path in sorted(log_dir.glob("*.jsonl")):
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        start = next((e for e in events if e.get("event") == "session_start"), None)
        if start is None:
            continue
        errs = set()
        for e in events:
            if e.get("event") == "diagnosis" and e.get("diagnosis_status") == "diagnosed":
                errs |= error_keys(e.get("diagnosed_error"), e.get("rule"))
        out.append({"learner_id": start.get("learner_id"), "started": start.get("timestamp"),
                    "question_id": start.get("question_id"), "errors": errs,
                    "hints": sum(e.get("event") == "hint" for e in events),
                    "revealed": any(e.get("event") == "reveal_step" for e in events), "file": path.name})
    return out


def load_practice(pdir: Path):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(pdir.glob("*.json"))]


def rows(guided, practice, learner=None):
    out = []
    for a in practice:
        if learner and a.get("learner_id") != learner:
            continue
        res = a.get("result") or {}
        attempt_errors = set()
        for e in res.get("errors", []):
            attempt_errors |= error_keys(e.get("category"), e.get("rule"))
        earlier = [g for g in guided if a.get("learner_id") and g["learner_id"] == a.get("learner_id")
                   and g["started"] and g["started"] < a["started_at"]]
        prior = set().union(*(g["errors"] for g in earlier)) if earlier else set()
        repeated = sorted(prior & attempt_errors)
        out.append({
            "learner_id": a.get("learner_id") or "",
            "practice_id": a["practice_id"],
            "question_id": a["question_id"],
            "started_at": a["started_at"],
            "submitted": bool(a.get("submitted_at")),
            "independent": bool(res.get("fully_correct")) and not a.get("help_requested"),
            "answer_correct": res.get("answer_correct"),
            "model_correct": res.get("model_correct"),
            "execution_correct": res.get("execution_correct"),
            "attempt_errors": ";".join(sorted(attempt_errors)),
            "earlier_guided_sessions": len(earlier),
            "earlier_errors": ";".join(sorted(prior)),
            "repeated_errors": ";".join(repeated),
            "transfer": ("—" if not earlier else "repeated earlier error" if repeated
                         else "no repeat" if res else "not submitted"),
            "duration_seconds": a.get("duration_seconds"),
            "help_requested": bool(a.get("help_requested")),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--learner")
    ap.add_argument("--guided-dir", default=str(ROOT / "logs" / "guided"))
    ap.add_argument("--practice-dir", default=str(ROOT / "logs" / "practice"))
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "results" / "d3"))
    args = ap.parse_args()

    table = rows(load_guided(Path(args.guided_dir)), load_practice(Path(args.practice_dir)), args.learner)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if table:
        with (out / "d3_report.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(table[0]))
            w.writeheader()
            w.writerows(table)
    (out / "d3_report.json").write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")

    done = [r for r in table if r["submitted"]]
    print(f"D3 attempts: {len(table)} ({len(done)} submitted, learners: {len({r['learner_id'] for r in table})})")
    for r in table:
        print(f"  {r['learner_id'] or '(no id)':<10} {r['question_id']:<12} "
              f"independent={r['independent']!s:<5} answer={r['answer_correct']!s:<5} "
              f"model={r['model_correct']!s:<5} exec={r['execution_correct']!s:<5} "
              f"help={r['help_requested']!s:<5} {r['duration_seconds'] or '-'}s  "
              f"errors=[{r['attempt_errors']}] earlier=[{r['earlier_errors']}] → {r['transfer']}")
    if done:
        rate = lambda k: sum(1 for r in done if r[k]) / len(done)  # noqa: E731
        print(f"\n  independent {rate('independent'):.0%}   answer correct {rate('answer_correct'):.0%}   "
              f"help requested {rate('help_requested'):.0%}")
        linked = [r for r in done if r["earlier_guided_sessions"]]
        if linked:
            rep = sum(1 for r in linked if r["repeated_errors"]) / len(linked)
            print(f"  linked to earlier guided sessions: {len(linked)}   repeated an earlier error: {rep:.0%}")
    print(f"\n✓ wrote {out / 'd3_report.csv'}")


if __name__ == "__main__":
    main()
