"""What the question-sheet evals share: a stub of the sheet's tool, its
description read from an arm file, the simulated project the sessions work
in, the card a surface draws, and the run loop.

Composite spec: docs/doperpowers/specs/2026-11-23-question-sheet-design.md in
the MAWS repository, child C1 (parent pin ad4427f93, MAWS board ticket #866).
§2.1 is the input the stub accepts, §2.2 its result, §2.4 what the
description asks of the agent, §12 the evals (E1 revise, E2 the card alone).

The stub (`Sheet`) is the tool as the evals need it and no more: it validates
a call as §2.1 says (the schema as a whole, then each entry alone), assigns
ids `q<n>`, revises and withdraws by the ownership rule, captures a
reference's text from the simulated project, returns §2.2's result (contract
X7's first line, entry places when part of a call was refused), and records
every call. There is no inbox, no answer and no delivery: no scenario needs
one.

An arm is a Markdown file holding a wording of the tool's description: the
text before its first `## ` heading is the description; a `## <field>`
section replaces that field's description in the input schema (fields:
ask, id, question, header, options, label, description, preview,
recommended, multiSelect, context, references, withdraw).

The model is reached through the local gateway as the to-human evals reach it
(`mid_turn.gateway_client`), in Claude Code's request shape. A session's
scripted prefix is cached (one breakpoint at its end, one at the newest
message), and each group of runs sharing a prefix warms the cache with its
first run before the rest start.
"""
from __future__ import annotations

import copy, json, re, shlex
from pathlib import Path

from mid_turn import (CC_BETA, CC_SYSTEM, FINAL_ANSWER, MESSAGE_RESULT, MESSAGE_TOOL, MESSAGE_TOOL_DEF, THINKING,
                      claude_code_system, ends_on_final, response_blocks)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORLD = HERE / "question-sheet" / "world"
DEFAULT_ARM = HERE / "question-sheet" / "description-v1.md"
STYLE = REPO / "output-styles" / "to-human.md"
SHEET_TOOL = "mcp__sminos__AskUserQuestion"
CWD = "/Users/dev/tally"

# -- the tool's input (§2.1) and its limits (§1)

LIMITS = {"entries": 20, "question": 2000, "header": 60, "options": 12, "label": 200, "description": 500,
          "preview": 8000, "context": 8000, "references": 8}

FIELD_DESCRIPTIONS = {
    "ask": "Questions to add, or to revise by id: 1 to 20 entries.",
    "id": "The id of an open question you asked (\"q3\"): this entry replaces that question. Leave it out to add a "
          "new question; the tool assigns ids.",
    "question": "The question.",
    "header": "Optional short label.",
    "options": "Zero to twelve choices; none for a question answered in words. The human can always add text.",
    "label": "The choice, short. Unique within the question.",
    "description": "Optional: what choosing it means.",
    "preview": "Optional Markdown shown beside the focused option (single-select only).",
    "recommended": "Optional: true on the option you recommend.",
    "multiSelect": "Optional: the human may pick several options.",
    "context": "Optional Markdown: what the human needs to judge the question.",
    "references": "Optional: up to eight files the question is about, captured as they are now; each a path and an "
                  "optional [first, last] line range.",
    "withdraw": "Ids of open questions you asked that no longer need an answer.",
}


def parse_arm(path):
    """The description and the field descriptions an arm file sets."""
    text = re.sub(r"^---\n.*?\n---\n", "", Path(path).read_text(), flags=re.S)
    parts = re.split(r"^## +(\w+)\s*$", text, flags=re.M)
    fields = dict(FIELD_DESCRIPTIONS)
    for name, body in zip(parts[1::2], parts[2::2]):
        if name not in fields:
            raise SystemExit(f"question_sheet: {path} sets an unknown field {name!r}")
        fields[name] = body.strip()
    return parts[0].strip(), fields


def sheet_tool_def(path=DEFAULT_ARM):
    description, f = parse_arm(path)
    s = lambda key, **kw: {"type": "string", "description": f[key], **kw}
    option = {"type": "object", "additionalProperties": False, "required": ["label"], "properties": {
        "label": s("label", maxLength=LIMITS["label"]),
        "description": s("description", maxLength=LIMITS["description"]),
        "preview": s("preview", maxLength=LIMITS["preview"]),
        "recommended": {"type": "boolean", "description": f["recommended"]}}}
    reference = {"type": "object", "additionalProperties": False, "required": ["path"], "properties": {
        "path": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 2, "maxItems": 2}}}
    entry = {"type": "object", "additionalProperties": False, "required": ["question"], "properties": {
        "id": s("id", pattern=r"^q[0-9]+$"),
        "question": s("question", maxLength=LIMITS["question"]),
        "header": s("header", maxLength=LIMITS["header"]),
        "options": {"type": "array", "maxItems": LIMITS["options"], "items": option, "description": f["options"]},
        "multiSelect": {"type": "boolean", "description": f["multiSelect"]},
        "context": s("context", maxLength=LIMITS["context"]),
        "references": {"type": "array", "maxItems": LIMITS["references"], "items": reference,
                       "description": f["references"]}}}
    schema = {"type": "object", "additionalProperties": False, "properties": {
        "ask": {"type": "array", "minItems": 1, "maxItems": LIMITS["entries"], "items": entry, "description": f["ask"]},
        "withdraw": {"type": "array", "items": {"type": "string", "pattern": r"^q[0-9]+$"}, "description": f["withdraw"]}}}
    return {"name": SHEET_TOOL, "description": description, "input_schema": schema}


# -- the stub

class InputError(ValueError):
    """A call that fails the schema as a whole: nothing changes (§2.1)."""


ENTRY_KEYS = {"id", "question", "header", "options", "multiSelect", "context", "references"}
OPTION_KEYS = {"label", "description", "preview", "recommended"}


def _text(v, name, limit, required=False):
    if v is None and not required:
        return
    if not isinstance(v, str) or (required and not v.strip()):
        raise InputError(f"{name} must be a non-empty string" if required else f"{name} must be a string")
    if len(v) > limit:
        raise InputError(f"{name} is {len(v)} characters; at most {limit}")


def validate(inp):
    """§2.1's schema as a whole; raises InputError naming the first fault."""
    if not isinstance(inp, dict) or set(inp) - {"ask", "withdraw"}:
        raise InputError("the input takes only ask and withdraw")
    ask, withdraw = inp.get("ask"), inp.get("withdraw")
    if not ask and not withdraw:
        raise InputError("at least one of ask and withdraw must be non-empty")
    if ask is not None and (not isinstance(ask, list) or not 1 <= len(ask) <= LIMITS["entries"]):
        raise InputError(f"ask takes 1 to {LIMITS['entries']} entries")
    if withdraw is not None and (not isinstance(withdraw, list)
                                 or not all(isinstance(i, str) and re.fullmatch(r"q\d+", i) for i in withdraw)):
        raise InputError("withdraw takes question ids such as \"q3\"")
    named = [e.get("id") for e in ask or [] if isinstance(e, dict) and e.get("id") is not None] + list(withdraw or [])
    dup = next((i for i in named if named.count(i) > 1), None)
    if dup:
        raise InputError(f"{dup} is named more than once in the call")
    for n, e in enumerate(ask or [], 1):
        where = f"entry {n}"
        if not isinstance(e, dict) or set(e) - ENTRY_KEYS:
            raise InputError(f"{where} has a field the schema does not take: {sorted(set(e) - ENTRY_KEYS)}")
        if e.get("id") is not None and not (isinstance(e["id"], str) and re.fullmatch(r"q\d+", e["id"])):
            raise InputError(f"{where}: id must look like \"q3\"")
        _text(e.get("question"), f"{where}: question", LIMITS["question"], required=True)
        _text(e.get("header"), f"{where}: header", LIMITS["header"])
        _text(e.get("context"), f"{where}: context", LIMITS["context"])
        opts = e.get("options") or []
        if not isinstance(opts, list) or len(opts) > LIMITS["options"]:
            raise InputError(f"{where}: options takes at most {LIMITS['options']}")
        if e.get("multiSelect") and not opts:
            raise InputError(f"{where}: multiSelect needs options")
        labels = []
        for o in opts:
            if not isinstance(o, dict) or set(o) - OPTION_KEYS:
                raise InputError(f"{where}: an option has a field the schema does not take")
            _text(o.get("label"), f"{where}: an option's label", LIMITS["label"], required=True)
            _text(o.get("description"), f"{where}: an option's description", LIMITS["description"])
            _text(o.get("preview"), f"{where}: an option's preview", LIMITS["preview"])
            if o.get("preview") and e.get("multiSelect"):
                raise InputError(f"{where}: a preview is for single-select questions only")
            labels.append(o["label"])
        if len(set(labels)) != len(labels):
            raise InputError(f"{where}: option labels must be unique within a question")
        refs = e.get("references") or []
        if not isinstance(refs, list) or len(refs) > LIMITS["references"]:
            raise InputError(f"{where}: references takes at most {LIMITS['references']}")
        for r in refs:
            lines = r.get("lines") if isinstance(r, dict) else None
            if (not isinstance(r, dict) or not isinstance(r.get("path"), str) or set(r) - {"path", "lines"}
                    or (lines is not None and not (isinstance(lines, list) and len(lines) == 2
                                                   and all(isinstance(x, int) and x >= 1 for x in lines)
                                                   and lines[0] <= lines[1]))):
                raise InputError(f"{where}: a reference is a path and an optional [first, last] line range")


class Sheet:
    """One session's sheet, as the evals need it: open questions with their
    fields and revisions, ids never reused, and every call recorded."""

    def __init__(self, fs=None):
        self.fs = fs
        self.questions = {}  # id -> question; closed ones stay with their state
        self.next_id = 1
        self.calls = []

    def open_ids(self):
        return [q for q, v in self.questions.items() if v["state"] == "open"]

    def capture(self, ref):
        """A reference's text as Read would return it, or the reason it cannot be captured."""
        if self.fs is None:
            return None, "no files in this sheet"
        path = self.fs.resolve(ref["path"])
        if Path(path).name.startswith(".env"):
            return None, f"the reference {ref['path']} could not be read: permission denied"
        if path not in self.fs.files:
            return None, f"the reference {ref['path']} could not be read: no such file"
        lines = ref.get("lines")
        body = self.fs.read(path, *(lines and (lines[0], lines[1] - lines[0] + 1) or ()))
        return {"path": ref["path"], "lines": lines, "body": body}, None

    def call(self, inp, asker="main", call_id=None):
        """Applies one call and returns its result text (§2.2); raises InputError for a call that fails the schema."""
        record = {"input": copy.deepcopy(inp), "asker": asker, "call_id": call_id}
        try:
            validate(inp)
        except InputError as e:
            record["error"] = str(e)
            self.calls.append(record)
            raise
        added, revised, withdrew, refused = [], [], [], []
        for n, e in enumerate(inp.get("ask") or [], 1):
            qid = e.get("id")
            if qid is not None:
                q = self.questions.get(qid)
                if q is None:
                    refused.append((n, f"entry {n}, {qid} is not a question on this sheet"))
                    continue
                if q["state"] != "open":
                    refused.append((n, f"entry {n}, {qid} is not open ({q['state']})"))
                    continue
                if q["asker"] != asker:
                    refused.append((n, f"entry {n}, {qid} was asked by another asker"))
                    continue
            refs, why = [], None
            for r in e.get("references") or []:
                cap, why = self.capture(r)
                if why:
                    break
                refs.append(cap)
            if why:
                refused.append((n, f"entry {n}, {why}"))
                continue
            fields = {k: copy.deepcopy(e[k]) for k in ("question", "header", "options", "multiSelect", "context")
                      if e.get(k) is not None}
            fields["references"] = refs
            if qid is None:
                qid = f"q{self.next_id}"
                self.next_id += 1
                self.questions[qid] = {"id": qid, "revision": 1, "asker": asker, "state": "open", "call_id": call_id,
                                       "history": [], **fields}
                added.append((n, qid))
            else:
                q = self.questions[qid]
                q["history"].append({k: v for k, v in q.items() if k != "history"})
                for k in ("question", "header", "options", "multiSelect", "context", "references"):
                    q.pop(k, None)
                q.update(fields, revision=q["revision"] + 1, call_id=call_id)
                revised.append((n, qid, q["revision"]))
        for qid in inp.get("withdraw") or []:
            q = self.questions.get(qid)
            if q is None or q["state"] != "open":
                refused.append((None, f"{qid} is not open" + (f" ({q['state']})" if q else "")))
            elif q["asker"] != asker and asker != "main":
                refused.append((None, f"{qid} was asked by another asker"))
            else:
                q["state"] = "withdrawn"
                withdrew.append(qid)
        record.update(added=[q for _, q in added], revised=[q for _, q, _ in revised], withdrew=withdrew,
                      refused=[why for _, why in refused])
        self.calls.append(record)
        return result_text(added, revised, withdrew, refused)


def result_text(added, revised, withdrew, refused):
    """§2.2: the first line's fixed grammar, entry places when any entry was refused, then what was not done."""
    places = any(n is not None for n, _ in refused)
    first = []
    if added:
        first.append("Added " + ", ".join(f"{q} (entry {n})" if places else q for n, q in added) + ".")
    if revised:
        first.append("Revised " + ", ".join(f"{q} (entry {n}, revision {r})" if places else f"{q} (revision {r})"
                                            for n, q, r in revised) + ".")
    if withdrew:
        first.append("Withdrew " + ", ".join(withdrew) + ".")
    lines = [" ".join(first)] if first else []
    if refused:
        lines.append("Not done: " + " ".join(why.rstrip(".") + "." for _, why in refused))
    return "\n".join(lines)


# -- the card (§8): what a surface shows of one question, and all a judge of E2 sees

def render_card(q):
    head = q.get("header") or "(no header)"
    asker = "main" if q.get("asker", "main") == "main" else f"from {q['asker']}"
    out = [f"### {head}  ·  {q['id']}, revision {q.get('revision', 1)}, asked by the {asker} agent", "",
           q["question"].strip()]
    if q.get("context"):
        out += ["", "**Context**", "", q["context"].strip()]
    for r in q.get("references") or []:
        span = f" lines {r['lines'][0]}-{r['lines'][1]}" if r.get("lines") else ""
        out += ["", f"**Reference: {r['path']}{span}** (as it was when asked)", "```", r["body"].rstrip(), "```"]
    if q.get("options"):
        out += ["", "**Options**" + (" (pick any number)" if q.get("multiSelect") else " (pick one)")]
        for i, o in enumerate(q["options"], 1):
            mark = "  [recommended]" if o.get("recommended") else ""
            out.append(f"{i}. {o['label']}{mark}" + (f": {o['description']}" if o.get("description") else ""))
            if o.get("preview"):
                out += ["   Preview:", "   " + o["preview"].strip().replace("\n", "\n   ")]
    out += ["", "[a free-text field for your answer or a note]"]
    return "\n".join(out)


# -- the simulated project

class FS:
    """The project's files, keyed by absolute path under CWD."""

    def __init__(self, files=None):
        if files is None:
            files = {f"{CWD}/{p.relative_to(WORLD)}": p.read_text() for p in sorted(WORLD.rglob("*")) if p.is_file()}
        self.files = dict(files)

    def copy(self):
        return FS(self.files)

    def resolve(self, path):
        path = path.strip()
        if path.startswith("~"):
            return path
        p = path if path.startswith("/") else f"{CWD}/{path}"
        parts = []
        for seg in p.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                parts and parts.pop()
            else:
                parts.append(seg)
        return "/" + "/".join(parts)

    def read(self, path, offset=None, limit=None):
        """The file as Read returns it: numbered lines."""
        lines = self.files[self.resolve(path)].split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        start = max(1, int(offset or 1))
        end = len(lines) if limit is None else min(len(lines), start + int(limit) - 1)
        return "\n".join(f"{n:>6}\t{lines[n - 1]}" for n in range(start, end + 1))

    def rel(self, path):
        return path[len(CWD) + 1:] if path.startswith(CWD + "/") else path

    def under(self, root):
        root = self.resolve(root or ".")
        return [p for p in sorted(self.files) if p == root or p.startswith(root.rstrip("/") + "/")]

    def grep(self, pattern, root=".", names_only=False, glob=None):
        try:
            rx = re.compile(pattern)
        except re.error:
            rx = re.compile(re.escape(pattern))
        out = []
        for p in self.under(root):
            if glob and not Path(p).match(glob.replace("**/", "")):
                continue
            hits = [(n, line) for n, line in enumerate(self.files[p].split("\n"), 1) if rx.search(line)]
            if hits:
                out += [self.rel(p)] if names_only else [f"{self.rel(p)}:{n}:{line}" for n, line in hits]
        return out


NO_OUTPUT = "(Bash completed with no output)"


class Env:
    """Canned results for every tool the sessions have; scripted steps may override a result."""

    def __init__(self, fs, sheet, shell_overrides=(), git_log=""):
        self.fs, self.sheet = fs, sheet
        self.shell_overrides = list(shell_overrides)  # (regex, output) tried before the generic shell
        self.git_log = git_log
        self.agents = 0

    def tool(self, name, inp, call_id=None):
        """(content, is_error) for one tool call."""
        if name == SHEET_TOOL:
            try:
                return self.sheet.call(inp, call_id=call_id), False
            except InputError as e:
                return f"InputValidationError: {e}. Nothing on the sheet changed.", True
        if name == MESSAGE_TOOL:
            return MESSAGE_RESULT, False
        if name == "Read":
            path = self.fs.resolve(inp.get("file_path", ""))
            if path not in self.fs.files:
                return "File does not exist.", True
            return self.fs.read(path, inp.get("offset"), inp.get("limit")), False
        if name == "Write":
            path = self.fs.resolve(inp.get("file_path", ""))
            new = path not in self.fs.files
            self.fs.files[path] = inp.get("content", "")
            return (f"File created successfully at: {path}" if new else f"The file {path} has been updated."), False
        if name == "Edit":
            path = self.fs.resolve(inp.get("file_path", ""))
            body, old, new = self.fs.files.get(path), inp.get("old_string", ""), inp.get("new_string", "")
            if body is None:
                return "File does not exist.", True
            count = body.count(old) if old else 0
            if count == 0:
                return "String to replace not found in file.", True
            if count > 1 and not inp.get("replace_all"):
                return (f"Found {count} matches of the string to replace, but replace_all is false. To replace all "
                        "occurrences, set replace_all to true."), True
            self.fs.files[path] = body.replace(old, new) if inp.get("replace_all") else body.replace(old, new, 1)
            return f"The file {path} has been updated.", False
        if name == "Grep":
            hits = self.fs.grep(inp.get("pattern", ""), inp.get("path") or ".",
                                names_only=inp.get("output_mode", "files_with_matches") == "files_with_matches",
                                glob=inp.get("glob"))
            return ("\n".join(hits) if hits else "No matches found"), False
        if name == "Glob":
            pat = inp.get("pattern", "*")
            hits = [self.fs.rel(p) for p in self.fs.under(inp.get("path") or ".") if Path(p).match(pat.replace("**/", ""))]
            return ("\n".join(hits) if hits else "No files found"), False
        if name == "Agent":
            self.agents += 1
            return (f"Async agent launched successfully. agentId: a{self.agents:02d}c7e91f4. The agent is working in "
                    "the background; you will be notified when it completes."), False
        if name == "SendMessage":
            return json.dumps({"success": True, "message": f"Message sent to {inp.get('to')}."}), False
        if name == "Bash":
            return self.shell(inp.get("command", "")), False
        return NO_OUTPUT, False

    def shell(self, command):
        for rx, out in self.shell_overrides:
            if re.search(rx, command):
                return out
        outputs = []
        for segment in re.split(r"&&|\|\||;|\n", command):
            first = segment.split("|")[0].strip()
            try:
                words = shlex.split(first)
            except ValueError:
                words = first.split()
            out = self.shell_one(words)
            if out:
                outputs.append(out)
        return "\n".join(outputs) or NO_OUTPUT

    def shell_one(self, words):
        while words and re.match(r"\w+=", words[0]):
            words = words[1:]
        if not words:
            return ""
        cmd, args = words[0], words[1:]
        if cmd == "cd":
            return ""
        if cmd == "git":
            sub = args[0] if args else ""
            if sub == "log":
                return self.git_log
            if sub == "status":
                return "On branch csv-export\nnothing to commit, working tree clean"
            if sub == "branch":
                return "* csv-export\n  main"
            if sub in ("pull", "fetch"):
                return "Already up to date."
            return ""
        if cmd in ("pytest", "python", "python3", "uv", "make") and ("pytest" in words or cmd == "pytest" or
                                                                    (cmd == "make" and "test" in args)):
            return "........................................................................ [ 33%]\n" \
                   "........................................................................ [ 67%]\n" \
                   "...................................................................... [100%]\n" \
                   "214 passed, 3 skipped in 43.08s"
        if cmd in ("ruff", "mypy") or (cmd in ("python", "python3", "uv") and ({"ruff", "mypy"} & set(args))):
            return "All checks passed!" if "ruff" in words else "Success: no issues found in 41 source files"
        if cmd in ("cat", "head", "tail", "sed", "nl", "less", "wc"):
            paths = [a for a in args if not a.startswith("-") and self.fs.resolve(a) in self.fs.files]
            out = []
            for p in paths:
                body = self.fs.files[self.fs.resolve(p)]
                out.append(f"{len(body.splitlines())} {p}" if cmd == "wc" else body.rstrip("\n"))
            return "\n".join(out)
        if cmd == "ls":
            target = next((a for a in args if not a.startswith("-")), ".")
            root = self.fs.resolve(target).rstrip("/") + "/"
            names = sorted({p[len(root):].split("/")[0] for p in self.fs.files if p.startswith(root)})
            return "\n".join(names)
        if cmd in ("grep", "rg"):
            flags = [a for a in args if a.startswith("-")]
            rest = [a for a in args if not a.startswith("-")]
            if not rest:
                return ""
            pattern, roots = rest[0], rest[1:] or ["."]
            names_only = any("l" in f.lstrip("-") and not f.startswith("--") for f in flags)
            pattern = pattern.replace("\\|", "|")
            hits = [h for r in roots for h in self.fs.grep(pattern, r, names_only=names_only)]
            return "\n".join(hits)
        if cmd == "find":
            root = args[0] if args and not args[0].startswith("-") else "."
            name = args[args.index("-name") + 1] if "-name" in args else "*"
            return "\n".join("./" + self.fs.rel(p) for p in self.fs.under(root) if Path(p).match(name))
        if cmd in ("echo", "printf"):
            return " ".join(a for a in args if not a.startswith("-"))
        return {"pwd": CWD, "whoami": "dev", "hostname": "macbook",
                "date": "Mon Nov 23 15:42:10 UTC 2026"}.get(cmd, "")


# -- the session the model continues

PREAMBLE = f"""You are Claude Code, Anthropic's official CLI for Claude. You are an interactive agent that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user.

# Environment
 - Primary working directory: {CWD}
 - Is a git repository: true
 - Platform: darwin
 - Today's date: 2026-11-23

# Output Style: to-human
"""


def style_body(path=STYLE):
    return re.sub(r"^---\n.*?\n---\n", "", Path(path).read_text(), flags=re.S).strip()


def tool(name, description, props, required):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props, "required": required}}


BASE_TOOLS = [
    tool("Bash", "Executes a bash command in the project and returns its output.",
         {"command": {"type": "string"}, "description": {"type": "string"},
          "run_in_background": {"type": "boolean"}}, ["command"]),
    tool("Read", "Reads a file from the local filesystem; returns its lines numbered (cat -n).",
         {"file_path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, ["file_path"]),
    tool("Edit", "Performs an exact string replacement in a file.",
         {"file_path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"},
          "replace_all": {"type": "boolean"}}, ["file_path", "old_string", "new_string"]),
    tool("Write", "Writes a file, overwriting it if it exists.",
         {"file_path": {"type": "string"}, "content": {"type": "string"}}, ["file_path", "content"]),
    tool("Grep", "Searches file contents with a regular expression.",
         {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"},
          "output_mode": {"type": "string", "enum": ["content", "files_with_matches", "count"]}}, ["pattern"]),
    tool("Agent", "Launch a subagent. run_in_background returns at once; you are notified when it finishes.",
         {"description": {"type": "string"}, "prompt": {"type": "string"}, "subagent_type": {"type": "string"},
          "run_in_background": {"type": "boolean"}}, ["description", "prompt"]),
    MESSAGE_TOOL_DEF,
]


def tools_for(arm_path):
    return BASE_TOOLS + [sheet_tool_def(arm_path)]


def build(script, env):
    """The messages of a scripted session, each scripted tool call run through `env` unless the step gives its
    result. A script is a list of steps:
      ("user", text)                       a user message (the task, a notification, the human's message)
      ("assistant", text|None, [calls])    calls: (name, input) or (name, input, result) or
                                           (name, input, result, effect) where effect(env) runs before the result
      ("final", text)                      a message sent alone with final: true, its result and the made-up answer"""
    msgs, n = [], 0
    for step in script:
        kind = step[0]
        if kind == "user":
            msgs.append({"role": "user", "content": step[1]})
        elif kind == "assistant":
            _, text, calls = step
            content = [{"type": "text", "text": text}] if text else []
            results = []
            for call in calls:
                name, inp = call[0], call[1]
                n += 1
                tid = f"toolu_p{n:03d}"
                content.append({"type": "tool_use", "id": tid, "name": name, "input": inp})
                if len(call) > 3 and call[3]:
                    call[3](env)
                if len(call) > 2 and call[2] is not None:
                    out, err = (call[2](env) if callable(call[2]) else call[2]), False
                    if name == SHEET_TOOL:  # the sheet always applies a scripted call, so its state follows
                        out, err = env.tool(name, inp, tid)
                else:
                    out, err = env.tool(name, inp, tid)
                results.append({"type": "tool_result", "tool_use_id": tid, "content": out, **({"is_error": True} if err else {})})
            msgs.append({"role": "assistant", "content": content})
            if results:
                msgs.append({"role": "user", "content": results})
        elif kind == "final":
            n += 1
            tid = f"toolu_p{n:03d}"
            msgs += [{"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": MESSAGE_TOOL,
                                                         "input": {"text": step[1], "final": True}}]},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": MESSAGE_RESULT}]},
                     {"role": "assistant", "content": [{"type": "text", "text": FINAL_ANSWER}]}]
        else:
            raise ValueError(f"unknown step {kind!r}")
    return msgs


def with_breakpoint(msgs):
    """A copy of the messages with a cache breakpoint on the last block of the last message."""
    msgs = copy.deepcopy(msgs)
    last = msgs[-1]
    if isinstance(last["content"], str):
        last["content"] = [{"type": "text", "text": last["content"]}]
    block = last["content"][-1]
    if isinstance(block, dict):
        block["cache_control"] = {"type": "ephemeral"}
    return msgs


def plain(content):
    """SDK blocks as request dicts, thinking blocks kept with their signatures."""
    out = []
    for b in content:
        d = b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else dict(b)
        d.pop("citations", None) if d.get("type") == "text" else None
        out.append(d)
    return out


def live(client, model, effort, system, tools, prefix, env, max_steps, stop_after_sheet=1):
    """Continues a session from its prefix until the turn ends, a final message ends it, `max_steps` responses
    have run, or `stop_after_sheet` more responses have run after the first sheet call. Returns the steps, each
    {"stop", "blocks", "results", "usage"}, and how the run ended."""
    msgs = with_breakpoint(prefix)
    steps, sheet_seen, ended = [], None, "max_steps"
    for i in range(max_steps):
        req = with_breakpoint(msgs) if i else msgs
        resp = client.beta.messages.create(model=model, max_tokens=16000, output_config={"effort": effort},
                                           thinking=THINKING["thinking"], betas=THINKING["betas"] + [CC_BETA],
                                           system=system, tools=tools, messages=req)
        blocks = response_blocks(resp.content)
        uses = [b for b in resp.content if b.type == "tool_use"]
        results = []
        for b in uses:
            out, err = env.tool(b.name, b.input, b.id)
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, **({"is_error": True} if err else {})})
        u = resp.usage
        steps.append({"stop": resp.stop_reason, "blocks": blocks, "results": [r["content"] for r in results],
                      "usage": {"input": u.input_tokens, "cache_read": u.cache_read_input_tokens or 0,
                                "cache_write": u.cache_creation_input_tokens or 0, "output": u.output_tokens}})
        if not uses:
            ended = "turn_end"
            break
        if ends_on_final(blocks):
            ended = "final_message"
            break
        if sheet_seen is None and any(b.name == SHEET_TOOL for b in uses):
            sheet_seen = i
        if sheet_seen is not None and i - sheet_seen >= stop_after_sheet:
            ended = "after_sheet"
            break
        msgs = msgs + [{"role": "assistant", "content": plain(resp.content)}, {"role": "user", "content": results}]
    return steps, ended


def sheet_calls(steps):
    """The sheet calls a run made, with the step each came in."""
    return [(i, b) for i, s in enumerate(steps) for b in s["blocks"] if b["type"] == "tool_use" and b["name"] == SHEET_TOOL]


def notes_before(steps, step_index):
    """The agent's own words around a sheet call, as automatic capture (§10) would take them: the text and progress
    notes of the response that made the call, and of the response before it."""
    out = []
    for s in steps[max(0, step_index - 1):step_index + 1]:
        out += [b["text"].strip() for b in s["blocks"] if b["type"] in ("text", "progress") and b["text"].strip()]
    return "\n\n".join(out)


def judge(client, prompt, effort="low", model="claude-opus-5-5"):
    """One judge's JSON verdict, in the gateway's request shape."""
    resp = client.beta.messages.create(model=model, max_tokens=8000, output_config={"effort": effort},
                                       system=CC_SYSTEM, betas=[CC_BETA], messages=[{"role": "user", "content": prompt}])
    out = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{.*\}", out, re.S)
    if m is None:
        raise ValueError(f"the judge gave no JSON (stop {resp.stop_reason})")
    return json.loads(m.group(0))


def usage_total(runs):
    t = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    for x in runs:
        for s in x.get("steps", []):
            for k in t:
                t[k] += s["usage"][k]
    return t


PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-fable-5-2": (8.0, 40.0)}


def cost(usage, model="claude-opus-5-5"):
    """List-price dollars for a usage total: cache writes at 1.25x input, reads at 0.05x (Opus 5.5's $0.20)."""
    i, o = PRICES[model]
    return round((usage["input"] * i + usage["cache_write"] * i * 1.25 + usage["cache_read"] * i * 0.05
                  + usage["output"] * o) / 1e6, 2)


def run_jobs(jobs, key, run, workers=8):
    """Runs `run(job)` for every job: the first job of each `key(job)` group alone (it writes the group's cache),
    then the rest side by side. A job that raises is kept as {"job": job, "error": ...}."""
    import concurrent.futures as cf
    firsts, rest, seen = [], [], set()
    for j in jobs:
        (rest if key(j) in seen else firsts).append(j)
        seen.add(key(j))
    out = []

    def safe(j):
        try:
            return run(j)
        except Exception as e:  # kept in the results, counted as an error
            return {"job": list(j), "error": repr(e)}
    with cf.ThreadPoolExecutor(workers) as pool:
        out += list(pool.map(safe, firsts))
        out += list(pool.map(safe, rest))
    return out


def session(script, arm_path):
    """A fresh environment, the scripted prefix built through it, and the request's system and tools."""
    from question_sheet_session import GIT_LOG, make_fs
    fs = make_fs()
    env = Env(fs, Sheet(fs), git_log=GIT_LOG)
    prefix = build(script, env)
    return env, prefix, claude_code_system(PREAMBLE + style_body()), tools_for(arm_path)
