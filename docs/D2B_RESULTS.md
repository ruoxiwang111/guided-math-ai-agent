# D2b results and limitations

**Status: offline technical validation on constructed data.** No learners were involved. Nothing here supports a claim about learning outcomes.

## What was run

- **Dataset D2b**: 60 learner responses to the 15 question-bank problems, each annotated by the researcher before the system was run (evaluation_plan §4.2). 49 responses were drafted by DeepSeek and then screened, edited and annotated by the researcher; 11 were written by the researcher. Split 20 dev / 40 test, stratified by error category (fixed seed).
- **System under test**: the rule-based diagnosis (normaliser, SymPy checks, matcher). It makes **no LLM calls**, so a run is deterministic.
- **Run**: test split only (40 cases), commit `fff51a7`, 2026-10-12, after the dataset was frozen. Output: `eval/results/diagnosis_d2b/20261012-221755-test/`. The dev split was not used for any reported number.
- **Second annotator**: one human annotator independently labelled 13 cases (22%), blind to the first labels. Status agreement 12/13 (kappa 0.83); error-category agreement 6/9 among cases both called incorrect (kappa 0.61); first-invalid-step agreement 2/3. Five disagreements were discussed; four first labels were kept (the first annotator decided), one was corrected (D2b-009, a dev case, step 5 → 3). With this few cases the kappa values are unstable and this is **not** a formal inter-rater reliability study.

## Results (test split, n = 40: 26 incorrect, 11 correct, 3 uncertain)

| Measure | Result | Pre-set target | Met? |
| --- | --- | --- | --- |
| Coverage (incorrect responses given a specific category) | 10 / 26 = 38.5% | ≥ 60% | No |
| Conditional accuracy (of those 10) | 10 / 10 | ≥ 75% | Yes |
| Wrong specific labels | 0 | – | – |
| Correct responses flagged as erroneous | 0 / 11 | ≤ 5% | Yes |
| First-invalid-step localisation (9 cases) | 8 right, 0 wrong, 1 uncertain | ≥ 80% | Yes |

Where the other 16 incorrect responses went: 8 returned *uncertain*, 2 *insufficient evidence*, and **6 were reported as "no error detected"**. Of the 11 correct responses, 7 were accepted and 4 returned *uncertain*. Of the 3 reference-*uncertain* responses, 2 were returned *uncertain* and 1 as "no error detected".

By layer (incorrect only): modelling 1 / 9 diagnosed, execution 8 / 13, final-answer-only 1 / 4. By origin: AI-drafted 47.4% coverage (n = 33), researcher-written 14.3% (n = 7); with 7 cases this difference should not be interpreted.

Confusion matrix (rows = reference, raw counts): E1 → uncertain 3; E2 → no error 3; E3 → uncertain 2, no error 1; E4 → E4 1, uncertain 1, no error 2; E5 → E5 1, insufficient evidence 2; E6 → E6 2, uncertain 1; E7 → E7 6.

## What this shows

1. **The system rarely labels wrongly, but it labels little.** Every specific diagnosis it made was right, and it did not accuse any correct response. It diagnoses well when the error is in the algebra (E7: 6/6; E6: 2/3) and mostly declines when the error is in how the problem was modelled.
2. **The development result overstated modelling performance.** On D2a with each case's own mutation removed, coverage was 68.8% (modelling 35.7%); on independent D2b modelling errors it was 1 / 9. D2a is a development set built from the same design as the system and should not be quoted as accuracy.
3. **There is a safety gap.** 6 of 26 incorrect responses (23%) were reported as "no error detected", which for a learner is worse than "not sure". From the case file: three E2 cases (variable defined inconsistently with the equation) had equations that still solve to the correct answer, which the equation-level check cannot see; two E4 cases were line-by-line solutions that are internally consistent with the learner's own mistranslated equation; one E3 case also gave the correct solution. These are descriptions of what the rules did, not tested explanations.
4. **Over-caution is partly by design.** Three of the four correct responses returned *uncertain* used `1/2x`- or `1/4x`-style notation, which the tutor deliberately asks the learner to clarify. The fourth had a variable definition the matcher could not map to the problem.

## Limitations

- **Small and constructed.** 40 test cases, 3–6 per error category. Report counts, not comparisons between categories. Responses are simulated, mostly drafted by a language model; real learners will write differently.
- **Annotation.** One primary annotator; a second human annotator covered 13 cases. Disagreements were resolved by the primary annotator, not by a third rater. The second annotator saw only the responses, but both are adults reading the same rubric, not a check against ground truth about learners' intentions.
- **Possible label issues, not acted on.** In five test cases the system's output matches the standard solution (D2b-057, -011, -082, -083, -085) while the reference says incorrect or uncertain. They may be genuine misses of non-equation errors, or labels worth a second look. They were **not** relabelled after seeing results; any relabelling would have to be reported as post-freeze.
- **Composition was fitted to quotas.** The set was screened and topped up until every minimum in evaluation_plan §4.2 was met, before the system was run. It is not a random sample of anything.
- **The correction after the run.** D2b-009 (dev) was corrected after the test run. It does not touch the test split.
- **Scope.** One topic; two E5 cases used two unknowns, which V1 declines by design.
- **Shared-model concern.** Because the diagnosis is rule-based, drafting by the same model family used elsewhere in the project cannot make the diagnosis rules "grade themselves". It does limit how realistic the drafted responses are, and it affects the LLM-dependent parts (structure extraction, hint wording), which D2b does not test.

## Next steps

Tune on the dev split only (variable-definition consistency check; line-by-line check against the problem's own relationships), then re-run a fresh, frozen test split. Collect real learner responses only with ethics approval, parental consent, child assent and safeguarding arrangements.
