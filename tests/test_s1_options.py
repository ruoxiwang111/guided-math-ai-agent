"""
Tests for core/s1_options.py and its use in the S1 state.

Run from the project root:
    python -m pytest tests/test_s1_options.py -v
"""
import json
from pathlib import Path

import pytest

from core.s1_options import PROMPT, build_s1_item, load_targets, to_submission
from core.state_manager import ASK, HINT, S2, TutorSession

ROOT = Path(__file__).resolve().parents[1]
BANK = json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))
Q = {q["question_id"]: q for q in BANK["questions"]}
TARGETS = load_targets()


def test_every_bank_question_has_a_target():
    assert set(TARGETS) == set(Q)


@pytest.mark.parametrize("qid", sorted(Q))
def test_item_shape(qid):
    item = build_s1_item(Q[qid], TARGETS)
    ids = [o["id"] for o in item["options"]]
    texts = [o["text"] for o in item["options"]]
    assert item["prompt"] == PROMPT
    assert len(item["options"]) == 4
    assert ids == ["A", "B", "C", "D"]
    assert len(set(texts)) == 4                                     # no duplicates
    assert sum(o["source"] == "target" for o in item["options"]) == 1
    assert item["correct_id"] in ids
    correct = next(o for o in item["options"] if o["id"] == item["correct_id"])
    assert correct["text"] == TARGETS[qid]["target"]


@pytest.mark.parametrize("qid", sorted(Q))
def test_distractors_do_not_reveal_values(qid):
    item = build_s1_item(Q[qid], TARGETS)
    for o in item["options"]:
        if o["source"] == "known_quantity":
            assert "已给出" not in o["text"] and not any(ch.isdigit() for ch in o["text"].replace("5年后", ""))


def test_item_is_deterministic():
    assert build_s1_item(Q["Q07"], TARGETS) == build_s1_item(Q["Q07"], TARGETS)


def test_correct_position_varies_across_questions():
    positions = {build_s1_item(Q[qid], TARGETS)["correct_id"] for qid in Q}
    assert len(positions) >= 3


def test_to_submission():
    item = build_s1_item(Q["Q01"], TARGETS)
    right = to_submission(item, item["correct_id"])
    assert right == {**right, "type": "s1_choice", "correct": True, "chosen_source": "target"}
    wrong_id = next(o["id"] for o in item["options"] if o["source"] == "known_quantity")
    assert to_submission(item, wrong_id)["correct"] is False
    with pytest.raises(ValueError):
        to_submission(item, "Z")


def test_unknown_question_raises():
    with pytest.raises(KeyError):
        build_s1_item({"question_id": "Q99", "known_quantities": []}, TARGETS)


# --- integration with the state machine ------------------------------------

def test_correct_choice_moves_to_s2():
    s = TutorSession(Q["Q04"])
    s.start()
    item = build_s1_item(Q["Q04"], TARGETS)
    a = s.submit(to_submission(item, item["correct_id"]))
    assert (a.type, a.state) == (ASK, S2)


def test_choosing_a_known_quantity_is_e1_with_specific_evidence():
    s = TutorSession(Q["Q04"])
    s.start()
    item = build_s1_item(Q["Q04"], TARGETS)
    wrong = next(o for o in item["options"] if o["source"] == "known_quantity")
    a = s.submit(to_submission(item, wrong["id"]))
    assert a.type == HINT and a.category == "E1" and a.hint_level == 1
    assert wrong["text"] in a.diagnosis["evidence"] and "已知量" in a.diagnosis["evidence"]