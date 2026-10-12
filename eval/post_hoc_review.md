# Post-hoc review of five D2b test cases

Done on 2026-10-12, **after** the frozen run (commit `fff51a7`) and after seeing the system's output. The labels in `eval/d2b_cases.xlsx` and `eval/diagnostic_cases.json` and the stored results are **unchanged**. The headline numbers in `docs/D2B_RESULTS.md` use the original labels; this file supports a separate sensitivity analysis.

These five cases had a system output of "no error detected" while the reference said incorrect or uncertain. The post-hoc view was formed by checking the algebra against the stated principles (error_taxonomy §14.3: accept mathematically equivalent equations, accept alternative choices of unknown, do not mark a correct response incorrect because of form). It is the researcher's view after that check, not an independent annotation.

| Case | Original label | System output | Post-hoc view | Reason |
| --- | --- | --- | --- | --- |
| D2b-057 (Q15) | incorrect, E3 | no error (x = 32) | likely over-strict label (correct) | `56−x = x−4−4` simplifies to `56−x = x−8`, i.e. 2x = 64, x = 32; equivalent to the standard `56−x−4 = x+4` |
| D2b-011 (Q09) | uncertain | no error (x = 15) | keep uncertain | Equation is the standard one; the unknown is not defined ("设x"), so the grey case stays |
| D2b-082 (Q01) | incorrect, E2 | no error (x = 10) | likely over-strict label (correct) | Defines x and y, writes the second quantity as x+5 in the equation; consistent with the problem, y simply unused; equation is the standard one |
| D2b-083 (Q02) | incorrect, E2 | no error (x = 8) | likely over-strict label (correct) | Same pattern as D2b-082 (second price written as x+12) |
| D2b-085 (Q12) | incorrect, E2 | no error (x = 40) | likely over-strict label (correct) | Same pattern (daughter's age written as x/4) |

## Sensitivity (test split, n = 40)

| | Original labels | If the four "likely over-strict" cases are read as correct |
| --- | --- | --- |
| Incorrect responses | 26 | 22 |
| Diagnosed with a specific category | 10 (38.5%) | 10 / 22 = 45.5% |
| Conditional accuracy | 10 / 10 | 10 / 10 |
| Incorrect passed as "no error detected" | 6 | 2 (both E4 line-by-line solutions) |
| Modelling errors diagnosed | 1 / 9 | 1 / 5 |
| Correct responses flagged as erroneous | 0 / 11 | 0 / 15 |
| Share of reference-correct cases | 11 / 40 = 27.5% | 15 / 40 = 37.5% (above the 20–30% planned range) |

Coverage stays below the 60% target either way. The "missed errors" finding shrinks from 6 to 2 cases, so the safety statement in the main results should be read together with this table.
