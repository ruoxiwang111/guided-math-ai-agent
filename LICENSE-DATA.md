# Data licence

Copyright (c) 2026 Ruoxi Wang

The data in this repository is licensed under the **Creative Commons Attribution 4.0 International licence (CC BY 4.0)**: https://creativecommons.org/licenses/by/4.0/ (full legal code: https://creativecommons.org/licenses/by/4.0/legalcode).

You may share and adapt the data for any purpose, including commercially, as long as you give appropriate credit, link to the licence and indicate if you made changes.

## What this covers

- `data/question_bank.json`: the 15 question-bank problems, their mutations and Challenge AI items.
- Everything under `eval/`: the evaluation datasets (D1, D2a, D2b with annotations) and the results.

The source code is **not** covered by this licence; it is under the MIT License (see `LICENSE`).

## Notes on the data

- The D2b learner responses are constructed, not collected from real learners. 49 of the 60 were drafted by a language model (DeepSeek) and then screened, edited and annotated by the researcher; 11 were written by the researcher. The provenance of each case is recorded in `eval/d2b_generation_log.json` and in the `source` field of `eval/diagnostic_cases.json`.
- The annotations are the researcher's judgements; a second annotator labelled 13 of the 60 cases. See `docs/D2B_RESULTS.md` for what the data can and cannot support.
- No personal data about learners is included.
