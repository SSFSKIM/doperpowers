# `.smns` acceptance record

The Acceptance section of `2026-10-13-smns-project-log-design.md`, run on
2026-10-14 from the `smns-project-log` branch after main (7.152.1) was merged
into it. Steps 1–5 ran live, in real interactive Claude Code sessions
(harness 2.1.299) driven through tmux. Step 6 ran on the stub harness, and
step 7 ran the suites.

| step | verdict |
| --- | --- |
| 1. `list` shows both sessions with no `seat add` | pass |
| 2. untagged is recorded, `@b` delivers, `@all` wakes | pass |
| 3. `<message>` and an async ask reach `chat --host` | pass, with finding F1 |
| 4. spawn provenance, retiring the spawner, ambiguous `@c` | pass, with finding F2 |
| 5. `charge` and `derive` | pass, with a note on the 120-character cut |
| 6. two homes, the mirror, the daemon, under two seconds | pass (stub harness) |
| 7. the three suites | pass |

## Setup

- `R` = `/tmp/smns-acc/R`: `git init`, then `sminos project init --name
  demo`, then `.smns` committed. The project id was
  `d8236eb9-1b98-4a2b-8a51-853456e06c54`.
- `SMINOS_HOME=/tmp/smns-acc/sminos` was set in every process that could run
  sminos or the hook. That covered the tmux server, which was started on its
  own socket (`tmux -L smnsacc`) from an environment scrubbed of the
  controlling session's `CLAUDE_CODE_*`, `CLAUDECODE`, and `CMUX_*`
  variables. It also covered each `claude` (checked with `ps eww` on every
  session pid) and every operator CLI call, which went through a wrapper
  that also unset `CLAUDE_CODE_SESSION_ID`. The real `~/.claude/sminos` had
  no file newer than the run's start when the run ended.
- Each session was started as `claude --plugin-dir <worktree> --settings
  /tmp/smns-acc/settings.json --model sonnet`, where the settings file is
  `{"enabledPlugins": {"doperpowers@doperpowers": false}}`. In `/plugin` →
  Installed, `doperpowers` was listed once, as `inline` (this branch). Every
  `stop_hook_summary` lists two Stop hooks, the human's `notify.sh` and one
  `smns-record.sh`, so one copy was loaded. `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`
  came from the human's settings, and the ask mod ran.
- Sessions: `a` (6065de22, renamed with `/rename a`); `b`, left with its
  derived name `r-4f` (181b8631); `r-c3` (4042325f), a derived-name session
  given ten prompts for step 5; a third session renamed `c` (47398437); and
  the seat `c` spawned in step 4 (114730d8).
- Every `sminos` call inside a session was typed into that session's prompt
  as a request ("Run this shell command and show me its output: …"). The
  session ran it through its Bash tool. The outputs below are the tool
  results from the transcripts, not the sessions' paraphrases.
- Accepting the workspace-trust dialog for `R` let the harness record that
  directory in `~/.claude.json`, as it does for any interactive session.
  That entry was left in place. Editing `~/.claude.json` while the human's
  sessions run could race the harness's own writes.

## 1. `sminos list` with no `seat add`

Operator, in `R`, after both sessions had started and before anything else
had run:

    $ sminos list
    demo
      r-4f   idle
      a      idle

The log already held each session's `joined`, written by
`hooks/smns-record.sh` at `SessionStart`. a's event was written before the
rename, so it carries `alias: "r-f6", name_source: "derived"`. `list` takes
the live harness name.

**Verdict: pass.** The `demo` heading shows rows `a` and `b` (`r-4f`), each
with a state word.

## 2. Untagged, `@b`, `@all`

In a:

    $ sminos say "merged #12"
    recorded 6065de22:2 in demo

b started no turn. Its transcript file did not yet exist, its harness status
stayed `idle`, and its pane was unchanged. In b:

    $ sminos chat
    chat demo · 1 new
    16:02:52 6065de22:2 a → *  merged #12

In a:

    $ sminos say "@r-4f look at X"
    recorded 6065de22:3 in demo
    r-4f: sent

b started a turn whose first content was the peer frame (transcript line
40, `origin.kind: "peer"`):

    Another Claude session sent a message:
    [sminos chat demo 6065de22:3 from a → @you]
    @r-4f look at X

b read the chat and asked a what X was (`@a got "look at X" but X is a
literal placeholder…`). a woke on that frame and answered, so the delivery
also worked in the opposite direction. In a:

    $ sminos say "@all rebase in progress"
    recorded 6065de22:8 in demo
    r-4f: sent

The event's audience is the members that were live when it was submitted.
The sender is not among them:

    {"seq": 8, "kind": "say", "from": "a", "to": [{"session": "181b8631-…", "alias": "r-4f"}],
     "text": "@all rebase in progress", "wake": true}

b started a turn on `[sminos chat demo 6065de22:8 from a → @all | unread 1]`
and answered "It's an FYI that asks for nothing … I'm taking no action."

**Verdict: pass.**

## 3. Messages and questions to the host

In a, one turn with no tools. The prompt asked for the two lines verbatim,
and the assistant record is exactly:

    <message>done with the parser</message>
    `<message>not this</message>`

After the turn:

    $ sminos chat --host -n 3
    …
    16:05:23 a: done with the parser

Nothing was recorded for the backticked tag. a then called
`mcp__doperpowers__AskUserQuestion` with `async: true`:

    {"questions": [{"question": "Which parser should we keep?", "header": "Parser", "multiSelect": false,
      "options": [{"label": "Recursive descent", …}, {"label": "PEG", …}]}], "async": true}

The tool returned its accepted result at once, and the turn ended:

    $ sminos chat --host -n 3
    …
    16:06:50 a asks (open): Which parser should we keep?
        choices: Recursive descent · PEG

The answer was given through the session's UI. The `[ answer ]` button in
the `1 open question` band was clicked with an SGR mouse event sent through
`tmux send-keys -H`, which opened the engine's dialog. `PEG` was then chosen
with ↓ and Enter. The mod delivered the answer as a plugin prompt (`The
human responded to your async AskUserQuestion (call
toolu_013EtwMgTXYK2Kw2cZSMiST5): …`), and a's next Stop recorded it:

    $ sminos chat --host -n 3
    …
    16:06:50 a asks: Which parser should we keep?
        choices: Recursive descent · PEG
        answered: Your questions have been answered: "Which parser should we keep?"="PEG". You can now continue with these answers in mind.

**Verdict: pass.** See F1: one earlier mark in this run was exported one
turn late.

## 4. Spawn, retire the spawner, ambiguous tag

This step ran after step 5 because `sminos retire a` would have taken `a`
out before step 5 set its line.

In a:

    $ sminos spawn c "wait for instructions" --model sonnet --settings /tmp/smns-acc/seat-settings.json
    seat spawned: R/c  [114730d8 / 114730d8-0ebe-4093-86b7-a53dd7ac9421]  status=working  (reply: sminos reply 114730d8)
    $ sminos list
    demo
      c      busy  · by a
      r-c3   idle  This session owns the parser's tokenizer: …
      r-4f   idle  owns the GUI tool
      a      busy  parser

Two flags were added to the command as written, `--model sonnet` and
`--settings`, the latter carrying `{"env": {"SMINOS_HOME":
"/tmp/smns-acc/sminos"}}`. A probe had shown that a `claude --bg` session
does not inherit its launcher's environment. A probe launched with
`SMINOS_HOME` set ran `printenv SMINOS_HOME` and got exit 1. The same probe
with that `--settings` file printed `/tmp/smns-acc/sminos`. Without the
file, seat c would have read its preamble's `sminos chat -n 30` against the
human's real registry and run the one-way import there (F3).

c read the preamble as a live seat. Its first tool call was `<worktree>/…/sminos
chat -n 30`, which printed this run's five chat lines. It then ran `sminos
status c "idle, waiting for instructions"`.

In b:

    $ sminos retire a
    retired a (session 6065de22; it holds no seat, so nothing is kept)
    $ sminos list
    demo
      a      idle  parser
      c      idle  · now: idle, waiting for instructions  · by a
      r-c3   idle  This session owns the parser's tokenizer: …
      r-4f   busy  owns the GUI tool

c is still live in `list`. a is back at the top, see F2. A third session
was opened in `R` and renamed with `/rename c`. In b:

    $ sminos list
    demo
      c#47398437   idle
      a            idle  parser
      c#114730d8   idle  · now: idle, waiting for instructions  · by a
      r-c3         idle  This session owns the parser's tokenizer: …
      r-4f         busy  owns the GUI tool
    $ sminos say "@c hi"
    Exit code 4
    sminos: ambiguous @c matches: c#114730d8, c#47398437

**Verdict: pass.** c keeps `· by a` and stays live after its spawner is
retired. Both c rows show their `#short`, and the tag is refused naming
both. See F2 for what happened to a.

## 5. `charge` and `derive`

In b:

    $ sminos charge r-4f "owns the GUI tool"
    r-4f in charge of: owns the GUI tool

`list --json` then gave `r-4f`: `"charge": "owns the GUI tool",
"charge_source": "set"`. In a:

    $ sminos charge a "parser"
    a in charge of: parser
    $ sminos list
    demo
      r-c3   idle  Tokenizer ownership acknowledgment
      r-4f   idle  owns the GUI tool
      a      busy  parser

`parser` is a's line, and a is still its alias. Before this, a's line had
been its user-set name (`charge_source: "name"`).

Derive needs a session with ten human prompts, a derived name, and no line.
`r-c3` was given ten one-line prompts that made it the owner of the
parser's tokenizer. Its line was then the harness's `ai-title` (`charge_source:
"title"`, source 4). In b:

    $ sminos derive r-c3
    r-c3: This session owns the parser's tokenizer: the lexer that turns source text into tokens, plus the peek/next interface the

While the fork ran, `$SMINOS_HOME/internal/93253` and the fork's
`a9be32cf-….jsonl` both existed. Afterwards:

| | before | after |
| --- | --- | --- |
| `list --json` members | 3 | 3 |
| transcript files in `R`'s project dir | 3 | 3 |
| internal markers | 0 | 0 |
| `chat --host` events | 22 | 23 |

`list --json`: `r-c3` `"charge_source": "derived"`, and the log holds an
`in-charge` event with `source: "derived"` in r-c3's file. The one new host
event is from `r-4f`, not `r-c3` or the fork: it is b's own `<message>`
reporting the command's output to its human, because b ran `derive` in a
turn. The fork recorded nothing.

**Verdict: pass.** One note: the derived line is cut at 120 characters in
the middle of a phrase ("…interface the"), which is §5's rule as written.
A cut at a word boundary, or a prompt asking for a shorter answer, would
read better. This is cosmetic.

## 6. Two homes, the mirror, the daemon

The Concrete Steps' hand run starts real `claude` under temporary `HOME`s,
which cannot authenticate, so the ticked steps are the suite's two-home
transcript (`SMINOS_FAMILY_ONLY=1 SMINOS_TRANSCRIPT=1
tests/sminos/run-sminos-tests.sh`, 791/791 passed, `<md>` the test's temp
dir):

    $ env $H1 sminos project init --name demo --remote <md>/remote.git
      project demo (a767609d-…) at <md>/R/.smns — commit it, so every clone is the same project
    $ env $H1 sminos spawn a "wait for instructions"
      seat spawned: R/a  [00000001 / 00000001-e808-4cad-a7e0-c1e6447bad28]  status=idle  (reply: sminos reply 00000001)
    $ env $H2 sminos spawn b "wait for instructions"
      seat spawned: R/b  [00000002 / 00000002-e808-4cad-a7e0-c1e6447bad28]  status=idle  (reply: sminos reply 00000002)
    $ env $H1 sminos daemon tick
      demo: synced · reconciled 0 · published 1 · delivered 0 · pushed
    $ env $H2 sminos project attach
      attached demo to <md>/remote.git
    $ env $H2 sminos daemon tick
      demo: synced · reconciled 0 · published 1 · delivered 0 · pushed
    $ env $H1 sminos daemon tick
      demo: synced · reconciled 0 · published 0 · delivered 0
    $ env $H1 sminos list
      demo
        b   busy @h2 0s
        a   idle
    $ env $H1 CLAUDE_CODE_SESSION_ID=<a> sminos say "@b hello"
      recorded 00000001:3 in demo
      b: recorded (on h2)
    $ env $H1 sminos daemon tick
      demo: synced · reconciled 0 · published 0 · delivered 0 · pushed
    $ env $H2 sminos daemon tick
      demo: synced · reconciled 0 · published 0 · delivered 1 to b
    $ env $H2 sminos daemon tick
      demo: synced · reconciled 0 · published 0 · delivered 0
    $ env $H2 sminos daemon tick    # b went idle
      demo: synced · reconciled 0 · published 0 · delivered 0
    $ env $H2 sminos daemon tick
      demo: synced · reconciled 0 · published 1 · delivered 0 · pushed
    $ env $H1 sminos daemon tick
      demo: synced · reconciled 0 · published 0 · delivered 0
    $ env $H1 sminos list
      demo
        b   idle @h2 1s
        a   idle
    $ env $H1 sminos daemon run --interval 1 & env $H2 sminos daemon run --interval 1 &
    $ env $H1 CLAUDE_CODE_SESSION_ID=<a> sminos say "@b while both daemons run"
      recorded 00000001:5 in demo
      b: recorded (on h2)
      (landed in b's socket after 0.8s)

The suite asserts that b's socket held nothing after the h1 tick. It also
asserts that the frame `[sminos chat demo 00000001:… from a → @you]` holds
`@b hello`, and that b holds it once.

**The timed run, by hand.** A separate driver used the suite's stub `claude`
and inbox stand-in, copied verbatim from `run-sminos-tests.sh`, with two
homes (`HOME`, `SMINOS_HOME`, `DAEMON_HOST=h1`/`h2`) and a bare repository
on local disk. It ran `sminos daemon run --interval 1` under both homes
and timed each `say "@b timed N"` from a until it landed in b's socket.
Before the loop it went through attach, tick, and `list` (`b idle @h2 1s`).
Two runs:

    n=10  min 0.65s  median 1.10s  max 1.46s  over 2 s: 0   frames 10 (distinct 10)
    n=30  min 0.52s  median 1.12s  max 1.53s  over 2 s: 0   frames 30 (distinct 30)

**Verdict: pass.** Each `say` landed within two seconds, the slowest of 40
in 1.53 s, and each was delivered once. The sessions were the stub's, not
real ones: two real machines were not available to this run.

## 7. The suites

    $ tests/sminos/run-sminos-tests.sh
    all 1453 assertions passed
    $ tests/issue-tracker/test-execute-dispatch.sh
    all tests passed
    $ tests/issue-tracker/test-review-dispatch.sh
    all tests passed
    $ scripts/lint-shell.sh
    Linting 1 shell files      (rc 0)

**Verdict: pass.**

## Findings

- **F1: a Stop can run before the turn's last record is on disk.** a's
  first `<message>` (record `375c7176`, written 16:02:53.993) was exported at
  a's next Stop (16:04:07), 73 s late. The other 23 marks in the run were
  exported 0.1–0.2 s after they were written. a's first Stop did run
  `smns-record.sh` (112 ms), and its position was `{uuid: "", offset: 0}`,
  so it read from the start of the file. The record was not yet on disk:
  the harness queues transcript writes and flushes every 100 ms
  (`FLUSH_INTERVAL_MS = 100` in the 2.1.292 bundle), and the Stop hooks are
  started without a flush first. A late mark is exported at the next Stop.
  The last mark of a session's last turn waits until the session is resumed
  and stops again. The Stop payload carries `last_assistant_message`, which
  is a deterministic signal: when it holds a mark and no assistant record
  past the position carries that text, `record` can poll briefly for the
  flush within its 5 s budget.
- **F2: `retire` of an interactive member does not hold.** `sminos retire a`
  recorded `retired` (seq 16), but the harness lists an interactive session
  with `id: null` (`claude agents --json --all`), so `claude stop` had
  nothing to stop. The next reading verb (b's `list`, 2 s later)
  reconciled a back in as a live session (`joined`, seq 17). The printed
  "retired a" is therefore untrue for any human-opened session. Two
  options: refuse `retire` for a member with no stoppable harness row and
  say its human closes it, or have reconciliation re-join a session retired
  by `retire` only if its process started after the retirement.
- **F3: a spawned seat does not inherit `SMINOS_HOME`.** `claude --bg` hands
  the launch to the harness's supervisor, which claims a pre-started spare,
  so the seat's environment is the supervisor's, not the spawner's. With
  the default home this is invisible. With a non-default `SMINOS_HOME`, a
  seat's sminos calls reach a different registry from its spawner's, and
  for a test registry that registry is the human's real one, where `migrate`
  runs. `spawn` could pass the home through a `--settings` overlay, or the
  docs could say the home must be the default for spawned seats. The test
  suite's stub `claude` inherits its environment, so this does not show
  there.
- In step 4 the spawned seat c ran on the human's installed doperpowers
  (7.152.1), not on this branch, because `--plugin-dir` applies only to
  the sessions it was given to. So c had no `smns-record.sh` hook. It was a
  member through its seat record, and its CLI was this branch's (the
  preamble names the worktree's launcher).

## Cleanup

The tmux server was killed, which ended the four interactive sessions.
Seat c was retired through sminos. The three background sessions (two
probes, c) were removed with `claude rm`. `~/.claude/projects/-private-tmp-smns-acc-R`
and `-probe` were deleted, along with `/tmp/smns-acc` and the driver's
scratch directories. Afterwards, `~/.claude/sessions` held no record under
`/tmp/smns-acc`, and `claude agents --json --all` listed none.
