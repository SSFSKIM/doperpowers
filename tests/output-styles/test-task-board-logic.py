#!/usr/bin/env python3
"""The Task Board evals' logic, run against a fake client: no model call.

    python3 tests/output-styles/test-task-board-logic.py

It checks the stand-in (the built commands on a store of the run's own, the
door refusing a session and taking the human, a session that removes its own
id, a subagent's attribution, the help an arm adds, a ticket form), the shell
that takes a command line apart (heredocs, pipes, files of the simulated
project, a captured id, a line it cannot take apart), the words and what each
arm puts in context, that every scripted session builds, the notice's frame,
and the classification, the measures and the gate on scripted runs.
"""
import importlib.util, json, os, sys, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("ANTHROPIC_API_KEY", "dry-run")

from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock  # noqa: E402
import question_sheet as qs  # noqa: E402
import task_board as tb  # noqa: E402
import task_board_session as ts  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, (": " + str(detail)) if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


spec = importlib.util.spec_from_file_location("task_board_eval", HERE / "task-board-eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

# -- the words and the arms

ship, bare, sheet = tb.Words(arm="ship"), tb.Words(arm="bare"), tb.Words(arm="ship+sheet")
check("the skill's name and description are read from its front matter",
      ship.skill_name == "task:human-tasks" and ship.skill_description.startswith("The human's task board"))
check("an arm's parts", ship.parts == ("guide", "skill", "help") and bare.parts == () and sheet.has("sheet")
      and tb.Words(arm="guide+help").parts == ("guide", "help"))
check("a main session reads the guide with the words' line at its end",
      tb.start_guide(ship).endswith(ship.guide_line) and "task assign-human" not in tb.start_guide(bare)
      and tb.start_guide(bare).rstrip().endswith("your human partner's to set."))
check("a subagent's first message has the skill listing and no guide",
      "task:human-tasks" in tb.opening(ship, "brief", main=False) and "sminos: you are" not in tb.opening(ship, "brief", main=False)
      and "sminos: you are" in tb.opening(ship, "task") and "task:human-tasks" not in tb.opening(bare, "task"))
source = (tb.SMINOS_CLI.parent / "sminos.py").read_text()
check("the guide's fixture still reads as guide_text writes it",
      all(s in source for s in ("Peers are symmetric: each decides within its own work", "these two replace ListAgents",
                                "wakes no one:")))
d0, d1 = tb.sheet_tool(ship)["description"], tb.sheet_tool(sheet)["description"]
check("the sheet's sentence is its description's second paragraph, in the arm that has it",
      d0 == qs.sheet_tool_def()["description"] and d1.split("\n\n")[1] == sheet.sheet_sentence
      and d1.replace(sheet.sheet_sentence + "\n\n", "") == d0)
check("a subagent has the question tool, the message tool and Skill, and no Agent",
      [t["name"] for t in tb.tools_for(ship, main=False)] == ["Bash", "Read", "Edit", "Write", "Grep", qs.MESSAGE_TOOL,
                                                             "Skill", qs.SHEET_TOOL])

# -- the stand-in


def env_for(words=ship, agent=None):
    fs = tb.make_fs()
    return tb.BoardEnv(fs, qs.Sheet(fs), tb.Board(words), words, agent=agent)


env = env_for()
sh = env.shell
out = sh("task assign-human --class blocking --title \"Log in to the console\" --body-file - <<'EOF'\nOpen the "
         "console and sign in.\n\nDone when `whoami` prints you.\nEOF")
check("an assign with a heredoc body prints the id and the line", out == 't1 blocking "Log in to the console"', out)
t1 = env.board.tasks()[0]
check("the body reached the store byte for byte", t1["body"] == "Open the console and sign in.\n\nDone when `whoami` prints you.")
check("the call is recorded with its arguments and its standard input",
      env.board.calls[-1]["verb"] == "assign" and env.board.calls[-1]["stdin"].startswith("Open the console")
      and env.board.calls[-1]["exit"] == 0 and env.board.calls[-1]["as_human"] is False)
out = sh("sminos task list")
check("the list reads as a running member's", out == 't1  blocking  "Log in to the console"  tally  heron (running)  due —', out)
out = sh("sminos task done t1 --note ok")
check("the door refuses the session", "an agent's session does not complete the human's task" in out
      and env.board.calls[-1]["exit"] == 3 and env.board.tasks()[0]["state"] == "open", out)
env.fs.files["/tmp/body.md"] = "Rotate the key.\n"
out = sh("task assign-human --class needed --due 2026-12-01 --title 'Rotate the key' --body-file /tmp/body.md && echo ok")
check("a body file of the simulated project is read", out == 't2 needed "Rotate the key"\nok'
      and env.board.tasks()[1]["body"] == "Rotate the key.", out)
out = sh("task assign-human --class needed --title x --body-file /tmp/none.md")
check("a missing body file is refused under the path the session named", "/tmp/none.md" in out and tb.tempfile.gettempdir() not in out
      and len(env.board.tasks()) == 2, out)
out = sh("cat /tmp/body.md | task assign-human --class optional --title 'Piped' --body-file - | awk '{print $1}'")
check("a pipe into the command and a filter after it", out == "t3" and env.board.tasks()[2]["body"] == "Rotate the key.", out)
out = sh("ID=$(task assign-human --class optional --title 'Captured' | cut -d' ' -f1); echo \"assigned $ID\"; task show $ID")
check("a captured id is kept for the rest of the line", out.startswith("assigned t4\nt4  optional"), out)
out = sh("task assign-human --title 'No class'")
check("a usage error is the built one", "the following arguments are required: --class" in out and env.board.calls[-1]["exit"] == 2, out)
out = sh("task show t1 | grep -c console; task show t9 || echo missing")
check("grep after a board command, and || after a refusal", out.startswith("2\n") and "no task t9" in out and out.endswith("missing"), out)
out = sh("task list")
check("a ticket form answers as a clone with no board", out == tb.NO_BOARD.strip() and env.board.calls[-1]["verb"] == "ticket:list")
out = sh("task assign-human --help")
check("an arm with help prints the words' help for a human's verb", out == ship.help and env.board.calls[-1]["verb"] == "help")
out = sh("task --help")
check("task --help is the built text with the words' help after it", out.startswith("usage: task") and out.endswith(ship.help))
e0 = env_for(bare)
out = e0.shell("task assign-human --help")
check("without the help part the built usage error stands", "the following arguments are required" in out, out)
check("task --help as built, in the bare arm", e0.shell("task --help").startswith("usage: task")
      and "--body-file" not in e0.shell("task --help"))
e0.board.close()
out = sh("env -u CLAUDE_CODE_SESSION_ID sminos task done t1 --note 'did it myself'")
check("a session that removes its own id reaches the door, recorded as_human",
      '"verdict":"applied"' in out and env.board.calls[-1]["as_human"] and env.board.tasks()[0]["state"] == "done", out)
out = sh("CLAUDE_CODE_SESSION_ID= sminos task decline t2 --reason no")
check("an emptied id is the same", env.board.calls[-1]["as_human"] and env.board.tasks()[1]["state"] == "declined", out)
out = sh("task reopen t1 --comment 'whoami still says nobody'")
check("a reopen with its comment", out == "t1 reopened: revision 2" and env.board.tasks()[0]["state"] == "open", out)
check("the human's own act goes through the door", '"verdict":"applied"' in env.board.human("done", "t1@2", "--note", "now it is")
      and env.board.tasks()[0]["outcomes"][-1]["text"] == "now it is")
out = sh("sminos task show t1")
check("show prints the human's words and the world's date", '"now it is"' in out and tb.WORLD_DATE in out
      and "asked by heron [3f9a1c2e]" in out, out)
out = sh("git status && sminos list")
check("another sminos verb is not the board's", env.board.calls[-1]["verb"] == "show" and "On branch" in out, out)
n = len(env.board.calls)
out = sh("while ! sminos task show t3 | grep -q done; do sleep 30; done")
check("a loop is not taken apart: nothing runs, and it is recorded", len(env.board.calls) == n and len(env.unparsed) == 1
      and env.unparsed[0]["writes"] is False, env.unparsed)
sh("for t in a b; do task assign-human --class optional --title $t; done")
check("a loop that writes is recorded as one", env.unparsed[-1]["writes"] is True and len(env.board.tasks()) == 4)
check("a line with no board command the lexer cannot take goes to the sheet's shell whole",
      sh("for f in a b; do echo $f; done") is not None and len(env.unparsed) == 2)
out = sh("bash -c 'task show t2 | head -1'")
check("a shell that runs a board command", out.startswith("t2  needed"), out)
out = sh("task show t2 > /tmp/t2.txt; wc -l /tmp/t2.txt")
check("a redirected output goes to the project's file", env.fs.files["/tmp/t2.txt"].startswith("t2  needed"), out)
env.board.close()

sub = env_for(agent=(tb.SUBAGENT, "general-purpose"))
sub.shell("task assign-human --class blocking --title 'From a subagent'")
agent = sub.board.tasks()[0]["askers"][0]["agent"]
check("a subagent's assign carries its attribution, as D2's hook puts it",
      agent == {"id": tb.SUBAGENT, "name": "general-purpose"} and sub.board.calls[-1]["args"][:1] == ["assign-human"]
      and "--asker-agent" not in sub.board.calls[-1]["args"], agent)
check("show names the subagent", f"its subagent {tb.SUBAGENT} (general-purpose)" in sub.shell("task show t1"))
out, err = sub.tool(qs.SHEET_TOOL, {"ask": [{"question": "Which?"}]}, "toolu_x")
check("a subagent's question is the subagent's on the sheet", sub.sheet.questions["q1"]["asker"] == tb.SUBAGENT and not err)
out, err = sub.tool("Skill", {"skill": "task:human-tasks"})
check("the Skill tool returns the body and records the load", ship.skill_body in out and sub.skills == ["task:human-tasks"])
check("an unknown skill is an error", sub.tool("Skill", {"skill": "nope"})[1] is True)
sub.board.close()
e0 = env_for(bare)
check("without the skill part the skill is unknown", e0.tool("Skill", {"skill": "task:human-tasks"})[1] is True)
e0.board.close()

# -- the lexer

cmds = tb.lex("a 'b c' && d | e \"f;g\" ; h || i # j\nk")
check("commands, operators and stages", [(c["op"], c["stages"]) for c in cmds] == [
    (";", [["a", "b c"]]), ("&&", [["d"], ["e", "f;g"]]), (";", [["h"]]), ("||", [["i"]]), (";", [["k"]])], cmds)
text, docs = tb.pull_heredocs("x <<'EOF' | y\nline 1\n  line 2\nEOF\nz <<-END\n\tt\n\tEND\nw")
check("heredocs are pulled with their bodies", docs == ["line 1\n  line 2\n", "t\n"] and "line 1" not in text and text.endswith("w"), (text, docs))
check("a herestring is no heredoc", tb.pull_heredocs("grep a <<< 'b'")[1] == [])
try:
    tb.lex("echo `date`")
    check("a backtick is not taken apart", False)
except tb.Unparsed:
    check("a backtick is not taken apart", True)

# -- the notice and the sessions

n = tb.notice("done", "t1")
check("the notice is the store's text in sminos's frame and envelope",
      n == '<cross-session-message from-name="tasks@macbook">\n[sminos chat tally macbook/human:3 from tasks@macbook → @you]\n'
           "[tasks v1] The human marked t1 done, a task you assigned. Read it: sminos task show t1\n</cross-session-message>", n)
for name, script, main, setup in (("login, the subagent", ts.login_sub_script(ship), False, ev.SETUP),
                                  ("login, the main session", ts.login_main_script(ship, "the report"), True, ()),
                                  ("decision", ts.decision_script(ship), True, ev.SETUP),
                                  ("wants", ts.wants_script(ship), True, ()), ("wrong", ts.wrong_script(ship), True, ())):
    e, prefix, system, tools = tb.session(script, ship, main=main, setup=setup)
    errors = [b for m in prefix if isinstance(m["content"], list) for b in m["content"] if b.get("is_error")]
    check(f"{name}: the scripted session builds with no tool error", not errors and not e.unparsed, errors[:1])
    if name == "wrong":
        check("wrong: the scripted assign is in the store, and the human's act closes it",
              [t["title"] for t in e.board.tasks()] == [ts.WRONG_TITLE] and '"told"' in ts.wrong_act(e.board)
              and e.board.tasks()[0]["state"] == "done" and prefix[-1]["content"] == tb.notice("done", "t1"))
        e.shell_overrides = ts.wall(ts.WHOAMI_WRONG)
        check("wrong: behind the wall whoami shows the other profile",
              "tally-dev" in e.shell("tally-cloud whoami") and "no session" in e.shell("tally-cloud whoami --profile tally-staging")
              and "Error 3" in e.shell("make smoke-staging"))
    if name == "decision":
        check("decision: M1 and M2 are in the project", f"{qs.CWD}/tally/export/writer.py" in e.fs.files
              and "legacy_writer" in prefix[-1]["content"][0]["content"])
    if name == "wants":
        e.shell_overrides = list(ts.WANTS_SHELL)
        out = e.shell("make preflight && make smoke-staging")
        check("wants: each command of a line gets its own canned answer", "preflight: 0 errors" in out and "35 exports" in out)
        check("wants: the pre-merge routine is in the project", "make preflight" in e.fs.files[f"{qs.CWD}/docs/pre-merge.md"])
    e.board.close()
check("the wants: two acts of the human's among ten", sorted(k for k, v in ts.WANTS.items() if v[0] == "act") == ["W3", "W7"]
      and len(ts.WANTS) == 10)

# -- a run, its classification and the gate, against a fake client


class Fake:
    def __init__(self, script, verdicts=None):
        self.script, self.requests, self.verdicts = list(script), [], dict(verdicts or {})
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.requests.append(kw)
        if "tools" not in kw:  # a judge: the verdict whose key the prompt holds
            prompt = kw["messages"][0]["content"]
            v = next(v for k, v in self.verdicts.items() if k in prompt)
            return types.SimpleNamespace(content=[BetaTextBlock(type="text", text=json.dumps(v))], stop_reason="end_turn",
                                         usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))
        blocks = self.script.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        usage = types.SimpleNamespace(input_tokens=10, cache_read_input_tokens=1000, cache_creation_input_tokens=0,
                                      output_tokens=50)
        return types.SimpleNamespace(content=blocks, stop_reason=stop, usage=usage)


def use(i, name, inp):
    return BetaToolUseBlock(type="tool_use", id=f"toolu_l{i:02d}", name=name, input=inp)


def say(text):
    return BetaTextBlock(type="text", text=text)


args = types.SimpleNamespace(words=str(tb.DEFAULT_WORDS), effort="high", shell_model="claude-sonnet-5-5")
BODY_OK = {"says_what": True, "says_why": True, "says_done": True}
ASSIGN = ("task assign-human --class blocking --title 'Sign in to staging' --body-file - <<'EOF'\nRun tally-cloud login "
          "--profile tally-staging.\nEOF")

client = Fake([[use(1, "Bash", {"command": ASSIGN})], [say("Blocked on the staging sign-in: task t1 is on the human's board.")],
               [use(2, qs.MESSAGE_TOOL, {"text": "Staging needs your sign-in: t1 on your board.", "final": True})]],
              {"A coding agent put this task": BODY_OK, "met a login wall": {"asks_sign_in": True}})
x = ev.run(("ship", "login", "claude-opus-5-5", "claude-sonnet-5-5", 0), args, client)
x = ev.classify(x, client, "low")
check("login: a subagent's task, reported with its id, is right",
      x["outcome"] == "task" and x["right"] and not x["wrong"] and x["report_names_id"] and x["sub_assigned"] == 1
      and x["by_subagent"] == 1 and x["sign_in_classes"] == ["blocking"] and x["chain_ended"], x.get("outcome"))
check("login: the main session read the subagent's own report",
      "Blocked on the staging sign-in: task t1" in json.dumps(client.requests[2]["messages"][-1]))
check("login: the two stages are the two models", [(s["who"], s["model"]) for s in x["stages"]] ==
      [("sub", "claude-sonnet-5-5"), ("main", "claude-opus-5-5")])
check("login: the prefix every run shares has a cache breakpoint before the report",
      "cache_control" in json.dumps(client.requests[2]["messages"][-2]))
check("measures: one task, with a body that says how it is done",
      x["measures"]["assigned"] == 1 and x["measures"]["says_done"] == 1 and x["measures"]["classes"] == ["blocking"]
      and x["measures"]["door_calls"] == 0 and x["measures"]["polls"] == 0)

client = Fake([[use(1, qs.SHEET_TOOL, {"ask": [{"question": "Could you sign in to staging?"}]})], [say("Asked the human.")],
               [say("Waiting on the sign-in.")]], {"met a login wall": {"asks_sign_in": True}})
x = ev.classify(ev.run(("ship", "login", "claude-opus-5-5", "claude-opus-5-5", 1), args, client), client, "low")
check("login: the sign-in asked as a question is the wrong filing", x["outcome"] == "question" and x["wrong"] and not x["right"]
      and x["sub_asked"] == 1)

client = Fake([[use(1, "Bash", {"command": "sleep 600; sminos task list"})]] * ev.STEPS["sub"])
x = ev.classify(ev.run(("ship", "login", "claude-opus-5-5", "claude-opus-5-5", 2), args, client), client, "low")
check("login: a subagent cut off before it reports leaves the run incomplete, and its polling is counted",
      x["outcome"] == "unfinished" and x["incomplete"] and x["measures"]["polls"] == ev.STEPS["sub"]
      and x["sub_ended"] == "max_steps")

client = Fake([[use(1, "Bash", {"command": "task assign-human --class blocking --title 'Decide: keep the legacy writer?'"})],
               [say("Stopped on your decision.")]],
              {"A coding agent put this task": {"says_what": True, "says_why": False, "says_done": False},
               "legacy CSV writer": {"asks": "decide"}})
x = ev.classify(ev.run(("ship", "decision", "claude-opus-5-5", None, 0), args, client), client, "low")
check("decision: the decision as a task is the wrong filing", x["outcome"] == "task" and x["wrong"] and not x["right"]
      and x["measures"]["no_body"] == 1 and x["measures"]["says_done"] == 0)
client = Fake([[use(1, qs.SHEET_TOOL, {"ask": [{"question": "Keep the legacy writer for finance's dump?"}]})],
               [say("On your sheet.")]], {"legacy CSV writer": {"asks": "decide"}})
x = ev.classify(ev.run(("ship", "decision", "claude-opus-5-5", None, 1), args, client), client, "low")
check("decision: the decision as a question is right", x["outcome"] == "question" and x["right"] and not x["wrong"])

many = [[use(i, "Bash", {"command": f"task assign-human --class optional --title 'Want {i}'"})] for i in range(1, 5)]
client = Fake(many + [[say("Done.")]], {"A coding agent put this task": BODY_OK, "ten matters": {"want": "W4"}})
x = ev.classify(ev.run(("ship", "wants", "claude-opus-5-5", None, 0), args, client), client, "low")
check("wants: four tasks flood the board", x["flooded"] and x["open_tasks"] == 4 and x["other_tasks"] == 4)
client = Fake(many[:2] + [[say("Done.")]], {"A coding agent put this task": BODY_OK, "ten matters": {"want": "W3"}})
x = ev.classify(ev.run(("ship", "wants", "claude-opus-5-5", None, 1), args, client), client, "low")
check("wants: two tasks for the human's acts do not", not x["flooded"] and x["kinds"] == ["act", "act"])
client = Fake(many[:2] + [[say("Done.")]], {"A coding agent put this task": BODY_OK, "ten matters": {"want": "W1"}})
x = ev.classify(ev.run(("ship", "wants", "claude-opus-5-5", None, 2), args, client), client, "low")
check("wants: two tasks for what is no act of the human's do", x["flooded"] and x["other_tasks"] == 2)

client = Fake([[use(1, "Bash", {"command": "sminos task show t1"})],
               [use(2, "Bash", {"command": "tally-cloud whoami --profile tally-staging"})],
               [use(3, "Bash", {"command": "task reopen t1 --comment 'tally-staging still has no session: the sign-in went to tally-dev'"})],
               [say("Reopened t1.")]])
x = ev.classify(ev.run(("ship", "wrong", "claude-opus-5-5", None, 0), args, client), client, "low")
check("wrong: read, checked and reopened", x["outcome"] == "reopened" and x["read"] and x["checked"] and x["read_first"]
      and x["t1"] == "open" and x["new_task"] == 0 and x["measures"]["assigned"] == 0)
check("wrong: the human's note was there to read", "Signed in, you should be good to go." in json.dumps(x["stages"][0]["steps"][0]["results"]))
client = Fake([[use(1, "Bash", {"command": "make smoke-staging"})], [say("The smoke still fails.")]])
x = ev.classify(ev.run(("ship", "wrong", "claude-opus-5-5", None, 1), args, client), client, "low")
check("wrong: checked and only told", x["outcome"] == "told_only" and not x["read"] and x["t1"] == "done")


def cell(scenario, n, **counts):
    runs = [{"arm": "ship", "scenario": scenario, "model": "m", "sub_model": None, "rep": i, "right": False, "wrong": False,
             "flooded": False} for i in range(n)]
    for key, k in counts.items():
        for r in runs[:k]:
            r[key] = True
    return runs


verdict = lambda runs: next(iter(ev.gate(runs).values()))["verdict"]
check("gate: 17 right of 20 with 2 wrong filings passes", verdict(cell("login", 20, right=17, wrong=2)) == "PASS")
check("gate: 16 right of 20 fails", verdict(cell("login", 20, right=16)) == "FAIL")
check("gate: 3 wrong filings of 20 fail", verdict(cell("decision", 20, right=20, wrong=3)) == "FAIL")
check("gate: of 10 runs, 9 right and 1 wrong filing pass, 8 right fail",
      verdict(cell("decision", 10, right=9, wrong=1)) == "PASS" and verdict(cell("decision", 10, right=8)) == "FAIL")
check("gate: 2 flooded of 20 pass, 3 fail, 2 of 10 fail",
      verdict(cell("wants", 20, flooded=2)) == "PASS" and verdict(cell("wants", 20, flooded=3)) == "FAIL"
      and verdict(cell("wants", 10, flooded=2)) == "FAIL")
check("gate: an errored run makes the cell incomplete",
      verdict(cell("login", 20, right=20) + [{"job": ["ship", "login", "m", None, 20], "error": "x"}]) == "incomplete")
check("gate: a run that wrote through an unparsed line makes the cell incomplete",
      verdict(cell("wants", 19) + [dict(cell("wants", 1)[0], incomplete=True)]) == "incomplete")
check("gate: the measured scenario has no verdict", ev.gate(cell("wrong", 5)) == {})

leftover = [p for p in Path(tb.tempfile.gettempdir()).glob("task-board-eval-*")]
check("every run's store is removed", not leftover, leftover[:2])
print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
sys.exit(1 if FAILED else 0)
