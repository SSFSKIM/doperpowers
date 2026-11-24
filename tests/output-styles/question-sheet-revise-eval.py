#!/usr/bin/env python3
"""E1 of the question sheet: when an open question it asked changes, does the
agent revise it rather than ask a second one? Hand-run: it spends model calls.

Composite spec: docs/doperpowers/specs/2026-11-23-question-sheet-design.md in
the MAWS repository, child C1 (parent pin ad4427f93, MAWS board ticket #866),
§2.4 and §12 (E1).

The human hands the agent the CSV export spec's M1 and M2 and leaves. The
agent reads the code, puts three questions on its sheet in one call (q1 the
row cap, recommending splitting big exports into several files; q2 billing
contacts' email and phone; q3 accounts with no time zone), and works. Then
the scenario's trigger arrives and the model continues the session live,
under the to-human style, with the stub of the sheet's tool described by the
arm (question_sheet.py; arms are description files, default
question-sheet/description-v1.md):

  option_gone  reading the downloads code: a job owns exactly one file, so
               q1's recommended option (several files) cannot be built
               without unscheduled work; q1 should be revised
  premise      a rebase brings a migration that makes the contacts' email and
               phone admin-only and leaves open whether finance reads them;
               q2's premise is gone and its question changes; revise
  subagent     a subagent the agent sent off reports that finance's loader
               accepts only UTC with a literal Z: q3 (no time zone) becomes a
               question about every account's format; revise
  distinct     the control: the legacy writer M2 deletes feeds finance's
               nightly dump, a new matter; a new question is right, and
               folding it into q1-q3 is the failure

Histories (question_sheet_session.e1_script): short (the ask, then the
trigger); far (the ask, then about forty tool rounds of work: M1 and M2,
library source read while debugging, a review and its fixes, the full suite,
the branch's diff; then the trigger); near (the same steps with the ask moved
to just before the trigger). far and near differ only in how far back the
ask is, so far minus near is what having moved on costs.

A run ends at the turn's end, a final message, --max-steps responses, or one
response after its first sheet call. Its outcome, from the stub's record:

  revised                 the target revised (an `ask` entry with its id)
  replaced                the target withdrawn and a question for the same
                          decision added: one question stands, the human's
                          draft and the "updated" mark are lost
  withdrawn               the target withdrawn and nothing added for it
  duplicated              a question for the same decision added while the
                          target stays open: the observed problem
  revised+duplicated      both
  untouched               the target left as it was (cut_off when the run ran
                          out of steps first)
  distinct: added, repurposed (an open question revised into the new matter),
            no_ask

Whether an added question asks for the same decision as the target, and
whether a revision still asks for the decision it replaced, is judged
(claude-opus-5-5, --judge-effort) from the two cards alone.

  python3 tests/output-styles/question-sheet-revise-eval.py [NAME=DESCRIPTION.md ...]
      [--scenarios option_gone,premise,subagent,distinct] [--history far,near,short] [--reps 5]
      [--model claude-opus-5-5] [--effort high] [--judge-effort low] [--max-steps 8]
      [--workers 8] [--out question-sheet-revise-results.json] [--dry-run]

It calls the local gateway (mid_turn.gateway_client: ANTHROPIC_BASE_URL,
ANTHROPIC_AUTH_TOKEN) in Claude Code's request shape.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import question_sheet as qs  # noqa: E402
import question_sheet_session as ss  # noqa: E402

SAME = """An agent keeps questions for a human on a sheet; the human sees each one as a card. Question A was open on the sheet. Later the agent put question B on it.

<A>
{a}
</A>

<B>
{b}
</B>

Does B ask the human for the same decision as A, or for one that would settle or replace A's, so that a human who saw both would have to work out which one stands? Or is B a separate decision, answerable on its own whatever the answer to A? Answer JSON only: {"same_decision": true|false, "why": "<one short clause>"}"""

REVISED = """An agent keeps questions for a human on a sheet and revised one of them in place.

<before>
{a}
</before>

<after>
{b}
</after>

Does the revised question still ask for the same decision as before (reframed, with facts or options changed, is fine), or has it become a question about a different matter? Answer JSON only: {"same_decision": true|false, "why": "<one short clause>"}"""


def card(q):
    return qs.render_card({**q, "references": []})  # the reference bodies add nothing to these two judgments


def run(job, args, arms):
    arm, scenario, history, rep = job
    env, prefix, system, tools = qs.session(ss.e1_script(scenario, history), arms[arm])
    n0 = len(env.sheet.calls)
    before = {q: json.loads(json.dumps(v)) for q, v in env.sheet.questions.items()}
    steps, ended = qs.live(client, args.model, args.effort, system, tools, prefix, env, args.max_steps)
    return {"arm": arm, "scenario": scenario, "history": history, "rep": rep, "ended": ended, "steps": steps,
            "calls": env.sheet.calls[n0:], "before": before,
            "after": {q: {k: v for k, v in env.sheet.questions[q].items() if k != "history"} for q in env.sheet.questions}}


def classify(x, judge_effort):
    """The run's outcome, with the judgments it rests on written on the run."""
    t = ss.E1_TRIGGERS[x["scenario"]]
    target, calls = t["target"], [c for c in x["calls"] if "error" not in c]
    added = [q for c in calls for q in c["added"]]
    revised = [q for c in calls for q in c["revised"]]
    withdrew = [q for c in calls for q in c["withdrew"]]
    x["schema_errors"] = sum("error" in c for c in x["calls"])
    x["judged"] = {}
    for q in revised:  # does each revision still ask what it asked?
        x["judged"][f"revise {q}"] = qs.judge(client, REVISED.replace("{a}", card(x["before"][q])).replace(
            "{b}", card(x["after"][q])), judge_effort)
    repurposed = [q for q in revised if x["judged"][f"revise {q}"].get("same_decision") is False]
    if target is None:
        x["outcome"] = "repurposed" if repurposed else "added" if added else "no_ask"
        return x
    same = []
    for q in added:
        v = qs.judge(client, SAME.replace("{a}", card(x["before"][target])).replace("{b}", card(x["after"][q])),
                     judge_effort)
        x["judged"][f"added {q}"] = v
        if v.get("same_decision") is True:
            same.append(q)
    open_target = x["after"][target]["state"] == "open"
    if target in revised:
        x["outcome"] = "revised+duplicated" if same else "revised"
    elif target in withdrew:
        x["outcome"] = "replaced" if same else "withdrawn"
    elif same and open_target:
        x["outcome"] = "duplicated"
    else:
        x["outcome"] = "cut_off" if x["ended"] == "max_steps" else "untouched"
    x["repurposed"] = repurposed
    return x


FAIL = {"duplicated", "revised+duplicated", "untouched", "cut_off", "repurposed"}


def summary(results):
    rows = {}
    for x in results:
        if "error" in x:
            continue
        r = rows.setdefault((x["arm"], x["scenario"], x["history"]), {"runs": 0, "outcomes": {}, "schema_errors": 0})
        r["runs"] += 1
        r["outcomes"][x["outcome"]] = r["outcomes"].get(x["outcome"], 0) + 1
        r["schema_errors"] += x["schema_errors"]
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="*", help="NAME=PATH to a description file (default v1)")
    ap.add_argument("--scenarios", default=",".join(ss.E1_TRIGGERS))
    ap.add_argument("--history", default="far,near")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--judge-effort", default="low")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="question-sheet-revise-results.json")
    ap.add_argument("--dry-run", action="store_true", help="build every session and print its size; call nothing")
    args = ap.parse_args()
    arms = dict(a.split("=", 1) for a in args.arms) or {"v1": str(qs.DEFAULT_ARM)}
    jobs = [(a, s, h, r) for a in arms for s in args.scenarios.split(",") for h in args.history.split(",")
            for r in range(args.reps)]
    if args.dry_run:
        for a, s, h, _ in sorted({j[:3] + (0,) for j in jobs}):
            env, prefix, system, tools = qs.session(ss.e1_script(s, h), arms[a])
            print(a, s, h, f"{len(prefix)} messages, {len(json.dumps(prefix)):,} characters, open {env.sheet.open_ids()}")
        print(len(jobs), "runs")
        raise SystemExit
    from mid_turn import gateway_client
    client = gateway_client()
    out = qs.run_jobs(jobs, key=lambda j: j[:3], run=lambda j: run(j, args, arms), workers=args.workers)
    for x in out:
        if "error" not in x:
            try:
                classify(x, args.judge_effort)
            except Exception as e:
                x["outcome"], x["judge_error"] = "judge_error", repr(e)
    out.sort(key=lambda x: (x.get("arm", ""), x.get("scenario", ""), x.get("history", ""), x.get("rep", 0)))
    usage = qs.usage_total(out)
    Path(args.out).write_text(json.dumps({"python": sys.version.split()[0], "args": vars(args), "usage": usage,
                                          "runs": out}, indent=1, ensure_ascii=False, default=str))
    print(f"{len(out)} runs, {sum('error' in x for x in out)} errors; usage {usage}, about ${qs.cost(usage, args.model)} "
          f"at list price (judges not counted); full output in {args.out}")
    for key, r in sorted(summary(out).items()):
        fails = sum(v for k, v in r["outcomes"].items() if k in FAIL)
        print(*key, f"runs {r['runs']}", json.dumps(r["outcomes"]), f"failures {fails}", f"schema errors {r['schema_errors']}")
    for x in out:
        if "error" in x:
            print("error", x["job"], x["error"])
        else:
            print(x["arm"], x["scenario"], x["history"], x["rep"], x["outcome"], x["ended"],
                  [(c.get("added"), c.get("revised"), c.get("withdrew"), c.get("error")) for c in x["calls"]])
