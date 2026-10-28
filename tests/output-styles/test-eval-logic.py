#!/usr/bin/env python3
"""The to-human evals' logic, run against a fake client: no model call.

    python3 tests/output-styles/test-eval-logic.py

It drives each eval's run() through scripted responses, then checks what the
requests carried (display "updates", the shipped message tool, the gateway's
Claude Code shape), what each tool call got back, the per-message counts, the
agent-step eval's shell, and its turn endings: a final message ending the
run, the turn-end forms, the closing-text judges and the tool-form histories.
"""
import importlib.util, json, os, re, sys, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("ANTHROPIC_API_KEY", "dry-run")

from anthropic.types.beta import BetaTextBlock, BetaThinkingBlock, BetaToolUseBlock  # noqa: E402
import mid_turn  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, (": " + detail) if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def text(t):
    return BetaTextBlock(type="text", text=t)


def note(t):
    return BetaThinkingBlock(type="thinking", thinking=t, signature="sig")


def use(i, name, inp):
    return BetaToolUseBlock(type="tool_use", id="toolu_%02d" % i, name=name, input=inp)


class FakeClient:
    """Answers turn requests from a script, judge requests by the note's words."""

    def __init__(self, script):
        self.script, self.requests, self.judged, self.judge_requests = list(script), [], [], []
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.turn))
        self.messages = types.SimpleNamespace(create=self.judge)

    def turn(self, **kw):
        if "tools" not in kw:  # a judge: every judge goes through the beta API in the gateway's shape
            return self.judge(**kw)
        self.requests.append(kw)
        content = self.script.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return types.SimpleNamespace(content=content, stop_reason=stop)

    def judge(self, **kw):
        prompt = kw["messages"][0]["content"]
        self.judged.append(prompt)
        self.judge_requests.append(kw)
        inner = lambda tag: prompt.split("<%s>" % tag)[1].split("</%s>" % tag)[0].strip()  # noqa: E731
        if "<note>" in prompt:
            to_human = "you" in inner("note").lower()
            verdict = {"addressed_to_human": to_human, "needs_action_from_human": to_human, "why": "fake"}
        elif "<sent>" in prompt:
            verdict = {"restates": inner("sent").lower() in inner("closing").lower(), "adds_new": False, "why": "fake"}
        elif "refuse" in inner("closing"):
            return types.SimpleNamespace(content=[], stop_reason="refusal")
        else:
            verdict = {"addressed_to_human": "you" in inner("closing").lower(), "why": "fake"}
        return types.SimpleNamespace(content=[text(json.dumps(verdict))], stop_reason="end_turn")


def results_sent(client):
    """The tool results each request after the first carried, by tool-use id."""
    out = {}
    for kw in client.requests[1:]:
        for r in kw["messages"][-1]["content"]:
            out[r["tool_use_id"]] = r["content"]
    return out


# -- mid_turn: the shipped tool and the counts

name, tool_def, result = mid_turn.shipped_message_tool()
check("the shipped tool's name", name == "mcp__to-human__message", name)
check("the shipped tool's description", tool_def["description"] == "Send the human a message.", tool_def["description"])
check("the shipped tool's schema", tool_def["input_schema"] == {"type": "object", "properties": {
    "text": {"type": "string", "description": "The message, in Markdown."},
    "final": {"type": "boolean", "description": "True when this message ends your turn: once it is sent the turn ends, "
              "and you write nothing after it."}}, "required": ["text"]}, json.dumps(tool_def))
check("the shipped tool's result", result == "sent", result)
check("the plugin's made-up answer after a final message", mid_turn.FINAL_ANSWER == "Message sent to the human.", mid_turn.FINAL_ANSWER)
final_call = {"type": "tool_use", "id": "f", "name": mid_turn.MESSAGE_TOOL, "input": {"text": "x", "final": True}}
plain_call = {"type": "tool_use", "id": "p", "name": mid_turn.MESSAGE_TOOL, "input": {"text": "y"}}
bash_call = {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "ls"}}
check("a final ends the turn only among message calls alone", mid_turn.ends_on_final([final_call])
      and mid_turn.ends_on_final([plain_call, final_call]) and not mid_turn.ends_on_final([final_call, bash_call])
      and not mid_turn.ends_on_final([plain_call]) and not mid_turn.ends_on_final(
          [{**final_call, "input": {"text": "x", "final": "true"}}]))
cc = mid_turn.claude_code_system(mid_turn.CC_IDENTITY + " You are an interactive agent.\n# Style")
check("the gateway's shape: the identity line its own first block", cc == [{"type": "text", "text": mid_turn.CC_IDENTITY},
      {"type": "text", "text": "You are an interactive agent.\n# Style"}], json.dumps(cc))
try:
    mid_turn.claude_code_system("You are a helpful assistant.")
    check("a system prompt without the identity line is refused", False)
except SystemExit:
    check("a system prompt without the identity line is refused", True)

steps = [
    {"stop": "tool_use", "blocks": [
        {"type": "progress", "text": "Telling you the dialog needs approving at 14:30.", "judged": {"addressed_to_human": True, "needs_action_from_human": True}},
        {"type": "text", "text": "<message>A</message>"},
        {"type": "tool_use", "id": "t1", "name": mid_turn.MESSAGE_TOOL, "input": {"text": "B"}},
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "git log"}}]},
    {"stop": "tool_use", "blocks": [
        {"type": "progress", "text": "Checking the log next.", "judged": {"addressed_to_human": False, "needs_action_from_human": False}},
        {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "git status"}},
        {"type": "progress", "text": "after the last call: not judged"}]},
    {"stop": "tool_use", "blocks": [{"type": "tool_use", "id": "t4", "name": mid_turn.MESSAGE_TOOL, "input": {"text": "done"}}]},
    {"stop": "end_turn", "blocks": [{"type": "progress", "text": "end"}, {"type": "text", "text": "<message>C</message> and <message>D</message>"}]},
]
c = mid_turn.count_messages(steps)
want = {"mid_span": 1, "mid_span_trailing": 0, "mid_tool": 1, "mid_lost": 1, "mid_lost_action": 1, "notes_judged": 2,
        "judge_errors": 0, "final_span": 2, "final_tool": 1, "cut_off_tool": 0, "tool_calls": 2}
check("the per-message counts", c == want, json.dumps(c))
check("only notes before a tool call are judged", [b["text"] for b in mid_turn.notes_to_judge(steps)] ==
      ["Telling you the dialog needs approving at 14:30.", "Checking the log next."])
out_of_steps = mid_turn.count_messages(steps[:2])
check("a run cut off on a tool call has no final message", out_of_steps["final_span"] == 0 and out_of_steps["final_tool"] == 0
      and out_of_steps["mid_span"] == 1, json.dumps(out_of_steps))
s = mid_turn.shares(mid_turn.add_counts(dict(c), c), 2)
check("the shares", s == {"mid": 6, "lost": 2, "lost_share": 0.333, "final": 6, "final_span_share": 0.667,
                          "cut_off_tool": 0, "tool_calls_per_run": 2.0}, json.dumps(s))
code = [
    {"stop": "tool_use", "blocks": [
        {"type": "text", "text": "The view reads `<message>x</message>` as literal, and so does this:\n```\n<message>y</message>\n```"},
        {"type": "text", "text": "<message>before the call</message>"},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
        {"type": "text", "text": "<message>after the last call</message>"}]},
    {"stop": "end_turn", "blocks": [{"type": "text", "text": "`<message>quoted</message>` and <message>final</message>"}]},
]
c = mid_turn.count_messages(code)
check("spans read as the view reads them, code literal", c["mid_span"] == 2 and c["final_span"] == 1, json.dumps(c))
check("a span after the response's last call is mid-turn, counted apart", c["mid_span_trailing"] == 1, json.dumps(c))
cut = [steps[0], {"stop": "tool_use", "blocks": [{"type": "tool_use", "id": "t9", "name": mid_turn.MESSAGE_TOOL, "input": {"text": "last?"}}]}]
c = mid_turn.count_messages(cut)
check("a lone message call the run stopped after is cut off, neither kind", c["cut_off_tool"] == 1 and c["mid_tool"] == 1
      and c["final_tool"] == 0 and c["tool_calls"] == 2, json.dumps(c))
check("cut-off calls stay out of the shares", mid_turn.shares(c, 1)["mid"] == 3 and mid_turn.shares(c, 1)["final"] == 0)
check("the messages a run delivered, in order", mid_turn.message_texts(steps) == ["A", "B", "done", "C", "D"])
check("the judge prompt keeps f7's wording", mid_turn.JUDGE.startswith("A coding agent works for a human who is away")
      and '{"addressed_to_human": true|false, "needs_action_from_human": true|false, "why": "<one short clause>"}' in mid_turn.JUDGE
      and mid_turn.JUDGE.count("{note}") == 1)

# -- the agent-step eval

step = load("to-human-agent-step-eval")
fake = FakeClient([
    [note("I'll tell you about the keychain dialog first."), use(0, mid_turn.MESSAGE_TOOL, {"text": "Approve the dialog at 14:30."}),
     use(1, "Bash", {"command": "cd /Users/dev/proj && git status && git log --oneline -5 | head -3"})],
    [note("Running the smoke export."), use(2, "Bash", {"command": "make smoke-export"}), use(3, "Bash", {"command": "uname -a"})],
    [use(4, "SendMessage", {"to": step.AGENT, "message": "smoke-export: 3 of 3 passed"})],
    [text("<message>Smoke export passed; the executor has it.</message>")],
])
step.client = fake
x = step.run("variant", "STYLE", "keep_working", 0)
first = fake.requests[0]
check("agent-step: display updates on every request, in the gateway's shape", all(
      r.get("thinking") == {"type": "adaptive", "display": "updates"}
      and r.get("betas") == ["thinking-display-updates-2026-08-18", mid_turn.CC_BETA]
      and r["system"][0] == {"type": "text", "text": mid_turn.CC_IDENTITY} and r["system"][1]["text"].endswith("STYLE")
      for r in fake.requests))
check("agent-step: the shipped tool from the first request", mid_turn.MESSAGE_TOOL_DEF in first["tools"])
check("agent-step: the new scenario reaches the model", step.INCOMING["keep_working"] in first["messages"][-1]["content"])
sent = results_sent(fake)
check("agent-step: the message tool answers sent", sent["toolu_00"] == "sent", sent["toolu_00"])
check("agent-step: a compound git command reads as a working shell", "working tree clean" in sent["toolu_01"]
      and "Merge pull request #48" in sent["toolu_01"], sent["toolu_01"])
check("agent-step: the smoke export answers", "3 of 3 passed" in sent["toolu_02"], sent["toolu_02"])
check("agent-step: another command is neutral", sent["toolu_03"] == "(Bash completed with no output)", sent["toolu_03"])
check("agent-step: each response's blocks in order", [[b["type"] for b in st["blocks"]] for st in x["steps"]] ==
      [["progress", "tool_use", "tool_use"], ["progress", "tool_use", "tool_use"], ["tool_use"], ["text"]])
check("agent-step: the run ends on the turn's end", x["stop"] == "end_turn" and len(fake.requests) == 4)
out = [x, {"arm": "control", "scenario": "keep_working", "rep": 0, "error": "boom"}]
import concurrent.futures as cf  # noqa: E402
with cf.ThreadPoolExecutor(2) as pool:
    n = mid_turn.judge_runs(fake, out, pool)
check("agent-step: both notes judged, the errored run skipped", n == 2 and len(fake.judged) == 2, str(n))
check("judges go in the gateway's shape", all(r["system"] == mid_turn.CC_SYSTEM and r["betas"] == [mid_turn.CC_BETA]
      and r["output_config"] == {"effort": "low"} for r in fake.judge_requests))
counts = step.tally(out)
c = counts[("keep_working", "short", "variant")]
check("agent-step: the tally", c["reached"] == 1 and c["mid_tool"] == 1 and c["mid_lost"] == 1 and c["final_span"] == 1
      and c["tool_calls"] == 1 and c["critical"] == 0, json.dumps(c))
arm = step.by_arm(counts)["variant"]
check("agent-step: the arm's figures", arm["lost_share"] == 0.5 and arm["final_span_share"] == 1.0
      and arm["tool_calls_per_run"] == 1.0, json.dumps(arm))
check("agent-step: each scenario's own history by default", step.DEFAULT_HISTORY == {"milestone3": "silent2", "complete": "reported3"})

# -- the agent-step eval: a final message ends the run, and the turn's end

fake = FakeClient([
    [use(0, mid_turn.MESSAGE_TOOL, {"text": "M2 is merged; nothing needs you.", "final": True})],
    [text("never asked for")],
])
step.client = fake
x = step.run("new", "STYLE", "milestone", 0)
c = mid_turn.count_messages(x["steps"])
check("final: message calls alone, one final, end the run with no request after", len(fake.requests) == 1
      and x["steps"][-1] == {"stop": "end_turn", "synthetic": True, "blocks": [{"type": "text", "text": mid_turn.FINAL_ANSWER}]}
      and x["stop"] == "end_turn", "%d requests" % len(fake.requests))
check("final: the call counts as the final message", c["final_tool"] == 1 and c["cut_off_tool"] == 0 and c["final_span"] == 0, json.dumps(c))
check("final: the synthetic answer is no unsent prose", not step.outcome(x)["unsent_prose"] and step.outcome(x)["reached"])
fake = FakeClient([
    [use(0, mid_turn.MESSAGE_TOOL, {"text": "Fixing it.", "final": True}), use(1, "SendMessage", {"to": step.AGENT, "message": "fix"})],
    [text("Done.")],
])
step.client = fake
x = step.run("new", "STYLE", "late_failure", 0)
e = step.turn_end(x)
check("final: beside another tool's call the turn goes on", len(fake.requests) == 2 and e["form"] == "tool_mixed+close"
      and e["final_mixed"] == 1 and e["closing_text"] == "Done.", json.dumps(e))
fake = FakeClient([[use(i, "Bash", {"command": "git log"})] for i in range(3)])
step.client = fake
x = step.run("new", "STYLE", "late_failure", 0, max_steps=3)
check("max_steps bounds a run, which then counts as cut off", len(fake.requests) == 3 and step.turn_end(x)["form"] == "cut_off")


def call(name, **inp):
    return {"type": "tool_use", "id": "x", "name": name, "input": inp}


def said(t):
    return {"type": "text", "text": t}


M = mid_turn.MESSAGE_TOOL
SYN = {"stop": "end_turn", "synthetic": True, "blocks": [said(mid_turn.FINAL_ANSWER)]}
FORMS = {
    "tool_final": [{"stop": "tool_use", "blocks": [call(M, text="hi", final=True)]}, SYN],
    "tool_no_final+close": [{"stop": "tool_use", "blocks": [call(M, text="hi")]}, {"stop": "end_turn", "blocks": [said("Sent.")]}],
    "span": [{"stop": "end_turn", "blocks": [said("<message>hi</message>")]}],
    "span_after_tool": [{"stop": "tool_use", "blocks": [call(M, text="hi")]},
                        {"stop": "end_turn", "blocks": [said("<message>hi again</message>")]}],
    "tool_mixed+close": [{"stop": "tool_use", "blocks": [call(M, text="hi", final=True), call("SendMessage", to="a", message="m")]},
                         {"stop": "end_turn", "blocks": [said("Done.")]}],
    "mid_only+close": [{"stop": "tool_use", "blocks": [call(M, text="hi"), call("Bash", command="ls")]},
                       {"stop": "tool_use", "blocks": [call("SendMessage", to="a", message="m")]},
                       {"stop": "end_turn", "blocks": [said("Done.")]}],
    "silent": [{"stop": "end_turn", "blocks": [said("Noted.")]}],
    "cut_off": [{"stop": "tool_use", "blocks": [call("Bash", command="ls")]}],
}
got = {want: step.turn_end({"steps": steps, "scenario": "milestone"})["form"] for want, steps in FORMS.items()}
check("turn end: every form read as itself", all(k == v for k, v in got.items()), json.dumps(got))
counts = {k: mid_turn.count_messages(v) for k, v in FORMS.items()}
check("turn end: the counts agree", counts["tool_final"]["final_tool"] == 1 and counts["tool_no_final+close"]["final_tool"] == 1
      and counts["span_after_tool"]["final_span"] == 1 and counts["tool_mixed+close"]["mid_tool"] == 1
      and counts["cut_off"]["final_tool"] == counts["cut_off"]["final_span"] == 0, json.dumps(counts))
e = step.turn_end({"steps": FORMS["tool_no_final+close"], "scenario": "milestone"})
check("turn end: the closing text and the message before it", e["closing_text"] == "Sent." and e["last_message"] == "hi")
e = step.turn_end({"steps": FORMS["tool_final"], "scenario": "milestone"})
check("turn end: a final message has no closing text", e["closing_text"] is None and e["last_message"] == "hi" and e["final_flags"] == [True])
e = step.turn_end({"steps": [{"stop": "tool_use", "blocks": [call(M, text="<message>x</message>")]},
                             {"stop": "end_turn", "blocks": [said("<message>y</message>")]}], "scenario": "milestone"})
check("turn end: tags inside the tool's text and spans are counted", e["tag_in_tool"] == 1 and e["spans"] == 1, json.dumps(e))

fake = FakeClient([])
step.client = fake
ends = []
for scenario, steps in [("milestone", FORMS["tool_no_final+close"]), ("milestone", FORMS["mid_only+close"]),
                        ("milestone", FORMS["tool_final"]), ("routine_peer", FORMS["silent"]), ("milestone", FORMS["silent"])]:
    x = {"steps": steps, "scenario": scenario}
    x["end"] = step.turn_end(x)
    ends.append((scenario, step.judge_end(x), x["end"]))
check("judges: a closing text after a message gets both judges", ends[0][1] == 2 and ends[0][2]["restatement"]["restates"] is False
      and ends[0][2]["addressed"]["addressed_to_human"] is False)
check("judges: a final message and a routine notice get none", ends[2][1] == 0 and ends[3][1] == 0)
check("judges: plain text with no message before it is judged for its address only", ends[4][1] == 1
      and "restatement" not in ends[4][2] and "addressed" in ends[4][2])
x = {"steps": [{"stop": "tool_use", "blocks": [call(M, text="hi")]}, {"stop": "end_turn", "blocks": [said("I told you: hi. refuse")]}],
     "scenario": "milestone"}
x["end"] = step.turn_end(x)
step.judge_end(x)
check("judges: a restatement read, a refusal kept as an error", x["end"]["restatement"]["restates"] is True
      and "error" in x["end"]["addressed"], json.dumps(x["end"]))
x["arm"] = "v2"
forms = step.final_forms([x, {"arm": "v2", "scenario": "routine_peer", "steps": FORMS["silent"],
                              "end": step.turn_end({"steps": FORMS["silent"]})}])["v2"]
check("judges: the arm's figures", forms["forms"] == {"tool_no_final+close": 1, "silent": 1} and forms["restates"] == 1
      and forms["judge_errors"] == 1 and forms["closing_after_message"] == 1 and forms["routine_runs"] == 1
      and forms["routine_noise"] == 0, json.dumps(forms))

opening = step.tool_form(step.HISTORIES["short"])
check("tool form: the opening's message becomes a final call, its result and the made-up answer",
      [m["role"] for m in opening[-3:]] == ["assistant", "user", "assistant"]
      and opening[-3]["content"][0]["input"] == {"text": step.OPENING[-1]["content"][0]["text"].removeprefix("<message>\n")
                                                 .removesuffix("\n</message>"), "final": True}
      and opening[-2]["content"][0]["content"] == "sent" and opening[-1]["content"][0]["text"] == mid_turn.FINAL_ANSWER)
calls_in = lambda h: sum(b.get("name") == M for m in h if isinstance(m["content"], list) for b in m["content"])  # noqa: E731
check("tool form: every message converted, unsent prose kept", calls_in(step.tool_form(step.HISTORIES["silent2"])) == 1
      and calls_in(step.tool_form(step.HISTORIES["reported3"])) == 2
      and not any("<message>" in json.dumps(m) for m in step.tool_form(step.HISTORIES["reported3"]))
      and "M1 is merged and M2 is under way, as planned." in json.dumps(step.tool_form(step.HISTORIES["silent2"])))
fake = FakeClient([[text("Noted.")]])
step.client = fake
step.run("new", "STYLE", "milestone", 0, tool_history=True)
check("tool form: the run sends it", calls_in(fake.requests[0]["messages"]) == 1
      and not any("<message>" in json.dumps(m) for m in fake.requests[0]["messages"]))
check("plan: reps from the first, each scenario's own history", step.plan(["v2"], ["milestone3", "ruling"], 2, first_rep=1) ==
      [("v2", "milestone3", 1, "silent2"), ("v2", "milestone3", 2, "silent2"), ("v2", "ruling", 1, "short"), ("v2", "ruling", 2, "short")])
check("plan: named histories", step.plan(["a", "b"], ["ruling"], 1, histories=["long"]) == [("a", "ruling", 0, "long"), ("b", "ruling", 0, "long")])

shell = step.shell
check("shell: git log follows the scenario", "#50" in shell("git log --oneline", 4) and "#48" not in shell("git log --oneline", 1))
check("shell: git log in full", shell("git log -3", 2).startswith("commit 9c04e1a") and "Author: Dev" in shell("git log -3", 2))
check("shell: the spec reads", "four milestones" in shell("cat docs/specs/2026-10-20-csv-export.md", 2).lower()
      or "Four milestones" in shell("cat docs/specs/2026-10-20-csv-export.md", 2))
check("shell: TECH-DEBT.md reads", "minor" in shell("head -20 TECH-DEBT.md", 2))
check("shell: sed -n on a file", "Four milestones" in shell("sed -n '1,40p' docs/specs/2026-10-20-csv-export.md", 2),
      shell("sed -n '1,40p' docs/specs/2026-10-20-csv-export.md", 2))
check("shell: gh pr view", "MERGED" in shell("gh pr view 48", 2))
check("shell: hostname and date", shell("hostname; date", 2).startswith("macbook\nTue Oct 20"))
check("shell: a command that prints nothing", shell("sleep 5", 2) == "(Bash completed with no output)")
check("shell: keep_working's clock is before its window", step.canned(types.SimpleNamespace(
    name="Bash", input={"command": "date"}), "keep_working") == "Tue Oct 20 14:05:31 UTC 2026"
      and "14:30 UTC" in step.INCOMING["keep_working"] and "between 14:30 and 14:40 UTC" in step.INCOMING["keep_working"])
dates = re.findall(r"Date:\s+\w+ \w+ \d+ (\d\d:\d\d):", step.canned(types.SimpleNamespace(
    name="Bash", input={"command": "git log -5"}), "keep_working"))
check("shell: keep_working's commits come before its clock", dates and all(d < "14:05" for d in dates), str(dates))
check("shell: the other scenarios' clock", step.canned(types.SimpleNamespace(name="Bash", input={"command": "date"}), "milestone")
      == "Tue Oct 20 16:42:07 UTC 2026")
check("shell: an unclosed quote", shell("grep -rn 'oops src", 2) == "(Bash completed with no output)")
check("shell: echo prints", shell("echo done && git branch", 2) == "done\n* main")

# -- the fan-out eval

fan = load("to-human-fanout-eval")
fake = FakeClient([
    [note("You should know I'm about to run 1,230 haiku calls."), use(0, mid_turn.MESSAGE_TOOL, {"text": "Launching 1,230 claude-haiku-5-5 calls at medium."}),
     use(1, "mcp__plugin_ptc_ptc__exec", {"code": "res = await asyncio.gather(*[llm(PROMPT + read(f), model='claude-haiku-5-5', effort='medium') for f in files[10:]])"})],
    [text("<message>Launched; I'll write the report when it lands.</message>")],
])
fan.client = fake
x = fan.run("variant", "STYLE", "ptc_llm", 0)
check("fanout: display updates and the shipped tool", fake.requests[0].get("thinking", {}).get("display") == "updates"
      and mid_turn.MESSAGE_TOOL_DEF in fake.requests[0]["tools"])
sent = results_sent(fake)
check("fanout: the message tool answers sent and is no launch", sent["toolu_00"] == "sent"
      and sent["toolu_01"] == "(cell running in the background)", json.dumps(sent))
check("fanout: the launch is marked", x["outcome"] == "launched" and x["steps"][0]["blocks"][2].get("launch") is True)
before, notes, after = fan.split_messages(x)
check("fanout: the tool's message is before the launch", before == ["Launching 1,230 claude-haiku-5-5 calls at medium."]
      and notes == ["You should know I'm about to run 1,230 haiku calls."] and after == ["Launched; I'll write the report when it lands."])
with cf.ThreadPoolExecutor(2) as pool:
    fan_out = [x]
    mid_turn.judge_runs(fake, fan_out, pool)
fan_out[0]["judged"] = {"announces_run": True, "models": True, "efforts": True, "count": True, "purpose": False}
c = fan.tally(fan_out)[("ptc_llm", "variant")]
check("fanout: the tally", c["tool_message"] == 1 and c["text_message"] == 0 and c["mid_tool"] == 1 and c["mid_lost"] == 1
      and c["final_span"] == 1 and c["announces_run"] == 1, json.dumps(c))
check("fanout: the arm's figures", fan.by_arm(fan.tally(fan_out))["variant"]["lost_share"] == 0.5)

LAUNCH = {"code": "res = await asyncio.gather(*[llm(PROMPT + read(f), model='claude-haiku-5-5', effort='medium') for f in files[10:]])"}
fake = FakeClient([
    [use(0, "mcp__plugin_ptc_ptc__exec", LAUNCH)],
    [use(1, mid_turn.MESSAGE_TOOL, {"text": "Launched 1,230 haiku calls; the report follows when they land."})],
    [text("")],
])
fan.client = fake
x = fan.run("variant", "STYLE", "ptc_llm", 0)
c = mid_turn.count_messages(x["steps"])
check("fanout: a lone message call after the launch runs on to the turn's end", len(fake.requests) == 3
      and c["final_tool"] == 1 and c["mid_tool"] == 0 and c["cut_off_tool"] == 0, json.dumps(c))
fake = FakeClient([[use(0, "mcp__plugin_ptc_ptc__exec", LAUNCH)]] +
                  [[use(i, mid_turn.MESSAGE_TOOL, {"text": "again %d" % i})] for i in range(1, 9)])
fan.client = fake
x = fan.run("variant", "STYLE", "ptc_llm", 0)
c = mid_turn.count_messages(x["steps"])
check("fanout: the continuation is bounded, and a run still cut off says so", len(fake.requests) == 2 + fan.SETTLE
      and c["cut_off_tool"] == 1 and c["mid_tool"] == fan.SETTLE and c["final_tool"] == 0, "%d requests, %s" % (len(fake.requests), json.dumps(c)))
fake = FakeClient([[use(i, "Bash", {"command": "ls"})] for i in range(3)] + [[use(3, mid_turn.MESSAGE_TOOL, {"text": "x"})]]
                  + [[use(4, mid_turn.MESSAGE_TOOL, {"text": "y"})], [text("<message>z</message>")]])
fan.client = fake
x = fan.run("variant", "STYLE", "smoke", 0)
c = mid_turn.count_messages(x["steps"])
check("fanout: the step budget settles a lone message call too", len(fake.requests) == 6 and x["outcome"] == "ended_turn"
      and c["final_span"] == 1 and c["final_tool"] == 1 and c["mid_tool"] == 1 and c["cut_off_tool"] == 0, "%d requests, %s" % (len(fake.requests), json.dumps(c)))

print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
sys.exit(1 if FAILED else 0)
