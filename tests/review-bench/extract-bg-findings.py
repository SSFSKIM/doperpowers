#!/usr/bin/env python3
"""extract-bg-findings.py <state.json> <state> — recover a bg review session's findings.

Sources, in order of authority:
  1. The last ReportFindings tool call in the session transcript
     (state.json's linkScanPath) — /code-review reports through it.
  2. The longest assistant text block in the transcript — /review prints its
     review as a mid-turn message; state.json's output.result only records the
     final (often one-line) message, so result alone loses the body.
  3. output.result as fallback when the transcript is unavailable.
"""
import json
import sys

state_file, state = sys.argv[1], sys.argv[2]
d = json.load(open(state_file))
out = d.get("output") or {}
result = out.get("result") if isinstance(out, dict) else (str(out) if out else None)

findings = None
longest_text = ""
tp = d.get("linkScanPath")
if tp:
    try:
        with open(tp) as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message") or {}
                for c in msg.get("content") or []:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and c.get("name") == "ReportFindings":
                        findings = c.get("input")
                    elif c.get("type") == "text" and len(c.get("text") or "") > len(longest_text):
                        longest_text = c["text"]
    except FileNotFoundError:
        pass

sections = []
if findings is not None:
    lines = ["## ReportFindings (level=%s, %d findings)"
             % (findings.get("level"), len(findings.get("findings") or []))]
    for f in findings.get("findings") or []:
        loc = f.get("file", "?")
        if f.get("line") is not None:
            loc += ":%s" % f["line"]
        lines.append("")
        lines.append("- **%s** — %s" % (f.get("short_summary") or f.get("summary"), loc))
        lines.append("  %s" % f.get("summary"))
        if f.get("failure_scenario"):
            lines.append("  Failure: %s" % f["failure_scenario"])
        if f.get("verdict"):
            lines.append("  Verdict: %s" % f["verdict"])
        if f.get("category"):
            lines.append("  Category: %s" % f["category"])
    sections.append("\n".join(lines))

body = longest_text if len(longest_text) > len(result or "") else (result or "")
if body:
    sections.append(("## Review body\n\n" + body) if sections else body)
if result and result != body:
    sections.append("## Final message\n\n" + result)

if state != "done" or not sections:
    print("extract-bg-findings: job state=%s with no usable output" % state, file=sys.stderr)
    sys.exit(1)
print("\n\n".join(sections))
