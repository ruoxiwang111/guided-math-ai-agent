"""The D1 scorer must give 100% when the 'model' returns the reference itself (oracle)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import eval_structure_d1 as ev  # noqa: E402
from core.structure import extract_structure  # noqa: E402

CASES = json.loads((ROOT / "eval" / "structure_cases.json").read_text(encoding="utf-8"))["cases"]


def test_oracle_scores_perfectly():
    backend = ev.OracleBackend(CASES)
    rows = [ev.score_case(c, extract_structure(c["input_text"], backend)) for c in CASES]
    s = ev.summarise(rows)
    assert s["scope_accuracy"] == 1 and s["equation_correctness"] == 1
    assert s["field_accuracy_unknown_known"] == 1 and s["consistent_but_wrong_rate"] == 0


def test_learner_equation_copied_into_structure_counts_as_consistent_but_wrong():
    case = next(c for c in CASES if c["source"] == "with_learner_work")

    class CopiesLearner(ev.OracleBackend):
        def complete(self, system, user):
            out = super().complete(system, user)
            if "独立解" in system:
                return json.dumps({"parts": [{"label": "x", "value": "495/2"}]})
            d = json.loads(out)
            d["equation"] = "0.8*(x-10)=190"                       # the learner's wrong equation
            d["verification_conditions"] = [{"description": "d", "lhs": "0.8*(x-10)", "op": "==", "rhs": "190"}]
            return json.dumps(d, ensure_ascii=False)

    row = ev.score_case(case, extract_structure(case["input_text"], CopiesLearner([case])))
    assert row["decision"] == "in_scope" and row["equation_correct"] is False and row["consistent_but_wrong"] is True