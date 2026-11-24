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
DEFAULT_ARM = HERE / "question-sheet" / "description-v3.md"  # the wording the composite ships (§2.4)
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


def _string(v, name, limit, required=False, min_length=0):
    """A string field as the schema types it: present means a string, within its length."""
    if v is None:
        if required:
            raise InputError(f"{name} is required")
        return
    if not isinstance(v, str):
        raise InputError(f"{name} must be a string")
    if len(v) < min_length:
        raise InputError(f"{name} must not be empty")
    if limit is not None and len(v) > limit:
        raise InputError(f"{name} is {len(v)} characters; at most {limit}")


def _bool(v, name):
    if v is not None and not isinstance(v, bool):
        raise InputError(f"{name} must be a boolean")


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


ID = re.compile(r"q[1-9][0-9]*")


def validate(inp):
    """The schema as a whole (C2's published tool-input schema, sminos/types/sheet/schema/tool-input.schema.json,
    with the two whole-call rules its title states); raises InputError naming the first fault. An entry's own
    rules (unique labels, a preview only without multiSelect, multiSelect only with options, lines in order)
    are not here: they refuse that entry alone (entry_fault)."""
    if not isinstance(inp, dict) or set(inp) - {"ask", "withdraw"}:
        raise InputError("the input takes only ask and withdraw")
    ask, withdraw = inp.get("ask"), inp.get("withdraw")
    if ask is not None and (not isinstance(ask, list) or not 1 <= len(ask) <= LIMITS["entries"]):
        raise InputError(f"ask takes 1 to {LIMITS['entries']} entries")
    if withdraw is not None and (not isinstance(withdraw, list) or not withdraw
                                 or not all(isinstance(i, str) and ID.fullmatch(i) for i in withdraw)):
        raise InputError("withdraw takes one or more question ids such as \"q3\"")
    if not ask and not withdraw:
        raise InputError("at least one of ask and withdraw must be non-empty")
    for n, e in enumerate(ask or [], 1):
        where = f"entry {n}"
        if not isinstance(e, dict):
            raise InputError(f"{where} must be an object")
        if set(e) - ENTRY_KEYS:
            raise InputError(f"{where} has a field the schema does not take: {sorted(set(e) - ENTRY_KEYS)}")
        if "id" in e and not (isinstance(e["id"], str) and ID.fullmatch(e["id"])):
            raise InputError(f"{where}: id must look like \"q3\"")
        _string(e.get("question"), f"{where}: question", LIMITS["question"], required=True, min_length=1)
        _string(e.get("header"), f"{where}: header", LIMITS["header"])
        _string(e.get("context"), f"{where}: context", LIMITS["context"])
        _bool(e.get("multiSelect"), f"{where}: multiSelect")
        opts = e.get("options")
        if opts is not None and (not isinstance(opts, list) or len(opts) > LIMITS["options"]):
            raise InputError(f"{where}: options is a list of at most {LIMITS['options']}")
        for o in opts or []:
            if not isinstance(o, dict) or set(o) - OPTION_KEYS:
                raise InputError(f"{where}: an option is an object with label, description, preview, recommended")
            _string(o.get("label"), f"{where}: an option's label", LIMITS["label"], required=True, min_length=1)
            _string(o.get("description"), f"{where}: an option's description", LIMITS["description"])
            _string(o.get("preview"), f"{where}: an option's preview", LIMITS["preview"])
            _bool(o.get("recommended"), f"{where}: an option's recommended")
        refs = e.get("references")
        if refs is not None and (not isinstance(refs, list) or len(refs) > LIMITS["references"]):
            raise InputError(f"{where}: references is a list of at most {LIMITS['references']}")
        for r in refs or []:
            if not isinstance(r, dict) or set(r) - {"path", "lines"}:
                raise InputError(f"{where}: a reference is an object with path and lines")
            _string(r.get("path"), f"{where}: a reference's path", None, required=True, min_length=1)
            lines = r.get("lines")
            if lines is not None and not (isinstance(lines, list) and len(lines) == 2 and all(_int(x) for x in lines)):
                raise InputError(f"{where}: a reference's lines are two integers")
    named = [e.get("id") for e in ask or [] if e.get("id") is not None] + list(withdraw or [])
    dup = next((i for i in named if named.count(i) > 1), None)
    if dup:
        raise InputError(f"{dup} is named more than once in the call")


def entry_fault(n, e):
    """An entry's own fault, as the clause of `Not done:` that refuses it (C2's grammar), or None."""
    opts = e.get("options") or []
    labels = [o["label"] for o in opts]
    dup = next((l for l in labels if labels.count(l) > 1), None)
    if dup is not None:
        return f'entry {n}, two options share the label "{dup[:200]}"'
    if e.get("multiSelect") and any(o.get("preview") for o in opts):
        return f"entry {n}, an option's preview needs a single-select question"
    if e.get("multiSelect") and not opts:
        return f"entry {n}, multiSelect needs options"
    for r in e.get("references") or []:
        lines = r.get("lines")
        if lines is not None and not 1 <= lines[0] <= lines[1]:
            return f"entry {n}, lines must be [a, b] with 1 <= a <= b"
    return None


CLOCK = "15:42"  # the session machine's local time in every scripted world
MAX_OPEN = 500  # open questions a sheet holds (C2's grammar: "the sheet holds 500 open questions")


class Sheet:
    """One session's sheet, as the evals need it: open questions with their
    fields and revisions, ids never reused, and every call recorded with the
    card each added or revised question showed after it (and before, for a
    revision)."""

    def __init__(self, fs=None, workdirs=(CWD,)):
        self.fs = fs
        self.workdirs = tuple(workdirs)
        self.questions = {}  # id -> question; closed ones stay with their state
        self.next_id = 1
        self.calls = []

    def open_ids(self):
        return [q for q, v in self.questions.items() if v["state"] == "open"]

    def capture(self, ref):
        """A reference's text as Read would return it, or the reason it cannot be captured (§2.3: a path outside
        the session's working directories is refused; a file over 256 KB needs a range)."""
        if self.fs is None:
            return None, "no files in this sheet"
        path = self.fs.resolve(ref["path"])
        why = lambda reason: f"the reference {ref['path']} could not be read: {reason}"
        if not any(path == d or path.startswith(d.rstrip("/") + "/") for d in self.workdirs):
            return None, why("it is outside the session's working directories")
        if Path(path).name.startswith(".env"):
            return None, why("permission denied")
        if path not in self.fs.files:
            return None, why("no such file")
        lines = ref.get("lines")
        size = self.fs.sizes.get(path, len(self.fs.files[path].encode()))
        if not lines and size > 256 * 1024:
            return None, why(f"the file is {size // 1024} KB, over Read's 256 KB without a range; name a line range")
        body = self.fs.read(path, *(lines and (lines[0], lines[1] - lines[0] + 1) or ()))
        return {"path": ref["path"], "lines": lines, "body": body}, None

    @staticmethod
    def card_of(q):
        return copy.deepcopy({k: v for k, v in q.items() if k != "history"})

    def asked_by(self, q):
        return "the main conversation" if q["asker"] == "main" else f"the subagent {q['asker']}"

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
        shown, before = {}, {}
        for n, e in enumerate(inp.get("ask") or [], 1):
            qid = e.get("id")
            if qid is not None:
                q = self.questions.get(qid)
                if q is None:
                    refused.append((n, f"entry {n}, {qid} is not open (never asked at {CLOCK})"))
                    continue
                if q["state"] != "open":
                    refused.append((n, f"entry {n}, {qid} is not open ({q['state']} at {CLOCK})"))
                    continue
                if q["asker"] != asker:
                    refused.append((n, f"entry {n}, {qid} was asked by {self.asked_by(q)}; only its asker revises it"))
                    continue
            fault = entry_fault(n, e)
            if not fault and qid is None and len(self.open_ids()) >= MAX_OPEN:
                fault = f"entry {n}, the sheet holds {MAX_OPEN} open questions"
            if fault:
                refused.append((n, fault))
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
                before[qid] = self.card_of(q)
                q["history"].append(self.card_of(q))
                for k in ("question", "header", "options", "multiSelect", "context", "references"):
                    q.pop(k, None)
                q.update(fields, revision=q["revision"] + 1, call_id=call_id)
                revised.append((n, qid, q["revision"]))
            shown[qid] = self.card_of(self.questions[qid])
        for qid in inp.get("withdraw") or []:
            q = self.questions.get(qid)
            if q is None or q["state"] != "open":
                refused.append((None, f"{qid} is not open ({q['state'] if q else 'never asked'} at {CLOCK})"))
            elif q["asker"] != asker and asker != "main":
                refused.append((None, f"{qid} was asked by {self.asked_by(q)}; only its asker or the main "
                                      "conversation withdraws it"))
            else:
                q["state"] = "withdrawn"
                withdrew.append(qid)
        record.update(added=[q for _, q in added], revised=[q for _, q, _ in revised], withdrew=withdrew,
                      refused=[why for _, why in refused], shown=shown, before=before,
                      result=result_text(added, revised, withdrew, refused))
        self.calls.append(record)
        return record["result"]


def result_text(added, revised, withdrew, refused):
    """§2.2 and C2's grammar: the first line's sentences, each id with its entry's place exactly when some entry or
    withdrawal of the call was refused, `Nothing done.` when nothing was; then what was not done."""
    places = bool(refused)
    first = []
    if added:
        first.append("Added " + ", ".join(f"{q} (entry {n})" if places else q for n, q in added) + ".")
    if revised:
        first.append("Revised " + ", ".join(f"{q} (entry {n}, revision {r})" if places else f"{q} (revision {r})"
                                            for n, q, r in revised) + ".")
    if withdrew:
        first.append("Withdrew " + ", ".join(withdrew) + ".")
    lines = [" ".join(first) if first else "Nothing done."]
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


# -- calling the model

PLAN_WAITS = []  # (time, seconds waited) for each refusal for plan usage


def create(client, **kw):
    """A request, retried for up to ten minutes when the gateway refuses it for plan usage (an exhausted account
    behind it; another usually serves a minute later). Any other error is raised."""
    import time
    for attempt in range(11):
        try:
            return client.beta.messages.create(**kw)
        except Exception as e:
            if "plan usage" not in str(e) or attempt == 10:
                raise
            PLAN_WAITS.append((time.strftime("%H:%M:%S"), 60))
            time.sleep(60)


# -- the simulated project

class FS:
    """The project's files, keyed by absolute path under CWD."""

    def __init__(self, files=None, sizes=None):
        if files is None:
            files = {f"{CWD}/{p.relative_to(WORLD)}": p.read_text() for p in sorted(WORLD.rglob("*")) if p.is_file()}
        self.files = dict(files)
        self.sizes = dict(sizes or {})  # a file whose stand-in content is smaller than the file it stands for

    def copy(self):
        return FS(self.files, self.sizes)

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


def simple_commands(command):
    """The words of each command a command line runs, split on ;, &&, ||, & and newlines outside quotes; of a
    pipeline only its first command."""
    out, words, word, quote, piped, i = [], [], "", None, False, 0
    has_word = False

    def end_word():
        nonlocal word, has_word
        if has_word:
            words.append(word)
        word, has_word = "", False

    def end_command():
        nonlocal words, piped
        end_word()
        if words and not piped:
            out.append(words)
        words, piped = [], False
    while i < len(command):
        c = command[i]
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < len(command):
                i += 1
                word += command[i]
            else:
                word += c
        elif c in "'\"":
            quote, has_word = c, True
        elif c == "\\" and i + 1 < len(command):
            i += 1
            if command[i] != "\n":
                word, has_word = word + command[i], True
        elif c in " \t":
            end_word()
        elif c in ";\n" or command.startswith("&&", i) or command.startswith("||", i):
            end_command()
            i += 1 if command.startswith(("&&", "||"), i) else 0
        elif c == "&" and (command[i - 1:i] == ">" or command[i + 1:i + 2] == ">"):  # 2>&1, &> : a redirection
            word, has_word = word + c, True
        elif c == "&":
            end_command()
        elif c == "|":
            end_word()
            if words and not piped:
                out.append(words)
            words, piped = [], True
        elif c == "#" and not has_word:
            while i < len(command) and command[i] != "\n":
                i += 1
            continue
        else:
            word, has_word = word + c, True
        i += 1
    end_command()
    return out


class Env:
    """Canned results for every tool the sessions have; scripted steps may override a result."""

    def __init__(self, fs, sheet, shell_overrides=(), git_log=""):
        self.fs, self.sheet = fs, sheet
        self.shell_overrides = list(shell_overrides)  # (regex, output) tried before the generic shell
        self.git_log = git_log
        self.agents = 0
        self.committed = dict(fs.files)
        self.main = dict(fs.files)  # main as the branch left it: what `git diff main...` compares against
        self.commits = 0
        self.simulator = None  # (client, model, facts): answers what the canned shell cannot
        self.suite_extra = 196  # tests of the whole suite the world does not hold
        self.simulated = []

    SIM = """You are the shell of a developer's Mac, in the git repository {cwd} (branch csv-export; Python 3.12.7 in
.venv with the project's dependencies installed; the `tally` package and its tests are the files listed below).
Print exactly what this command line would print, stdout and stderr, and nothing else: no commentary, no code
fences. If it would print nothing, print nothing.

Keep to what is established. These facts hold:
{facts}
Every test in the repository passes, and the tests are exactly those in the files (pytest 8.3.3). Where the
output depends on something not given here, print a plausible, unremarkable result consistent with the files and
with the earlier outputs below; never invent a new problem, failure, warning or surprise, and never contradict
the files.
{earlier}

The repository's files: {listing}

The branch's history (git log --oneline):
{log}

{named}
Command line:
{command}"""

    def simulate(self, command):
        client, model, facts = self.simulator
        named = [p for p in self.fs.files if self.fs.rel(p) in command or p in command]
        files = "".join(f"--- {self.fs.rel(p)} ---\n{self.fs.files[p][:6000]}\n" for p in named[:4])
        earlier = "".join(f"\n$ {x['command']}\n{x.get('output', '')[:1500]}\n" for x in self.simulated[-6:])
        prompt = self.SIM.format(cwd=CWD, facts=facts, command=command, log=self.git_log,
                                 earlier=("\nEarlier outputs of this shell:" + earlier) if earlier else "",
                                 listing=", ".join(self.fs.rel(p) for p in sorted(self.fs.files) if p.startswith(CWD)),
                                 named=("Files the command names, as they are now:\n" + files) if files else "")
        try:
            resp = create(client, model=model, max_tokens=4000, output_config={"effort": "low"},
                                               system=CC_SYSTEM, betas=[CC_BETA],
                                               messages=[{"role": "user", "content": prompt}])
            out = "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception as e:  # the run goes on; the miss is recorded
            out, resp = NO_OUTPUT, None
            self.simulated.append({"command": command, "error": repr(e)})
            return out
        u = getattr(resp, "usage", None)
        self.simulated.append({"command": command, "output": out,
                               "usage": {"input": u.input_tokens, "output": u.output_tokens} if u else None})
        return out or NO_OUTPUT

    def mark_committed(self):
        """The working tree as committed: what the live part of a run starts from."""
        self.committed = dict(self.fs.files)

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
            if re.search(rx, command, re.S | re.I):
                return out(self) if callable(out) else out
        outputs = []
        # "$(cat <<'EOF' ... EOF)", Claude Code's form for a commit message: the message itself, quoted
        command = re.sub(r"\"?\$\(cat\s*<<-?\s*['\"]?(\w+)['\"]?\n(.*?)\n\s*\1\s*\)\"?",
                         lambda m: shlex.quote(m.group(2)), command, flags=re.S)
        heredoc = re.compile(r"(?:cat|tee)\s*(?:>\s*(\S+)\s*)?<<-?\s*['\"]?(\w+)['\"]?\s*(?:>\s*(\S+))?\n(.*?)\n\2\s*(?:\n|$)", re.S)
        while True:
            m = heredoc.search(command)
            if not m:
                break
            path = m.group(1) or m.group(3)
            if path:
                self.fs.files[self.fs.resolve(path.strip("'\""))] = m.group(4) + "\n"
            command = command[:m.start()] + "\n" + command[m.end():]
        if self.simulator and re.search(r"(^|[;&|\n]\s*)(for|while|until|if|case|function)\b|\$\(|<<", command):
            return self.simulate(command.strip())  # a compound command is answered whole
        for words in simple_commands(command):
            out = self.shell_one(words)
            if out is None:  # a command the canned shell cannot answer goes to the simulator
                line = " ".join(w if re.fullmatch(r"\d*(>>?|<)(&\d+)?\S*|&>\S*", w) else shlex.quote(w) for w in words)
                out = self.simulate(line) if self.simulator else ""
                out = "" if out == NO_OUTPUT else out
            if out:
                outputs.append(out)
        return "\n".join(outputs) or NO_OUTPUT

    def shell_one(self, words):
        """One simple command's output; the first command of a pipeline stands for the pipeline."""
        while words and re.match(r"\w+=", words[0]):
            words = words[1:]
        if not words:
            return ""
        cmd, args = words[0], words[1:]
        if cmd in ("cd", ":"):
            return ""
        if cmd == "git":
            return self.git(args)
        if cmd == "sed" and any(a.startswith("-i") for a in args):
            return self.sed_in_place(args)
        if cmd in ("pytest", "python", "python3", "uv", "make") and ("pytest" in words or cmd == "pytest" or
                                                                    (cmd == "make" and "test" in args)):
            return self.pytest(args)
        if cmd == "make" and "fixtures" in args:
            self.fs.files.setdefault(f"{CWD}/.fixtures/usage_2m.sql", "-- rows=2000000\n")
            self.fs.sizes[f"{CWD}/.fixtures/usage_2m.sql"] = 611 * 2**20
            return ("python -m tests.fixtures.generate --rows 2000000 --out .fixtures/usage_2m.sql\n"
                    "generating usage_events: 2,000,000 rows across 14 products ... done in 58.2s\n"
                    "wrote .fixtures/usage_2m.sql (611 MB)")
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
            path = self.fs.resolve(target)
            if path in self.fs.files:
                names, root = [Path(path).name], str(Path(path).parent) + "/"
            else:
                root = path.rstrip("/") + "/"
                names = sorted({p[len(root):].split("/")[0] for p in self.fs.files if p.startswith(root)})
            if not names:
                return f"ls: {target}: No such file or directory"
            if not any("l" in a for a in args if a.startswith("-") and not a.startswith("--")):
                return "\n".join(names)

            def size(name):
                full = root + name
                if full in self.fs.files:
                    return self.fs.sizes.get(full, len(self.fs.files[full].encode()))
                return 192
            return "\n".join(f"{'d' if root + n not in self.fs.files else '-'}rw-r--r--  1 dev  staff  {size(n):>10} "
                             f"Nov 23 14:02 {n}" for n in names)
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
            return " ".join(a for a in args if not a.startswith("-")).replace("$?", "0")
        if cmd in ("mkdir", "touch", "rm", "mv", "cp", "chmod"):
            if cmd == "touch":
                for a in args:
                    if not a.startswith("-"):
                        self.fs.files.setdefault(self.fs.resolve(a), "")
            return ""
        known = {"pwd": CWD, "whoami": "dev", "hostname": "macbook", "date": "Mon Nov 23 15:42:10 UTC 2026",
                 "true": "", "false": "", "export": "", "source": "", "sleep": "", "head": "", "tail": ""}
        return known.get(cmd)  # None: not something the canned shell can answer


    def changed(self):
        new = sorted(p for p in self.fs.files if p not in self.committed)
        mod = sorted(p for p in self.fs.files if p in self.committed and self.fs.files[p] != self.committed[p])
        return mod, new

    def git(self, args):
        sub = args[0] if args else ""
        mod, new = self.changed()
        if sub == "status":
            if not mod and not new:
                return "On branch csv-export\nnothing to commit, working tree clean"
            if "--short" in args or "-s" in args or any(a.startswith("--porcelain") for a in args):
                return "\n".join([f" M {self.fs.rel(p)}" for p in mod] + [f"?? {self.fs.rel(p)}" for p in new])
            out = ["On branch csv-export"]
            if mod:
                out += ["Changes not staged for commit:"] + [f"\tmodified:   {self.fs.rel(p)}" for p in mod]
            if new:
                out += ["Untracked files:"] + [f"\t{self.fs.rel(p)}" for p in new]
            return "\n".join(out)
        if sub == "diff":
            import difflib
            refs = [a for a in args[1:] if not a.startswith("-") and a != "--"]
            if any(not re.fullmatch(r"(origin/)?main(\.\.\.?(csv-export|HEAD)?)?|HEAD|csv-export", r) for r in refs):
                return None  # a commit or another ref: the simulator, with the history
            base = self.main if any("main" in r for r in refs) else self.committed
            files = [p for p in sorted(set(base) | set(self.fs.files)) if p.startswith(CWD + "/")
                     and not p.startswith(CWD + "/.fixtures") and base.get(p) != self.fs.files.get(p)]
            if "--name-only" in args:
                return "\n".join(self.fs.rel(p) for p in files)
            if "--name-status" in args:
                return "\n".join(("A" if p not in base else "D" if p not in self.fs.files else "M") + "\t" +
                                 self.fs.rel(p) for p in files)
            out, stat = [], []
            for p in files:
                old, new = base.get(p, ""), self.fs.files.get(p, "")
                d = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                              "/dev/null" if p not in base else f"a/{self.fs.rel(p)}",
                                              f"b/{self.fs.rel(p)}", lineterm=""))
                plus = sum(l.startswith("+") and not l.startswith("+++") for l in d)
                minus = sum(l.startswith("-") and not l.startswith("---") for l in d)
                stat.append((self.fs.rel(p), plus, minus))
                out += [f"diff --git a/{self.fs.rel(p)} b/{self.fs.rel(p)}"] + d
            if "--stat" in args or "--shortstat" in args:
                lines = [f" {f} | {a + m} {'+' * min(a, 40)}{'-' * min(m, 40)}" for f, a, m in stat]
                total = f" {len(stat)} files changed, {sum(a for _, a, _ in stat)} insertions(+), " \
                        f"{sum(m for _, _, m in stat)} deletions(-)"
                return "\n".join(([] if "--shortstat" in args else lines) + [total]) if stat else ""
            return "\n".join(out)
        if sub == "commit":
            if not mod and not new:
                return "On branch csv-export\nnothing to commit, working tree clean"
            self.commits += 1
            msg = next((args[i + 1] for i, a in enumerate(args) if a in ("-m", "--message") and i + 1 < len(args)), None)
            path = next((args[i + 1] for i, a in enumerate(args) if a in ("-F", "--file") and i + 1 < len(args)), None)
            if msg is None and path and self.fs.resolve(path) in self.fs.files:
                msg = self.fs.files[self.fs.resolve(path)]
            msg = (msg or "").strip() or "Update"
            sha = f"{0x5a3c1e0 + self.commits * 0x10f3b:07x}"
            self.committed = dict(self.fs.files)
            self.git_log = f"{sha} {msg.splitlines()[0]}\n" + self.git_log
            return f"[csv-export {sha}] {msg.splitlines()[0]}\n {len(mod) + len(new)} files changed"
        if sub == "log":
            if "--" in args or any(a.startswith(("--stat", "-p", "--patch", "--name")) for a in args):
                return None  # paths or patches: the simulator, with the history
            n = next((int(a[1:]) for a in args if re.fullmatch(r"-\d+", a)), None)
            n = next((int(args[i + 1]) for i, a in enumerate(args) if a in ("-n", "--max-count") and i + 1 < len(args)
                      and args[i + 1].isdigit()), n)
            return "\n".join(self.git_log.split("\n")[:n])
        if sub == "rev-parse":
            return (self.git_log.split()[0] if self.git_log else "b81f2c4") + "9d04c2e51f7a3b86e0d12c4f9a7e5b3d01"
        if sub == "branch":
            head = self.git_log.split("\n")[0]
            return f"* csv-export {head}\n  main       b81f2c4 reports: pin a report to the dashboard (#196)"
        if sub == "reflog":
            return "\n".join(f"{l.split()[0]} HEAD@{{{i}}}: commit: {l.split(' ', 1)[1]}"
                             for i, l in enumerate(self.git_log.split("\n")[:8]))
        if sub in ("pull", "fetch"):
            return "Already up to date."
        if sub in ("add", "checkout", "switch", "stash", "restore", "rm", "mv", "config", "tag"):
            return ""
        return None  # show, merge-base, worktree, blame and the rest: the simulator

    def sed_in_place(self, args):
        """`sed -i` with s/// expressions: basic regular expressions unless -E or -r."""
        ere = any(a in ("-E", "-r") for a in args)
        exprs = [a for a in args if len(a) > 3 and a[0] == "s" and not a[1].isalnum() and a.count(a[1]) >= 3]
        paths = [a for a in args if self.fs.resolve(a) in self.fs.files]
        for e in exprs:
            d = e[1]
            parts = re.split(r"(?<!\\)" + re.escape(d), e[2:])
            if len(parts) < 3:
                continue
            old, new, flags = parts[0].replace("\\" + d, d), parts[1].replace("\\" + d, d), parts[2]
            if not ere:  # BRE: ( ) { } + ? | are literal unless escaped
                old = re.sub(r"\\([(){}+?|])|([(){}+?|])", lambda m: m.group(1) or "\\" + m.group(2), old)
            new = new.replace("&", r"\g<0>")
            for p in paths:
                path = self.fs.resolve(p)
                try:
                    self.fs.files[path] = re.sub(old, new, self.fs.files[path], count=0 if "g" in flags else 1, flags=re.M)
                except re.error:
                    self.fs.files[path] = self.fs.files[path].replace(old, new)
        return ""

    def pytest(self, args):
        """Every test passes. The tests are those the named paths hold (the whole suite adds 196 the world does
        not hold), filtered by -k's words and -m slow; -v lists them by name."""
        paths = [a.split("::")[0] for a in args if a.split("::")[0].startswith("tests")]
        files = [p for p in sorted(self.fs.files) if p.endswith(".py") and "/tests/" in p and
                 (not paths or any(self.fs.rel(p).startswith(x.rstrip("/")) for x in paths))]
        names = []
        for p in files:
            body = self.fs.files[p]
            for m in re.finditer(r"^((?:@pytest\.mark\.\w+.*\n)*)def (test_\w+)", body, re.M):
                slow = "mark.slow" in m.group(1)
                names.append((self.fs.rel(p), m.group(2), slow))
        k = next((args[i + 1] for i, a in enumerate(args) if a == "-k" and i + 1 < len(args)), None)
        mark = next((args[i + 1] for i, a in enumerate(args) if a == "-m" and i + 1 < len(args)), "")
        if k:
            words = [w for w in re.split(r"\s+|\(|\)", k) if w and w not in ("and", "or", "not")]
            names = [x for x in names if any(w in x[1] for w in words)]
        if mark.strip() == "slow":
            names = [x for x in names if x[2]]
        elif "not slow" in mark or not mark:
            names = [x for x in names if not x[2]]
        extra = 0 if paths or k else self.suite_extra
        n = len(names) + extra
        slow = sum(x[2] for x in names)
        seconds = 0.2 + (n - slow) * 0.019 + slow * 83.5
        tail = f"{n} passed" + (", 3 skipped" if extra else "") + f" in {seconds:.2f}s"
        if slow and any(a in ("-s", "--capture=no") for a in args):
            tail = "  wrote 2,000,000 rows in 21.7s; peak RSS 88.4 MB (baseline 71.0 MB)\n" + tail
        if any(a in ("-v", "--verbose", "-vv") for a in args):
            body = [f"{f}::{t} PASSED".ljust(72) + f"[{100 * (i + 1) // max(1, len(names)):>3}%]"
                    for i, (f, t, _) in enumerate(names)]
            return "\n".join(body + ([f"... and {extra} more PASSED"] if extra else []) + ["", tail])
        dots = "." * n
        lines = [dots[i:i + 72] for i in range(0, len(dots), 72)] or [""]
        return "\n".join(lines) + "\n" + tail


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
                if name == "Bash":  # a scripted commit joins the history a live `git log` shows
                    for sha, msg in re.findall(r"^\[csv-export (\w+)\] (.+)$", out, re.M):
                        env.git_log = f"{sha} {msg}\n" + env.git_log
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


def live(client, model, effort, system, tools, prefix, env, max_steps, done=None):
    """Continues a session from its prefix until the turn ends, a final message ends it, `max_steps` responses
    have run, or one more response has run after `done(env, calls)` first holds (calls: the sheet calls made
    live; by default, any). Returns the steps, each {"stop", "blocks", "results", "usage"}, and how the run
    ended."""
    done = done or (lambda env, calls: bool(calls))
    n0 = len(env.sheet.calls)
    msgs = with_breakpoint(prefix)
    steps, sheet_seen, ended = [], None, "max_steps"
    for i in range(max_steps):
        req = with_breakpoint(msgs) if i else msgs
        resp = create(client, model=model, max_tokens=16000, output_config={"effort": effort},
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
        if sheet_seen is None and done(env, env.sheet.calls[n0:]):
            sheet_seen = i
        if sheet_seen is not None and i - sheet_seen >= 1:
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


JUDGE_USAGE = {"calls": 0, "input": 0, "output": 0}


class JudgeError(ValueError):
    """A judge that gave no valid verdict in three tries: the run's judging is incomplete, never a success."""


def judge(client, prompt, effort="low", model="claude-opus-5-5", valid=None, tries=3):
    """One judge's JSON verdict, in the gateway's request shape, checked by `valid` (a verdict -> bool) and asked
    again when it gives none; its tokens are added to JUDGE_USAGE. Raises JudgeError after `tries`."""
    last = None
    for _ in range(tries):
        resp = create(client, model=model, max_tokens=8000, output_config={"effort": effort},
                      system=CC_SYSTEM, betas=[CC_BETA], messages=[{"role": "user", "content": prompt}])
        u = getattr(resp, "usage", None)
        JUDGE_USAGE["calls"] += 1
        if u is not None:
            JUDGE_USAGE["input"] += u.input_tokens
            JUDGE_USAGE["output"] += u.output_tokens
        out = "".join(b.text for b in resp.content if b.type == "text")
        m = re.search(r"\{.*\}", out, re.S)
        try:
            verdict = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            verdict = None
        if isinstance(verdict, dict) and (valid is None or valid(verdict)):
            return verdict
        last = out[:200] or f"(stop {resp.stop_reason})"
    raise JudgeError(f"no valid verdict in {tries} tries; last: {last!r}")


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


def session(script, arm_path, overrides=(), simulator=None):
    """A fresh environment, the scripted prefix built through it, and the request's system and tools.
    `overrides` are (regex, output) answers tried before staging's and the generic shell's; `simulator`
    (client, model) answers, from then on, what the canned shell cannot."""
    from question_sheet_session import GIT_LOG, SIM_FACTS, STAGING, make_fs
    fs = make_fs()
    env = Env(fs, Sheet(fs), shell_overrides=list(overrides) + STAGING, git_log=GIT_LOG)
    prefix = build(script, env)
    env.mark_committed()
    # the whole suite answers with the count the session last showed for it
    shown = [int(m) for m in re.findall(r"(\d+) passed, \d+ skipped", json.dumps(prefix))]
    if shown:
        world = sum(1 for p in fs.files if "/tests/" in p and p.endswith(".py")
                    for m in re.finditer(r"^((?:@pytest\.mark\.\w+.*\n)*)def test_", fs.files[p], re.M)
                    if "mark.slow" not in m.group(1))
        env.suite_extra = max(0, shown[-1] - world)
    if simulator:
        env.simulator = (*simulator, SIM_FACTS)
    return env, prefix, claude_code_system(PREAMBLE + style_body()), tools_for(arm_path)
