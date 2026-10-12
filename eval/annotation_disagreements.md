# Annotation disagreements

Recorded before discussion; the original annotations are kept (evaluation_plan §5.1).

## 2026-10-12 — D2b, second annotator (13 cases)

Status agreement 0.92 (kappa 0.83); category agreement 0.67 (kappa 0.61); first-step agreement 0.67.

| Case | Field | First annotator | Second annotator | Resolution |
| --- | --- | --- | --- | --- |
| D2b-009 | first_invalid_step | 5 | 3 | 采纳第二标注人:改为 3。第 3 步 2x＝15 已错(25－5＝20),原标注 5 漏看了这一步。已用 --allow-relabel 记录 |
| D2b-033 | reference_status | uncertain | correct | 保留原标注(uncertain)。作答写"设x"没有说明 x 指谁,方程在 x 是小红时成立,在 x 是妈妈时不成立,存在不止一种解释 |
| D2b-037 | primary_error | E1 | E2 | 保留原标注(E1)。题目问回家时的速度,作答设的是去学校的距离,目标量不匹配。第二标注人倾向 E2(变量含义不清),经讨论仍有分歧,按主标注人 |
| D2b-054 | primary_error | None | E3 | 保留原标注(无类别)。只有最终答案,按 error_taxonomy §14.3 不凭答案推断错误类别。第二标注人标 E3,属于由答案反推 |
| D2b-063 | primary_error | E2 | E1 | 保留原标注(E2)。作答把 x 设为回家速度、方程里却用 12x 当速度项,变量角色前后不一致。第二标注人倾向 E1(求速度而非时间),经讨论仍有分歧,按主标注人 |
