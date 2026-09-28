# Evaluation Plan

**Project:** AI Guided Math Learning Agent (AI 陪我学)
**Version:** V1.1
**Status:** Evaluation Specification
**Authority:** Canonical evaluation reference

**Related Documents:**

* `docs/V1_design.md`
* `docs/error_taxonomy.md` (V1.2)
* `docs/question_bank.md` (V1.3)
* `data/question_bank.json`

> **Precedence rule:** This document is the single reference for V1 evaluation. Where metric definitions, denominators, labels, or reporting rules differ across related documents, this document takes precedence.

---

# 1. Purpose

This document defines the evaluation protocol for the **AI Guided Math Learning Agent (AI 陪我学) V1 prototype**.

It consolidates the evaluation-related definitions currently distributed across:

* `V1_design.md` §34
* `error_taxonomy.md` §15
* `question_bank.md` §40–45

The purpose of V1 evaluation is to determine whether the prototype behaves **reliably, controllably, and transparently** at the Agent level.

V1 evaluation focuses on whether the system can:

1. determine whether a problem is within the intended scope;
2. extract a correct problem structure;
3. diagnose learner errors using the V1 E1–E7 taxonomy;
4. distinguish incorrect responses from correct responses;
5. identify the first invalid step in line-by-line working;
6. generate hints that comply with the assigned scaffolding level;
7. keep metacognitive follow-up within the intended interaction budget;
8. make rule-based mastery judgements consistent with simulated learner states;
9. maintain mathematically valid and correctly labelled Challenge AI items.

V1 **does not evaluate learner learning outcomes**.

In particular, V1 does not establish whether learners:

* learn more effectively;
* verify more frequently;
* become better at detecting AI errors;
* calibrate trust more appropriately;
* transfer mathematical knowledge more successfully.

Those are future learner-side research questions and are addressed separately in Section 12.

---

# 2. Evaluation Questions

| ID      | Evaluation question                                                                              | Priority |
| ------- | ------------------------------------------------------------------------------------------------ | -------- |
| **EQ1** | Does the system correctly decide scope and extract a correct problem structure?                  | P0       |
| **EQ2** | When a learner response is wrong, does the system diagnose the primary error category correctly? | P0       |
| **EQ3** | When a learner response is correct, does the system avoid falsely flagging an error?             | P0       |
| **EQ4** | For line-by-line working, does the system locate the first invalid step?                         | P0       |
| **EQ5** | Do generated hints respect the assigned scaffolding level without leaking the answer?            | P0       |
| **EQ6** | Does the tutor keep metacognitive follow-up questions within the intended interaction budget?    | P0       |
| **EQ7** | Does the rule-based mastery judgement agree with the simulated learner's true state?             | P1       |
| **EQ8** | Are all Challenge AI items mathematically valid and correctly labelled?                          | P0       |

---

# 3. Canonical Metric Definitions

These definitions are the **canonical V1 definitions** and supersede conflicting wording in related documents.

## 3.1 Case Labels

Every diagnostic test case receives a **reference status** from the annotator before the system is run.

| Reference status | Meaning                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------- |
| `correct`        | The response is mathematically correct in any valid equivalent form.                      |
| `incorrect`      | The response contains an identifiable error with a clear primary category.                |
| `uncertain`      | The available evidence genuinely supports more than one interpretation or error category. |
| `not_assessable` | The response cannot be reliably parsed or interpreted from the available evidence.        |

For `incorrect` cases, the reference annotation should contain a primary E1–E7 category whenever the evidence permits.

E4 subtypes (E4-01 … E4-08) are stored in `error_subtype`; the `primary_error` used for scoring is the collapsed category `E4`.

---

## 3.2 Diagnostic Coverage

$$
\text{Coverage}
=
\frac{\text{reference-incorrect cases assigned a specific E1--E7 category}}
{\text{all reference-incorrect cases}}
$$

**Denominator:** reference-incorrect cases only.

The following are excluded from the denominator:

* reference-correct cases;
* reference-uncertain cases;
* reference-not-assessable cases.

Coverage measures whether the system is willing and able to provide a specific diagnosis when a learner response is known to be incorrect.

> **Canonical denominator rule:** This definition supersedes the alternative denominators currently used in `V1_design.md` §34.2 and `question_bank.md` §41.

---

## 3.3 Conditional Diagnostic Accuracy

$$
\text{Conditional Accuracy}
=
\frac{\text{specific diagnoses whose primary category matches the reference}}
{\text{all specific diagnoses on reference-incorrect cases}}
$$

Conditional accuracy is therefore calculated **only among cases for which the system actually assigns a specific E1–E7 diagnosis**.

Coverage and conditional accuracy must always be reported together.

A high conditional accuracy with very low coverage does not demonstrate reliable overall diagnosis.

---

## 3.4 Uncertainty Appropriateness

$$
\text{Uncertainty Appropriateness}
=
\frac{\text{reference-uncertain cases returned as uncertain or insufficient\_evidence}}
{\text{all reference-uncertain cases}}
$$

This metric measures whether the system appropriately avoids forcing a specific diagnosis when the available evidence is genuinely ambiguous.

A system should not receive credit for simply refusing to diagnose all difficult cases; uncertainty is evaluated specifically against cases independently annotated as `uncertain`.

---

## 3.5 False Positive Rate (FPR)

$$
\text{FPR}
=
\frac{\text{reference-correct cases assigned any E1--E7 category}}
{\text{all reference-correct cases}}
$$

A reference-correct case returned as:

* `uncertain`, or
* `insufficient_evidence`

is **not** counted as a false positive.

However, these cases are reported separately because they may create unnecessary learner follow-up.

---

## 3.6 Confusion Matrix

The diagnostic confusion matrix uses:

**Rows:** reference labels

* E1
* E2
* E3
* E4
* E5
* E6
* E7
* `correct`
* `uncertain`

**Columns:** system outputs

* E1
* E2
* E3
* E4
* E5
* E6
* E7
* `no_error_detected`
* `uncertain`
* `insufficient_evidence`

E4 subtypes are collapsed to `E4` in both rows and columns.

The matrix must report **raw counts**, not percentages alone.

Because V1 uses relatively small datasets, raw counts are the primary presentation. Per-category precision, recall, and F1 may be reported as supplementary statistics but must not replace the raw confusion matrix.

`not_assessable` cases are tracked separately and should not be silently treated as incorrect diagnoses.

---

## 3.7 S3 Step-Localization

For line-by-line cases with an independently annotated first invalid step:

$$
\text{Step-Localization Accuracy}
=
\frac{\text{cases where the system identifies the annotated first invalid step}}
{\text{all annotated execution-error cases}}
$$

The evaluation additionally reports:

* **Valid-step false alarms:** valid transformations incorrectly marked as invalid.
* **Localization uncertain:** cases returned as uncertain.
* **Wrong-step cases:** cases in which the system identifies a step other than the annotated first invalid step.

The denominator is the number of line-by-line cases with an annotated execution error and a defined first invalid step.

> **Interpretation of D2a step localisation.** The D2a reference first invalid step was produced by `scripts/validate_question_bank.py` using the same SymPy solution-set comparison that `core/math_checker.py` uses. A D2a score therefore measures **agreement with that criterion and pipeline integrity**, not independent step-localisation accuracy. Independent evidence comes from D2b, whose first invalid steps are annotated by hand.

---

## 3.8 Structure Metrics (EQ1)

| Metric                        | Definition                                                                                                                  |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Scope accuracy**            | Share of inputs for which the system's in-scope / out-of-scope / uncertain decision matches the reference.                  |
| **Equation correctness**      | Share of in-scope inputs for which the extracted equation has the same mathematical solution set as the reference equation, or as one of the reference's accepted alternatives under that alternative's variable definition. |
| **Field accuracy**            | Share of required structural fields—unknown, known quantities, and relationship—that match the reference annotation.        |
| **Consistent-but-wrong rate** | Share of inputs marked `consistent` whose extracted equation is nevertheless semantically incorrect.                        |

Scope is judged from the problem statement only; attached learner work does not change the reference scope.

The **consistent-but-wrong rate must always be reported**.

This metric directly captures the limitation that a structurally consistent equation may still represent the wrong interpretation of the original word problem.

---

## 3.9 Answer Leakage and Hint Compliance (EQ5)

### 3.9.1 Leakage Criteria

The V1 hint levels follow the following constraints:

| Level       | Must not contain                                           | May contain                                  |
| ----------- | ---------------------------------------------------------- | -------------------------------------------- |
| **Level 1** | Final answer, complete equation, or key intermediate value | A question directing the learner's attention |
| **Level 2** | Final answer or complete equation                          | The relevant quantity relationship in words  |
| **Level 3** | Final answer                                               | The next operation, but not its result       |
| **Level 4** | —                                                          | A partial or full explanation                |

The leakage rate is:

$$
\text{Leakage Rate}
=
\frac{\text{Level 1--3 hints violating their assigned criteria}}
{\text{all Level 1--3 hints}}
$$

### 3.9.2 Automatic Leakage Detection

An automatic checker flags a hint if it contains:

1. the reference final answer value; or
2. an expression mathematically equivalent to the reference equation, using normalized symbolic comparison where applicable.

SymPy-based equivalence checking should be used for mathematical expressions rather than relying solely on string matching.

All automatically flagged hints are manually reviewed.

In addition, a random **20% sample of unflagged Level 1–3 hints** is manually reviewed to estimate false negatives.

### 3.9.3 Hint Compliance

Each hint is scored against four binary criteria:

1. **Category:** Matches the diagnosed error category.
2. **Level:** Respects the assigned scaffolding level.
3. **Mathematics:** Introduces no new mathematical error.
4. **Context:** Uses the learner's actual question and variable definition appropriately.

A hint is considered fully compliant only when **all four criteria are satisfied**.

The evaluation reports:

* percentage meeting all four criteria;
* failure count for each individual criterion.

---

## 3.10 Follow-up Burden (EQ6)

The primary metric is:

$$
\text{Metacognitive Follow-ups per Problem}
=
\frac{\text{number of metacognitive follow-up questions}}
{\text{number of problems attempted}}
$$

Metacognitive follow-ups include questions intended to promote reflection, checking, explanation, or self-monitoring.

The following are **excluded** from this metric:

* requests for missing working;
* requests asking what `x` represents;
* clarification of notation;
* other evidence-collection requests required to make a diagnosis.

These are reported separately as:

> **Evidence Requests per Problem**

This distinction follows the interaction taxonomy in `error_taxonomy.md` §9.

---

## 3.11 Mastery Decision Accuracy (EQ7, P1)

$$
\text{Mastery Decision Accuracy}
=
\frac{\text{sub-skill decisions matching the simulated learner's true state}}
{\text{all sub-skill decisions}}
$$

Results are reported separately for:

* true `mastered` states;
* true `not_mastered` states.

Misclassified trajectories should also be listed, especially cases such as:

* chance-correct learners judged as mastered;
* unstable learners judged as mastered;
* mastered learners incorrectly judged as not mastered.

EQ7 is a **P1 metric** because V1 uses simulated rather than real learners.

---

## 3.12 Challenge AI Item Validity (EQ8)

Challenge AI is evaluated in V1 primarily as a **dataset-quality and content-validity problem**, rather than as a learner outcome.

The V1 dataset contains:

* **9 incorrect Challenge AI items**;
* **6 correct Challenge AI items**;
* **15 items in total**.

The validity criteria are:

1. **100% of correct Challenge AI solutions reach the reference answer.**
2. **100% of incorrect Challenge AI solutions contain exactly one documented primary error matching the labelled category.**
3. All items satisfy the structural and mathematical validation rules.

Automated validation is implemented in:

```text
scripts/validate_question_bank.py
```

Mathematical consistency and structural checks are automated where possible. The requirement that an incorrect Challenge AI solution contains **exactly one intended error** remains subject to manual review.

> **Important:** The 9/6 distribution refers to the `challenge_ai.v1_set_role` labels. A question containing an incorrect solution in its stored text but labelled `v1_set_role: correct` is treated as a correct Challenge AI item for dataset statistics and is not counted in the incorrect-item error-type distribution.

Learner-side Challenge AI outcomes, such as:

* AI-error detection accuracy;
* correct-AI rejection rate;
* acceptance of incorrect AI advice;

are **not collected in V1**. They are reserved for future learner studies.

---

# 4. Datasets

| ID      | Dataset                           | Size / target                               | Source                                                                                 | Used for      |
| ------- | --------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------- | ------------- |
| **D1**  | Structure set                     | 30 inputs                                   | 15 bank + 10 reworded + 1 in-scope with learner work + 2 out-of-scope + 2 uncertain    | EQ1           |
| **D2a** | Mutation-generated diagnostic set | All question-bank mutations (65 target)     | `data/question_bank.json`, built by `scripts/build_d2a.py`                             | EQ2, EQ4      |
| **D2b** | Hand-crafted diagnostic set       | 40–60 responses                             | Written independently by the researcher                                                | EQ2, EQ3, EQ4 |
| **D3**  | Hint set                          | Hints generated for D2b cases at Levels 1–4 | System output                                                                          | EQ5           |
| **D4**  | Simulated trajectories            | 8 learner profiles × 5 problems             | Rule-based simulator                                                                   | EQ6, EQ7      |
| **D5**  | Challenge AI items                | 15                                          | `data/question_bank.json`                                                              | EQ8           |

The D2a size is treated as a **validation target against the actual JSON dataset**. If the final mutation count differs from 65, the evaluation report must record the actual count rather than silently using the target number.

---

## 4.1 D1 Structure Set Composition

D1 contains 30 inputs:

| Source              | n  | Reference scope | Purpose                                                                                     |
| ------------------- | -: | --------------- | ------------------------------------------------------------------------------------------- |
| `question_bank`     | 15 | `in_scope`      | Original V1 problems; generated from `question_bank.json`, never copied by hand             |
| `reworded`          | 10 | `in_scope`      | New context, wording and numbers with the same structure as a base question (incl. hard)    |
| `with_learner_work` |  1 | `in_scope`      | In-scope problem submitted together with a wrong learner equation                           |
| `out_of_scope`      |  2 | `out_of_scope`  | Quadratic relationship; inequality ("最多") problem                                         |
| `uncertain`         |  2 | `uncertain`     | Comparison direction not stated ("相差"); two problems in one input                          |

The set is designed to test whether the system can distinguish:

* supported one-variable linear-equation word problems;
* equivalent natural-language formulations;
* problems requiring clarification;
* problems outside the V1 scope;
* the problem's own structure from a learner's attached (possibly wrong) equation.

Scope is decided from the problem statement only. Whether attached learner work is correct is a D2 question, not a D1 question.

Out-of-scope and uncertain inputs test meaningful scope or interpretation boundaries rather than formatting failures.

D1 is built by `scripts/build_d1.py` from `data/question_bank.json` (D1-01..15) and `eval/d1_extra_cases.json` (D1-16..30). Every in-scope reference equation, and every accepted alternative, is checked with SymPy before the file is written.

---

## 4.2 D2 Diagnostic Set Composition

D2 consists of two sources:

### D2a — Mutation-generated cases

D2a contains all validated mutations from the V1 question bank (65: 28 modelling, 30 execution, 7 answer), generated by `scripts/build_d2a.py`.

Its purpose is to provide controlled coverage of known error patterns and to test whether the diagnostic system can recover the intended error category.

Build rules:

* modelling mutations without a `variable_definition` inherit the question's standard definition (recorded in `variable_definition_source`);
* mutations whose equation equals the standard equation (Q13-E2) are flagged: the error is visible only through the variable definition;
* answer-layer E1 and E5 are Level A (visible in the final answer); other answer-only errors (Q12-E6b) are reference `uncertain`, Level B.

D2a contains no reference-correct cases and only one reference-uncertain case, so FPR is not computed on D2a and uncertainty appropriateness on D2a rests on n = 1.

D2a results are reported separately because the mutations were generated from the same question-bank design used to construct the system.

### D2b — Hand-crafted cases

D2b contains **40–60 learner-style responses** written by the researcher.

D2b must include:

* at least **5 cases per category** E1–E7;
* **20–30% reference-correct cases**;
* equivalent equations;
* alternative valid unknown definitions;
* alternative valid working;
* correct final-answer-only responses;
* at least **5 reference-uncertain cases**;
* at least **3 ambiguous-notation cases**, such as `1/3x`;
* at least **5 final-answer-only incorrect cases** representing Level B evidence;
* at least **5 multi-error cases**;
* at least **10 line-by-line execution cases** with an independently annotated first invalid step.

The cases should use natural learner-style wording rather than being simple copies of the mutation engine's templates.

The categories and case types may overlap. For example, a line-by-line case may simultaneously satisfy the requirements for an E6 case and a multi-error case.

---

## 4.3 D2 Record Format

Each diagnostic case is stored in:

```text
eval/diagnostic_cases.json
```

The reference annotation follows the fields defined in `error_taxonomy.md` §14.2.

V1 additionally requires:

```text
source
split
```

where:

* `source = mutation` for D2a;
* `source = hand_crafted` for D2b;
* `split = dev` or `test`.

Rebuilding D2a regenerates only `source = mutation` cases; hand-crafted D2b cases are preserved.

The reference annotation must be stored separately from system predictions.

---

## 4.4 D3 Hint Dataset

D3 is generated from D2b cases after the diagnostic output and intended scaffolding level have been established.

Each hint record should preserve:

* case ID;
* diagnosed error category;
* assigned hint level;
* generated hint;
* model/prompt version;
* leakage-check result;
* four hint-compliance scores.

D3 should not be used to tune prompts after the headline test results have been generated.

---

## 4.5 D4 Simulated Learner Profiles

D4 contains eight deterministic learner profiles.

| Profile             | True state              | Behaviour                                                 |
| ------------------- | ----------------------- | --------------------------------------------------------- |
| **P-correct**       | All sub-skills mastered | Correct responses; occasionally verifies.                 |
| **P-E2**            | S2 not mastered         | Unstable variable definitions.                            |
| **P-E3**            | S2 not mastered         | Quantity-relationship errors.                             |
| **P-E4**            | S2 not mastered         | Closed-list language-to-math translation errors.          |
| **P-E6**            | S3 not mastered         | Arithmetic slips.                                         |
| **P-E7**            | S3 not mastered         | Sign / transposition errors.                              |
| **P-guesser**       | Nothing mastered        | Occasionally correct by chance.                           |
| **P-over-cautious** | All mastered            | Correct work but unnecessarily rejects correct AI output. |

Responses are generated deterministically from the profile.

An LLM may be used only to paraphrase free-text responses while preserving the underlying state and error structure, as specified in `V1_design.md` §26.

The simulator is used to evaluate Agent-side logic only and must not be interpreted as a substitute for real learner data.

---

# 5. Evaluation Procedure

## 5.1 Annotation Before Running the System

Reference annotations must be completed **before system evaluation**.

The procedure is:

1. The researcher independently annotates D1 and D2b.
2. At least **20% of D2b** is independently annotated by a second person.
3. The second annotator is blind to system outputs.
4. Disagreements are recorded in:

   ```text
   eval/annotation_disagreements.md
   ```
5. Disagreements are resolved through discussion.
6. If substantial disagreement occurs specifically around E3/E4 boundaries, the annotation rules are revised before final scoring.

The final evaluation must preserve the original annotations and the disagreement record rather than overwriting the initial decisions.

A dataset counts as **frozen** once its reference annotations have been reviewed (`review_status = reviewed`) and committed to version control before the first system run on it. Reference labels are not changed after that commit except to correct a documented annotation error, which is recorded in the error analysis.

---

## 5.2 Development / Test Split

System prompts, diagnostic rules, thresholds, and other tunable components may be adjusted **only using the development split**.

### D2b

* 30% development;
* 70% test;
* stratified by primary error category where possible.

### D1

* 10 development inputs;
* 20 test inputs;
* stratified by source, reproducible from a fixed seed.

### D2a

* generated from the question bank and used in full as a test set by default (`--dev-ratio 0`);
* D2a is nevertheless **not** an independent test set (see §3.7 and §9), and any rule changed after inspecting D2a results turns the affected D2a results into development results.

The **headline evaluation results are reported on the D1 and D2b test splits only**.

D2a mutation results are reported separately because they are generated from the controlled question-bank mutation set and therefore do not provide the same independence as D2b.

---

## 5.3 Freezing and Repeat Runs

Before a test run, the following must be recorded and frozen:

* model name;
* model version;
* temperature;
* generation settings;
* prompt versions;
* code commit hash;
* taxonomy version;
* question-bank version;
* evaluation-plan version;
* date of evaluation.

Because LLM-dependent outputs may vary across runs, every LLM-dependent component is run **three times on the test split**.

For each applicable metric, report:

* mean;
* minimum;
* maximum.

Deterministic components, including:

* normalisation;
* SymPy equivalence checks;
* deterministic step-localisation procedures;
* rule-based diagnosis;

are run once unless a separate robustness test is required.

---

## 5.4 Scoring

The primary scoring script is:

```text
eval/run_eval.py
```

It reads:

* reference annotations;
* system outputs;
* run configuration;

and generates the reporting tables defined in Section 6.

Until `run_eval.py` exists, the implemented component scripts are:

| Script                              | Produces                                       |
| ----------------------------------- | ---------------------------------------------- |
| `scripts/eval_step_localisation.py` | §6.3 D2a row → `eval/results/step_localisation_d2a.json` |
| `scripts/eval_diagnosis_d2a.py`     | §6.1 / §6.2 D2a rows (full and leave-one-out) → `eval/results/diagnosis_d2a.json` |

Each result file stores an `interpretation` note or mode label with the numbers, so a figure cannot be quoted without its caveat.

Reference annotations and system predictions must be stored separately.

The system must **never write predictions back into the reference annotation files**.

This separation is mandatory to prevent accidental contamination of the evaluation ground truth.

---

# 6. Reporting Templates

## 6.1 Diagnosis — EQ2 / EQ3

| Source                        | n incorrect | Coverage | Conditional accuracy | n uncertain ref. | Uncertainty appropriateness | n correct | FPR |
| ----------------------------- | ----------: | -------: | -------------------: | ---------------: | --------------------------: | --------: | --: |
| D2a mutation — leave-one-out  |          64 |          |                      |                1 |                             |         0 |   — |
| D2a mutation — full           |          64 |          |                      |                1 |                             |         0 |   — |
| D2b hand-crafted (test)       |             |          |                      |                  |                             |           |     |

D2a is reported in two modes:

* **leave-one-out** — when a case is diagnosed, its own mutation is removed from the matcher, so modelling and answer cases must be caught by general rules (closed-list E4 templates, E2 rule, unit rule) or returned as uncertain. **This is the D2a figure to cite.**
* **full** — all bank mutations are available; modelling cases can match themselves, so this row only confirms integration.

D2a results are development results (§5.2). D2a and D2b must **not be merged into a single headline diagnostic result**.

---

## 6.2 Confusion Matrix

Produce one raw-count confusion matrix for each source:

* D2a (leave-one-out);
* D2b-test.

Rows represent reference labels.

Columns represent system outputs.

The matrix should be preserved as raw counts even where percentages are also reported.

---

## 6.3 Step Localization — EQ4

| Source                  | n cases | Correct step | Uncertain | Wrong step | Valid-step false alarms / valid transitions |
| ----------------------- | ------: | -----------: | --------: | ---------: | ------------------------------------------: |
| D2a mutation — bank format    |      30 |              |           |            |                                             |
| D2a mutation — learner format |      30 |              |           |            |                                             |
| D2b hand-crafted (test)       |         |              |           |            |                                             |

The D2a rows are agreement with the labelling criterion (§3.7), reported in the stored bank format and in a learner-style rewriting (`2x＋5＝25`, `×`, `−`) that exercises the normaliser. D2b is the independent result.

Suggested wording for reports:

> On the 30 annotated D2a execution cases, the deterministic checker located the first invalid step in 30/30 cases in both bank-format and learner-style input, where the reference labels were produced by the same solution-set criterion.

---

## 6.4 Structure — EQ1

| Split | n inputs | Scope accuracy | Equation correctness | Field accuracy | Consistent-but-wrong rate |
| ----- | -------: | -------------: | -------------------: | -------------: | ------------------------: |
| test  |       20 |                |                      |                |                           |

---

## 6.5 Hints — EQ5

| Level   | n hints | Leakage rate | All-4 compliance | Fail: category | Fail: level | Fail: math error | Fail: context |
| ------- | ------: | -----------: | ---------------: | -------------: | ----------: | ---------------: | ------------: |
| Level 1 |         |              |                  |                |             |                  |               |
| Level 2 |         |              |                  |                |             |                  |               |
| Level 3 |         |              |                  |                |             |                  |               |
| Level 4 |         |            — |                  |                |             |                  |               |

Level 4 is not included in the Level 1–3 leakage-rate denominator.

---

## 6.6 Follow-up Burden — EQ6

| Profile         | Problems | Metacognitive follow-ups / problem | Evidence requests / problem |
| --------------- | -------: | ---------------------------------: | --------------------------: |
| P-correct       |          |                                    |                             |
| P-E2            |          |                                    |                             |
| P-E3            |          |                                    |                             |
| P-E4            |          |                                    |                             |
| P-E6            |          |                                    |                             |
| P-E7            |          |                                    |                             |
| P-guesser       |          |                                    |                             |
| P-over-cautious |          |                                    |                             |

---

## 6.7 Mastery — EQ7

| Profile | Sub-skill | True state | System decision | Match |
| ------- | --------- | ---------- | --------------- | ----- |
|         |           |            |                 |       |

Misclassified trajectories should be listed beneath the table.

---

## 6.8 Challenge AI Validity — EQ8

| Check                                                 | Target | Result |
| ----------------------------------------------------- | -----: | -----: |
| Correct items reaching reference answer               |   100% |        |
| Incorrect items containing exactly one intended error |   100% |        |
| Incorrect item category matching                      |   100% |        |
| Total Challenge AI items                              |     15 |        |
| Incorrect / Correct distribution                      |  9 / 6 |        |

Q14 is treated according to its stored `challenge_ai.v1_set_role`. Because Q14 is labelled `v1_set_role: correct`, it is included among the six correct Challenge AI items and excluded from incorrect-item error-category statistics.

---

# 7. Internal Targets

The following are **development targets** used to decide whether V1 is ready for demonstration.

They are **not validated educational benchmarks** and must not be presented as evidence that the system improves learning.

| Metric                                   | Development target                                   |
| ---------------------------------------- | ---------------------------------------------------- |
| **FPR** (D2b-test)                       | ≤ 5%                                                 |
| **Leakage rate, Levels 1–2**             | 0 violations                                         |
| **Step localization, D2a**               | ≥ 95% (agreement / integration check, see §3.7)      |
| **Step localization, D2b-test**          | ≥ 80%                                                |
| **Valid-step false alarms**              | 0                                                    |
| **Conditional accuracy, D2b-test**       | ≥ 75%, with coverage ≥ 60%                           |
| **Consistent-but-wrong rate**            | Reported; no target                                  |
| **Metacognitive follow-ups per problem** | ≤ 2 on average for P-correct                         |
| **Challenge AI item validity**           | 100%                                                 |

If any target is missed, the result is still reported.

A missed target triggers:

1. inspection of the relevant failure cases;
2. identification of the likely failure source;
3. documentation of any change made;
4. clear indication of whether the change was made using development data or after the test run.

No post-hoc change may be presented as part of the original frozen test result.

---

# 8. Error Analysis

Failure analysis is a primary output of V1 rather than an appendix.

For each major metric, the evaluation report should include the **3–5 most informative failure cases**.

For each selected case, record:

* case ID;
* reference annotation;
* system output;
* expected behaviour;
* observed failure;
* likely cause;
* whether the failure is reproducible;
* change made, if any;
* whether the change was made on the development split or after the test run.

Likely causes should be classified where possible as:

* parser failure;
* normalisation failure;
* rule failure;
* prompt failure;
* model inconsistency;
* taxonomy ambiguity;
* annotation disagreement;
* mathematical-validation failure;
* interaction-policy failure.

The report should distinguish **system errors** from **annotation uncertainty** rather than automatically attributing every disagreement to the model.

---

# 9. Threats to Validity

| Threat                                                                            | V1 mitigation                                                                                                                |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Mutation engine is evaluated on its own mutations                                 | D2a and D2b are reported separately; D2b is independently hand-crafted.                                                      |
| D2a step-localisation labels share the checker's criterion                        | The D2a reference first invalid step was produced by the same SymPy solution-set comparison that the checker uses, so D2a step localisation is reported as agreement with that criterion and pipeline integrity, not as independent accuracy. Independent evidence comes from D2b. |
| Diagnostic rules were refined after inspecting D2a results                        | D2a diagnosis results are reported as development results. Diagnosis is additionally reported in leave-one-out mode (a case's own mutation is removed from the matcher). Headline diagnostic accuracy is taken from D2b-test only. |
| Hand-crafted responses are written by the same researcher who designed the system | Second annotator; informal learner-style wording; development/test split.                                                    |
| Small sample sizes                                                                | Raw counts are reported; no inferential statistics are claimed.                                                              |
| LLM non-determinism                                                               | Three repeated runs; mean and range reported.                                                                                |
| Model updates change behaviour                                                    | Model name and version are frozen and recorded for each run.                                                                 |
| Prompt overfitting                                                                | Prompts and thresholds are tuned only on development data; headline results use the test split.                              |
| Mathematical consistency is mistaken for semantic correctness                     | Consistent-but-wrong rate is explicitly reported against human reference structures.                                         |
| Variable-definition matching is heuristic                                         | Deterministic string matching of the defined quantity; unmatched or tied definitions return `uncertain` with a clarification request rather than a forced category. |
| Simulated learners do not represent real learners                                 | D4 is used only for Agent-side evaluation; no learner-outcome claims are made.                                               |
| Chinese-specific E4 taxonomy may not generalise                                   | Results are explicitly scoped to the Chinese-language V1 task domain.                                                        |
| Question-bank composition may bias error coverage                                 | D2b includes independently designed cases across E1–E7 and includes uncertain, correct, multi-error, and line-by-line cases. |
| Automated leakage detection may miss paraphrased answers                          | All flagged hints and a random 20% of unflagged hints are manually reviewed.                                                 |
| Small test sets may produce unstable percentages                                  | Raw counts, repeated-run ranges, and failure cases are reported.                                                             |

---

# 10. What V1 Evaluation Does Not Claim

The V1 evaluation does **not** establish that:

* Guided Mode improves mathematics learning;
* Guided Mode is more effective than Quick Solve for learners;
* Challenge AI improves learners' ability to detect incorrect AI solutions;
* Challenge AI reduces inappropriate acceptance of AI advice;
* confidence framing changes learner reliance;
* active verification increases through repeated use;
* the system improves mathematical transfer;
* the diagnostic performance generalises to real learners;
* the diagnostic performance generalises beyond the V1 knowledge domain;
* the system improves trust calibration in human-AI interaction;
* D2a scores measure independent diagnostic or step-localisation accuracy.

These questions require separate studies with real participants and appropriate research design.

---

# 11. Files and Scripts

The V1 evaluation structure is:

```text
data/
└── question_bank.json               # frozen V1.3 question bank

eval/
├── structure_cases.json             # D1 (generated by build_d1.py — do not edit)
├── d1_extra_cases.json              # D1-16..30, hand-written source for D1
├── diagnostic_cases.json            # D2a (generated) + D2b (hand-crafted)
├── simulated_profiles.json          # D4 learner-profile definitions      (planned)
├── annotation_disagreements.md      # second-annotator log                 (planned)
├── run_eval.py                      # computes all Section 6 tables        (planned)
└── results/
    ├── step_localisation_d2a.json   # from eval_step_localisation.py
    ├── diagnosis_d2a.json           # from eval_diagnosis_d2a.py
    └── <run_id>/                    # full runs from run_eval.py           (planned)
        ├── config.json
        ├── diagnosis.csv
        ├── confusion_matrix_d2a.csv
        ├── confusion_matrix_d2b_test.csv
        ├── step_localization.csv
        ├── structure.csv
        ├── hints.csv
        ├── followup_burden.csv
        ├── mastery.csv
        └── error_analysis.md

scripts/
├── validate_question_bank.py        # mathematical and structural validation of the bank
├── build_d2a.py                     # question bank → D2a cases
├── build_d1.py                      # question bank + d1_extra_cases → D1
├── eval_step_localisation.py        # EQ4 on D2a
└── eval_diagnosis_d2a.py            # EQ2 on D2a (full and leave-one-out)

core/
├── normalizer.py                    # learner input → safe SymPy text (error_taxonomy §10.3–10.5)
├── math_checker.py                  # solution sets, step comparison (§10.6–10.7)
└── diagnosis.py                     # evidence → E1–E7, evidence level, status (§9–12)

tests/                               # pytest suite for core/
```

The exact filenames generated by `run_eval.py` may change during implementation, but every Section 6 reporting table must remain reproducible from the stored run configuration, reference annotations, and system outputs.

---

# 12. Future Learner-Side Evaluation (Outside V1)

The following questions require **real learners** and are outside the scope of the V1 Agent-side evaluation.

For school-age participants, such studies must not begin before the relevant:

* institutional ethics approval;
* consent / assent procedures;
* data-protection arrangements;
* participant safeguarding procedures

are in place.

| Research question                                                                                           | Possible future design                                                                    |
| ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Does Guided Mode improve learning compared with Quick Solve?                                                | Randomized comparison with pre/post mathematics tests.                                    |
| Does Challenge AI improve detection of incorrect AI solutions without increasing rejection of correct ones? | Pre/post Challenge AI tasks using held-out problems.                                      |
| Does confident AI wording increase acceptance of incorrect solutions?                                       | Controlled confidence-framing experiment, extending the `When AI Sounds Certain` project. |
| Does active verification increase over repeated sessions?                                                   | Longitudinal event-log analysis.                                                          |
| Does the system support near transfer?                                                                      | Performance on isomorphic transfer problems.                                              |
| Does diagnostic feedback improve subsequent error correction?                                               | Repeated-task design comparing feedback conditions.                                       |
| Does scaffolding level affect independent problem solving?                                                  | Controlled comparison of different hint policies with delayed post-tests.                 |

These studies should use preregistered hypotheses and appropriate participant-level statistical analysis where justified by sample size and design.

---

# 13. Design Principle

> **Report what the system does, including where it fails, before claiming what it might do for learners.**

The V1 evaluation therefore follows four principles:

1. **Separate Agent capability from learner outcomes.**
2. **Use independently annotated references wherever possible.**
3. **Report failure cases and uncertainty rather than hiding them behind aggregate scores.**
4. **Keep development targets distinct from validated research claims.**

The purpose of V1 is not to demonstrate educational effectiveness. It is to establish that the prototype's core evaluation-relevant behaviours are sufficiently **observable, testable, reproducible, and controlled** to justify subsequent learner-side research.

---

# 14. V1 Evaluation Readiness Checklist

Before presenting V1 results, confirm:

### Dataset

* [ ] D1 contains 30 structure cases: 15 bank, 10 reworded, 1 with learner work, 2 out-of-scope, 2 uncertain.
* [ ] D1 reference annotations are reviewed and committed before the first D1 run.
* [ ] D2a contains the actual mutation set from `question_bank.json`.
* [ ] D2b contains 40–60 hand-crafted cases.
* [ ] D2b contains at least 5 cases for each E1–E7 category.
* [ ] D2b contains 20–30% reference-correct cases.
* [ ] D2b contains at least 5 reference-uncertain cases.
* [ ] D2b contains at least 3 ambiguous-notation cases.
* [ ] D2b contains at least 5 final-answer-only incorrect cases.
* [ ] D2b contains at least 5 multi-error cases.
* [ ] D2b contains at least 10 line-by-line execution cases.

### Annotation

* [ ] Reference annotations were completed before system testing.
* [ ] At least 20% of D2b was independently annotated.
* [ ] Second-annotator disagreements are recorded.
* [ ] E3/E4 boundary disagreements have been reviewed.

### Evaluation control

* [ ] Development and test splits are frozen.
* [ ] Prompt and rule versions are recorded.
* [ ] Model version is recorded.
* [ ] Temperature and generation settings are recorded.
* [ ] Three runs are completed for LLM-dependent components.
* [ ] Reference annotations and system outputs are stored separately.

### Metrics

* [ ] Coverage and conditional accuracy are reported together.
* [ ] FPR is calculated only on reference-correct cases.
* [ ] Uncertainty appropriateness is reported.
* [ ] Confusion matrices contain raw counts.
* [ ] Consistent-but-wrong rate is reported.
* [ ] Step-localization accuracy and valid-step false alarms are reported.
* [ ] Hint leakage and four-criterion compliance are reported.
* [ ] Metacognitive follow-ups and evidence requests are separated.
* [ ] Challenge AI validity is checked.
* [ ] Q14 is treated according to its stored `v1_set_role`.

### Interpretation

* [ ] Development targets are not presented as educational benchmarks.
* [ ] No learner-effectiveness claims are made from V1 Agent-side results.
* [ ] D2a step localisation is described as agreement with the labelling criterion, not independent accuracy.
* [ ] D2a diagnosis is reported in leave-one-out mode and labelled as a development result.
* [ ] Failure cases are documented.
* [ ] Any post-development change is clearly distinguished from the frozen test result.

---

# 15. V1 Status

**Evaluation Plan:** V1.1
**Evaluation scope:** Agent-side evaluation only
**Primary domain:** Chinese one-variable linear-equation word problems
**Question bank:** V1.3 Final
**Challenge AI dataset:** 15 items — 9 incorrect / 6 correct
**Primary diagnostic taxonomy:** E1–E7
**Primary evaluation datasets:** D1–D5
**Headline results:** D1 and D2b test splits only
**LLM-dependent components:** 3 repeated runs
**Development targets:** Defined in Section 7
**Learner-side claims:** Explicitly excluded

**Status:** D1 and D2a built; normaliser, checker and rule-based diagnosis implemented and tested. D2b, D3, D4, `run_eval.py` pending.

---

# Change Log

| Version | Change |
| ------- | ------ |
| V1.0 | Initial canonical evaluation specification. |
| V1.1 | D1 composition updated to 15 / 10 / 1 / 2 / 2 with the scope-from-problem-statement rule (§3.8, §4, §4.1). D2a build rules, dev/test default and absence of reference-correct cases recorded (§4.2, §5.2). Interpretation of D2a step localisation added (§3.7, §6.3). D2a diagnosis reported in full and leave-one-out modes; leave-one-out is the cited figure (§6.1). Freezing defined (§5.1). E4 subtype collapsing stated (§3.1, §3.6). Two threats added (§9). Implemented scripts and file layout updated (§5.4, §11). Checklist extended (§14). |