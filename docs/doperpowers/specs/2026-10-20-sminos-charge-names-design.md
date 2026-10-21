# A session is named after what it is in charge of

A session's name is how every other session and the owner tell it apart: it is the alias `sminos list`, the desk and a delivered message show, the `@alias` a peer types, the name in the engine's own prompt footer, `/resume` list and agents view. Today it carries no meaning for most sessions. A session opened in a terminal is `<directory>-<2 hex>` (`doperpowers-c4`, `sminos-23`); one launched by MAWS, the SDK or `--bg` takes its AI-written topic title (`AutoPM charter 프로젝트 맥락`, `<critical> 전달과 단일 message 태그`); only the ones the owner `/rename`d say what they do (`swarm-orch`, `CI-opt`). The logs on the MacBook, 2026-10-20: 325 joins under a generated name, 14 under a title, 106 under a name the owner gave, 23 a host gave, 237 seats. A message from `doperpowers-c4` tells its reader nothing about who wrote it, and which of the two shapes a session ends up with depends on how it was launched.

After this change a session with a generated name is renamed, once its in-charge line exists, to a 2–4 word name that says what it owns (`sminos-desk-orchestrator`, `ask-mod-reload-safety`). The name changes again only when the session's standing responsibility does. A name the owner gave, a seat's alias and a name a host gave are never touched. A peer that still writes the old alias reaches the renamed session and is told its new name.

To see it: in a session that has had ten prompts from its human, run `sminos derive <alias>` (or wait for the daemon's hourly run). It prints the line and the proposed name. At that session's next prompt the footer shows the new name, `sminos list` shows it as the alias with its in-charge line beside it, and the model reads one line of context saying it was renamed. `sminos say "@doperpowers-c4 hi"` from another session still delivers, and prints `note: @doperpowers-c4 is now @sminos-desk-orchestrator#8659f74a`.

Terms are those of the project log design (`docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`): **member**, **alias**, **in-charge line** (§5 there: one line per member saying what it is in charge of; sources `set`, the owner's name, `derived`, the title), **derive** (§5: the daemon forks a member's session headless every hour and asks it for that line, for local members with at least 10 prompts from their human, at most once per 6 hours), **seat**. New here: **engine name**, the name the Claude Code engine registers for a running session in `~/.claude/sessions/<pid>.json` (`name`, with `nameSource` saying where it came from), which is what sminos reads as a seat-less member's alias (`held_alias` in `sminos/skills/sminos/scripts/sminos.py`); **charge name**, a name sminos proposed from the in-charge line; **pending name**, a charge name written for its session's mod to apply; **former alias**, an alias a member held before its current one.

## Progress

- [x] (2026-10-20) Spike: how a plugin can set the engine name, run against engine 2.1.305 (Surprises & Discoveries).
- [x] (2026-10-20) M1 — derive proposes a charge name; sminos knows its own names (53f0b667, fix 6c54c52a; task review clean)
- [x] (2026-10-20) M2 — the name mod applies a pending name (9386dbdc, fix 5cfac89b; task review clean; live check 7/7)
- [x] (2026-10-20) M3 — former aliases still reach, with a note; docs, version, acceptance (4c8176ae, fix 2240f707; task review clean; full ci-gate GREEN on 4c8176ae, sminos gate on 2240f707)

## 1. Where the name comes from

**The in-charge line is the meaning; the name is a short form of it.** The design keeps one source of what a session does, the line (§5 of the project log design). The name is proposed together with that line, so the two cannot drift apart. *Alternative:* have the session's own model name itself, through a guide line or a `charge --name` it calls. That lost on evidence: across every project log on the MacBook, sessions set their own line with `sminos charge` 11 times, mostly through spawn briefs, against 183 lines derive wrote. A model does not name itself unprompted. *Alternative:* a mod that, at some turn count, asks a small model to name the session from `$.session.messages()`. That lost because it re-sends a long conversation uncached to a second model, and it duplicates derive, which already reads the session's whole context through its fork and reuses the parent's prompt cache.

**Derive's fork answers two lines when the member may be named.** The fork already runs. Asking it for one more line costs no extra model call. The prompt for an eligible member (§2) is, verbatim, with the bracketed parts present only when they apply:

```
In one line: what is this session in charge of in this project — its standing responsibility, not its latest step?
On a second line, name the session after that responsibility: `name: ` followed by 2 to 4 lowercase English words joined by hyphens, specific enough that another session reading only the name knows what this one owns. Leave out the project's name, which is shown beside it.[ Its current name is `<current>`: keep it unless the responsibility has changed so that it no longer fits.][ Taken by other sessions: <name>, <name>, ….]
Answer with the two lines only.
```

A member that is not eligible gets today's prompt (`DERIVE_PROMPT`), unchanged.

- A member's **proposed names** are the `name`s of every `in-charge` event with source `derived` that carries one, across the member's session and the sessions it continues (its lineage, as `charge_of` reads them); its **latest proposal** is the newest of them. `<current>` is the engine name the session holds when that is one of its proposed names, else its latest proposal. The latest proposal is passed whether or not the engine has applied it yet. Either way the name stays the same from one derive to the next. Without that instruction the name would be rewritten every 6 hours, because the line is: one desk-orchestrating session's derived lines, 2026-10-19/20, said the same thing seven ways ("Orchestrates the MAWS desk …", "Orchestrating the sminos desk …").
- The taken list is the aliases of the project's other non-retired members, plus the engine names of this machine's other running sessions. The engine refuses a name a live session on the same machine holds, and gives a suffixed name instead (§3). sminos refuses an alias that shadows another current member of the project (`shadowing`). Naming the taken names keeps the fork from choosing either.
- **Format: 2–4 words, lowercase ASCII, hyphen-joined, no project name.** The owner chose 2–4 words and descriptive over the 2–3 first proposed (2026-10-20). Lowercase ASCII kebab is what can follow `@` in a message without quoting. The project is already shown beside the alias everywhere a name appears, and `@<project>/<alias>` qualifies it. *Alternative:* free form, Korean allowed. That lost because a name with spaces or Hangul cannot be typed as an `@` tag.

**Parsing the answer.** Take the first mark span's text when the answer has marks (`extract_marks`, as `answer_line` does; the fork runs under the session's output style), else the whole text. The **line** is the first non-empty line that does not start with `name:` (case-insensitive), cut to `DERIVE_LINE_MAX`, which is today's `answer_line` with one skip added. The **name** is the rest of the first line that starts with `name:`. It is lowercased, and surrounding backticks, quotes and one trailing period are trimmed. It is kept only if it matches `^[a-z0-9]+(?:-[a-z0-9]+){1,3}$`, is at most 48 characters, and is not in the taken list. Otherwise this derive records the line with no name and prints why (`no name: <reason>`). A missing or invalid name never fails the derive, because the line is still worth recording.

**Recording.** The `in-charge` event gains an optional field `name` (Interfaces). It is written on a derived event when the member is eligible and the answer's name was kept. `sminos derive` prints `<alias>: <line>` as today, and then, when a name was kept, `<alias>: name <name>` on a second line.

**Cadence: derive's own.** The first name arrives with the first derived line: 10 prompts from the human, then at most every 6 hours, from the daemon's hourly `derive --all`. The owner chose this over a lower naming threshold, to spend no extra model calls (2026-10-20). A short session keeps its generated name. A member whose line was `set` (`sminos charge`, `spawn --brief`) is not derived and so is not named. Today that is almost only seats, which are not named anyway (§2).

## 2. Which names sminos may replace, and knowing its own

**Eligibility is read from the session's running engine record, not from the member row.** The member row cannot be trusted for this. `held_alias` keeps the alias a session already holds, and that alias's source, whenever the engine name is one it treats as generated (`collision` among them) or would shadow another member. So an owner's `/rename` that collided, or that shadows another member's alias, still lists as the old `derived` alias (the design review ran the function: both return `('project-ab', 'derived')`). Eligibility judged from the row would overwrite those names. Derive reads the record `_on_sight` chooses, as it reads `before` (§3):

| the running engine record | named? |
|---|---|
| `nameSource` `derived` (the engine's `<dir>-<hex>`) | yes |
| `nameSource` `auto` (the engine promoted a title: SDK, MAWS, `--bg`, bridge sessions) | yes |
| `name` is one of the member's proposed names (§1), whatever its `nameSource` (`hook`, or `user` after a resume) | yes; the name is passed to the fork to keep |
| any other: `user` (the owner's `/rename` or `--name`), `peer` (a host named it), `collision`, a `hook` name that is not the proposal | no |
| no running record (the session is stopped) | no: the line only |
| the member is a seat | no |

`collision` is excluded because the engine also records it for the owner's own `/rename` that collided (`QTn` in the engine: a `user` request that yields is recorded `collision`). Treating it as generated would overwrite a name the owner chose.

**sminos decides which names are its own from its log, not from the engine's source label.** The spike showed the engine does not keep that label: a name set through the hook is registered `hook`, and after a resume the same name is restored as `user`, because the transcript stores no source. If sminos trusted the label, one resume would turn every charge name into "the owner named it". Derive would stop (`derive_refusal`: "its human named it"), the name would replace the derived line as the member's in-charge line (`charge_of`, source `name`), and the name could never follow the responsibility again. So, where a member row is built (`_member`), a seat-less member whose alias is one of its proposed names (§1) has name source `charge`, whatever the engine says, provided that, for a local member with a running engine record, the record's name is that same name. Without that proviso, an owner rename that `held_alias` hides would still read as sminos's. The test is "one of", not "the latest". A session that holds an applied name A while a newer proposal B waits, or was refused because B was taken (§3), must still read A as sminos's. Otherwise the resumed session's `user` label would stop every later derive. `charge_of`'s `name` source and `derive_refusal`'s "its human named it" read `user` only, so after the relabel they apply only to a `user` name sminos never proposed. `publish_renames` publishes `charge` as it publishes any source change, so other machines and the desk read the same label. The relabel is made only where the session's running engine record is read, its own machine; a row built without that record (another machine's member, a stopped one) takes the source its machine last published, so a demotion back to `user` there reaches every reader too. If the owner later `/rename`s the session to a name sminos never proposed, the source reads `user` again: their name wins, and derive stops proposing (the member is no longer eligible). An owner who renames it to one of sminos's proposed names is indistinguishable from sminos, and no harm follows from that.

## 3. Applying a name: the engine's hook path, at the next prompt

**The only way a plugin renames a session the way sminos needs is `sessionTitle` from a `UserPromptSubmit` hook.** The engine (2.1.304 source, `aMt` → `zdt(title, "hook")`, confirmed live on 2.1.305) treats it as a rename. It writes the `custom-title` and `agent-name` records, registers the engine name with `nameSource: "hook"`, applies its own collision rule (a name a live session on this machine holds yields a suffixed one), and is not overwritten later by the engine's title promotion, which replaces only `derived` and `auto` names. A function-hook mod returns it from `classic.UserPromptSubmit`. *Alternatives, both measured or read:*
- `$.command.run({ command: "rename", args })` runs the owner's `/rename` and registers `user`, the label sminos must not read as its own (§2). It also writes command rows into the transcript, and it runs only once the session is idle.
- `sessionTitle` from `SessionStart` changes only the session's title. At startup and at resume the engine name stayed what it was (spike). Using it would leave the title and the engine name disagreeing.

The cost is timing: a pending name applies at the session's next prompt. That prompt can be the owner's, a peer message the engine submits (`source: system`), a plugin's prompt, or a scheduled wake-up. A session nobody prompts again keeps its old name, and its alias with it. That is acceptable: a session no one talks to is not being misread.

**The name the proposal replaces is read before the fork.** The fork can run for up to two minutes (`SMINOS_DERIVE_TIMEOUT`, 120 s). If the owner `/rename`s the session in that time and derive read the engine name only afterwards, the owner's new name would become the `from` the mod checks against, and `name-due` would overwrite it at the next prompt. So derive reads the member's running engine record (the one `_on_sight` reads) and decides eligibility before it starts the fork, and keeps that record's name as `before`. When the fork returns, it reads the record again. If the record's name is no longer `before`, or the session no longer runs in that process, the naming part of this derive is discarded: the line is recorded without a `name`, and `no name: renamed during derive` is printed. The next derive judges the member afresh, and a `user` name is refused there as today.

**Handing the name to the session.** Derive runs in the daemon or a terminal, never in the session, so the name crosses through a file. After recording an event with a name:
- `before` already equals the name → remove any pending file for the session;
- it differs → write the pending file (Interfaces) with `from` set to `before`;
- no running record when derive started (the session is stopped) → nothing. A resume draws a new engine name anyway. The next derive after the session runs again writes the file.

`derive --all` also removes pending files older than 7 days. A session that went that long without a prompt gets a fresh file from its next derive.

**The mod checks before it applies; the CLI owns the check.** `sminos/hooks/mods/name.tsx`, registered in `sminos/hooks/mods/register.tsx`, hooks `classic.UserPromptSubmit`:
1. Let the hooks beneath answer (`next(e)`). If their result already sets `sessionTitle`, or the session is an internal fork (`SMNS_INTERNAL`), return it unchanged.
2. Read the session's pending file (`$.fs`, under the sminos home: `SMINOS_HOME`, else `DAEMON_HOME`, else `$HOME/.claude/sminos`, as `root()` resolves it). If there is none, or its text is the text this module last handled, return the result unchanged. This read is the only cost a prompt pays when no rename is due.
3. Otherwise run `sminos name-due --session <id>` (`$.process.run`, bounded as `address.tsx` bounds `who`). Whatever the attempt's outcome (a name, nothing, a non-zero exit, a throw or a timeout), remember the file's text as handled, so the check runs once per pending name and not once per prompt. A rename that misses through a transient failure gets another chance when the next derive rewrites the file.
4. If it printed a name, return the result with `sessionTitle` set to it and one line added to `additionalContext`: `sminos renamed this session to "<name>" after its standing responsibility; other sessions now see and address it by that name.` If it printed nothing, return the result unchanged.

`name-due` prints the name only when the running engine record's name still equals the file's `from` and differs from the file's `name`, and the name is still free. That catches every case where something moved between derive and this prompt: the owner `/rename`d it, which is the race this check exists for; the name is already applied; a resume put the session in a new process under a new engine name. **Free** means two things: no other non-retired member of the session's project holds it as its alias, on any machine (else `shadowing` would keep the old alias while the engine showed the new name); and no other running session on this machine holds it as its engine name (else the engine would yield a suffixed `collision` name, which is not sminos's and so not eligible again). A proposal that is no longer free is not due. The file stays, the mod's memo stops it from asking again, and the next derive is told the name is taken and proposes another. What is left is the window between `name-due` answering and the engine applying, a fraction of a second. A collision in that window leaves the session under the engine's suffixed name, which is still descriptive. That is accepted, not handled. The check reads the engine record, not the hook input's `session_title`. `session_title` is the custom title, and a session named by title promotion (`auto`) has none in its transcript (7 of the 8 such sessions on the MacBook; the eighth was later `/rename`d), so comparing against it could not tell "unchanged" from "renamed" for those. *Alternative:* the mod scans `~/.claude/sessions/*.json` itself. That lost because it re-implements in TypeScript the choice of the running record among a crashed process's leftovers, which `_on_sight`/`peer_running` already make. A process spawn once per rename is cheap.

Once the engine applies the name, nothing more is needed. `held_alias` takes a non-generated engine name as the alias. `publish_renames` (the daemon, every tick) appends `renamed` with source `charge` (§2). `sminos who --session` (the commit address) picks it up within its minute. The guide (`smns-guide.sh`) shows it at the next compaction or resume.

## 4. Former aliases still reach the member

A rename breaks every `@alias` a peer learned. Today a name matches only a member's current alias, short, or session id (`match_members` and `find_target`'s `matches` in `sminos.py`). After this change, each lookup that matches by alias falls back, **in the same scope and only when no member's current alias matches**, to members that formerly held that alias. A former alias is any alias of the member's own `joined`/`renamed` events and its lineage's, other than its current alias and its short.

- **Precedence:** a current alias always wins. A former alias is only a fallback, so a session that now goes by a name, or later takes it, owns it. If several members formerly held it (generated names do repeat over time, as `doperpowers-19` did), the one that held it most recently wins: the latest ts among the `joined`/`renamed` events carrying it. Equal ts is refused as ambiguous, named as today.
- **Scope:** the scope rules do not change. A bare `@old` looks in the sender's project. `@old#short` looks across the org, and the short still has to match. `@<project>/old` looks in that project. Retired members still answer to nothing.
- **The note:** whenever a target was found by a former alias, the command prints `note: @<old> is now <label>` on stderr through the CLI's `warn`, where `<label>` is the member as `candidate_labels` names it (`@alias#short`, or project-qualified across projects). This holds for `say` (once per tag) and for every member verb that goes through `find_target` (`steer`, `watch`, `charge <member>`, …). Stderr leaves stdout contracts (`--json`) unchanged, and a calling model reads both. The recorded recipient is the member's current alias, as for any tag.

This applies to any rename, including the owner's `/rename`, not only to charge names: the problem it fixes is the rename, whoever made it. The owner asked for it on 2026-10-20 ("old aliases are still found and messaged, and a note says the name changed").

## Acceptance

Each item is behavior someone can check. Items 1–5 and 7–8 run in `sminos/tests/run-sminos-tests.sh` (the `sminos` gate) against the stub `claude` its derive tests already use (`STUB_FORK_RESULT`). Item 6 runs in the mods suite and the live check.

1. **A generated-name member gets a charge name.** For a `derived`-named member with ≥10 human prompts, `sminos derive <alias>` with the fork answering `Owns the desk's uplink.\nname: desk-uplink-owner` prints `<alias>: Owns the desk's uplink.` and `<alias>: name desk-uplink-owner`. It appends an `in-charge` event `{source: derived, text: …, name: desk-uplink-owner}`, and writes `$SMINOS_HOME/names/<session>.json` with `name: desk-uplink-owner` and `from` set to the engine record's name. The fork's prompt carries the naming part and the taken list.
2. **Names it must not touch.** A member named `user` (a name sminos never proposed for it) is refused by derive as today (`not derived — its human named it`): no fork, no event, no pending file, as the existing test asserts. For members whose running engine record is named `peer`, `collision` or a foreign `hook` name, for a stopped member, and for a seat with no `set` line, the fork's prompt is today's `DERIVE_PROMPT` verbatim, the event carries no `name`, and no pending file is written. The same holds for a member that joined under a generated alias and was then `/rename`d by its owner to a name that collided (engine record `collision`) or that shadows another member's alias (engine record `user`). Its member row still lists the old `derived` alias, and it must still not be named. These two cases are built by renaming an already-joined member, not by fixtures whose row already says `collision` or `user`. If the stub fork changes the member's engine record to a `user` name while it runs, the line is recorded with no `name`, `no name: renamed during derive` is printed, and `name-due` prints nothing afterwards.
3. **Stability.** With a proposed name already in the log, the prompt says `Its current name is \`desk-uplink-owner\``. If the fork answers the same name and the engine name already equals it, no pending file remains. If it answers a different valid name, a pending file with the new name and `from: desk-uplink-owner` is written.
4. **Bad names are dropped, the line kept.** Answers naming `Desk Uplink`, `one-two-three-four-five`, a 60-character name, a taken alias, or no `name:` line all record the line with no `name`, print `no name: <reason>`, and write no pending file.
5. **sminos knows its own name after a resume.** A member whose engine record says `nameSource: "user"` and whose name is one of its proposed names lists with `name_source: "charge"` in `sminos list --json`. Its in-charge line is the derived one, not the name. `derive` does not refuse it with "its human named it". The daemon's tick publishes `renamed` with `name_source: charge` once. When the record's name then changes to something else (the owner's `/rename`), it lists as `user`, and its next derive is refused with "its human named it", as today. The sequence resume → a derive proposing a different name B → B taken by another session before it applies (`name-due` prints nothing) still lists the session as `charge` under its applied name, and the next derive runs, is told B is taken, and its new proposal applies.
6. **The mod applies it at the next prompt, once.** In the mods suite (`sminos/tests/mods/name.test.ts`): with a pending file and `name-due` printing a name, the hook returns `sessionTitle` and the context line. A second prompt with the same file runs no second `name-due`. With no file, the CLI is never run. A result from beneath that already sets `sessionTitle` passes unchanged. Under `SMNS_INTERNAL` nothing is read. Live (`sminos/tests/mods/live-name-check.py`, by hand, a few haiku turns): an interactive session with the sminos plugin and a pending file whose `from` is its engine name is renamed at its next prompt (the engine record shows the name with `nameSource: "hook"`, the transcript a `custom-title` record), and a session `/rename`d before that prompt keeps its own name.
7. **`name-due`.** It prints the name when the running record's name equals `from` and differs from `name`. It prints nothing when the record's name equals `name`, when it is neither, when there is no pending file, and when no record of the session runs. It also prints nothing when, after the file was written, the name came to be held by another member of the project (a remote member, through its log events) or by another running session on this machine (its engine record).
8. **Former aliases.** After a member's alias moves from `oldname` to `newname` (a `renamed` event), `sminos say "@oldname hi"` from another member of the project records the message to `newname`, delivers it, and prints `note: @oldname is now @newname#<short>` on stderr. The same holds for `@oldname#<short>` from another project and for `sminos steer oldname …` (`find_target`). If another current member's alias is `oldname`, that member gets the message and no note is printed. If two members held `oldname`, the more recent holder gets it. A retired member's former alias reaches nothing.

## Execution

**Binding on every milestone.** The sminos plugin only: nothing in doperpowers' own `hooks/mods/` changes. The CLI stays one Python file plus its siblings under `sminos/skills/sminos/scripts/`, standard library only. Mods are TypeScript under `sminos/hooks/mods/`, typechecked by `tests/mods/typecheck.sh` (the `mods-types` gate; it needs the engine's declarations laid in `.claude-plugin/types/`, `tests/mods/typecheck.sh --lay`, or copied from the main checkout's gitignored `.claude-plugin/types/`). Verify commits with `ci-gate` from the worktree, not by running the gates locally; one focused test file while iterating is fine. The engine facts this design rests on (§3 and Surprises) are pinned by the live check in M2, not by unit tests: a unit test cannot see the engine.

### M1 — derive proposes a charge name; sminos knows its own names

**At its end:** derive builds the naming prompt for eligible members, parses and validates the name, records it on the `in-charge` event, and writes or removes the pending file. Member rows report `charge` for sminos's own names. `charge_of` and `derive_refusal` stop reading those as the owner's. `sminos name-due` answers. `derive --all` sweeps stale pending files.

**Touches:** `sminos/skills/sminos/scripts/sminos.py` (`DERIVE_PROMPT` and its eligible variant, `derive_line`/`answer_line`, `cmd_derive`, `derive_refusal`, `charge_of`, `_member`, a new `name-due` verb in the parser), `sminos/skills/sminos/scripts/sminos_daemon.py` only if `publish_renames` needs a change to publish `charge` (it should not: it publishes `m.name_source`), and `sminos/tests/run-sminos-tests.sh` (the in-charge section and its stub fork).

**Interfaces:** produces the `in-charge` `name` field, the pending file, `name-due`, and the `charge` name source (Interfaces and Dependencies).

**Decisions:** eligibility is §2's table, read from the session's running engine record (never from the member row, which `held_alias` can leave stale). The taken list and `<current>` are as in §1. Parsing and validation are as in §1. The pending-file rules are as in §3. The relabel lives where the member row is built, so `list`, `find`, the daemon and the desk all read one answer. `name-due` exits 0 in every case except a usage error, because the mod reads its stdout and must never fail a prompt. The stub fork already takes `STUB_FORK_RESULT`; the tests also need to read the prompt it was given (log it in the stub, as `calls.log` logs argv), and acceptance 2's race needs the stub to rewrite the member's engine record while it runs (an environment variable naming the record and the name to write, beside the stub's existing `STUB_FORK_*` switches).

**Does not touch:** the mod, name resolution (`match_members`, `find_target`), docs, version.

**Proves:** acceptance 1–5 and 7.

### M2 — the name mod applies a pending name

**At its end:** a running session with a due pending name is renamed at its next `UserPromptSubmit` through the engine's hook path, once, and the model is told.

**Touches:** `sminos/hooks/mods/name.tsx` (new), `sminos/hooks/mods/register.tsx`, `sminos/tests/mods/name.test.ts` (new, beside `address.test.ts`, whose way of standing in for `$.process.run` and `$.env` it follows), `sminos/tests/mods/live-name-check.py` (new; isolation as `live-control-check.py`/`live-bridge-check.py` do it: temporary HOME and SMINOS_HOME, own tmux server, haiku).

**Interfaces:** consumes the pending file and `name-due` from M1.

**Decisions:** the hook algorithm is §3's four steps, and the context line is the exact string there. Register it after the address in `register.tsx`, since nothing depends on its place among the plugin's own hooks. Only `classic.UserPromptSubmit`: not `SessionStart`, whose `sessionTitle` does not rename (§3). The live check also asserts the two engine facts this design relies on, so an engine release that changes them fails it loudly: `SessionStart`'s `sessionTitle` leaves the engine name as it was, and after a resume a hook-set name is registered `user`. If either changes, §2 and §3 are revisited, not patched around.

**Does not touch:** the CLI beyond what M1 produced.

**Proves:** acceptance 6.

### M3 — former aliases still reach, with a note; docs, version, acceptance

**At its end:** §4 holds for `say` and every `find_target` verb. The docs say what changed, sminos is bumped, and the acceptance runs green.

**Touches:** `sminos/skills/sminos/scripts/sminos.py` (`_projection` keeps each session's alias history; the member row carries its former aliases; `match_members`, `resolve_tag` and `find_target`'s matching take the fallback and emit the note), `sminos/tests/run-sminos-tests.sh`, `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md` (the `in-charge` row of the event table gains `name`, and §5 gets one sentence pointing here), `sminos/hooks/hooks.json` (its description names the mod), `CLAUDE.md` (the `sminos/` row's mods list gains `name.tsx`, one sentence), and the version via `scripts/bump-version.sh --plugin sminos` (minor bump).

**Interfaces:** none new beyond the note's format (§4).

**Decisions:** one predicate decides "does name N reach member m, and was it by a former alias", used by both `match_members` and `find_target`, so the two cannot disagree. The current-before-former order is applied per lookup pass, inside the scope that pass already searches. The note is emitted once per resolved tag, by the resolving code, not by each caller.

**Does not touch:** the sminos skill body (`sminos/skills/sminos/SKILL.md`). The note tells a model what it needs at the moment it matters, and a skill edit would need its own evaluation (CLAUDE.md, "Skill Changes Require Evaluation") for no behavior a model lacks. MAWS's desk, which resolves names on its own side, is also out of scope.

**Proves:** acceptance 8; then the whole acceptance list, the `sminos` and `sminos-mods` gates and `mods-types` through `ci-gate`, and the live check by hand.

## Concrete Steps

From the worktree root:

    sminos/tests/run-sminos-tests.sh                 # the sminos gate locally, while iterating on M1/M3
    sminos/tests/mods/run.sh                         # the sminos-mods gate, M2
    tests/mods/typecheck.sh                          # mods-types (lay or copy the engine types first)
    ci-gate                                          # every gate on the committed HEAD: GREEN <url>
    python3 sminos/tests/mods/live-name-check.py     # by hand; prints one ok/FAIL line per engine fact and behavior

A manual end-to-end check, after installing the branch's sminos: in a member session with ≥10 prompts, `sminos derive <alias>` prints the line and `name <name>`; `cat ~/.claude/sminos/names/<session>.json` shows it pending; the next prompt in that session changes the footer's name; `sminos list` shows the new alias with `charge` in `--json`; `sminos say "@<old alias> ping"` from another session prints the note.

## Interfaces and Dependencies

**`in-charge` event, field `name`** (optional string): the charge name sminos proposed with this line. It is present only on `source: derived` events of eligible members whose answer's name was kept. Readers that do not know it ignore it, as the log's events allow.

**Pending file** `$SMINOS_HOME/names/<session-uuid>.json`, directory mode 0700, file 0600, written atomically (temporary file and rename):

```json
{"session": "<uuid>", "name": "<charge name>", "from": "<engine name when written>", "line": "<in-charge line>", "ts": "<ISO 8601 UTC>"}
```

**`sminos name-due --session <uuid>`**: stdout is the name to apply (one line) or nothing. It exits 0 except on a usage error. The name is due when the pending file exists and parses, a running engine record of the session exists (as `_on_sight` chooses it), its `name` equals `from`, it differs from `name`, and `name` is still free (§3).

**Name source `charge`**: in member rows (`list --json`'s `name_source`) and in `renamed`/`joined` events. It means the alias is one of the session's proposed names, and, on its machine, its running engine name too (§2).

**Former-alias note**: stderr, `note: @<old> is now <label>`, once per resolution by a former alias (§4).

**Engine dependency**: Claude Code ≥ 2.1.304. `UserPromptSubmit` `hookSpecificOutput.sessionTitle` renames with source `hook`. Pinned by `live-name-check.py`.

## Surprises & Discoveries

- Observation: `sessionTitle` from `UserPromptSubmit` renames the session fully; from `SessionStart` it sets only the title. Evidence: spike, engine 2.1.305, a `classic.SessionStart` hook returning `spike-start-name` and a `classic.UserPromptSubmit` hook returning `spike-prompt-name-ok`. After startup the registry read `{"name": "work-0b", "nameSource": "derived"}` while the next `UserPromptSubmit` saw `session_title: "spike-start-name"`. After the prompt it read `{"name": "spike-prompt-name-ok", "nameSource": "hook"}`, with `custom-title` and `agent-name` records written. After a resume, `SessionStart`'s title wrote a `custom-title` record and changed the footer, but the registry name stayed.
- Observation: a resume restores a hook-set name as `user`. Evidence: same spike, after `claude --resume`: `{"name": "spike-prompt-name-ok", "nameSource": "user"}`. The transcript's `custom-title` records carry no source, and the engine's restore path defaults to `user` (`JEe(R.agentName, …)` → `Wz(name, …, "user")`). This is why §2 identifies sminos's names from its log.
- Observation: sessions named by title promotion have no `custom-title` record. Evidence: of the 8 `auto`-named members on the MacBook, 7 have no `custom-title` record (5 to 2 674 `ai-title` records each); the eighth's one custom title is a later `/rename` (`sitting-fork`). This is why `name-due` compares engine names, not `session_title`.
- Observation: the engine records a collided `/rename` of the owner's as `collision`. Evidence: engine 2.1.304 `QTn`: `n === "user"` skips the pre-check, and a yield from `Zrn(e, "rename")` returns `recordSource: "collision"`. This is why `collision` is not eligible.

- Observation: `name-due` reconciles the project (`members(project)`) before it answers, so it is not instant. Evidence: M1 executor. The mod's bound on it (M2) must allow for that.

- Observation: a resumed session's engine record first carries a fresh generated `derived` name and only seconds later the restored `user` name. Evidence: `live-name-check.py`, M2, engine 2.1.305, sampling the record for 20 s after `--resume`. §2's "restored as `user`" holds once the restore lands; in the window, `name-due` sees a name other than `from` and prints nothing, and a derive is discarded as "renamed during derive", so nothing is applied wrongly.

## Decision Log

- Decision: verification. One independent spec review by `doperpowers:adversarial-reviewer` (the spec is technical-heavy: engine behavior, a cross-process hand-off, name resolution), and in the same round its buildability review of the execution section (three milestones). The branch review is `doperpowers:review-code` at medium (`reviewer-medium`). The live check runs by hand before merge.
  Rationale: the risk is in delivery (§4 decides which session receives a message) and in never overwriting a name the owner gave (§2, §3). Both are pinned by acceptance tests, so a single medium reviewer on a branch with those tests is proportionate. The panel is for changes whose failure modes the tests cannot reach.
  Date/Author: 2026-10-20, doperpowers-c4.
- Decision: the engine name a proposal replaces is read before the fork and re-checked after it; acceptance 2 and 5 follow the existing refusal of `user`-named members.
  Rationale: buildability review, 2026-10-20. An owner `/rename` during the fork (up to 120 s) would otherwise become the pending file's `from` and be overwritten at the next prompt; and `derive_refusal` already refuses a member its human named, which the first draft's acceptance contradicted. Rejected: re-reading after the fork only, which is the race itself.
  Date/Author: 2026-10-20, doperpowers-c4.
- Decision: naming eligibility comes from the running engine record, not the member row. The `charge` relabel also requires the record's name to match. `name-due` refuses a proposal another member or another local session took after derive.
  Rationale: design review, 2026-10-20. `held_alias` returns the old alias and source for an owner rename that collided or that shadows another member, so a row-based check would overwrite the owner's name. A name taken after derive would leave the engine and sminos disagreeing (shadowing) or produce an engine `collision` name. Rejected: reconciling the applied name after the fact. The window between `name-due` and the engine's apply is a fraction of a second, and the outcome of a collision there (a suffixed, still descriptive name) is acceptable.
  Date/Author: 2026-10-20, doperpowers-c4.
- Decision: a name is sminos's when it is any of the session's proposed names, not only the latest.
  Rationale: design review round 2, 2026-10-20. A resumed session holding applied name A (engine label `user`) with a newer proposal B pending, or refused as taken, would otherwise read as owner-named, and derive would stop for good. Rejected: recording the applied name in a separate event. The set of proposals already identifies it, needs no new event kind, and an owner choosing one of sminos's names is harmless.
  Date/Author: 2026-10-20, doperpowers-c4.
- Decision: a `charge` label already in the log yields to the running engine record's `nameSource` when that record no longer holds the name. 
  Rationale: M1 execution. Once `publish_renames` has logged `charge`, `held_alias` returns the logged label for an owner rename it hides (shadowing), so without this the §2 proviso would not hold. Tested: such a member lists as `user` and derive refuses it.
  Date/Author: 2026-10-20, M1 executor.
- Decision: the taken list (§1) also carries the aliases of the project's non-retired seats with no member row, which `shadowing` refuses too; it leaves out the member's own lineage and derive's internal forks; names are compared lowercased and only names of the charge-name form are listed in the prompt.
  Rationale: M1 execution; the list exists to keep the fork from proposing what the engine or sminos would refuse.
  Date/Author: 2026-10-20, M1 executor.
- Decision: "renamed during derive" (§3) also compares the record's pid, so a session restarted in another process during the fork counts as moved. Trimming strips quotes, then one trailing period, then quotes again. Refusal reasons print as `<alias>: no name: <reason>`, and only for eligible members. `name-due` finds the project from the engine record (`record_project`), so the pending file keeps the spec's fields; an unexpected error is a stderr warning with exit 0, and a session id that is not a UUID is a usage error. The per-member body of derive is `derive_member()`, so a stopped member (which the CLI's reconciliation retires before derive reaches it) is testable directly.
  Rationale: M1 execution, in the spirit of §1 and §3.
  Date/Author: 2026-10-20, M1 executor.
- Decision: the `charge` relabel (§2) is made only from a running engine record; rows without one take the published source.
  Rationale: M1 task review, 2026-10-20. Relabelling every row whose alias is a proposal turned a demotion the owning machine published (`user`, after an owner rename that shadows) back into `charge` on other machines, so local and remote rows disagreed and `charge_of` chose different lines. The owning machine is the one that can see the engine; the others read its verdict from the log.
  Date/Author: 2026-10-20, doperpowers-c4 (controller).
- Decision: a running seat-less session's `joined` event (`join_on_sight`) takes its source through the same relabel, so a resumed charge-named session that re-joins after being retired logs `charge`, not the engine's `user`.
  Rationale: M1 fix. `publish_renames` compares against the last `renamed` or `joined`; an earlier `renamed(charge)` hid the raw `user` join from the tick, so the log would have kept `user` for that session.
  Date/Author: 2026-10-20, M1 executor.
- Decision: the mod (§3) treats a `name-due` that exits non-zero as an answer with no name (the file is remembered as handled); only a throw or timeout leaves it for the next prompt. It skips the `poll_event` pass of `UserPromptSubmit` (it runs while the event is queued; the prompt's own submit follows). The session id is the hook input's; an empty `SMINOS_HOME`/`DAEMON_HOME` counts as unset, as `root()` reads it. The mods manual (`sminos/hooks/mods/README.md`) gains a `name` section.
  Rationale: M2 execution, in the spirit of §3's steps 1–3.
  Date/Author: 2026-10-20, M2 executor.
- Decision: the mod bounds `name-due` at 10 s, the bound the address puts on `who` (§3), not the 30 s first built.
  Rationale: a CLI that hangs every time costs that bound on each prompt until the file changes or the sweep removes it; `who` pays a comparable read, so its bound is the measured one.
  Date/Author: 2026-10-20, doperpowers-c4 (controller).
- Decision: any `name-due` attempt marks the pending file's text handled, a throw or a timeout included (§3 step 3), replacing "a CLI that could not run leaves the file unhandled".
  Rationale: the dispatching session, 2026-10-20. `name-due` reconciles the project, which can wait on a lock held elsewhere; retrying on every prompt turned a CLI that keeps hanging into 10 s on each prompt for as long as the file exists. A rename missed through a transient failure is retried when the next derive rewrites the file (within 6 hours), which is cheaper than a stalled prompt.
  Date/Author: 2026-10-20, doperpowers-c4.
- Decision: the former-alias note (§4) is written by `note()`, a sibling of `warn` that prints `sminos: note: …`, not by `warn` itself, whose `warning:` prefix would read a rename as a fault. `<old>` is the bare name the tag carried, without its `#short` or `project/`; `<label>` is project-qualified when the member's project is not the caller's. A former alias leaves out the current alias and the short of every session in the lineage (the placeholders a nameless session joined under). The predicate is `alias_reach`, and the current-before-former order is `current_first`, both shared by `match_members` and `find_target`. The latest holder is chosen before `one_per_session`, so a session held in two projects' logs is not refused as ambiguous with itself. `former_aliases` stays off `list --json`, since no consumer needs it. Refusals' "elsewhere" lists now name other projects' members that held the name before.
  Rationale: M3 execution, in the spirit of §4.
  Date/Author: 2026-10-20, M3 executor.

## Outcomes & Retrospective

Pending — written at finish.
