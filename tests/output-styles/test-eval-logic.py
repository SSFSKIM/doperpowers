#!/usr/bin/env python3
"""The to-human evals' logic, run against a fake client: no model call.

    python3 tests/output-styles/test-eval-logic.py

It drives each eval's run() through scripted responses, then checks what the
requests carried (display "updates", the shipped message tool), what each
tool call got back, the per-message counts, and the agent-step eval's shell.
"""
import importlib.util, json, os, sys, types
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
        self.script, self.requests, self.judged = list(script), [], []
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.turn))
        self.messages = types.SimpleNamespace(create=self.judge)

    def turn(self, **kw):
        self.requests.append(kw)
        content = self.script.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return types.SimpleNamespace(content=content, stop_reason=stop)

    def judge(self, **kw):
        prompt = kw["messages"][0]["content"]
        self.judged.append(prompt)
        to_human = "you" in prompt.split("<note>")[1].split("</note>")[0].lower()
        return types.SimpleNamespace(content=[text(json.dumps(
            {"addressed_to_human": to_human, "needs_action_from_human": to_human, "why": "fake"}))])


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
check("the shipped tool's schema", tool_def["input_schema"] == {"type": "object", "properties": {"text": {
    "type": "string", "description": "The message, in Markdown."}}, "required": ["text"]}, json.dumps(tool_def))
check("the shipped tool's result", result == "sent", result)

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
want = {"mid_span": 1, "mid_tool": 1, "mid_lost": 1, "mid_lost_action": 1, "notes_judged": 2, "judge_errors": 0,
        "final_span": 2, "final_tool": 1, "tool_calls": 2}
check("the per-message counts", c == want, json.dumps(c))
check("only notes before a tool call are judged", [b["text"] for b in mid_turn.notes_to_judge(steps)] ==
      ["Telling you the dialog needs approving at 14:30.", "Checking the log next."])
out_of_steps = mid_turn.count_messages(steps[:2])
check("a run cut off on a tool call has no final message", out_of_steps["final_span"] == 0 and out_of_steps["final_tool"] == 0
      and out_of_steps["mid_span"] == 1, json.dumps(out_of_steps))
s = mid_turn.shares(mid_turn.add_counts(dict(c), c), 2)
check("the shares", s == {"mid": 6, "lost": 2, "lost_share": 0.333, "final": 6, "final_span_share": 0.667,
                          "tool_calls_per_run": 2.0}, json.dumps(s))
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
check("agent-step: display updates on every request", all(r.get("thinking") == {"type": "adaptive", "display": "updates"}
      and r.get("betas") == ["thinking-display-updates-2026-08-18"] for r in fake.requests))
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
counts = step.tally(out)
c = counts[("keep_working", "short", "variant")]
check("agent-step: the tally", c["reached"] == 1 and c["mid_tool"] == 1 and c["mid_lost"] == 1 and c["final_span"] == 1
      and c["tool_calls"] == 1 and c["critical"] == 0, json.dumps(c))
arm = step.by_arm(counts)["variant"]
check("agent-step: the arm's figures", arm["lost_share"] == 0.5 and arm["final_span_share"] == 1.0
      and arm["tool_calls_per_run"] == 1.0, json.dumps(arm))
check("agent-step: each scenario's own history by default", step.DEFAULT_HISTORY == {"milestone3": "silent2", "complete": "reported3"})

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

print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
sys.exit(1 if FAILED else 0)
