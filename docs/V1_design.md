# AI Guided Math Learning Agent — V1 Design

## 1. Project Overview

### 1.1 Project Name

**AI 陪我学（AI Guided Math Learning Agent）**

### 1.2 Project Positioning

AI 陪我学 is a learning-oriented mathematics agent designed not only to provide answers, but to help students understand, construct, execute, evaluate, and verify mathematical solutions.

The project focuses on a specific problem in AI-assisted learning:

Generative AI can produce fluent and convincing solutions, but learners may accept an apparently plausible solution without independently checking the reasoning.

Therefore, the V1 system emphasizes **learner judgement and appropriate reliance**, rather than simply increasing the amount of explanation provided by AI.

The core design principle is:

> Do not only help students understand an AI solution; help them learn to judge whether the solution is correct.

### 1.3 V1 Knowledge Point

The initial Guided Mode focuses on:

**一元一次方程应用题（Linear Equation Word Problems）**

The system deliberately does not attempt to support all mathematics topics in Guided Mode.

If an uploaded question is outside the supported scope, the system explicitly communicates this limitation and provides Quick Solve instead.

This controlled scope prioritizes reliability and evaluability over broad but unreliable coverage.

---

# 2. V1 Scope and Priority

## 2.1 Supported Input

The intended system supports:

* Typed mathematical questions.
* Uploaded photographs of questions.
* Multiple questions contained in a single image.

These capabilities have different implementation priorities. See Section 3.

## 2.2 Supported Guided Mode

Guided Mode supports one knowledge point:

**一元一次方程应用题**

The learning process contains four core states:

1. S1 — Problem Understanding
2. S2 — Mathematical Modelling
3. S3 — Equation Execution
4. S4 — Evaluation / Verification

## 2.3 Unsupported Questions

For questions outside the supported knowledge point, the system follows:

Input → Scope Check → Quick Solve

The system does not force Guided Mode to operate outside its validated domain.

Example:

> “引导模式目前主要支持一元一次方程应用题。这道题暂时超出我的引导范围，我可以先帮你快速解题。”

---

# 3. P0 / P1 / P2 Priorities

The V1 design separates the core demonstrable system from secondary extensions.

## 3.1 P0 — Core Demonstration

P0 represents the minimum system that must work reliably for the project demonstration and technical evaluation.

P0 includes:

* Typed text input.
* Scope detection.
* Structured representation.
* Consistency checking.
* S1–S4 Guided Mode.
* Execution-error mutation.
* Challenge AI using question-bank items.
* Learning event logging.
* Learning report.
* Diagnostic evaluation using mutation-generated and hand-crafted responses.
* Simulated-student evaluation for diagnosis and scaffolding-related metrics.

P0 simulated-student evaluation is limited to:

* Error classification.
* Hint content compliance.
* Answer leakage.
* Follow-up behaviour.

Mastery decision evaluation is classified as P1.

If time becomes constrained, P0 should be protected first.

## 3.2 P1 — Important Extensions

P1 includes:

* Photograph and multimodal recognition.
* Near-transfer generation.
* Mastery decision evaluation.
* Modelling-error mutation for uploaded questions.
* AI confidence-framing condition.

P1 improves the usability and research value of the prototype but is not required for the minimum P0 demonstration.

## 3.3 P2 — Optional Extensions

P2 includes:

* Multiple-question recognition from a single image.
* Persistent learning history across sessions.

These features should only be implemented after the P0 pipeline is stable.

---

# 4. Four-Step System Pipeline

The intended complete architecture is:

User Input
↓
Step 1: Recognition and Confirmation
↓
Step 2: Scope Detection
↓
Step 3: Structured Representation and Consistency Checking
↓
Step 4: Guided Learning Agent
↓
S1 Understanding
↓
S2 Modelling
↓
S3 Execution
↓
S4 Evaluation / Verification
↓
Learning Evidence
↓
Mastery / Near Transfer / Learning Report

For the P0 implementation, text input can bypass image recognition:

Typed Question → Scope Detection → Structured Representation → Consistency Checking → Guided Mode

Photograph recognition is added in P1.

---

# 5. Step 1 — Recognition and Confirmation

## 5.1 Purpose

When image input is available, a multimodal model extracts the mathematical question.

If multiple questions are detected, the system can present them for selection.

The extracted text is displayed to the learner for confirmation or editing.

## 5.2 Design Principle

The learner should be able to correct recognition errors before the system performs mathematical reasoning.

This reduces the risk of generating a correct solution to an incorrectly recognized question.

The recognition model's confidence should be treated as a model-provided estimate, not a guaranteed probability of correctness.

---

# 6. Step 2 — Scope Detection

After the question has been confirmed, the system determines whether it belongs to the supported knowledge point.

Decision:

Is this a linear-equation word problem?

* Yes → Structured Representation.
* No → Quick Solve.
* Uncertain → Communicate uncertainty and avoid automatically entering Guided Mode.

Example structured output:

```json
{
  "in_scope": true,
  "knowledge_point": "一元一次方程应用题",
  "confidence": 0.94
}
```

The confidence field is a model estimate and should not be interpreted as a calibrated probability unless separately evaluated.

---

# 7. Step 3 — Structured Representation

For an in-scope question, the system extracts:

* Known quantities.
* Unknown quantity.
* Quantity relationships.
* Mathematical equation.
* Expected solution.
* Contextual verification conditions.

Example:

**Question:**

一件商品提价20%后售价为120元，求原价。

Possible representation:

```json
{
  "known_quantities": [
    {
      "name": "提价后的售价",
      "value": 120,
      "unit": "元"
    },
    {
      "name": "提价比例",
      "value": 0.20
    }
  ],
  "unknown": {
    "name": "原价",
    "symbol": "x",
    "unit": "元"
  },
  "relationship": "提价后的售价 = 原价 × 1.2",
  "equation": "1.2*x = 120",
  "expected_answer": 100
}
```

This is an actual linear-equation word problem rather than a direct arithmetic question.

The system should preserve the original wording alongside the structured representation so that later checks can refer to the original conditions.

---

# 8. Step 3.1 — Consistency Checking

The structured representation is subjected to multiple checks.

## 8.1 Programmatic Equation Solving

SymPy solves the extracted equation.

The backend checks whether the equation is mathematically solvable and whether the solution satisfies the extracted mathematical constraints.

## 8.2 Independent Solution

A separate LLM reasoning path independently solves the original question.

To reduce common-source errors, the independent solution should use:

* A different prompt.
* A separate reasoning context.
* Where feasible, a different model or model configuration.

The independent solution should not simply copy the structured equation generated by the first LLM call.

## 8.3 Original-Condition Check

The candidate answer is substituted back into the original problem conditions.

The system checks whether the answer satisfies the stated relationships and contextual constraints.

Where possible, this check should be implemented using code and explicitly represented mathematical conditions rather than relying solely on an LLM judgement.

---

# 9. Consistency Status

The three checks are interpreted as a consistency check, not as proof of semantic correctness.

Possible statuses:

```text
consistent
inconsistent
uncertain
```

## 9.1 Consistent

The structured equation, independent solution, and condition check agree.

This means:

The available computational and reasoning paths are mutually consistent.

It does not mean that the original question has been proven to be interpreted correctly.

## 9.2 Inconsistent

At least two validation paths disagree, or the candidate answer fails the original-condition check.

The system should not proceed as if the equation were reliable.

## 9.3 Uncertain

The system cannot confidently determine whether the representations agree.

Example response:

> “目前几种结果没有完全一致。为了避免带着错误题意继续学习，我们先一起核对一下题目中的数量关系。”

The system should record the consistency status in the event log.

---

# 10. Why Consistency Does Not Equal Correctness

The system explicitly recognizes the possibility of common-source semantic errors.

If the same LLM misreads the original problem and then independently reasons from the same mistaken interpretation, the two LLM outputs may agree.

SymPy can verify that the extracted equation is solved correctly, but it cannot determine whether the equation accurately represents the original natural-language problem.

Therefore:

**Three-way agreement indicates consistency, not guaranteed correctness.**

The evaluation dataset must include human-annotated reference structures to estimate the frequency of cases where the system is internally consistent but semantically incorrect.

The project should report this limitation rather than claiming that mathematical verification guarantees correct problem understanding.

---

# 11. Learning Modes

## 11.1 Quick Solve

Quick Solve provides:

* Final answer.
* Key solution steps.
* Concise explanation.
* Optional verification reminder.

Quick Solve is retained because a realistic product should not force every learner into a long guided interaction.

The system records:

```text
mode_selected = quick / guided
```

This can later support research on learning-mode choice and AI reliance.

## 11.2 Guided Mode

Guided Mode follows:

S1 Understanding → S2 Modelling → S3 Execution → S4 Evaluation / Verification.

The agent should not reveal the complete solution before the learner has had an opportunity to perform the relevant reasoning step.

---

# 12. State Design

## S1 — Problem Understanding

### Goal

Determine whether the learner understands:

* What the problem asks.
* Which quantities matter.
* What the target quantity is.

### Student Input

* Multiple-choice selection.
* Short text explanation.

### Judgement

* Multiple-choice response → Code-based evaluation.
* Free-text response → LLM classification.

### Example

“这道题最后要求我们求什么？”

### Transition

Correct understanding leads to S2.

Partial or incorrect understanding triggers targeted scaffolding within S1.

---

## S2 — Mathematical Modelling

### Goal

Determine whether the learner can:

* Define the unknown.
* Identify quantity relationships.
* Construct a valid equation.

### Student Input

The learner first states:

“我让 x 表示……”

Then provides an equation.

### Judgement

The system checks:

1. Whether the variable definition is meaningful.
2. Whether the equation can be solved.
3. Whether the equation's solution satisfies the original conditions.

The system must accept mathematically equivalent formulations rather than relying on string matching.

### Transition

Correct modelling leads to S3.

Incorrect modelling triggers diagnosis within the relevant S2 error categories.

---

## S3 — Equation Execution

### Goal

Determine whether the learner can correctly solve the equation.

### Student Input

Primarily:

* Numerical answer.
* Structured algebraic steps where available.

### Judgement

The system compares the learner's result with the mathematically checked solution.

For incorrect results, the system can compare the response against predefined execution-error patterns.

### Transition

Correct execution leads to S4.

Incorrect execution triggers diagnosis within E6/E7 and graduated scaffolding.

---

## S4 — Evaluation / Verification

### Goal

Determine whether the learner can evaluate a proposed answer or AI solution.

### Student Input

* Multiple-choice judgement.
* Optional explanation.

### Judgement

* Choice → Code-based evaluation.
* Explanation → LLM classification.

S4 evidence can also come from:

* Active verification behaviour.
* Challenge AI performance.

This prevents S4 from being permanently underrepresented when explicit verification questions are sampled rather than shown after every problem.

---

# 13. Diagnostic Framework

Diagnosis is a central technical component.

The system should not simply ask the LLM to provide an unconstrained diagnosis.

| State            | Student Input                 | Primary Judgement                              |
| ---------------- | ----------------------------- | ---------------------------------------------- |
| S1 Understanding | Multiple choice / short text  | Code for choice; LLM classification for text   |
| S2 Modelling     | Unknown definition + equation | SymPy + original-condition checking            |
| S3 Execution     | Numerical answer              | Code-based comparison + error patterns         |
| S4 Verification  | Choice + optional reason      | Code for choice; LLM classification for reason |

The candidate error types are constrained by state:

```text
S1 → E1
S2 → E2 / E3 / E4 / E5
S3 → E6 / E7
S4 → Verification behaviour
```

This reduces unnecessary ambiguity in diagnosis.

When multiple error types remain plausible, the system should return an uncertain diagnosis and use a targeted follow-up question.

---

# 14. Question Bank Design

## 14.1 Question Bank Size and Scope

The initial question bank will contain approximately **15–20 manually curated linear-equation word problems**.

All questions will be restricted to the V1 knowledge point.

The question bank serves three purposes:

1. Providing reliable default practice and demonstration content.
2. Providing reference answers and structures for evaluating the Agent.
3. Providing controlled items for Challenge AI and error-mutation testing.

The question bank is the primary source of stable, human-checked examples for the P0 demonstration.

## 14.2 Question-Level Data Structure

Each question should include the following fields:

| Field                         | Description                                                                |
| ----------------------------- | -------------------------------------------------------------------------- |
| question_id                   | Unique question identifier                                                 |
| question_text                 | Original problem statement                                                 |
| difficulty                    | Easy, medium, or hard                                                      |
| standard_unknown              | Definition of the reference unknown                                        |
| standard_equation             | Reference mathematical equation                                            |
| standard_answer               | Correct numerical or contextual answer                                     |
| subskill_tags                 | Relevant skills among S1–S4                                                |
| target_error_types            | Relevant E1–E7 categories                                                  |
| modelling_mutations           | One or two predefined incorrect modelling representations                  |
| correct_challenge_solution    | Correct solution version for Challenge AI                                  |
| incorrect_challenge_solutions | Predefined incorrect solution versions, each labelled with its error type  |
| verification_conditions       | Conditions used to check whether the answer satisfies the original problem |

The reference equation is not intended to be the only acceptable student formulation. Mathematically equivalent equations must still be accepted.

## 14.3 Difficulty Distribution

The initial 15–20 questions should include approximately:

* 30% easy questions;
* 50% medium questions;
* 20% hard questions.

Easy questions involve relatively direct quantity relationships.

Medium questions require translating a less explicit relationship into an equation.

Hard questions involve more complex wording, multiple relevant quantities, or additional reasoning about units and contextual constraints.

Difficulty labels are initial instructional design judgements, not empirically validated difficulty estimates.

## 14.4 Question Bank and Evaluation Separation

Question-bank items provide a controlled source of reference answers and predefined error patterns.

However, diagnostic evaluation must not rely exclusively on errors generated from these same predefined mutations.

Mutation-generated evaluation and hand-crafted realistic student responses must be reported separately.

The question bank supports controlled testing but does not, by itself, establish generalization to unseen learner responses.

---

# 15. Common Error Taxonomy

The V1 taxonomy is an initial instructional taxonomy, not a claim of empirical completeness.

## E1 — Problem Goal / Understanding Error

**State:** S1

The learner misunderstands what the question asks.

Example:

The question asks for the selling price, but the learner calculates the discount amount.

## E2 — Unknown Definition Error

**State:** S2

The learner defines the unknown ambiguously or changes its meaning during the solution.

Example:

x initially represents the number of books but later represents the total price.

## E3 — Quantity Relationship Error

**State:** S2

The learner establishes an incorrect mathematical relationship between quantities.

Example:

The learner constructs an incorrect perimeter relationship.

## E4 — Language-to-Mathematics Translation Error

**State:** S2

The learner incorrectly translates an explicitly stated linguistic relationship into mathematical form.

Example:

For “比原来增加20%”, the learner writes 0.2x instead of 1.2x.

### E3 vs E4

The distinction is:

* E3: The underlying quantity relationship is constructed incorrectly.
* E4: The stated relationship is understood linguistically but translated incorrectly into mathematical notation.

Detailed annotation rules and examples are defined separately in `error_taxonomy.md`.

## E5 — Unit / Magnitude Error

**State:** S2 or S4

The learner mixes units or accepts an implausible magnitude.

Example:

Using minutes directly with km/h without converting units.

## E6 — Arithmetic Execution Error

**State:** S3

The learner has a correct equation but makes an arithmetic mistake while solving it.

## E7 — Algebraic Operation / Sign Error

**State:** S3

The learner performs an algebraic operation incorrectly.

Example:

Correct:

```text
2x = 26
x = 13
```

Incorrect:

```text
2x = 26
x = 26
```

The key distinction is that E7 occurs during equation execution, rather than by changing the original modelling equation.

## Verification Is Not an Error Type

Failure to verify is treated as a learning behaviour, not an error category.

It is recorded separately:

```text
active_verification = true / false
```

This separates mathematical errors, learner behaviour, and Agent state.

---

# 16. Error Mutation Engine

The mutation engine has two separate layers.

## 16.1 Execution-Level Mutation

Execution errors are largely equation-independent.

For a mathematically checked equation, code can systematically generate errors such as:

* Incorrect transposition.
* Sign reversal.
* Incorrect arithmetic.
* Incorrect division.

Example:

Correct:

```text
2x + 6 = 20

2x = 14

x = 7
```

E7 execution error:

```text
2x + 6 = 20

2x = 26

x = 13
```

This layer can operate automatically on question-bank and uploaded questions once a suitable equation has been established.

## 16.2 Modelling-Level Mutation

Modelling errors depend on the semantic meaning of the original question.

Examples:

* Incorrect quantity relationship.
* Incorrect percentage translation.
* Incorrect unknown definition.

For question-bank items, these error versions are manually predefined.

For uploaded questions, the LLM may propose candidate incorrect equations, after which the system checks that:

1. The candidate is mathematically solvable.
2. It differs from the reference representation.
3. It corresponds to a defined error category.
4. The resulting answer differs where the mutation is intended to produce a different answer.
5. The candidate is consistent with the proposed error mechanism.

The final mutation should not be accepted solely because an LLM proposed it.

## 16.3 Ambiguous Error Mapping

Different error types may produce the same final numerical answer.

If multiple error types are consistent with the observed response, the system must return uncertain rather than arbitrarily selecting one.

The agent can then ask an additional diagnostic question.

Example:

“你在列这个方程时，x 表示的是哪一个量？”

This allows the system to distinguish between competing hypotheses.

---

# 17. Challenge AI

## 17.1 Purpose

Challenge AI is an explicit learner activity:

**找茬挑战 / Challenge AI**

The learner evaluates whether a proposed AI solution is correct.

The system should never deceptively present an error as an actual spontaneous AI failure.

## 17.2 Position in the Learning Flow

Challenge AI is a separate, explicitly labelled activity that learners can enter after completing a problem or from the learning report.

It is not a mandatory step in every S4 interaction.

S4 remains responsible for evaluating the learner's own solution and verification behaviour.

Challenge AI provides an additional opportunity to evaluate AI-generated solutions.

Challenge AI results can contribute to the learner's S4 judgement evidence and learning report.

The interface should provide a separate entry point, such as “找茬挑战”, while keeping the core Guided Mode flow unchanged.

## 17.3 Correct / Incorrect Balance

Challenge AI contains approximately:

* 60% incorrect AI solutions.
* 40% correct AI solutions.

This prevents the learner from adopting the trivial strategy of always rejecting the AI.

Two complementary measures are recorded.

### AI-Error Detection Accuracy

Percentage of incorrect AI solutions correctly identified.

### Correct-AI Rejection Rate

Percentage of correct AI solutions incorrectly rejected.

Together these capture both over-reliance and over-rejection.

## 17.4 Predefined Error Solutions

Each question-bank item should have predefined incorrect solution versions.

Each version is associated with a known error type such as E3, E4, E6, or E7.

The correct and incorrect solutions are checked before being presented.

This makes Challenge AI controllable, reproducible, measurable, and suitable for evaluation.

---

# 18. AI Confidence Framing

Challenge AI can optionally vary the wording used to present the same underlying solution.

### High-Confidence Condition

“这个解法一定是正确的。”

### Calibrated Condition

“根据目前的题意，这个解法看起来是正确的，但你可以再检查一下。”

The mathematical content remains unchanged.

V1 treats this as an experimental condition rather than a demonstrated causal effect.

The confidence-framing condition is P1.

---

# 19. AI Uncertainty

The system should communicate uncertainty when observable evidence indicates uncertainty.

Potential triggers include:

1. LLM solution and SymPy solution disagree.
2. Structured representation and independent solution disagree.
3. Condition checking fails.
4. Free-text classification confidence is low.
5. Multiple error types fit the learner's response.
6. Image recognition is ambiguous.
7. Multiple plausible interpretations of the question remain.

The system should explicitly communicate uncertainty rather than fabricate confidence.

Model-provided confidence scores should not be assumed to be calibrated probabilities.

---

# 20. Adaptive Scaffolding

The agent uses graduated scaffolding:

```text
Level 1 — Prompt / Question
        ↓
Level 2 — Targeted Hint
        ↓
Level 3 — More Explicit Hint
        ↓
Level 4 — Explanation / Partial Solution
```

The agent should stop escalating when the learner demonstrates sufficient understanding.

The backend controls the allowed hint level.

The LLM generates the wording within the constraints of that level.

The system evaluates whether the generated wording complies with the intended hint level rather than assuming that backend state control guarantees content compliance.

---

# 21. Follow-up Question Budget

For junior-high learners, excessive questioning can make the interaction inefficient.

V1 therefore limits follow-up questions.

Default:

**1–2 metacognitive follow-up questions per problem.**

Additional questions are allowed when repeated misunderstanding makes them necessary.

Possible triggers:

* Incorrect answer.
* Correct answer with weak reasoning.
* Ambiguous diagnosis.
* Failure to verify.
* Sampled verification opportunity.

The system records:

```text
follow_up_count
```

and calculates:

Average follow-up questions per problem.

---

# 22. Active Verification

Active verification is an observable learner behaviour.

A verification event is classified as active when the learner initiates verification without an immediately preceding explicit agent instruction to verify.

Examples:

* Clicking “我来检查一下”.
* Independently substituting an answer.
* Independently checking contextual reasonableness.

The system records:

```text
active_verification = true
```

and calculates:

**Active Verification Rate**

The denominator should be defined consistently in implementation, preferably as eligible problem-solving opportunities in which the learner had an opportunity to verify.

---

# 23. Learning Event Log

V1 includes an event log.

Example:

```json
{
  "session_id": "anonymous_001",
  "question_id": "Q08",
  "state": "S2",
  "student_input_type": "equation",
  "diagnosed_error": "E3",
  "diagnosis_status": "definite",
  "hint_level": 2,
  "follow_up_count": 1,
  "active_verification": false
}
```

Events may include:

* Question selection.
* Mode selection.
* Scope decision.
* Consistency status.
* State transition.
* Learner response.
* Diagnosed error.
* Diagnosis status.
* Hint level.
* Follow-up count.
* Challenge AI judgement.
* AI-error detection.
* Correct-AI rejection.
* Active verification.
* Final answer.
* Mastery evidence.
* Near-transfer result.

The event log should distinguish missing evidence from a negative outcome.

---

# 24. Mastery Judgement

V1 uses a simple rule-based provisional mastery model.

For each subskill:

A learner is provisionally considered to have demonstrated mastery when they successfully solve two consecutive relevant questions with little or no prompting.

Possible status values:

```text
mastered
not_yet_mastered
insufficient_evidence
```

This is a practical V1 heuristic rather than a formal psychometric model.

Mastery decision evaluation is P1.

---

# 25. Mastery Decision Evaluation

The mastery rule is evaluated against simulated learners with predefined true states.

Example:

```text
Simulated Student A
-------------------
S1: mastered
S2: not_mastered
S3: mastered
S4: insufficient_evidence

Typical error:
E7
```

The simulated learner's responses are generated according to the predefined profile.

The system's mastery decision is compared against the known true state.

Metric:

**Mastery Decision Accuracy**

This avoids evaluating the rule against its own output.

The test should include cases where:

* The learner guesses correctly.
* The learner succeeds only after substantial prompting.
* The learner performs inconsistently.
* The learner has mastered some subskills but not others.

This is a P1 evaluation component, not a P0 success criterion.

---

# 26. Simulated Student Design

P0 simulated-student evaluation is limited to diagnosis and scaffolding-related metrics.

The simulator should not rely on an LLM to invent arbitrary student reasoning.

## 26.1 Deterministic Core

Rules define:

* The student's response profile.
* Correct or incorrect answer.
* Equation structure.
* Error type.
* Verification behaviour.
* Expected response to a hint.

This provides a reliable evaluation ground truth.

## 26.2 LLM Language Variation

An LLM may optionally rewrite a deterministic response into more natural student language.

Example:

Deterministic response:

“把20%的增加量算成0.2x。”

Possible language variation:

“我觉得应该就是把原来的数乘0.2吧。”

The mathematical content remains controlled by the simulator.

This prevents the evaluation benchmark from depending on an LLM's ability to role-play students accurately.

## 26.3 P0 Evaluation Scope

P0 simulated-student evaluation covers:

* Diagnostic classification.
* Hint content compliance.
* Answer leakage.
* Follow-up behaviour.

Mastery decision evaluation is P1.

---

# 27. Diagnostic Evaluation Dataset

The diagnostic test set must contain two distinct sources.

## 27.1 Mutation-Generated Errors

These are generated systematically by the error mutation engine.

Purpose:

* Test whether the technical pipeline works.
* Verify that known error transformations can be recognized.

These results should be reported separately.

They primarily demonstrate controlled pipeline performance.

## 27.2 Hand-Crafted Realistic Student-Style Errors

A separate dataset is manually constructed to resemble realistic learner responses.

The target size is approximately **40–60 responses**, with at least five examples for each error category E1–E7.

The dataset should include:

* Incomplete reasoning.
* Ambiguous wording.
* Multiple simultaneous errors.
* Partially correct answers.
* Informal student language.
* Errors not generated by the mutation engine.

Purpose:

Evaluate whether the diagnostic system generalizes beyond its own generated patterns.

The two datasets must never be collapsed into a single headline accuracy without reporting their sources.

---

# 28. Error Annotation and Dataset Review

The researcher will perform the initial annotation of the hand-crafted diagnostic dataset.

Each response should be annotated with:

* Reference error type or types.
* Relevant learning state.
* Whether the response is partially correct.
* Whether the evidence supports a definite diagnosis or an uncertain classification.

Approximately **20% of the dataset** will be independently reviewed by a peer or a member of the researcher's academic supervisory group, subject to availability.

Disagreements will be documented and resolved through discussion.

The review is intended to identify ambiguous categories and improve annotation rules, rather than to claim formal inter-rater reliability from a small sample.

Particular attention should be given to:

* E3 versus E4.
* Multiple simultaneous errors.
* Partially correct modelling.
* Ambiguous responses.

If annotation disagreement is substantial, the taxonomy or annotation rules should be revised before interpreting diagnostic accuracy.

Mutation-generated and hand-crafted datasets will remain separate throughout evaluation and reporting.

---

# 29. Near Transfer

Near-transfer problems retain the underlying mathematical structure while changing:

* Numerical values.
* Surface context.
* Wording.

Example:

Original problem:

A product increases in price by 20% and becomes 120 yuan.

Near-transfer problem:

A quantity increases by 25% and becomes 150 units.

The generated problem must be programmatically checked before being presented.

The system should verify that:

* The new problem is mathematically valid.
* The intended equation is correct.
* The solution satisfies the generated conditions.
* Any required answer constraints are satisfied.

The transfer result is treated as evidence about performance on a related problem, not as evidence of long-term learning.

Near transfer is P1.

---

# 30. Learning Report

The learner receives a concise report containing the following components.

## 30.1 Skill Evidence

Example:

```text
题意理解       已掌握
数学建模       进行中
方程计算       已掌握
结果验证       证据不足
```

The report should distinguish a lack of evidence from a demonstrated lack of mastery.

## 30.2 Frequent Errors

Example:

```text
主要错误：

E3 等量关系建立错误
E7 代数操作/变号错误
```

## 30.3 Judgement Behaviour

Example:

```text
主动验证率：60%

AI 错误识别率：75%

正确 AI 误拒率：20%
```

The report should describe observed behaviour rather than making unsupported claims about psychological characteristics.

---

# 31. Anonymous Learning History

The system uses anonymous learner/session identifiers.

Example:

```text
anonymous_001
anonymous_002
```

Where implemented, the system may associate multiple sessions with the same anonymous identifier.

Stored information may include:

* Completed questions.
* State performance.
* E1–E7 error history.
* Mastery evidence.
* Verification behaviour.
* Challenge AI performance.
* Near-transfer performance.

No unnecessary personally identifiable information should be collected.

Persistent cross-session history is P2.

---

# 32. Agent Architecture

The system uses a backend-controlled state machine.

```text
                ┌─────────────────────┐
                │   Student Interface │
                └──────────┬──────────┘
                           ↓
                ┌─────────────────────┐
                │   State Manager     │
                │   S1 → S2 → S3 → S4│
                └──────────┬──────────┘
                           ↓
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
   Diagnosis          Hint Strategy       Validation
        ↓                  ↓                  ↓
      LLM              Rule Engine          SymPy
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ↓
                    Tutor Response
```

## 32.1 State Manager

Controls:

* Current state.
* Valid transitions.
* Hint level.
* Follow-up budget.
* Mastery evidence.
* Event logging.

## 32.2 LLM

Responsible primarily for:

* Natural-language generation.
* Free-text classification.
* Explanation.
* Supportive dialogue.

## 32.3 Programmatic Components

Responsible for:

* Equation solving.
* Numerical comparison.
* Mathematical checking.
* Error mutation.
* State constraints.

This separation reduces the risk of allowing the LLM to make uncontrolled mathematical or state-transition decisions.

---

# 33. Structured Agent Output

The LLM should preferably return structured information.

Example:

```json
{
  "state": "S2",
  "diagnosis": "The learner may have confused the relationship between the two quantities.",
  "strategy": "targeted_hint",
  "message": "先看看题目中的两个数量分别表示什么，再想一想它们之间有什么关系。",
  "expected_concept": "quantity_relationship",
  "mastery_evidence": false
}
```

The backend validates the output.

The LLM does not have unrestricted authority to change the learning state.

---

# 34. V1 Evaluation

P0 evaluation focuses on Agent-side reliability, controllability, and generalization beyond self-generated patterns.

## 34.1 Structure Success Rate

Measures whether the system correctly:

* Identifies scope.
* Extracts the required structure.
* Generates a mathematically valid representation.
* Passes consistency checking.

The initial test set contains approximately 30 simulated uploaded questions, including:

* Supported questions.
* Unsupported questions.
* Ambiguous questions.
* Different surface forms.

The reference structure is human-annotated, rather than generated by the same system.

This allows the evaluation to detect cases where the system is internally consistent but semantically wrong.

Results should distinguish:

* Scope classification accuracy.
* Structural field accuracy.
* Equation correctness.
* Consistency-check outcome.

A single aggregate structure success rate may be reported alongside these component metrics, with its definition made explicit.

## 34.2 Diagnostic Accuracy and Coverage

Diagnostic evaluation uses two complementary metrics.

### Diagnostic Coverage

Diagnostic Coverage measures the proportion of eligible test responses for which the system produces a definite error classification.

```text
Coverage =
Responses with a definite diagnosis
/
All eligible test responses
```

Responses classified as uncertain or ambiguous are not counted as definite diagnoses.

### Conditional Diagnostic Accuracy

Conditional Diagnostic Accuracy measures the proportion of definite diagnoses that match the reference annotation.

```text
Conditional Accuracy =
Correct definite diagnoses
/
All definite diagnoses
```

The two metrics must always be reported together.

A system cannot claim high diagnostic performance merely by returning uncertain for difficult cases.

Results must be reported separately for:

1. Mutation-generated errors.
2. Hand-crafted realistic student-style errors.

Where useful, results should also be broken down by E1–E7 and by learning state.

For responses with multiple valid error labels, evaluation should use the predefined annotation policy rather than forcing a single label where the evidence does not support one.

## 34.3 Answer Leakage Rate

Measures how frequently the agent reveals information that should not yet be revealed at the current scaffolding level.

The evaluation should use predefined leakage criteria and inspect actual generated responses.

## 34.4 Hint Content Compliance

Evaluates the actual LLM-generated wording.

For example:

A Level 1 prompt should not directly reveal the equation.

A Level 2 hint may point toward the relevant relationship but should not provide the complete solution.

This metric evaluates generated content rather than assuming that backend state control guarantees content compliance.

## 34.5 Average Follow-up Questions

Measures interaction burden:

Total follow-up questions / number of eligible problems.

The evaluation should report the relevant test set and treatment of incomplete sessions.

## 34.6 Challenge AI Metrics

Two primary measures:

* AI-error detection accuracy.
* Correct-AI rejection rate.

Additional analysis can compare performance across:

* Error types.
* Correct and incorrect solution conditions.
* Confidence-framing conditions, when P1 is implemented.

---

# 35. P0 Success Criteria

The P0 demonstration is considered successful when the following works end-to-end:

Typed Question
↓
Scope Detection
↓
Structured Representation
↓
Consistency Checking
↓
Guided Mode
↓
S1
↓
S2
↓
S3
↓
S4
↓
Event Log
↓
Learning Report

P0 also includes:

* Execution-error mutation.
* Challenge AI on question-bank items.
* Diagnostic evaluation on mutation-generated and hand-crafted responses.
* Simulated-student evaluation for diagnosis and scaffolding-related metrics.

Photograph recognition, near transfer, mastery decision evaluation, and other P1/P2 features are not required for the P0 demonstration.

---

# 36. Design Basis

The system draws on several learning and human-AI interaction concepts.

## Scaffolding and Fading

The agent provides temporary support and reduces assistance as the learner demonstrates understanding.

## Generation Effect

The learner is encouraged to generate intermediate reasoning before receiving the complete AI solution.

## Self-Explanation

Asking learners to articulate what a variable or equation represents makes their reasoning more explicit.

## Appropriate Reliance / Trust Calibration

Challenge AI and verification tasks frame AI assistance as something to evaluate rather than automatically accept or reject.

These ideas support the central design principle:

AI should support learner judgement rather than replace learner judgement.

The theoretical rationale and relevant literature will be developed further in the project's research documentation.

---

# 37. Connection to Research Motivation

The project connects two research concerns.

The MSc research examines how learners use and evaluate Generative AI in learning and problem-solving.

The related HCI project, **When AI Sounds Certain**, investigates whether confident AI language can affect reliance on incorrect AI advice.

AI 陪我学 translates these concerns into a concrete learning-system design.

The conceptual chain is:

AI capability → Human judgement → AI communication → Appropriate reliance.

The V1 prototype does not claim to establish causal educational effects.

Instead, it implements measurable mechanisms that can support future empirical research.

---

# 38. Quick Solve as a Research Variable

Quick Solve remains available as a low-friction mode.

The system records:

```text
mode_selected = quick / guided
```

This allows later analysis of:

* Mode preference.
* Switching behaviour.
* Verification after direct answers.
* Potential patterns of AI reliance.

Quick Solve can optionally end with:

“答案出来了。你要不要花 10 秒检查一下这个结果是否符合题目条件？”

This provides a lightweight verification opportunity.

---

# 39. Learner-Side Research — Future Work

The following are research hypotheses rather than V1 findings:

* Whether Guided Mode improves learning.
* Whether Challenge AI improves AI-error detection.
* Whether confidence framing changes reliance.
* Whether active verification increases.
* Whether the system improves transfer.
* Whether learners become better calibrated toward AI.

These questions require evaluation with real learners.

No causal learner-outcome claims should be made based solely on the P0 prototype or simulated-student evaluation.

---

# 40. V2 Roadmap

Potential extensions include:

## 40.1 Probabilistic Mastery

Replace the two-consecutive-success rule with probabilistic knowledge-tracing approaches.

## 40.2 Distant Transfer

Test substantially different problem structures.

## 40.3 Richer Knowledge Tracing

Explore graph-based or other sequential learner models.

## 40.4 Multi-Concept Question Bank

Expand beyond one knowledge point.

## 40.5 Learner-Side Experimental Evaluation

Conduct controlled studies with real learners.

## 40.6 Teacher / Parent Dashboard

Provide authorized users with aggregated learning information.

## 40.7 Multimodal Learning Support

Explore voice, visual explanation, or other modalities after the core architecture is validated.

---

# 41. Technical Stack

## 41.1 Frontend

* HTML.
* CSS.
* JavaScript.

The tutoring interface uses ordinary HTML/CSS/JavaScript.

jsPsych is not required for the core tutoring interface.

It may be introduced later for controlled behavioural experiments involving conditions such as AI confidence framing.

## 41.2 Backend

* Python.
* Flask.

## 41.3 AI

DeepSeek or another validated multimodal/text model depending on API capabilities.

The exact multimodal provider must be confirmed during implementation before P1 image recognition is developed.

The existing text-based DeepSeek integration can be retained for P0.

## 41.4 Mathematical Validation

* SymPy.

## 41.5 Data

* JSON.
* CSV.
* Local session/event storage.

## 41.6 Development

* VS Code.
* Git / GitHub.

---

# 42. Privacy and Data Minimisation

Because the intended users may include school-age learners, V1 follows a data-minimisation principle.

The system should avoid collecting unnecessary personally identifiable information.

Anonymous identifiers should be used where learning history is required.

If the system is later evaluated with minors in a research setting, appropriate institutional ethics review, consent/assent procedures, and data-protection requirements must be completed before collecting learner data.

---

# 43. V1 Non-Goals

The following are not required for the P0 core:

* Training a custom mathematical LLM.
* Building a large-scale question bank.
* Full mathematics curriculum coverage.
* 3D avatars.
* Voice tutors.
* AI-generated educational videos.
* Advanced teacher dashboards.
* Advanced knowledge tracing.
* Long-term educational outcome claims.
* Unrestricted autonomous Agent behaviour.

The project prioritizes:

Reliable problem handling + adaptive scaffolding + learner judgement + measurable evaluation.

---

# 44. Final Design Principle

The central principle of AI 陪我学 is:

> Do not make AI more persuasive than necessary. Make the learner better at judging AI.

The project treats correctness, uncertainty, verification, appropriate reliance, and learner judgement as first-class design concerns.

The goal of V1 is not to build the largest possible AI tutor.

It is to build a **small, controllable, testable learning Agent** that demonstrates how AI assistance can be designed around learner judgement rather than answer delivery.
