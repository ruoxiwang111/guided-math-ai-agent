"""
core/normalizer.py — learner input → safe, SymPy-parsable text.

Implements error_taxonomy.md §10.3–10.5:
  - full-width symbols, ×·÷, −, brackets        → standard ASCII
  - implicit multiplication (2x, 3(x+1), (1/3)x) → explicit '*'
  - percent (20%)                                → (20/100)
  - leading words (解：/所以/∴ …), trailing units (元/岁/厘米 …) are stripped
  - `1/3x`, `1/2(x+1)`                           → AMBIGUOUS, never guessed
  - powers / other variables                     → UNSUPPORTED (outside V1)
  - chained equalities (2x=20-6=14)              → kept as chain_parts for the checker

It never decides whether the learner is right. It only says whether a line
can be read safely, and if so, gives the normalised text. Parser failure is
never a learner error (§10.5.5).

Public API
    normalize_line(text)  -> NormalizedLine
    split_steps(text)     -> list[str]
    normalize_steps(text_or_lines) -> list[NormalizedLine]
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from sympy import Symbol
from sympy.parsing.sympy_parser import parse_expr, standard_transformations

# ---------------------------------------------------------------------------
# Status values
# ---------------------------------------------------------------------------

OK = "ok"                      # safe to check mathematically
AMBIGUOUS = "ambiguous"        # needs clarification from the learner (§10.4)
UNSUPPORTED = "unsupported"    # outside V1 (powers, several variables …)
PARSE_ERROR = "parse_error"    # cannot be read; not a learner error
NOT_MATH = "not_math"          # words only, e.g. "答：小华10岁"
EMPTY = "empty"

EQUATION = "equation"
EXPRESSION = "expression"

CLARIFY_FRACTION_ZH = "这个写法有两种可能的理解。你想表达的是 `({num}/{den})×{nxt}`，还是 `{num}/({den}×{nxt})`？请用括号写清楚。"


@dataclass
class Issue:
    code: str
    message: str


@dataclass
class NormalizedLine:
    original: str
    normalized: str | None = None      # e.g. "2*x+5=15"; None unless status == OK
    status: str = OK
    kind: str | None = None            # "equation" | "expression" | None
    chain_parts: list[str] = field(default_factory=list)  # for a=b=c inputs
    unit: str | None = None            # stripped trailing unit, e.g. "元"
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == OK

    def issue_codes(self) -> list[str]:
        return [i.code for i in self.issues]


# ---------------------------------------------------------------------------
# Character tables
# ---------------------------------------------------------------------------

# applied after NFKC (which already maps full-width ＝＋－（）ｘ２％．，；：)
CHAR_MAP = {
    "−": "-", "–": "-", "—": "-", "﹣": "-",
    "×": "*", "✕": "*", "✖": "*", "·": "*", "⋅": "*", "•": "*", "∙": "*",
    "÷": "/", "∕": "/",
    "[": "(", "]": ")", "{": "(", "}": ")",
    "【": "(", "】": ")", "〔": "(", "〕": ")",
    "X": "x",
}

LEADING_WORDS = [
    "解方程", "解得", "解", "所以", "因此", "因为", "于是", "则", "得到", "得", "即", "故",
    "移项得", "移项", "合并得", "合并同类项得", "化简得", "去括号得", "两边同除以", "∴", "∵",
]
ANSWER_PREFIX = re.compile(r"^\s*答\s*[:：]?")
DEFINITION_PREFIX = re.compile(r"^\s*设")

UNITS = [
    "平方厘米", "平方米", "千米/小时", "米/分钟", "千米/时", "米/分", "元/千克",
    "厘米", "千米", "公里", "千克", "分钟", "小时", "毫米",
    "cm", "km", "kg", "mm", "min",
    "元", "岁", "米", "人", "台", "本", "支", "天", "分", "秒", "克", "个", "件", "颗", "只", "次",
]
UNIT_RE = re.compile(r"\s*\(?\s*(" + "|".join(map(re.escape, UNITS)) + r")\s*\)?\s*$")

POWER_RE = re.compile(r"\^|\*\*|[²³]")
ALLOWED_RE = re.compile(r"^[0-9x+\-*/().=\s]*$")

# "/ number" directly followed by x or "(":  1/3x, 1/2(x+1), 2/3 x, (x+1)/2x
AMBIGUOUS_FRACTION_RE = re.compile(r"/\s*(\d+(?:\.\d+)?)\s*(x|\()")
SIMPLE_NUMERATOR_RE = re.compile(r"(?:^|[^\w.)])(\d+(?:\.\d+)?)\s*$")

TRANSFORMS = standard_transformations  # no implicit multiplication: we insert '*' ourselves
X = Symbol("x")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_ascii(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(CHAR_MAP.get(ch, ch) for ch in text)


def _strip_leading_words(text: str) -> str:
    changed = True
    while changed:
        changed = False
        t = text.lstrip()
        for w in LEADING_WORDS:
            if t.startswith(w):
                t = t[len(w):].lstrip(" :：,，")
                changed = True
                break
        text = t
    return text


def _strip_unit(text: str) -> tuple[str, str | None]:
    """Remove one trailing unit after a number or ')', e.g. 'x=5元' → 'x=5'."""
    m = UNIT_RE.search(text)
    if m and m.start() > 0 and re.search(r"[0-9x)]\s*$", text[: m.start()]):
        return text[: m.start()], m.group(1)
    return text, None


def _percent(text: str) -> str:
    return re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", text)


def _insert_multiplication(text: str) -> str:
    s = re.sub(r"\s+", "", text)
    s = re.sub(r"(\d)(x|\()", r"\1*\2", s)   # 2x  3(
    s = re.sub(r"\)(x|\d|\()", r")*\1", s)   # )x  )2  )(
    s = re.sub(r"x(\(|x)", r"x*\1", s)       # x(  xx
    return s


def _parse_side(side: str):
    return parse_expr(side, local_dict={"x": X}, transformations=TRANSFORMS, evaluate=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_line(text: str) -> NormalizedLine:
    """Normalise one line of learner input. Never raises."""
    res = NormalizedLine(original=text)
    if text is None or not str(text).strip():
        res.status = EMPTY
        return res

    # check powers BEFORE NFKC, which would turn x² into x2
    if POWER_RE.search(str(text)):
        res.status = UNSUPPORTED
        res.issues.append(Issue("power", "出现乘方/平方，超出一元一次方程范围"))
        return res

    s = _to_ascii(str(text)).strip().rstrip("。.;")

    if ANSWER_PREFIX.match(s):
        res.status = NOT_MATH
        res.issues.append(Issue("answer_sentence", "答句，不做数学检查"))
        return res
    s = _strip_leading_words(s)

    # checked after stripping, so "解：设小华x岁" is recognised too
    if DEFINITION_PREFIX.match(s):
        res.status = NOT_MATH
        res.issues.append(Issue("variable_definition", "变量定义，由诊断模块处理"))
        return res
    s, unit = _strip_unit(s)
    res.unit = unit

    # other single-letter variable used instead of x (y, a, n …) → rename, keep a record
    letters = set(re.findall(r"[A-Za-z]", s))
    if letters and letters != {"x"}:
        others = letters - {"x"}
        if "x" not in letters and len(others) == 1:
            v = others.pop()
            s = re.sub(rf"(?<![A-Za-z]){v}(?![A-Za-z])", "x", s)
            res.issues.append(Issue("variable_renamed", f"变量 {v} 视为 x"))
        else:
            res.status = UNSUPPORTED
            res.issues.append(Issue("multiple_variables", "出现多个字母变量，超出一元一次方程范围"))
            return res

    if POWER_RE.search(s):
        res.status = UNSUPPORTED
        res.issues.append(Issue("power", "出现乘方/平方，超出一元一次方程范围"))
        return res

    if re.search(r"[一-鿿]", s):
        res.status = NOT_MATH if not re.search(r"[0-9x=]", s) else PARSE_ERROR
        res.issues.append(Issue("chinese_text", "包含无法解析的文字"))
        return res

    s = _percent(s)

    m = AMBIGUOUS_FRACTION_RE.search(s)
    if m:
        num_m = SIMPLE_NUMERATOR_RE.search(s[: m.start()])
        num = num_m.group(1) if num_m else "…"
        res.status = AMBIGUOUS
        res.issues.append(Issue(
            "ambiguous_fraction",
            CLARIFY_FRACTION_ZH.format(num=num, den=m.group(1),
                                       nxt="x" if m.group(2) == "x" else "(…)"),
        ))
        return res

    if not ALLOWED_RE.match(s):
        res.status = PARSE_ERROR
        res.issues.append(Issue("illegal_character", "包含无法识别的符号"))
        return res

    s = _insert_multiplication(s)

    if re.search(r"x\d|x\.", s):
        res.status = AMBIGUOUS
        res.issues.append(Issue("digit_after_x", "x 后面直接跟数字（如 x2），不清楚是 x×2 还是 x²，请写清楚"))
        return res

    if s.count("(") != s.count(")"):
        res.status = PARSE_ERROR
        res.issues.append(Issue("unbalanced_parentheses", "括号不配对"))
        return res

    parts = s.split("=")
    if any(p == "" for p in parts):
        res.status = PARSE_ERROR
        res.issues.append(Issue("empty_side", "等号一边为空"))
        return res

    try:
        for p in parts:
            if not _parse_side(p).free_symbols <= {X}:
                raise ValueError("unexpected symbol")
    except Exception:  # noqa: BLE001 – any parser failure is a parse_error, not a learner error
        res.status = PARSE_ERROR
        res.issues.append(Issue("syntax", "无法解析这个式子"))
        return res

    if len(parts) == 1:
        res.kind = EXPRESSION
        res.normalized = parts[0]
    else:
        res.kind = EQUATION
        if len(parts) > 2:
            res.chain_parts = parts
            res.issues.append(Issue("chained_equality", "连等式：按 首项 = 末项 检查，中间各段由检查模块逐段核对"))
            res.normalized = f"{parts[0]}={parts[-1]}"
        else:
            res.normalized = f"{parts[0]}={parts[1]}"
    return res


STEP_SPLIT_RE = re.compile(r"[\n\r;；，,。﹐﹔]+")


def split_steps(text: str) -> list[str]:
    """Split pasted working into lines (newline, ； ， 。). Lines keep their original characters."""
    return [p.strip() for p in STEP_SPLIT_RE.split(text or "") if p.strip()]


def normalize_steps(steps) -> list[NormalizedLine]:
    """Accept a string (split into lines) or a list of lines."""
    lines = split_steps(steps) if isinstance(steps, str) else list(steps)
    return [normalize_line(line) for line in lines]