"""
Run the guided tutor in the terminal and show what each module decided on every turn.

    一道题 → learner input → Normalizer → Math Checker → Diagnosis → State Manager
           → TutorAction → wording (template / cached / live) → tutor reply → learner again ↺

Run from the project root:
    python scripts/run_agent.py                       # pick a question-bank item, answer interactively
    python scripts/run_agent.py --question Q05        # a given bank item
    python scripts/run_agent.py --text "甲、乙两人……"  # any one-variable word problem (needs DEEPSEEK_API_KEY)
    python scripts/run_agent.py --demo                # replay the 长方形 example, no typing needed
    python scripts/run_agent.py --replay inputs.json  # replay a list of inputs (JSON array of input dicts)
    python scripts/run_agent.py --mode live           # wording mode: template | cached | live
    python scripts/run_agent.py --no-trace            # tutor replies only

While answering:
    S1   type the option letter (A/B/C/D)
    S2   first line "设……", second line the equation (either may be empty)
    S3   one step per line, finish with an empty line
    S4   the answer, then y/n for "checked it"
    any  "?你的问题" asks the teacher   ":reveal" shows this step (after 2 tries)   ":quit" stops

The trace is for developers and demos. Normalizer / Math Checker lines are recomputed here
with the same functions the diagnosis uses; Diagnosis / State lines are read from the
session's own event log, so they show what the agent actually decided.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import math_checker as mc  # noqa: E402
from core.llm_client import TutorVoice, default_backend  # noqa: E402
from core.normalizer import normalize_line, normalize_steps  # noqa: E402
from core.review import build_review  # noqa: E402
from core.s1_options import build_s1_item, load_targets, to_submission  # noqa: E402
from core.state_manager import INPUT_FOR_STATE, TutorSession  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

STATE_LABELS = {"S1": "理解题意", "S2": "设未知数、列方程", "S3": "解方程", "S4": "写答案并检验", "DONE": "完成"}

DEMO = [  # the 长方形 example (question bank Q05)
    {"type": "s1_choice", "chosen_id": "@target"},
    {"type": "modelling", "variable_definition": "设宽为x厘米，长为x+4厘米", "equation": ""},
    {"type": "modelling", "variable_definition": "设宽为x厘米，长为x+4厘米", "equation": "2(x+x+4)=28"},
    {"type": "reflection", "text": "周长是长加宽的和的2倍"},
    {"type": "steps", "steps": "2x+4=14\n2x=10\nx=5"},
    {"type": "reflection", "text": "每一步两边做同样的运算"},
    {"type": "final_answer", "final_answer_text": "长9厘米，宽5厘米", "verified": False},
    {"type": "reflection", "text": "2×(9+5)=28，长比宽多4，都满足"},
]


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------

def ok(flag):
    return "✓" if flag else "✗"


def trace_input(session: TutorSession, inp: dict) -> list[str]:
    """Normalizer / Math Checker view of the input (same functions the diagnosis calls)."""
    out, kind = [], inp.get("type")
    ref_eq = session.model["equation"]
    if kind == "modelling":
        eq = (inp.get("equation") or "").strip()
        if not eq:
            out.append(f"  · Normalizer    （没有方程，只检查设法：{inp.get('variable_definition') or '空'}）")
            return out
        nl = normalize_line(eq)
        if nl.ok:
            out.append(f"  {ok(True)} Normalizer    {eq}  →  {nl.normalized}")
            same = mc.equivalent(eq, ref_eq) if nl.kind == "equation" else None
            out.append(f"  {ok(bool(same))} Math Checker  与参考方程 {ref_eq} "
                       f"{'同解' if same else '不同解' if same is False else '无法比较'}")
        else:
            out.append(f"  {ok(False)} Normalizer    {eq}  →  {nl.status}：{'；'.join(i.message for i in nl.issues)}")
    elif kind == "steps":
        lines = normalize_steps(inp.get("steps") or "")
        shown = " | ".join(l.normalized or f"[{l.status}]" for l in lines)
        out.append(f"  {ok(all(l.ok for l in lines))} Normalizer    {shown}")
        r = mc.check_steps(inp.get("steps") or "", reference_equation=ref_eq)
        out.append(f"  {ok(r.status == mc.ALL_VALID)} Math Checker  {r.summary()}"
                   + (f"，最后得到 x = {r.final_value}" if r.final_value is not None else ""))
    elif kind == "final_answer":
        out.append(f"  · Math Checker  参考答案：{session.q.get('final_answer_text')}")
    return out


def trace_events(events: list[dict], state_before: str, state_after: str, action) -> list[str]:
    out = []
    for e in events:
        ev = e["event"]
        if ev == "diagnosis":
            parts = [e.get("diagnosis_status")]
            if e.get("diagnosed_error"):
                parts.append(e.get("error_subtype") or e["diagnosed_error"])
            if e.get("rule"):
                parts.append(f"rule={e['rule']}")
            if e.get("first_invalid_step"):
                parts.append(f"第{e['first_invalid_step']}行")
            if e.get("accepted_model"):
                parts.append(f"model={e['accepted_model']}")
            out.append(f"  ✓ Diagnosis     {'  '.join(p for p in parts if p)}")
        elif ev == "evidence_request":
            out.append(f"  · Evidence      请学生补充：{e['request']}（不计入追问次数）")
        elif ev == "reveal_step":
            who = "学生主动要求" if e.get("requested_by_learner") else "4 级提示后仍未解决"
            out.append(f"  · Reveal        给出这一步的参考（{who}）")
        elif ev == "metacognitive_follow_up":
            out.append(f"  · Follow-up     反思追问：{e['kind']}（计入追问次数 {e['follow_up_count']}）")
        elif ev == "learner_question":
            out.append("  · Question      学生提问：状态不变")
    move = f"{state_before} → {state_after}" if state_before != state_after else f"{state_after}（不变）"
    act = [action.type]
    if action.hint_level:
        act.append(f"提示 {action.hint_level} 级")
    if action.category:
        act.append(action.category)
    out.append(f"  ✓ State         {move}   TutorAction: {' · '.join(act)}")
    return out


def say(voice: TutorVoice, action, show_trace: bool):
    while action is not None:
        m = voice.render(action)
        src = f"   [{m.source}]" if show_trace else ""
        print(f"\n🧑‍🏫 {m.text}{src}")
        action = action.next_action


# ---------------------------------------------------------------------------
# input
# ---------------------------------------------------------------------------

def read_input(session: TutorSession, s1_item: dict):
    """Ask the learner in the terminal; returns an input dict or None to quit."""
    expected = "reflection" if session.awaiting_reflection else INPUT_FOR_STATE.get(session.state)
    if expected == "s1_choice":
        for o in s1_item["options"]:
            print(f"   {o['id']}. {o['text']}")
        print(f"   {s1_item['unsure_option']['id']}. {s1_item['unsure_option']['text']}")
    first = input(f"\n[{session.state} {STATE_LABELS.get(session.state, '')}] 你：").strip()
    if first in (":quit", ":q"):
        return None
    if first.startswith(("?", "？")):
        return {"type": "question", "text": first[1:].strip()}
    if first == ":reveal":
        return {"type": "reveal_request"}
    if expected == "reflection":
        return {"type": "reflection", "text": first}
    if expected == "s1_choice":
        return {"type": "s1_choice", "chosen_id": first.upper()}
    if expected == "modelling":
        eq = input("   方程：").strip()
        return {"type": "modelling", "variable_definition": first, "equation": eq}
    if expected == "steps":
        lines = [first]
        while True:
            ln = input("   ").strip()
            if not ln:
                break
            lines.append(ln)
        return {"type": "steps", "steps": "\n".join(l for l in lines if l)}
    if expected == "final_answer":
        checked = input("   代回原题检查过了吗？(y/n)：").strip().lower().startswith("y")
        return {"type": "final_answer", "final_answer_text": first, "verified": checked,
                "active_verification": checked}
    return None


def to_session_input(inp: dict, s1_item: dict) -> dict:
    if inp.get("type") != "s1_choice":
        return inp
    cid = inp.get("chosen_id")
    if cid == "@target":
        cid = next(o["id"] for o in s1_item["options"] if o["source"] == "target")
    return to_submission(s1_item, cid)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def load_question(args, backend):
    bank = json.loads((ROOT / "data" / "question_bank.json").read_text(encoding="utf-8"))
    questions = {q["question_id"]: q for q in bank["questions"]}
    targets = load_targets(ROOT / "data" / "s1_targets.json")
    if args.text:
        if backend is None:
            sys.exit("✗ --text 需要 DEEPSEEK_API_KEY（结构提取要调用模型）；也可以用 --question 选题库题")
        from core.structure import extract_structure, question_id_for
        print("正在分析题目结构（LLM 提取 + SymPy 核对）…")
        ex = extract_structure(args.text, backend)
        for c in ex.checks:
            print(f"  {ok(c.ok)} {c.name}" + (f"：{c.detail}" if getattr(c, 'detail', None) else ""))
        if not ex.usable:
            sys.exit(f"✗ 这道题不能进入引导（scope={ex.scope}, consistency={ex.consistency}）")
        q = ex.question
        q["question_id"] = question_id_for(args.text)
        print("\n开始之前，确认一下我有没有读对题目。我读到的已知条件：")
        for k in q.get("known_quantities", []):
            print(f"   · {k['name']}：{k['value']} {k.get('unit', '')}")
        note = input("没问题直接回车；有不对的地方请写出来：").strip()
        if note:
            print("按你的说明重新读题并核对…")
            ex = extract_structure(args.text, backend, learner_note=note)
            if not ex.usable:
                sys.exit("✗ 按你的说明重新读题后核对没有通过，这道题先不引导（你的说明可能和原题不符）")
            q = ex.question
            q["question_id"] = question_id_for(args.text)
        return q, {q["question_id"]: q["s1"]}
    qid = args.question or ("Q05" if args.demo else None)
    if qid is None:
        for q in bank["questions"]:
            print(f"  {q['question_id']}  {q['question'][:40]}…")
        qid = input("\n选一道题（如 Q05）：").strip().upper()
    if qid not in questions:
        sys.exit(f"✗ 没有 {qid}")
    return questions[qid], targets


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--question")
    ap.add_argument("--text")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--replay")
    ap.add_argument("--mode", choices=["template", "cached", "live"])
    ap.add_argument("--no-trace", action="store_true")
    args = ap.parse_args()

    backend = None if args.mode == "template" else default_backend()
    q, targets = load_question(args, backend)
    session = TutorSession(q, session_id="cli")
    voice = TutorVoice(backend, q, mode=args.mode or ("template" if backend is None else None))
    s1_item = build_s1_item(q, targets)
    trace = not args.no_trace

    print(f"\n题目：{q['question']}")
    print(f"（措辞模式：{voice.mode}{'，未连接 AI' if backend is None else ''}）")
    say(voice, session.start(), trace)

    script = DEMO if args.demo else (json.loads(Path(args.replay).read_text(encoding="utf-8")) if args.replay else None)
    step = 0
    while session.state != "DONE" or session.awaiting_reflection:
        if script is not None:
            if step >= len(script):
                break
            inp = script[step]
            step += 1
            if inp["type"] == "reflection" and not session.awaiting_reflection:
                continue                       # the scripted reflection was not asked this time
            shown = inp.get("equation") if inp["type"] == "modelling" else None
            print(f"\n[{session.state}] 你：" + {
                "s1_choice": "（选题目所求）", "modelling": f"{inp.get('variable_definition')}  {shown or ''}",
                "steps": (inp.get("steps") or "").replace("\n", " | "),
                "final_answer": inp.get("final_answer_text", ""), "reflection": inp.get("text", ""),
                "question": "？" + inp.get("text", ""), "reveal_request": ":reveal",
            }.get(inp["type"], ""))
        else:
            try:
                inp = read_input(session, s1_item)
            except EOFError:
                inp = None
            if inp is None:
                break
        try:
            sub = to_session_input(inp, s1_item)
        except ValueError as exc:
            print(f"  ✗ {exc}")
            continue

        n_events, before = len(session.events), session.state
        pre = trace_input(session, sub) if trace else []
        action = session.submit(sub)
        if trace:
            print("\n".join(pre + trace_events(session.events[n_events:], before, session.state, action)))
        say(voice, action, trace)

    if session.state == "DONE":
        print("\n✓ Session complete")
        target = (targets.get(q["question_id"]) or q.get("s1") or {}).get("target")
        print_review(build_review(session, target=target))
        if script is None:
            try:
                text = input("\n✍️ 用一句话写下这道题的关键（回车跳过）：").strip()
            except EOFError:
                text = ""
            if text:
                say(voice, session.submit({"type": "self_summary", "text": text}), trace)
        print("\nsummary:", json.dumps(session.summary(), ensure_ascii=False))


def print_review(r: dict):
    print("\n━━━━━━━━ 复盘 ━━━━━━━━")
    print("📝 解题思路回顾")
    for p in r["solution_path"]:
        print(f"   {p['label']:<6} {p['text']}")
    if r["highlights"]:
        print("👍 做得好的地方")
        for h in r["highlights"]:
            print(f"   · {h}")
    print("🧭 这次的过程")
    for j in r["journey"]:
        err = f"（出现过：{'；'.join(j['errors'])}）" if j["errors"] else ""
        print(f"   {j['label']}：{j['status']}{err}")
    print(f"📚 本题涉及：{'；'.join(r['knowledge_points'])}")
    if r["weak_points"]:
        print(f"   这次暴露的薄弱点：{'；'.join(r['weak_points'])}")
        print(f"   （{r['weak_points_note']}）")
    if r["takeaways"]:
        print("💡 记住这几点")
        for t in r["takeaways"]:
            print(f"   · {t}")
    if r["next_time"]:
        print("➡️ 下次试试")
        for t in r["next_time"]:
            print(f"   · {t}")


if __name__ == "__main__":
    main()
