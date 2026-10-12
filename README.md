# AI 陪我学 — AI Guided Math Learning Agent

A guided tutor for middle-school **linear-equation word problems** (一元一次方程应用题). Instead of handing the student a worked solution, it walks them through four stages — understand the problem, build the equation, solve it, verify the answer — and gives graded hints when they go wrong. The aim is to help learners judge whether a solution is correct, not only to read one.

> **Status: V1 technical prototype.** It has been evaluated offline on constructed data and by the developer's own testing. It has **not** been tested with real learners, and nothing here is evidence that it improves learning. See [Evaluation status](#evaluation-status) and [Limitations](#limitations).

## Why

Generative AI can produce fluent, plausible solutions, and learners may accept them without checking the reasoning. This project asks what a tutor looks like when its main job is to build the learner's own judgement (appropriate reliance), and when every teaching decision can be traced to a rule rather than to a language model's mood.

## How it works

The system separates **decisions** from **wording**.

| Layer | What it does | Uses an LLM? |
| --- | --- | --- |
| Normaliser | Parses what the learner typed (full-width symbols, implicit multiplication, `1/3x` ambiguity) | No |
| Math checker | SymPy: is each line equivalent to the previous one? where does the first invalid step occur? | No |
| Diagnosis | Assigns an error category E1–E7 (goal, unknown definition, relationship, language-to-maths translation, unit, arithmetic, algebraic/sign) or returns *uncertain* | No |
| State machine | S1 → S2 → S3 → S4; chooses the hint level (L1–L4, then reveal on request), follow-up questions and when to move on | No |
| Leakage guard | Rejects any wording that gives away the final answer, the complete equation or the reference setup before the learner has earned it | No |
| Wording | Phrases the hint the state machine chose; falls back to a template if the LLM fails or leaks | Yes (DeepSeek) |
| Structure extraction | Reads a new problem into unknown / known quantities / equation, then checks it (linear and unique, numbers appear in the text, an independent solve agrees) | Yes (DeepSeek), checked by code |

The language model never changes the state, never decides whether an answer is right, and never sees the reference solution when it writes a low-level hint.

Other features: a review after each problem (solution path, weak points, similar problems), an independent-attempt mode with no feedback until submission, a command-line runner that prints what every module decided on each turn, and a Quick Solve mode for problems outside Guided Mode's scope.

## Quick start

Python 3.11 is what the project is developed on.

```
git clone https://github.com/ruoxiwang111/guided-math-ai-agent.git
cd guided-math-ai-agent
python -m venv .venv
```

Activate the environment (Windows PowerShell):

```
.venv\Scripts\Activate.ps1
```

or on macOS / Linux:

```
source .venv/bin/activate
```

Then:

```
pip install -r requirements.txt
```

Create a file named `.env` in the project root containing your own DeepSeek key:

```
DEEPSEEK_API_KEY=your-key-here
```

`.env` is git-ignored; never commit it. Without a key the guided tutor still runs on templates, but problem reading from new text and photos, and live wording, need the key.

Start the web app (http://localhost:5000):

```
python app.py
```

Or use the terminal runner:

```
python scripts/run_agent.py --demo
```

```
python scripts/run_agent.py --question Q05
```

Run the tests (they need no key):

```
python -m pytest tests -q
```

Use `tests` explicitly: a bare `pytest` also collects `test_deepseek.py`, a connectivity check that needs a key.

## Evaluation status

The evaluation plan ([docs/evaluation_plan.md](docs/evaluation_plan.md)) defines eight questions (EQ1–EQ8), datasets D1–D5, a freeze rule before each run, and a development/test split. Headline results are meant to come from independent test splits only. This table says what exists today.

| Question | Evidence | Status |
| --- | --- | --- |
| EQ1 problem structure | **D1-test**, 20 inputs × 3 live runs, commit `f6969cf`, `deepseek-chat`, temperature 0.3: scope accuracy 76.7%, equation correctness 92.6%, field accuracy 82.0%. No wrong equation was accepted as teachable for a solvable problem; 4.4% "consistent but wrong" comes from one ambiguous input the system did not flag | Run |
| EQ2 diagnosis | **D2a** (65 rule-generated mutations): 100% coverage and accuracy when the matcher may see the mutation list; **leave-one-out** (the case's own mutation removed): coverage 68.8% (modelling 35.7%, execution 100%, answer 66.7%), conditional accuracy 100%, 0 wrong labels | Development result only |
| EQ3 false alarms | Unit tests on equivalent and alternative correct forms; D2a contains no correct cases | Partial |
| EQ4 first invalid step | D2a: 30/30 in both the stored and a learner-style format. The reference comes from the same SymPy criterion as the checker, so this shows agreement and pipeline integrity, **not independent accuracy** | Development result only |
| EQ5 hints and leakage | Template hints per level in scripted scenarios; leakage checker tested. No live-hint review yet | Partial |
| EQ6 follow-up budget | State-machine tests; scripted end-to-end flows. No simulated-trajectory study | Partial |
| EQ7 mastery rule | Not built | Not run |
| EQ8 Challenge AI items | 15/15 bank items validated | Done |

**Not yet done:** D2b — an independently annotated diagnostic set (tooling is built; the cases are still being written and annotated), a second human annotator, the live-hint review, and any study with learners. When D2b is run it becomes the headline result for EQ2–EQ4, and D2a stays a development result.

Software checks: 798 automated tests, including scripted end-to-end sessions in which the language model is replaced by a fake that errs or fails on purpose.

### Reproducing

```
python scripts/eval_structure_d1.py
```

```
python scripts/eval_diagnosis_d2a.py
```

```
python scripts/eval_step_localisation.py
```

The first needs a DeepSeek key and takes a few minutes; results go to `eval/results/`. LLM-dependent results vary between runs, which is why D1 is run three times and the minimum and maximum are reported.

D2b workflow (annotation workbook → import → freeze → run): see the docstrings at the top of `scripts/d2b_template.py`, `d2b_import.py`, `d2b_second.py` and `eval_diagnosis_d2b.py`.

## Repository layout

```
app.py, guided_routes.py     Flask app and the Guided Mode / practice API
core/                        normaliser, math checker, diagnosis, state machine,
                             LLM wording and leakage guard, structure extraction,
                             review, similar-problem generation, independent practice
data/question_bank.json      15 verified problems with mutations and Challenge AI items
docs/                        V1 design, error taxonomy, question bank, evaluation plan
eval/                        datasets (D1, D2a; D2b workbook) and results
scripts/                     evaluation, dataset building and the terminal runner
tests/                       798 tests
templates/index.html         the web interface
```

## Limitations

- **Scope.** One topic (one-variable linear equation word problems). Anything else is declined or sent to Quick Solve, by design.
- **Small, constructed data.** D1 has 20 test inputs, the question bank has 15 problems. With so few cases per category, results are reported as raw counts and rates, not as statistical comparisons between categories.
- **The designer built the first datasets.** D2a was generated from the same design the system was built on, so it is not an independent test. D2b is meant to fix this, but its responses are drafted by a language model (DeepSeek) and then screened and annotated by one researcher; a second, human annotator for at least 20% of cases is still to be added. The diagnosis itself is rule-based, so shared-model bias affects the realism of the drafted answers and the LLM-dependent parts (D1 extraction, hint wording), not the diagnosis rules.
- **Modelling errors are the weak point.** Without a matching known mutation, relationship errors (E3) are mostly returned as *uncertain* rather than diagnosed. The design prefers saying "not sure" to guessing.
- **Over-cautious structure check.** In D1, three correct extractions of two-stage journey and discount problems were rejected every run because the independent second solve was wrong; ambiguous problems are not yet detected reliably.
- **Simulated and developer testing only.** No real learner has used it under study conditions. Developer sessions are functional checks, not evidence of learning.
- **Any future study with school-age participants** needs institutional ethics approval, consent from parents and assent from the child, data protection and safeguarding arrangements first.
- **Single LLM provider.** DeepSeek is the only backend wired in.

## Documentation

- [V1 design](docs/V1_design.md) — scope, pipeline, states
- [Error taxonomy](docs/error_taxonomy.md) — E1–E7 and the diagnostic rules
- [Question bank](docs/question_bank.md) — problems, mutations, validation
- [Evaluation plan](docs/evaluation_plan.md) — questions, metrics, datasets, threats to validity

## Licence

No licence has been chosen yet. Until one is added, all rights are reserved by the author.
