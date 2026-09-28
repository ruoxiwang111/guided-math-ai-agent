# Error Taxonomy and Diagnostic Rules

**Project:** AI Guided Math Learning Agent
**Version:** V1.2
**Status:** Revised Design Specification
**Related Documents:**

* `docs/V1_design.md`
* `docs/question_bank.md`
* `docs/evaluation_plan.md`

---

## 1. Purpose

This document defines the operational error taxonomy, diagnostic procedures, instructional feedback rules, input normalization rules, and evaluation metrics for the V1 guided mathematics tutoring system.

The system aims not only to determine whether a learner's answer is correct, but also to identify the likely source of an error and provide an appropriate hint that supports independent reasoning.

The diagnostic system follows six principles:

1. Diagnose the learner's reasoning, not merely the final answer.
2. Distinguish mathematical modelling errors from calculation and algebraic execution errors.
3. Treat error-pattern matching as a diagnostic hypothesis, not definitive evidence.
4. Prefer deterministic mathematical checks when reliable checks are available.
5. Avoid falsely identifying a correct answer as incorrect.
6. Return an uncertain diagnosis when the available evidence is insufficient.

An error label represents a hypothesis about the learner's current reasoning. It is not a definitive assessment of the learner's ability or mathematical understanding.

The system should therefore be precise about what it can verify, cautious about what it infers, and helpful about what the learner can do next.

---

# 2. Diagnostic Scope

V1 Guided Mode supports one topic:

**一元一次方程应用题 (linear equation word problems).**

The system uses four learning states:

| State             | Learning objective                                       | Relevant categories            |
| ----------------- | -------------------------------------------------------- | ------------------------------ |
| S1: Understanding | Identify the target quantity and understand the question | E1                             |
| S2: Modelling     | Define the unknown and construct a valid equation        | E2, E3, E4, E5                 |
| S3: Execution     | Solve the equation using valid mathematical operations   | E6, E7                         |
| S4: Evaluation    | Check the solution against the original conditions       | E5 and verification behaviours |

Only error categories relevant to the current state should be considered.

An incorrect final answer does not automatically indicate a calculation or algebraic error. If the original equation is incorrect, the primary error may instead be a modelling error.

The backend state manager determines the current state and the categories that may be considered. The language model must not independently override these constraints.

---

# 3. Error Categories

## E1 — Misunderstanding the Question Goal

**State:** S1 — Understanding

### Definition

The learner misunderstands what the problem asks them to determine, confuses the target quantity with a known or intermediate quantity, or answers a different question.

### Typical example

A problem asks for the total distance travelled, but the learner gives only the distance travelled during the first stage.

### Diagnostic evidence

Evidence may include:

* The learner explicitly identifies the wrong target quantity.
* The learner's explanation demonstrates confusion between the requested quantity and an intermediate quantity.
* A follow-up question confirms that the learner has misunderstood what must be found.

An incorrect numerical answer alone is insufficient evidence for E1.

### Diagnostic question

“这道题最后要求我们求什么？请用自己的话说一遍。”

### Four-level scaffolding

| Level                  | Hint                                 |
| ---------------------- | ------------------------------------ |
| 1 — Prompt             | “先看题目的最后一句，想一想题目要求我们求什么。”            |
| 2 — Targeted hint      | “题目要求的是整个过程的结果，还是其中某一个阶段的结果？”        |
| 3 — More explicit hint | “把题目最后一句中的目标量圈出来，再区分它与题目已经给出的已知量。”   |
| 4 — Explanation        | “这道题要求的是……。前面提到的……只是中间量，不能直接作为最终答案。” |

### Resolution evidence

The learner correctly identifies the target quantity in their own words or selects the correct target from a set of options.

---

## E2 — Unclear or Inconsistent Definition of the Unknown

**State:** S2 — Modelling

### Definition

The learner fails to define the unknown clearly, changes its meaning during the solution, or uses a variable that does not correspond to the quantities in the equation.

### Typical example

The learner defines \(x\) as the original price but later uses \(x\) to represent the discounted price without adjusting the relationship.

### Diagnostic evidence

Evidence may include:

* The learner cannot explain what the variable represents.
* The variable refers to different quantities in different parts of the solution.
* The equation is inconsistent with the learner's stated definition.

### Boundary with E3 and E4

E2 concerns the meaning of the variable itself.

If the variable is clearly defined but the relationship between quantities is wrong, consider E3 or E4.

### Diagnostic question

“你设的 \(x\) 表示什么？后面每次出现 \(x\)，都表示同一个量吗？”

### Four-level scaffolding

| Level                  | Hint                                               |
| ---------------------- | -------------------------------------------------- |
| 1 — Prompt             | “列方程之前，先想清楚你准备设哪个量为 \(x\)。”                        |
| 2 — Targeted hint      | “试着补全：设 \(x\) 表示……。这个量在题目中对应哪一部分？”                 |
| 3 — More explicit hint | “检查方程中每一个 \(x\)，它们是否都表示你刚才定义的同一个量？”                |
| 4 — Explanation        | “可以设 \(x\) 表示……。因此，方程中的……应表示……，不能在中途改变 \(x\) 的含义。” |

### Resolution evidence

The learner defines the unknown consistently and uses it correctly throughout the equation.

---

## E3 — Incorrect Relationship Between Quantities

**State:** S2 — Modelling

### Definition

The learner correctly identifies the relevant quantities and defines the unknown, but constructs an equation that does not represent the relationship between those quantities.

E3 is the **default category for quantity-relationship modelling errors that do not match an explicitly defined E4 phrase pattern**.

This rule is important for making E3 and E4 operationally distinguishable during annotation and implementation.

### Typical examples

#### Example 1 — Incorrect total relationship

A problem states that two quantities have a total of 80.

The learner correctly identifies the quantities but constructs an equation that does not represent the total relationship.

For example:

$$
x-20=80
$$

when the intended relationship requires both quantities to be represented in the equation.

This is E3 **because the error is not being classified as a specific closed-list language-translation error**.

#### Example 2 — Missing quantity

A problem states that the total cost consists of a fixed fee plus a variable charge.

The learner correctly identifies both quantities but includes only the variable charge in the equation.

This is E3.

#### Example 3 — Incorrect structural relationship

The learner correctly defines two quantities but treats a total relationship as a difference or omits one component, where the mistake does not match an E4 closed-list pattern.

This is E3.

### Diagnostic evidence

Evidence may include:

* The unknown and relevant quantities are clearly defined.
* The equation does not satisfy the original relationship.
* The error cannot be matched to a specific phrase pattern in the E4 closed list.
* The learner's equation itself provides enough information to establish the incorrect relationship.

### Boundary with E4

E3 and E4 are mutually exclusive as primary labels for the same modelling mistake.

Use the following decision rule:

> **If the incorrect expression can be traced to a phrase in the closed E4 list, and the student's expression matches the documented error pattern, classify it as E4. Otherwise, if the quantities are defined but their relationship is incorrectly represented, classify it as E3.**

The mere presence of an E4 phrase in the question is **not sufficient** to assign E4.

The learner's actual expression must match the relevant translation error.

If the evidence cannot distinguish E3 from E4, return `uncertain`.

### Diagnostic question

“你方程中的每一部分分别对应题目里的哪个量？它们之间的关系和原题一致吗？”

### Four-level scaffolding

| Level                  | Hint                                     |
| ---------------------- | ---------------------------------------- |
| 1 — Prompt             | “先不要计算，想一想题目中几个量之间是什么关系。”                |
| 2 — Targeted hint      | “试着先用文字表达它们的关系，再把文字关系转换成方程。”             |
| 3 — More explicit hint | “分别写出每个量的表达式，再根据题目给出的总量或相等关系把它们连接起来。”    |
| 4 — Explanation        | “题目中的……与……之间满足……关系。因此，应先表示……，再根据……写出方程。” |

### Resolution evidence

The learner constructs an equation that represents the original relationship and can explain the meaning of its terms.

---

# 4. E4 — Closed-List Chinese Language-to-Mathematics Translation Error

**State:** S2 — Modelling

## 4.1 Definition

E4 refers specifically to incorrect translation of a predefined Chinese mathematical phrase into a mathematical expression or relationship.

E4 uses a **closed phrase-pattern list**.

Only errors that satisfy the conditions of an entry in this list may be classified as E4.

All other quantity-relationship modelling errors should be classified as E3 when sufficient evidence exists.

This closed-list design reduces disagreement between E3 and E4 during annotation and allows parts of the diagnosis to be implemented using deterministic pattern matching.

---

## 4.2 Closed Phrase-Pattern List

| ID    | 中文原文       | Intended relationship | Typical incorrect translation | Diagnostic boundary                                    |
| ----- | ---------- | --------------------- | ----------------------------- | ------------------------------------------------------ |
| E4-01 | 甲比乙多5      | 甲 = 乙 + 5             | 甲 = 乙 − 5 / 乙 = 甲 + 5         | Reversed comparison direction                          |
| E4-02 | 甲比乙少5      | 甲 = 乙 − 5             | 甲 = 乙 + 5 / 乙 = 甲 − 5         | Reversed comparison direction                          |
| E4-03 | 比原来增加了20%  | 新量 = 1.2x             | 新量 = 0.2x                     | Represents only the increase rather than the new total |
| E4-04 | 增加到原来的120% | 新量 = 1.2x             | 新量 = 0.2x / 新量 = x + 1.2      | Confuses final proportion with amount of increase      |
| E4-05 | 增加到120     | 新量 = 120              | 新量 = x + 120                  | Treats final value as an increment                     |
| E4-06 | 打八折        | 新价 = 0.8x             | 新价 = x − 0.8                  | Treats 0.8 as a fixed subtraction                      |
| E4-07 | 甲是乙的3倍     | 甲 = 3乙                | 乙 = 3甲                        | Reverses multiplicative relationship                   |
| E4-08 | 比原来少了三分之一  | 新量 = \(\frac{2}{3}x\) | 新量 = \(\frac{1}{3}x\)         | Represents amount removed rather than amount remaining |

Here \(x\) represents the original quantity unless the problem explicitly defines another variable.

The table is a V1 operational taxonomy, not an exhaustive description of all possible Chinese mathematical language.

---

## 4.3 E4 Diagnostic Criteria

An E4 diagnosis requires **all** of the following:

1. The original problem contains a phrase matching an entry in the closed list, including an approved equivalent wording.
2. The learner's variable definition is sufficiently clear.
3. The learner's mathematical expression matches the documented incorrect pattern or a documented equivalent transformation.
4. The mismatch is not explained by an alternative valid interpretation.
5. The available evidence supports a language-to-mathematics translation error.

The presence of a phrase alone is never enough.

For example, if a question contains “甲比乙多5” but the learner writes a mathematically correct equation using a different choice of unknown, the system must not label the response E4.

---

## 4.4 E4 and Direct Evidence

A student's **variable definition plus equation is itself observable reasoning evidence**.

The learner does not need to provide an additional verbal explanation when the written modelling work already satisfies the E4 criteria.

For example:

> 设乙的数量为 \(x\)，甲的数量为 \(x-5\)。

For the question:

> 甲比乙多5。

the variable definition and equation directly demonstrate the reversed comparison.

If the pattern matches E4-01 and the mathematical checks confirm the mismatch, this is:

* Evidence level: A
* Diagnosis status: `diagnosed`
* Primary error: E4-01

No additional diagnostic question is required merely to reconfirm an already observable error.

---

## 4.5 Diagnostic Question

“题目中的‘……’具体表示原来的量、变化的量，还是变化后的量？”

The system should replace “……” with the relevant phrase.

---

## 4.6 Four-Level Scaffolding

| Level                  | Hint                                           |
| ---------------------- | ---------------------------------------------- |
| 1 — Prompt             | “先圈出题目中的关键数量关系词，想一想它表示什么。”                     |
| 2 — Targeted hint      | “这里描述的是变化量还是变化后的总量？请先用自己的话解释。”                 |
| 3 — More explicit hint | “把原来的量设为 \(x\)，分别写出原来的量、变化的量和变化后的量，再对照题目中的表述。” |
| 4 — Explanation        | “题目中的‘……’表示……，所以对应的表达式应为……。注意区分变化了多少和变化后的总量。”  |

Levels 3 and 4 may be generated dynamically from the E4 template, but the mathematical relationship must be validated before being shown to the learner.

---

## 4.7 Resolution Evidence

The learner correctly translates the relevant phrase into an equivalent mathematical expression and can explain or demonstrate the relationship through their revised equation.

---

## 4.8 E4 Extension Process

New E4 patterns must not be introduced solely because the language model proposes them.

To add a new E4 pattern:

1. Document the original Chinese phrase.
2. Document approved equivalent wordings.
3. Define the intended mathematical relationship.
4. Define one or more typical incorrect expressions.
5. Specify variable-definition assumptions.
6. Specify boundary cases and valid alternative interpretations.
7. Define how the pattern differs from E3.
8. Add positive examples.
9. Add negative examples.
10. Add ambiguous examples where `uncertain` is the correct outcome.
11. Add the pattern to the diagnostic dataset.
12. Review the pattern independently where feasible.
13. Update the taxonomy version.

New patterns should only become active in the production classifier after passing the above review process.

English or other-language patterns should be defined separately for future localization. The Chinese E4 list must not automatically be transferred to another language.

---

# 5. E5 — Unit or Magnitude Error

**State:** S2 or S4 — Modelling or Evaluation

## Definition

The learner uses incompatible units, omits a necessary unit conversion, or accepts an answer that violates an explicit contextual constraint or justified magnitude range.

### Typical examples

* Adding metres directly to centimetres without converting units.
* Reporting a time in minutes when the question requires hours.
* Accepting a negative distance where the problem explicitly requires a non-negative distance.
* Accepting a value outside the range implied by the problem's stated conditions.

### Diagnostic evidence

Evidence may include:

* Incompatible units in an equation.
* Violation of an explicit constraint.
* Incorrect unit conversion.
* A magnitude that is demonstrably incompatible with the problem conditions.

An unusual numerical result alone is insufficient evidence for E5.

### Boundary with E6

Use E5 when the central issue is unit compatibility or contextual magnitude.

Use E6 when the intended arithmetic operation is valid but the numerical computation is incorrect.

### Diagnostic question

“你得到的结果单位是什么？它符合题目给出的条件和实际数量范围吗？”

### Four-level scaffolding

| Level                  | Hint                                               |
| ---------------------- | -------------------------------------------------- |
| 1 — Prompt             | “检查一下题目中每个数量的单位。”                                  |
| 2 — Targeted hint      | “你相加或比较的几个量，单位是否一致？”                               |
| 3 — More explicit hint | “先把所有相关数量转换成同一单位，再重新检查方程或结果。”                      |
| 4 — Explanation        | “题目中的……和……分别使用……单位。统一单位后，相关数量应为……，因此原来的结果不符合题目条件。” |

### Resolution evidence

The learner obtains a unit-consistent answer satisfying the problem's explicit conditions.

---

# 6. E6 — Arithmetic Execution Error

**State:** S3 — Execution

## Definition

The learner starts from an appropriate equation and intends to perform a valid mathematical operation but makes a numerical calculation error.

### Typical examples

* Calculating \(7\times8=54\).
* Calculating \(42\div6=8\).
* Incorrectly adding or subtracting numerical values while evaluating a valid expression.

### Diagnostic evidence

Evidence may include:

* The equation before the erroneous step is appropriate.
* The intended operation is mathematically valid.
* The numerical result is incorrect.

### Boundary with E7

E6 concerns the numerical computation itself.

E7 concerns an invalid algebraic transformation that does not preserve equality.

### Diagnostic question

“你这一步进行了什么计算？能不能保留原来的等式，重新检查计算结果？”

### Four-level scaffolding

| Level                  | Hint                                      |
| ---------------------- | ----------------------------------------- |
| 1 — Prompt             | “检查一下这一步的计算。”                             |
| 2 — Targeted hint      | “先保留原来的等式，重新计算这一行的数值。”                    |
| 3 — More explicit hint | “把这一步的乘法、除法、加法或减法单独写出来，再计算一次。”            |
| 4 — Explanation        | “这一行需要计算……。正确的计算结果是……。将它代回原来的等式后，可以继续求解。” |

### Resolution evidence

The learner corrects the numerical computation while preserving the valid equation structure.

---

# 7. E7 — Algebraic Operation or Sign Error

**State:** S3 — Execution

## Definition

The learner starts from an appropriate equation but applies an invalid algebraic transformation while solving it.

### Typical examples

* From \(x+5=12\), writing \(x=12+5\).
* From \(3x=18\), writing \(x=18-3\).
* Dividing only one side of an equation by 3.
* Applying an operation to one term when it must be applied to the entire expression.

### Diagnostic evidence

Evidence may include:

* The equation before the erroneous step is valid.
* The transformation does not preserve the solution set.
* The error occurs during equation solving rather than in the original modelling equation.

### Boundary with E3 and E4

If the original equation is incorrect because it misrepresents the problem, diagnose the modelling error first.

Do not label an incorrect original modelling equation as E7 merely because the equation contains an incorrect sign or operation.

### Diagnostic question

“从上一行到这一行，你对等号两边分别做了什么操作？”

### Four-level scaffolding

| Level                  | Hint                                |
| ---------------------- | ----------------------------------- |
| 1 — Prompt             | “检查一下从上一行到这一行的变化。”                  |
| 2 — Targeted hint      | “等式两边需要保持相等。你对左右两边做了相同的操作吗？”        |
| 3 — More explicit hint | “分别写出等号左边和右边进行的运算，再检查这个变换是否保持等式成立。” |
| 4 — Explanation        | “从……到……，应在等式两边同时……。因此正确的下一步应为……。”   |

### Resolution evidence

The learner produces a valid algebraic transformation and obtains a solution satisfying the equation.

---

# 8. Verification Behaviour — Tracked Separately

Failure to verify an answer is **not** an E1–E7 mathematical error.

It is a learning behaviour recorded separately from error diagnosis.

| Behaviour               | Operational definition                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------ |
| No verification         | The learner submits an answer without checking it when verification is relevant.           |
| Prompted verification   | The learner checks after an explicit agent instruction.                                    |
| Active verification     | The learner initiates a check without an immediately preceding explicit agent instruction. |
| Successful verification | The learner correctly checks the answer against the original conditions.                   |
| Incorrect verification  | The learner attempts a check but applies the check incorrectly.                            |

An incorrect verification may provide evidence for E5, E6, or E7 depending on the actual reasoning.

Lack of verification alone must not be interpreted as evidence that the learner lacks understanding or does not trust the system.

---

# 9. Diagnostic Decision Procedure

## Step 1 — Identify the current state

Determine whether the learner is working on understanding, modelling, execution, or evaluation.

Only consider categories relevant to the current state.

---

## Step 2 — Validate mathematical content

Use deterministic checks where feasible:

* Compare numerical answers with the expected answer.
* Use SymPy to solve equations and check equivalence.
* Substitute proposed solutions into equations and original conditions.
* Check units and explicit contextual constraints.
* Accept mathematically equivalent equations.
* Accept valid alternative choices of unknown.
* Accept valid alternative solution sequences.

A mathematical check establishes whether a response satisfies a defined condition. It does not, by itself, establish why the learner made a mistake.

---

## Step 3 — Examine observable reasoning

The system should use all available learner-produced reasoning, including:

* Variable definitions.
* Equations.
* Ordered solution steps.
* Numerical calculations.
* Short explanations.
* Verification attempts.

A written variable definition plus equation is observable reasoning and may constitute Level A evidence.

The system should not require an additional verbal explanation when the written work already satisfies the operational diagnostic criteria.

---

## Step 4 — Assign evidence level

| Level                         | Evidence                                                                                                    | Typical use             |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------- |
| A — Direct reasoning evidence | Variable definition, equation, written working, or explanation directly supports a specific error category. | May support `diagnosed` |
| B — Answer-pattern evidence   | Final answer matches a predefined mutation, but reasoning is unavailable.                                   | `uncertain`             |
| C — Ambiguous evidence        | Multiple explanations remain plausible.                                                                     | `uncertain`             |
| D — Unassessable input        | Input cannot be reliably parsed or interpreted.                                                             | `insufficient_evidence` |

Evidence level describes the strength of the evidence, not the severity of the error.

---

## Step 5 — Assign diagnosis status

| Status                  | Meaning                                                        | System action                          |
| ----------------------- | -------------------------------------------------------------- | -------------------------------------- |
| `diagnosed`             | Evidence supports a specific error category                    | Provide targeted hint                  |
| `uncertain`             | Multiple explanations remain plausible or evidence is indirect | Ask a diagnostic follow-up when useful |
| `no_error_detected`     | Response satisfies available checks                            | Continue or request verification       |
| `insufficient_evidence` | Not enough information to assess the response                  | Request missing information            |

The system must not treat `uncertain` or `insufficient_evidence` as evidence that the learner made an error.

---

## Step 6 — Select the instructional action

If a category is diagnosed:

* Provide a hint associated with that category.
* Respect the current scaffolding level.
* Do not repeat a diagnostic question unnecessarily.

If the diagnosis is uncertain:

* Ask a short question that distinguishes the plausible explanations.
* Prefer collecting the missing evidence over making an unsupported error claim.

If the learner's response is correct:

* Do not invent an error.
* Continue to the next learning step or initiate verification.

---

## Step 7 — Avoid unnecessary diagnostic follow-ups

The tutor should not ask a diagnostic follow-up when the learner's existing response already provides sufficient evidence for a specific error category.

For S2:

> **Variable definition + equation = observable reasoning evidence.**

If they satisfy the E3 or E4 operational criteria, they can directly constitute Level A evidence.

For S3:

> **Line-by-line working is the default input mode.**

The ordered steps normally provide sufficient evidence to locate the first invalid transformation.

The system should request additional reasoning only when:

* The variable definition is ambiguous.
* The equation is ambiguous.
* Mathematical notation has multiple interpretations.
* A mutation match is the only evidence available.
* Multiple error categories remain plausible.
* The submitted work cannot be reliably parsed or checked.

### Evidence collection versus metacognitive follow-up

The following are **evidence-collection actions**, not metacognitive follow-ups:

* “请写出你的解题步骤。”
* “你这里的 \(x\) 表示什么？”
* “这个 `1/3x` 是指 `(1/3)×x` 还是 `1/(3×x)`？”
* Requesting a missing equation or intermediate step.

These actions do **not** count toward the per-problem metacognitive follow-up budget.

Metacognitive follow-ups are questions intended to prompt reflection on:

* Reasoning.
* Confidence.
* Verification.
* Whether the learner should rely on the AI answer.
* Whether the learner can independently justify the answer.

These remain subject to the 1–2 follow-up budget defined in `docs/V1_design.md`.

This distinction prevents diagnostic evidence collection from consuming the limited budget intended for reflection and judgement training.

---

# 10. Step-by-Step Diagnosis in S3

This section defines the preferred procedure for distinguishing E6 from E7.

## 10.1 Default input: line-by-line working

Line-by-line working is the **default input mode** for S3 Guided Mode.

The interface should initially present a multi-line solution editor rather than only a single final-answer field.

The learner is instructed:

> “请按解题顺序逐行写出你的步骤，每一行写出一个等式或计算结果。完成后再提交最终答案。”

The interface should support:

* Adding a new line.
* Editing a previous line.
* Submitting the current working.
* Optionally adding a short explanation of the operation used.
* Entering the final answer.

The learner may choose a final-answer-only option, but this should be an explicit alternative rather than the default.

The interface should explain that showing working allows the tutor to identify the specific step that needs attention.

Requesting working is an evidence-collection action and does not count toward the metacognitive follow-up budget.

---

## 10.2 Normalize and parse each line

Each submitted line should first pass through mathematical input normalization and parsing.

Normalization must preserve mathematical meaning.

The system must not silently resolve ambiguous expressions by choosing one interpretation.

The normalization rules are defined in Section 10.3.

After normalization, the system should distinguish:

* Equations.
* Expressions.
* Numerical answers.
* Unsupported or ambiguous input.

Invalid or ambiguous input should return `uncertain` or `insufficient_evidence`, rather than being automatically classified as an error.

---

## 10.3 Mathematical Input Normalization

The input parser should support common Chinese junior-secondary mathematical notation.

| Input type                  | Example             | Normalization rule                                                                            |
| --------------------------- | ------------------- | --------------------------------------------------------------------------------------------- |
| Full-width equality sign    | `2x＋5＝15`           | Convert full-width mathematical symbols to standard internal representations.                 |
| Multiplication              | `2×x`, `2·x`, `2*x` | Normalize supported multiplication symbols to a common multiplication representation.         |
| Division                    | `18÷3`, `18/3`      | Normalize unambiguous division notation.                                                      |
| Implicit multiplication     | `2x`, `3(x+1)`      | Interpret as \(2\times x\) and \(3\times(x+1)\) under the supported grammar.                  |
| Percentage                  | `20%`               | Convert to the exact rational value where appropriate while preserving original display text. |
| Decimal                     | `0.2`               | Preserve as a numeric value and normalize internally for symbolic comparison.                 |
| Explicit fraction           | `(1/3)x`            | Interpret as \((1/3)\times x\).                                                               |
| Explicit fraction           | `x/3`               | Interpret as \(x/3\).                                                                         |
| Explicit denominator        | `1/(3x)`            | Interpret as \(1/(3x)\).                                                                      |
| Ambiguous fraction          | `1/3x`              | Do not automatically choose an interpretation. Request clarification.                         |
| Chinese variable definition | `设乙为x`              | Associate \(x\) with quantity “乙” using the semantic definition.                              |

---

## 10.4 Ambiguous Expression Handling

The expression:

`1/3x`

may mean either:

$$
\frac{1}{3}x
$$

or:

$$
\frac{1}{3x}.
$$

The system must not silently select one interpretation.

Instead, display:

> “这个写法有两种可能的理解。你想表达的是 `(1/3)×x`，还是 `1/(3×x)`？请用括号写清楚。”

Until the ambiguity is resolved:

* Do not mark the response mathematically incorrect.
* Do not assign E3, E4, E6, or E7 based on the ambiguous expression.
* Record the input as requiring clarification.
* Do not count the clarification request as a metacognitive follow-up.

This rule protects the system from turning a parser ambiguity into a false learner error.

---

## 10.5 Normalization Safety Rules

1. Preserve the original learner input.
2. Store the normalized expression separately.
3. Apply only documented meaning-preserving transformations.
4. Do not use an LLM to silently rewrite ambiguous mathematical expressions before deterministic checking.
5. Do not classify parser failure as a learner mathematical error.
6. If normalization changes or loses mathematical meaning, reject the normalized representation and request clarification.

These rules are directly relevant to false-positive control.

---

## 10.6 Compare Consecutive Equations

For consecutive equations \(E_i\) and \(E_{i+1}\), check whether they have the same solution set under the applicable assumptions.

For the V1 linear-equation domain, the backend may use SymPy to:

1. Parse both equations.
2. Solve both equations symbolically.
3. Compare their solution sets.
4. Check whether the transformation preserves the original equation's solutions.

For example:

$$
2x+5=15
$$

and

$$
2x=10
$$

are equivalent.

Likewise:

$$
2x=10
$$

and

$$
x=5
$$

are equivalent.

However:

$$
x+5=12
$$

followed by:

$$
x=12+5
$$

is not equivalent.

The system must accept different but mathematically equivalent representations rather than relying on string equality.

---

## 10.7 Locate the First Invalid Transformation

The system should inspect the solution sequence in order and identify the **first transition that is demonstrably invalid**.

This is the primary candidate for the execution error.

Later errors may be consequences of the first invalid step and should not automatically be treated as independent errors.

For example:

1. `2x + 5 = 15`
2. `2x = 10`
3. `x = 10 / 2`
4. `x = 6`

The transition from line 3 to line 4 is the first invalid step.

The preceding algebraic transformation is valid.

The system should therefore investigate the numerical calculation at the final step rather than incorrectly classifying the whole solution as an algebraic modelling error.

---

## 10.8 Distinguish E6 from E7

| Observed error                                                  | Candidate diagnosis |
| --------------------------------------------------------------- | ------------------- |
| Valid algebraic operation but incorrect numerical calculation   | E6                  |
| Incorrect sign change or transposition                          | E7                  |
| Invalid division or multiplication of equation sides            | E7                  |
| Correct algebraic transformation but incorrect final arithmetic | E6                  |
| Unsupported or ambiguous transformation                         | `uncertain`         |

For example:

$$
3x=18
$$

followed by:

$$
x=18-3
$$

is an E7 candidate because the learner appears to subtract 3 instead of dividing both sides by 3.

By contrast:

$$
x=\frac{18}{3}=7
$$

contains a valid algebraic operation but an incorrect numerical result.

This is an E6 candidate.

The system should use the actual mathematical steps to classify the error rather than infer the operation solely from the final answer.

---

## 10.9 Mathematical Equivalence Limitations

SymPy equivalence checks are deterministic computational checks, not a universal proof system for every mathematical expression.

V1 should limit automatic step verification to:

* Supported linear equations.
* Documented variable assumptions.
* Supported mathematical notation.

If a line contains:

* Unsupported notation.
* Ambiguous expressions.
* An expression outside the supported grammar.
* A transformation whose equivalence cannot be reliably established.

the system should return `uncertain`.

The backend must not force E6 or E7 merely because symbolic comparison failed.

---

## 10.10 Fallback: Final Answer Only

If the learner explicitly chooses to submit only a final numerical answer:

1. Check the answer against the reference solution.
2. Check the answer against the original conditions.
3. Compare it with predefined mutations where available.
4. Record matching mutations as candidate hypotheses.
5. Do not assign `diagnosed` based on the final answer alone.
6. Request working or ask a discriminating question when necessary.

A final answer may be consistent with several different mistakes.

Even if it exactly matches a predefined E6 or E7 mutation, the mutation is only evidence of a **candidate error pattern**, not proof of the learner's actual reasoning.

---

# 11. Multiple Errors and Primary Diagnosis

A learner may make more than one error in a single solution.

V1 distinguishes primary and secondary errors.

The primary error is the earliest supported error in the learner's reasoning that is sufficient to explain the subsequent incorrect result.

### Example

1. The learner translates “比原来增加了20%” incorrectly.
2. The learner solves the resulting equation correctly.
3. The final answer is incorrect.

The primary diagnosis is E4, not E6 or E7.

If the learner subsequently makes a separate arithmetic mistake, record it as a secondary error only when independent evidence supports it.

For S3, the first invalid transition is the primary execution-error candidate.

---

# 12. Mutation Matching and Diagnostic Evidence

Mutation matching generates diagnostic hypotheses. It is not a substitute for observing learner reasoning.

## 12.1 Sources of mutation patterns

Mutation patterns may come from:

* Manually authored question-bank examples.
* Programmatically generated execution errors.
* Predefined E4 phrase-pattern errors.
* Validated modelling-error templates.

Each mutation must have a documented relationship to the original question and relevant error category.

---

## 12.2 Evidence Levels

| Level                         | Available evidence                                                                                          | Permitted status                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- | --------------------------------- |
| A — Direct reasoning evidence | Variable definition, equation, written working, or explanation directly supports a specific error category. | `diagnosed`, if checks support it |
| B — Answer-pattern evidence   | Final answer matches a predefined mutation, but reasoning is unavailable.                                   | `uncertain`                       |
| C — Ambiguous evidence        | Multiple explanations remain plausible.                                                                     | `uncertain`                       |
| D — Unassessable input        | Response cannot be reliably parsed or interpreted.                                                          | `insufficient_evidence`           |

### Important rule

A student does **not** need to provide a verbal explanation to qualify for Level A.

Written mathematical work is itself observable reasoning.

For S2, a variable definition plus equation can constitute Level A evidence.

For S3, ordered working steps can constitute Level A evidence when the first invalid transformation can be reliably identified.

---

## 12.3 Example: S2 Direct Evidence

Question:

> 甲比乙多5。

Learner:

> 设乙的数量为 \(x\)，甲的数量为 \(x-5\)。

The variable definition and equation directly show a reversed comparison.

If the pattern matches E4-01:

* Candidate: E4-01
* Evidence: A
* Status: `diagnosed`
* Action: E4-01 hint

No additional diagnostic question is necessary.

---

## 12.4 Example: S3 Direct Evidence

Learner submits:

$$
2x+5=15
$$

$$
2x=10
$$

$$
x=10/2
$$

$$
x=6
$$

The system checks each transition.

The first three lines preserve the solution set.

The final numerical calculation is incorrect.

The system may therefore classify:

* Primary error: E6
* Evidence: A
* Status: `diagnosed`

---

## 12.5 Example: Final Answer Mutation

Suppose:

* Correct answer = 12.
* Predefined E6 mutation = 14.
* Learner submits only 14.

The system records:

* Candidate category: E6
* Evidence: B
* Status: `uncertain`

It should then request the working or ask a discriminating question.

If the learner's subsequent working demonstrates the corresponding arithmetic error, the diagnosis may be upgraded to:

* Evidence: A
* Status: `diagnosed`

If the learner's working reveals E7 instead, the system must revise the diagnosis.

---

# 13. Four-Level Scaffolding and Hint Compliance

All error categories use the same four-level scaffolding framework.

| Level                  | Instructional function                                                               |
| ---------------------- | ------------------------------------------------------------------------------------ |
| 1 — Prompt             | Encourage reconsideration of relevant information.                                   |
| 2 — Targeted hint      | Direct attention to the source of difficulty without revealing the answer.           |
| 3 — More explicit hint | Break the reasoning into smaller steps or identify the next operation.               |
| 4 — Explanation        | Provide a clear explanation or partial solution when earlier hints are insufficient. |

Levels 1 and 2 are predefined category-specific prototypes.

Levels 3 and 4 may be generated by the language model using category-specific templates.

Generated hints must:

1. Match the diagnosed error category.
2. Match the current learning state.
3. Use the learner's actual question.
4. Respect the learner's variable definitions.
5. Preserve mathematical correctness.
6. Avoid introducing unsupported assumptions.
7. Respect the answer-leakage policy in `docs/V1_design.md`.
8. Remain within the backend-assigned hint level.

The language model must not independently increase the hint level.

Hint compliance is evaluated separately from diagnostic accuracy.

---

# 14. Diagnostic Dataset and Annotation Rules

The diagnostic dataset should contain both incorrect and correct learner responses.

It should include:

* Clear examples of E1–E7.
* Ambiguous examples where `uncertain` is correct.
* Correct equations written in mathematically equivalent forms.
* Correct equations using alternative valid choices of unknown.
* Correct solutions using different valid operation sequences.
* Final-answer-only cases.
* Multiple-error cases.
* E3/E4 boundary cases.
* Ambiguous notation cases.
* S3 step-localization cases.

## 14.1 Correct-response subset

Approximately **20–30% of the diagnostic test set** should contain reference-correct responses.

These should include:

* Standard correct answers.
* Mathematically equivalent equations.
* Different valid choices of unknown.
* Different valid solution sequences.
* Different but equivalent numerical representations.

This subset is necessary for measuring false-positive behaviour.

---

## 14.2 Annotation Fields

| Field                    | Description                                                       |
| ------------------------ | ----------------------------------------------------------------- |
| `case_id`                | Unique diagnostic-case identifier                                 |
| `question_id`            | Related question-bank item                                        |
| `state`                  | S1, S2, S3, or S4                                                 |
| `learner_response`       | Original response or ordered working steps                        |
| `normalized_response`    | Parser-normalized representation                                  |
| `reference_status`       | Correct, incorrect, or not assessable                             |
| `primary_error`          | E1–E7 or null                                                     |
| `secondary_errors`       | Additional independently supported categories                     |
| `evidence_level`         | A, B, C, or D                                                     |
| `diagnosis_status`       | Diagnosed, uncertain, no_error_detected, or insufficient_evidence |
| `evidence`               | Specific part of the response supporting the annotation           |
| `recommended_hint_level` | Initial hint level                                                |
| `first_invalid_step`     | S3 first invalid transition, if applicable                        |
| `review_status`          | Pending, reviewed, or adjudicated                                 |

---

## 14.3 Annotation Principles

1. Annotate observed evidence, not presumed intention.
2. Use one primary error unless multiple independent errors are clearly supported.
3. Use `uncertain` when two categories remain plausible.
4. Do not infer an error category from a final answer alone.
5. Accept mathematically equivalent equations.
6. Accept valid alternative solution methods.
7. Accept valid alternative choices of unknown.
8. Keep reference annotations independent from the tutor's diagnosis.
9. Record exact evidence supporting each annotation.
10. Treat ambiguous notation as an input issue rather than a mathematical error.
11. Do not label a correct response as incorrect because of formatting differences.
12. Do not treat agreement with the AI's diagnosis as independent evidence.

At least 20% of hand-crafted diagnostic examples should be independently reviewed by another person where feasible.

Disagreements should be documented and resolved through discussion.

The initial dataset is intended for prototype evaluation and should not be presented as establishing formal inter-rater reliability.

---

# 15. Diagnostic Evaluation Metrics

The evaluation measures both:

1. Whether the system can identify genuine errors.
2. Whether the system avoids falsely accusing learners who are correct.

---

## 15.1 Diagnostic Coverage

The proportion of eligible incorrect responses for which the system assigns a specific error category.

$$
\text{Coverage}=
\frac{\text{Incorrect responses assigned a specific category}}
{\text{All eligible incorrect responses}}
$$

Higher coverage is not automatically better.

A system that labels every response may achieve high coverage while making many unsupported diagnoses.

---

## 15.2 Conditional Diagnostic Accuracy

The proportion of specifically diagnosed responses whose primary error label matches the reference annotation.

$$
\text{Conditional Accuracy}=
\frac{\text{Correct primary diagnoses}}
{\text{Responses assigned a specific diagnosis}}
$$

Coverage and conditional accuracy should always be reported together.

---

## 15.3 False Positive Rate

The false positive rate measures how often the system incorrectly identifies a correct learner response as erroneous.

$$
\text{FPR}=
\frac{\text{Correct responses incorrectly flagged as erroneous}}
{\text{All reference-correct responses}}
$$

A reference-correct response includes:

* Mathematically equivalent equations.
* Valid alternative unknown definitions.
* Correct alternative solution paths.
* Equivalent numerical representations.

For example, if the reference solution is:

$$
x=5
$$

the system must not flag:

$$
2x=10
$$

as incorrect merely because the format differs.

The correct-response subset should represent approximately 20–30% of the diagnostic test set.

False positive rate should be reported separately from diagnostic coverage and conditional diagnostic accuracy.

---

## 15.4 Confusion Matrix

Use a confusion matrix to describe diagnostic classification behaviour.

Rows represent reference labels and columns represent system predictions.

Include:

* E1–E7.
* `uncertain`.
* `insufficient_evidence`.
* `no_error_detected`, where applicable.

The matrix should make E3/E4 confusion visible.

In particular, inspect:

1. Reference E3 predicted as E4.
2. Reference E4 predicted as E3.
3. Correct responses incorrectly assigned an error.
4. Ambiguous cases appropriately assigned `uncertain`.

Do not force uncertain cases into E1–E7 merely to produce a conventional seven-class matrix.

For the initial small dataset, the confusion matrix and underlying case counts are the primary diagnostic presentation.

Per-category precision, recall, and F1 may be included as supplementary descriptive statistics only when sample sizes permit.

---

## 15.5 S3 Step-Localization Accuracy

For line-by-line S3 submissions, evaluate whether the system identifies the first invalid transformation correctly.

Report:

* Number of cases with an independently annotated first-invalid step.
* Number of cases where the system identifies the correct step.
* Number of cases where the system returns `uncertain`.
* Number of cases where the system incorrectly identifies a valid transformation as invalid.

The step-localization result is correct only when it agrees with the reference annotation.

A correct final answer alone does not constitute evidence that the system successfully localized an error.

---

## 15.6 Hint Compliance

Evaluate whether generated hints:

* Match the diagnosed error category.
* Respect the current scaffolding level.
* Avoid revealing the complete answer prematurely.
* Do not introduce a mathematical error.
* Use the learner's actual question and variable definitions.

Hint compliance is evaluated separately from diagnostic accuracy.

---

# 16. Implementation Architecture

The taxonomy is a design specification and does not require every decision to be made by an LLM.

## 16.1 Deterministic backend responsibilities

Use Python and SymPy for:

* Mathematical input normalization.
* Supported expression parsing.
* Equation solving.
* Symbolic equivalence checks.
* Solution-set comparison.
* Numerical answer checking.
* Substitution into original conditions.
* Unit and constraint checks where explicitly encoded.
* E4 closed-list pattern matching.
* Mutation matching.
* S3 step comparison.
* First-invalid-step localization.
* State enforcement.
* Hint-level enforcement.
* Follow-up budget enforcement.
* Evaluation metric calculation.

## 16.2 Language model responsibilities

Use the language model for:

* Interpreting natural-language explanations.
* Interpreting semantic variable definitions.
* Generating diagnostic follow-up questions.
* Generating learner-friendly hints.
* Producing explanations within the defined scaffolding level.
* Handling natural-language responses that cannot be handled deterministically.

The language model may propose a candidate diagnosis.

The backend determines whether the available evidence is sufficient for that diagnosis to become confirmed.

The language model must not independently:

* Change the learning state.
* Override deterministic mathematical checks.
* Mark a correct answer as incorrect without evidence.
* Confirm an error based solely on its own generated interpretation.
* Increase the hint level beyond the backend instruction.

---

# 17. Uncertainty Handling

The system should explicitly represent uncertainty.

Relevant uncertainty triggers include:

* SymPy and the language model disagree.
* Two independent solution checks disagree.
* Original conditions are not satisfied.
* E3 and E4 remain difficult to distinguish.
* Variable definition is ambiguous.
* Mathematical notation is ambiguous.
* Multiple error categories explain the same final answer.
* Mutation matching identifies multiple possible errors.
* The language model has low classification confidence.
* The response falls outside the supported mathematical grammar.

The system should use:

```text
consistent
inconsistent
uncertain
```

for mathematical consistency checks where appropriate.

These statuses describe the evidence available to the system. They are not equivalent to proof of correctness or incorrectness.

---

# 18. Diagnostic Follow-Up Policy

The tutor should use follow-up questions selectively.

### Evidence collection

Used when the system needs missing information:

* Requesting solution steps.
* Asking what \(x\) represents.
* Clarifying ambiguous notation.
* Requesting a missing equation.

These do **not** count toward the metacognitive follow-up budget.

### Metacognitive follow-up

Used to support learner judgement:

* Asking the learner to explain why an equation represents the problem.
* Asking whether they believe an answer satisfies the original condition.
* Asking what they would verify before accepting an AI solution.
* Asking the learner to compare two possible solution approaches.

These count toward the 1–2 follow-up budget.

The distinction should be stored in the event log.

---

# 19. Design Principle

The diagnostic system should follow the principle:

> **Be precise about what can be verified, cautious about what must be inferred, and efficient about what needs to be asked.**

A strong tutoring system should not simply classify every wrong answer.

It should identify errors from observable reasoning whenever possible, use deterministic mathematical checks where appropriate, and explicitly represent uncertainty when evidence is insufficient.

In particular:

* **S2:** variable definition + equation can provide direct diagnostic evidence.
* **S3:** line-by-line working is the default and enables deterministic first-error localization.
* **Final-answer-only:** mutation matching generates a hypothesis, not a confirmed diagnosis.
* **E3/E4:** E4 uses a closed Chinese phrase-pattern list; other quantity-relationship errors default to E3.
* **Ambiguous notation:** clarify rather than guess.
* **Correct responses:** actively protect against false-positive diagnosis.
* **Hints:** scaffold reasoning rather than immediately revealing answers.

The ultimate objective is not merely to produce a correct answer.

It is to help the learner develop the ability to **understand, model, solve, evaluate, and independently verify** mathematical reasoning while maintaining appropriate reliance on AI assistance.
