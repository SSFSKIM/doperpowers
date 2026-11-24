# sminos: find the session to talk to, across the org

The owner's org of Claude Code sessions is growing past what reading a list serves. Today a session that wants to know "who should I talk to about the hub's sync", "is anyone in charge of the CI for MAWS", or "who last touched `sminos_hub.py`" runs `sminos list --org` and reads every row: alias, project, machine, state, branch and a one-line **in-charge line** (what the session is responsible for, which sminos derives from the session itself; `docs/doperpowers/specs/2026-11-08-sminos-derive-on-compact-design.md`). With 37 sessions that output was 5.7k characters, and sessions read it whole (the October directory eval, `docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md`); with hundreds of sessions, and stopped ones that still hold the context of work they did last week, a single line per session is too little to judge by and the whole list is too much to read.

After this change every session carries, besides its in-charge line, a **summary**: three short lines, `doing:`, `made:` and `next:`, refreshed whenever its line is derived, which now includes every compaction. And `sminos find "<question>"` answers a question in plain words with the sessions best placed to answer it — live or stopped, in any project, on any enrolled machine — each with why it fits, its summary, and how to reach it, from one call to a small model (haiku) over every such session's information. `sminos who @<session>` shows one session's summary. Plain `sminos list` does not change.

To see it working: on the MacBook, after a session compacts, `sminos who @<its short>` on the Mac mini prints its three summary lines; from a session on the mini, `sminos find "who runs CI for these repositories"` names the CI session on the MacBook first, with a reason; `sminos find "who is translating the Klingon dictionary"` says no session matches.

## Progress

- [x] (2026-11-23) Design approved by the owner, as presented in the brainstorm.
- [x] (2026-11-23) Spec review (`doperpowers:adversarial-reviewer`, the spec and its execution section): two rounds, folded.
- [x] (2026-11-24) M1 — the summary: derived, recorded, shown by `who @<session>`; every compaction derives. Reviewed clean after one fix round (a withdrawn historical row inherited a predecessor's summary; a mark beside unmarked text on one line corrupted the fallback fields). `6f354d356..5782858e3`, ci-gate GREEN.
- [x] (2026-11-24) M2 — `find` as the org's search. Reviewed clean after one fix round (transcript cleanup confined to the minted id, `list`'s scope shared and the newest join kept, no credentials in test logs, failure wording). `76361ce2c..d71d7dfb0`, ci-gate GREEN; the real-model check ranked the CI session first and answered the Klingon question with no match, exit 4.
- [ ] Whole-branch review (review-code, medium), merge, release.
- [ ] Live acceptance 7–10 on both Macs.

## Terms

- **Derive** — `sminos derive` (`cmd_derive`, `derive_member`, `derive_line` in `sminos/skills/sminos/scripts/sminos.py`) puts one question to a session about itself and records the answer as an `in-charge` event with `source: derived` in the session's project log. It asks through the session's bridge (`btw`: a tool-less side question read from the session's own warm prompt cache, about 7k tokens read) where one runs, else a headless fork (`sminos_fork.headless_fork`). The daemon runs `derive --all` every five minutes (a first line after the tenth tool call, then at most every six hours); the compaction hook (`sminos/hooks/smns-derive.sh`) runs `derive <session> --compacted`.
- **Corpus** — what `find` hands the model: one block of text per session it may name (§3).
- **Internal process** — a `claude` process sminos starts for itself, never a member: `SMNS_INTERNAL=1` in its environment keeps the record hook from recording it, and a marker `$SMINOS_HOME/internal/<pid>`, written before it may start, keeps reconciliation from joining it (`sminos_fork.headless_fork`).

## 1. The summary

### 1a. Asked with the line

The derive question gains one ask, `SUMMARY_ASK`, appended by `derive_prompt` to every prompt it builds, after the line's question and keep-bar (`DERIVE_KEEP`) and after the charge-name ask when there is one:

    SUMMARY_ASK = (
        "Then three lines that summarize this session's work now, for a session in another project that has never "
        "seen this conversation and is deciding whether to ask you about something:\n"
        "doing: the task in hand and how far it has got\n"
        "made: what you own or have produced, named so that session can find it: file and spec paths, PR and issue "
        "numbers with their repository, the decisions taken\n"
        "next: what you are waiting on, and what comes next\n"
        "Name everything by what it is, never by a label coined in this conversation (a milestone, finding or step "
        "number, a nickname for a piece of work) unless you say what it stands for. At most 200 characters a line. "
        "Write the three lines afresh each time, whether or not the line above changes.")

The closing instruction becomes "Answer with these four lines only." (line, `doing:`, `made:`, `next:`), or "Answer with these five lines only." when a charge name is asked too (line, `name:`, then the three).

Why these three: `made:` is what lets a question name an artifact ("who touched `sminos_hub.py`", "who holds the P6 apps spec") and still find the session; `doing:` and `next:` say whether the session is the one to ask now and what it is blocked on. The owner's requirement, written into the ask: the reader is a session in another project with none of this conversation, so a summary that says "M3 landed, F1 open, waiting on line 6" says nothing to it. The line keeps its keep-bar, because other sessions follow a session by its line and a line reworded at each derive reads as new work (1,005 of 1,018 re-derives did that before `DERIVE_KEEP`); the summary is the session's state and is meant to change, so it has none.

### 1b. Read from the answer

An answer can arrive marked: a session under the to-human output style wraps what it says in `<message>` spans (`extract_marks`), and today `answer_text` keeps only the first span. With four or five lines to read, a model may split them across spans, mark only some of them, or wrap commentary around them, so one reader, `answer_fields(text) -> AnswerFields(line, name, summary)`, replaces the reading in `answer_line`, `answer_name` and the new summary, and those three become its fields:

- **Labelled fields** — `name:`, `doing:`, `made:`, `next:` (a line beginning, after optional whitespace, with the label and a colon, case-insensitive; `NAME_LINE_RE` and a new `SUMMARY_LINE_RE`): each is the first such line in the marked text (every span, in order), else in the unmarked text. Its value is the text after the label, trimmed of whitespace and of backticks and quotes at its ends; `name` is then read as `answer_name` reads it today (lowercased, one trailing period dropped); each summary value is cut to `SUMMARY_LINE_MAX` (200) characters. The backticks or quotes come off only when one pair wraps the whole value, so `` `a.py` and `b.py` `` stays whole, and a value made only of those delimiters is empty.
- **The line** — the first non-empty line that carries no label, taken from the marked text when any span holds one, else from the unmarked text; cut to `DERIVE_LINE_MAX` (120) as today. Commentary outside the marks never becomes the line while a mark holds one, which is today's behavior for an answer whose first span is the line.
- **The summary** — `{"doing": …, "made": …, "next": …}` when all three labels are present with non-empty values, else `None`. Three are required, not some: a partial summary would show as if whole, and the ask tells the session to write `next:` even when nothing is pending.

An unmarked answer reads exactly as today: the line is its first unlabelled line, the name its first `name:` line. "The unmarked text" is the answer outside its marks (`unmarked_text`), with a line break wherever a mark stood, so words beside a mark on the same line never join a marked field; a closing tag with no open mark is no boundary, and an unclosed mark runs to the end.

### 1c. Recorded on the line's event

`derive_member` records the summary on the event it already writes: `lifecycle(project, m.session, "in-charge", text=line, source="derived", name=…, summary={…})`, the `summary` field only when `answer_fields` gave one. An answer without a summary records the line alone, as today: the summary never fails a derive.

Event shape (one JSON line in the project's log, as every event):

    {"kind": "in-charge", "session": "<uuid>", "text": "<line>", "source": "derived",
     "name": "<charge name, when kept>",
     "summary": {"doing": "<text>", "made": "<text>", "next": "<text>"}, …the writer's own fields}

A field on the existing event, not a new event kind: the `in-charge` event is already the one record of what a session does, already written by one writer (derive) at the right moments, and already carried to every enrolled machine (every machine follows every org project; the org directory spec, §3). A new kind would need its own sync, sweep and latest-wins rule for the same moments.

### 1d. Read into the member

`summary_of(member, events, info)` returns `(summary, ts)`: the latest event, by `latest_across_writers`, among the in-charge events of the member's visible sessions that carries a well-formed `summary` (a dict with the three keys, each a non-empty string), and that event's `ts`; `(None, "")` when none does, or when the member's own session is unlisted to this reader (a retired, withdrawn successor rebuilt by `who <commit>` would otherwise inherit a visible predecessor's summary). `_member` sets two new `Member` fields from it, `summary` and `summary_age` (seconds, by `ts_age`). A later line set by `sminos charge` or a spawn's `--brief` does not clear a summary; its age says how old it is.

The member's visible sessions are `member.session`, the sessions of `member.former` that the log does not show unlisted to this reader (`unlisted_here(x, info[x])`), and `member.thread_sessions`, which `thread_sessions` already filters that way. Not `charge_of`'s set as it stands: `former` comes from `lineage`, which does not filter, so a visible session that continues a withdrawn one would otherwise carry the withdrawn one's summary into `who` and into `find`'s corpus. A summary is richer than a line (paths, PRs, decisions), and the owner's withdrawal of a session's view must hide it. `who_lines` likewise prints a summary only for a session not unlisted to this reader: `who <commit>`'s historical path (`who_matches`, which rebuilds rows of retired sessions from `view.info` without that filter) prints no summary for a session `unlisted_here` holds.

`member_json` carries `"summary"` (the dict, or `null`) and `"summary_age"`, so `list --json` and programs reading it (the desk, later, if MAWS wants it) have it. `channel show --json` embeds `member_json`, so it carries the two fields too. Text rows of `list`, `chart` and `tui` do not change, and `derive` does not print the summary (the daemon's log would grow three lines a member a run): the summary is for search and for looking at one session, not for scanning a list.

## 2. Every compaction derives

`derive <session> --compacted` derives at every compaction. The every-third-compaction counter goes: `compaction_due`, `compactions_path`, `DERIVE_COMPACTIONS`, the `SMINOS_DERIVE_COMPACTIONS` override, the count's removal in `derive_member`, and `derive --all`'s sweep of `$SMINOS_HOME/compactions/`. Files already in that directory are left: a few bytes each, read by nothing.

Why: the summary is state, and a compaction marks the most state change a session goes through, so a summary refreshed only every third compaction would describe work two compactions old. The counter existed to save forks; the compaction derive asks through the session's warm cache (`btw`, about 7k tokens read and 460 written per ask in the logs), which is small against a compaction's own cost. The line is unaffected in practice: `DERIVE_KEEP` keeps it unchanged unless it is wrong. `--compacted` still clears the member's `now:` status (`clear_status`) and waives only the pacing rules it waives today; the six-hour daemon path is unchanged and asks for the summary too, since it is the same `derive_member`.

Two derives of one member that overlap (a compaction's and the daemon's) record in the order they finish, so the older answer can win until the next derive. That holds for the line today as well, the window is one derive, and the next one corrects it: known and accepted, not handled here.

## 3. `sminos find "<question>"`

`find` becomes the search. Its old meaning, `list --org <words>` (a keyword filter), stays available under that name; `find` keeps its slot in `READING_VERBS`.

    sminos find <question…> [--all] [--json]

The words after `find` are joined with spaces into the question, so `sminos find ci-kit` still works, as a question.

### 3a. The corpus

The corpus is `list --org`'s own scope and rows, never a wider read: the projects `list_scope` returns under `--org` (every project known here but one that has left this machine, `has_left`, whose retained log no longer updates), and in each the rows `project_rows` yields, keeping those with a session whose state is live (`FILLED`: busy, idle, waiting) or held (`HELD_STATES`: stopped, gone) and that has not ended (`m.end` empty). Each session is one entry (a member that shows in several projects' rows, as a channel's roster does, is one), and the caller is left out: the session `CLAUDE_CODE_SESSION_ID` names, with its current thread (`sminos_threads.stamp`), not a thread it has left. The projects come from `widened_scope()`, extracted from `list_scope` so the two cannot drift, and a member in two projects (a move's dual membership) is kept in the one it joined last, by the directory's own deduplicator (`one_per_session`). With `--all` a retired or ended entry says why (retired, ended after it stopped, or its machine retired). `--all` adds the retired rows and, as `cmd_list` does under `--all`, the ended threads `view_of(p).ended` holds. The owner chose live and stopped: a stopped session still holds the context of work it did, and an addressed message wakes it (or is held for it, its reach line says why), so it is a session one can ask.

Because it is built from `project_rows`, `find` sees what `list --org` sees and nothing more. That includes per-session visibility: a session whose owner withdrew this machine's view of it (`unlisted`, `sminos_visibility`) is out of `project_rows` here, so out of `list --org` and out of the corpus, and its summary never reaches the model. The summary it adds is in the same project logs every enrolled machine already reads.

Every field an entry draws is free text some writer chose — a set line or a spawn's brief can be any length, and a summary written by another machine's sminos is only known to be non-empty — so `find_entry` normalizes every interpolated string (control characters dropped, whitespace runs collapsed to one space) and caps each: the in-charge line and each summary line at `CORPUS_FIELD_MAX` (200) characters; the alias, kind, machine, project name, repository and branch at `CORPUS_NAME_MAX` (64); each channel name at 64, at most ten of them. The question gets the same treatment, capped at `CORPUS_FIELD_MAX` × 5 (1,000). The size check is on the assembled prompt, question included: over `FIND_PROMPT_MAX` (400,000 characters) it is refused before any call, `sminos: find: the prompt is <n> characters, over find's budget of 400000; narrow it with list --org <words>`, exit 1. The figure is a conservative character budget, set well below the small model's context window as characters usually count against it, not a token guarantee. Splitting is not built (Delegated unknowns).

Each entry is a block of plain text:

    [a45b97a3] CI-opt — doperpowers on macbook; busy (interactive); doperpowers@main; active 17s ago
      in charge (24m): I'm in charge of CI here: ci-kit itself, the CI for MAWS, cua, doperpowers …
      doing (2h): …
      made: …
      next: …
      channels: desk-integration

the summary's three lines only when it has one, `channels:` only when it is in any (by name). About 150 tokens a session: 165 sessions today, about 25k tokens.

### 3b. The call

One call through a new `sminos_fork.ask_model(prompt, *, model, effort, timeout)`: `claude -p --safe-mode --no-session-persistence --session-id <minted> --model haiku --effort medium --tools "" --output-format json`, the prompt on standard input, the working directory `$SMINOS_HOME`, started as an internal process. `ask_model` shares `headless_fork`'s machinery — the start gate, the internal marker, the `SMNS_INTERNAL` environment, the timeout, the JSON result read from the last `{` line of stdout, the cleanup of a transcript the engine wrote anyway under the minted id and of the marker — by extracting that machinery into one helper both call, `run_internal`, so the two never drift.

The start gate is fixed in the extraction. Today `headless_fork` starts `/bin/sh -c 'read -r _ <&N; exec N<&-; exec "$@"'` and writes the internal marker before releasing the gate with a newline; but a failed `read` (end of file: the parent died, or failed before writing the marker and closed the pipe) falls through to `exec` all the same, so the engine starts unmarked and the record hook and reconciliation see a member that is none. `run_internal`'s gate execs only after a successful read (`read -r _ <&N || exit 1`), and on any failure between the start and the release (the marker not written, an exception) it kills and reaps the child before raising `ForkFailed`. Derive's headless fork runs through the same helper, so its path is fixed too; its other behavior and its existing tests do not change.

The call goes out on the calling environment's own first-party Anthropic login, never through a gateway and never on an API key: the corpus is the whole org's directory, and that is the boundary it must not cross, a third party or a key billed apart from the owner's subscription. The first-party login is whatever the engine finds there — the account the caller's `CLAUDE_CONFIG_DIR` selects, or `CLAUDE_CODE_OAUTH_TOKEN` (how a devcloud VM may authenticate) — and is kept as it is, never replaced by another account. What would cross the boundary is dropped: a caller can run inside a gateway-routed session whose settings exported a base URL, an auth token and model aliases into its environment (`gateway_env_keys`, which `launch_env` drops for a plain-route launch), or carry an API key. So `ask_model` starts from `os.environ` and drops every key `gateway_env_keys()` names, every variable whose name starts with `ANTHROPIC_` (base URL, auth token, API key, model overrides), `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOUNDRY`, `CLAUDE_CODE_SUBAGENT_MODEL` and `CLODEX_SETTINGS`, and the launch-only markers `launch_env` drops; it sets `SMNS_INTERNAL=1`. `PATH`, `HOME`, `CLAUDE_CONFIG_DIR` and `CLAUDE_CODE_OAUTH_TOKEN` stay. An environment with no first-party login left is the engine's own failure, reported as any failed call is (§3e). Derive's fork keeps its environment as today: it resumes a session on that session's own route.

- `--safe-mode`, not `--bare`: `claude --help` says bare's auth is "strictly ANTHROPIC_API_KEY or apiKeyHelper via --settings (OAuth and keychain are never read)", so a bare call bills an API key instead of the owner's subscription, and fails where there is none. Safe mode starts with no plugins, hooks, MCP servers or CLAUDE.md and uses the machine's own login; `skills/query-transcript/scripts/query_transcript.py` runs haiku this way.
- Standard input, not an argument: the corpus is tens of kilobytes and grows with the org.
- `$SMINOS_HOME` as the working directory: never a macOS protected folder (`launch_refused`), and no project's files near it.
- Timeout `SMINOS_FIND_TIMEOUT` seconds, default 120, as derive's `SMINOS_DERIVE_TIMEOUT`.

The prompt, `FIND_PROMPT`, puts the instructions first, the corpus after, and the question last (a long context is read best with the question nearest the answer):

    FIND_PROMPT = (
        "You are the directory of an organization of Claude Code sessions. Below are its sessions, then a question "
        "one of them asks. Pick the sessions best placed to answer the question or to own what it asks about: at "
        "most five, best first, judged by what each is in charge of, is doing, has made and is waiting on. A weak "
        "match is worse than none: when no session fits, say so. Answer with one JSON object and nothing else:\n"
        '{"matches": [{"short": "<the 8 characters in brackets>", "why": "<one line: what about it fits>"}], '
        '"note": "<one line: why nothing fits, or what the asker should know; empty otherwise>"}\n\n'
        "Sessions:\n\n%s\n\nQuestion: %s")

### 3c. The answer, checked

`parse_find(text)` reads the first JSON object in the model's result text (a code fence around it is tolerated) into `(matches, note)`. The object must have `matches` as a list; each item that is an object with a string `short` is kept, `why` (a string, else empty) cut to one line of 200 characters; `note` a string, else empty. An object without a `matches` list (`{}`, `{"matches": null}`), or with a non-empty `matches` list none of whose items is valid, is a failure (§3e), as is a result with no parseable JSON object; only a valid empty list is "no match".

Then, in order: every `short` is checked against the corpus, one the corpus does not hold dropped and counted; repeats of a short are dropped; and the first five that remain are kept. This is the boundary between the model and a message: a short the model made up would otherwise be offered as an address.

### 3d. Output

For each match, in the model's order: the member's `list` row (`row_cells`, as `list --org` draws it, with its project), then `why:`, the summary's lines with the summary's age when it has one, and the lines that say how to reach it — the same lines `who` prints, which `who_lines` and `find` share through one function, `reach_lines(project, member)`, extracted from `who_lines`. Its outcomes, each case's words reused from where the CLI already says them:

| The member | Reach lines |
|---|---|
| live | `reach: sminos say "@<short> ..."` (today's) |
| a stopped seat, not retired | today's: resumed, or held and why (`hold_for`, `hold_words`) |
| a stopped thread its machine wakes (a stopped member has its transcript on its machine) | the resume command, and "message it, which wakes it" (today's) |
| held by its machine, for any reason but `transcript` | the resume command, and that a message waits, with why (today's) |
| held because its machine published `transcript` (no conversation of it is there) | that a message waits, with `HOLD_WORDS["transcript"]`; no resume command, since there is nothing there to resume |
| its machine admits nothing from here (`read-only`) | today's refusal line |
| another machine's, with no wake published | the resume command there, and an untagged note in its project (today's) |
| a local `gone` member with no seat: no transcript of it here (`_member` calls a seatless local session `gone` exactly when it is not stopped by its human and `transcript_path` finds nothing; today's `who_lines` says nothing) | "nothing on this machine resumes it" |
| an ended thread (`--all`) | how it returns, as `unreachable_hint` words an ended thread |
| a member of a machine the org retired (`--all`) | `unreachable_hint`'s retired-machine words |
| a retired seat (`--all`) | `unreachable_hint`'s retired-seat words |

`reach_lines` (as built in M1) takes the cases in this order: a retired machine's member, a retired seat, an ended thread, live, a stopped seat, a local `gone` member, then the rest as `who_lines` had them; the `transcript` row's line reads "leave it a message" with no "or" and no resume command, and `who <commit>` shows the same lines for those rows. In practice a local seatless member is rarely `gone`: reconciliation adopts it into a thread its human opened, which reads as `stopped`; the suite reaches that row by patching `stopped_human`.

Where `unreachable_hint` builds its sentence inside a refusal, the sentence is factored out so `reach_lines` and the refusal say the same thing.

    $ sminos find "who runs CI for these repositories"
    CI-opt [a45b97a3]  interactive  busy  @macbook  doperpowers  doperpowers@main  in charge: I'm in charge of CI here: …
      why: owns ci-kit and the CI of doperpowers, MAWS and cua
      doing (2h): …
      made: …
      next: …
      reach: sminos say "@a45b97a3 ..."

A short is matched after its brackets and `@` are stripped and it is lowercased. `why:` prints even when the reason is empty; the note, cleaned as `why` is, prints as `note: …` after the matches when there are any. When the model named shorts the corpus does not hold, a last line says so (repeats are dropped silently, not counted): `(the model named 1 session that is not in the directory; left out)`. With no match left: `no session matches: <note>` (the note omitted when empty), exit 4 (`EXIT_UNKNOWN`, the CLI's code for "nothing answers to it", as `who` uses). `--json` prints one object: `{"question", "corpus": <entries>, "matches": [<member_json(m, p, private=False)> + "why"], "note", "dropped"}`, exit 0 or 4 as in text.

### 3e. Failure

A call that fails — it does not start, times out, exits non-zero, returns an error result, no parseable JSON object, or one without a `matches` list — or a prompt over budget (§3a) prints `sminos: find: <reason>` on stderr and exits 1; a call or parse failure ends `; list --org <words> lists the sessions some words match`, and under `--json` stdout stays empty. An unusable `SMINOS_FIND_TIMEOUT` is refused the same way before anything is read or called. There is no fallback to keyword filtering: a silent substitute would hand back a different kind of answer under the same name; the error tells the caller `list --org <words>` exists.

## 4. Looking at one session: `who @<session>`

`sminos who @<session>` prints what `who` prints for a commit's session — who it is now and how to reach it — for a session named as a message tag names one: `@<short>` anywhere in the org, `@<project>/<alias>`, or a bare `@<alias>` in the caller's project and channels, through the same resolution `say` applies to its tags (`resolve_tags`' rules). It prints a `<tag>:` header, then the session's lines; `@all`, more than one tag, extra words, or `--session` beside it are usage errors (exit 2). `who_lines` gains the summary after the in-charge line, `doing (<age>): …`, `made: …`, `next: …`, so `who <commit|PR>` shows it too.

The approved design named `who --session <short>` for this. That form already has a consumer: the session's address mod calls `who --session <id>` and takes its output as the `Sminos-Session:` line it appends to every commit message and PR body. Its output cannot grow; `who @<session>` is the form that reads as "who is this", and `who`'s existing text for a session is the right body.

## 5. What it is not

- **No line in the SessionStart guide** (`sminos guide`), and no instruction anywhere telling sessions to check for other sessions before starting work. The owner ruled duplicate work is not a concern this needs to address: the in-charge line already separates work, and the task tracker will carry a claimed state. `find` is documented in the sminos skill as a tool a session reaches for.
- **No index, no embeddings, no server.** One model call over the whole corpus judges fit better than keyword or vector matching at this size, and needs nothing kept up to date. It runs on the asking machine, over the logs that machine already holds.
- **No summary in `list`'s text rows.**

## 6. A consumer of the old `find`: MAWS's acceptance scene

MAWS's reach acceptance runs `sminos find "$1" --org --json` (`apps/desk-hub/deploy/vm/scene.sh`, its `as-session <session> find <name>` step, driven by `reach-items.ts`' item 3a, "U's list --org, find and @short name nothing of S"). After this change that call is refused (`find` takes no `--org`), and item 3a would not notice: it only checks that no output line names the private session, and `asSession` does not look at the exit status, so a refused `find` passes as "names nothing".

The scene stages sminos by commit (each scene runs its own copy of sminos at a pinned commit, not the machine's installed plugin), so nothing breaks until a scene fixture update moves that pin past this change. The handoff is tied to that update, and is MAWS's change, which the orchestrator of this spec gives MAWS's landing session with these three parts:

1. The scene's `find` step runs `sminos list --org "$1" --json`, which prints the rows `find` printed until now.
2. Item 3a's check asserts the call exited 0 and its output parsed as a JSON array of rows, before asserting no row names S; a refused or malformed call then fails the item instead of passing it.
3. The check is relabelled for what it proves, the keyword list (`list --org <words>`), not `find`.

What 3a protected on the sminos side holds for the new `find` by construction (§3a: the corpus is `project_rows`, which leaves out a session withdrawn from this machine's view), and acceptance 6 pins it. Nothing else in either repository calls `sminos find`.

## Delegated unknowns

- **The hub carries the new field.** The MAWS hub (`apps/desk-hub`) shows no filter on log event kinds or fields: session-plane kinds are listed (`SESSION_KINDS`), log events are not. Resolved by acceptance 7: a summary written on the MacBook shows on the mini.
- **The corpus outgrowing its budget.** At about 150 tokens a session, `FIND_PROMPT_MAX` (§3a) holds a couple of thousand sessions; past it `find` refuses with a clear message. When the org nears it, `find` splits the corpus and asks the parts in parallel, as `query-transcript --all` asks segments. Not built now.
- **Effort and latency.** `--effort medium` is the starting point; acceptance 8 measures the call's time on the real corpus. M2's check on the MacBook against a copy of its home: the CI question 45 s on a cold copy; warm runs about 24 s, about 11 s of it building the corpus (the reconciliation `list --org` does) and about 17 s the model call. The corpus build, not only the effort, is the lever if the mini runs over. A slower-than-30-second answer, or poor ranking, moves the effort.

## Acceptance

In the suite (`sminos/tests/run-sminos-tests.sh`, with the stub `claude`):

1. A derive's prompt carries `SUMMARY_ASK` and ends "Answer with these four lines only." (with a charge-name ask, "five lines"); an answer of a line and the three labelled lines records an `in-charge` event whose `summary` holds the three texts; a summary line of more than 200 characters is cut to 200.
2. Reading the answer (§1b), each case checked on the recorded event's `text` and `summary` and, where a name is asked, the kept `name`: labelled lines before the line; a `name:` line among them; the five lines split across two `<message>` spans; only the summary marked, the line and name unmarked; the line marked with commentary outside the marks (the commentary is never the line); an unmarked answer, read as today. An answer missing `next:` records the line with no `summary` field and the derive succeeds.
3. Two `derive <member> --compacted` runs in a row both fork (the stub's call log shows two forks); `$SMINOS_HOME/compactions/` is never written.
4. `sminos who @<short>` prints the member's summary lines with the summary's age; `who <commit>` for a commit of that session does too; `list` prints no `doing:`; `list --json` carries `summary` and `summary_age`. A member whose summary came from another machine's log (an event written by another writer) shows it. `who @<short>` of a local `gone` member with no seat (no transcript of it here) prints "nothing on this machine resumes it"; of another machine's member whose published hold is `transcript`, that a message waits and why, with no resume command. A session that continues one the log shows unlisted here carries no summary from it, and `who <commit>` naming a retired withdrawn session prints no summary: in both the withdrawn session's distinctive summary text is absent from the output.
5. `sminos find "<question>"` starts one internal process — `SMNS_INTERNAL=1`, its marker present while it runs, `--safe-mode`, `--no-session-persistence`, `--model haiku`, `--tools ""`, no `--bare` — whose standard input holds the question after the corpus. Run with gateway variables (the keys a stub gateway settings file names), `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` and `CLAUDE_CODE_USE_BEDROCK` in the caller's environment, the stub records none of them in the process's environment. The corpus holds live and stopped members with their summaries, and not the caller, retired or ended members; with `--all` it holds those, a seatless ended thread among them, and a retired machine's member, whose reach line gives `unreachable_hint`'s words. A project's retained log after it has left this machine (`has_left`) contributes nothing, with or without `--all`. A session withdrawn from this machine's view (`unlisted`) never appears in the process's standard input, while a session still in view does. Every interpolated field is capped (a 5,000-character set line reaches the corpus as 200, a 300-character branch as 64), and an assembled prompt over `FIND_PROMPT_MAX` (lowered for the test), a long question tipping it over, exits 1 with the budget message and starts no process. `CLAUDE_CODE_OAUTH_TOKEN` and `CLAUDE_CONFIG_DIR` in the caller's environment reach the process unchanged.
6. Given a stub answer naming two corpus shorts, one unknown and one repeat, `find` prints the two rows with their `why:`, summaries and reach lines (a stopped member's says how a message reaches it), and the dropped count; given seven valid shorts it prints five. Given `{"matches": [], "note": "…"}` it prints `no session matches: …` and exits 4; given `{}`, a non-empty `matches` with no valid item (`[1, {"why": "x"}]`), a crash, a timeout or text with no JSON object, it exits 1 with the reason on stderr and no match — each of these in text and in `--json`, which gives the documented object. `list --org <words>` keeps the old keyword results (the former `find <words>` cases, moved to it).
6a. The start gate (§3b): a gate closed without the release byte never starts the stub engine (its call log stays empty, no process outlives the helper); a failure to write the marker kills and reaps the child and raises `ForkFailed`. Derive's headless fork passes its existing tests through the same helper.

Live, after the release reaches both Macs (the orchestrator runs these):

7. A session on the MacBook compacts; within a minute `sminos who @<short>` on the mini prints its three summary lines. Read by someone who has not seen that session: the lines name paths, PRs with their repository, and features, and no unexplained milestone or finding numbers.
8. From a session on the mini, `sminos find "who runs CI for these repositories"` names the MacBook's CI session first with a reason that fits, in under 30 seconds.
9. `sminos find "who is translating the Klingon dictionary"` prints `no session matches` and exits 4.
10. A question that only a stopped session's summary answers names that session, and its reach line says a message wakes it or why it is held.
11. `ci-gate` on the branch is GREEN.

## Execution

**Verification.** One independent review of this spec by `doperpowers:adversarial-reviewer`, and, the execution section having two milestones, its buildability review by the same agent in the same round. The branch is reviewed through `doperpowers:review-code` at the medium rung (`doperpowers:reviewer-medium`): a focused diff in one plugin, whose risks — the derive prompt and parsing, the removed counter, an internal process that must never become a member (the start gate), the whole directory sent only on the caller's first-party login, never a gateway or an API key, the corpus kept to `list --org`'s view, a model's output turned into addresses — are pinned by the suite.

**Binding on every milestone.**

- The sminos plugin only, plus the documentation named below; nothing in doperpowers' own `hooks/` or skills changes. The CLI stays `sminos.py` and its sibling modules, standard library only.
- Verify a commit with `ci-gate` from the worktree; do not run the gates' commands locally. One focused Python test file while iterating is fine.
- Version: `scripts/bump-version.sh --plugin sminos` once on the branch, minor (1.56.0 → 1.57.0), in M1's commit; M2 ships in the same release and needs no second bump.
- The sminos skill's text (`sminos/skills/sminos/SKILL.md`) changes only to document `find`'s and `who @`'s interface and that a summary exists. That documents a verb; it shapes no behavior the skill asks of sessions, so it needs no writing-skills evaluation. A line that tells sessions when to search would need one, and is out of scope (§5).
- The repository is public: no hostnames other than the org's machine names already used in its specs, no IPs, accounts, secret names or values, or local absolute paths in code comments, tests' committed fixtures or docs.
- A test that runs real `claude` is not added: the stub stands in, as it does for derive.

### M1 — the summary

**At its end:** every derive asks for and records the summary (§1a–1c), every compaction derives (§2), members carry their summary (§1d), and `who @<session>` and `who <commit|PR>` show it (§4).

**Touches:** `sminos/skills/sminos/scripts/sminos.py` — `derive_prompt`, `answer_text`, `answer_line` and `answer_name` (their reading moved into a new `answer_fields`), `SUMMARY_*` constants beside `NAME_LINE_RE`, `derive_member`, `cmd_derive`, the removed `compaction_due` and `compactions_path`, `Member`, `_member`, a new `summary_of` beside `charge_of`, `member_json`, `who_lines` (its reach lines extracted into `reach_lines`, with §3d's table, and `unreachable_hint`'s sentences factored out for it), `cmd_who` and the `who` parser, the usage block's `who` and `derive` lines. `sminos/tests/run-sminos-tests.sh` (the derive cases, the every-third-compaction block that exports `SMINOS_DERIVE_COMPACTIONS`, the `who` cases). `sminos/skills/sminos/SKILL.md` (the in-charge paragraph under "Your lines and your project": the summary exists and how to see it; the `who` line under "Who is here"). `sminos/hooks/hooks.json`'s description of `smns-derive.sh` if it states the cadence. `docs/whats-inside.md` (the `names` row says "every third compaction"). `docs/doperpowers/specs/2026-11-08-sminos-derive-on-compact-design.md` §5: one sentence at its head saying this spec's §2 replaces it. The bump.

**Decisions:** `who @<session>` resolves through the tag resolver `say` uses, read-only: it must not record or deliver anything, so call the resolution part alone; a tag that resolves to no session, or to several, exits 4 with `say`'s wording for the same case. The summary ask goes on every derive prompt, the daemon's included; a session whose model answers only the line (an older cached answer style) loses nothing. `answer_fields` is pure and takes the raw fork text, as `answer_name` does; `answer_line` and `answer_name` stay as thin readers of it, since `derive_line` and `derive_member` call them.

**Does not touch:** `find`, `sminos_fork.py`, `unreachable_hint`'s refusal wording, the daemon's derive cadence and caps (`derive --all`, `derive_order`, `DERIVE_EVERY`, `DERIVE_RETRY`), `name.tsx`, `who --session` and `who --thread`.

**Proves:** acceptance 1–4.

### M2 — `find` as the org's search

**At its end:** `sminos find "<question>"` answers from one haiku call over the corpus (§3), and the documentation says so.

**Touches:** `sminos/skills/sminos/scripts/sminos_fork.py` (`run_internal`, extracted from `headless_fork` with the gate fixed, §3b; `ask_model` and its environment). `sminos/skills/sminos/scripts/sminos.py` — `cmd_find` rewritten, new `find_corpus`, `find_entry`, `find_prompt`, `parse_find` and `FIND_PROMPT`, the `find` parser (`question` words, `--all`, `--json`; no `list_flags`), `cmd_list`'s two `a.find` checks (the flag goes with `find`'s use of `cmd_list`), the usage block's `find` line. `sminos/tests/run-sminos-tests.sh` — the stub `claude` gains a branch for a `-p` call without `--resume` (it records its argv, environment and marker as the fork branch does, saves its standard input to `find-prompt.txt`, and answers `STUB_FIND_RESULT`, or fails or crashes on the same switches the fork branch reads); the old `find <words>` cases move to `list --org <words>`; the new cases. The Python tests that call the old `find` (a grep for `"find"` in `sminos/tests/*.py` finds exactly these): `test_list_fold.py`, `test_org_retired.py`, `test_channels.py`, `test_channels_roster.py` — their list and fold assertions move to `list --org <words>` — and `test_visibility.py`, whose withdrawn-member case keeps asserting on `find`, now through the stub, that the withdrawn session is not in the model's standard input and a session still in view is. The gate's tests live beside `headless_fork`'s. `sminos/skills/sminos/SKILL.md` ("Who is here": `find`'s new line, and `list --org <words>` for keyword filtering). `docs/whats-inside.md` (the sminos CLI row's `find`). `docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md` §4: one sentence where it defines `find` as `list --org <words>`, pointing here.

**Decisions:** the corpus is built from `list_scope`'s `--org` projects and the members `project_rows` yields for each (§3a), deduplicated by session, never from `list`'s printed text. The entry's ages use the CLI's `short_age`. Matches print in the model's order, deduplicated by short. The question is passed to the model verbatim; `find` with no words is a usage error. `ask_model`'s minted session id exists only so a transcript the engine writes despite `--no-session-persistence` is found and deleted, as in `headless_fork`.

**Does not touch:** derive, the summary's shape, `list`'s text and `--json` beyond M1, the guide (§5).

**Proves:** acceptance 5, 6 and 6a, and runs 7–10's commands once on this Mac against a copy of its sminos home (below) to check the prompt on the real model; 7–10 proper run after release.

## Concrete Steps

From the worktree root:

    scripts/bump-version.sh --plugin sminos --since origin/main   # M1: the bump accepted
    ci-gate                                                        # each milestone: GREEN <run-url>

The real-model check at M2's end, on the MacBook, against a copy so the branch's CLI writes nothing into the machine's own sminos home (every reading verb reconciles, and reconciling writes events):

    cp -R ~/.claude/sminos <scratch>/sminos-home
    SMINOS_HOME=<scratch>/sminos-home sminos/bin/sminos find "who runs CI for these repositories"
    # expect: the CI session first, a fitting why:, its summary when it has one, a reach line; under 30 s
    SMINOS_HOME=<scratch>/sminos-home sminos/bin/sminos find "who is translating the Klingon dictionary"; echo "exit $?"
    # expect: no session matches…  exit 4

The engine's login is the machine's own (the call is `--safe-mode`, persists nothing, and is internal); only `SMINOS_HOME` is redirected. Summaries will be sparse in the copy (no derive has asked for them yet); the check is the prompt and the parsing, not the summaries.

After release (the orchestrator), on each Mac: `sminos derive <a member>` or a real compaction, then `sminos who @<short>` from the other Mac, then acceptance 8–10's `find` commands.

## Interfaces and Dependencies

In `sminos/skills/sminos/scripts/sminos.py`:

    SUMMARY_LABELS = ("doing", "made", "next")
    SUMMARY_LINE_MAX = 200
    SUMMARY_ASK = …                      # §1a, exact
    SUMMARY_LINE_RE                      # a line starting, after whitespace, with one of the labels and ':' (case-insensitive)
    class AnswerFields(NamedTuple): line: str; name: str | None; summary: dict | None
    def answer_fields(text) -> AnswerFields           # §1b; answer_line and answer_name read it
    CORPUS_FIELD_MAX = 200
    CORPUS_NAME_MAX = 64
    FIND_PROMPT_MAX = 400_000            # characters of the assembled prompt, a conservative budget
    def summary_of(member, events, info) -> tuple[dict | None, str]   # (summary, ts) of its visible sessions, §1d
    class Member(NamedTuple): … summary: dict | None = None; summary_age: float | None = None
    def member_json(m, project=None, private=True)   # + "summary", "summary_age"
    def reach_lines(project, member) -> list[str]     # from who_lines; used by who_lines and cmd_find
    FIND_PROMPT = …                      # §3b, exact
    def find_corpus(caller_session, include_ended) -> list[tuple[Project, Member]]
    def find_entry(project, member) -> str           # one corpus block, §3a
    def parse_find(text) -> tuple[list[dict], str]   # (matches [{short, why}], note); raises FindFailed on no JSON object, no `matches` list, or a non-empty one with no valid item
    SMINOS_FIND_TIMEOUT (env), default 120

In `sminos/skills/sminos/scripts/sminos_fork.py`:

    def run_internal(args, *, cwd, env, timeout, stdin_text=None, cleanup=None, what="fork") -> dict
        # the gate (read must succeed before exec), the marker, the run, the result JSON and its empty-answer check (§3b);
        # `cleanup` is the caller's own (headless_fork keeps its transcript cleanup, sparing its parent's;
        # ask_model removes only <child's config dir>/projects/*/<minted>.jsonl), the marker removed even if it raises;
        # `what` names the process in errors; headless_fork and ask_model both call it
    def ask_model(prompt, *, model="haiku", effort="medium", timeout=120) -> ForkAnswer
        # a fresh internal `claude -p` (§3b) on the caller's first-party login (no gateway, no API key), prompt on stdin;
        # ForkFailed as headless_fork raises it

CLI:

    sminos find <question…> [--all] [--json]   # exit 0 matches, 4 none, 1 failure
    sminos who @<short|project/alias|alias>      # a session's who_lines, its summary included

The `in-charge` event's optional `summary` field: §1c. M1 produces `answer_fields`, `summary_of`, the `Member` fields, `member_json`'s fields and `reach_lines`; M2 consumes `Member.summary`, `summary_age` and `reach_lines`.

## Outcomes & Retrospective

Pending — written at finish.
