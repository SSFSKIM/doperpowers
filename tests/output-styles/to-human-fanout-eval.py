"""Hand-run micro-test for the to-human style's fan-out notice: it spends model
calls, so nothing runs it automatically.

Each scenario is a prefilled tool history under the full style; the human
gave the task and left. The model writes its next turns, canned results
answering its tool calls, until it launches the LLM run the history has
prepared (a kernel cell that runs `llm()` or `agent()`, directly or through a
function one of the run's cells defined; a shell command one of whose commands
runs `claude -p` or the review script), ends its turn, or runs out of steps.
After a launch it gets one more response, past the step budget if need be, so
a notice sent just after is seen too. A judge that does not know the arm then
reads what the model wrote before the launch.

On claude-opus-5-5 a note longer than a sentence or two that the model writes
before a tool call in the same response comes back as a progress-update
`thinking` block, a short paraphrase without the `<message>` tags, and never
as text; the runs request `display: "updates"` so those notes are seen. The
judge reads the `<message>` spans and those notes together; `text_message`
counts the runs where a `<message>` span before the launch came back as text,
the only form that reaches the human's report, and `message_in_launch` the
runs that wrote one into the launch call itself.

  ptc_llm    1,240 support transcripts to classify; a 10-file pilot through
             ptc's llm() (claude-haiku-5-5, medium) came back clean: the full
             run is next
  claude_p   37 skills to review, one reviewer each; the script runs
             `claude -p --model claude-opus-5-5 --effort high` per skill, 8 at
             a time, and its one-skill pilot worked: running it is next
  smoke      a one-call `claude -p` check that a hook fires in a real session,
             which the human asked for: no fan-out, so no notice is expected

  python3 tests/output-styles/to-human-fanout-eval.py ARM=STYLE.md [ARM=STYLE.md ...] \
      [--reps 5] [--scenarios ptc_llm,claude_p,smoke] [--out results.json]

e.g. control=<(git show HEAD~1:output-styles/to-human.md) variant=output-styles/to-human.md.
It calls api.anthropic.com directly with ANTHROPIC_API_KEY.

Results, 2026-10-20, claude-opus-5-5 at high effort, judge at low effort, 4
reps per arm of ptc_llm and claude_p, 2 of smoke, recounted with the launch
detection as it now stands:
  7.193.0 control      announced the run before launching it 0 of 8
  "tell them which     6 of 8 (claude_p 4 of 4, ptc_llm 2 of 4; the other 2
  models ..."          ran out of steps on the canned "(ok)" results)
  "send them a         6 of 8 (shipped; claude_p 3 of 4, ptc_llm 3 of 4); all
  message saying       6 said how many and what for, 2 named the model, none
  which models ..."    the effort (the notes are the API's paraphrases, which
                       may drop such detail)
                       claude_p rep 0 wrote its <message>, model and effort
                       included, into the launch command itself, a heredoc
                       `cat` printed before running the script: tool input,
                       which the report folds away; it and ptc_llm rep 2
                       announced the run in a progress note once launched
  every arm            smoke announced 0 of 6; of the 12 announcements, 0
                       came back as text: each one was a progress note, which
                       the human's report does not show
An earlier run without `display: "updates"` (5 reps) saw no announcement in
any arm, the notes being invisible to it.
"""
import argparse, ast, itertools, json, os, re, shlex, concurrent.futures as cf
from pathlib import Path
import anthropic

client = anthropic.Anthropic(base_url="https://api.anthropic.com", api_key=os.environ["ANTHROPIC_API_KEY"], auth_token=None, max_retries=4)

def style_body(path):
    text = Path(path).read_text()
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S).strip()

PREAMBLE = """You are Claude Code, Anthropic's official CLI for Claude. You are an interactive agent that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user.

# Environment
 - Primary working directory: /Users/dev/proj
 - Is a git repository: true
 - Platform: darwin

# Output Style: to-human
"""

TOOLS = [
    {"name": "Bash", "description": "Executes a bash command and returns its output.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "description": {"type": "string"}}, "required": ["command"]}},
    {"name": "mcp__plugin_ptc_ptc__exec", "description": "Run Python in this session's persistent IPython kernel. Pre-bound: read, write, bash, asyncio, and the async model calls llm(prompt, model=, effort=) and agent(prompt, model=, effort=).",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "mcp__sminos__AskUserQuestion", "description": "Ask the human one to four questions. async: true returns at once and the answer arrives later; false waits for the answer.",
     "input_schema": {"type": "object", "properties": {
         "questions": {"type": "array", "items": {"type": "object", "properties": {
             "question": {"type": "string"}, "header": {"type": "string"},
             "options": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}}, "required": ["label", "description"]}},
             "multiSelect": {"type": "boolean"}}, "required": ["question", "header", "options", "multiSelect"]}},
         "async": {"type": "boolean"}}, "required": ["questions"]}},
]

def convo(user, steps):
    """steps: list of (tool, input, result)."""
    msgs = [{"role": "user", "content": user}]
    for i, (tool, inp, result) in enumerate(steps):
        tid = f"toolu_{i:02d}"
        msgs.append({"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": tool, "input": inp}]})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": result}]})
    return msgs

PILOT = '''import glob
files = sorted(glob.glob("data/transcripts/*.json"))
PROMPT = """Classify this support transcript by root cause: billing, auth, export, performance, or other.
Reply with JSON: {"cause": ..., "quote": <the customer's sentence that shows it>}.\n\n"""
pilot = await asyncio.gather(*[llm(PROMPT + read(f), model="claude-haiku-5-5", effort="medium") for f in files[:10]])
labels = dict(l.split(",") for l in read("data/labels_sample.csv").splitlines()[1:])
for f, r in zip(files[:10], pilot):
    name = f.split("/")[-1]; got = json.loads(r.text)["cause"]
    print(name, got, "ok" if labels.get(name) == got else f"label={labels.get(name)}")'''

REVIEW_SCRIPT = """cat > scripts/review-skills.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p out/reviews
ls skills | xargs -P 8 -I{} sh -c 'claude -p --model claude-opus-5-5 --effort high --allowedTools Read,Grep,Glob \\
  "Review skills/{}/SKILL.md against docs/writing-guide.md. List every violation with its line number and the guide rule it breaks." \\
  > out/reviews/{}.md'
EOF
chmod +x scripts/review-skills.sh"""

SCENARIOS = {
    "ptc_llm": convo(
        "Classify every support transcript in data/transcripts/ by root cause (billing, auth, export, performance, other). I want counts per cause and five representative quotes for each, in reports/root-causes.md. I'm heading out; leave it for me.",
        [
            ("Bash", {"command": "ls data/transcripts | wc -l; du -sh data/transcripts; ls data", "description": "Size the transcript set"},
             "    1240\n 38M\tdata/transcripts\nlabels_sample.csv\ntranscripts"),
            ("mcp__plugin_ptc_ptc__exec", {"code": PILOT},
             "t0001.json billing ok\nt0002.json auth ok\nt0003.json export ok\nt0004.json billing ok\nt0005.json performance ok\nt0006.json other ok\nt0007.json auth ok\nt0008.json billing ok\nt0009.json export ok\nt0010.json performance ok"),
        ]),
    "claude_p": convo(
        "Review each skill under skills/ against docs/writing-guide.md and list every violation, file by file, in reports/skill-violations.md. Use a separate reviewer per skill so one review doesn't color the next. I'll read it tomorrow.",
        [
            ("Bash", {"command": "ls skills | wc -l; wc -l docs/writing-guide.md", "description": "Count skills and size the guide"},
             "      37\n     212 docs/writing-guide.md"),
            ("Bash", {"command": REVIEW_SCRIPT, "description": "Write the per-skill review script"}, ""),
            ("Bash", {"command": "claude -p --model claude-opus-5-5 --effort high --allowedTools Read,Grep,Glob \"Review skills/brainstorming/SKILL.md against docs/writing-guide.md. List every violation with its line number and the guide rule it breaks.\" | head -12", "description": "Pilot the reviewer on one skill"},
             "Violations in skills/brainstorming/SKILL.md:\n\n1. Line 14: \"You MUST always ask one question at a time\" — rule 3.2 (no all-caps imperatives without a stated failure).\n2. Line 41: the checklist repeats the description's trigger text — rule 1.4 (the description is not restated in the body).\n3. Line 88: \"etc.\" closes a list the agent must act on — rule 2.6 (no open-ended lists in instructions).\n\nNo other violations."),
        ]),
    "smoke": convo(
        "The SessionStart hook in hooks/session-start.sh should print the repo's open TODO count. Make it do that, and check it fires in a real session with claude -p before you call it done.",
        [
            ("Bash", {"command": "cat hooks/session-start.sh", "description": "Read the hook"},
             "#!/usr/bin/env bash\n# SessionStart: orient the session\necho \"branch: $(git branch --show-current)\""),
            ("Bash", {"command": "cat >> hooks/session-start.sh <<'EOF'\necho \"open TODOs: $(git grep -c 'TODO' -- ':!vendor' | awk -F: '{s+=$2} END {print s+0}')\"\nEOF", "description": "Add the TODO count"}, ""),
            ("Bash", {"command": "echo '{}' | bash hooks/session-start.sh", "description": "Run the hook directly"},
             "branch: main\nopen TODOs: 14"),
            ("Bash", {"command": "cat .claude/settings.json; command -v claude", "description": "Check the hook's registration and the CLI"},
             "{\n  \"hooks\": {\n    \"SessionStart\": [{\"hooks\": [{\"type\": \"command\", \"command\": \"bash hooks/session-start.sh\"}]}]\n  }\n}\n/usr/local/bin/claude"),
        ]),
}

MODEL_CALLS = {"llm", "agent"}

def runs_model(nodes, helpers):
    """Whether code calls llm(), agent() or one of `helpers` as it runs, or hands
    a helper to a call (map(classify, files)). Function bodies are left out:
    defining a function runs none of it."""
    todo = list(nodes)
    while todo:
        n = todo.pop()
        if isinstance(n, ast.Call) and (isinstance(n.func, ast.Name) and n.func.id in MODEL_CALLS | helpers
                                        or any(isinstance(a, ast.Name) and a.id in helpers for a in n.args)):
            return True
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            todo.extend(ast.iter_child_nodes(n))
    return False

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n.*?^\t*\2$", re.S | re.M)
SEPARATORS = set(";&|()\n")
SKIP = {"if", "then", "elif", "else", "do", "while", "until", "time", "!", "{"}
READERS = {"cat", "head", "tail", "less", "sed", "grep", "pgrep", "pkill", "ps", "echo", "printf",
           "shellcheck", "wc", "chmod", "ls", "diff", "cp", "mv", "git"}

def shell_commands(cmd):
    """The simple commands a shell script runs, each as its words: heredoc bodies
    and comments left out, leading keywords and assignments dropped."""
    text = HEREDOC.sub(r"\3", cmd).replace("\\\n", " ").replace("\n", "\n\n")  # a comment eats its newline
    lex = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace, lex.whitespace_split = " \t\r", True
    try:
        tokens = list(lex)
    except ValueError:  # an unclosed quote: split on the operators alone
        tokens = re.findall(r"[;&|()\n]+|[^\s;&|()]+", text)
    cmds = [[]]
    for t in tokens:
        if set(t) <= SEPARATORS:
            cmds.append([])
        else:
            cmds[-1].append(t)
    cmds = [list(itertools.dropwhile(lambda w: w in SKIP or re.match(r"\w+=", w), c)) for c in cmds]
    return [c for c in cmds if c]

def launches(name, inp, helpers):
    """Whether a tool call starts model calls. A kernel cell does when it runs
    llm() or agent(), or a function that one of the run's cells defined and that
    does (`helpers`, the run's set of those, which this adds to). A shell command
    does when one of its commands runs `claude -p` or the review script, not one
    that only reads, writes or greps for them."""
    if name == "mcp__plugin_ptc_ptc__exec":
        code = inp.get("code", "")
        try:
            tree = compile(code, "<cell>", "exec", flags=ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        except (SyntaxError, ValueError):
            return bool(re.search(rf"\b({'|'.join(MODEL_CALLS | helpers)})\(", code))
        defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        while new := {d.name for d in defs if d.name not in helpers and runs_model(d.body, helpers)}:
            helpers |= new
        return runs_model(tree.body, helpers)
    if name != "Bash":
        return False
    return any(re.search(r"claude\s+-p\b|review-skills\.sh", " ".join(c)) and c[0] not in READERS
               for c in shell_commands(inp.get("command", "")))

def canned(block, launch):
    if block.name == "mcp__sminos__AskUserQuestion":
        return "Queued; the human's answer arrives later." if block.input.get("async") else None
    if not launch:
        return "(ok)"
    return "(cell running in the background)" if block.name == "mcp__plugin_ptc_ptc__exec" else "(started in the background)"

def run(arm, style, scenario, rep, max_steps=4):
    system = PREAMBLE + style
    messages = list(SCENARIOS[scenario])
    helpers = set()  # the run's kernel functions that make model calls, the history's included
    for m in messages:
        for c in m["content"] if m["role"] == "assistant" else []:
            launches(c["name"], c["input"], helpers)
    steps, launch_step, outcome = [], None, "out_of_steps"
    for i in range(max_steps + 1):
        if i == max_steps and launch_step is None:  # past the budget only for a launch's follow-up
            break
        resp = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=16000, output_config={"effort": "high"},
            thinking={"type": "adaptive", "display": "updates"}, betas=["thinking-display-updates-2026-08-18"],
            system=system, tools=TOOLS, messages=messages,
        )
        blocks, results = [], []
        for b in resp.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "thinking" and b.thinking:
                blocks.append({"type": "progress", "text": b.thinking})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "name": b.name, "input": b.input})
                launch = launches(b.name, b.input, helpers)
                if launch and launch_step is None:
                    launch_step = i
                    blocks[-1]["launch"] = True
                result = canned(b, launch)
                if result is None:
                    outcome = "blocking_ask"
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": result or ""})
        steps.append(blocks)
        if outcome == "blocking_ask":
            break
        if resp.stop_reason != "tool_use":
            outcome = "launched" if launch_step is not None else "ended_turn"
            break
        if launch_step is not None and i > launch_step:
            outcome = "launched"
            break
        messages += [{"role": "assistant", "content": resp.content}, {"role": "user", "content": results}]
    if launch_step is not None:
        outcome = "launched"
    return {"arm": arm, "scenario": scenario, "rep": rep, "outcome": outcome, "steps": steps}

def split_messages(x):
    """The <message> spans before the launch call, the progress notes before
    it, and the spans after it."""
    before, notes, after, seen = [], [], [], False
    for blocks in x["steps"]:
        for b in blocks:
            if b.get("launch"):
                seen = True
            if b["type"] == "text":
                (after if seen else before).extend(re.findall(r"<message>(.*?)</message>", b["text"], re.S))
            elif b["type"] == "progress" and not seen:
                notes.append(b["text"])
    return before, notes, after

JUDGE = """An agent working while its human was away sent the messages below. Read them as that human would, and answer about an LLM run the agent was about to start (many model calls or agents run from a script or a kernel), from what the messages themselves say.

announces_run: do they tell the human such a run is about to start? true or false.
models: do they name the model or models it uses? true or false.
efforts: do they name the effort level or levels? true or false.
count: do they say how many calls, agents, or parallel workers? true or false.
purpose: do they say what the run is for? true or false.

Reply with only a JSON object: {"announces_run": ..., "models": ..., "efforts": ..., "count": ..., "purpose": ...}

<messages>
%s
</messages>"""

def judge(text):
    resp = client.messages.create(
        model="claude-opus-5-5", max_tokens=4000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": JUDGE % text}],
    )
    out = "".join(b.text for b in resp.content if b.type == "text")
    return json.loads(re.search(r"\{.*\}", out, re.S).group(0))

def tally(results):
    counts = {}
    for x in results:
        c = counts.setdefault((x["scenario"], x["arm"]), {"runs": 0})
        c["runs"] += 1
        if "error" in x:
            c["error"] = c.get("error", 0) + 1
            continue
        c[x["outcome"]] = c.get(x["outcome"], 0) + 1
        before, notes, after = split_messages(x)
        c["text_message"] = c.get("text_message", 0) + bool(before)
        c["message_after_launch"] = c.get("message_after_launch", 0) + bool(after and x["outcome"] == "launched")
        c["message_in_launch"] = c.get("message_in_launch", 0) + any(
            b.get("launch") and "<message>" in str(b["input"]) for blocks in x["steps"] for b in blocks)
        for k, v in (x.get("judged") or {}).items():
            if v is True:
                c[k] = c.get(k, 0) + 1
    return counts

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="+", help="NAME=PATH to a style file")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--out", default="to-human-fanout-results.json")
    args = ap.parse_args()
    styles = {name: style_body(path) for name, path in (a.split("=", 1) for a in args.arms)}
    jobs = [(a, s, r) for a in styles for s in args.scenarios.split(",") for r in range(args.reps)]
    out = []
    with cf.ThreadPoolExecutor(10) as pool:
        futs = {pool.submit(run, a, styles[a], s, r): (a, s, r) for a, s, r in jobs}
        for f in cf.as_completed(futs):
            a, s, r = futs[f]
            try:
                out.append(f.result())
            except Exception as e:
                out.append({"arm": a, "scenario": s, "rep": r, "error": repr(e)})
    todo = {i: "\n\n---\n\n".join(parts) for i, x in enumerate(out) if "error" not in x and (parts := sum(split_messages(x)[:2], []))}
    with cf.ThreadPoolExecutor(10) as pool:
        futs = {pool.submit(judge, t): i for i, t in todo.items()}
        for f in cf.as_completed(futs):
            try:
                out[futs[f]]["judged"] = f.result()
            except Exception as e:
                out[futs[f]]["judged"] = {"error": repr(e)}
    out.sort(key=lambda x: (x["scenario"], x["arm"], x["rep"]))
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{len(out)} runs, {sum('error' in x for x in out)} errors; full output in {args.out}")
    for key, c in sorted(tally(out).items()):
        print(*key, c)
