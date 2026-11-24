# sminos: find the session to talk to, across the org

The owner's org of Claude Code sessions is growing past what reading a list serves. Today a session that wants to know "who should I talk to about the hub's sync", "is anyone in charge of the CI for MAWS", or "who last touched `sminos_hub.py`" runs `sminos list --org` and reads every row: alias, project, machine, state, branch and a one-line **in-charge line** (what the session is responsible for, which sminos derives from the session itself; `docs/doperpowers/specs/2026-11-08-sminos-derive-on-compact-design.md`). With 37 sessions that output was 5.7k characters, and sessions read it whole (the October directory eval, `docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md`); with hundreds of sessions, and stopped ones that still hold the context of work they did last week, a single line per session is too little to judge by and the whole list is too much to read.

After this change every session carries, besides its in-charge line, a **summary**: three short lines, `doing:`, `made:` and `next:`, refreshed whenever its line is derived, which now includes every compaction. And `sminos find "<question>"` answers a question in plain words with the sessions best placed to answer it — live or stopped, in any project, on any enrolled machine — each with why it fits, its summary, and how to reach it, from one call to a small model (haiku) over every such session's information. `sminos who @<session>` shows one session's summary. Plain `sminos list` does not change.

To see it working: on the MacBook, after a session compacts, `sminos who @<its short>` on the Mac mini prints its three summary lines; from a session on the mini, `sminos find "who runs CI for these repositories"` names the CI session on the MacBook first, with a reason; `sminos find "who is translating the Klingon dictionary"` says no session matches.

## Progress

- [x] (2026-11-23) Design approved by the owner, as presented in the brainstorm.
- [ ] Spec review (`doperpowers:adversarial-reviewer`, the spec and its execution section).
- [ ] M1 — the summary: derived, recorded, shown by `who @<session>`; every compaction derives.
- [ ] M2 — `find` as the org's search.
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

`answer_summary(text)` reads the answer (through `answer_text`, as `answer_line` and `answer_name` do, so a `<message>` mark from the session's output style is stripped): the first line beginning, after optional whitespace, with each of `doing:`, `made:` and `next:` (case-insensitive), its text after the label trimmed of whitespace, backticks and quotes at its ends, and cut to `SUMMARY_LINE_MAX` (200) characters. It returns `{"doing": …, "made": …, "next": …}` when all three labels are present with non-empty text, else `None`. Three are required, not some: a partial summary would show as if whole, and the ask tells the session to write `next:` even when nothing is pending.

`answer_line` skips the summary's label lines as it already skips `name:` lines (`SUMMARY_LINE_RE` beside `NAME_LINE_RE`), so the in-charge line is the first line that is neither, whatever order the model answers in.

### 1c. Recorded on the line's event

`derive_member` records the summary on the event it already writes: `lifecycle(project, m.session, "in-charge", text=line, source="derived", name=…, summary={…})`, the `summary` field only when `answer_summary` gave one. An answer without a summary records the line alone, as today: the summary never fails a derive.

Event shape (one JSON line in the project's log, as every event):

    {"kind": "in-charge", "session": "<uuid>", "text": "<line>", "source": "derived",
     "name": "<charge name, when kept>",
     "summary": {"doing": "<text>", "made": "<text>", "next": "<text>"}, …the writer's own fields}

A field on the existing event, not a new event kind: the `in-charge` event is already the one record of what a session does, already written by one writer (derive) at the right moments, and already carried to every enrolled machine (every machine follows every org project; the org directory spec, §3). A new kind would need its own sync, sweep and latest-wins rule for the same moments.

### 1d. Read into the member

`summary_of(member, events)` returns `(summary, ts)`: the latest event, by `latest_across_writers`, among the in-charge events of the member's sessions (the same set `charge_of` reads: `member.session`, `member.former`, `member.thread_sessions`) that carries a well-formed `summary` (a dict with the three keys, each a non-empty string), and that event's `ts`; `(None, "")` when none does. `_member` sets two new `Member` fields from it, `summary` and `summary_age` (seconds, by `ts_age`). A later line set by `sminos charge` or a spawn's `--brief` does not clear a summary; its age says how old it is.

`member_json` carries `"summary"` (the dict, or `null`) and `"summary_age"`, so `list --json` and programs reading it (the desk, later, if MAWS wants it) have it. Text rows of `list`, `chart` and `tui` do not change: the summary is for search and for looking at one session, not for scanning a list.

## 2. Every compaction derives

`derive <session> --compacted` derives at every compaction. The every-third-compaction counter goes: `compaction_due`, `compactions_path`, `DERIVE_COMPACTIONS`, the `SMINOS_DERIVE_COMPACTIONS` override, the count's removal in `derive_member`, and `derive --all`'s sweep of `$SMINOS_HOME/compactions/`. Files already in that directory are left: a few bytes each, read by nothing.

Why: the summary is state, and a compaction marks the most state change a session goes through, so a summary refreshed only every third compaction would describe work two compactions old. The counter existed to save forks; the compaction derive asks through the session's warm cache (`btw`, about 7k tokens read and 460 written per ask in the logs), which is small against a compaction's own cost. The line is unaffected in practice: `DERIVE_KEEP` keeps it unchanged unless it is wrong. `--compacted` still clears the member's `now:` status (`clear_status`) and waives only the pacing rules it waives today; the six-hour daemon path is unchanged and asks for the summary too, since it is the same `derive_member`.

## 3. `sminos find "<question>"`

`find` becomes the search. Its old meaning, `list --org <words>` (a keyword filter), stays available under that name; `find` keeps its slot in `READING_VERBS`.

    sminos find <question…> [--all] [--json]

The words after `find` are joined with spaces into the question, so `sminos find ci-kit` still works, as a question.

### 3a. The corpus

Every member of every project known here (`known_projects`, as `list --org` takes them) whose state is live (`FILLED`: busy, idle, waiting) or held (`HELD_STATES`: stopped, gone) and that has not ended (`m.end` empty), each session once (a member that shows in several projects' rows, as a channel's roster does, is one entry), minus the caller: the session `CLAUDE_CODE_SESSION_ID` names, with the sessions of its thread. `--all` adds retired and ended members, the ones `list --all` shows. The owner chose live and stopped: a stopped session still holds the context of work it did, and an addressed message wakes it (or is held for it, its row says why), so it is a session one can ask.

`find` shows nothing `list --org --all --json` would not; the summary it adds is in the same project logs every enrolled machine already reads. `list` applies no per-session visibility of its own (a session's `access` and `shares` govern who may message it, `sminos_visibility`), so neither does `find`.

Each entry is a block of plain text:

    [a45b97a3] CI-opt — doperpowers on macbook; busy (interactive); doperpowers@main; active 17s ago
      in charge (24m): I'm in charge of CI here: ci-kit itself, the CI for MAWS, cua, doperpowers …
      doing (2h): …
      made: …
      next: …
      channels: desk-integration

the summary's three lines only when it has one, `channels:` only when it is in any (by name). About 150 tokens a session: 165 sessions today, about 25k tokens.

### 3b. The call

One call through a new `sminos_fork.ask_model(prompt, *, model, effort, timeout)`: `claude -p --safe-mode --no-session-persistence --session-id <minted> --model haiku --effort medium --tools "" --output-format json`, the prompt on standard input, the working directory `$SMINOS_HOME`, started as an internal process. `ask_model` shares `headless_fork`'s machinery — the start gate, the internal marker, the `SMNS_INTERNAL` environment, the timeout, the JSON result read from the last `{` line of stdout, the cleanup of a transcript the engine wrote anyway under the minted id and of the marker — by extracting that machinery into one helper both call, so the two never drift. `headless_fork`'s behavior and its tests do not change.

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

`parse_find(text)` reads the first JSON object in the model's result text (a code fence around it is tolerated) into `(matches, note)`: `matches` a list of `{short, why}` with `short` a string and `why` cut to one line of 200 characters. Every `short` is checked against the corpus; one the corpus does not hold is dropped and counted. This is the boundary between the model and a message: a short the model made up would otherwise be offered as an address. A result with no parseable JSON object is a failure (§3e), not an empty answer.

### 3d. Output

For each match, in the model's order: the member's `list` row (`row_cells`, as `list --org` draws it, with its project), then `why:`, the summary's lines with the summary's age when it has one, and the lines that say how to reach it — the same lines `who` prints, which `who_lines` and `find` share through one function, `reach_lines(project, member)`, extracted from `who_lines` (a live session's `sminos say "@<short> …"`; a stopped one that its machine wakes, "message it, which wakes it"; one it holds, why, and that the message waits; one that cannot be reached from here, why).

    $ sminos find "who runs CI for these repositories"
    CI-opt [a45b97a3]  interactive  busy  @macbook  doperpowers  doperpowers@main  in charge: I'm in charge of CI here: …
      why: owns ci-kit and the CI of doperpowers, MAWS and cua
      doing (2h): …
      made: …
      next: …
      reach: sminos say "@a45b97a3 ..."

When the model named shorts the corpus does not hold, a last line says so: `(the model named 1 session that is not in the directory; left out)`. With no match left: `no session matches: <note>` (the note omitted when empty), exit 4 (`EXIT_UNKNOWN`, the CLI's code for "nothing answers to it", as `who` uses). `--json` prints one object: `{"question", "corpus": <entries>, "matches": [<member_json(m, p, private=False)> + "why"], "note", "dropped"}`, exit 0 or 4 as in text.

### 3e. Failure

A call that fails — it does not start, times out, exits non-zero, returns an error result or no parseable JSON object — prints `sminos: find: <reason>` on stderr and exits 1. There is no fallback to keyword filtering: a silent substitute would hand back a different kind of answer under the same name; the error tells the caller `list --org <words>` exists.

## 4. Looking at one session: `who @<session>`

`sminos who @<session>` prints what `who` prints for a commit's session — who it is now and how to reach it — for a session named as a message tag names one: `@<short>` anywhere in the org, `@<project>/<alias>`, or a bare `@<alias>` in the caller's project and channels, through the same resolution `say` applies to its tags (`resolve_tags`' rules). `who_lines` gains the summary after the in-charge line, `doing (<age>): …`, `made: …`, `next: …`, so `who <commit|PR>` shows it too.

The approved design named `who --session <short>` for this. That form already has a consumer: the session's address mod calls `who --session <id>` and takes its output as the `Sminos-Session:` line it appends to every commit message and PR body. Its output cannot grow; `who @<session>` is the form that reads as "who is this", and `who`'s existing text for a session is the right body.

## 5. What it is not

- **No line in the SessionStart guide** (`sminos guide`), and no instruction anywhere telling sessions to check for other sessions before starting work. The owner ruled duplicate work is not a concern this needs to address: the in-charge line already separates work, and the task tracker will carry a claimed state. `find` is documented in the sminos skill as a tool a session reaches for.
- **No index, no embeddings, no server.** One model call over the whole corpus judges fit better than keyword or vector matching at this size, and needs nothing kept up to date. It runs on the asking machine, over the logs that machine already holds.
- **No summary in `list`'s text rows.**

## 6. A consumer of the old `find`: MAWS's acceptance scene

MAWS's endpoint acceptance harness runs `sminos find "$1" --org --json` (`apps/desk-hub/deploy/vm/scene.sh`, its `as-session <session> find <name>` step) and reads list's JSON rows. After this change that call is refused (`find` takes no `--org`). The scene's line becomes `sminos list --org "$1" --json`, which prints the same rows `find` printed until now. It is MAWS's change, landed in MAWS before this sminos release reaches a machine the scene runs on; the orchestrator of this spec hands it to MAWS's landing session with the one-line diff. Nothing else in either repository calls `sminos find`.

## Delegated unknowns

- **The hub carries the new field.** The MAWS hub (`apps/desk-hub`) shows no filter on log event kinds or fields: session-plane kinds are listed (`SESSION_KINDS`), log events are not. Resolved by acceptance 7: a summary written on the MacBook shows on the mini.
- **The corpus outgrowing the model's window.** At about 150 tokens a session the window holds thousands of sessions. When the corpus nears it, `find` splits the corpus and asks the parts in parallel, as `query-transcript --all` asks segments. Not built now.
- **Effort and latency.** `--effort medium` is the starting point; acceptance 8 measures the call's time on the real corpus. A slower-than-30-second answer, or poor ranking, moves the effort.

## Acceptance

In the suite (`sminos/tests/run-sminos-tests.sh`, with the stub `claude`):

1. A derive's prompt carries `SUMMARY_ASK` and ends "Answer with these four lines only." (with a charge-name ask, "five lines"); an answer of a line and the three labelled lines records an `in-charge` event whose `summary` holds the three texts; a line of more than 200 characters is cut to 200.
2. An answer whose labelled lines come before the line, or that adds a `name:` line, still records the right line; an answer missing `next:` records the line with no `summary` field and the derive succeeds.
3. Two `derive <member> --compacted` runs in a row both fork (the stub's call log shows two forks); `$SMINOS_HOME/compactions/` is never written.
4. `sminos who @<short>` prints the member's summary lines with the summary's age; `who <commit>` for a commit of that session does too; `list` prints no `doing:`; `list --json` carries `summary` and `summary_age`. A member whose summary came from another machine's log (an event written by another writer) shows it.
5. `sminos find "<question>"` starts one internal process — `SMNS_INTERNAL=1`, its marker present while it runs, `--safe-mode`, `--no-session-persistence`, `--model haiku`, `--tools ""`, no `--bare` — whose standard input holds the question after the corpus; the corpus holds live and stopped members with their summaries, and not the caller, retired or ended members; with `--all` it holds those too.
6. Given a stub answer naming two corpus shorts and one unknown, `find` prints the two rows with their `why:`, summaries and reach lines (a stopped member's says how a message reaches it), and the dropped count; given `{"matches": [], "note": "…"}` it prints `no session matches: …` and exits 4; given a crash, a timeout or text with no JSON object, it exits 1 with the reason on stderr and no match; `--json` gives the documented object. `list --org <words>` keeps the old keyword results (the suite's former `find <words>` cases, moved to it).

Live, after the release reaches both Macs (the orchestrator runs these):

7. A session on the MacBook compacts; within a minute `sminos who @<short>` on the mini prints its three summary lines. Read by someone who has not seen that session: the lines name paths, PRs with their repository, and features, and no unexplained milestone or finding numbers.
8. From a session on the mini, `sminos find "who runs CI for these repositories"` names the MacBook's CI session first with a reason that fits, in under 30 seconds.
9. `sminos find "who is translating the Klingon dictionary"` prints `no session matches` and exits 4.
10. A question that only a stopped session's summary answers names that session, and its reach line says a message wakes it or why it is held.
11. `ci-gate` on the branch is GREEN.

## Execution

**Verification.** One independent review of this spec by `doperpowers:adversarial-reviewer`, and, the execution section having two milestones, its buildability review by the same agent in the same round. The branch is reviewed through `doperpowers:review-code` at the medium rung (`doperpowers:reviewer-medium`): a focused diff in one plugin, whose risks — the derive prompt and parsing, the removed counter, an internal process that must never become a member, a model's output turned into addresses — are pinned by the suite.

**Binding on every milestone.**

- The sminos plugin only, plus the documentation named below; nothing in doperpowers' own `hooks/` or skills changes. The CLI stays `sminos.py` and its sibling modules, standard library only.
- Verify a commit with `ci-gate` from the worktree; do not run the gates' commands locally. One focused Python test file while iterating is fine.
- Version: `scripts/bump-version.sh --plugin sminos` once on the branch, minor (1.56.0 → 1.57.0), in M1's commit; M2 ships in the same release and needs no second bump.
- The sminos skill's text (`sminos/skills/sminos/SKILL.md`) changes only to document `find`'s and `who @`'s interface and that a summary exists. That documents a verb; it shapes no behavior the skill asks of sessions, so it needs no writing-skills evaluation. A line that tells sessions when to search would need one, and is out of scope (§5).
- The repository is public: no hostnames other than the org's machine names already used in its specs, no IPs, accounts, secret names or values, or local absolute paths in code comments, tests' committed fixtures or docs.
- A test that runs real `claude` is not added: the stub stands in, as it does for derive.

### M1 — the summary

**At its end:** every derive asks for and records the summary (§1a–1c), every compaction derives (§2), members carry their summary (§1d), and `who @<session>` and `who <commit|PR>` show it (§4).

**Touches:** `sminos/skills/sminos/scripts/sminos.py` — `derive_prompt`, `answer_line`, a new `answer_summary` and `SUMMARY_*` constants beside `answer_name` and `NAME_LINE_RE`, `derive_member`, `cmd_derive`, the removed `compaction_due` and `compactions_path`, `Member`, `_member`, a new `summary_of` beside `charge_of`, `member_json`, `who_lines` (its reach lines extracted into `reach_lines`), `cmd_who` and the `who` parser, the usage block's `who` and `derive` lines. `sminos/tests/run-sminos-tests.sh` (the derive cases, the every-third-compaction block that exports `SMINOS_DERIVE_COMPACTIONS`, the `who` cases). `sminos/skills/sminos/SKILL.md` (the in-charge paragraph under "Your lines and your project": the summary exists and how to see it; the `who` line under "Who is here"). `sminos/hooks/hooks.json`'s description of `smns-derive.sh` if it states the cadence. `docs/whats-inside.md` (the `names` row says "every third compaction"). `docs/doperpowers/specs/2026-11-08-sminos-derive-on-compact-design.md` §5: one sentence at its head saying this spec's §2 replaces it. The bump.

**Decisions:** `who @<session>` resolves through the tag resolver `say` uses, read-only: it must not record or deliver anything, so call the resolution part alone; a tag that resolves to no session, or to several, exits 4 with `say`'s wording for the same case. The summary ask goes on every derive prompt, the daemon's included; a session whose model answers only the line (an older cached answer style) loses nothing. `answer_summary` is pure and takes the raw fork text, as `answer_name` does.

**Does not touch:** `find`, `sminos_fork.py`, the daemon's derive cadence and caps (`derive --all`, `derive_order`, `DERIVE_EVERY`, `DERIVE_RETRY`), `name.tsx`, `who --session` and `who --thread`.

**Proves:** acceptance 1–4.

### M2 — `find` as the org's search

**At its end:** `sminos find "<question>"` answers from one haiku call over the corpus (§3), and the documentation says so.

**Touches:** `sminos/skills/sminos/scripts/sminos_fork.py` (the shared run helper extracted from `headless_fork`, and `ask_model`). `sminos/skills/sminos/scripts/sminos.py` — `cmd_find` rewritten, new `find_corpus`, `find_entry`, `find_prompt`, `parse_find` and `FIND_PROMPT`, the `find` parser (`question` words, `--all`, `--json`; no `list_flags`), `cmd_list`'s two `a.find` checks (the flag goes with `find`'s use of `cmd_list`), the usage block's `find` line. `sminos/tests/run-sminos-tests.sh` — the stub `claude` gains a branch for a `-p` call without `--resume` (it records its argv, environment and marker as the fork branch does, saves its standard input to `find-prompt.txt`, and answers `STUB_FIND_RESULT`, or fails or crashes on the same switches the fork branch reads); the old `find <words>` cases move to `list --org <words>`; the new cases. `sminos/skills/sminos/SKILL.md` ("Who is here": `find`'s new line, and `list --org <words>` for keyword filtering). `docs/whats-inside.md` (the sminos CLI row's `find`). `docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md` §4: one sentence where it defines `find` as `list --org <words>`, pointing here.

**Decisions:** the corpus is built from the members `project_rows` yields for each known project, deduplicated by session, never from `list`'s printed text. The entry's ages use the CLI's `short_age`. Matches print in the model's order, deduplicated by short. The question is passed to the model verbatim; `find` with no words is a usage error. `ask_model`'s minted session id exists only so a transcript the engine writes despite `--no-session-persistence` is found and deleted, as in `headless_fork`.

**Does not touch:** derive, the summary's shape, `list`'s text and `--json` beyond M1, the guide (§5).

**Proves:** acceptance 5–6, and runs 7–10's commands once on this Mac against a copy of its sminos home (below) to check the prompt on the real model; 7–10 proper run after release.

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
    def answer_summary(text) -> dict | None          # §1b
    def summary_of(member, events) -> tuple[dict | None, str]   # (summary, ts), §1d
    class Member(NamedTuple): … summary: dict | None = None; summary_age: float | None = None
    def member_json(m, project=None, private=True)   # + "summary", "summary_age"
    def reach_lines(project, member) -> list[str]     # from who_lines; used by who_lines and cmd_find
    FIND_PROMPT = …                      # §3b, exact
    def find_corpus(caller_session, include_ended) -> list[tuple[Project, Member]]
    def find_entry(project, member) -> str           # one corpus block, §3a
    def parse_find(text) -> tuple[list[dict], str]   # (matches [{short, why}], note); raises FindFailed on no JSON object
    SMINOS_FIND_TIMEOUT (env), default 120

In `sminos/skills/sminos/scripts/sminos_fork.py`:

    def ask_model(prompt, *, model="haiku", effort="medium", timeout=120) -> ForkAnswer
        # a fresh internal `claude -p` (§3b), prompt on stdin; ForkFailed as headless_fork raises it

CLI:

    sminos find <question…> [--all] [--json]   # exit 0 matches, 4 none, 1 failure
    sminos who @<short|project/alias|alias>      # a session's who_lines, its summary included

The `in-charge` event's optional `summary` field: §1c. M1 produces `answer_summary`, `summary_of`, the `Member` fields, `member_json`'s fields and `reach_lines`; M2 consumes `Member.summary`, `summary_age` and `reach_lines`.

## Outcomes & Retrospective

Pending — written at finish.
