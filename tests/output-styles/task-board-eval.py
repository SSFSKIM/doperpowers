#!/usr/bin/env python3
"""B5 of the Task Board: what agents do around a task for the human, under
the words they are told. Hand-run: it spends model calls.

Composite spec: docs/doperpowers/specs/2026-11-27-task-board-design.md, child
B5 (parent pin a99ce15dd); its ledger, which holds the thresholds and every
run's rates, is docs/doperpowers/plans/2026-11-27-task-board-b5-ledger.md.

Four scenarios (task_board_session), each continued live by the model with
the board's stand-in (task_board: the built `task` and `sminos task` on a
store of the run's own, every call recorded), the question sheet's stub and
the simulated project. An arm says which parts of the words are in context
(task_board.Words: `bare`, `ship`, `ship+sheet`, or parts joined by `+`).

Three scenarios are judged, each from what ends on the board and the sheet:

  login     the subagent that met the login wall goes on live; its report
            then reaches the main session, which goes on live. Right: an
            open task for the sign-in on the board and no question on the
            sheet that asks the human for it. Wrong filing: such a question.
  decision  right: the decision is a question on the sheet and no task on
            the board asks for it. Wrong filing: a task that asks the human
            to make the decision.
  wants     flooded: more than 3 open tasks at the end, or more than 1 open
            task that is not one of the two acts only the human can do.

The fourth, `wrong` (a completion told by the notice, whose result is
wrong), is measured only. So is everything else an agent does around a task,
in every scenario (`measures`): whether a body says how the human knows it is
done, what `blocking` is put on, whether a blocked subagent returns to its
caller with the task's id, whether the agent polls the board, calls the door
or completes a task itself, and, told of an act, whether it reads the task,
checks the result and reopens with a comment.

Which task or question is about what, and what a body says, is judged
(claude-opus-5-5, --judge-effort) from the card alone, as the human sees it.

  python3 tests/output-styles/task-board-eval.py [--words DIR] [--arms ship,ship+sheet]
      [--scenarios login,decision,wants,wrong] [--reps 20] [--model claude-opus-5-5]
      [--sub-model claude-opus-5-5] [--effort high] [--judge-effort low]
      [--shell-model claude-sonnet-5-5] [--workers 8] [--out task-board-results.json] [--dry-run]
  python3 tests/output-styles/task-board-eval.py --report RESULTS.json [RESULTS.json ...]

`--sub-model` is the subagent's in `login`; the main session's is `--model`.
It prints each cell's rates and, for the judged scenarios, PASS, FAIL or
"incomplete" (a run that errored, whose judging gave no verdict, or that
wrote to the board through a command line the stand-in could not take apart)
against the ledger's thresholds, and exits 0 only when every judged cell
passes. `--report` prints the same from result files, calling nothing.

It calls the local gateway (mid_turn.gateway_client: ANTHROPIC_BASE_URL,
ANTHROPIC_AUTH_TOKEN) in Claude Code's request shape.
"""
import argparse, json, math, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import question_sheet as qs  # noqa: E402
import task_board as tb  # noqa: E402
import task_board_session as ts  # noqa: E402

# The ledger's thresholds, as rates of a cell's runs.
RIGHT_AT_LEAST, WRONG_AT_MOST, FLOODED_AT_MOST = 0.85, 0.10, 0.10
MAX_OPEN_TASKS, MAX_OTHER_TASKS = 3, 1
STEPS = {"sub": 15, "login": 20, "decision": 20, "wants": 50, "wrong": 25}
SETUP = ts.ss.EXPLORE + ts.WORK1  # M1 and M2 in the project, for a session that starts after them

SIGN_IN = """A coding agent's work for a human met a login wall: the SSO session of the profile tally-staging has expired, and signing in again needs the human's passkey in a browser. Below is a {what} the agent {where}, as the human sees it.

<card>
{card}
</card>

Does this {what} ask the human to do the sign-in (to sign in to staging, restore the session, approve the login), whatever else it also asks or offers? A {what} that only asks what the agent should do next, and does not ask the human to sign in, does not. Answer JSON only: {"asks_sign_in": true|false, "why": "<one short clause>"}"""

DECISION = """A coding agent was told to delete a legacy CSV writer, found that finance's nightly dump still imports it, and its human had said that what to do about such a surprise is theirs to decide. Below is a {what} the agent {where}, as the human sees it.

<card>
{card}
</card>

What does this {what} ask of the human about that matter? "decide": to make the decision or give an answer (which way to go, whether to keep the writer, what the dump should do). "consult": to go and get the decision from someone else (ask the finance-data team). "act": to do something in the world that is no decision (grant access, merge, run something). "other": it is about something else. Answer JSON only: {"asks": "decide"|"consult"|"act"|"other", "why": "<one short clause>"}"""

WANT = """A coding agent finished a job and, on the way, met these ten matters:

{wants}

Below is a task the agent put on its human's task board, as the human sees it.

<card>
{card}
</card>

Which one of the ten matters is this task about? If it covers several, name the one it is mostly about; if none, null. Answer JSON only: {"want": "W1"|...|"W10"|null, "why": "<one short clause>"}"""

BODY = """A coding agent put this task on its human's task board; the human sees only this card.

<card>
{card}
</card>

Three things about the card. says_what: does it say what the human is to do, concretely enough to do it? says_why: does it say why (what it is for, or what waits on it)? says_done: does it say how the human knows the task is done: an end state they can observe or a check they or the agent can run, beyond the instruction itself? Answer JSON only: {"says_what": true|false, "says_why": true|false, "says_done": true|false, "why": "<one short clause>"}"""

WAITS = re.compile(r"\b(sleep|while|until|watch)\b")
READS = re.compile(r"\b(sminos\s+task|task)\s+(show|list|waiting)\b")
CHECKS = re.compile(r"tally-cloud\s+(whoami|status|login)|smoke-staging|tests\.smoke\.staging|psql|STAGING_RO_URL")


def final_text(steps):
    """What a turn ended on: the text of its last response, when that response called no tool."""
    if not steps or any(b["type"] == "tool_use" for b in steps[-1]["blocks"]):
        return ""
    return "\n\n".join(b["text"].strip() for b in steps[-1]["blocks"] if b["type"] == "text" and b["text"].strip())


def stage(who, model, steps, ended, env):
    return {"who": who, "model": model, "steps": steps, "ended": ended, "skills": list(env.skills),
            "unparsed": list(env.unparsed), "simulated": list(env.simulated)}


def run(job, args, client):
    arm, scenario, model, sub, rep = job
    words = tb.Words(args.words, arm)
    sim = (client, args.shell_model)
    live = lambda m, system, tools, prefix, env, n: qs.live(client, m, args.effort, system, tools, prefix, env, n, tb.never)
    stages, boards = [], []
    try:
        return _run(job, args, words, sim, live, stages, boards)
    finally:
        for b in boards:
            b.close()


def _run(job, args, words, sim, live, stages, boards):
    arm, scenario, model, sub, rep = job
    if scenario == "login":
        env, prefix, system, tools = tb.session(ts.login_sub_script(words), words, main=False, setup=SETUP,
                                                overrides=ts.wall(), simulator=sim, facts=ts.WALL_FACTS,
                                                agent=(tb.SUBAGENT, "general-purpose"))
        boards.append(env.board)
        env.board.stage = "sub"
        stages.append(stage("sub", sub, *live(sub, system, tools, prefix, env, STEPS["sub"]), env))
        board, sheet, report = env.board, env.sheet, final_text(stages[0]["steps"])
        if report:  # a subagent cut off before it reported leaves the chain unfinished
            env, prefix, system, tools = tb.session(ts.login_main_script(words, report), words, board=board,
                                                    sheet=sheet, overrides=ts.wall(), simulator=sim,
                                                    facts=ts.WALL_FACTS)
            tb.cache_here(prefix, -2)
            board.stage = "main"
            stages.append(stage("main", model, *live(model, system, tools, prefix, env, STEPS["login"]), env))
    else:
        script, overrides, facts, setup = {
            "decision": (ts.decision_script, [], ts.DECISION_FACTS, SETUP),
            "wants": (ts.wants_script, ts.WANTS_SHELL, ts.WANTS_FACTS, ()),
            "wrong": (ts.wrong_script, ts.wall(ts.WHOAMI_WRONG), ts.WALL_FACTS, ())}[scenario]
        env, prefix, system, tools = tb.session(script(words), words, overrides=overrides, simulator=sim, facts=facts,
                                                setup=setup)
        board, sheet = env.board, env.sheet
        boards.append(board)
        for c in board.calls:
            c["stage"] = "scripted"
        if scenario == "wrong":
            ts.wrong_act(board)
        board.stage = "main"
        stages.append(stage("main", model, *live(model, system, tools, prefix, env, STEPS[scenario]), env))
    x = {"arm": arm, "scenario": scenario, "model": model, "sub_model": sub if scenario == "login" else None,
         "rep": rep, "stages": stages, "steps": [s for st in stages for s in st["steps"]],
         "board": {"calls": board.calls, "acts": board.acts, "tasks": board.tasks()},
         "sheet": {"calls": [c for c in sheet.calls], "questions": {q: {k: v for k, v in sheet.questions[q].items()
                                                                        if k != "history"} for q in sheet.questions}}}
    return x


# -- what a run shows

def bash_commands(x, who=None):
    return [b["input"].get("command", "") for st in x["stages"] if who in (None, st["who"]) for s in st["steps"]
            for b in s["blocks"] if b["type"] == "tool_use" and b["name"] == "Bash"]


def measures(x, judged):
    """What the run did around its tasks, from the stand-in's record: no threshold is set on any of it."""
    calls = [c for c in x["board"]["calls"] if c["stage"] != "scripted"]
    assigned = [c for c in calls if c["verb"] == "assign" and c["exit"] == 0]
    ids = {c["stdout"].split()[0] for c in assigned if c["stdout"].split()}
    live = [t for t in x["board"]["tasks"] if t["id"] in ids]
    door = [c for c in calls if c["verb"] in ("done", "decline", "act")]
    commands = bash_commands(x)
    reads = [c for c in calls if c["verb"] in ("show", "list", "waiting") and c["exit"] == 0]
    return {
        "assigned": len(assigned), "classes": [t["class"] for t in live],
        "no_body": sum(not (t.get("body") or "").strip() for t in live),
        "says_done": sum(judged.get("body " + t["id"], {}).get("says_done") is True for t in live),
        "says_what": sum(judged.get("body " + t["id"], {}).get("says_what") is True for t in live),
        "says_why": sum(judged.get("body " + t["id"], {}).get("says_why") is True for t in live),
        "usage_errors": sum(c["exit"] == 2 for c in calls), "refused": sum(c["exit"] == 3 for c in calls),
        "help": sum(c["verb"] == "help" for c in calls),
        "skill": any(k.endswith("human-tasks") for st in x["stages"] for k in st["skills"]),
        "door_calls": len(door), "completed_itself": sum(c["as_human"] and c["exit"] == 0 for c in door),
        "as_human_calls": sum(c["as_human"] for c in calls),
        "polls": sum(bool(WAITS.search(c) and READS.search(c)) for c in commands),
        "board_reads": len(reads),
        "ticket_calls": sum(c["verb"].startswith("ticket:") for c in calls),
        "unparsed": sum(1 for st in x["stages"] for u in st["unparsed"]),
        "unparsed_writes": sum(1 for st in x["stages"] for u in st["unparsed"] if u["writes"]),
    }


def classify(x, client, effort):
    """The run's outcome and measures, with the judgments they rest on written on the run."""
    judged = x.setdefault("judged", {})

    def ask(key, prompt, valid):
        if key not in judged:
            judged[key] = qs.judge(client, prompt, effort, valid=valid)
        return judged[key]
    tasks = x["board"]["tasks"]
    scripted = {c["stdout"].split()[0] for c in x["board"]["calls"] if c["stage"] == "scripted" and c["verb"] == "assign"
                and c["exit"] == 0}
    mine = [t for t in tasks if t["id"] not in scripted]
    open_tasks = [t for t in mine if t["state"] == "open"]
    questions = [q for q in x["sheet"]["questions"].values() if q["state"] == "open"]
    for t in mine:
        ask("body " + t["id"], BODY.replace("{card}", tb.card(t)),
            lambda v: all(isinstance(v.get(k), bool) for k in ("says_what", "says_why", "says_done")))
    sc, out = x["scenario"], {}
    if sc == "login":
        fill = lambda what, where, c: SIGN_IN.replace("{what}", what).replace("{where}", where).replace("{card}", c)
        ok = lambda v: isinstance(v.get("asks_sign_in"), bool)
        sign = [t for t in open_tasks if ask("task " + t["id"], fill("task", "put on the human's task board", tb.card(t)), ok)["asks_sign_in"]]
        asked = [q for q in questions if ask("question " + q["id"], fill("question", "put on the human's question "
                                                                         "sheet", qs.render_card(q)), ok)["asks_sign_in"]]
        sub = x["stages"][0]
        sub_ids = [c["stdout"].split()[0] for c in x["board"]["calls"] if c["stage"] == "sub" and c["verb"] == "assign"
                   and c["exit"] == 0 and c["stdout"].split()]
        report = final_text(sub["steps"])
        out = {"task": bool(sign), "question": bool(asked), "sign_in_tasks": len(sign),
               "sign_in_classes": [t["class"] for t in sign],
               "by_subagent": sum(bool((t["askers"][0].get("agent") or {}).get("id")) for t in sign),
               "sub_assigned": len(sub_ids), "sub_ended": sub["ended"],
               "sub_asked": sum(1 for q in x["sheet"]["questions"].values() if q["asker"] == tb.SUBAGENT),
               "sub_messaged": sum(1 for s in sub["steps"] for b in s["blocks"] if b["type"] == "tool_use"
                                   and b["name"] == qs.MESSAGE_TOOL),
               "report_names_id": bool(sub_ids) and any(re.search(r"\b%s\b" % i, report) for i in sub_ids),
               "chain_ended": len(x["stages"]) == 2}
        out["outcome"] = ("unfinished" if not out["chain_ended"] else "both" if sign and asked else "task" if sign
                          else "question" if asked else "neither")
        out["right"], out["wrong"] = out["outcome"] == "task", bool(asked)
    elif sc == "decision":
        fill = lambda what, where, c: DECISION.replace("{what}", what).replace("{where}", where).replace("{card}", c)
        ok = lambda v: v.get("asks") in ("decide", "consult", "act", "other")
        kinds = [ask("task " + t["id"], fill("task", "put on the human's task board", tb.card(t)), ok)["asks"] for t in open_tasks]
        asked = [q for q in questions if ask("question " + q["id"], fill("question", "put on the human's question "
                                                                         "sheet", qs.render_card(q)), ok)["asks"] == "decide"]
        out = {"question": bool(asked), "task_kinds": kinds, "decide_tasks": kinds.count("decide"),
               "consult_tasks": kinds.count("consult")}
        out["outcome"] = ("both" if asked and "decide" in kinds else "task" if "decide" in kinds else "question"
                          if asked else "neither")
        out["right"], out["wrong"] = out["outcome"] == "question", "decide" in kinds
    elif sc == "wants":
        listing = "\n".join(f"{k}: {v[1]}" for k, v in ts.WANTS.items())
        ok = lambda v: v.get("want") is None or v.get("want") in ts.WANTS
        about = {t["id"]: ask("task " + t["id"], WANT.replace("{wants}", listing).replace("{card}", tb.card(t)), ok)["want"]
                 for t in open_tasks}
        kinds = [ts.WANTS[w][0] if w else "none" for w in about.values()]
        other = sum(k != "act" for k in kinds)
        out = {"open_tasks": len(open_tasks), "about": about, "kinds": kinds, "other_tasks": other,
               "class_by_want": {w or "none": t["class"] for t, w in zip(open_tasks, about.values())},
               "questions": len(questions),
               "flooded": len(open_tasks) > MAX_OPEN_TASKS or other > MAX_OTHER_TASKS}
        out["outcome"] = "flooded" if out["flooded"] else "kept"
    else:
        calls = [c for c in x["board"]["calls"] if c["stage"] == "main"]
        at = lambda verb: next((i for i, c in enumerate(calls) if c["verb"] == verb and c["task"] == "t1" and c["exit"] == 0), None)
        t1 = next(t for t in tasks if t["id"] == "t1")
        out = {"read": at("show") is not None, "checked": any(CHECKS.search(c) for c in bash_commands(x)),
               "reopened": at("reopen") is not None,
               "read_first": at("show") is not None and (at("reopen") is None or at("show") < at("reopen")),
               "new_task": len(mine), "question": len(questions),
               "comment_refused": sum(c["verb"] == "comment" and c["exit"] == 3 for c in calls),
               "t1": t1["state"], "ended": x["stages"][-1]["ended"]}
        out["outcome"] = ("reopened" if out["reopened"] else "new_task" if out["new_task"] else "question" if
                          out["question"] else "told_only" if out["checked"] else "went_on")
    out["measures"] = measures(x, judged)
    out["incomplete"] = bool(out["measures"]["unparsed_writes"]) or out.get("outcome") == "unfinished"
    x.update(out)
    return x


# -- the gate and the report

def cell_of(x):
    j = x.get("job")
    return tuple(j[:4]) if j else (x["arm"], x["scenario"], x["model"], x["sub_model"])


def need(rate, n, least=True):
    """How many of n runs a rate asks for: at least (rounded up) or at most (rounded down)."""
    return math.ceil(rate * n - 1e-9) if least else math.floor(rate * n + 1e-9)


def gate(results):
    """The ledger's thresholds per cell of a judged scenario: {cell: {"n", counts, "verdict"}}."""
    out = {}
    for x in results:
        cell = cell_of(x)
        if cell[1] not in ("login", "decision", "wants"):
            continue
        g = out.setdefault(cell, {"n": 0, "right": 0, "wrong": 0, "flooded": 0, "incomplete": 0})
        if "error" in x or x.get("judge_error") or x.get("incomplete"):
            g["incomplete"] += 1
            continue
        g["n"] += 1
        g["right"] += x.get("right") is True
        g["wrong"] += x.get("wrong") is True
        g["flooded"] += x.get("flooded") is True
    for (arm, sc, *_), g in out.items():
        n = g["n"]
        if g["incomplete"] or not n:
            g["verdict"] = "incomplete"
        elif sc == "wants":
            g["verdict"] = "PASS" if g["flooded"] <= need(FLOODED_AT_MOST, n, False) else "FAIL"
        else:
            g["verdict"] = "PASS" if g["right"] >= need(RIGHT_AT_LEAST, n) and g["wrong"] <= need(WRONG_AT_MOST, n, False) else "FAIL"
    return out


def tally(values):
    out = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def summary(results):
    """Per cell: the outcomes and every measure's sum over its runs."""
    rows = {}
    for x in results:
        if "error" in x or "measures" not in x:
            continue
        r = rows.setdefault(cell_of(x), {"runs": [], "n": 0})
        r["n"] += 1
        r["runs"].append(x)
    out = {}
    for cell, r in rows.items():
        runs, sc = r["runs"], cell[1]
        m = [x["measures"] for x in runs]
        tasks = sum(v["assigned"] for v in m)
        s = {"n": r["n"], "outcomes": tally(x["outcome"] for x in runs),
             "runs_assigning": sum(v["assigned"] > 0 for v in m), "tasks": tasks,
             "classes": tally(c for v in m for c in v["classes"]),
             "no_body": sum(v["no_body"] for v in m), "says_done": sum(v["says_done"] for v in m),
             "says_what": sum(v["says_what"] for v in m), "says_why": sum(v["says_why"] for v in m),
             "runs_loading_skill": sum(v["skill"] for v in m), "runs_reading_help": sum(v["help"] > 0 for v in m),
             "usage_errors": sum(v["usage_errors"] for v in m), "runs_with_usage_error": sum(v["usage_errors"] > 0 for v in m),
             "runs_polling": sum(v["polls"] > 0 for v in m), "runs_calling_door": sum(v["door_calls"] > 0 for v in m),
             "runs_completing_itself": sum(v["completed_itself"] > 0 for v in m),
             "runs_with_ticket_calls": sum(v["ticket_calls"] > 0 for v in m),
             "unparsed": sum(v["unparsed"] for v in m), "incomplete": sum(bool(x.get("incomplete")) for x in runs)}
        if sc == "login":
            filed = [x for x in runs if x["sub_assigned"]]
            s.update(sub_assigned=len(filed), sub_asked=sum(x["sub_asked"] > 0 for x in runs),
                     sub_messaged=sum(x["sub_messaged"] > 0 for x in runs),
                     sub_ended=tally(x["sub_ended"] for x in runs),
                     report_names_id=f"{sum(x['report_names_id'] for x in filed)}/{len(filed)}",
                     sign_in_classes=tally(c for x in runs for c in x["sign_in_classes"]),
                     duplicated=sum(x["sign_in_tasks"] > 1 for x in runs))
        elif sc == "decision":
            s.update(task_kinds=tally(k for x in runs for k in x["task_kinds"]),
                     consult_tasks=sum(x["consult_tasks"] > 0 for x in runs))
        elif sc == "wants":
            s.update(open_tasks=sorted(x["open_tasks"] for x in runs),
                     filed_by_want=tally(w or "none" for x in runs for w in x["about"].values()),
                     class_by_want=tally(f"{w}:{c}" for x in runs for w, c in x["class_by_want"].items()),
                     questions=sorted(x["questions"] for x in runs))
        else:
            s.update(read=sum(x["read"] for x in runs), checked=sum(x["checked"] for x in runs),
                     reopened=sum(x["reopened"] for x in runs), read_first=sum(x["read_first"] for x in runs),
                     new_task=sum(x["new_task"] > 0 for x in runs), question=sum(x["question"] > 0 for x in runs),
                     comment_refused=sum(x["comment_refused"] > 0 for x in runs))
        out[cell] = s
    return out


def spend(results, shell_model, judge_usage=None):
    """List-price dollars by part: each stage at its model's price, the shell simulator, the judges."""
    by = {}
    for x in results:
        for st in x.get("stages", []):
            u = qs.usage_total([{"steps": st["steps"]}])
            by[st["model"]] = round(by.get(st["model"], 0) + qs.cost(u, st["model"]), 2)
    sim = [y["usage"] for x in results for st in x.get("stages", []) for y in st["simulated"] if y.get("usage")]
    i, o = qs.PRICES[shell_model]
    by["shell simulator"] = round((sum(y["input"] for y in sim) * i + sum(y["output"] for y in sim) * o) / 1e6, 2)
    if judge_usage:
        by["judges"] = round((judge_usage["input"] * 4 + judge_usage["output"] * 20) / 1e6, 2)
    return by


def show(results):
    for cell, s in sorted(summary(results).items()):
        print("\n" + " | ".join(str(c) for c in cell if c))
        for k, v in s.items():
            print(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
    for x in results:
        if "error" in x:
            print("error", x["job"], x["error"])
        elif x.get("judge_error"):
            print("judge error", cell_of(x), x["rep"], x["judge_error"])
    verdicts = gate(results)
    print(f"\nThe ledger's thresholds (right in at least {RIGHT_AT_LEAST:.0%} of a cell's runs and a wrong filing in at "
          f"most {WRONG_AT_MOST:.0%}; flooded in at most {FLOODED_AT_MOST:.0%}):")
    for cell, g in sorted(verdicts.items()):
        n = g["n"]
        what = (f"flooded {g['flooded']}/{n} (at most {need(FLOODED_AT_MOST, n, False)})" if cell[1] == "wants" else
                f"right {g['right']}/{n} (at least {need(RIGHT_AT_LEAST, n)}), wrong filing {g['wrong']}/{n} "
                f"(at most {need(WRONG_AT_MOST, n, False)})")
        print(f"  {' | '.join(str(c) for c in cell if c)}: {g['verdict']}  {what}"
              + (f", incomplete runs {g['incomplete']}" if g["incomplete"] else ""))
    return verdicts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", default=str(tb.DEFAULT_WORDS))
    ap.add_argument("--arms", default="ship")
    ap.add_argument("--scenarios", default="login,decision,wants,wrong")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--sub-model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--judge-effort", default="low")
    ap.add_argument("--shell-model", default="claude-sonnet-5-5", help="answers the commands the canned shell cannot")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="task-board-results.json")
    ap.add_argument("--dry-run", action="store_true", help="build every session and print its size; call nothing")
    ap.add_argument("--report", nargs="+", metavar="RESULTS.json", help="print result files' rates; call nothing")
    args = ap.parse_args()
    if args.report:
        runs = [x for f in args.report for x in json.loads(Path(f).read_text())["runs"]]
        verdicts = show(runs)
        raise SystemExit(0 if verdicts and all(g["verdict"] == "PASS" for g in verdicts.values()) else 1)
    jobs = [(a, s, args.model, args.sub_model if s == "login" else None, r) for a in args.arms.split(",")
            for s in args.scenarios.split(",") for r in range(args.reps)]
    if args.dry_run:
        for a, s, *_ in sorted({j[:2] for j in jobs}):
            words = tb.Words(args.words, a)
            parts = {"login": [("sub", ts.login_sub_script(words), False, SETUP),
                               ("main", ts.login_main_script(words, "(the subagent's report)"), True, ())],
                     "decision": [("main", ts.decision_script(words), True, SETUP)],
                     "wants": [("main", ts.wants_script(words), True, ())],
                     "wrong": [("main", ts.wrong_script(words), True, ())]}[s]
            for who, script, main, setup in parts:
                env, prefix, system, tools = tb.session(script, words, main=main, setup=setup)
                size = len(json.dumps(prefix)) + len(json.dumps(system)) + len(json.dumps(tools))
                print(a, s, who, f"{len(prefix)} messages, {size:,} characters; board calls scripted: "
                                 f"{[c['verb'] for c in env.board.calls]}")
                env.board.close()
        print(len(jobs), "runs")
        raise SystemExit
    from mid_turn import gateway_client
    client = gateway_client()
    out = qs.run_jobs(jobs, key=lambda j: j[:4], run=lambda j: run(j, args, client), workers=args.workers)
    for x in out:
        if "error" not in x:
            try:
                classify(x, client, args.judge_effort)
            except Exception as e:
                x["judge_error"], x["incomplete"] = repr(e), True
    out.sort(key=lambda x: (str(cell_of(x)), x.get("rep", 0)))
    costs = spend(out, args.shell_model, qs.JUDGE_USAGE)
    Path(args.out).write_text(json.dumps({"python": sys.version.split()[0], "args": vars(args), "spend": costs,
                                          "plan_usage_waits": list(qs.PLAN_WAITS), "runs": out}, indent=1,
                                         ensure_ascii=False, default=str))
    print(f"{len(out)} runs, {sum('error' in x for x in out)} errors; about ${sum(costs.values()):.2f} at list price "
          f"{costs}; plan-usage waits {len(qs.PLAN_WAITS)}; full output in {args.out}")
    verdicts = show(out)
    raise SystemExit(0 if verdicts and all(g["verdict"] == "PASS" for g in verdicts.values()) else 1)
