"""
core/s1_options.py — deterministic multiple-choice items for S1 (Problem Understanding).

V1_design.md §12 S1: "这道题最后要求我们求什么？" — a multiple-choice response is judged
by code, so S1 can run without the LLM. Free-text S1 answers are left to the LLM layer.

Options for one question:
    correct       the target from data/s1_targets.json
    distractors   1 hand-written intermediate quantity (s1_targets.json)
                  + known quantities from question_bank.json (given ≠ asked: typical E1)
The order is shuffled deterministically per question, so a question always shows the
same item (reproducible for evaluation and event logs).

Public API
    load_targets(path)                          -> dict
    build_s1_item(question, targets, n_options=4) -> dict
    to_submission(item, chosen_id)              -> dict   # input for TutorSession.submit
                                                          # chosen_id "U" = 我不确定 (asks for help)
"""
from __future__ import annotations

import json
import random
from pathlib import Path

PROMPT = "这道题最后要求我们求什么？"
# kept apart from `options` (always shown last, never shuffled): choosing it is not an answer,
# it asks for help — the state manager gives a hint and records no error
UNSURE = {"id": "U", "text": "我不确定", "source": "unsure"}
DEFAULT_TARGETS = Path(__file__).resolve().parents[1] / "data" / "s1_targets.json"


def load_targets(path: str | Path = DEFAULT_TARGETS) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))["targets"]


def _known_label(k: dict) -> str:
    """{'name': '年龄和', ...} → '年龄和'. No value shown, so the option does not give itself away."""
    return k["name"]


def build_s1_item(question: dict, targets: dict, n_options: int = 4) -> dict:
    qid = question["question_id"]
    if qid not in targets:
        raise KeyError(f"no S1 target for {qid} in s1_targets.json")
    t = targets[qid]

    options = [{"text": t["target"], "source": "target"}]
    if t.get("intermediate"):
        options.append({"text": t["intermediate"], "source": "intermediate_quantity"})
    for k in question.get("known_quantities", []):
        if len(options) >= n_options:
            break
        options.append({"text": _known_label(k), "source": "known_quantity"})

    texts = [o["text"] for o in options]
    if len(set(texts)) != len(texts):
        raise ValueError(f"{qid}: duplicate S1 option texts {texts}")
    if len(options) < 2:
        raise ValueError(f"{qid}: an S1 item needs at least one distractor")

    random.Random(qid).shuffle(options)
    for i, o in enumerate(options):
        o["id"] = "ABCDEFG"[i]
    correct = next(o["id"] for o in options if o["source"] == "target")
    return {"question_id": qid, "prompt": PROMPT, "options": options, "correct_id": correct,
            "unsure_option": dict(UNSURE)}


def to_submission(item: dict, chosen_id: str) -> dict:
    """Turn a learner's click into the S1 input expected by TutorSession.submit()."""
    if chosen_id == UNSURE["id"]:
        return {"type": "s1_choice", "correct": False, "unsure": True, "chosen_id": chosen_id,
                "chosen_text": UNSURE["text"], "chosen_source": "unsure"}
    chosen = next((o for o in item["options"] if o["id"] == chosen_id), None)
    if chosen is None:
        raise ValueError(f"option {chosen_id!r} not in {[o['id'] for o in item['options']]}")
    return {
        "type": "s1_choice",
        "correct": chosen_id == item["correct_id"],
        "chosen_id": chosen_id,
        "chosen_text": chosen["text"],
        "chosen_source": chosen["source"],
    }
