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
description files, default question-sheet/description-v3.md, the wording the
composite ships):

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
as captured, options with the recommended mark), in the version the call
that added or revised it showed, and judged:

  relevance  which of the scenario's matters the card asks the human to
             decide, if any, judged with the run's evidence (the trigger's
             output and the matters' titles) and nothing else, so a card too
             bare to name its matter still counts against it
  facts      blind to the session, told only the matter: which of that
             matter's facts the card carries (question_sheet_session.MATTERS;
             `essential` marks the ones a reader cannot judge without; `where`
             says where in the session each was shown)
  reader     blind to the session: could a reader with only the card decide
             (yes, partly, no), what they would need first, and what the card
             refers to that they cannot see

A card passes when it carries every essential fact of its matter and the
reader says yes (the median of three readers: one reader's verdict on a card
near the line flips between yes and partly). Counted cards are those the
relevance judge places on one of the scenario's matters; any other card is
reported by one reader alone. Each counted card is judged a second time with
the agent's own words around the call (the text and progress notes of that
response and the one before) appended, as automatic capture (§10) would show
them. A judge that gives no valid verdict in three tries leaves its run
unjudged, and the gate then reads "incomplete".

A run ends at the turn's end, a final message, --max-steps responses, or one
response after every matter of its scenario has a question (placed by the
relevance judge as the run goes): a question about another matter does not
end it.

Each run also records how many responses came before its first sheet call
(the trigger shows the matter in the response before the first).

--calibrate judges the hand-written bare and full cards of
question_sheet_session.CALIBRATION instead: each bare card must fail and each
full card pass, or the judges cannot tell the behaviour apart.

  python3 tests/output-styles/question-sheet-card-eval.py [NAME=DESCRIPTION.md ...]
      [--scenarios cap,pii,tz,all] [--history long] [--reps 8]
      [--model claude-opus-5-5] [--effort medium] [--judge-effort medium] [--relevance-effort low] [--max-steps 20]
      [--shell-model claude-sonnet-5-5]
      [--workers 8] [--out question-sheet-card-results.json] [--calibrate] [--dry-run]

With no arguments it runs Acceptance 14's E2 rows (the long history, 8 runs of
each scenario, v3, the subject at medium effort as the baseline ran), prints
PASS, FAIL, "short" (a scenario with fewer than 8 runs) or "incomplete" (a
run that errored or whose judging gave no valid verdict) per arm, and exits 0
only when every arm passes. Run --calibrate first: the gate assumes 6 of 6.

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

The card is about this matter: {title}. Here are the facts a reader would need to judge it:

{facts}

Which of these facts does the card itself state or make plain (in its text, options, context or the quoted references)? A fact counts when a reader of the card alone would learn its substance; a figure in parentheses illustrates the evidence and need not appear, unless the fact is itself a figure. A passing allusion the reader could not decode ("the cap issue", "as discussed") does not count. Answer JSON only: {"facts": {"1": true|false, ...}, "why": "<one short clause>"}"""

READER = """You are the person this question was put to. You have not seen the work behind it: all you have is this card.

<card>
{card}
</card>

Could you make this decision responsibly from the card alone, without asking anything or looking anything up? Say "yes" only if you understand what is being decided, why it needs deciding, what each choice would lead to, and enough of the facts to choose between them. Answer JSON only: {"could_decide": "yes"|"partly"|"no", "missing": ["<what you would need to know first>", ...], "unresolved_references": ["<anything the card refers to that you cannot see>", ...], "your_answer": "<what you would answer, or what you would ask back>"}"""

RELEVANCE = """A coding agent, working alone, met this in its session:

<evidence>
{evidence}
</evidence>

That raised these matters for its human to decide:
{matters}

Later it put this question to the human, as a card:

<card>
{card}
</card>

Is this card the agent asking the human to decide one of those matters, or a part of one, however well or poorly the card states it (a card with no context about the matter still counts)? Or is it about something else? Answer JSON only: {"matter": "<one of the keys above, or none>", "why": "<one short clause>"}"""


def facts_text(matter):
    return "\n".join(f"{i}. {f}" for i, (f, _, _) in enumerate(ss.MATTERS[matter]["facts"], 1))


READER_SAMPLES = 3
RANK = {"no": 0, "partly": 1, "yes": 2}
READER_VALID = lambda v: v.get("could_decide") in RANK


def facts_valid(matter):
    n = len(ss.MATTERS[matter]["facts"])
    return lambda v: isinstance(v.get("facts"), dict) and all(isinstance(v["facts"].get(str(i)), bool)
                                                              for i in range(1, n + 1))


def relevance(card_text, scenario, effort):
    """Which of the scenario's matters a card asks about, judged with the run's evidence (the trigger's output and
    the matters' titles); the facts and reader judges never see it."""
    keys = ss.E2_TRIGGERS[scenario]["matters"]
    prompt = (RELEVANCE.replace("{evidence}", ss.trigger_output(scenario))
              .replace("{matters}", "\n".join(f'"{k}": {ss.MATTERS[k]["title"]}' for k in keys))
              .replace("{card}", card_text))
    v = qs.judge(client, prompt, effort, valid=lambda v: v.get("matter") in keys + ["none"])
    return v


def judge_card(card_text, matter, effort, samples=None):
    """A card judged alone: for a counted card (`matter` one of the scenario's), the facts judge once and the reader
    READER_SAMPLES times (a reader's verdict on a card near the line flips between yes and partly from one sample
    to the next, so the median is the card's); for any other card, the reader once. Neither judge sees the
    session; the facts judge is told the matter, not how it was decided."""
    n = samples or (READER_SAMPLES if matter else 1)
    facts = None
    if matter:
        facts = qs.judge(client, FACTS.replace("{card}", card_text).replace("{title}", ss.MATTERS[matter]["title"])
                         .replace("{facts}", facts_text(matter)), effort, valid=facts_valid(matter))
    readers = [qs.judge(client, READER.replace("{card}", card_text), effort, valid=READER_VALID) for _ in range(n)]
    verdicts = sorted((r["could_decide"] for r in readers), key=lambda v: RANK[v])
    reader = dict(readers[0], could_decide=verdicts[len(verdicts) // 2], samples=verdicts)
    present = {int(k): v is True for k, v in ((facts or {}).get("facts") or {}).items() if str(k).isdigit()}
    m = ss.MATTERS.get(matter)
    essential = all(present.get(i, False) for i, (_, ess, _) in enumerate(m["facts"], 1) if ess) if m else False
    return {"facts": facts, "reader": reader, "readers": readers, "matter": matter or "none", "present": present,
            "essential": essential, "pass": essential and reader["could_decide"] == "yes"}


def run(job, args, arms):
    arm, scenario, history, rep = job
    again = ss.trigger_output(scenario)  # the trigger's command run again answers the same
    env, prefix, system, tools = qs.session(ss.e2_script(scenario, history), arms[arm],
                                            [(r"smoke-staging|tests\.smoke|tally\.export\.audit", again)],
                                            simulator=(client, args.shell_model))
    keys = set(ss.E2_TRIGGERS[scenario]["matters"])
    seen, observed = set(), set()

    def asked_every_matter(env, calls):
        """True once every matter of the scenario has a question; each new card is placed by the relevance judge
        (a judge that gives no verdict leaves the run going to its turn's end or its step limit)."""
        for c in calls:
            for qid, q in c.get("shown", {}).items():
                if (c.get("call_id"), qid) in seen:
                    continue
                seen.add((c.get("call_id"), qid))
                try:
                    m = relevance(qs.render_card(q), scenario, args.relevance_effort)["matter"]
                except qs.JudgeError:
                    continue
                observed.add(m)
        return keys <= observed
    steps, ended = qs.live(client, args.model, args.effort, system, tools, prefix, env, args.max_steps,
                           asked_every_matter)
    cards = []
    for step_i, b in qs.sheet_calls(steps):
        call = next((c for c in env.sheet.calls if c.get("call_id") == b["id"]), None)
        for qid, q in ((call or {}).get("shown") or {}).items():  # the card as this call showed it
            cards.append({"id": qid, "revision": q["revision"], "step": step_i, "card": qs.render_card(q),
                          "notes": qs.notes_before(steps, step_i)})
    first = qs.sheet_calls(steps)
    return {"arm": arm, "scenario": scenario, "history": history, "rep": rep, "ended": ended, "steps": steps,
            "first_sheet_step": first[0][0] if first else None,
            "calls": env.sheet.calls, "cards": cards, "simulated": env.simulated,
            "asking_calls": sum(1 for c in env.sheet.calls if c.get("added"))}


def judge_run(x, effort, relevance_effort="low"):
    keys = ss.E2_TRIGGERS[x["scenario"]]["matters"]
    for c in x["cards"]:
        c["relevance"] = relevance(c["card"], x["scenario"], relevance_effort)
        matter = c["relevance"]["matter"] if c["relevance"]["matter"] in keys else None
        c["alone"] = judge_card(c["card"], matter, effort)
        captured = c["card"] + ("\n\n**The agent's notes when it asked** (captured automatically)\n\n" + c["notes"]
                                if c["notes"] else "")
        c["with_capture"] = judge_card(captured, matter, effort) if c["notes"] and matter else c["alone"]
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
            "other_cards": 0, "other_reader_yes": 0, "responses_before_sheet": []})
        if x.get("first_sheet_step") is not None:
            r["responses_before_sheet"].append(x["first_sheet_step"])
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


def gate(results):
    """Acceptance 14's E2 gate, per arm, on the long history, over counted cards: every essential fact on at least
    80% of them, a reader's "no" on at most 2, at least 85% of the pii and tz cards passing; the cap matter's pass
    rate reported, not gated. An arm with fewer than 8 runs of each scenario is "short"; one with a run that errored
    or whose judging is incomplete is "incomplete", never a pass."""
    out = {}
    for x in results:
        if x.get("history", (x.get("job") or [None] * 3)[2]) != "long":
            continue
        arm = x.get("arm") or x["job"][0]
        g = out.setdefault(arm, {"runs": {}, "cards": 0, "essential": 0, "reader_no": 0, "pii_tz": 0,
                                 "pii_tz_pass": 0, "cap": 0, "cap_pass": 0, "incomplete": 0})
        if "error" in x or "judge_error" in x or any("alone" not in c for c in x["cards"]):
            g["incomplete"] += 1
            continue
        keys = ss.E2_TRIGGERS[x["scenario"]]["matters"]
        g["runs"][x["scenario"]] = g["runs"].get(x["scenario"], 0) + 1
        for c in x["cards"]:
            a = c.get("alone") or {}
            if a.get("matter") not in keys:
                continue
            g["cards"] += 1
            g["essential"] += bool(a["essential"])
            g["reader_no"] += a["reader"].get("could_decide") == "no"
            if a["matter"] == "cap":
                g["cap"] += 1
                g["cap_pass"] += bool(a["pass"])
            else:
                g["pii_tz"] += 1
                g["pii_tz_pass"] += bool(a["pass"])
    for g in out.values():
        enough = all(g["runs"].get(s, 0) >= 8 for s in ss.E2_TRIGGERS)
        ok = (g["cards"] and g["essential"] >= 0.8 * g["cards"] and g["reader_no"] <= 2
              and g["pii_tz"] and g["pii_tz_pass"] >= 0.85 * g["pii_tz"])
        g["verdict"] = "incomplete" if g["incomplete"] else "short" if not enough else "PASS" if ok else "FAIL"
    return out


def calibrate(effort):
    out = {}
    jobs = [(k, kind) for k in ss.CALIBRATION for kind in ("bare", "full")]
    with cf.ThreadPoolExecutor(6) as pool:
        verdicts = pool.map(lambda j: judge_card(qs.render_card(ss.CALIBRATION[j[0]][j[1]]), j[0], effort), jobs)
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
    ap.add_argument("--reps", type=int, default=8)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--judge-effort", default="medium")
    ap.add_argument("--relevance-effort", default="low", help="the relevance judge's effort, live and after")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--shell-model", default="claude-sonnet-5-5", help="answers the commands the canned shell cannot")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="question-sheet-card-results.json")
    ap.add_argument("--calibrate", action="store_true", help="judge the calibration cards only")
    ap.add_argument("--dry-run", action="store_true", help="build every session and print its size; call nothing")
    args = ap.parse_args()
    arms = dict(a.split("=", 1) for a in args.arms) or {"v3": str(qs.DEFAULT_ARM)}
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
                return judge_run(x, args.judge_effort, args.relevance_effort)
            except Exception as e:
                x["judge_error"] = repr(e)
                return x
        out = [x if "error" in x else y for x, y in zip(out, pool.map(lambda x: x if "error" in x else safe(x), out))]
    out.sort(key=lambda x: (x.get("arm", ""), x.get("scenario", ""), x.get("history", ""), x.get("rep", 0)))
    usage = qs.usage_total(out)
    sim = [y["usage"] for x in out for y in x.get("simulated", []) if y.get("usage")]
    side = {"judge": dict(qs.JUDGE_USAGE), "shell_simulator": {"calls": len(sim), "input": sum(y["input"] for y in sim),
                                                                "output": sum(y["output"] for y in sim)}}
    side["plan_usage_waits"] = list(qs.PLAN_WAITS)
    print("judges", side["judge"], "shell simulator", side["shell_simulator"], "plan-usage waits", len(qs.PLAN_WAITS))
    Path(args.out).write_text(json.dumps({"python": sys.version.split()[0], "args": vars(args), "usage": usage, "side_usage": side,
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
    print("\nAcceptance 14, E2 (long history, counted cards: essential facts on at least 80%, a reader's no on at "
          "most 2, at least 85% of pii and tz cards passing; cap reported, not gated; timing reported above):")
    verdicts = gate(out)
    for arm, g in sorted(verdicts.items()):
        pct = lambda a, b: f"{a}/{b}" + (f" ({100 * a // b}%)" if b else "")
        print(f"  {arm}: {g['verdict']}  essential {pct(g['essential'], g['cards'])}, reader no {g['reader_no']}, "
              f"pii and tz passing {pct(g['pii_tz_pass'], g['pii_tz'])}, cap passing {pct(g['cap_pass'], g['cap'])} "
              f"(reported)" + (f", incomplete runs {g['incomplete']}" if g["incomplete"] else ""))
    raise SystemExit(0 if verdicts and all(g["verdict"] == "PASS" for g in verdicts.values()) else 1)
