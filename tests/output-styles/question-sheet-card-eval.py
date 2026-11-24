#!/usr/bin/env python3
"""E2 of the question sheet: can a question be judged from its card alone?
Hand-run: it spends model calls.

Composite spec: docs/doperpowers/specs/2026-11-23-question-sheet-design.md in
the MAWS repository, child C1 (parent pin ad4427f93, MAWS board ticket #866),
§2.4, §10 and §12 (E2).

The human hands the agent the CSV export spec's M1 and M2 and leaves. The
agent reads the spec and the code (where the reasons behind each matter
below are), works, and then a step of its own shows a matter only the human
can decide; the model continues live, under the to-human style, with the stub
of the sheet's tool described by the arm (question_sheet.py; arms are
description files, default question-sheet/description-v1.md):

  cap   a staging smoke run: acme-logistics' 1,412,903-row report is over the
        spec's 1,000,000-row cap
  pii   a column audit: a viewer's export carries billing contacts' email
        and phone in three report types
  tz    a staging smoke run: 1,204 of 3,170 accounts have no time zone and
        every export of theirs fails
  all   the three at once (and whether they go in one call)

Histories (question_sheet_session.e2_script): short (the reading, the writer,
the trigger) and long (the reading, about forty tool rounds of work, the
trigger), so the reasons are far back when the question is written.

The project's shell is canned, and a command it cannot answer goes to
--shell-model, as in E1 (question-sheet-revise-eval.py says how).

Each question a run puts on the sheet is drawn as its card
(question_sheet.render_card: header, question, context, the references' text
as captured, options with the recommended mark) and judged from the card
alone, never the session:

  facts   which matter the card is about (every card is judged against all
          three, since a run may raise a matter its scenario did not
          trigger), and which of that matter's facts it carries (question_sheet_session.MATTERS; `essential` marks the
          ones a reader cannot judge without; `where` says where in the
          session each was shown)
  reader  a reader with only the card: could they decide (yes, partly, no),
          what they would need first, and what the card refers to that they
          cannot see

A card passes when it carries every essential fact of its matter and the
reader says yes (the median of three readers: one reader's verdict on a card
near the line flips between yes and partly). Pass rates count the cards
about the scenario's own matters; a card about another matter (the session
showed its reasons but not its numbers) is reported by the reader alone. Each card is judged a second time with the agent's own words
around the call (the text and progress notes of that response and the one
before) appended, as automatic capture (§10) would show them: the difference
is what capture would add.

--calibrate judges the hand-written bare and full cards of
question_sheet_session.CALIBRATION instead: each bare card must fail and each
full card pass, or the judges cannot tell the behaviour apart.

  python3 tests/output-styles/question-sheet-card-eval.py [NAME=DESCRIPTION.md ...]
      [--scenarios cap,pii,tz,all] [--history long,short] [--reps 5]
      [--model claude-opus-5-5] [--effort high] [--judge-effort medium] [--max-steps 20]
      [--shell-model claude-sonnet-5-5]
      [--workers 8] [--out question-sheet-card-results.json] [--calibrate] [--dry-run]

It calls the local gateway (mid_turn.gateway_client: ANTHROPIC_BASE_URL,
ANTHROPIC_AUTH_TOKEN) in Claude Code's request shape.
"""
import argparse, concurrent.futures as cf, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import question_sheet as qs  # noqa: E402
import question_sheet_session as ss  # noqa: E402

FACTS = """A coding agent put a question for a human on a sheet. The human sees only this card:

<card>
{card}
</card>

The agent's session may have raised these matters, each with the facts a reader would need to judge it:

{matters}

Which matter is the card about ("none" if none of them)? For that matter, which of its facts does the card itself state or make plain (in its text, options, context or the quoted references)? A fact counts when a reader of the card alone would learn its substance; a figure in parentheses illustrates the evidence and need not appear, unless the fact is itself a figure. A passing allusion the reader could not decode ("the cap issue", "as discussed") does not count. Answer JSON only: {"matter": "<key or none>", "facts": {"1": true|false, ...}, "why": "<one short clause>"}"""

READER = """You are the person this question was put to. You have not seen the work behind it: all you have is this card.

<card>
{card}
</card>

Could you make this decision responsibly from the card alone, without asking anything or looking anything up? Say "yes" only if you understand what is being decided, why it needs deciding, what each choice would lead to, and enough of the facts to choose between them. Answer JSON only: {"could_decide": "yes"|"partly"|"no", "missing": ["<what you would need to know first>", ...], "unresolved_references": ["<anything the card refers to that you cannot see>", ...], "your_answer": "<what you would answer, or what you would ask back>"}"""


def matters_text(keys):
    out = []
    for k in keys:
        m = ss.MATTERS[k]
        out.append(f'"{k}": {m["title"]}\n' + "\n".join(f"  {i}. {f}" for i, (f, _, _) in enumerate(m["facts"], 1)))
    return "\n\n".join(out)


READER_SAMPLES = 3
RANK = {"no": 0, "partly": 1, "yes": 2}


def judge_card(card_text, matter_keys, effort):
    """The facts judge once, the reader READER_SAMPLES times: a reader's verdict on a card near the line flips
    between yes and partly from one sample to the next, so the median is the card's."""
    facts = qs.judge(client, FACTS.replace("{card}", card_text).replace("{matters}", matters_text(matter_keys)), effort)
    readers = [qs.judge(client, READER.replace("{card}", card_text), effort) for _ in range(READER_SAMPLES)]
    verdicts = sorted((r.get("could_decide") for r in readers), key=lambda v: RANK.get(v, -1))
    reader = dict(readers[0], could_decide=verdicts[len(verdicts) // 2], samples=verdicts)
    m = ss.MATTERS.get(facts.get("matter"))
    present = {int(k): v is True for k, v in (facts.get("facts") or {}).items() if str(k).isdigit()}
    essential = all(present.get(i, False) for i, (_, ess, _) in enumerate(m["facts"], 1) if ess) if m else False
    return {"facts": facts, "reader": reader, "readers": readers, "matter": facts.get("matter"), "present": present,
            "essential": essential, "pass": essential and reader.get("could_decide") == "yes"}


def run(job, args, arms):
    arm, scenario, history, rep = job
    again = ss.trigger_output(scenario)  # the trigger's command run again answers the same
    env, prefix, system, tools = qs.session(ss.e2_script(scenario, history), arms[arm],
                                            [(r"smoke-staging|tests\.smoke|tally\.export\.audit", again)],
                                            simulator=(client, args.shell_model))
    steps, ended = qs.live(client, args.model, args.effort, system, tools, prefix, env, args.max_steps)
    cards = []
    for step_i, b in qs.sheet_calls(steps):
        call = next((c for c in env.sheet.calls if c.get("call_id") == b["id"]), None)
        for qid in (call or {}).get("added", []) + (call or {}).get("revised", []):
            q = {k: v for k, v in env.sheet.questions[qid].items() if k != "history"}
            cards.append({"id": qid, "step": step_i, "card": qs.render_card(q),
                          "notes": qs.notes_before(steps, step_i)})
    return {"arm": arm, "scenario": scenario, "history": history, "rep": rep, "ended": ended, "steps": steps,
            "calls": env.sheet.calls, "cards": cards, "simulated": env.simulated,
            "asking_calls": sum(1 for c in env.sheet.calls if c.get("added"))}


def judge_run(x, effort):
    keys = ss.E2_TRIGGERS[x["scenario"]]["matters"]
    for c in x["cards"]:
        c["alone"] = judge_card(c["card"], list(ss.MATTERS), effort)
        captured = c["card"] + ("\n\n**The agent's notes when it asked** (captured automatically)\n\n" + c["notes"]
                                if c["notes"] else "")
        c["with_capture"] = judge_card(captured, list(ss.MATTERS), effort) if c["notes"] else c["alone"]
    x["matters_asked"] = sorted({c["alone"]["matter"] for c in x["cards"]} & set(keys))
    return x


def summary(results):
    rows = {}
    for x in results:
        if "error" in x:
            continue
        r = rows.setdefault((x["arm"], x["scenario"], x["history"]), {
            "runs": 0, "runs_asking": 0, "cards": 0, "matter_cards": 0, "pass": 0, "essential": 0, "reader_yes": 0,
            "pass_with_capture": 0, "asking_calls": 0, "matters_unasked": 0, "facts_by_where": {},
            "other_cards": 0, "other_reader_yes": 0})
        keys = ss.E2_TRIGGERS[x["scenario"]]["matters"]
        r["runs"] += 1
        r["runs_asking"] += bool(x["cards"])
        r["asking_calls"] += x["asking_calls"]
        r["matters_unasked"] += len(set(keys) - set(x.get("matters_asked", [])))
        for c in x["cards"]:
            r["cards"] += 1
            a = c.get("alone") or {}
            if a.get("matter") not in keys:  # a matter this session never showed the numbers of: the reader only
                r["other_cards"] += 1
                r["other_reader_yes"] += (a.get("reader") or {}).get("could_decide") == "yes"
                continue
            r["matter_cards"] += 1
            r["pass"] += a["pass"]
            r["essential"] += a["essential"]
            r["reader_yes"] += a["reader"].get("could_decide") == "yes"
            r["pass_with_capture"] += c["with_capture"]["pass"]
            for i, (_, _, where) in enumerate(ss.MATTERS[a["matter"]]["facts"], 1):
                w = r["facts_by_where"].setdefault(where.split(":")[0], [0, 0])
                w[0] += a["present"].get(i, False)
                w[1] += 1
    return rows


def calibrate(effort):
    out = {}
    jobs = [(k, kind) for k in ss.CALIBRATION for kind in ("bare", "full")]
    with cf.ThreadPoolExecutor(6) as pool:
        verdicts = pool.map(lambda j: judge_card(qs.render_card(ss.CALIBRATION[j[0]][j[1]]), list(ss.MATTERS), effort), jobs)
        for (k, kind), v in zip(jobs, verdicts):
            out[f"{k} {kind}"] = v
            ok = v["pass"] == (kind == "full")
            print(f"{'PASS' if ok else 'FAIL'}  {k} {kind}: pass={v['pass']} essential={v['essential']} "
                  f"reader={v['reader'].get('could_decide')} facts={v['present']}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="*", help="NAME=PATH to a description file (default v1)")
    ap.add_argument("--scenarios", default=",".join(ss.E2_TRIGGERS))
    ap.add_argument("--history", default="long")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--judge-effort", default="medium")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--shell-model", default="claude-sonnet-5-5", help="answers the commands the canned shell cannot")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="question-sheet-card-results.json")
    ap.add_argument("--calibrate", action="store_true", help="judge the calibration cards only")
    ap.add_argument("--dry-run", action="store_true", help="build every session and print its size; call nothing")
    args = ap.parse_args()
    arms = dict(a.split("=", 1) for a in args.arms) or {"v1": str(qs.DEFAULT_ARM)}
    jobs = [(a, s, h, r) for a in arms for s in args.scenarios.split(",") for h in args.history.split(",")
            for r in range(args.reps)]
    if args.dry_run:
        for a, s, h, _ in sorted({j[:3] + (0,) for j in jobs}):
            env, prefix, system, tools = qs.session(ss.e2_script(s, h), arms[a])
            print(a, s, h, f"{len(prefix)} messages, {len(json.dumps(prefix)):,} characters")
        for k, c in ss.CALIBRATION.items():
            print(f"\n== calibration {k}, full\n" + qs.render_card(c["full"]))
        print(len(jobs), "runs")
        raise SystemExit
    from mid_turn import gateway_client
    client = gateway_client()
    if args.calibrate:
        v = calibrate(args.judge_effort)
        Path(args.out).write_text(json.dumps({"calibration": v}, indent=1, ensure_ascii=False))
        raise SystemExit(0 if all(x["pass"] == k.endswith("full") for k, x in v.items()) else 1)
    out = qs.run_jobs(jobs, key=lambda j: j[:3], run=lambda j: run(j, args, arms), workers=args.workers)
    with cf.ThreadPoolExecutor(args.workers) as pool:
        def safe(x):
            try:
                return judge_run(x, args.judge_effort)
            except Exception as e:
                x["judge_error"] = repr(e)
                return x
        out = [x if "error" in x else y for x, y in zip(out, pool.map(lambda x: x if "error" in x else safe(x), out))]
    out.sort(key=lambda x: (x.get("arm", ""), x.get("scenario", ""), x.get("history", ""), x.get("rep", 0)))
    usage = qs.usage_total(out)
    Path(args.out).write_text(json.dumps({"python": sys.version.split()[0], "args": vars(args), "usage": usage,
                                          "runs": out}, indent=1, ensure_ascii=False, default=str))
    print(f"{len(out)} runs, {sum('error' in x for x in out)} errors, "
          f"{sum('judge_error' in x for x in out)} judge errors; usage {usage}, about ${qs.cost(usage, args.model)} "
          f"at list price (judges not counted); full output in {args.out}")
    for key, r in sorted(summary(out).items()):
        print(*key, json.dumps(r))
    for x in out:
        if "error" in x:
            print("error", x["job"], x["error"])
            continue
        for c in x["cards"]:
            a, w = c.get("alone", {}), c.get("with_capture", {})
            print(x["arm"], x["scenario"], x["history"], x["rep"], c["id"], "matter", a.get("matter"),
                  "pass", a.get("pass"), "reader", (a.get("reader") or {}).get("could_decide"),
                  "facts", a.get("present"), "| with capture: pass", w.get("pass"))
        if not x["cards"]:
            print(x["arm"], x["scenario"], x["history"], x["rep"], "no question asked; ended", x["ended"])
