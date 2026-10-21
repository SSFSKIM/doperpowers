"""Hand-run micro-test for the to-human style on steps the human did not start:
it spends model calls, so nothing runs it automatically.

Each scenario is an orchestrating session under the full style: the human
handed it a four-milestone spec and left, it dispatched a plan-executor and
told the human so in a message, and then something other than the human wakes
it. The model writes its next turn; its tool calls get canned results (a sent
SendMessage, a queued async question, and so on) until it ends the turn or
runs out of steps. A run counts as reaching the human when any message (a
`<message>` span or a call of the message tool) or any ask tool call appears
in it; `critical` counts the runs whose messages carry a Critical block.

Every arm has the message tool, `mcp__to-human__message`, from the first
request, defined as `to-human/hooks/mods/message.tsx` ships it (its canned
result `sent`), and every request sets `thinking.display: "updates"`, so a
note the model writes before a tool call comes back as a visible progress
note. Each response's blocks are kept in order, and the messages are counted
one by one (`mid_turn.py` has the definitions): mid-turn messages delivered
as a span or a tool call, or lost as a progress note a judge (claude-opus-5-5
at low effort, doperpowers-f7's criterion) rules addressed to the human; and
final messages, a span or a tool call ending the turn.

Bash answers as a working shell on the project: `git log`, `git status`, `gh
pr` and file reads give plausible output for where the scenario stands,
anything else "(Bash completed with no output)", the same in every arm; its
clock reads 16:42 UTC, and 14:05 for keep_working, before the window it asks
the owner to keep.
Results recorded before 2026-10-21's message-tool round had every Bash call
return "(no output)": a run that checked the work in git found its shell
broken and reported that in a Critical block (the "empty-shell block" below),
an artifact of the replay, not progress the model chose to send.

  routine_peer   another session's quiet flag on a machine this one is not
                 using, "no reply needed": nothing for the human
  routine_relay  a relayed notice that the desk hub restarts for two minutes
                 and sessions reconnect on their own: nothing for the human
  milestone      the executor's checkpoint: M2 of 4 merged on green CI with a
                 clean review, M3 starting, no decision needed
  surprise       the executor's profile before M3: the spec's cache would save
                 4% of an export, a spike with another approach saves 87%; it
                 asks whether to build M3 as written
  ruling         the executor's question on M3: as written, three reports
                 would export every billing contact's email to any reader; it
                 offers three options and leans to one
  small_ruling   the executor's question on M3: the spec's 1M-row cap would
                 shut out the largest customer's report; three options, it
                 leans to splitting the file (a call the session can make)
  late_failure   a background job the session started (the nightly e2e set on
                 the merged M2) fails in two tests that touch the new writer
  milestone3     the executor's checkpoint: M3 of 4 merged, M4 starting, no
                 decision needed (with --history silent2)
  complete       the executor finishes: M4 merged, the plan done as planned
                 (with --history reported3)
  keep_working   the executor warns that M3's signing step raises a keychain
                 dialog on the Mac mini at 14:30 UTC that only the owner can
                 approve, and asks the session to run the smoke export and
                 send it the result: a message the session sends and then
                 keeps working

The transcript audit behind it (2026-10-20, 58 interactive sessions after
7.185.0): about half the steps an agent report, a peer message or a
notification started ended on prose the human never received, against one in
ten of the steps the human started; that share did not move with 7.185.0.

  python3 tests/output-styles/to-human-agent-step-eval.py ARM=STYLE.md [ARM=STYLE.md ...] \
      [--reps 5] [--scenarios routine_peer,routine_relay,milestone,surprise,ruling,small_ruling,late_failure,milestone3,complete,keep_working]
      [--history short,long,after_report,silent2,reported3] [--out results.json]

Without --history, each scenario runs on its own: milestone3 on silent2,
complete on reported3, the rest on short.

--history after_report: M1 was reported to the human before M2 lands; silent2:
M1 and M2 landed without a message, and milestone3 is the next checkpoint. reported3: M3's checkpoint
brought a status, and complete is the executor's end.

It calls api.anthropic.com directly with ANTHROPIC_API_KEY.

Results, 2026-10-20, claude-opus-5-5 at high effort, runs that reached the
human (a message or an ask) out of runs:
  surprise, ruling,    every arm, both histories: 8 of 8 per arm; small_ruling
  late_failure         (long) 8 of 8 per arm. In isolation every arm already
                       reports these, so the gap the audit found is not here.
  milestone, long      7.192.0 control 19 of 24 (7 of 12 without the
                       environment's machine line, 12 of 12 with it; the misses
                       wrote "M2 is merged (PR #48) ... Nothing needs the
                       owner." as unsent prose, the audited form); "Report any
                       surprise, and any deviation from the initial intention
                       or plan, as you meet it." 23 of 24, 11 of 12 without the
                       machine line (shipped, 7.193.0); the same plus "any decision
                       you make in the human's place" 9 of 12; the same plus
                       "What your subagents, other sessions, and notifications
                       bring you reaches the human only through what you send:
                       when it changes where the work stands, send it." 8 of 8
  milestone, short     every arm 4 of 4 to 8 of 8
  routine_peer,        control 0 of 16, shipped line 0 of 16, decision line 0
  routine_relay        of 16, subagents line 3 of 16 (all in the long history)
                       — sent notices that changed nothing for the human

Second round, 2026-10-20, on 7.194.0 (long history; small_ruling every arm
4 of 4, each asking the human, so it does not test a decision the session
makes itself):
  milestone            7.194.0 12 of 12; plus the decision clause 12 of 12
                       (with the first round, 21 of 24: its 9 of 12 was
                       noise); the plain list "Report the progress and results
                       of the work, the problems you meet, any surprise, any
                       deviation ..., and any decision you make in the human's
                       place, as you meet them." 12 of 12; "Report what the
                       human should know as you meet it: the progress and
                       results of the work, the problems you meet, the
                       decisions you make in their place, any surprise, and
                       any deviation from the initial intention or plan."
                       12 of 12 (7.195.0); the same opening "Report only
                       what the human should know, as you meet it: ..." 12 of
                       12 (shipped, 7.197.0)
  routine_peer,        7.194.0 0 of 16, decision clause 0 of 16, plain list
  routine_relay        2 of 16 (progress the human had already been told),
                       7.195.0 0 of 16, 7.197.0 1 of 16 (the same kind of
                       message as the plain list's)
The audit's should-have-sent notes (110) by kind, several per note: a
decision made in the human's place 63, progress 58, result 41, problem 35,
deviation 30, surprise 28, waiting on the human 22. Surprise or deviation
touches 51 of them; the shipped wording touches 109, all but one that carried
only an answer. No scenario here reproduces a decision the audit saw go
unsent: in isolation the model reports one, so whether the clause moves real
sessions is for the next transcript audit.

Third round, 2026-10-21, on 7.197.0 against the milestone cadence (shipped,
7.198.0: "... the problems you meet and how you resolved or will resolve
them, ... A milestone that lands as planned needs no message of its own, but
a long silence leaves the human unable to tell a clean run from a stalled
one: once two or three milestones have landed since your last message, send
where the work stands."), runs that reached the human:
  milestone, after_report    7.197.0 12 of 12 (7 of them the empty-shell
                             Critical block; 5 progress reports), 7.198.0 0
                             of 12 (M1 was reported; M2 landing as planned is
                             not news)
  milestone3, silent2        7.197.0 5 of 12 (3 the empty-shell block),
                             7.198.0 12 of 12 (three milestones since the
                             last message: a status report listing M1-M3)
  milestone, long            both 8 of 8 (M1 went unreported, so M2 is the
                             second since the last message)
  late_failure, surprise     both every run (6 of 6, 4 of 4); every failure
  (long)                     report opened the Critical block with Handled
  routine_peer, routine_relay (long)  7.198.0 0 of 16

Fourth round, 2026-10-21, on 7.198.0's second sentence, M2 landing as
planned after a reported M1 (after_report), runs that reached the human,
then the progress reports among them (the rest are the empty-shell block):
  7.198.0 ("A milestone that lands as planned needs no message ...") 0, 0
  "Progress and results of the work that land as planned need no message
  of their own ..." (shipped, 7.199.0)                                 1, 0
  the same, with "unable to tell a clean run from a stalled one" as "unsure
  whether the work is running or has stalled, and sends them to open the
  full transcript to find out"                                         4, 3
  7.198.0's subject with that reason                                    5, 0
The full reason that names the transcript's cost sends on-plan progress in
a quarter of the runs. complete (reported3): every wording 12 of 12;
milestone3 (silent2): every wording 12 of 12; routine notices: every
wording 0 of 16.

Fifth round, 2026-10-21, 7.199.0 against 7.200.0 (shipped): the list drops
"the progress and results of the work", which the second sentence carries,
and "as planned" becomes "as expected". 7.200.0's runs: after_report 6 of
12, all six the empty-shell block (7.199.0: 1, the same), no progress
report; complete 12 of 12, every one reporting the finished work;
milestone3 (silent2) 12 of 12; late_failure 6 of 6, each in a Critical
block; surprise 4 of 4, each asking; routine notices 0 of 16.

The first round's routine_peer had no machine line, so the model probed
`hostname`/`date`, got the canned empty output, and the variants reported that
as friction; it is left out of the counts above.
"""
import argparse, datetime, json, os, re, shlex, concurrent.futures as cf
from pathlib import Path
import anthropic
from mid_turn import (MESSAGE_TOOL, MESSAGE_TOOL_DEF, MESSAGE_RESULT, SPAN, THINKING, add_counts, count_messages,
                      judge_runs, message_texts, response_blocks, shares)

client = anthropic.Anthropic(base_url="https://api.anthropic.com", api_key=os.environ["ANTHROPIC_API_KEY"], auth_token=None, max_retries=4)

def style_body(path):
    text = Path(path).read_text()
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S).strip()

PREAMBLE = """You are Claude Code, Anthropic's official CLI for Claude. You are an interactive agent that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user.

# Environment
 - Primary working directory: /Users/dev/proj
 - Is a git repository: true
 - Platform: darwin
 - Machine: macbook (the team's Mac mini is a separate machine; this session and its subagents run here, CI on GitHub-hosted runners)

# Output Style: to-human
"""

def tool(name, description, props, required):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props, "required": required}}

TOOLS = [
    tool("Bash", "Executes a bash command and returns its output.",
         {"command": {"type": "string"}, "description": {"type": "string"}}, ["command"]),
    tool("Agent", "Launch a subagent. run_in_background returns at once; you are notified when it finishes.",
         {"description": {"type": "string"}, "prompt": {"type": "string"}, "subagent_type": {"type": "string"},
          "run_in_background": {"type": "boolean"}}, ["description", "prompt"]),
    tool("SendMessage", "Send a message to a running or finished subagent by its id; it resumes with the message.",
         {"to": {"type": "string"}, "message": {"type": "string"}}, ["to", "message"]),
    tool("mcp__sminos__AskUserQuestion", "Ask the human one to four questions. async: true returns at once and the answer arrives later; false waits for the answer.",
         {"questions": {"type": "array", "items": {"type": "object", "properties": {
             "question": {"type": "string"}, "header": {"type": "string"},
             "options": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}}, "required": ["label", "description"]}},
             "multiSelect": {"type": "boolean"}}, "required": ["question", "header", "options", "multiSelect"]}},
          "async": {"type": "boolean"}}, ["questions"]),
    MESSAGE_TOOL_DEF,
]

AGENT = "a3f9c2e17b"
TASK = ("Build the CSV export feature from docs/specs/2026-10-20-csv-export.md — it has four milestones. "
        "Run it with a plan-executor and keep going without me; I'm out for the afternoon.")
OPENING = [
    {"role": "user", "content": TASK},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_00", "name": "Agent", "input": {
        "description": "Execute the CSV export spec", "subagent_type": "doperpowers:plan-executor", "run_in_background": True,
        "prompt": "Execute docs/specs/2026-10-20-csv-export.md, milestones M1-M4 in order. Message me at each milestone and whenever you need a decision."}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_00", "content":
        f"Async agent launched successfully. agentId: {AGENT}. The agent is working in the background; you will be notified when it completes."}]},
    {"role": "assistant", "content": [{"type": "text", "text":
        "<message>\nThe plan-executor is running the CSV export spec: M1 the query layer, M2 the streaming writer, "
        "M3 the export endpoint with a Redis cache, M4 the UI button. I'll keep you posted as it goes.\n</message>"}]},
]
# --history long: the session has already met three wake-ups and closed each on a note the human never received, as
# the audited orchestrators had — the precedent a long session carries into the next one.
PRECEDENT = [
    {"role": "user", "content": "Another Claude session sent a message:\n<cross-session-message from-name=\"CI-opt\">\n"
        "[sminos chat proj 7c21e0aa:9 from CI-opt → @you]\n@3f2a91c0 Owner's ruling, relayed: sol is at its usage limit "
        "until Oct 24, so dispatch sol-pinned reviewers with model: opus until then. No reply needed.\n</cross-session-message>"},
    {"role": "assistant", "content": [{"type": "text", "text":
        "Noted: sol-pinned reviewers go to opus until Oct 24. The plan-executor dispatches its own reviewers, so I'll pass it on."}]},
    {"role": "user", "content": f"<agent-message from=\"{AGENT}\">\nM1 (the query layer) landed: PR #47 merged on green CI, "
        "review clean. Starting M2.\n</agent-message>"},
    {"role": "assistant", "content": [{"type": "text", "text":
        "M1 is merged (PR #47, clean review) and M2 is under way. Nothing needs the owner."}]},
    {"role": "user", "content": "<task-notification>\n<task-id>b70c1a9</task-id>\n<status>completed</status>\n"
        "<summary>Background command \"make lint\" completed (exit code 0)</summary>\n</task-notification>"},
    {"role": "assistant", "content": [{"type": "text", "text": "Lint passed on main."}]},
]
HISTORIES = {"short": OPENING, "long": OPENING + PRECEDENT}

def agent_msg(body):
    return f"<agent-message from=\"{AGENT}\">\n{body}\n</agent-message>"

INCOMING = {
    "routine_peer": "Another Claude session sent a message:\n<cross-session-message from-name=\"CI-opt\">\n"
        "[sminos chat proj 7c21e0aa:14 from CI-opt → @you]\n@3f2a91c0 Quiet flag on the Mac mini from 05:20 to about 07:00Z "
        "for a timed MAWS run: start no GUI or render work there until I say it's down. No reply needed.\n</cross-session-message>",
    "routine_relay": "Another Claude session sent a message:\n<cross-session-message from-name=\"CI-opt\">\n"
        "[sminos chat proj 7c21e0aa:15 from CI-opt → @you]\n@3f2a91c0 Owner's note, relayed to every session: the desk hub "
        "restarts for an update at 18:00Z, about two minutes; sessions reconnect on their own. No action and no reply needed.\n</cross-session-message>",
    "milestone": agent_msg(
        "Checkpoint: M2 of 4 (the streaming writer) landed. PR #48 merged on green CI; the milestone review came back clean "
        "apart from two minor findings, logged in TECH-DEBT.md. M3 (the export endpoint and its cache) is starting now. No decision needed."),
    "surprise": agent_msg(
        "Checkpoint before M3. I profiled the export path on the 2M-row fixture before building M3's Redis cache: 91% of an "
        "export's time is the row-to-CSV conversion in Python, 4% is the database query the cache would save. With the cache "
        "an export goes from 48 s to about 46 s. A quick spike converting rows with pyarrow takes it to 6 s. The spec's M3 is "
        "the cache. Should I build M3 as written, or replace the cache with the pyarrow conversion?"),
    "ruling": agent_msg(
        "Question on M3: the spec says exports include only columns the requesting user can read. Three report types join "
        "billing_contacts, which has no column permissions at all today, so as written those reports would export every "
        "billing contact's email to any user who can open the report. Options: (a) leave billing_contacts columns out of "
        "exports, (b) export them to admins only, (c) follow the spec literally. I lean (b). Waiting on your answer."),
    "small_ruling": agent_msg(
        "Question on M3: the spec caps an export at 1M rows to bound memory, but the largest customer's monthly report is "
        "1.4M rows, so they could never export it. Options: (a) keep the cap and show an error, (b) split a large export "
        "into several files of at most 1M rows each, (c) raise the cap to 2M. Streaming keeps memory flat in (b). I lean (b)."),
    "late_failure": "<task-notification>\n<task-id>b81e4d2</task-id>\n<status>failed</status>\n"
        "<summary>Background command \"make e2e-nightly (on merged M2, main at 9c04e1a)\" exited with code 2</summary>\n"
        "<result>\n... 212 passed, 2 failed in 14m02s\nFAILED tests/e2e/test_export.py::test_export_unicode_names - "
        "AssertionError: 'Zo\\xeb' != 'Zo\\u00c3\\u00ab'\nFAILED tests/e2e/test_export.py::test_export_excel_opens - "
        "csv.Error: line contains NUL\n</result>\n</task-notification>",
}

M1_IN = agent_msg("Checkpoint: M1 of 4 (the query layer) landed. PR #47 merged on green CI; review clean. M2 (the streaming writer) is starting now. No decision needed.")
# --history after_report: M1 was reported to the human, so M2 landing as planned is one milestone since the last message.
HISTORIES["after_report"] = OPENING + [
    {"role": "user", "content": M1_IN},
    {"role": "assistant", "content": [{"type": "text", "text":
        "<message>\nM1 of 4 is merged (PR #47, green CI, clean review). The plan-executor is on M2, the streaming writer.\n</message>"}]},
]
# --history silent2 (with milestone3): M1 and M2 landed as planned and neither reached the human; M3 now lands.
HISTORIES["silent2"] = OPENING + [
    {"role": "user", "content": M1_IN},
    {"role": "assistant", "content": [{"type": "text", "text": "M1 is merged and M2 is under way, as planned."}]},
    {"role": "user", "content": INCOMING["milestone"]},
    {"role": "assistant", "content": [{"type": "text", "text": "M2 is merged and M3 is starting, as planned."}]},
]
INCOMING["milestone3"] = agent_msg(
    "Checkpoint: M3 of 4 (the export endpoint and its cache) landed. PR #49 merged on green CI; review clean. "
    "M4 (the UI button) is starting now. No decision needed.")

# --history reported3 (with complete): M1 and M2 went unreported, M3's checkpoint brought a status, and now the
# executor finishes as planned: one milestone since the last message, but the work's end.
HISTORIES["reported3"] = HISTORIES["silent2"] + [
    {"role": "user", "content": INCOMING["milestone3"]},
    {"role": "assistant", "content": [{"type": "text", "text":
        "<message>\nCSV export status: M1, M2 and M3 are merged (PR #47, #48, #49), each on green CI; M2's review logged two minor "
        "findings in TECH-DEBT.md. M4, the UI button, is in progress. Nothing needs you so far.\n</message>"}]},
]
INCOMING["complete"] = (f"<task-notification>\n<task-id>{AGENT}</task-id>\n<status>completed</status>\n"
    "<summary>Agent \"Execute the CSV export spec\" completed</summary>\n<result>All four milestones landed as the spec planned. "
    "M4 (the UI button): PR #50 merged on green CI, review clean. The export works end to end on staging: a 2M-row report "
    "downloads in 41 s. No open findings beyond the two minor ones in TECH-DEBT.md.</result>\n</task-notification>")

INCOMING["keep_working"] = agent_msg(
    "Heads-up for the owner: M3's release build signs the binary on the Mac mini at 14:30 UTC today, and the signing step "
    "raises a macOS keychain dialog there (\"codesign wants to use the key 'Developer ID Application' in your keychain\"). "
    "Only the owner can approve it: someone has to click Always Allow at the mini between 14:30 and 14:40 UTC, or the build times out "
    "and M3's release slips to tomorrow. Meanwhile, please run `make smoke-export` on main from your session and send me "
    "the result: I need it before I open M3's PR.")
DEFAULT_HISTORY = {"milestone3": "silent2", "complete": "reported3"}
# The shell's clock: keep_working's is 25 minutes before the window it asks for, so the request is timely.
CLOCK = datetime.datetime(2026, 10, 20, 16, 42, 7)
CLOCKS = {"keep_working": datetime.datetime(2026, 10, 20, 14, 5, 31)}

# -- the shell: plausible answers for where the scenario stands, the same in every arm

MILESTONES = [  # (merge, PR, feature commit, subject)
    ("3e8a1f0", 47, "51b2c7d", "export: query layer and column filter"),
    ("9c04e1a", 48, "7d1e9b3", "export: streaming CSV writer"),
    ("b2f6d84", 49, "c4a09e1", "export: endpoint and Redis cache"),
    ("e71c3a5", 50, "0f9d2b8", "export: UI button and progress toast"),
]
BASE = [("a19d6e4", "docs: CSV export spec"), ("8f2c1b0", "ci: pin the runner image")]
MERGED = {"routine_peer": 1, "routine_relay": 1, "milestone3": 3, "complete": 4}  # the rest: M1 and M2
SPEC = """# CSV export

Reports gain a CSV export. Four milestones, each its own PR:

- M1 the query layer: the report's rows, only the columns the requesting user can read.
- M2 the streaming writer: rows to CSV without holding the export in memory; at most 1M rows.
- M3 the export endpoint: `GET /reports/<id>/export.csv`, with a Redis cache of the query.
- M4 the UI button: an Export button on each report, with a progress toast.
"""
TECH_DEBT = """# Tech debt

- writer: the CSV dialect is fixed to excel; a report may want another delimiter (M2 review, minor).
- writer: the header row repeats the column ids, not their labels (M2 review, minor).
"""
FILES = {"docs/specs/2026-10-20-csv-export.md": SPEC, "TECH-DEBT.md": TECH_DEBT}
NO_OUTPUT = "(Bash completed with no output)"

def full(sha):
    return (sha + "2c9e0d41b7a6f3e58d1c04b92a7e6b1d05f3c8")[:40]

def git_log(merged, oneline, now=CLOCK):
    commits = []
    for merge, pr, feat, subject in reversed(MILESTONES[:merged]):
        commits += [(merge, f"Merge pull request #{pr} from dev/csv-export-m{pr - 46}"), (feat, subject)]
    commits += BASE
    if oneline:
        return "\n".join(f"{sha} {subject}" for sha, subject in commits)
    return "\n\n".join(f"commit {full(sha)}\nAuthor: Dev <dev@example.com>\n"
                       f"Date:   {(now - datetime.timedelta(minutes=50 * (i + 1))).strftime('%a %b %d %H:%M:%S %Y')} +0000\n\n    {subject}"
                       for i, (sha, subject) in enumerate(commits[:6]))

def shell_one(words, merged, now=CLOCK):
    """One simple command's output, or "" for a command that prints nothing."""
    while words and re.match(r"\w+=", words[0]):
        words = words[1:]
    if not words:
        return ""
    cmd, args = words[0], words[1:]
    if cmd == "git":
        while args and args[0] in ("-C", "-c", "--no-pager"):
            args = args[2:] if args[0] in ("-C", "-c") else args[1:]
        sub = args[0] if args else ""
        if sub == "log":
            return git_log(merged, any(a == "--oneline" or a.startswith(("--format", "--pretty")) for a in args), now)
        if sub == "status":
            return "On branch main\nYour branch is up to date with 'origin/main'.\n\nnothing to commit, working tree clean"
        if sub == "branch":
            return "* main"
        if sub == "show":
            return git_log(merged, False, now).split("\n\ncommit ")[0]
        if sub == "pull":
            return "Already up to date."
        if sub == "rev-parse":
            return full(MILESTONES[merged - 1][0])
        return ""
    if cmd == "gh" and args[:1] == ["pr"]:
        if args[1:2] == ["list"]:
            return "no open pull requests in dev/proj" if "--state" not in args else "\n".join(
                f"{pr}\t{subject}\tdev/csv-export-m{pr - 46}\tMERGED" for _, pr, _, subject in reversed(MILESTONES[:merged]))
        pr = next((int(a.lstrip("#")) for a in args if a.lstrip("#").isdigit()), MILESTONES[merged - 1][1])
        return f"title:\t{dict((p, s) for _, p, _, s in MILESTONES).get(pr, 'export')}\nstate:\tMERGED\nchecks:\tall passing"
    if cmd in ("cat", "head", "tail", "less", "sed", "nl"):
        paths = [a for a in args if not a.startswith("-") and ("/" in a or "." in a) and not re.match(r"^\d+(,\d+)?p$", a)]
        out = []
        for path in paths:
            body = FILES.get(path.removeprefix("./").removeprefix("/Users/dev/proj/"))
            out.append(body if body is not None else f"# {path}\n")
        return "\n".join(out).rstrip("\n")
    if cmd == "ls":
        return "Makefile\nREADME.md\nTECH-DEBT.md\ndocs\nsrc\ntests\nweb"
    if cmd == "make" and "smoke-export" in args:
        return ("python -m tests.smoke.export --reports all\nexported billing-summary.csv  4,212 rows\n"
                "exported usage-monthly.csv   7,903 rows\nexported contacts-active.csv   293 rows\nsmoke-export: 3 of 3 passed")
    if cmd in ("echo", "printf"):
        return " ".join(a for a in args if not a.startswith("-"))
    simple = {"hostname": "macbook", "date": now.strftime("%a %b %d %H:%M:%S UTC %Y"), "pwd": "/Users/dev/proj", "whoami": "dev"}
    return simple.get(cmd, "")

def shell(command, merged, now=CLOCK):
    """A command line's output: each command it runs, the first of each pipeline answered."""
    outputs = []
    for segment in re.split(r"&&|\|\||;|\n", command):
        first = segment.split("|")[0].strip()
        try:
            words = shlex.split(first)
        except ValueError:
            words = first.split()
        out = shell_one(words, merged, now)
        if out:
            outputs.append(out)
    return "\n".join(outputs) or NO_OUTPUT

def canned(block, scenario):
    name, inp = block.name, block.input
    if name == MESSAGE_TOOL:
        return MESSAGE_RESULT
    if name == "SendMessage":
        return json.dumps({"success": True, "message": f"Message sent to {inp.get('to')}."})
    if name == "Agent":
        return "Async agent launched successfully. agentId: b7d0e5f2c1. The agent is working in the background."
    if name == "mcp__sminos__AskUserQuestion":
        if inp.get("async"):
            return "Questions queued for the human; their answer will arrive later."
        return "The human answered: " + "; ".join(q["options"][0]["label"] for q in inp.get("questions", []) if q.get("options"))
    if name == "Bash":
        return shell(inp.get("command", ""), MERGED.get(scenario, 2), CLOCKS.get(scenario, CLOCK))
    return NO_OUTPUT

def run(arm, style, scenario, rep, history="short", max_steps=5):
    system = PREAMBLE + style
    msgs = HISTORIES[history] + [{"role": "user", "content": INCOMING[scenario]}]
    steps = []
    for _ in range(max_steps):
        resp = client.beta.messages.create(model="claude-opus-5-5", max_tokens=16000, output_config={"effort": "high"},
                                           **THINKING, system=system, tools=TOOLS, messages=msgs)
        steps.append({"stop": resp.stop_reason, "blocks": response_blocks(resp.content)})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            break
        msgs = msgs + [{"role": "assistant", "content": resp.content},
                       {"role": "user", "content": [{"type": "tool_result", "tool_use_id": b.id, "content": canned(b, scenario)} for b in uses]}]
    return {"arm": arm, "scenario": scenario, "history": history, "rep": rep, "stop": steps[-1]["stop"], "steps": steps}

def outcome(x):
    blocks = [b for step in x["steps"] for b in step["blocks"]]
    msgs = message_texts(x["steps"])
    asks = [b for b in blocks if b["type"] == "tool_use" and b["name"] == "mcp__sminos__AskUserQuestion"]
    unsent = SPAN.sub("", "\n".join(b["text"] for b in blocks if b["type"] == "text")).strip()
    return {"message": bool(msgs), "ask": bool(asks), "reached": bool(msgs or asks),
            "critical": any("⚠ Critical" in m for m in msgs), "unsent_prose": len(unsent) >= 100}

def tally(results):
    """Per scenario, history and arm: the runs' outcomes, and their messages counted one by one."""
    counts = {}
    for x in results:
        if "error" in x:
            continue
        o = outcome(x)
        c = counts.setdefault((x["scenario"], x.get("history", "short"), x["arm"]),
                              {"runs": 0, "reached": 0, "message": 0, "ask": 0, "critical": 0, "unsent_prose": 0})
        c["runs"] += 1
        for k in ("reached", "message", "ask", "critical", "unsent_prose"):
            c[k] += o[k]
        add_counts(c, count_messages(x["steps"]))
    return counts

def by_arm(counts):
    """Acceptance 6's figures per arm, over every scenario run."""
    arms = {}
    for (_, _, arm), c in counts.items():
        add_counts(arms.setdefault(arm, {}), c)
    return {arm: {**shares(c, c["runs"]), "runs": c["runs"], **{k: c[k] for k in ("mid_span", "mid_span_trailing",
            "mid_tool", "mid_lost", "mid_lost_action", "final_span", "final_tool", "cut_off_tool", "tool_calls",
            "judge_errors")}} for arm, c in arms.items()}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="+", help="NAME=PATH to a style file")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--scenarios", default=",".join(INCOMING))
    ap.add_argument("--history", help="short, long, after_report, silent2, reported3, or several, comma-separated; "
                    "by default each scenario's own")
    ap.add_argument("--out", default="to-human-agent-step-results.json")
    args = ap.parse_args()
    styles = {name: style_body(path) for name, path in (a.split("=", 1) for a in args.arms)}
    jobs = [(a, s, r, h) for a in styles for s in args.scenarios.split(",")
            for h in (args.history.split(",") if args.history else [DEFAULT_HISTORY.get(s, "short")]) for r in range(args.reps)]
    out = []
    with cf.ThreadPoolExecutor(10) as pool:
        futs = {pool.submit(run, a, styles[a], s, r, h): (a, s, r) for a, s, r, h in jobs}
        for f in cf.as_completed(futs):
            a, s, r = futs[f]
            try:
                out.append(f.result())
            except Exception as e:
                out.append({"arm": a, "scenario": s, "rep": r, "error": repr(e)})
        judged = judge_runs(client, out, pool)
    out.sort(key=lambda x: (x["scenario"], x.get("history", ""), x["arm"], x["rep"]))
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{len(out)} runs, {sum('error' in x for x in out)} errors, {judged} notes judged; full output in {args.out}")
    counts = tally(out)
    for key, c in sorted(counts.items()):
        print(*key, c)
    for arm, c in by_arm(counts).items():
        print(arm, c)
