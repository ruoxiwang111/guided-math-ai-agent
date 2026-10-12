# AI 陪我学 — Project summary

**What it is.** A guided tutor for middle-school linear-equation word problems that helps learners build and check solutions themselves. A rule-based state machine (understand → model → solve → verify) makes every teaching decision, SymPy checks the mathematics, and a language model is used only to phrase hints and to read new problems into a structure that code then verifies.

**Problem.** Fluent AI solutions invite learners to accept answers without judging them. The project explores a tutor whose job is to build the learner's own judgement, with decisions that can be traced to a rule, a mathematical check and a logged piece of evidence.

**Design.**
- Seven error categories (goal, unknown definition, relationship, language-to-maths translation, unit, arithmetic, algebraic/sign), assigned by rules; *uncertain* is a valid answer.
- Four hint levels before a reveal, with a leakage guard that blocks wording giving away the answer or the reference setup too early.
- Wording falls back to templates whenever the language model fails or leaks, so a model error cannot change what the tutor decides.
- Review after each problem (solution path, weak points, similar problems) and an independent-attempt mode with no feedback.

**What has been evaluated (offline, constructed data).**
- 798 automated tests, including end-to-end sessions with a deliberately faulty language model.
- Problem reading, 20 held-out inputs × 3 live runs: equation correct 92.6%; no wrong equation passed on as teachable for a solvable problem; one ambiguous input not flagged; over-cautious on two-stage journey and discount problems.
- Diagnosis on 65 rule-generated cases: 100% when the matcher knows the mutation; with each case's own mutation removed, coverage 68.8% (modelling errors 35.7%) at 100% accuracy and no wrong labels. This is a development result, not an independent test.
- Diagnosis on an independently annotated test split (40 constructed cases, frozen before the run, second human annotator on 13 cases): every specific label was right and no correct response was flagged, but only 10 of 26 errors received a label (target 60%); modelling errors 1 of 9; **6 of 26 incorrect responses were passed as "no error detected"**. Details and limitations: docs/D2B_RESULTS.md.

**What has not.** Live-hint quality review is pending, and the diagnostic set is small and simulated. No study with learners has been run, so the project makes no claim about learning outcomes.

**What I would do next.** Fix the missed-error and over-cautious cases on a development split and re-test on a fresh frozen one; then, with ethics approval, pilot with real learners.

**Suggested wording** (for a CV or an email): "Built and evaluated a rule-governed guided-learning agent for middle-school algebra word problems; offline technical validation on constructed and simulated data (798 tests; held-out structure-extraction and diagnosis evaluations with pre-registered freeze rules); no learner study yet."

**Avoid** describing it as an experiment, a user study, or evidence that it improves learning.

Code and evaluation plan: github.com/ruoxiwang111/guided-math-ai-agent (private at the time of writing; make it public or share access before linking it).
