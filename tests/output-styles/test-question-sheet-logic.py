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


# -- validation: C2's published tool-input schema (sminos/types/sheet/schema/tool-input.schema.json) as a whole

def refuses(inp, words):
    try:
        qs.validate(inp)
    except qs.InputError as e:
        return words in str(e)
    return False


def accepts(inp):
    try:
        qs.validate(inp)
        return True
    except qs.InputError:
        return False


check("empty call refused", refuses({}, "at least one"))
check("an empty withdraw is a schema fault (minItems 1)", refuses({"ask": [entry()], "withdraw": []}, "one or more"))
check("21 entries refused", refuses({"ask": [entry()] * 21}, "1 to 20"))
check("an id named twice refused", refuses({"ask": [entry(id="q1")], "withdraw": ["q1"]}, "more than once"))
check("q0 is not an id", refuses({"withdraw": ["q0"]}, "question ids"))
check("an unknown field refused", refuses({"ask": [entry(async_=True)]}, "does not take"))
check("13 options refused", refuses({"ask": [entry(options=[{"label": str(i)} for i in range(13)])]}, "at most 12"))
check("a long question refused", refuses({"ask": [entry("x" * 2001)]}, "at most 2000"))
check("today's form refused", refuses({"questions": [entry()]}, "only ask and withdraw"))
check("options: false is a schema fault", refuses({"ask": [entry(options=False)]}, "options is a list"))
check("references: 0 is a schema fault", refuses({"ask": [entry(references=0)]}, "references is a list"))
check('recommended: "false" is a schema fault',
      refuses({"ask": [entry(options=[{"label": "A", "recommended": "false"}])]}, "boolean"))
check('multiSelect: "yes" is a schema fault', refuses({"ask": [entry(multiSelect="yes")]}, "boolean"))
check("lines of strings are a schema fault", refuses({"ask": [entry(references=[{"path": "a", "lines": ["1", "2"]}])]},
                                                     "two integers"))
check("entry-local rules pass the schema", accepts({"ask": [entry(multiSelect=True)]}) and
      accepts({"ask": [entry(references=[{"path": "a", "lines": [9, 3]}])]}) and
      accepts({"ask": [entry(options=[{"label": "A"}, {"label": "A"}])]}) and
      accepts({"ask": [entry(multiSelect=True, options=[{"label": "A", "preview": "x"}])]}))

# -- the stub's results (§2.2, C2's grammar sminos/types/sheet/grammar/result.md)

fs = ss.make_fs()
sheet = qs.Sheet(fs)
r = sheet.call({"ask": [entry("A?"), entry("B?", options=[{"label": "x"}, {"label": "y", "recommended": True}])]})
check("add assigns q1, q2", r == "Added q1, q2.", r)
r = sheet.call({"ask": [entry("A, revised?", id="q1"), entry("C?")], "withdraw": ["q2"]})
check("revise, add and withdraw in one line", r == "Added q3. Revised q1 (revision 2). Withdrew q2.", r)
check("revision kept with history", sheet.questions["q1"]["revision"] == 2 and len(sheet.questions["q1"]["history"]) == 1)
check("a call records the card it showed and, for a revision, the one before",
      sheet.calls[-1]["shown"]["q1"]["question"] == "A, revised?" and sheet.calls[-1]["before"]["q1"]["question"] == "A?"
      and sheet.calls[-1]["shown"]["q3"]["question"] == "C?")
r = sheet.call({"ask": [entry("D?"), entry("E?", id="q2"), entry("F?", references=[{"path": ".env"}])],
                "withdraw": ["q9"]})
check("partial refusal carries entry places", r.split("\n")[0] == "Added q4 (entry 1).", r)
check("partial refusal says what was not done, in the grammar's clauses",
      r.split("\n")[1] == "Not done: entry 2, q2 is not open (withdrawn at 15:42). entry 3, the reference .env could "
                          "not be read: permission denied. q9 is not open (never asked at 15:42).", r)
r = sheet.call({"ask": [entry("G?", references=[{"path": "nope.py"}]), entry("H?", id="q3")]})
check("a refused add before a revise keeps places", r == "Revised q3 (entry 2, revision 2).\nNot done: entry 1, "
      "the reference nope.py could not be read: no such file.", r)
r = sheet.call({"ask": [entry("I?")], "withdraw": ["q99"]})
check("a refused withdrawal alone puts places on the adds", r.split("\n")[0] == "Added q5 (entry 1).", r)
r = sheet.call({"ask": [entry("Dup?", options=[{"label": "A"}, {"label": "A"}])], "withdraw": ["q2"]})
check("a call in which nothing was done says so on its first line", r == 'Nothing done.\nNot done: entry 1, two '
      'options share the label "A". q2 is not open (withdrawn at 15:42).', r)
r = sheet.call({"ask": [entry("M?", multiSelect=True), entry("P?", multiSelect=True, options=[{"label": "A", "preview": "x"}]),
                        entry("L?", references=[{"path": "pyproject.toml", "lines": [9, 3]}]), entry("Fine?"),
                        entry("I, revised?", id="q5")]})
check("entry-local faults refuse their entry alone", r == "Added q6 (entry 4). Revised q5 (entry 5, revision 2).\n"
      "Not done: entry 1, multiSelect needs options. entry 2, an option's preview needs a single-select question. "
      "entry 3, lines must be [a, b] with 1 <= a <= b.", r)
sheet.call({"withdraw": ["q6"]})
r = sheet.call({"ask": [entry("Std?", references=[{"path": f"{ss.STDLIB}/csv.py"}])]})
check("a reference outside the working directories is refused", "it is outside the session's working directories" in r, r)
fs.files[ss.P(".fixtures/usage_2m.sql")] = "-- rows=2000000\n"
fs.sizes[ss.P(".fixtures/usage_2m.sql")] = 611 * 2**20
r = sheet.call({"ask": [entry("Big?", references=[{"path": ".fixtures/usage_2m.sql"}])]})
check("a file the world models over 256 KB needs a range", "over Read's 256 KB without a range" in r, r)
r = sheet.call({"ask": [entry("Big, ranged?", references=[{"path": ".fixtures/usage_2m.sql", "lines": [1, 1]}])]})
check("with a range it is captured", r.startswith("Added"), r)
n_next = sheet.next_id
r = sheet.call({"ask": [entry("J?", id="q1")]}, asker="a01")
check("a subagent cannot revise the main agent's question", r == "Nothing done.\nNot done: entry 1, q1 was asked by "
      "the main conversation; only its asker revises it." and sheet.questions["q1"]["revision"] == 2, r)
r = sheet.call({"withdraw": ["q5"]}, asker="a01")
check("a subagent cannot withdraw it either", r == "Nothing done.\nNot done: q5 was asked by the main conversation; "
      "only its asker or the main conversation withdraws it." and sheet.questions["q5"]["state"] == "open", r)
r = sheet.call({"ask": [entry("K?")]}, asker="a01")
r2 = sheet.call({"withdraw": [f"q{n_next}"]})
check("the main conversation may withdraw a subagent's question", r == f"Added q{n_next}." and
      r2 == f"Withdrew q{n_next}.", (r, r2))
n = len(sheet.calls)
try:
    sheet.call({"ask": [entry("L?"), entry("M?", options=False)]})
    check("a schema failure raises", False)
except qs.InputError:
    check("a schema failure changes nothing", sheet.next_id == n_next + 1 and len(sheet.calls) == n + 1
          and "error" in sheet.calls[-1])
cap, why = sheet.capture({"path": "tally/http/downloads.py", "lines": [1, 3]})
check("a reference is captured as Read shows it", why is None and cap["body"].split("\n")[0].endswith(
    '\t"""Download links for generated files (print view today; the CSV export\'s') and len(cap["body"].split("\n")) == 3, cap)
first_line = __import__("re").compile(r"^(?:Nothing done\.|Outcome not known yet\.|Added q[0-9]+(?: \(entry [0-9]+\))?(?:, q[0-9]+(?: \(entry [0-9]+\))?)*\.(?: Revised q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\)(?:, q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\))*\.)?(?: Withdrew q[0-9]+(?:, q[0-9]+)*\.)?|Revised q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\)(?:, q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\))*\.(?: Withdrew q[0-9]+(?:, q[0-9]+)*\.)?|Withdrew q[0-9]+(?:, q[0-9]+)*\.)$")
results = [c for c in sheet.calls if "error" not in c]
check("every result's first line matches C2's pattern", len(results) > 10 and
      all(first_line.match(c["result"].split("\n")[0]) for c in results), [c["result"] for c in results])

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
check("pytest counts the tests it is given", sh("pytest tests/export/test_x.py -q").endswith("2 passed in 0.24s"),
      sh("pytest tests/export/test_x.py -q"))
sh("sed -i '' 's/normalize(), \"f\"/normalize(), \"g\"/' tally/export/writer.py")
check("sed -i edits in place", 'format(value.normalize(), "g")' in env.fs.files[ss.P("tally/export/writer.py")])
check("git diff shows the edit", '+        return format(value.normalize(), "g")' in sh("git diff"), sh("git diff"))
out = sh("git add -A && git commit -m 'wip: two tests'")
check("a commit cleans the tree", "2 files changed" in out and "nothing to commit" in sh("git status"), out)
sh("echo x > tests/export/y.py")
sh("touch tests/export/z.py")
out = sh("git add -A && git commit -m \"$(cat <<'EOF'\nexport: a message\n\nwith a body\nEOF\n)\"")
check("a commit message in Claude Code's heredoc form is kept", "export: a message" in out, out)
check("git log shows the commit", sh("git log --oneline -3").split("\n")[1].endswith("wip: two tests"))
check("git log honours -N", len(sh("git log --oneline -3").split("\n")) == 3)
check("commands split outside quotes only", qs.simple_commands('git commit -m "a; b" && git log | head -2') ==
      [["git", "commit", "-m", "a; b"], ["git", "log"]])
env_p, *_ = qs.session(ss.e1_script("premise", "far"), qs.DEFAULT_ARM)
check("the branch's scripted commits sit on main's new one", env_p.shell("git log --oneline -4").split("\n")[3]
      .startswith("5d0e7a9"), env_p.shell("git log --oneline -4"))
check("pytest -v lists the tests it ran", "tests/export/test_x.py::test_a PASSED" in sh("pytest tests/export/test_x.py -v"))
check("pytest -k filters by name", sh("pytest tests/export/test_x.py -k test_b -q").endswith("1 passed in 0.22s"),
      sh("pytest tests/export/test_x.py -k test_b -q"))
check("an unknown command prints nothing without a simulator", sh("uv run python -c 'print(1)'") == qs.NO_OUTPUT)


class SimClient:
    def __init__(self):
        self.prompts = []
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        return types.SimpleNamespace(content=[BetaTextBlock(type="text", text="1")])


sim = SimClient()
env.simulator = (sim, "claude-sonnet-5-5", ss.SIM_FACTS)
out = sh("uv run python -c 'print(1)' && git status")
check("an unknown command goes to the simulator alone", out.startswith("1\nOn branch") and
      sim.prompts[0].endswith("Command line:\nuv run python -c 'print(1)'")
      and "1,204 of them" in sim.prompts[0] and env.simulated[-1]["output"] == "1", out)
check("2>&1 is a redirection, not a separator", qs.simple_commands("pytest -q 2>&1 | tail -3") == [["pytest", "-q", "2>&1"]])
sh("stat -f '%z' x.sql >> /tmp/o.txt 2>&1")
check("redirections reach the simulator unquoted", sim.prompts[-1].endswith("stat -f %z x.sql >> /tmp/o.txt 2>&1"),
      sim.prompts[-1][-60:])
sh("for c in a b; do git show $c; done")
check("a compound command goes to the simulator whole", sim.prompts[-1].endswith("for c in a b; do git show $c; done")
      and "41b0c8a docs: CSV export spec" in sim.prompts[-1])
check("a known command does not", sh("git status").startswith("On branch") and len(sim.prompts) == 3)
env_f, *_ = qs.session(ss.e2_script("cap", "long"), qs.DEFAULT_ARM)
check("the slow test takes its time and needs the fixture make wrote", "611 MB" not in env_f.shell("ls -la .fixtures")
      and "640679936" in env_f.shell("ls -la .fixtures") and "in 83.70s" in env_f.shell("pytest tests/export -m slow -q -s"))
check("git log over paths is not answered by the canned shell", env_f.shell_one(["git", "log", "--", "Makefile"]) is None)
env_d, prefix_d, *_ = qs.session(ss.e1_script("premise", "far"), qs.DEFAULT_ARM)
shown = next(b["content"] for m in prefix_d if m["role"] == "user" and isinstance(m["content"], list)
             for b in m["content"] if "diff --git a/tally/export/writer.py" in str(b.get("content", "")))
live_diff = env_d.shell("git diff main...csv-export")
check("the live branch diff agrees with the one the session showed",
      all(f"diff --git a/{f}" in live_diff for f in ("tally/export/writer.py", "tally/export/columns.py",
                                                      "tests/export/test_writer.py", "docs/export.md"))
      and "migrations/0042" not in live_diff and "tally/auth/permissions.py" not in live_diff, live_diff[:300])
check("git diff --stat against main lists the branch's files", "tally/export/writer.py |" in
      env_d.shell("git diff --stat main...HEAD") and "files changed" in env_d.shell("git diff --stat main...HEAD"))
check("git diff against a commit goes to the simulator", env_d.shell_one(["git", "diff", "3d70a1e"]) is None)
check("echo reads $? as 0", sh('false; echo "exit=$?"').endswith("exit=0"))
env.simulator = None
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

env, prefix, system, tools = qs.session(ss.e1_script("option_gone", "short"), qs.DEFAULT_ARM)
fake = Fake([[use(4, qs.SHEET_TOOL, {"ask": [entry("Unrelated?")]})], [use(5, "Bash", {"command": "git status"})],
             [use(6, qs.SHEET_TOOL, {"ask": [entry("Cap?", id="q1")]})], [use(7, "Bash", {"command": "ls"})],
             [BetaTextBlock(type="text", text="never reached")]])
touched = lambda env, calls: any("q1" in c.get("revised", []) for c in calls)
steps, ended = qs.live(fake, "claude-opus-5-5", "medium", system, tools, prefix, env, 20, touched)
check("an early unrelated call does not stop an E1 run", ended == "after_sheet" and len(steps) == 4, (ended, len(steps)))

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
e2.client = Fake([], [facts_missing, yes, facts_all, yes, facts_all, partly])  # one reader each: READER_SAMPLES is 1
e2.judge_run(x, "low")
check("E2 capture judged only where there are notes", x["cards"][0]["with_capture"]["pass"] and
      x["cards"][1]["with_capture"] is x["cards"][1]["alone"])
check("E2 the matters asked are read from the cards", x["matters_asked"] == ["cap"])
e2.READER_SAMPLES = 3
e2.client = Fake([], [facts_all, yes, partly, yes])
check("E2 the reader is the median of three", e2.judge_card("card", ["cap"], "low")["reader"]["could_decide"] == "yes")
e2.client = Fake([], [facts_all, partly, yes, {"could_decide": "no"}])
check("E2 one yes of three is not a yes", not e2.judge_card("card", ["cap"], "low")["pass"])
e2.client = Fake([], [{"matter": "pii", "facts": {"1": True}}, yes])
v = e2.judge_card("card", list(ss.MATTERS), "low", counted=["cap"])
check("E2 a card outside the counted matters gets one reader", len(v["readers"]) == 1)

# -- Acceptance 14's gates


def e1_runs(fails=0, repurposed=0, changed=30, control=10, history="far"):
    out = []
    for i in range(changed):
        out.append({"arm": "v3", "history": history, "scenario": ["option_gone", "premise", "subagent"][i % 3],
                    "outcome": "duplicated" if i < fails else "revised"})
    for i in range(control):
        out.append({"arm": "v3", "history": history, "scenario": "distinct",
                    "outcome": "repurposed" if i < repurposed else "added"})
    return out


check("E1 gate: 1 failure in 30 passes", e1.gate(e1_runs(fails=1))["v3"]["verdict"] == "PASS")
check("E1 gate: 2 failures in 30 fail", e1.gate(e1_runs(fails=2))["v3"]["verdict"] == "FAIL")
check("E1 gate: a repurposed control fails", e1.gate(e1_runs(repurposed=1))["v3"]["verdict"] == "FAIL")
check("E1 gate: 29 changed runs are short", e1.gate(e1_runs(changed=29))["v3"]["verdict"] == "short")
check("E1 gate: other histories are not counted", e1.gate(e1_runs(history="near")) == {})


def card(matter, essential=True, reader="yes"):
    return {"alone": {"matter": matter, "essential": essential, "reader": {"could_decide": reader},
                      "pass": essential and reader == "yes"}}


def e2_runs(essential_misses=0, noes=0, pii_fails=0, reps=8, cap_pass=False):
    out = []
    for sc in ("cap", "pii", "tz", "all"):
        for r in range(reps):
            cards = [card(m) for m in ss.E2_TRIGGERS[sc]["matters"]] + [card(None)]
            out.append({"arm": "v3", "history": "long", "scenario": sc, "cards": cards})
    counted = [c for x in out for c in x["cards"][:-1]]
    for c in counted:
        if c["alone"]["matter"] == "cap" and not cap_pass:
            c["alone"].update(reader="partly", pass_=False)
            c["alone"]["reader"] = {"could_decide": "partly"}
            c["alone"]["pass"] = False
    for c in counted[:essential_misses]:
        c["alone"].update(essential=False, **{"pass": False})
    for c in [c for c in counted if c["alone"]["matter"] == "tz"][:noes]:
        c["alone"]["reader"] = {"could_decide": "no"}
        c["alone"]["pass"] = False
    for c in [c for c in counted if c["alone"]["matter"] == "pii"][:pii_fails]:
        c["alone"]["reader"] = {"could_decide": "partly"}
        c["alone"]["pass"] = False
    return out  # 48 counted cards: 16 cap, 16 pii, 16 tz


g = e2.gate(e2_runs())["v3"]
check("E2 gate: cap failing alone does not fail the gate", g["verdict"] == "PASS" and g["cap_pass"] == 0, g)
check("E2 gate: essential facts on 80% pass", e2.gate(e2_runs(essential_misses=9))["v3"]["verdict"] == "PASS")
check("E2 gate: essential facts below 80% fail", e2.gate(e2_runs(essential_misses=10))["v3"]["verdict"] == "FAIL")
check("E2 gate: two readers' no pass", e2.gate(e2_runs(noes=2))["v3"]["verdict"] == "PASS")
check("E2 gate: three readers' no fail", e2.gate(e2_runs(noes=3))["v3"]["verdict"] == "FAIL")
check("E2 gate: 85% of pii and tz passing pass", e2.gate(e2_runs(pii_fails=4))["v3"]["verdict"] == "PASS")
check("E2 gate: below 85% of pii and tz fail", e2.gate(e2_runs(pii_fails=5))["v3"]["verdict"] == "FAIL")
check("E2 gate: 7 runs of a scenario are short", e2.gate(e2_runs(reps=7))["v3"]["verdict"] == "short")
check("the evals ship v3 as their default", qs.DEFAULT_ARM.name == "description-v3.md" and
      "Ask when a question comes up, then keep working." in qs.sheet_tool_def()["description"]
      and "at that moment" not in qs.sheet_tool_def()["description"])

print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
sys.exit(1 if FAILED else 0)
