# AI 陪我学 — AI Guided Math Learning Agent

A tutor for middle-school **linear-equation word problems** (一元一次方程应用题). The learner goes through four stages — understand the problem, build the equation, solve it, check the answer — and gets graded hints when a step is wrong. The aim is for the learner to judge whether a solution is correct, not just to read one.

**Status: V1 technical prototype.** It has been evaluated offline on constructed data and by the developer's own testing. No real learner has used it, and nothing here is evidence that it improves learning. See [Evaluation status](#evaluation-status) and [Limitations](#limitations).

## Why

Generative AI writes fluent solutions, and learners can accept them without checking the reasoning. This project builds a tutor whose job is to strengthen the learner's own judgement, and in which every teaching decision comes from a rule that can be inspected, not from a language model's output.

<!-- Add 2-3 sentences in your own words: what you found in your MSc interviews and why that led to this project. -->

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

The language model does not change the state, does not decide whether an answer is right, and does not see the reference solution when it writes a low-level hint.

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

The [evaluation plan](docs/evaluation_plan.md) defines eight questions (EQ1–EQ8), datasets D1–D5 and a rule to freeze each test set before running it. Headline numbers come from independent test splits only. Details and caveats for the diagnosis test are in [D2b results](docs/D2B_RESULTS.md).

| Question | Result so far | Status |
| --- | --- | --- |
| EQ1 problem structure | D1-test (20 inputs, 3 live runs): scope accuracy 76.7%, equation correctness 92.6%, field accuracy 82.0%. No wrong equation was accepted as teachable for a solvable problem. The relationship field was reviewed by hand (39 of 50 matched); the judgement was drafted by Claude and confirmed by the researcher, so it is not independent | Run |
| EQ2 diagnosis | D2b-test (40 cases, frozen): coverage 10/26 = 38.5% (target ≥60%, not met), 10/10 of the labels given were right. Modelling errors: 1/9 diagnosed. 6 of 26 incorrect responses were reported as "no error detected" | Run |
| EQ3 false alarms | D2b-test: 0 of 11 correct responses flagged as erroneous; 4 returned *uncertain* | Run, small n |
| EQ4 first invalid step | D2b-test: 8 right, 0 wrong, 1 uncertain of 9 (target ≥80% met) | Run, small n |
| EQ5 hints and leakage | Template hints and the leakage checker are tested on scripted scenarios. No live-hint review yet | Partial |
| EQ6 follow-up budget | State-machine tests and scripted flows. No simulated-trajectory study | Partial |
| EQ7 mastery rule | Not built | Not run |
| EQ8 Challenge AI items | 15 of 15 bank items validated | Done |

Not done yet: the live-hint review, a larger diagnostic set with real learner responses, and any study with learners. The D2b responses are simulated (mostly drafted by a language model, then screened and annotated by the researcher). A second human annotator labelled 13 of the 60 cases.

After the frozen test, three small diagnosis rules (V1.1) were added using the D2b dev split only. The dev result improved (coverage 42.9% to 64.3%), but that is a development result: the V1 test numbers above remain the reported result, and V1.1 needs a new frozen test set.

804 automated tests pass, including scripted end-to-end sessions in which the language model is replaced by a fake that fails on purpose.

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

```
python scripts/eval_diagnosis_d2b.py
```

The first needs a DeepSeek key and takes a few minutes; results go to `eval/results/`. LLM-dependent results vary between runs, which is why D1 is run three times and the minimum and maximum are reported.

D2b workflow (annotation workbook → import → second annotator → freeze → run): see the docstrings at the top of `scripts/d2b_template.py`, `d2b_import.py`, `d2b_second.py` and `eval_diagnosis_d2b.py`.

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
tests/                       804 tests
templates/index.html         the web interface
```

## Limitations

- One topic only (one-variable linear equation word problems). Anything else is declined or sent to Quick Solve.
- The task is Chinese. The interface can be shown in English (`?lang=en`, or the button in the header), but only interface text is translated. Problems, the tutor's questions, hints, feedback and review content stay in Chinese. English tutoring is not supported and no result applies to English problems.
- The data is small and constructed: 20 test inputs for D1, 15 bank problems, 40 test cases for D2b. Results are raw counts, not comparisons between categories.
- D2a was generated from the same design as the system, so it is not an independent test. D2b is independent of the rules, but 49 of its 60 responses were drafted by DeepSeek and then screened and annotated by one researcher; a second annotator covered 13 cases, and the first annotator resolved disagreements. Because the diagnosis is rule-based, this affects how realistic the responses are and the LLM-dependent parts (extraction, hint wording), not the diagnosis rules.
- Modelling errors are the weak point. On D2b-test 1 of 9 was diagnosed, and 6 of 26 incorrect responses were reported as "no error detected", for example a variable definition that contradicts the equation while the equation still gives the right answer. The design prefers "not sure" to guessing, but this gap is real.
- The structure check is over-cautious: in D1, three correct extractions of two-stage journey and discount problems were rejected every run because the independent second solve was wrong. Ambiguous problems are not yet detected reliably.
- No real learner has used it under study conditions; developer sessions are functional checks. A study with school-age participants needs ethics approval, parental consent, child assent, and data-protection and safeguarding arrangements first.
- DeepSeek is the only LLM backend.

## Documentation

- [V1 design](docs/V1_design.md) — scope, pipeline, states
- [Error taxonomy](docs/error_taxonomy.md) — E1–E7 and the diagnostic rules
- [Question bank](docs/question_bank.md) — problems, mutations, validation
- [Evaluation plan](docs/evaluation_plan.md) — questions, metrics, datasets, threats to validity
- [D2b results and limitations](docs/D2B_RESULTS.md) — the independent diagnostic test, read honestly

## Licence

The code is released under the [MIT License](LICENSE).

The evaluation data (the D2b constructed learner responses and their annotations under `eval/`) is **not** released and is not covered by the MIT licence; it is withheld from the public repository. The aggregate results are reported in [D2b results and limitations](docs/D2B_RESULTS.md).
