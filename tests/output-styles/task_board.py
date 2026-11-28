"""What the Task Board evals share: the board's stand-in, the words under
test, the shell that routes a session's `task` commands to the stand-in, and
the session builder.

Composite spec: docs/doperpowers/specs/2026-11-27-task-board-design.md, child
B5 (parent pin a99ce15dd). D2's "What agents are told" and contract X7 are
what is tested; D1 is the line the judges draw; D5's notice is what the
stand-in says.

Everything else is the question sheet's harness, imported and not changed
(question_sheet: the simulated project `tally`, its canned shell and shell
simulator, the sheet's stub, the run loop, the judge, the job runner).

The stand-in (`Board`) is the commands themselves, on a store of its own: a
session's `task ...` and `sminos task ...` run the repository's `task` CLI
and its `sminos task` family against a temporary SMINOS_HOME made for the
run, as the session `SESSION`, and every call is recorded with its arguments,
its standard input, its output and its exit. So an id, a refusal, a usage
error and `show`'s text are the built ones. What the stand-in adds:

  the door      the human's act is the harness's (`Board.human`): the same
                `sminos task done|decline|comment`, run as a terminal that is
                no session. A session that removes CLAUDE_CODE_SESSION_ID
                from its own command reaches it too, as it would, and the
                call is recorded `as_human`.
  the notice    B1's M2 (the push) is not on main; `notice` builds the frame
                a session would be sent, from the store's own text
                (sminos_tasks.notice_text) in sminos's own chat frame and
                peer envelope.
  the mod       B1's M4 is not built; a subagent's assigning command gets
                `--asker-agent <id> --asker-name <type>` after its verb, as
                D2's hook will put it.
  a member      the run's session has no thread on the temporary home, so the
                built commands print it as `[3f9a1c2e] (gone)` in no project;
                `Board.look` writes those cells as a running member's
                (`tally  heron (running)`), and the run's date as the
                world's.
  the help      `task <a human's verb> --help` is a usage error as built; an
                arm with the `help` part prints the words' help.txt there
                and after `task --help`.
  tickets       the simulated project has no ticket board: a ticket form
                answers as `task` answers in a clone whose default branch
                holds no board file.

The words (`Words`): a directory under task-board/ holding one version of
what agents are told, in the four parts an arm switches:

  guide   guide-line.md      one line at the end of sminos's start guide,
                             which a main session reads at its start and a
                             subagent never does (the guide is a SessionStart
                             hook's)
  skill   SKILL.md           `task:human-tasks`: its description in every
                             session's skill listing, a subagent's too; its
                             body what the Skill tool returns
  help    help.txt           above
  sheet   sheet-sentence.md  one sentence added to the question tool's
                             description, after its first paragraph

Arms: `bare` (none), `ship` (guide, skill, help: what B1's M5 ships),
`ship+sheet` (all four); any other name is its parts joined by `+`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import question_sheet as qs  # noqa: E402
import question_sheet_session as ss  # noqa: E402
from mid_turn import CC_IDENTITY, claude_code_system  # noqa: E402

REPO = qs.REPO
DIR = HERE / "task-board"
DEFAULT_WORDS = DIR / "words-v1"
TASK_MAIN = REPO / "task" / "cli" / "main.py"
SMINOS_CLI = REPO / "sminos" / "skills" / "sminos" / "scripts" / "sminos"
SESSION = "3f9a1c2e-6b1d-4e0a-9c57-2d8e41b7a0f3"
ALIAS, PROJECT, MACHINE = "heron", "tally", "macbook"
WORLD_DATE = "2026-11-23"
SUBAGENT = "a01c7e91f4"  # the id question_sheet.Env gives a session's first subagent
ARMS = {"bare": (), "ship": ("guide", "skill", "help"), "ship+sheet": ("guide", "skill", "help", "sheet")}
PARTS = ("guide", "skill", "help", "sheet")
NO_BOARD = ("error: refs/remotes/origin/HEAD holds no .doperpowers/board.json: the default branch of tally-app/tally, "
            "as this clone last fetched it, gives task no board\n")
HUMAN_ONLY = ("assign-human", "revise", "withdraw", "reopen")
WRITES = ("assign-human", "assign", "revise", "comment", "withdraw", "reopen", "done", "decline", "act")


def _load(name, path, beside=True):
    """A module of another part of the repository, loaded under a name of its own."""
    if beside:
        sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if beside:
            sys.path.remove(str(path.parent))
    return mod


human_form = _load("task_cli_human", REPO / "task" / "cli" / "human.py").form  # which of `task`'s forms are the board's


def sminos_modules():
    """(sminos, sminos_tasks), for the notice's texts; loaded when first asked for."""
    global _SMINOS
    if _SMINOS is None:
        scripts = str(SMINOS_CLI.parent)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import sminos
        _SMINOS = (sminos, sminos.sibling_module("sminos_tasks"))
    return _SMINOS


_SMINOS = None


# -- the words

class Words:
    """One version of what agents are told, and the parts of it an arm puts in context."""

    def __init__(self, path=DEFAULT_WORDS, arm="ship"):
        self.path, self.arm = Path(path), arm
        self.parts = tuple(ARMS[arm]) if arm in ARMS else tuple(p for p in arm.split("+") if p)
        unknown = set(self.parts) - set(PARTS)
        if unknown:
            raise SystemExit(f"task_board: the arm {arm!r} names no part {sorted(unknown)}; parts: {', '.join(PARTS)}")
        read = lambda name: (self.path / name).read_text().strip()
        self.guide_line, self.help, self.sheet_sentence = read("guide-line.md"), read("help.txt"), read("sheet-sentence.md")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", (self.path / "SKILL.md").read_text(), re.S)
        front = dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)
        self.skill_name, self.skill_description, self.skill_body = "task:" + front["name"], front["description"], m.group(2).strip()

    def has(self, part):
        return part in self.parts


def reminder(text):
    return f"<system-reminder>\n{text}\n</system-reminder>\n"


def start_guide(words):
    """sminos's start guide as a member of the simulated project reads it, the words' line at its end."""
    text = re.sub(r"^<!--.*?-->\n", "", (DIR / "guide-as-built.md").read_text(), flags=re.S).strip()
    return "SessionStart hook additional context: " + text + ("\n" + words.guide_line if words.has("guide") else "")


def skill_listing(words):
    sminos_skill = (SMINOS_CLI.parents[1] / "SKILL.md").read_text()
    rows = [("sminos:sminos", re.search(r"^description: (.*)$", sminos_skill, re.M).group(1))]
    if words.has("skill"):
        rows.append((words.skill_name, words.skill_description))
    return "The following skills are available for use with the Skill tool:\n\n" + "\n".join(f"- {n}: {d}" for n, d in rows)


def opening(words, text, main=True):
    """A session's first message: what its start put in context, then the human's task or the caller's brief.
    A subagent has the skill listing and no start guide."""
    return (reminder(start_guide(words)) if main else "") + reminder(skill_listing(words)) + text


SKILL_TOOL = qs.tool("Skill", "Invoke a skill by its name from the available-skills list; its instructions load into "
                              "the turn.", {"skill": {"type": "string"}, "args": {"type": "string"}}, ["skill"])


def sheet_tool(words):
    """The question tool as it ships, with the words' sentence after its first paragraph in an arm that has it."""
    d = qs.sheet_tool_def()
    if words.has("sheet"):
        first, _, rest = d["description"].partition("\n\n")
        d["description"] = f"{first}\n\n{words.sheet_sentence}\n\n{rest}"
    return d


def tools_for(words, main=True):
    """A main session's tools; a general-purpose subagent's are the same less Agent (it has the question tool and
    the message tool, as the owner's sessions give them)."""
    return [t for t in qs.BASE_TOOLS if main or t["name"] != "Agent"] + [SKILL_TOOL, sheet_tool(words)]


SUB_PREAMBLE = f"""{CC_IDENTITY} You are an agent for Claude Code. Given the message of the agent that launched you, use the tools available to complete the task. Complete the task fully: don't gold-plate, but don't leave it half-done. When you complete the task, respond with a concise report covering what was done and any key findings; the caller will relay this to the user, so it only needs the essentials.

Messages from the agent that launched you direct your work. Your final response is all your caller sees of your run.

# Environment
 - Primary working directory: {qs.CWD}
 - Is a git repository: true
 - Platform: darwin
 - Today's date: {WORLD_DATE}
"""


def system_for(main=True):
    return claude_code_system(qs.PREAMBLE + qs.style_body()) if main else claude_code_system(SUB_PREAMBLE)


# -- the board's stand-in

class Board:
    """The built commands on a store of the run's own; every call recorded."""

    def __init__(self, words=None):
        self.words = words
        self.root = tempfile.mkdtemp(prefix="task-board-eval-")
        for d in ("sminos", "cwd", "home", "files"):
            os.mkdir(os.path.join(self.root, d), 0o700)
        self.calls, self.acts, self.paths = [], [], {}
        self.stage = None  # which conversation of the run is calling, written on each call
        self.day = time.strftime("%Y-%m-%d", time.gmtime())

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def env(self, as_human):
        e = {"PATH": os.pathsep.join([os.path.dirname(sys.executable), "/usr/bin", "/bin"]),
             "HOME": os.path.join(self.root, "home"), "SMINOS_HOME": os.path.join(self.root, "sminos"),
             "TASK_SMINOS": str(SMINOS_CLI), "TASK_HOME": os.path.join(self.root, "home", "task"),
             "LANG": "en_US.UTF-8", "TZ": "UTC"}
        if not as_human:
            e["CLAUDE_CODE_SESSION_ID"] = SESSION
        return e

    def real(self, program, args, stdin, as_human):
        argv = [sys.executable, "-B", str(TASK_MAIN)] if program == "task" else [str(SMINOS_CLI)]
        try:
            p = subprocess.run(argv + list(args), input=(stdin or "").encode(), capture_output=True,
                               env=self.env(as_human), cwd=os.path.join(self.root, "cwd"), timeout=60)
        except subprocess.TimeoutExpired:
            return "", f"{program}: no answer within 60 s\n", 1
        return p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace"), p.returncode

    def look(self, text):
        """The built output as a running member of the simulated project would read it (the module's docstring)."""
        short = SESSION[:8]
        text = text.replace(f"—  [{short}] (gone)", f"{PROJECT}  {ALIAS} (running)")
        text = text.replace(f"asked by [{short}]", f"asked by {ALIAS} [{short}]")
        text = text.replace(self.day, WORLD_DATE).replace(time.strftime("%Y-%m-%d", time.gmtime()), WORLD_DATE)
        for real, shown in self.paths.items():
            text = text.replace(real, shown)
        return text

    def file(self, shown, content):
        """A body file of the simulated project, put where the command can read it."""
        real = os.path.join(self.root, "files", f"{len(self.paths)}-{os.path.basename(shown) or 'body'}")
        if content is not None:
            with open(real, "w") as f:
                f.write(content)
        self.paths[real] = shown
        return real

    def run(self, program, args, stdin=None, as_human=False, agent=None, call_id=None):
        """One `task` or `sminos` command line of a session: (stdout, stderr, exit), or None when it is not the
        board's (another verb of sminos's). `agent`: the subagent that ran it, (id, type)."""
        args = list(args)
        verb = args[0] if args else ""
        helps = any(a in ("-h", "--help") for a in args)
        told = self.words is not None and self.words.has("help")
        if program == "sminos" and verb not in ("task", "help"):
            return None
        sent = list(args)
        if agent and not as_human and ((program == "task" and verb == "assign-human") or
                                      (program == "sminos" and args[:2] == ["task", "assign"])):
            at = 1 if program == "task" else 2
            sent[at:at] = ["--asker-agent", agent[0], "--asker-name", agent[1]]
        if program == "task" and helps and told and (verb in HUMAN_ONLY or human_form([a for a in args if a not in
                                                                                    ("-h", "--help")]) is not None):
            out, err, code, kind = self.words.help + "\n", "", 0, "help"
        elif program == "task" and (not args or helps or verb == "--version"):
            out, err, code = self.real(program, sent, stdin, as_human)
            kind = "help"
            if told and code == 0 and (not args or verb in ("-h", "--help")):
                out = out.rstrip("\n") + "\n\n" + self.words.help + "\n"
        elif program == "task" and human_form(args) is None:
            out, err, code, kind = "", NO_BOARD, 1, "ticket:" + verb
        else:
            out, err, code = self.real(program, sent, stdin, as_human)
            kind = "help" if verb == "help" else (args[1] if program == "sminos" and len(args) > 1 else verb) or "usage"
            kind = "assign" if kind == "assign-human" else kind
        out, err = self.look(out), self.look(err)
        task = next((a.split("@")[0] for a in args if re.fullmatch(r"t[1-9][0-9]*(@[1-9][0-9]*)?", a)), None)
        self.calls.append({"stage": self.stage, "program": program, "args": args, "stdin": stdin, "as_human": as_human,
                           "agent": agent[0] if agent else None, "call_id": call_id, "verb": kind, "task": task,
                           "exit": code, "stdout": out, "stderr": err})
        return out, err, code

    def human(self, *args):
        """The human's act through the door, from a terminal that is no session: the verdict's line."""
        out, err, code = self.real("sminos", ["task"] + list(args), None, True)
        self.acts.append({"args": list(args), "exit": code, "stdout": out, "stderr": err})
        if code != 0:
            raise RuntimeError(f"the door refused the human's act {args}: {err.strip() or out.strip()}")
        return out.strip()

    def state(self):
        try:
            with open(os.path.join(self.root, "sminos", "tasks", "state.json")) as f:
                return json.load(f)
        except OSError:
            return None

    def tasks(self):
        """The store's tasks in order, each as the store keeps it."""
        s = self.state()
        return sorted(s["tasks"].values(), key=lambda t: int(t["id"][1:])) if s else []

    def listing(self):
        out, _, _ = self.real("sminos", ["task", "list", "--all"], None, False)
        return self.look(out).strip()


def notice(kind, task_id, clause="asker", agent=None, seq=3):
    """The frame a session is sent when the human acts on a task it assigned (D5; X6's text in sminos's chat frame
    and peer envelope, from `tasks@<machine>`): a user message's content."""
    sminos, tasks = sminos_modules()
    text = tasks.notice_text(clause, kind, task_id, agent)
    frame = sminos.compose_chat_frame(PROJECT, f"{MACHINE}/human:{seq}", f"tasks@{MACHINE}", "@you", 0, text)
    return sminos.peer_envelope(frame, sender=f"tasks@{MACHINE}")


def card(t):
    """A task as the board shows it to the human: all a judge sees."""
    out = [f"### {t['title']}", f"{t['id']} · {t['class']}" + (f" · due {t['due']}" if t.get("due") else "") +
           (" · " + " ".join("#" + x for x in t["tags"]) if t.get("tags") else "")]
    out += ["", t["body"].strip() if (t.get("body") or "").strip() else "(no body)"]
    for c in t.get("comments") or []:
        if c.get("by") != "human":
            out += ["", f"Comment by the agent: {c['text']}"]
    return "\n".join(out)


# -- the shell: a session's command line, its board commands run by the stand-in

HEREDOC = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
MARK = re.compile(r"\x00H(\d+)\x00")
SUB_OPEN, SUB_CLOSE = "\x01", "\x02"
MENTIONS = re.compile(r"(^|[\s;&|(/`])(task|sminos)(\s|$)")
KEYWORDS = {"for", "while", "until", "if", "case", "function", "select", "[[", "do", "then", "{", "("}
REDIRECT = re.compile(r"(\d*)(>>?|<)(&\d+|\S*)|&>(\S*)")
WRAPPERS = {"command", "time", "nohup", "exec", "builtin"}
WRITE = re.compile(r"\btask\s+(%s)\b" % "|".join(WRITES))  # a board command that changes the store


class Unparsed(Exception):
    """A command line the stand-in's shell does not run piece by piece."""


def pull_heredocs(command):
    """The command line with each heredoc replaced by a marker word, and the bodies."""
    lines, out, docs, i = command.split("\n"), [], [], 0
    while i < len(lines):
        line, found = lines[i], list(HEREDOC.finditer(lines[i]))
        i += 1
        for m in found:
            body = []
            while i < len(lines) and (lines[i].lstrip("\t") if m.group(1) else lines[i]) != m.group(3):
                body.append(lines[i].lstrip("\t") if m.group(1) else lines[i])
                i += 1
            i += 1
            line = line.replace(m.group(0), f" \x00H{len(docs)}\x00 ", 1)
            docs.append("\n".join(body) + "\n")
        out.append(line)
    return "\n".join(out), docs


def _closing(text, i):
    """The index of the parenthesis that closes the one at `i`, quotes skipped."""
    depth, quote = 0, None
    for j in range(i, len(text)):
        c = text[j]
        if quote:
            quote = None if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
    raise Unparsed("an unclosed $(")


def lex(text):
    """The commands of a command line (heredocs pulled): each {"op": how it joins the one before (`&&`, `||` or
    `;`), "src": its text, "stages": its pipeline, each stage a list of words}. A command substitution is kept
    in its word between SUB_OPEN and SUB_CLOSE. Raises Unparsed for a backtick."""
    cmds, stages, words, word, has, quote = [], [], [], "", False, None
    op, start, i, n = ";", 0, 0, len(text)

    def end_word():
        nonlocal word, has
        if has:
            words.append(word)
        word, has = "", False

    def end_stage():
        nonlocal words
        end_word()
        if words:
            stages.append(words)
        words = []

    def end_command(next_op, at, width):
        nonlocal stages, op, start
        end_stage()
        if stages:
            cmds.append({"op": op, "src": text[start:at].strip(), "stages": stages})
            op = next_op
        stages, start = [], at + width
    while i < n:
        c = text[i]
        if quote:
            if c == quote:
                quote = None
            elif quote == '"' and c == "\\" and i + 1 < n and text[i + 1] in '"\\$`\n':
                i += 1
                word += "" if text[i] == "\n" else text[i]
            elif quote == '"' and text.startswith("$(", i):
                j = _closing(text, i + 1)
                word += SUB_OPEN + text[i + 2:j] + SUB_CLOSE
                i = j
            elif quote == '"' and c == "`":
                raise Unparsed("a backtick")
            else:
                word += c
        elif c in "'\"":
            quote, has = c, True
        elif c == "\\" and i + 1 < n:
            i += 1
            if text[i] != "\n":
                word, has = word + text[i], True
        elif text.startswith("$(", i):
            j = _closing(text, i + 1)
            word, has = word + SUB_OPEN + text[i + 2:j] + SUB_CLOSE, True
            i = j
        elif c == "`":
            raise Unparsed("a backtick")
        elif c in " \t":
            end_word()
        elif c in ";\n":
            end_command(";", i, 1)
        elif text.startswith("&&", i) or text.startswith("||", i):
            end_command(text[i:i + 2], i, 2)
            i += 1
        elif c == "&" and (text[i - 1:i] == ">" or text[i + 1:i + 2] == ">"):
            word, has = word + c, True
        elif c == "&":
            end_command(";", i, 1)
        elif c == "|":
            end_stage()
            i += 1 if text[i + 1:i + 2] == "&" else 0
        elif c == "#" and not has:
            while i < n and text[i] != "\n":
                i += 1
            continue
        else:
            word, has = word + c, True
        i += 1
    if quote:
        raise Unparsed("an unclosed quote")
    end_command(";", n, 0)
    return cmds


def _printf(args):
    """printf's output for the forms a session pipes into a command: escapes, %s and %b taken in turn."""
    if not args:
        return ""
    unescape = lambda s: re.sub(r"\\([nt\\])", lambda m: {"n": "\n", "t": "\t", "\\": "\\"}[m.group(1)], s)
    fmt, rest = unescape(args[0]), list(args[1:])
    if "%" not in fmt.replace("%%", ""):
        return fmt.replace("%%", "%")
    out = ""
    while True:
        out += re.sub(r"%[sb]", lambda m: (unescape(rest.pop(0)) if m.group(0) == "%b" else rest.pop(0)) if rest else "",
                      fmt).replace("%%", "%")
        if not rest:
            return out


def text_filter(words, data, fs):
    """One stage of a pipeline that is no board command, over text: (output, exit), or None for a command or a
    form this does not know. Producers (cat of a file, echo, printf) and the filters sessions put after a board
    command (head, tail, grep, cut, awk's print of one field, wc -l, tee, tr -d, cat)."""
    cmd, args = words[0], words[1:]
    flags = [a for a in args if a.startswith("-") and len(a) > 1]
    rest = [a for a in args if not (a.startswith("-") and len(a) > 1)]
    lines = (data or "").splitlines()
    join = lambda ls: "".join(l + "\n" for l in ls)
    if cmd == "cat":
        if not rest or rest == ["-"]:
            return data or "", 0
        if all(fs.resolve(p) in fs.files for p in rest):
            return "".join(fs.files[fs.resolve(p)] for p in rest), 0
        return None
    if cmd == "echo":
        return " ".join(a for a in args if a not in ("-n", "-e")) + ("" if "-n" in args else "\n"), 0
    if cmd == "printf":
        return _printf(args), 0
    if cmd in ("head", "tail"):
        n = 10
        for i, a in enumerate(args):
            if re.fullmatch(r"-\d+", a):
                n = int(a[1:])
            elif a == "-n" and i + 1 < len(args) and args[i + 1].lstrip("+-").isdigit():
                n = int(args[i + 1].lstrip("-"))
            elif re.fullmatch(r"-n\d+", a):
                n = int(a[2:])
        if any(not a.startswith("-") and not a.lstrip("+-").isdigit() for a in args):
            return None
        return join(lines[:n] if cmd == "head" else lines[-n:] if n else []), 0
    if cmd in ("grep", "egrep", "rg"):
        letters = "".join(f[1:] for f in flags if not f.startswith("--"))
        if len(rest) != 1 or set(letters) - set("iEvcqFo") or any(f.startswith("--") for f in flags):
            return None
        try:
            rx = re.compile(re.escape(rest[0]) if "F" in letters else rest[0].replace("\\|", "|"),
                            re.I if "i" in letters else 0)
        except re.error:
            return None
        hits = [l for l in lines if bool(rx.search(l)) != ("v" in letters)]
        if "o" in letters and "v" not in letters:
            hits = [m.group(0) for l in lines for m in rx.finditer(l)]
        out = "" if "q" in letters else f"{len(hits)}\n" if "c" in letters else join(hits)
        return out, 0 if hits else 1
    if cmd == "cut":
        m = re.fullmatch(r"-d(.?)\s*-f(\d+)", " ".join(args).replace("-d ", "-d").replace("-f ", "-f").replace("'", ""))
        if not m:
            return None
        sep, k = m.group(1) or "\t", int(m.group(2))
        return join((l.split(sep) + [""] * k)[k - 1] if sep in l else l for l in lines), 0
    if cmd == "awk":
        m = re.fullmatch(r"\{\s*print \$(\d+)\s*;?\s*\}", rest[0].strip()) if len(rest) == 1 and not flags else None
        if not m:
            return None
        k = int(m.group(1))
        return join((l.split() + [""] * k)[k - 1] if k else l for l in lines), 0
    if cmd == "wc" and args == ["-l"]:
        return f"{len(lines)}\n", 0
    if cmd == "tee" and len(rest) == 1 and not flags:
        fs.files[fs.resolve(rest[0])] = data or ""
        return data or "", 0
    if cmd == "tr" and len(args) == 2 and args[0] == "-d":
        return (data or "").translate({ord(ch): None for ch in args[1].replace("\\n", "\n")}), 0
    return None


class BoardEnv(qs.Env):
    """question_sheet.Env with the board: a command line's `task` and `sminos task` commands are run by the
    stand-in, everything else by the sheet's canned shell and its simulator. `agent`: (id, type) when the session
    is a subagent's, which the sheet's stub and the stand-in are told."""

    def __init__(self, fs, sheet, board, words, shell_overrides=(), git_log="", agent=None):
        super().__init__(fs, sheet, shell_overrides, git_log)
        self.board, self.words, self.agent = board, words, agent
        self.skills, self.unparsed, self.call_id = [], [], None

    def tool(self, name, inp, call_id=None):
        self.call_id = call_id
        if name == "Skill":
            asked = str(inp.get("skill", "")).lstrip("/")
            self.skills.append(asked)
            if self.words.has("skill") and asked in (self.words.skill_name, self.words.skill_name.split(":")[1]):
                return f"Launching skill: {self.words.skill_name}\n\n{self.words.skill_body}", False
            if asked in ("sminos:sminos", "sminos"):
                body = re.sub(r"^---\n.*?\n---\n", "", (SMINOS_CLI.parents[1] / "SKILL.md").read_text(), flags=re.S)
                return "Launching skill: sminos:sminos\n\n" + body.strip(), False
            return f"Unknown skill: {asked}", True
        if name == qs.SHEET_TOOL and self.agent:
            try:
                return self.sheet.call(inp, asker=self.agent[0], call_id=call_id), False
            except qs.InputError as e:
                return f"InputValidationError: {e}. Nothing on the sheet changed.", True
        return super().tool(name, inp, call_id)

    # the board's part of the facts the shell simulator keeps to
    def simulate(self, command):
        client, model, facts = self.simulator
        listing = self.board.listing() or "(no tasks)"
        board = ("\n- `task` and `sminos task` work the human's task board, and none of them runs inside this command "
                 "line: the board is exactly what `sminos task list --all` prints now:\n"
                 + "\n".join("    " + l for l in listing.splitlines()) +
                 "\n  Nothing on the board changes while a command runs. A command that waits for a task to change "
                 "(a loop, a sleep, a watch) prints what it prints until the Bash tool's limit and then ends with "
                 "`Command timed out after 2m 0s`. Never print that a task was assigned, changed, completed or "
                 "declined.")
        self.simulator = (client, model, facts + board)
        try:
            return super().simulate(command)
        finally:
            self.simulator = (client, model, facts)

    def shell(self, command, as_human=False):
        """A command line, command by command, so that a canned answer for one command of a line answers that
        command alone. A line this cannot take apart goes whole to the sheet's shell when it names no board
        command, and to the simulator, recorded in `unparsed`, when it does."""
        try:
            return self.run_line(command, as_human)
        except Unparsed as e:
            if not MENTIONS.search(command):
                return super().shell(command)
            self.unparsed.append({"command": command, "why": str(e),
                                  "writes": bool(WRITE.search(command))})
            return self.simulate(command.strip()) if self.simulator else qs.NO_OUTPUT

    def run_line(self, command, as_human=False):
        text, docs = pull_heredocs(command)
        cmds = lex(text)
        for c in cmds:
            if any(s[0] in KEYWORDS for s in c["stages"]):
                raise Unparsed(f"a compound command ({c['stages'][0][0]})")
        restore = lambda src: MARK.sub(lambda m: "<<'TASKBOARDEOF'", src) + "".join(
            f"\n{docs[int(k)]}TASKBOARDEOF" for k in MARK.findall(src))
        outputs, last, variables = [], 0, {}

        def value(s):
            return re.sub(r"\$\{?(\w+)\}?", lambda m: variables.get(m.group(1), m.group(0)), s)
        for c in cmds:
            if (c["op"] == "&&" and last != 0) or (c["op"] == "||" and last == 0):
                continue
            stages = [[value(w) for w in s] for s in c["stages"]]
            first = stages[0]
            if first == ["unset", "CLAUDE_CODE_SESSION_ID"] or first == ["export", "CLAUDE_CODE_SESSION_ID="]:
                as_human, last = True, 0
                continue
            m = re.fullmatch(r"(\w+)=" + SUB_OPEN + r"(.*)" + SUB_CLOSE, first[0], re.S) if len(stages) == 1 and len(first) == 1 else None
            if m:  # VAR=$(...): the inner line's output, kept for the rest of the line
                inner = self.run_line(m.group(2), as_human) if MENTIONS.search(m.group(2)) else super().shell(m.group(2))
                variables[m.group(1)] = "" if inner == qs.NO_OUTPUT else inner.strip()
                last = self.last_exit if MENTIONS.search(m.group(2)) else 0
                continue
            if any(SUB_OPEN in w for s in stages for w in s):
                raise Unparsed("a command substitution")
            if not any(self.board_words(s) for s in stages):
                out, last = super().shell(value(restore(c["src"]))), 0
            else:
                out, last = self.pipeline(stages, docs, as_human)
            if out and out != qs.NO_OUTPUT:
                outputs.append(out.rstrip("\n"))
        self.last_exit = last
        return "\n".join(outputs) or qs.NO_OUTPUT

    last_exit = 0

    @staticmethod
    def strip(words):
        """A stage's words less what wraps its command: (words, removes the session's id, heredoc number, standard
        input's file, where standard output goes, whether standard error is dropped)."""
        words, human, doc, stdin, target, quiet = list(words), False, None, None, None, False
        kept, i = [], 0
        while i < len(words):
            w = words[i]
            m, r = MARK.fullmatch(w), REDIRECT.fullmatch(w)
            if m:
                doc = int(m.group(1))
            elif w.startswith("<<<"):
                stdin = ("text", (w[3:] or (words[i + 1] if i + 1 < len(words) else "")) + "\n")
                i += 0 if w[3:] else 1
            elif r and kept:
                fd, kind, where = r.group(1), r.group(2), r.group(3) if r.group(2) else r.group(4)
                if r.group(2) is None:
                    kind, fd = ">", ""
                if not where and i + 1 < len(words):
                    i += 1
                    where = words[i]
                if kind == "<":
                    stdin = ("file", where)
                elif fd == "2":
                    quiet = quiet or where == "/dev/null"
                elif not where.startswith("&"):
                    target = (where, kind == ">>")
            else:
                kept.append(w)
            i += 1
        while kept:
            w = kept[0]
            if re.fullmatch(r"\w+=.*", w, re.S):
                human = human or w.split("=", 1)[0] == "CLAUDE_CODE_SESSION_ID"
            elif w == "env":
                j = 1
                while j < len(kept) and (kept[j].startswith("-") or re.fullmatch(r"\w+=.*", kept[j], re.S)):
                    if kept[j] in ("-u", "--unset") and j + 1 < len(kept):
                        human = human or kept[j + 1] == "CLAUDE_CODE_SESSION_ID"
                        j += 1
                    elif kept[j] in ("-i", "-", "--ignore-environment") or kept[j].startswith(("-uCLAUDE_CODE_SESSION_ID",
                                                                                         "--unset=CLAUDE_CODE_SESSION_ID",
                                                                                         "CLAUDE_CODE_SESSION_ID=")):
                        human = True
                    j += 1
                kept = kept[j - 1:]
            elif w == "timeout" and len(kept) > 1:
                kept = kept[1:]
            elif w not in WRAPPERS:
                break
            kept = kept[1:]
        return kept, human, doc, stdin, target, quiet

    def board_words(self, stage):
        """Whether a stage runs a board command, or a shell that runs one."""
        words = self.strip(stage)[0]
        if not words:
            return False
        name = os.path.basename(words[0])
        if name in ("bash", "sh", "zsh") and "-c" in words:
            return bool(MENTIONS.search(words[words.index("-c") + 1] if words.index("-c") + 1 < len(words) else ""))
        return name == "task" or (name == "sminos" and len(words) > 1 and words[1] in ("task", "help"))

    def pipeline(self, stages, docs, as_human):
        data, errors, code = None, "", 0
        for stage in stages:
            words, human, doc, stdin, target, quiet = self.strip(stage)
            if not words:
                raise Unparsed("an empty stage")
            if doc is not None:
                data = docs[doc]
            elif stdin:
                data = stdin[1] if stdin[0] == "text" else self.fs.files.get(self.fs.resolve(stdin[1]), "")
            name = os.path.basename(words[0])
            if name in ("bash", "sh", "zsh") and "-c" in words and self.board_words(stage):
                out = self.run_line(words[words.index("-c") + 1], as_human or human)
                out, err, code = ("" if out == qs.NO_OUTPUT else out + "\n"), "", self.last_exit
            elif self.board_words(stage):
                args = list(words[1:])
                for i, a in enumerate(args[:-1]):  # a body file of the simulated project
                    if a == "--body-file" and args[i + 1] != "-":
                        path = self.fs.resolve(args[i + 1])
                        args[i + 1] = self.board.file(args[i + 1], self.fs.files.get(path))
                out, err, code = self.board.run(name, args, data, as_human or human, self.agent, self.call_id)
            else:
                done = text_filter(words, data, self.fs)
                if done is None:
                    raise Unparsed(f"a pipeline through {words[0]}")
                (out, code), err = done, ""
            if target:
                path = self.fs.resolve(target[0])
                if target[0] != "/dev/null":
                    self.fs.files[path] = (self.fs.files.get(path, "") if target[1] else "") + out
                out = ""
            errors += "" if quiet else err
            data = out
        return errors + (data or ""), code


# -- a session

def make_fs():
    """The sheet's project, with the files of task-board/world/ over it."""
    fs = ss.make_fs()
    world = DIR / "world"
    for p in sorted(world.rglob("*")):
        if p.is_file():
            fs.files[f"{qs.CWD}/{p.relative_to(world)}"] = p.read_text()
    return fs


def session(script, words, main=True, board=None, sheet=None, overrides=(), simulator=None, facts="", agent=None,
            setup=()):
    """A fresh environment (or one on a board and a sheet an earlier stage of the run left), the scripted prefix
    built through it, and the request's system and tools; as question_sheet.session, with the board. `setup`:
    steps run first for what they leave in the project (files, commits) and kept out of the conversation."""
    fs = make_fs()
    board = board or Board(words)
    env = BoardEnv(fs, sheet or qs.Sheet(fs), board, words, shell_overrides=list(overrides), git_log=ss.GIT_LOG,
                   agent=agent)
    if setup:
        qs.build(list(setup), env)
    prefix = qs.build(script, env)
    env.mark_committed()
    shown = [int(m) for m in re.findall(r"(\d+) passed, \d+ skipped", json.dumps(prefix))]
    if shown:  # the whole suite answers with the count the session last showed for it (question_sheet.session)
        world = sum(1 for p in fs.files if "/tests/" in p and p.endswith(".py")
                    for m in re.finditer(r"^((?:@pytest\.mark\.\w+.*\n)*)def test_", fs.files[p], re.M)
                    if "mark.slow" not in m.group(1))
        env.suite_extra = max(0, shown[-1] - world)
    if simulator:
        env.simulator = (*simulator, ss.SIM_FACTS + facts)
    return env, prefix, system_for(main), tools_for(words, main)


def cache_here(prefix, index):
    """A cache breakpoint on message `index`: where the part every run of a group shares ends, when what follows
    is the run's own."""
    m = prefix[index]
    if isinstance(m["content"], str):
        m["content"] = [{"type": "text", "text": m["content"]}]
    m["content"][-1]["cache_control"] = {"type": "ephemeral"}
    return prefix


def never(env, calls):
    """question_sheet.live's `done` for a run that ends only with its turn."""
    return False
