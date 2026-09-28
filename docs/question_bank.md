# 一元一次方程应用题题库

**Version: V1.3 Final**

## 1. 题库目的

本题库用于 `AI 陪我学 / AI Guided Math Learning Agent` V1 的：

* 一元一次方程应用题练习；
* Guided Mode 分步解题；
* 学习者错误诊断；
* Verification 检查；
* Challenge AI「找茬挑战」；
* 后续 evaluation 数据采集。

V1 当前仅覆盖：

> **一元一次方程应用题（linear equation word problems）**

题库不用于直接证明系统具有学习效果，而用于验证：

1. 学习者能否正确识别题目中的未知量；
2. 能否建立正确数量关系；
3. 能否将自然语言关系转换为数学表达式；
4. 能否正确执行方程变形和计算；
5. 能否检查最终答案是否符合题意；
6. 能否识别正确或错误的 AI 解法。

---

# 2. 数据结构

每道题包含以下字段：

| 字段                          | 含义                      |
| --------------------------- | ----------------------- |
| `question_id`               | 题目 ID                   |
| `difficulty`                | 难度：easy / medium / hard |
| `topic`                     | 知识点                     |
| `question`                  | 题目文本                    |
| `known_quantities`          | 已知数量及单位                 |
| `unknown`                   | 未知量、符号和单位               |
| `variable_definition`       | 标准未知量定义                 |
| `relationship`              | 核心数量关系                  |
| `equation`                  | 标准方程                    |
| `answer`                    | 标准未知量答案                 |
| `final_answer_text`         | 面向学习者的最终答案              |
| `e4_patterns`               | 题目涉及的 E4 语言模式           |
| `accepted_equivalent_forms` | 可接受的等价方程                |
| `verification_conditions`   | 答案验证条件                  |
| `mutations`                 | 预定义错误变异                 |
| `challenge_ai`              | Challenge AI 正确 / 错误解法  |

---

# 3. 错误分类

本题库使用 `docs/error_taxonomy.md` V1.2：

* **E1**：理解题目目标错误
* **E2**：未知量定义不清或前后不一致
* **E3**：数量关系建立错误
* **E4**：中文语言关系 → 数学关系转换错误
* **E5**：单位 / 数量级错误
* **E6**：算术执行错误
* **E7**：代数变形、移项、符号等操作错误

其中 E4 使用封闭模式：

* E4-01：「甲比乙多5」
* E4-02：「甲比乙少5」
* E4-03：「比原来增加了20%」
* E4-04：「增加到原来的120%」
* E4-05：「增加到120」
* E4-06：「打八折」
* E4-07：「甲是乙的3倍」
* E4-08：「比原来少了三分之一」

**本 V1.3 题库不新增 E4 模式。**

对于不属于上述封闭语言模式的建模错误，使用 E3。

---

# 4. 难度分布

共 15 题：

| 难度        |     数量 |       比例 |
| --------- | -----: | -------: |
| Easy      |      5 |    33.3% |
| Medium    |      7 |    46.7% |
| Hard      |      3 |    20.0% |
| **Total** | **15** | **100%** |

由于总题数为 15，目标 30% / 50% / 20% 在整数题目下采用 **5 / 7 / 3** 分配，实际比例为约 **33% / 47% / 20%**。

---

# 5. Question Bank

## Q01

**Difficulty:** Easy

**Topic:** 年龄关系

### Question

小明今年的年龄比小华大5岁，两人的年龄之和是25岁。小明和小华今年分别多少岁？

### Known quantities

* 年龄差：5岁
* 年龄和：25岁

### Unknown

设小华今年年龄为 `x` 岁。

### Variable definition

设小华今年 `x` 岁，则小明今年 `(x + 5)` 岁。

### Relationship

* 小明 = 小华 + 5
* 小明 + 小华 = 25

### Standard equation

```text
x + (x + 5) = 25
```

### Answer

```text
x = 10
```

小华10岁，小明15岁。

### E4 pattern

* E4-01

### Accepted equivalent forms

```text
2*x + 5 = 25
```

```text
25 - x = x + 5
```

或者：

> 设小明今年 `x` 岁，则小华为 `(x - 5)` 岁。

```text
x + (x - 5) = 25
```

此时：

```text
x = 15
```

变量不同，因此属于正确解法，而不是 E4 错误。

### Verification

* `x + (x + 5) = 25`
* `(x + 5) - x = 5`
* `x > 0`

### Error mutations

**Q01-E3**

```text
x + 5 = 25
```

只把小明的年龄当成两人年龄总和，漏掉小华。

**Q01-E4-01**

```text
x + (x - 5) = 25
```

设小华为 `x`，却把小明写成 `x - 5`。

**Q01-E6**

```text
x + (x + 5) = 25

2*x + 5 = 25

2*x = 18

x = 9
```

错误发生在 `25 - 5` 的计算。

**Q01-E7**

```text
2*x + 5 = 25

2*x = 30

x = 15
```

移项时符号错误。

### Challenge AI

**Role:** incorrect

**Correct**

> 设小华年龄为x岁，那么小明是(x+5)岁。根据两人年龄和为25岁，列出x+(x+5)=25，解得x=10。所以小华10岁，小明15岁。检查：10+15=25，15−10=5，符合题意。

**Incorrect**

> 设小华年龄为x岁，那么小明就是(x−5)岁。根据两人的年龄和为25岁，可以列出x+(x−5)=25。解得x=15，所以小华15岁，小明10岁。检查可知两人的年龄差仍然是5岁，但方向与题目不符。

**Error:** E4-01

---

## Q02

**Difficulty:** Easy

**Topic:** 文具价格

### Question

小丽买了一支笔和一个笔记本，一共花了28元。笔记本比笔贵12元。笔和笔记本各多少钱？

### Known quantities

* 总价：28元
* 价格差：12元

### Unknown

设笔的价格为 `x` 元。

### Variable definition

设笔 `x` 元，则笔记本 `(x + 12)` 元。

### Relationship

笔记本 = 笔 + 12

### Standard equation

```text
x + (x + 12) = 28
```

### Answer

```text
x = 8
```

笔8元，笔记本20元。

### E4 pattern

* E4-01

### Accepted equivalent forms

```text
2*x + 12 = 28
```

或者设笔记本为 `x` 元：

```text
x + (x - 12) = 28
```

此时：

```text
x = 20
```

### Verification

* `x + (x + 12) = 28`
* `(x + 12) - x = 12`
* `x > 0`

### Error mutations

**Q02-E3**

```text
x + 12 = 28
```

只写笔记本价格等于总价，漏掉笔的价格。

**Q02-E4-01**

```text
x + (x - 12) = 28
```

把“笔记本比笔贵12元”的方向写反。

**Q02-E6**

```text
x + (x + 12) = 28

2*x + 12 = 28

2*x = 14

x = 7
```

`28 - 12` 算错。

**Q02-E7**

```text
2*x + 12 = 28

2*x = 40

x = 20
```

移项时符号错误。

### Challenge AI

**Role:** correct

**Correct**

> 设笔的价格为x元，则笔记本为(x+12)元。总价28元，所以x+(x+12)=28，2x=16，x=8。因此笔8元，笔记本20元。检查：8+20=28，20−8=12。

**Incorrect**

> 设笔的价格为x元，那么笔记本价格为(x+12)元。总价为28元，所以x+(x+12)=28。整理得2x+12=28，因此2x=40，解得x=20。所以笔20元，笔记本32元。

**Error:** E7

---

## Q03

**Difficulty:** Easy

**Topic:** 打折求原价

### Question

一件衣服打八折后售价为160元。这件衣服的原价是多少？

### Unknown

设原价为 `x` 元。

### Relationship

折后价 = 原价 × 0.8

### Standard equation

```text
0.8*x = 160
```

### Answer

```text
x = 200
```

原价200元。

### E4 pattern

* E4-06

### Accepted equivalent forms

```text
x*80/100 = 160
```

```text
x = 160/0.8
```

### Verification

* `0.8*x = 160`
* `x > 160`

### Error mutations

**Q03-E4-06**

```text
x - 0.8 = 160
```

把“打八折”理解成减去0.8元。

**Q03-E6**

```text
0.8*x = 160

x = 160/0.8

x = 180
```

除法计算错误。

**Q03-E7**

```text
0.8*x = 160

x = 160 - 0.8

x = 159.2
```

应除以0.8，却减去0.8。

**Q03-E5**

最终答案写成：

> 原价200千克。

单位错误。

### Challenge AI

**Role:** incorrect

**Correct**

> 设原价为x元。八折表示售价是原价的80%，所以0.8x=160，x=200。原价200元。检查：200×0.8=160。

**Incorrect**

> 打八折就是从原价中减去0.8元。因此可以列出x−0.8=160。解得x=160.8元。

**Error:** E4-06

---

## Q04

**Difficulty:** Easy

**Topic:** 往返路程

### Question

小明去学校时每分钟骑300米，骑了10分钟。放学后他绕路去书店再回家，也骑了10分钟。已知他往返一共骑了5500米。求小明回家时每分钟骑多少米。

### Revision note

加入“绕路”是为了避免默认去程和回程经过完全相同路线而产生矛盾。

### Unknown

设回家时每分钟骑 `x` 米。

### Relationship

去程路程 + 回程路程 = 往返总路程。

### Standard equation

```text
300*10 + 10*x = 5500
```

### Answer

```text
x = 250
```

回程速度为250米/分钟。

### Accepted equivalent forms

```text
3000 + 10*x = 5500
```

```text
10*x = 5500 - 3000
```

### Verification

* `300*10 + 10*x = 5500`
* `x > 0`

### Error mutations

**Q04-E2**

```text
3000 + x = 5500
```

`x` 定义为速度，却直接作为回程路程使用。

**Q04-E3**

```text
300*10 = 10*x
```

误以为去程和回程路程相同。

**Q04-E6**

```text
3000 + 10*x = 5500

10*x = 2000

x = 200
```

`5500 - 3000` 计算错误。

**Q04-E7**

```text
3000 + 10*x = 5500

10*x = 2500

x = 2500*10
```

应除以10，却乘以10。

**Q04-E1**

最终答案：

> 回程2500米。

求的是速度，却回答了路程。

**Q04-E5**

最终答案：

> 250米。

缺少速度单位。

### Challenge AI

**Role:** correct

**Correct**

> 去程路程是300×10=3000米，所以回程路程是5500−3000=2500米。回程用了10分钟，设速度为x米/分钟，10x=2500，x=250。回家时每分钟骑250米。

**Incorrect**

> 去程3000米，往返一共5500米，所以回程应该是2500米。因为回程用了10分钟，所以速度是2500×10=25000米/分钟。

**Error:** E7

---

## Q05

**Difficulty:** Easy

**Topic:** 长方形周长

### Question

一个长方形的长比宽多4厘米，周长是28厘米。这个长方形的长和宽分别是多少？

### Unknown

设宽为 `x` 厘米。

### Variable definition

长为 `(x + 4)` 厘米。

### Standard equation

```text
2*(x + (x + 4)) = 28
```

### Answer

```text
x = 5
```

宽5厘米，长9厘米。

### E4 pattern

* E4-01

### Accepted equivalent forms

```text
4*x + 8 = 28
```

```text
x + (x + 4) = 14
```

或者：

> 设长为x厘米，则宽为(x−4)厘米。

```text
2*(x + (x - 4)) = 28
```

此时 `x = 9`。

### Verification

* `2*(x + (x + 4)) = 28`
* `(x + 4) - x = 4`
* `x > 0`

### Error mutations

**Q05-E3**

```text
x + (x + 4) = 28
```

周长公式漏乘2。

**Q05-E4-01**

```text
2*(x + (x - 4)) = 28
```

把“长比宽多4厘米”的方向写反。

**Q05-E6**

```text
2*(x + (x + 4)) = 28

x + (x + 4) = 12

2*x = 8

x = 4
```

`28 ÷ 2` 计算错误。

**Q05-E7**

```text
2*(x + (x + 4)) = 28

4*x + 8 = 28

4*x = 36

x = 9
```

把 `+8` 移到右边时没有变号（应为 `−8`）。

### Challenge AI

**Role:** incorrect

**Correct**

> 设宽为x厘米，那么长为(x+4)厘米。根据周长公式2(长+宽)=28，得到2[x+(x+4)]=28，4x+8=28，4x=20，x=5。所以宽5厘米，长9厘米。

**Incorrect**

> 设宽为x厘米，长为(x+4)厘米。2[x+(x+4)]=28，4x+8=28，4x=36，x=9。所以宽9厘米，长13厘米。

**Error:** E7

---

## Q06

**Difficulty:** Medium

**Topic:** 人数关系

### Question

一个班男生和女生共42人，男生人数比女生少6人。这个班男生和女生各有多少人？

### Unknown

设女生人数为 `x` 人。

### Variable definition

男生人数为 `(x - 6)` 人。

### Standard equation

```text
x + (x - 6) = 42
```

### Answer

```text
x = 24
```

女生24人，男生18人。

### E4 pattern

* E4-02

### Accepted equivalent forms

```text
2*x - 6 = 42
```

或者：

> 设男生为x人，则女生为(x+6)人。

```text
x + (x + 6) = 42
```

此时 `x = 18`。

### Verification

* `x + (x - 6) = 42`
* `x - (x - 6) = 6`
* `x - 6 > 0`
* `x` 为整数

### Error mutations

**Q06-E3**

```text
x + (x - 6) = 48
```

把题目给出的总人数42误读成48。

**Q06-E4-02**

```text
x + (x + 6) = 42
```

把“男生比女生少6人”的方向写反。

**Q06-E6**

```text
x + (x - 6) = 42

2*x - 6 = 42

2*x = 50

x = 25
```

`42 + 6` 算成50。

**Q06-E7**

```text
2*x - 6 = 42

2*x = 36

x = 18
```

移项时符号错误。

### Challenge AI

**Role:** correct

**Correct**

> 设女生有x人，那么男生有(x−6)人。总人数是42，所以x+(x−6)=42，2x=48，x=24。女生24人，男生18人。检查：24+18=42，24−18=6。

**Incorrect**

> 设女生有x人，那么男生有(x−6)人。列方程x+(x−6)=42，整理得2x−6=42。移项时把6移到左边，得到2x=36，所以x=18。因此女生18人，男生12人。

**Error:** E7

---

## Q07

**Difficulty:** Medium

**Topic:** 涨价求原价

### Question

某商品涨价20%后，售价为180元。求这件商品原来的价格。

### Unknown

设原价为 `x` 元。

### Relationship

现价 = 原价 × 120%。

### Standard equation

```text
1.2*x = 180
```

### Answer

```text
x = 150
```

原价150元。

### E4 pattern

* E4-03

### Accepted equivalent forms

```text
x + 0.2*x = 180
```

```text
x*(1 + 20/100) = 180
```

### Verification

* `1.2*x = 180`
* `x < 180`
* `x > 0`

### Error mutations

**Q07-E4-03**

```text
0.2*x = 180
```

把“增加了20%”只理解为增加量，而不是涨价后的总价。

**Q07-E6**

```text
1.2*x = 180

x = 180/1.2

x = 120
```

除法计算错误。

**Q07-E7**

```text
1.2*x = 180

x = 180*1.2

x = 216
```

应除以1.2，却乘以1.2。

### Challenge AI

**Role:** incorrect

**Correct**

> 设原价为x元。增加了20%表示现价是原价的120%，所以1.2x=180，x=150。原价150元。检查：150×1.2=180。

**Incorrect**

> 涨价20%后是180元，因此涨价部分就是原价的20%。可以直接列出0.2x=180，解得x=900元。

**Error:** E4-03

---

## Q08

**Difficulty:** Medium

**Topic:** 折扣与优惠顺序

### Question

一件商品先打八折，然后再优惠10元，最后实际支付190元。求这件商品的原价。

### Unknown

设原价为 `x` 元。

### Standard equation

```text
0.8*x - 10 = 190
```

### Answer

```text
x = 250
```

原价250元。

### E4 pattern

* E4-06

### Accepted equivalent forms

```text
0.8*x = 200
```

```text
0.8*x = 190 + 10
```

### Verification

```text
0.8*x - 10 = 190
```

并且：

```text
x > 190
```

### Error mutations

**Q08-E4-06**

```text
x - 0.8 - 10 = 190
```

把“打八折”理解成减0.8元。

**Q08-E3**

```text
0.8*(x - 10) = 190
```

把优惠顺序弄反，先减10元再打八折。

**Q08-E6**

```text
0.8*x - 10 = 190

0.8*x = 210

x = 262.5
```

`190 + 10` 算错。

**Q08-E7**

```text
0.8*x = 200

x = 200*0.8

x = 160
```

应除以0.8，却乘以0.8。

### Challenge AI

**Role:** incorrect

**Correct**

> 设原价为x元。先打八折是0.8x元，再减10元，所以0.8x−10=190，0.8x=200，x=250。原价250元。检查：250×0.8=200，200−10=190。

**Incorrect**

> 设原价为x元。先优惠10元，再打八折，因此方程为0.8(x−10)=190。解得x=247.5元。

**Error:** E3

---

## Q09

**Difficulty:** Medium

**Topic:** 往返时间

### Question

小王去公司时每分钟行驶500米，用了12分钟。回家时每分钟行驶400米。已知这一天往返一共行驶了12000米。求小王回家用了多少分钟。

### Unknown

设回家用了 `x` 分钟。

### Standard equation

```text
500*12 + 400*x = 12000
```

### Answer

```text
x = 15
```

回家用了15分钟。

### Accepted equivalent forms

```text
6000 + 400*x = 12000
```

```text
400*x = 6000
```

### Verification

* `500*12 + 400*x = 12000`
* `400*x = 500*12`
* `x > 0`

### Error mutations

**Q09-E3**

```text
6000 + 400*x = 6000
```

把回程路程和总路程混淆。

**Q09-E6**

```text
6000 + 400*x = 12000

400*x = 5000

x = 12.5
```

`12000 - 6000` 计算错误。

**Q09-E7**

```text
400*x = 6000

x = 6000*400
```

应除以400，却乘以400。

**Q09-E1**

最终回答：

> 回程路程是6000米。

求的是时间，却回答了路程。

**Q09-E5**

最终回答：

> 回家用了15小时。

时间单位错误。

### Challenge AI

**Role:** correct

**Correct**

> 去程路程是500×12=6000米，往返共12000米，所以回程也是6000米。设回程用x分钟，400x=6000，x=15。回家用了15分钟。

**Incorrect**

> 去程已经是6000米，而往返总路程是12000米，所以回程也是6000米。回程速度是400米/分钟，因此需要6000×400=2400000分钟。

**Error:** E7

---

## Q10

**Difficulty:** Medium

**Topic:** 工作效率

### Question

一项工作，甲单独做每天完成全部工作的1/6，乙单独做每天完成全部工作的1/3。两人合作，需要多少天完成全部工作？

### Unknown

设合作需要 `x` 天。

### Relationship

两人每天完成：

```text
1/6 + 1/3 = 1/2
```

合作完成的总工作量为1。

### Standard equation

```text
x*(1/6 + 1/3) = 1
```

### Answer

```text
x = 2
```

需要2天。

### Accepted equivalent forms

```text
x/6 + x/3 = 1
```

```text
x/2 = 1
```

### Verification

* `x*(1/6 + 1/3) = 1`
* `x > 0`

### Error mutations

**Q10-E3**

```text
x*(1/6 - 1/3) = 1
```

错误地把两人的工作效率相减。

**Q10-E3b**

```text
x = 6 + 3
```

把两人单独完成所需天数直接相加。

**Q10-E2**

```text
x = 1/6 + 1/3
```

把x定义为合作天数，却将其作为每天完成的工作量。

**Q10-E6**

```text
x*(1/6 + 1/3) = 1

x*(1/3) = 1

x = 3
```

把 `1/6 + 1/3` 算成 `1/3`。

**Q10-E7**

```text
x/2 = 1

x = 1/2
```

应两边乘2，却除以2。

### Challenge AI

**Role:** incorrect

**Correct**

> 设合作x天完成。两人每天共完成1/6+1/3=1/2，所以x×1/2=1，x=2。需要2天。

**Incorrect**

> 甲每天完成六分之一，乙每天完成三分之一，因此两人每天完成的工作量是1/6−1/3=−1/6。所以需要−6天完成工作。

**Error:** E3

---

## Q11

**Difficulty:** Medium

**Topic:** 混合购买

### Question

小李买了2本相同的练习册和3支相同的笔，一共花了29元。一本练习册比一支笔贵2元。一本练习册和一支笔分别多少钱？

### Unknown

设一支笔的价格为 `x` 元。

### Variable definition

练习册价格为 `(x + 2)` 元。

### Standard equation

```text
2*(x + 2) + 3*x = 29
```

### Answer

```text
x = 5
```

笔5元，练习册7元。

### E4 pattern

* E4-01

### Accepted equivalent forms

```text
5*x + 4 = 29
```

或者设练习册为 `x` 元：

```text
2*x + 3*(x - 2) = 29
```

此时 `x = 7`。

### Verification

* `2*(x + 2) + 3*x = 29`
* `(x + 2) - x = 2`
* `x > 0`

### Error mutations

**Q11-E3**

```text
(x + 2) + 3*x = 29
```

漏掉2本练习册中的一本。

**Q11-E4-01**

```text
2*(x - 2) + 3*x = 29
```

把价格差方向写反。

**Q11-E6**

```text
2*(x + 2) + 3*x = 29

5*x + 4 = 29

5*x = 27

x = 27/5
```

`29 - 4` 算成27。

**Q11-E7**

```text
5*x + 4 = 29

5*x = 33

x = 33/5
```

移项时符号错误。

### Challenge AI

**Role:** incorrect

**Correct**

> 设一支笔x元，那么一本练习册(x+2)元。2(x+2)+3x=29，5x+4=29，5x=25，x=5。所以笔5元，练习册7元。检查：2×7+3×5=29。

**Incorrect**

> 设一支笔为x元，那么一本练习册为(x+2)元。列式2(x+2)+3x=29，整理得5x+4=29。因此5x=27，所以x=5.4。因此一支笔5.4元，一本练习册7.4元。

**Error:** E6

---

## Q12

**Difficulty:** Medium

**Topic:** 年龄变化

### Question

小红今年的年龄是妈妈的1/4。5年后，小红的年龄是妈妈的1/3。小红和妈妈今年分别多少岁？

### Unknown

设妈妈今年 `x` 岁。

### Variable definition

小红今年：

```text
x/4
```

岁。

### Relationship

5年后：

```text
小红 = x/4 + 5
```

妈妈：

```text
x + 5
```

并且：

```text
x/4 + 5 = (x + 5)/3
```

### Standard equation

```text
x/4 + 5 = (x + 5)/3
```

### Answer

```text
x = 40
```

妈妈40岁，小红10岁。

### Accepted equivalent forms

```text
3*x + 60 = 4*x + 20
```

```text
3*(x/4 + 5) = x + 5
```

或者设小红今年为 `x` 岁：

```text
x + 5 = (4*x + 5)/3
```

此时 `x = 10`。

### Verification

* `x/4 + 5 = (x + 5)/3`
* `x/4 > 0`

### Error mutations

**Q12-E3**

```text
x/4 = x/3
```

忘记5年后两人的年龄都增加5岁。

**Q12-E2**

```text
x/4 + 5 = x/3
```

把x定义为妈妈5年后的年龄，却按今年年龄使用。

**Q12-E6**

```text
3*x + 60 = 4*x + 20

60 - 20 = x

x = 30
```

`60 - 20` 算错。

**Q12-E6b**

最终回答：

> 小红12岁。

将 `40 ÷ 4` 计算错误。

**Q12-E7**

```text
3*x + 60 = 4*x + 20

3*x - 4*x = 60 + 20

x = -80
```

移项时符号错误。

### Challenge AI

**Role:** correct

**Correct**

> 设妈妈今年x岁，小红今年x/4岁。5年后妈妈(x+5)岁，小红(x/4+5)岁。列出x/4+5=(x+5)/3，两边乘12得3x+60=4x+20，x=40。妈妈40岁，小红10岁。检查：5年后小红15岁，妈妈45岁，15是45的1/3。

**Incorrect**

> 设妈妈今年x岁，小红今年x/4岁。5年后，两人的年龄分别是x+5和x/4+5。列出x/4+5=(x+5)/3，两边乘12得到3x+60=4x+20。移项时得到3x−4x=60+20，所以−x=80，x=−80。年龄不可能是负数，说明计算有问题。

**Error:** E7

---

## Q13

**Difficulty:** Hard

**Topic:** 分段行程

### Question

甲、乙两地相距36千米。小王先骑自行车从甲地出发，每小时骑12千米，骑了一段时间后改乘汽车，每小时行驶30千米。整个过程用了2小时。骑自行车和乘汽车分别用了多少小时？

### Unknown

设骑自行车用了 `x` 小时。

### Variable definition

乘汽车：

```text
2 - x
```

小时。

### Standard equation

```text
12*x + 30*(2 - x) = 36
```

### Answer

```text
x = 4/3
```

骑自行车 `4/3` 小时，即80分钟；乘汽车 `2/3` 小时，即40分钟。

### Accepted equivalent forms

```text
12*x + 60 - 30*x = 36
```

```text
18*x = 24
```

或者设乘汽车为 `x` 小时：

```text
12*(2 - x) + 30*x = 36
```

此时：

```text
x = 2/3
```

### Verification

* `12*x + 30*(2 - x) = 36`
* `x > 0`
* `x < 2`

### Error mutations

**Q13-E3**

```text
12*x + 30*x = 36
```

错误地认为两段时间相同。

**Q13-E2**

方程形式保持：

```text
12*x + 30*(2 - x) = 36
```

但定义为：

> 设乘汽车用了x小时。

此时方程中的x含义与表达式不一致。

**Q13-E6**

```text
12*x + 30*(2 - x) = 36

12*x + 60 - 30*x = 36

-18*x = -24

x = 3/2
```

最终除法计算错误。

**Q13-E7**

```text
12*x + 30*(2 - x) = 36

42*x - 60 = 36

x = 16/7
```

去括号及合并同类项时符号错误。

**Q13-E5**

最终答案：

> 骑自行车4/3分钟，乘汽车2/3分钟。

把小时单位错误地写成分钟。

### Challenge AI

**Role:** incorrect

**Correct**

> 设骑自行车x小时，则乘汽车(2−x)小时。12x+30(2−x)=36，12x+60−30x=36，−18x=−24，x=4/3。4/3小时=80分钟，所以骑车80分钟，乘汽车40分钟。

**Incorrect**

> 设骑自行车x小时，则乘汽车(2−x)小时。12x+30(2−x)=36，解得x=4/3。所以骑自行车用了4/3分钟，乘汽车用了2/3分钟。

**Error:** E5

---

## Q14

**Difficulty:** Hard

**Topic:** 连续百分比

### Question

某商品第一次涨价20%，第二次在涨价后的价格基础上减少10%，最后价格为216元。求商品原来的价格。

### Unknown

设原价为 `x` 元。

### Relationship

第一次涨价：

```text
1.2*x
```

第二次在涨价后的价格基础上减少10%：

```text
1.2*x*0.9
```

### Standard equation

```text
x*1.2*0.9 = 216
```

### Answer

```text
x = 200
```

原价200元。

### E4 pattern

* E4-03

这里的 E4-03 仅对应：

> “增加了20%” → 新价格为 `1.2*x`

“减少10%”本身不属于当前 V1 E4 封闭清单，因此不单独标记为新的 E4 类型。

### Accepted equivalent forms

```text
1.08*x = 216
```

```text
x*(1 + 0.2)*(1 - 0.1) = 216
```

### Verification

* `x*1.2*0.9 = 216`
* `1.2*x > 216`

### Error mutations

**Q14-E4-03**

```text
0.2*x*0.9 = 216
```

把第一次“增加20%”误写成增加量 `0.2x`。

**Q14-E3**

```text
1.2*x - 0.1*x = 216
```

第二次减少10%时错误地以原价x作为计算基准，而不是以第一次涨价后的价格作为基准。

**Q14-E6**

```text
1.08*x = 216

x = 216/1.08

x = 220
```

除法计算错误。

**Q14-E7**

```text
1.08*x = 216

x = 216*1.08

x = 233.28
```

应除以1.08，却乘以1.08。

### Challenge AI

**Role:** correct

**Correct**

> 设原价为x元。涨价20%后是1.2x元，再在此基础上降价10%，是1.2x×0.9=1.08x元。1.08x=216，x=200。原价200元。检查：200×1.2=240，240×0.9=216。

**Incorrect**

> 设商品原价为x元。涨价20%后增加的金额是0.2x，因此涨价后的价格是0.2x。再减少10%后得到0.18x。由于最终价格为216元，所以0.18x=216，解得x=1200元。

**Error:** E4-03

---

## Q15

**Difficulty:** Hard

**Topic:** 分配与转移

### Question

学校购买了一批笔记本电脑，分给甲、乙两个班。甲班拿出4台给乙班后，两个班的电脑数量相同。如果两个班原来共有56台电脑，原来甲、乙两个班分别分到多少台？

### Unknown

设乙班原来有 `x` 台。

### Variable definition

甲班原来：

```text
56 - x
```

台。

### Relationship

甲班给乙班4台后：

```text
甲班 = 56 - x - 4
```

```text
乙班 = x + 4
```

两者相等。

### Standard equation

```text
56 - x - 4 = x + 4
```

### Answer

```text
x = 24
```

乙班24台，甲班32台。

### Accepted equivalent forms

```text
52 - x = x + 4
```

```text
x + 4 = 56 - x - 4
```

也可以先推出：

> 甲班原来比乙班多8台。

然后：

```text
x + (x + 8) = 56
```

或者设甲班原来为x台：

```text
x - 4 = (56 - x) + 4
```

此时 `x = 32`。

### Verification

* `(56 - x) - 4 = x + 4`
* `x > 0`
* `56 - x > 0`
* `x` 为整数

### Error mutations

**Q15-E3**

```text
(56 - x) - 4 = x
```

只考虑甲班减少4台，忘记乙班同时增加4台。

**Q15-E3b**

```text
(56 - x) + 4 = x - 4
```

把转移方向理解反了。

**Q15-E6**

```text
56 - x - 4 = x + 4

52 - x = x + 4

46 = 2*x

x = 23
```

`52 - 4` 算成46。

**Q15-E7**

```text
52 - x = x + 4

52 + 4 = x + x

x = 28
```

移项时符号错误。

### Challenge AI

**Role:** incorrect

**Correct**

> 设乙班原来有x台，甲班有(56−x)台。甲班拿出4台后有(52−x)台，乙班有(x+4)台，两者相同：52−x=x+4，x=24。乙班24台，甲班32台。检查：32−4=28，24+4=28。

**Incorrect**

> 设乙班原来有x台，那么甲班原来有(56−x)台。甲班拿出4台后有(56−x−4)台。由于两班最后相同，可以列出56−x−4=x。解得x=26，因此乙班26台，甲班30台。甲班拿出4台后变成26台，所以两班相同。

**Error:** E3

---

# 6. Challenge AI 分布

V1 Challenge AI 共15题：

| Question | Role      | Error |
| -------- | --------- | ----- |
| Q01      | incorrect | E4-01 |
| Q02      | correct   | —     |
| Q03      | incorrect | E4-06 |
| Q04      | correct   | —     |
| Q05      | incorrect | E7    |
| Q06      | correct   | —     |
| Q07      | incorrect | E4-03 |
| Q08      | incorrect | E3    |
| Q09      | correct   | —     |
| Q10      | incorrect | E3    |
| Q11      | incorrect | E6    |
| Q12      | correct   | —     |
| Q13      | incorrect | E5    |
| Q14      | correct   | —     |
| Q15      | incorrect | E3    |

### Distribution

* Incorrect: **9**
* Correct: **6**
* Incorrect share: **60%**

符合 V1 目标：

> **9 incorrect : 6 correct**

因此学习者不能简单采用“看到AI解法就一定挑错”的策略。

---

# 7. Challenge AI 错误类型覆盖

| Error type | Challenge AI questions |
| ---------- | ---------------------- |
| E1         | —                      |
| E2         | —                      |
| E3         | Q08, Q10, Q15          |
| E4         | Q01, Q03, Q07          |
| E5         | Q13                    |
| E6         | Q11                    |
| E7         | Q05                    |

Challenge AI 中重点覆盖：

* 语言关系错误；
* 数量关系错误；
* 单位错误；
* 算术错误；
* 代数操作错误。

E1/E2 在完整题库的学生错误 mutation 中覆盖，但本轮 Challenge AI 15题不强制覆盖全部错误类型。

---

# 8. 学生错误 Mutation 覆盖

题库同时提供 modelling / execution / answer 三类错误：

### Modelling

主要覆盖：

* E2：未知量定义不一致；
* E3：数量关系错误；
* E4：语言关系转换错误。

### Execution

主要覆盖：

* E6：计算错误；
* E7：代数操作 / 符号错误。

### Answer

主要覆盖：

* E1：回答对象错误；
* E5：单位错误；
* E6：最终计算错误。

注意：

> `failure to verify` 不作为 E1–E7 中的数学错误，而作为 verification / metacognitive behavior 单独记录。

---

# 9. 等价方程原则

系统在判断学生步骤时，不要求必须得到与标准答案完全相同的字符串。

以下情况均可视为有效：

### 形式等价

例如：

```text
x + (x + 5) = 25
```

与：

```text
2*x + 5 = 25
```

数学等价。

### 左右交换

例如：

```text
2*x + 5 = 25
```

与：

```text
25 = 2*x + 5
```

数学等价。

### 不同未知量

例如：

> 设小华为x。

与：

> 设小明为x。

都可以，只要变量定义与最终解释一致。

因此：

```text
x + (x - 5) = 25
```

在“x表示小明年龄”的定义下是正确的；

在“x表示小华年龄”的定义下则是错误的 E4-01。

---

# 10. Verification 原则

每道题至少提供一个可以直接代入标准答案检查的条件。

Verification 不只是检查最终数值，还可以检查：

* 总量；
* 差值；
* 比例；
* 正数约束；
* 时间范围；
* 整数约束；
* 单位合理性。

例如 Q15：

```text
32 - 4 = 28

24 + 4 = 28
```

两边相等，因此满足“甲给乙4台后数量相同”。

---

# 11. Boundary / Edge Cases

题库设计时重点考虑以下边界：

### 正数约束

年龄、人数、价格、时间、长度等通常要求：

```text
x > 0
```

### 整数约束

人数、电脑数量等：

```text
x ∈ Z
```

### 时间范围

Q13：

```text
0 < x < 2
```

避免出现负时间或超过总时间。

### 单位一致

例如：

```text
米 ÷ 分钟 = 米/分钟
```

而不是：

```text
米
```

### 百分比基准

连续百分比题必须明确：

> 第二次变化作用于第一次变化后的价格。

因此：

```text
x*1.2*0.9
```

不能简单写成：

```text
x + 0.2*x - 0.1*x
```

---

# 12. Validation Checklist

在提交题库前，使用：

```powershell
python scripts/validate_question_bank.py
```

或 Windows 环境下：

```powershell
.venv\Scripts\python.exe scripts/validate_question_bank.py
```

脚本应验证：

1. 每道题标准方程能得到标准答案；
2. 所有 accepted equivalent forms 能得到正确答案；
3. 所有 verification conditions 在标准答案下成立；
4. modelling mutation 与标准答案不同；
5. execution mutation 在 `first_invalid_step` 前保持正确；
6. `first_invalid_step` 确实为第一个错误步骤；
7. Challenge AI correct version 与标准答案一致；
8. Challenge AI incorrect / correct 比例符合要求；
9. mutation ID 不重复。

---

# 13. V1.3 Revision Summary

本版本相较之前版本重点修正：

### Q05

修正周长展开后的 E7 mutation：

```text
4*x + 8 = 28

4*x = 36
```

明确为错误的移项操作。

### Q06

删除不可解的：

```text
x - (x - 6) = 42
```

改为可验证、可解的 modelling / execution mutation。

### Q11

总价从31元改为29元（原题无整数解）：

```text
2*(x + 2) + 3*x = 29
```

因此：

```text
5*x + 4 = 29

5*x = 25

x = 5
```

错误变异：

```text
5*x = 33
```

明确属于 E7。

### Q12

改为真实年龄关系：

```text
x/4 + 5 = (x + 5)/3
```

解得：

```text
x = 40
```

即妈妈40岁，小红10岁。

### Q03 / Q04 / Q07 / Q08 / Q09

全部改为**反向求未知量**的应用题，而不是直接计算题。

### Q14

不新增 E4-09。

“减少10%”不属于当前 V1 E4 封闭清单，因此只保留：

```text
E4-03
```

用于“增加20%”这一明确的语言转换错误。

### Q15

删除冗余的“甲比乙多8台”条件。

采用：

```text
x = 乙班原有数量
```

得到：

```text
56 - x - 4 = x + 4

x = 24
```

---

# 14. Final Status

**Question bank version:** V1.3 Final

**Questions:** 15

**Difficulty:** 5 Easy / 7 Medium / 3 Hard

**Guided Mode scope:** 一元一次方程应用题

**Challenge AI:** 9 Incorrect / 6 Correct

**Equivalent formulations:** Included

**Verification conditions:** Included

**Boundary constraints:** Included

**Student mutations:** Included

**Challenge AI solutions:** Complete correct + incorrect solutions

**SymPy validation:** Designed to pass `scripts/validate_question_bank.py`

**Status:** Ready for V1 implementation and automated validation.
