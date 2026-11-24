#!/usr/bin/env python3
"""The question-sheet evals' logic, run against a fake client: no model call.

    python3 tests/output-styles/test-question-sheet-logic.py

It checks the stub against the composite spec's §2.1 and §2.2 (validation,
ids, revisions, ownership, the result's grammar with and without entry
places, reference capture), that every scripted history builds with no tool
error and the sheet E1 expects, the run loop's request shape and stopping,
and both evals' classification on scripted runs.
"""
import importlib.util, json, os, re, sys, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("ANTHROPIC_API_KEY", "dry-run")

from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock  # noqa: E402
import question_sheet as qs  # noqa: E402
import question_sheet_session as ss  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, (": " + str(detail)) if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def entry(q="Which?", **kw):
    return {"question": q, **kw}


# -- validation (§2.1, §1)

def refuses(inp, words):
    try:
        qs.validate(inp)
    except qs.InputError as e:
        return words in str(e)
    return False


check("empty call refused", refuses({}, "at least one"))
check("empty ask and withdraw refused", refuses({"ask": [], "withdraw": []}, "at least one"))
check("21 entries refused", refuses({"ask": [entry()] * 21}, "1 to 20"))
check("an id named twice refused", refuses({"ask": [entry(id="q1")], "withdraw": ["q1"]}, "more than once"))
check("multiSelect without options refused", refuses({"ask": [entry(multiSelect=True)]}, "needs options"))
check("equal labels refused", refuses({"ask": [entry(options=[{"label": "A"}, {"label": "A"}])]}, "unique"))
check("a preview on multi-select refused",
      refuses({"ask": [entry(multiSelect=True, options=[{"label": "A", "preview": "x"}])]}, "single-select"))
check("an unknown field refused", refuses({"ask": [entry(async_=True)]}, "does not take"))
check("13 options refused", refuses({"ask": [entry(options=[{"label": str(i)} for i in range(13)])]}, "at most 12"))
check("a long question refused", refuses({"ask": [entry("x" * 2001)]}, "at most 2000"))
check("a bad line range refused", refuses({"ask": [entry(references=[{"path": "a", "lines": [9, 3]}])]}, "line range"))
check("today's form refused", refuses({"questions": [entry()]}, "only ask and withdraw"))

# -- the stub's results (§2.2)

fs = ss.make_fs()
sheet = qs.Sheet(fs)
r = sheet.call({"ask": [entry("A?"), entry("B?", options=[{"label": "x"}, {"label": "y", "recommended": True}])]})
check("add assigns q1, q2", r == "Added q1, q2.", r)
r = sheet.call({"ask": [entry("A, revised?", id="q1"), entry("C?")], "withdraw": ["q2"]})
check("revise, add and withdraw in one line", r == "Added q3. Revised q1 (revision 2). Withdrew q2.", r)
check("revision kept with history", sheet.questions["q1"]["revision"] == 2 and len(sheet.questions["q1"]["history"]) == 1)
r = sheet.call({"ask": [entry("D?"), entry("E?", id="q2"), entry("F?", references=[{"path": ".env"}])],
                "withdraw": ["q9"]})
check("partial refusal carries entry places", r.split("\n")[0] == "Added q4 (entry 1).", r)
check("partial refusal says what was not done",
      r.split("\n")[1] == "Not done: entry 2, q2 is not open (withdrawn). entry 3, the reference .env could not be "
                          "read: permission denied. q9 is not open.", r)
r = sheet.call({"ask": [entry("G?", references=[{"path": "nope.py"}]), entry("H?", id="q3")]})
check("a refused add before a revise keeps places", r == "Revised q3 (entry 2, revision 2).\nNot done: entry 1, "
      "the reference nope.py could not be read: no such file.", r)
r = sheet.call({"ask": [entry("I?")]})
check("ids are never reused", r == "Added q5.", r)
r = sheet.call({"ask": [entry("J?", id="q1")]}, asker="a01")
check("a subagent cannot revise the main agent's question", "asked by another asker" in r and
      sheet.questions["q1"]["revision"] == 2, r)
r = sheet.call({"withdraw": ["q5"]}, asker="a01")
check("a subagent cannot withdraw it either", "another asker" in r and sheet.questions["q5"]["state"] == "open", r)
r = sheet.call({"ask": [entry("K?")]}, asker="a01")
r2 = sheet.call({"withdraw": ["q6"]})
check("the main conversation may withdraw a subagent's question", r == "Added q6." and r2 == "Withdrew q6.", (r, r2))
n = len(sheet.calls)
try:
    sheet.call({"ask": [entry("L?"), entry("M?", multiSelect=True)]})
    check("a schema failure raises", False)
except qs.InputError:
    check("a schema failure changes nothing", sheet.next_id == 7 and len(sheet.calls) == n + 1 and "error" in sheet.calls[-1])
cap, why = sheet.capture({"path": "tally/http/downloads.py", "lines": [1, 3]})
check("a reference is captured as Read shows it", why is None and cap["body"].split("\n")[0].endswith(
    '\t"""Download links for generated files (print view today; the CSV export\'s') and len(cap["body"].split("\n")) == 3, cap)

# -- the card

card = qs.render_card({"id": "q2", "revision": 1, "asker": "main", "question": "B?", "header": "Bee",
                       "context": "Because.", "options": [{"label": "x"}, {"label": "y", "recommended": True}],
                       "references": [{"path": "a.py", "lines": [1, 2], "body": "     1\tone\n     2\ttwo"}]})
check("the card shows what a surface shows", all(s in card for s in ("### Bee", "B?", "**Context**", "Because.",
      "**Reference: a.py lines 1-2**", "2. y  [recommended]", "free-text field")), card)

# -- the histories

for name, fn, trig, hists in (("e1", ss.e1_script, ss.E1_TRIGGERS, ("short", "near", "far")),
                              ("e2", ss.e2_script, ss.E2_TRIGGERS, ("short", "long"))):
    for sc in trig:
        for h in hists:
            env, prefix, system, tools = qs.session(fn(sc, h), qs.DEFAULT_ARM)
            errors = [b["content"] for m in prefix if m["role"] == "user" and isinstance(m["content"], list)
                      for b in m["content"] if b.get("is_error")]
            ok = not errors and (env.sheet.open_ids() == (["q1", "q2", "q3"] if name == "e1" else []))
            check(f"{name} {sc} {h} builds", ok, errors or env.sheet.open_ids())
env_n, pre_n, *_ = qs.session(ss.e1_script("premise", "near"), qs.DEFAULT_ARM)
env_f, pre_f, *_ = qs.session(ss.e1_script("premise", "far"), qs.DEFAULT_ARM)
strip = lambda msgs: sorted(re.sub(r'"(tool_use_id|id)": "toolu_p\d+"', "", json.dumps(m, sort_keys=True)) for m in msgs)
check("near and far hold the same steps", strip(pre_n) == strip(pre_f))
check("premise's rebase changes the grants", "billing_contacts" in env_f.fs.files[ss.P("tally/auth/permissions.py")])
check("the tool definition carries the arm's description",
      qs.sheet_tool_def()["description"].startswith("Put questions for the human on this session's question sheet."))
check("the built-in's async is not offered", "async" not in json.dumps(qs.sheet_tool_def()["input_schema"]))

# -- the shell the live part meets

env, *_ = qs.session(ss.e2_script("cap", "short"), qs.DEFAULT_ARM, [(r"smoke-staging", ss.trigger_output("cap"))])
sh = env.shell
check("the live part starts from a clean tree", sh("git status") == "On branch csv-export\nnothing to commit, working tree clean")
sh("mkdir -p tests/export && cat > tests/export/test_x.py <<'EOF'\ndef test_a():\n    pass\n\n\ndef test_b():\n    pytest\nEOF\n")
check("a heredoc writes its file", env.fs.files.get(ss.P("tests/export/test_x.py"), "").startswith("def test_a"))
check("git status shows the new file", "?? tests/export/test_x.py" in sh("git status --short"), sh("git status --short"))
check("pytest counts the tests it is given", sh("pytest tests/export/test_x.py -q").endswith("2 passed in 0.58s"),
      sh("pytest tests/export/test_x.py -q"))
sh("sed -i '' 's/normalize(), \"f\"/normalize(), \"g\"/' tally/export/writer.py")
check("sed -i edits in place", 'format(value.normalize(), "g")' in env.fs.files[ss.P("tally/export/writer.py")])
check("git diff shows the edit", '+        return format(value.normalize(), "g")' in sh("git diff"), sh("git diff"))
out = sh("git add -A && git commit -m 'wip: two tests'")
check("a commit cleans the tree", "2 files changed" in out and "nothing to commit" in sh("git status"), out)
check("git log shows the commit", sh("git log --oneline -3").split("\n")[0].endswith("wip: two tests"))
check("echo reads $? as 0", sh('false; echo "exit=$?"').endswith("exit=0"))
check("staging answers the numbers the session showed",
      "1204" in sh('psql "$STAGING_RO_URL" -c "select count(*) from accounts where timezone is null"'))
check("the trigger run again answers the same", "ExportTooLarge" in sh("make smoke-staging"))

# -- the run loop against a fake client


class Fake:
    def __init__(self, script, verdicts=None):
        self.script, self.requests, self.verdicts = list(script), [], list(verdicts or [])
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.requests.append(kw)
        if "tools" not in kw:  # a judge
            v = self.verdicts.pop(0)
            return types.SimpleNamespace(content=[BetaTextBlock(type="text", text=json.dumps(v))], stop_reason="end_turn")
        blocks = self.script.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        usage = types.SimpleNamespace(input_tokens=10, cache_read_input_tokens=1000, cache_creation_input_tokens=0,
                                      output_tokens=50)
        return types.SimpleNamespace(content=blocks, stop_reason=stop, usage=usage)


def use(i, name, inp):
    return BetaToolUseBlock(type="tool_use", id=f"toolu_l{i:02d}", name=name, input=inp)


env, prefix, system, tools = qs.session(ss.e1_script("option_gone", "short"), qs.DEFAULT_ARM)
fake = Fake([[use(1, "Read", {"file_path": "tally/http/downloads.py"})],
             [BetaTextBlock(type="text", text="Revising q1."), use(2, qs.SHEET_TOOL, {"ask": [entry("Cap?", id="q1")]})],
             [use(3, "Bash", {"command": "git status"})],
             [BetaTextBlock(type="text", text="never reached")]])
steps, ended = qs.live(fake, "claude-opus-5-5", "high", system, tools, prefix, env, 8)
req = fake.requests[0]
check("requests carry the gateway's shape", req["system"][0]["text"].startswith("You are Claude Code") and
      "claude-code-20250219" in req["betas"] and req["thinking"]["display"] == "updates")
check("the prefix's end is a cache breakpoint", req["messages"][-1]["content"][-1].get("cache_control") == {"type": "ephemeral"})
check("the newest message is a breakpoint later", fake.requests[1]["messages"][-1]["content"][-1].get("cache_control")
      and not prefix[-1]["content"][-1].get("cache_control"))
check("a run stops one response after its first sheet call", ended == "after_sheet" and len(steps) == 3, (ended, len(steps)))
check("the stub applied the live call", steps[1]["results"] == ["Revised q1 (revision 2)."] and
      env.sheet.questions["q1"]["revision"] == 2, steps[1]["results"])
check("the notes around a call are captured", qs.notes_before(steps, 1) == "Revising q1.")

# -- E1's outcomes

e1 = load("question-sheet-revise-eval")


def e1_run(calls, scenario="option_gone", ended="after_sheet"):
    env, prefix, system, tools = qs.session(ss.e1_script(scenario, "short"), qs.DEFAULT_ARM)
    before = json.loads(json.dumps(env.sheet.questions))
    n0 = len(env.sheet.calls)
    for c in calls:
        env.sheet.call(c)
    return {"scenario": scenario, "ended": ended, "calls": env.sheet.calls[n0:], "before": before,
            "after": {q: {k: v for k, v in env.sheet.questions[q].items() if k != "history"} for q in env.sheet.questions}}


def outcome(calls, verdicts, **kw):
    e1.client = Fake([], verdicts)
    return e1.classify(e1_run(calls, **kw), "low")["outcome"]


same, other = {"same_decision": True}, {"same_decision": False}
check("E1 revised", outcome([{"ask": [entry("Cap?", id="q1")]}], [same]) == "revised")
check("E1 duplicated", outcome([{"ask": [entry("Cap, again?")]}], [same]) == "duplicated")
check("E1 revised and duplicated", outcome([{"ask": [entry("Cap?", id="q1"), entry("Cap 2?")]}], [same, same])
      == "revised+duplicated")
check("E1 replaced", outcome([{"ask": [entry("Cap 2?")], "withdraw": ["q1"]}], [same]) == "replaced")
check("E1 withdrawn", outcome([{"withdraw": ["q1"]}], []) == "withdrawn")
check("E1 an unrelated add leaves it untouched", outcome([{"ask": [entry("Other?")]}], [other]) == "untouched")
check("E1 cut off", outcome([], [], ended="max_steps") == "cut_off")
check("E1 distinct added", outcome([{"ask": [entry("Dump?")]}], [], scenario="distinct") == "added")
check("E1 distinct repurposed", outcome([{"ask": [entry("Dump?", id="q2")]}], [other], scenario="distinct") == "repurposed")
check("E1 distinct no ask", outcome([], [], scenario="distinct") == "no_ask")

# -- E2's judging

e2 = load("question-sheet-card-eval")
facts_all = {"matter": "cap", "facts": {str(i): True for i in range(1, 7)}}
facts_missing = {"matter": "cap", "facts": {"1": True, "2": True, "3": False, "4": True, "5": True, "6": True}}
yes, partly = {"could_decide": "yes"}, {"could_decide": "partly"}
e2.READER_SAMPLES = 1
e2.client = Fake([], [facts_all, yes])
v = e2.judge_card("card", ["cap"], "low")
check("E2 a card with every fact and a yes passes", v["pass"] and v["essential"], v)
e2.client = Fake([], [facts_missing, yes])
check("E2 a missing essential fact fails", not e2.judge_card("card", ["cap"], "low")["pass"])
e2.client = Fake([], [facts_all, partly])
check("E2 a reader's partly fails", not e2.judge_card("card", ["cap"], "low")["pass"])
e2.client = Fake([], [{"matter": "pii", "facts": {"1": True}}, yes])
check("E2 a matter outside the scenario does not pass", not e2.judge_card("card", ["cap"], "low")["pass"])
x = {"scenario": "cap", "cards": [{"card": "c", "notes": "n"}, {"card": "d", "notes": ""}]}
e2.client = Fake([], [facts_missing, yes, facts_all, yes, facts_all, partly])
e2.judge_run(x, "low")
check("E2 capture judged only where there are notes", x["cards"][0]["with_capture"]["pass"] and
      x["cards"][1]["with_capture"] is x["cards"][1]["alone"])
check("E2 the matters asked are read from the cards", x["matters_asked"] == ["cap"])
e2.READER_SAMPLES = 3
e2.client = Fake([], [facts_all, yes, partly, yes])
check("E2 the reader is the median of three", e2.judge_card("card", ["cap"], "low")["reader"]["could_decide"] == "yes")
e2.client = Fake([], [facts_all, partly, yes, {"could_decide": "no"}])
check("E2 one yes of three is not a yes", not e2.judge_card("card", ["cap"], "low")["pass"])

print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
sys.exit(1 if FAILED else 0)
