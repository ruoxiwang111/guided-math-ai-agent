"""
core/state_manager.py — backend-controlled Guided Mode state machine (S1 → S2 → S3 → S4).

Implements V1_design.md §11.2, §12, §20–24, §32.1 and error_taxonomy.md §9 (steps 6–7),
§13, §18. Fully deterministic: it decides WHAT the tutor does next; the LLM layer
(core/llm_client.py) only turns a TutorAction into wording, within the constraints
given in TutorAction.prompt_spec. The LLM never changes the state (§33).

Usage
    session = TutorSession(question, session_id="anonymous_001")
    action = session.start()                                   # ask S1
    action = session.submit({"type": "s1_choice", "correct": True})
    action = session.submit({"type": "modelling", "variable_definition": "设小华x岁", "equation": "x+(x+5)=25"})
    action = session.submit({"type": "steps", "steps": ["2x+5=25", "2x=20", "x=10"]})
    action = session.submit({"type": "final_answer", "final_answer_text": "小华10岁，小明15岁",
                             "verified": True, "active_verification": True})
    session.events        # learning event log (V1_design §23)
    session.summary()     # per-state evidence for the learning report / mastery (§24, §30)

Policies
  hint level      = number of failed attempts in the current state (1…4); resets when the
                    state advances (§20: stop escalating once understanding is shown)
  after level 4   one more failure → the correct step is shown ("reveal"), the state is
                    recorded as not independently solved, and the session moves on
  reveal request  after REVEAL_AFTER_ATTEMPTS tries at a step (S2–S4) the learner may ask to
                    see that step ({"type": "reveal_request"}); recorded as revealed, and as
                    requested by the learner (help-seeking, not a failure of the hints)
  evidence requests (show working / what is x / clarify notation / discriminating question)
                    do NOT count toward the metacognitive budget (taxonomy §9 step 7, §18);
                    capped per state so the learner is never asked for the same thing forever
  metacognitive follow-ups (reflection after a corrected error, verification prompt in S4)
                    count toward the per-problem budget (default 2, V1_design §21); one slot
                    is reserved for the S4 verification prompt, so reflections can use at most
                    budget − 1
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from core import diagnosis as dx
from core import math_checker as mc
from core import review as rv

S1, S2, S3, S4, DONE = "S1", "S2", "S3", "S4", "DONE"
NEXT_STATE = {S1: S2, S2: S3, S3: S4, S4: DONE}
INPUT_FOR_STATE = {S1: "s1_choice", S2: "modelling", S3: "steps", S4: "final_answer"}

# action types
ASK = "ask"                                  # open the task of a state
HINT = "hint"                                # category-specific hint at a backend-set level
EVIDENCE_REQUEST = "evidence_request"        # not counted in the budget
METACOGNITIVE = "metacognitive_question"     # counted in the budget
REVEAL = "reveal_step"                       # show the correct step after level 4 failed
ANSWER_QUESTION = "answer_question"          # reply to a learner's own question (no state change)
REFLECTION_FEEDBACK = "reflection_feedback"  # closes a reflection: feedback on the reply, or the reason if "不知道"
EXPLANATION_FOLLOW_UP = "explanation_follow_up"  # reply to the learner's words after a discriminating question
COMPLETE = "complete"
SELF_SUMMARY_ACK = "self_summary_ack"        # the learner's own one-sentence summary was recorded
UNEXPECTED_INPUT = "unexpected_input"

MAX_HINT_LEVEL = 4
DEFAULT_METACOGNITIVE_BUDGET = 2
MAX_EVIDENCE_REQUESTS_PER_STATE = 2
REVEAL_AFTER_ATTEMPTS = 2                    # "看这一步的参考" becomes available after 2 tries

QUESTION_RE = re.compile(r"[？?]|怎么|为什么|什么意思|啥意思|不懂|不会|不明白|如何|能不能|可以.*吗|是什么|哪里")


def looks_like_question(text: str) -> bool:
    return bool(text and QUESTION_RE.search(text))


DONT_KNOW_RE = re.compile(r"不知道|不清楚|不会|不懂|不明白|没想法|想不出|不确定|不记得|忘了|没思路")


def asks_for_the_reason(text: str) -> bool:
    """'不知道' / '为什么' / '不懂' / '？' as a reply to a reflection question = "tell me the reason"."""
    t = re.sub(r"[\s，,。.!！~…]", "", text or "")
    if not t or DONT_KNOW_RE.search(t):
        return True
    return looks_like_question(t) and len(t) <= 6

TASK_OF_STATE = {
    S1: "identify_target",          # 这道题最后要求我们求什么？
    S2: "define_x_and_equation",    # 我让 x 表示……，列出方程
    S3: "solve_line_by_line",       # 一行一行写出解方程的过程
    S4: "state_and_check_answer",   # 写出最终答案，并检查是否符合题意
}


@dataclass
class TutorAction:
    type: str
    state: str
    task: str | None = None                  # what the learner should do next
    category: str | None = None              # E1–E7 for hints
    error_subtype: str | None = None
    hint_level: int | None = None
    request: str | None = None               # which evidence is requested
    counts_toward_budget: bool = False
    diagnosis: dict | None = None
    prompt_spec: dict = field(default_factory=dict)   # constraints for the LLM wording
    note: str | None = None
    next_action: "TutorAction | None" = None          # e.g. after a reveal, the next state's task


@dataclass
class StateRecord:
    attempts: int = 0
    failed_attempts: int = 0
    max_hint_level: int = 0
    evidence_requests: int = 0
    revealed: bool = False
    reveal_requested: bool = False           # shown because the learner asked (vs. after level 4)
    errors: list = field(default_factory=list)
    passed: bool = False

    @property
    def independent(self) -> bool:
        """Solved with little or no prompting (V1_design §24): no hint above level 1, not revealed."""
        return self.passed and not self.revealed and self.max_hint_level <= 1


class TutorSession:
    def __init__(self, question: dict, session_id: str = "anonymous",
                 metacognitive_budget: int = DEFAULT_METACOGNITIVE_BUDGET, start_state: str = S1):
        self.q = question
        self.session_id = session_id
        self.budget = metacognitive_budget
        self.state = start_state
        self.records = {s: StateRecord() for s in (S1, S2, S3, S4)}
        self.metacognitive_count = 0
        self.evidence_request_count = 0
        self.events: list[dict] = []
        self.pending: TutorAction | None = None      # action to resume after a reflection reply
        self.awaiting_reflection = False
        self.reflection_kind: str | None = None
        self._last_response: dict | None = None
        self.learner_questions = 0
        self.self_summary: str | None = None
        self.reflection_about: str | None = None       # the state a reflection question is about
        self.awaiting_explanation = False              # a discriminating question may be answered in words
        self._last_diagnosis: dx.Diagnosis | None = None
        self._diag_by_state: dict = {}
        self._step_revealed: set = set()               # S3 lines already shown as a step reference
        self.understanding: dict | None = None       # "我读到的已知条件" check before S1 (extracted problems)
        # the learner's accepted model (standard or an accepted alternative definition)
        self.model = {"variable_definition": question["variable_definition"],
                      "equation": question["equation"], "answer": question["answer"],
                      "is_standard": True}
        self.final_x = None

    # ------------------------------------------------------------------ helpers
    def _log(self, event: str, **kw):
        rec = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_id": self.session_id,
            "question_id": self.q["question_id"],
            "state": self.state,
            "event": event,
            "follow_up_count": self.metacognitive_count,
            "evidence_request_count": self.evidence_request_count,
        }
        rec.update(kw)
        self.events.append(rec)

    def _forbidden(self, level: int) -> list[str]:
        """
        What a hint at this level must not contain (evaluation_plan §3.9.1) — but only what the
        learner has not produced yet: after S2 is passed the equation is theirs, after S3 the value
        of x is theirs, so quoting them back is not leakage.
        """
        if level >= 4:
            return []
        forbidden = ["final_answer"]
        if level <= 2:
            forbidden.append("complete_equation")
        if level == 1:
            forbidden.append("key_intermediate_value")
        if self.records[S2].passed and "complete_equation" in forbidden:
            forbidden.remove("complete_equation")
        if self.records[S3].passed:
            forbidden = [f for f in forbidden if f not in ("final_answer", "key_intermediate_value")]
        if level <= 2 and not self.records[S2].passed:
            forbidden.append("reference_model")          # e.g. "小明(x+5)岁" before the learner set up x
        if level <= 2 and self.state == S1:
            forbidden.append("s1_target")                # do not name the right option
        return forbidden

    def _learner_history(self) -> list[str]:
        """Everything the learner has written in this session (exempt from the leakage check)."""
        out = []
        for e in self.events:
            if e.get("event") == "learner_response":
                r = e.get("response") or {}
                for k in ("variable_definition", "equation", "final_answer_text"):
                    if r.get(k):
                        out.append(str(r[k]))
                steps = r.get("steps")
                out += steps.splitlines() if isinstance(steps, str) else [str(x) for x in steps or []]
            elif e.get("event") in ("learner_explanation", "reflection_reply", "learner_question"):
                out.append(e.get("text", ""))
        return [x for x in out if x]

    def _corrected_error(self, state: str):
        """(category, subtype, rule) of the last diagnosed error in a state, or None."""
        for e in reversed(self.events):
            if e.get("event") == "diagnosis" and e.get("state") == state \
                    and e.get("diagnosis_status") == "diagnosed" and e.get("diagnosed_error"):
                return e["diagnosed_error"], e.get("error_subtype"), e.get("rule")
        return None

    def _reason_for(self, state: str) -> dict:
        """What the learner just corrected, in words (deterministic, from core/review)."""
        err = self._corrected_error(state)
        if not err:
            d = self._diag_by_state.get(state)
            if d is not None and d.rule == "one_side_wrong":
                side = d.details
                if side.get("missing_brackets"):
                    return {"corrected_error": f"方程{side['wrong_side_name']}：倍数关系少了括号",
                            "reason": f"“{side.get('bracket_factor')}倍”要乘的是一个完整的量，这个量有两项时要加括号。"}
                return {"corrected_error": f"方程{side['wrong_side_name']}表示的量",
                        "reason": "方程两边要表示题目里同一个量的两种说法，每一边都要和题目的描述对得上。"}
            return {}
        c, sub, rule = err
        family = rv.topic_family(self.q.get("topic"))
        return {"corrected_error": rv._weak_point(c, sub, rule, family),
                "reason": rv._takeaway(c, sub, rule, self.q.get("relationship"))}

    def _learner_definition(self) -> str | None:
        """The learner's OWN definition of x: the accepted one after S2, else the last one they wrote."""
        if self.records[S2].passed:
            return self.model["variable_definition"]
        for e in reversed(self.events):
            if e.get("event") == "learner_response" and (e.get("response") or {}).get("variable_definition"):
                return e["response"]["variable_definition"]
        return None

    def _reference_expressions(self) -> list[str]:
        """Expressions of the reference models ('x+5', '4x', 'x/4', '2-x'): the S2 answer in pieces."""
        defs = [self.q["variable_definition"]] + [f["variable_definition"] for f in
                                                   self.q.get("accepted_equivalent_forms", []) if "variable_definition" in f]
        out = []
        for d in defs:
            for m in re.findall(r"[(（][^()（）]*x[^()（）]*[)）]|\d+(?:\.\d+)?\s*\*?\s*x|x\s*/\s*\d+", d or ""):
                e = re.sub(r"[\s()（）*]", "", m)
                if e and e != "x" and e not in out:
                    out.append(e)
        return out

    def _spec(self, level: int | None = None, **extra) -> dict:
        spec = {
            "question_id": self.q["question_id"],
            "question": self.q["question"],
            "learner_variable_definition": self._learner_definition(),
            "reference_answer": str(self.model["answer"]),
            "reference_equation": self.model["equation"],
            "learner_history": self._learner_history(),
            "reference_expressions": self._reference_expressions(),
        }
        if level is not None:
            spec["hint_level"] = level
            spec["must_not_contain"] = self._forbidden(level)
        spec.update(extra)
        return spec

    def _question_view(self):
        """Question as seen from the learner's accepted model (for S3 checking)."""
        return dict(self.q, equation=self.model["equation"], answer=self.model["answer"])

    def _ask(self) -> TutorAction:
        if self.state == DONE:
            self._log("session_complete", summary=self.summary())
            return TutorAction(COMPLETE, DONE, note="guided session finished")
        self._log("ask", task=TASK_OF_STATE[self.state])
        return TutorAction(ASK, self.state, task=TASK_OF_STATE[self.state], prompt_spec=self._spec())

    def _advance(self, reflection: bool = False) -> TutorAction:
        rec = self.records[self.state]
        rec.passed = True
        self._log("state_passed", independent=rec.independent, max_hint_level=rec.max_hint_level,
                  revealed=rec.revealed)
        prev = self.state
        self.state = NEXT_STATE[self.state]
        self._log("state_transition", from_state=prev, to_state=self.state)
        nxt = self._ask()
        # a reflection question after an error was corrected, keeping one slot for S4 verification
        if reflection and rec.failed_attempts > 0 and not rec.revealed and self._budget_left(reserve=1):
            return self._metacognitive(prev, "explain_why_correct", resume=nxt)
        return nxt

    def _reflection_context(self, about_state: str, kind: str) -> dict:
        if kind == "prompt_verification":
            x = self.final_x if self.final_x is not None else self.model.get("answer")
            return {"verification_walkthrough": rv.verification_walkthrough(self.q, x)}
        return self._reason_for(about_state)

    def _budget_left(self, reserve: int = 0) -> bool:
        return self.metacognitive_count < self.budget - reserve

    def _metacognitive(self, about_state: str, kind: str, resume: TutorAction | None) -> TutorAction:
        self.metacognitive_count += 1
        self.pending = resume
        self.awaiting_reflection = True
        self.reflection_kind = kind
        self.reflection_about = about_state
        self._log("metacognitive_follow_up", kind=kind, about_state=about_state)
        # the answer of later steps must still not be given away, unless the problem is solved
        spec = self._spec(level=None if self.state == DONE else 2, kind=kind, about_state=about_state,
                          current_state=about_state, recent_work=self._recent_work(),
                          verification_conditions=[c["description"] for c in self.q.get("verification_conditions", [])],
                          **self._reflection_context(about_state, kind))
        if self.state == DONE:
            spec["must_not_contain"] = []
        return TutorAction(METACOGNITIVE, self.state, task=kind, counts_toward_budget=True, prompt_spec=spec)

    def _evidence_request(self, d: dx.Diagnosis) -> TutorAction | None:
        rec = self.records[self.state]
        if rec.evidence_requests >= MAX_EVIDENCE_REQUESTS_PER_STATE:
            return None
        rec.evidence_requests += 1
        self.evidence_request_count += 1
        request = d.follow_up or dx.ASK_WORKING
        self.awaiting_explanation = self.state in (S2, S3)
        self._log("evidence_request", request=request, diagnosis_status=d.status,
                  candidates=d.candidates, evidence_level=d.evidence_level)
        return TutorAction(EVIDENCE_REQUEST, self.state, task=INPUT_FOR_STATE[self.state],
                           request=request, diagnosis=asdict(d),
                           prompt_spec=self._spec(level=1, request=request, candidates=d.candidates,
                                                  evidence_repeat=rec.evidence_requests, rule=d.rule,
                                                  current_state=self.state, evidence=d.evidence,
                                                  **self._learner_context(d, None)))

    def _reveal(self, category: str | None, requested: bool = False) -> TutorAction:
        """Show the correct step of the current state, record it, and move on."""
        rec = self.records[self.state]
        rec.revealed = True
        rec.reveal_requested = requested
        self._log("reveal_step", diagnosed_error=category, requested_by_learner=requested,
                  attempts=rec.attempts)
        state = self.state
        if state == S2:
            # continue from the reference model
            self.model = {"variable_definition": self.q["variable_definition"],
                          "equation": self.q["equation"], "answer": self.q["answer"],
                          "is_standard": True}
        if state == S3:
            self.final_x = self.model["answer"]
        spec = self._spec(level=4, reveal=True, requested=requested,
                          reference_definition=self.q["variable_definition"])
        note = ("the learner asked to see this step" if requested
                else "level 4 did not resolve the error; the correct step is shown")
        reveal = TutorAction(REVEAL, state, category=category, hint_level=4, prompt_spec=spec, note=note)
        reveal.next_action = self._advance()
        return reveal

    def can_reveal(self) -> bool:
        """The learner may ask to see the current step after trying it at least REVEAL_AFTER_ATTEMPTS times."""
        return (self.state in (S2, S3, S4) and not self.awaiting_reflection
                and self.records[self.state].attempts >= REVEAL_AFTER_ATTEMPTS)

    def request_reveal(self) -> TutorAction:
        if not self.can_reveal():
            self._log("reveal_refused", attempts=self.records[self.state].attempts if self.state in self.records else None)
            return TutorAction(UNEXPECTED_INPUT, self.state, task=INPUT_FOR_STATE.get(self.state),
                               note=f"reveal is available after {REVEAL_AFTER_ATTEMPTS} attempts at this step")
        step = self._step_reference()
        if step is not None:
            return step
        return self._reveal(None, requested=True)

    def _step_reference(self) -> TutorAction | None:
        """
        S3: show only the correct version of the first wrong line and let the learner go on
        (a second request for the same line shows the whole step). None if there is no line.
        """
        d = self._last_diagnosis
        if self.state != S3 or d is None or not d.first_invalid_step or not d.details.get("prev_line"):
            return None
        r = self._last_response or {}
        steps = r.get("steps")
        lines = [ln.strip() for ln in (steps.splitlines() if isinstance(steps, str) else steps or []) if ln.strip()]
        k = d.first_invalid_step
        if not 1 <= k <= len(lines):
            return None
        key = (k, lines[k - 1])
        if key in self._step_revealed:
            return None
        from core.normalizer import normalize_line
        prev_nl, cur_nl = normalize_line(d.details["prev_line"]), normalize_line(lines[k - 1])
        if not (prev_nl.ok and cur_nl.ok):
            return None
        correct = dx.correct_next_line(prev_nl.normalized, cur_nl.normalized)
        if not correct:
            return None
        self._step_revealed.add(key)
        rec = self.records[S3]
        rec.revealed = True
        rec.reveal_requested = True
        self._log("reveal_step", diagnosed_error=d.primary_error, requested_by_learner=True, scope="line",
                  line_no=k, attempts=rec.attempts)
        reason = self._reason_for(S3).get("reason")
        spec = self._spec(level=3, reveal=True, requested=True, step_reveal=True, line_no=k,
                          learner_line=lines[k - 1], prev_line=d.details["prev_line"],
                          from_start_equation=bool(d.details.get("from_start_equation")),
                          correct_line=correct, reason=reason)
        spec["must_not_contain"] = []            # the learner asked for this line
        return TutorAction(REVEAL, S3, task=INPUT_FOR_STATE[S3], hint_level=3, prompt_spec=spec,
                           note="the learner asked to see the correct version of the wrong line")

    def _hint_or_reveal(self, d: dx.Diagnosis | None, category: str | None) -> TutorAction:
        rec = self.records[self.state]
        rec.failed_attempts += 1
        if rec.failed_attempts > MAX_HINT_LEVEL:
            return self._reveal(category)
        level = min(MAX_HINT_LEVEL, rec.failed_attempts)
        rec.max_hint_level = max(rec.max_hint_level, level)
        self.awaiting_explanation = self.state in (S2, S3)
        self._log("hint", diagnosed_error=category, hint_level=level,
                  diagnosis_status=d.status if d else "diagnosed",
                  evidence_level=d.evidence_level if d else None)
        return TutorAction(HINT, self.state, task=INPUT_FOR_STATE[self.state], category=category,
                           error_subtype=d.error_subtype if d else None, hint_level=level,
                           diagnosis=asdict(d) if d else None,
                           prompt_spec=self._spec(level=level, category=category,
                                                  rule=d.rule if d else None,
                                                  error_subtype=d.error_subtype if d else None,
                                                  evidence=d.evidence if d else None,
                                                  first_invalid_step=d.first_invalid_step if d else None,
                                                  solving_steps=rv.knowledge_points(self.q)[1].split("：", 1)[-1],
                                                  current_state=self.state,
                                                  **self._learner_context(d, category)))

    def _learner_context(self, d: dx.Diagnosis | None, category: str | None) -> dict:
        """
        What the learner actually wrote, plus deterministic facts about what is RIGHT in it,
        so the wording can quote the learner and acknowledge correct parts first.
        """
        r = self._last_response or {}
        ctx = {"learner_input": {k: v for k, v in r.items() if k != "type"}, "acknowledge": []}
        if self.state == S2:
            vd, eq = r.get("variable_definition"), r.get("equation")
            ctx.update(learner_definition=vd, learner_equation=eq)
            ref = dx.resolve_definition(vd, dx._references(self.q))[0] if vd else None
            if ref is not None and category not in ("E2",):
                ctx["acknowledge"].append(f"你写的“{vd.strip()}”这个设法没问题")
            if d is not None and d.details.get("wrong_side_text"):
                ctx.update({k: d.details[k] for k in ("correct_side_name", "correct_side_text", "wrong_side_name",
                                                      "wrong_side_text", "missing_brackets", "bracket_factor")
                            if k in d.details})
        elif self.state == S3 and d is not None and d.first_invalid_step:
            steps = r.get("steps")
            lines = [ln.strip() for ln in (steps.splitlines() if isinstance(steps, str) else steps or []) if ln.strip()]
            k = d.first_invalid_step
            if 1 <= k <= len(lines):
                prev = d.details.get("prev_line") or (lines[k - 2] if k >= 2 else None)
                ctx.update(line_no=k, learner_line=lines[k - 1], prev_line=prev,
                           from_start_equation=bool(d.details.get("from_start_equation")))
            if k >= 3:
                ctx["acknowledge"].append(f"前{k - 1}行都是对的")
            elif k == 2:
                ctx["acknowledge"].append("第1行没问题")
        elif self.state == S4 and d is not None and d.details.get("right"):
            ctx["acknowledge"].append(f"{'、'.join(d.details['right'])}的数值对了")
        return ctx

    def _handle_diagnosis(self, d: dx.Diagnosis) -> TutorAction:
        self._last_diagnosis = d
        rec = self.records[self.state]
        self._log("diagnosis", diagnosed_error=d.primary_error, error_subtype=d.error_subtype,
                  diagnosis_status=d.status, evidence_level=d.evidence_level,
                  first_invalid_step=d.first_invalid_step, rule=d.rule)
        self._diag_by_state[self.state] = d
        if d.status == dx.DIAGNOSED:
            rec.errors.append(d.error_subtype or d.primary_error)
            return self._hint_or_reveal(d, d.primary_error)
        if d.rule == "one_side_wrong":
            # located but not labelled: guidance on the normal hint ladder, no error category claimed
            return self._hint_or_reveal(d, None)
        # uncertain / insufficient: collect evidence first (§9 step 6), never claim an error
        req = self._evidence_request(d)
        if req is not None:
            return req
        # evidence requests exhausted: give a category-neutral hint so the learner can progress
        return self._hint_or_reveal(d, None)

    def _allowed_level(self):
        """Hint level a free answer may go up to; None = no restriction (the answer is already known)."""
        if self.state == DONE or self.records[self.state].passed:
            return None
        return max(1, self.records[self.state].max_hint_level)

    def _recent_work(self) -> list[dict]:
        return [e.get("response") for e in self.events if e["event"] == "learner_response"][-3:]

    def ask_question(self, text: str) -> TutorAction:
        """
        Learner's own question at any point. Answered within the current hint-level limits;
        it never changes the state, the hint level or the metacognitive budget, and is logged
        as help-seeking behaviour.
        """
        self.learner_questions += 1
        self._log("learner_question", text=text)
        level = self._allowed_level()
        spec = self._spec(level=level if level is not None else 4,
                          learner_question=text,
                          current_state=self.state,
                          current_task=TASK_OF_STATE.get(self.state),
                          reflection_kind=self.reflection_kind if self.awaiting_reflection else None,
                          **(self._reflection_context(self.reflection_about, self.reflection_kind)
                             if self.awaiting_reflection else {}),
                          recent_work=self._recent_work(),
                          verification_conditions=[c["description"] for c in self.q.get("verification_conditions", [])],
                          relationship=self.q.get("relationship"))
        return TutorAction(ANSWER_QUESTION, self.state, task=TASK_OF_STATE.get(self.state), prompt_spec=spec)

    @staticmethod
    def _is_help_request(r: dict) -> bool:
        """'不知道' / '不会' written instead of work (no x, no digits, no '=')."""
        text = " ".join(str(r.get(k) or "") for k in ("variable_definition", "equation", "steps",
                                                       "final_answer_text", "text")).strip()
        if not text or re.search(r"[xX=＝\d]", text):
            return False
        return bool(DONT_KNOW_RE.search(text)) or text in ("?", "？")

    def _help(self, r: dict) -> TutorAction:
        rec = self.records[self.state]
        rec.attempts += 1
        self._log("help_request", text={k: v for k, v in r.items() if k != "type"})
        d = dx.Diagnosis(status=dx.INSUFFICIENT, state=self.state, evidence_level="D", rule="help_request",
                         evidence="学生表示不知道这一步怎么做")
        return self._hint_or_reveal(d, None)

    def _reflection_feedback(self, text: str, explain: bool) -> TutorAction:
        """Close a reflection: short feedback on the reply, or the reason itself for "不知道"."""
        about, kind = self.reflection_about, self.reflection_kind
        self.awaiting_reflection = False
        self._log("reflection_reply", text=text, asked_for_reason=explain)
        resume, self.pending = self.pending, None
        spec = self._spec(level=None if self.state == DONE else 2, kind="explain" if explain else "feedback",
                          learner_reply=text, reflection_kind=kind, about_state=about,
                          recent_work=self._recent_work(), **self._reflection_context(about, kind))
        if self.state == DONE:
            spec["must_not_contain"] = []
        action = TutorAction(REFLECTION_FEEDBACK, self.state, task="explain" if explain else "feedback",
                             prompt_spec=spec)
        action.next_action = resume or self._ask()
        return action

    def explain(self, text: str) -> TutorAction:
        """
        The learner answers a discriminating question in words ("3x+5 是5年后小明的年龄…").
        No state change and no hint-level change: the reply looks at what they said and sends
        them back to revise their work.
        """
        text = (text or "").strip()
        if self.state not in (S2, S3) or not text:
            return TutorAction(UNEXPECTED_INPUT, self.state, task=INPUT_FOR_STATE.get(self.state),
                               note="an explanation answers a question about the current equation or step")
        self.awaiting_explanation = False
        self._log("learner_explanation", text=text)
        rec = self.records[self.state]
        level = max(1, rec.max_hint_level)
        r = self._last_response or {}
        spec = self._spec(level=level, learner_explanation=text, current_state=self.state,
                          learner_input={k: v for k, v in r.items() if k != "type"},
                          learner_equation=r.get("equation"), learner_definition=r.get("variable_definition"),
                          relationship=self.q.get("relationship"))
        return TutorAction(EXPLANATION_FOLLOW_UP, self.state, task=INPUT_FOR_STATE[self.state],
                           hint_level=level, prompt_spec=spec)

    def record_understanding(self, confirmed: bool, corrections: int = 0, notes=None):
        """The learner's check of how the system read the problem (before S1). Logged, not judged."""
        self.understanding = {"confirmed": bool(confirmed), "corrections": int(corrections),
                              "notes": list(notes or [])}
        self._log("understanding_check", **self.understanding)

    def record_self_summary(self, text: str) -> TutorAction:
        """Optional one-sentence summary after the problem is done (review / 复盘). Recorded, not judged."""
        text = (text or "").strip()
        if self.state != DONE or not text:
            return TutorAction(UNEXPECTED_INPUT, self.state, task=INPUT_FOR_STATE.get(self.state),
                               note="a self summary is written after the problem is finished")
        self.self_summary = text
        self._log("self_summary", text=text)
        return TutorAction(SELF_SUMMARY_ACK, DONE, note="self summary recorded")

    # ------------------------------------------------------------------ public API
    def start(self) -> TutorAction:
        self._log("session_start", mode="guided", learner_id=getattr(self, "learner_id", None))
        return self._ask()

    def submit(self, response: dict) -> TutorAction:
        kind = response.get("type")

        if kind == "question":
            return self.ask_question(response.get("text", ""))
        if kind == "reveal_request":
            return self.request_reveal()
        if kind == "self_summary":
            return self.record_self_summary(response.get("text", ""))

        # reply to a metacognitive question: recorded, not judged here (LLM may classify later)
        if kind == "reflection":
            if not self.awaiting_reflection:
                self._log("unexpected_input", got=kind, expected=INPUT_FOR_STATE.get(self.state))
                return TutorAction(UNEXPECTED_INPUT, self.state, task=INPUT_FOR_STATE.get(self.state),
                                   note="no metacognitive question is open")
            text = response.get("text", "")
            if asks_for_the_reason(text):
                # "不知道" / "为什么": give the reason now instead of moving on without it
                return self._reflection_feedback(text, explain=True)
            if looks_like_question(text):
                # a specific question: answer it, keep the reflection open
                return self.ask_question(text)
            return self._reflection_feedback(text, explain=False)
        if kind == "explanation":
            return self.explain(response.get("text", ""))
        if self.awaiting_reflection:
            # learner skipped the reflection question: allowed, recorded
            self.awaiting_reflection = False
            self.pending = None
            self._log("reflection_skipped")
        self.awaiting_explanation = False

        if self.state == DONE:
            return TutorAction(COMPLETE, DONE, note="session already complete")
        expected = INPUT_FOR_STATE[self.state]
        if kind != expected:
            self._log("unexpected_input", got=kind, expected=expected)
            return TutorAction(UNEXPECTED_INPUT, self.state, task=expected,
                               note=f"expected '{expected}' in {self.state}, got '{kind}'")

        if self._is_help_request(response):
            return self._help(response)

        self.records[self.state].attempts += 1
        self._last_response = response
        self._log("learner_response", student_input_type=kind,
                  response={k: v for k, v in response.items() if k != "type"})
        return getattr(self, f"_submit_{self.state.lower()}")(response)

    # -- S1: target identification (choice judged by code; free text by LLM → caller passes `correct`)
    def _submit_s1(self, r):
        if r.get("correct"):
            return self._advance()
        if r.get("unsure"):
            # "我不确定" is a request for help, not a wrong answer: hint, no error recorded
            self._log("s1_unsure")
            d = dx.Diagnosis(status=dx.INSUFFICIENT, state=S1, evidence_level="D", rule="s1_unsure",
                             evidence="学生选择了“我不确定”，还没有判断题目要求什么")
            return self._hint_or_reveal(d, None)
        chosen = r.get("chosen_text")
        why = {"known_quantity": "选了题目已经给出的已知量",
               "intermediate_quantity": "选了解题过程中的中间量"}.get(r.get("chosen_source"), "")
        evidence = f"学生选择的“{chosen}”不是题目所求" + (f"（{why}）" if why else "") if chosen \
            else "学生选择/说明的目标量与题目所求不一致"
        d = dx.Diagnosis(status=dx.DIAGNOSED, state=S1, primary_error="E1", candidates=["E1"],
                         evidence_level="A", evidence=evidence)
        return self._handle_diagnosis(d)

    # -- S2: variable definition + equation
    def _submit_s2(self, r):
        d = dx.diagnose_modelling(self.q, r.get("equation", ""), r.get("variable_definition"))
        if d.status == dx.NO_ERROR:
            vd = r.get("variable_definition") or self.q["variable_definition"]
            refs = dx._references(self.q)
            ref = next((x for x in refs if x["label"] == d.details.get("ref")), None) or refs[0]
            self.model = {"variable_definition": vd, "equation": ref["equation"],
                          "answer": ref["answer"], "is_standard": ref["label"] == "standard",
                          "learner_equation": r.get("equation")}
            self._log("diagnosis", diagnosis_status=d.status, evidence_level=d.evidence_level,
                      accepted_model=ref["label"])
            return self._advance(reflection=True)
        return self._handle_diagnosis(d)

    # -- S3: line-by-line working, checked against the learner's accepted model
    def _submit_s3(self, r):
        steps = r.get("steps") or []
        view = self._question_view()
        start = self.model.get("learner_equation") or self.model["equation"]
        d = dx.diagnose_steps(view, steps, self.model["variable_definition"], start_equation=start)
        if d.status == dx.NO_ERROR:
            check = mc.check_steps(steps, reference_equation=view["equation"])
            if check.status != mc.ALL_VALID:        # the working did not repeat the equation itself
                lines = steps.splitlines() if isinstance(steps, str) else list(steps)
                check = mc.check_steps([start] + lines, reference_equation=view["equation"])
            if check.final_matches_reference:
                self.final_x = check.final_value
                self._log("diagnosis", diagnosis_status=d.status, evidence_level=d.evidence_level,
                          final_value=str(check.final_value))
                return self._advance(reflection=True)
            d = dx.Diagnosis(status=dx.INSUFFICIENT, state=S3, evidence_level="D",
                             evidence="每一步都正确，但还没有解出 x = …", follow_up="continue_solving")
        return self._handle_diagnosis(d)

    # -- S4: final answer (+ verification behaviour)
    def _submit_s4(self, r):
        active = bool(r.get("active_verification"))
        verified = bool(r.get("verified")) or active
        self._log("verification", verified=verified, active_verification=active)

        d = dx.diagnose_final_answer(self.q, r.get("final_answer_text", ""))
        if d.status != dx.NO_ERROR:
            return self._handle_diagnosis(d)

        # contextual constraints (only meaningful for the standard meaning of x)
        if self.model["is_standard"] and self.final_x is not None:
            failed = [c.description for c in mc.check_conditions(self.q["verification_conditions"], self.final_x)
                      if c.holds is False]
            if failed:
                return self._handle_diagnosis(dx.Diagnosis(
                    status=dx.DIAGNOSED, state=S4, primary_error="E5", candidates=["E5"],
                    evidence_level="A", evidence=f"答案不满足题目条件：{'；'.join(failed)}"))

        self._log("diagnosis", diagnosis_status=d.status, evidence_level=d.evidence_level)
        if not verified and self._budget_left():
            # correct answer but no verification: one verification prompt (counts toward budget)
            self.records[S4].passed = True
            prev = self.state
            self.state = DONE
            self._log("state_transition", from_state=prev, to_state=DONE)
            return self._metacognitive(S4, "prompt_verification", resume=self._ask())
        return self._advance()

    # ------------------------------------------------------------------ reporting
    def summary(self) -> dict:
        return {
            "question_id": self.q["question_id"],
            "completed": self.state == DONE,
            "metacognitive_follow_ups": self.metacognitive_count,
            "evidence_requests": self.evidence_request_count,
            "accepted_model": "standard" if self.model["is_standard"] else "alternative",
            "states": {
                s: {"passed": r.passed, "independent": r.independent, "attempts": r.attempts,
                    "max_hint_level": r.max_hint_level, "revealed": r.revealed,
                    "reveal_requested": r.reveal_requested, "errors": r.errors}
                for s, r in self.records.items()
            },
            "active_verification": any(e.get("active_verification") for e in self.events
                                       if e["event"] == "verification"),
            "learner_questions": self.learner_questions,
            "self_summary": self.self_summary,
            "learner_id": getattr(self, "learner_id", None),
            "understanding": self.understanding,
        }

    def events_jsonl(self) -> str:
        return "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in self.events)
