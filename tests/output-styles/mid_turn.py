"""What the to-human evals share for counting messages one by one: the message
tool as it ships, the judge of progress notes, and the per-message counts.

On claude-opus-5-5 a note longer than a sentence or two written before a tool
call in the same response comes back as a progress-update `thinking` block (a
paraphrase without its `<message>` tags), visible only with `display:
"updates"`. A run is kept as its responses in order, each
`{"stop": <stop_reason>, "blocks": [...]}` with blocks of type `text`,
`progress` (a non-empty thinking block) and `tool_use`, so where each message
went can be read back.

  mid-turn message  in a response that calls a tool: a `<message>` span in a
                    text block before one of its calls (delivered), a call of
                    the message tool (delivered), or a progress note before
                    one of its calls that the judge rules addressed to the
                    human (lost). A span in a text block after the response's
                    last call is mid-turn too, since the turn goes on past
                    it, and delivered, since it came back as text; it is also
                    counted apart (`mid_span_trailing`), being rare.
  final message     a span in the response that ends the turn (no tool call),
                    or a message-tool call in a response that calls nothing
                    else and is followed by that one (the tool used for the
                    turn's last word). A response of message calls alone, one
                    of them `final: true`, ends the turn live: the plugin
                    answers the next step itself with FINAL_ANSWER and no
                    request; an eval that replays this keeps that made-up
                    answer as a last step marked `synthetic`, so the calls
                    count as final here
  cut off           a message-tool call in the run's last response when that
                    response calls nothing else and the run stopped before
                    the next: it could be either kind, so it is counted as
                    neither (`cut_off_tool`)

Spans are read as the to-human view reads them (sminos_marks.parse, the port
of the view's grammar): a tag inside inline code or a fenced block is
literal, and an unclosed mark runs to the end of the text.

The model is reached through the local gateway (`gateway_client`): the
stored ANTHROPIC_API_KEY has no credit. The gateway answers a Claude model
only for a request shaped as Claude Code's, its first system block the
identity line (`CC_SYSTEM`, `claude_code_system`) and the `claude-code` beta
(`CC_BETA`); anything else gets `429 rate_limit_error`. Every judge here
sends that shape, whichever client an eval passes.

Design: docs/doperpowers/specs/2026-10-20-to-human-message-tool-design.md
(acceptance 6).
"""
import json, os, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MESSAGE_TSX = REPO / "to-human" / "hooks" / "mods" / "message.tsx"
sys.path.insert(0, str(REPO / "sminos" / "skills" / "sminos" / "scripts"))
import sminos_marks  # noqa: E402


def _const(src, name):
    m = re.search(r"export const %s = '((?:[^'\\]|\\.)*)'" % name, src)
    if m is None:
        raise SystemExit("mid_turn: %s not found in %s" % (name, MESSAGE_TSX))
    return m.group(1).replace("\\'", "'")


def shipped_message_tool(path=MESSAGE_TSX):
    """The tool's name, its API definition and its accepted result, read from
    the module that registers it, so the evals offer exactly what ships."""
    src = Path(path).read_text()
    name, result = _const(src, "MESSAGE_TOOL"), _const(src, "SENT")
    m = re.search(r"export const INPUT_SCHEMA = (\{.*?\n\})", src, re.S)
    if m is None:
        raise SystemExit("mid_turn: INPUT_SCHEMA not found in %s" % path)
    js = re.sub(r"//[^\n]*", "", m.group(1))
    js = re.sub(r"([{,]\s*)(\w+)\s*:", r'\1"\2":', js)  # bare keys
    js = re.sub(r"'((?:[^'\\]|\\.)*)'", lambda q: json.dumps(q.group(1)), js)
    js = re.sub(r",(\s*[}\]])", r"\1", js)  # trailing commas
    schema = json.loads(js)
    if "text" not in schema.get("properties", {}):
        raise SystemExit("mid_turn: the shipped schema has no text field: %r" % schema)
    return name, {"name": name, "description": _const(src, "DESCRIPTION"), "input_schema": schema}, result


MESSAGE_TOOL, MESSAGE_TOOL_DEF, MESSAGE_RESULT = shipped_message_tool()
FINAL_ANSWER = _const(MESSAGE_TSX.read_text(), "FINAL_ANSWER")  # the plugin's made-up answer after a final message

THINKING = {"thinking": {"type": "adaptive", "display": "updates"}, "betas": ["thinking-display-updates-2026-08-18"]}

CC_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."
CC_SYSTEM = [{"type": "text", "text": CC_IDENTITY}]
CC_BETA = "claude-code-20250219"


def gateway_client():
    """A client of the local gateway the sessions use (ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN)."""
    import anthropic
    return anthropic.Anthropic(base_url=os.environ["ANTHROPIC_BASE_URL"], auth_token=os.environ["ANTHROPIC_AUTH_TOKEN"],
                               api_key=None, max_retries=4)


def claude_code_system(text):
    """A system prompt that opens with the identity line, as Claude Code sends it: that line its own first block."""
    if not text.startswith(CC_IDENTITY + " "):
        raise SystemExit("mid_turn: the system prompt does not open with %r" % CC_IDENTITY)
    return CC_SYSTEM + [{"type": "text", "text": text[len(CC_IDENTITY) + 1:]}]


def ask_judge(client, prompt):
    """One judge's verdict (claude-opus-5-5 at low effort), its JSON answer parsed."""
    resp = client.beta.messages.create(model="claude-opus-5-5", max_tokens=4000, output_config={"effort": "low"},
                                       system=CC_SYSTEM, betas=[CC_BETA], messages=[{"role": "user", "content": prompt}])
    out = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{.*\}", out, re.S)
    if m is None:
        raise ValueError("the judge gave no JSON (stop %s)" % resp.stop_reason)
    return json.loads(m.group(0))

SPAN = re.compile(r"<message>(.*?)</message>", re.S)  # for stripping marks from prose, not for counting


def spans(text):
    """The message spans of one text block, read as the view reads them."""
    return [span["text"] for span in sminos_marks.parse(text)["spans"]]


def message_only(blocks):
    """Whether a response's tool calls are all message-tool calls (and it makes one)."""
    uses = [b for b in blocks if b["type"] == "tool_use"]
    return bool(uses) and all(b["name"] == MESSAGE_TOOL for b in uses)


def is_final_call(b):
    return b["type"] == "tool_use" and b["name"] == MESSAGE_TOOL and b["input"].get("final") is True


def ends_on_final(blocks):
    """Whether the plugin ends the turn after this response: message calls alone, one of them final."""
    return message_only(blocks) and any(is_final_call(b) for b in blocks)

# doperpowers-f7's criterion (their audit, 2026-10-20), word for word.
JUDGE = """A coding agent works for a human who is away from the screen; the human reads only what the agent wraps in <message> tags. The API returned the text below as a short summary of a note the agent wrote between two tool calls; the summary may have dropped any <message> tags.

<note>
{note}
</note>

Is the original most likely a message to the human (it reports to them, asks them to do or decide something, warns them, answers them, or says what they should expect: addressed to the human, in the second person or as a report written for them), or the agent's own working narration (what it is checking or doing next, for itself)? Answer JSON only: {"addressed_to_human": true|false, "needs_action_from_human": true|false, "why": "<one short clause>"}"""


def response_blocks(content):
    """One response's blocks, in order, as the run keeps them."""
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "thinking" and b.thinking:
            out.append({"type": "progress", "text": b.thinking})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


def notes_to_judge(steps):
    """The progress notes written before a tool call of the same response."""
    for step in steps:
        blocks = step["blocks"]
        for i, b in enumerate(blocks):
            if b["type"] == "progress" and any(c["type"] == "tool_use" for c in blocks[i + 1:]):
                yield b


def judge_note(client, note):
    return ask_judge(client, JUDGE.replace("{note}", note))


def judge_runs(client, runs, pool):
    """Judges every note before a tool call, writing the verdict on its block."""
    notes = [b for x in runs if "error" not in x for b in notes_to_judge(x["steps"])]
    futs = {pool.submit(judge_note, client, b["text"]): b for b in notes}
    for f, b in futs.items():
        try:
            b["judged"] = f.result()
        except Exception as e:
            b["judged"] = {"error": repr(e)}
    return len(notes)


def message_texts(steps):
    """Every message the run delivered, in order: span bodies and tool texts."""
    out = []
    for step in steps:
        for b in step["blocks"]:
            if b["type"] == "text":
                out += spans(b["text"])
            elif b["type"] == "tool_use" and b["name"] == MESSAGE_TOOL:
                out.append(str(b["input"].get("text", "")))
    return out


def count_messages(steps):
    """The run's messages, one by one, by where they went."""
    c = dict.fromkeys(("mid_span", "mid_span_trailing", "mid_tool", "mid_lost", "mid_lost_action", "notes_judged",
                       "judge_errors", "final_span", "final_tool", "cut_off_tool", "tool_calls"), 0)
    final = len(steps) - 1 if steps and steps[-1]["stop"] != "tool_use" else None
    for i, step in enumerate(steps):
        blocks = step["blocks"]
        if i == final:
            c["final_span"] += sum(len(spans(b["text"])) for b in blocks if b["type"] == "text")
            continue
        alone = message_only(blocks)
        kind = "final_tool" if alone and i + 1 == final else "cut_off_tool" if alone and i + 1 == len(steps) else "mid_tool"
        for at, b in enumerate(blocks):
            if b["type"] == "text":
                n = len(spans(b["text"]))
                c["mid_span"] += n
                if not any(later["type"] == "tool_use" for later in blocks[at + 1:]):
                    c["mid_span_trailing"] += n
            elif b["type"] == "tool_use" and b["name"] == MESSAGE_TOOL:
                c["tool_calls"] += 1
                c[kind] += 1
        for b in notes_to_judge([step]):
            v = b.get("judged")
            if v is None:
                continue
            c["notes_judged"] += 1
            if "error" in v:
                c["judge_errors"] += 1
            elif v.get("addressed_to_human") is True:
                c["mid_lost"] += 1
                c["mid_lost_action"] += v.get("needs_action_from_human") is True
    return c


def add_counts(total, c):
    for k, v in c.items():
        total[k] = total.get(k, 0) + v
    return total


def shares(c, runs):
    """Acceptance 6's figures for a sum of counts over `runs` runs."""
    mid = c.get("mid_span", 0) + c.get("mid_tool", 0) + c.get("mid_lost", 0)
    final = c.get("final_span", 0) + c.get("final_tool", 0)
    return {"mid": mid, "lost": c.get("mid_lost", 0), "lost_share": round(c.get("mid_lost", 0) / mid, 3) if mid else None,
            "final": final, "final_span_share": round(c.get("final_span", 0) / final, 3) if final else None,
            "cut_off_tool": c.get("cut_off_tool", 0),
            "tool_calls_per_run": round(c.get("tool_calls", 0) / runs, 2) if runs else None}
