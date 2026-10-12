"""
D2b dataset pipeline: workbook → validation → import (split, freeze) → evaluation → second annotator.

The rows below are pipeline fixtures written for these tests only; they are not D2b cases.

Run from the project root:
    python -m pytest tests/test_d2b_dataset.py -v
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import d2b_io as io  # noqa: E402
import d2b_second  # noqa: E402
import eval_diagnosis_d2b as ev  # noqa: E402
from d2b_import import assign_splits  # noqa: E402
from d2b_template import build  # noqa: E402

ROWS = [
    dict(case_id="T-01", question_id="Q01", layer="modelling", variable_definition="设小华x岁",
         equation="x+(x+5)=25", reference_status="correct", tags="equivalent_equation", review_status="reviewed"),
    dict(case_id="T-02", question_id="Q01", layer="modelling", variable_definition="设小华x岁",
         equation="x+5=25", reference_status="incorrect", primary_error="E3", evidence_level="A",
         evidence="只写了小明", review_status="reviewed"),
    dict(case_id="T-03", question_id="Q03", layer="modelling", variable_definition="设原价x元",
         equation="x-0.8=160", reference_status="incorrect", primary_error="E4", error_subtype="E4-06",
         review_status="reviewed"),
    dict(case_id="T-04", question_id="Q01", layer="execution", variable_definition="设小华x岁",
         steps="2x+5=25\n2x=30\nx=15", reference_status="incorrect", primary_error="E7",
         first_invalid_step="2", review_status="reviewed"),
    dict(case_id="T-05", question_id="Q01", layer="execution", steps="x+(x+5)=25||2x+5=25||2x=20||x=10",
         reference_status="correct", tags="alt_working", review_status="reviewed"),
    dict(case_id="T-06", question_id="Q01", layer="answer", final_answer_text="10和15",
         reference_status="uncertain", review_status="reviewed"),
]


def workbook(path, rows):
    build(path, io.COLUMNS, io.load_bank(), rows, "test")
    return path


@pytest.fixture()
def env(tmp_path):
    cases = tmp_path / "diagnostic_cases.json"
    # the repository's file now holds the real, frozen D2b cases; the tests start from D2a only
    data = json.loads(io.CASES_JSON.read_text(encoding="utf-8"))
    data["cases"] = [c for c in data["cases"] if c.get("source") != "hand_crafted"]
    cases.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp_path, workbook(tmp_path / "d2b.xlsx", ROWS), cases


def run(script, *args):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=120)
    return r.returncode, r.stdout + r.stderr


def do_import(tmp, wb, cases, *extra):
    return run("d2b_import.py", "--workbook", wb, "--cases", cases, "--second", tmp / "second.json",
               "--corrections", tmp / "corrections.md", "--generation-log", tmp / "no_generation_log.json", *extra)


# ---------------------------------------------------------------- validation

def test_rows_are_read_and_blank_rows_skipped(tmp_path):
    rows = io.read_workbook(workbook(tmp_path / "w.xlsx", ROWS + [{"case_id": "T-99"}]))
    assert [r["case_id"] for r in rows] == [r["case_id"] for r in ROWS]
    assert io.split_steps(rows[4]["steps"]) == ["x+(x+5)=25", "2x+5=25", "2x=20", "x=10"]


def test_validation_errors():
    bad = [dict(r, _row=i) for i, r in enumerate([
        dict(ROWS[0], case_id="B-1", question_id="Q99"),
        dict(ROWS[3], case_id="B-2", first_invalid_step="7"),
        dict(ROWS[0], case_id="B-3", primary_error="E3"),
        dict(ROWS[1], case_id="B-4", error_subtype="E4-01"),
        dict(ROWS[1], case_id="B-4"),
    ], start=2)]
    bad = [{k: str(v) for k, v in r.items()} for r in bad]
    for r in bad:
        r["_row"] = int(r["_row"])
    errors, _ = io.validate(bad, io.load_bank())
    text = "\n".join(errors)
    for needle in ("Q99", "steps has 3", "cannot have a primary_error", "only for primary_error E4", "repeats row"):
        assert needle in text


def test_record_shape():
    rec = io.to_record({k: str(v) for k, v in ROWS[3].items()}, "test")
    assert rec["learner_response"]["steps"] == ["2x+5=25", "2x=30", "x=15"]
    assert rec["state"] == "S3" and rec["first_invalid_step"] == 2 and rec["source"] == "hand_crafted"
    assert rec["normalized_response"]["steps"][0] == "2*x+5=25"


def test_split_is_stratified_and_stable():
    cases = [{"case_id": f"C{i:02d}", "reference_status": "incorrect", "primary_error": "E3"} for i in range(10)]
    assign_splits(cases, {})
    assert sum(c["split"] == "dev" for c in cases) == 3
    before = {c["case_id"]: c["split"] for c in cases}
    more = [dict(c) for c in cases] + [{"case_id": "C10", "reference_status": "incorrect", "primary_error": "E3"}]
    assign_splits(more, before)
    assert all(c["split"] == before[c["case_id"]] for c in more if c["case_id"] in before)


# ---------------------------------------------------------------- import

def test_import_keeps_d2a_and_is_repeatable(env):
    tmp, wb, cases = env
    n_d2a = sum(c["source"] == "mutation" for c in json.loads(cases.read_text(encoding="utf-8"))["cases"])
    code, out = do_import(tmp, wb, cases)
    assert code == 0, out
    assert "✗ total cases: 6 (need 40–60)" in out            # composition is reported, not enforced
    data = json.loads(cases.read_text(encoding="utf-8"))["cases"]
    d2b = {c["case_id"]: c for c in data if c["source"] == "hand_crafted"}
    assert len(d2b) == 6 and sum(c["source"] == "mutation" for c in data) == n_d2a
    code, _ = do_import(tmp, wb, cases)
    again = {c["case_id"]: c["split"] for c in json.loads(cases.read_text(encoding="utf-8"))["cases"]
             if c["source"] == "hand_crafted"}
    assert code == 0 and again == {k: v["split"] for k, v in d2b.items()}


def test_check_writes_nothing(env):
    tmp, wb, cases = env
    before = cases.read_text(encoding="utf-8")
    code, out = do_import(tmp, wb, cases, "--check")
    assert code == 0 and "nothing written" in out and cases.read_text(encoding="utf-8") == before


def test_invalid_workbook_writes_nothing(env):
    tmp, _, cases = env
    before = cases.read_text(encoding="utf-8")
    wb = workbook(tmp / "bad.xlsx", [dict(ROWS[0], question_id="Q99")])
    code, out = do_import(tmp, wb, cases)
    assert code != 0 and "Q99" in out and cases.read_text(encoding="utf-8") == before


def test_reviewed_labels_are_frozen(env):
    tmp, wb, cases = env
    assert do_import(tmp, wb, cases)[0] == 0
    changed = workbook(tmp / "changed.xlsx", [dict(ROWS[1], primary_error="E4")] + ROWS[:1] + ROWS[2:])
    code, out = do_import(tmp, changed, cases)
    assert code != 0 and "changed after the case was reviewed" in out
    code, out = do_import(tmp, changed, cases, "--allow-relabel", "T-02: relation is a 比…多 reversal")
    assert code == 0, out
    log = (tmp / "corrections.md").read_text(encoding="utf-8")
    assert "T-02 `primary_error`: 'E3' → 'E4'" in log and "比…多" in log


# ---------------------------------------------------------------- evaluation

def test_metrics_on_fixture_cases(env):
    tmp, wb, cases = env
    do_import(tmp, wb, cases)
    d2b = [c for c in json.loads(cases.read_text(encoding="utf-8"))["cases"] if c["source"] == "hand_crafted"]
    r = ev.evaluate(d2b, io.load_bank())
    assert r["n"] == {"incorrect": 3, "correct": 2, "uncertain": 1, "not_assessable": 0}
    by = {c["case_id"]: c for c in r["cases"]}
    assert by["T-04"]["system_step"] == 2 and r["step_localisation"]["right_step"] == 1
    assert r["fpr"] == 0.0 and by["T-05"]["output"] == "no_error_detected"
    assert set(r["confusion_matrix"]) >= {"E3", "E7", "correct"}


def test_test_split_refuses_unreviewed(env):
    tmp, _, cases = env
    wb = workbook(tmp / "pending.xlsx", [dict(r, review_status="pending") for r in ROWS])
    do_import(tmp, wb, cases)
    code, out = run("eval_diagnosis_d2b.py", "--cases", cases, "--split", "all", "--out-dir", tmp / "res")
    assert code != 0 and "not reviewed" in out
    code, out = run("eval_diagnosis_d2b.py", "--cases", cases, "--split", "all", "--out-dir", tmp / "res",
                    "--allow-pending")
    assert code == 0, out
    assert "NOT FROZEN" in out
    summary = json.loads(next((tmp / "res").glob("*/summary.json")).read_text(encoding="utf-8"))
    assert summary["frozen"] is False and summary["results"]["n_cases"] == 6


# ---------------------------------------------------------------- second annotator

def test_second_annotator_round_trip(env):
    tmp, wb, cases = env
    do_import(tmp, wb, cases)
    blind = tmp / "second.xlsx"
    code, out = run("d2b_second.py", "export", "--cases", cases, "--out", blind, "--fraction", "0.5")
    assert code == 0, out
    rows = io.read_workbook(blind)
    assert rows and all(not r.get("reference_status") and not r.get("primary_error") for r in rows)
    answers = {"T-01": ("correct", ""), "T-02": ("incorrect", "E4"), "T-03": ("incorrect", "E4"),
               "T-04": ("incorrect", "E7"), "T-05": ("correct", ""), "T-06": ("uncertain", "")}
    filled = [dict(r, reference_status=answers[r["case_id"]][0], primary_error=answers[r["case_id"]][1])
              for r in rows]
    workbook(blind, filled)
    code, out = run("d2b_second.py", "compare", "--cases", cases, "--file", blind,
                    "--record", tmp / "second.json", "--disagreements", tmp / "dis.md")
    assert code == 0, out
    rec = json.loads((tmp / "second.json").read_text(encoding="utf-8"))
    assert sorted(rec["case_ids"]) == sorted(r["case_id"] for r in rows)
    md = (tmp / "dis.md").read_text(encoding="utf-8")
    assert ("| T-02 | primary_error | E3 | E4 |" in md) == ("T-02" in rec["case_ids"])
    code, out = do_import(tmp, wb, cases, "--check")
    assert f"second-annotated: {len(rows)}" in out


def test_kappa():
    assert d2b_second.kappa(list("aabb"), list("aabb")) == 1.0
    assert d2b_second.kappa(list("ab"), list("ba")) < 0


def test_template_does_not_overwrite(tmp_path):
    out = tmp_path / "d2b.xlsx"
    assert run("d2b_template.py", "--out", out, "--rows", "5")[0] == 0
    code, msg = run("d2b_template.py", "--out", out)
    assert code != 0 and "already exists" in msg
    assert io.read_workbook(out) == []


# ---------------------------------------------------------------- DeepSeek candidates (fake backend)

class FakeStudent:
    """Stands in for DeepSeek; records what it was shown."""
    seen = []

    def __init__(self, temperature=1.0):
        self.temperature = temperature

    def describe(self):
        return {"backend": "fake"}

    def complete(self, system, user):
        FakeStudent.seen.append(user)
        if "需要写的内容：只写最后的答案" in user:
            return json.dumps({"final_answer_text": "答：10岁"}, ensure_ascii=False)
        if "一步一行" in user:
            return json.dumps({"variable_definition": "设x", "equation": "2x＋5＝25", "steps": ["2x=20", "x=10"]},
                              ensure_ascii=False)
        return json.dumps({"variable_definition": "解：设x", "equation": "x+5=25"}, ensure_ascii=False)


def test_generated_candidates_fill_responses_only(tmp_path, monkeypatch):
    import core.llm_client as llm
    import d2b_generate as gen
    monkeypatch.setattr(llm, "DeepSeekBackend", FakeStudent)
    FakeStudent.seen = []
    wb = tmp_path / "d2b.xlsx"
    assert run("d2b_template.py", "--out", wb)[0] == 0
    monkeypatch.setattr(sys, "argv", ["d2b_generate.py", "--workbook", str(wb), "--log", str(tmp_path / "log.json")])
    gen.main()

    rows = io.read_workbook(wb)
    assert len(rows) == 60 and len({r["case_id"] for r in rows}) == 60
    assert all(not r.get(k) for r in rows for k in ("reference_status", "primary_error", "first_invalid_step"))
    assert {r["layer"] for r in rows} == {"modelling", "execution", "answer"}
    bank = io.load_bank()
    for shown in FakeStudent.seen:                                   # no reference solution, no codes
        assert not any(q["equation"] in shown for q in bank.values())
        assert not any(f"E{i}" in shown for i in range(1, 8))
    log = json.loads((tmp_path / "log.json").read_text(encoding="utf-8"))
    kinds = [log["cases"][r["case_id"]]["intended_kind"] for r in rows]
    assert kinds != sorted(kinds, key=[k for k, _ in gen.PLAN].index)  # shuffled, order gives nothing away

    # provenance at import: one row edited by the researcher, one kept as generated
    rows[0]["equation"] = rows[0].get("equation", "") + " "              # whitespace only → unchanged
    rows[1] = dict(rows[1], final_answer_text="答：小明15岁", equation="", steps="")
    rows[1]["layer"] = "answer"
    labelled = [dict(r, reference_status="uncertain", review_status="pending") for r in rows[:2]]
    workbook(tmp_path / "labelled.xlsx", labelled)
    cases = tmp_path / "cases.json"
    data = json.loads(io.CASES_JSON.read_text(encoding="utf-8"))
    data["cases"] = [c for c in data["cases"] if c.get("source") != "hand_crafted"]
    cases.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    code, out = run("d2b_import.py", "--workbook", tmp_path / "labelled.xlsx", "--cases", cases,
                    "--second", tmp_path / "s.json", "--corrections", tmp_path / "c.md",
                    "--generation-log", tmp_path / "log.json")
    assert code == 0, out
    got = {c["case_id"]: c["response_origin"] for c in json.loads(cases.read_text(encoding="utf-8"))["cases"]
           if c["source"] == "hand_crafted"}
    assert got[rows[0]["case_id"]] == "llm_generated" and got[rows[1]["case_id"]] == "llm_edited"
