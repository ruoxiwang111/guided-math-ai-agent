"""
Why was a D1 input rejected? Re-runs structure extraction on chosen cases and prints every check with
its detail, the raw extraction and the independent solution (evaluation_plan §6.4, error analysis).

This is a diagnostic, not a scored run: it does not change any code or any headline number, and its
output is kept apart from eval/results/structure_d1/.

Run from the project root (needs DEEPSEEK_API_KEY):
    python scripts/inspect_d1.py D1-12 D1-13 D1-23 D1-25 D1-28 D1-30
    python scripts/inspect_d1.py D1-30 --runs 5
Outputs eval/results/structure_d1_inspect/<timestamp>.json
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.structure import PROMPT_VERSION, extract_structure  # noqa: E402


def inspect(case, backend):
    ex = extract_structure(case["input_text"], backend)
    raw = ex.raw or {}
    return {
        "case_id": case["case_id"], "scope": ex.scope, "consistency": ex.consistency, "error": ex.error,
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in ex.checks],
        "raw_equation": raw.get("equation"), "raw_known_quantities": raw.get("known_quantities"),
        "raw_answer_parts": raw.get("answer_parts"), "raw_relationship": raw.get("relationship"),
        "independent": ex.independent,
    }


def show(r):
    print(f"\n=== {r['case_id']}  scope={r['scope']}  consistency={r['consistency']}"
          + (f"  error={r['error']}" if r["error"] else ""))
    print(f"  equation: {r['raw_equation']}")
    print(f"  known:    {json.dumps(r['raw_known_quantities'], ensure_ascii=False)}")
    for c in r["checks"]:
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}")
    print(f"  independent: {json.dumps(r['independent'], ensure_ascii=False)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", nargs="+")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    data = json.loads((ROOT / "eval" / "structure_cases.json").read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for c in (data["cases"] if isinstance(data, dict) else data)}
    missing = [c for c in args.cases if c not in cases]
    if missing:
        sys.exit(f"unknown case ids: {missing}")

    from core.llm_client import default_backend
    backend = default_backend()
    if backend is None:
        sys.exit("no LLM backend: set DEEPSEEK_API_KEY in .env")

    out = {"prompt_version": PROMPT_VERSION, "backend": backend.describe(), "results": []}
    for k in range(1, args.runs + 1):
        print(f"\n######## run {k}")
        for cid in args.cases:
            r = dict(inspect(cases[cid], backend), run=k)
            show(r)
            out["results"].append(r)

    folder = ROOT / "eval" / "results" / "structure_d1_inspect"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n✓ wrote {path}")


if __name__ == "__main__":
    main()
