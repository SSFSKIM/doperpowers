# A session is named after what it is in charge of

A session's name is how every other session and the owner tell it apart: it is the alias `sminos list`, the desk and a delivered message show, the `@alias` a peer types, the name in the engine's own prompt footer, `/resume` list and agents view. Today it carries no meaning for most sessions. A session opened in a terminal is `<directory>-<2 hex>` (`doperpowers-c4`, `sminos-23`); one launched by MAWS, the SDK or `--bg` takes its AI-written topic title (`AutoPM charter 프로젝트 맥락`, `<critical> 전달과 단일 message 태그`); only the ones the owner `/rename`d say what they do (`swarm-orch`, `CI-opt`). The logs on the MacBook, 2026-10-20: 325 joins under a generated name, 14 under a title, 106 under a name the owner gave, 23 a host gave, 237 seats. A message from `doperpowers-c4` tells its reader nothing about who wrote it, and which of the two shapes a session ends up with depends on how it was launched.

After this change a session with a generated name is renamed, once its in-charge line exists, to a 2–4 word name that says what it owns (`sminos-desk-orchestrator`, `ask-mod-reload-safety`). The name changes again only when the session's standing responsibility does. A name the owner gave, a seat's alias and a name a host gave are never touched. A peer that still writes the old alias reaches the renamed session and is told its new name.

To see it: in a session whose model has made ten tool calls, run `sminos derive <alias>` (or wait a few minutes for the daemon's run). It prints the line and the proposed name. Within a minute, once that session is between turns, the footer shows the new name, `sminos list` shows it as the alias with its in-charge line beside it, and the session's transcript carries the engine's own note that it was renamed. `sminos say "@doperpowers-c4 hi"` from another session still delivers, and prints `note: @doperpowers-c4 is now @sminos-desk-orchestrator#8659f74a`.

Terms are those of the project log design (`docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`): **member**, **alias**, **in-charge line** (§5 there: one line per member saying what it is in charge of; sources, as this design reorders them, `set`, `derived`, the owner's name, the title), **derive** (§5: the daemon forks a member's session headless and asks it for that line, at most once per 6 hours; this design changes its threshold from 10 prompts from the human to 10 tool calls by the session's model, and brings a member's first derive within about 5 minutes of its reaching that threshold, §1), **seat**. New here: **engine name**, the name the Claude Code engine registers for a running session in `~/.claude/sessions/<pid>.json` (`name`, with `nameSource` saying where it came from), which is what sminos reads as a seat-less member's alias (`held_alias` in `sminos/skills/sminos/scripts/sminos.py`); **charge name**, a name sminos proposed from the in-charge line; **pending name**, a charge name written for its session's mod to apply; **former alias**, an alias a member held before its current one.

## Progress

- [x] (2026-10-20) Spike: how a plugin can set the engine name, run against engine 2.1.305 (Surprises & Discoveries).
- [x] (2026-10-20) M1 — derive proposes a charge name; sminos knows its own names (53f0b667, fix 6c54c52a; task review clean)
- [x] (2026-10-20) M2 — the name mod applies a pending name (9386dbdc, fix 5cfac89b; task review clean; live check 7/7)
- [x] (2026-10-20) M3 — former aliases still reach, with a note; docs, version, acceptance (4c8176ae, fix 2240f707; task review clean; full ci-gate GREEN on 4c8176ae, sminos gate on 2240f707)
- [x] (2026-10-21) Branch review (reviewer-medium): three P2 findings. name-due's eligibility recheck and the former-alias session binding are fixed (b1169e2d, d9dbbdb0). The cross-project `charge` provenance is dropped along with the `charge` source (Decision Log).
- [ ] (2026-10-21) Owner's design changes: M4 — derive for every member, from 10 tool calls, soon; no `charge` source; M5 — the mod renames through the engine's `/rename` between turns. Then the branch review again at medium.

## 1. Where the name comes from

**The in-charge line is the meaning; the name is a short form of it.** The design keeps one source of what a session does, the line (§5 of the project log design). The name is proposed together with that line, so the two cannot drift apart. *Alternative:* have the session's own model name itself, through a guide line or a `charge --name` it calls. That lost on evidence: across every project log on the MacBook, sessions set their own line with `sminos charge` 11 times, mostly through spawn briefs, against 183 lines derive wrote. A model does not name itself unprompted. *Alternative:* a mod that, at some turn count, asks a small model to name the session from `$.session.messages()`. That lost because it re-sends a long conversation uncached to a second model, and it duplicates derive, which already reads the session's whole context through its fork and reuses the parent's prompt cache.

**Derive's fork answers two lines when the member may be named.** The fork already runs. Asking it for one more line costs no extra model call. The prompt for an eligible member (§2) is, verbatim, with the bracketed parts present only when they apply:

```
In one line: what is this session in charge of in this project — its standing responsibility, not its latest step?
On a second line, name the session after that responsibility: `name: ` followed by 2 to 4 lowercase English words joined by hyphens, specific enough that another session reading only the name knows what this one owns. Leave out the project's name, which is shown beside it.[ Its current name is `<current>`: keep it unless it no longer describes the standing responsibility well, because the responsibility changed or became clearer than when the name was chosen.][ Taken by other sessions: <name>, <name>, ….]
Answer with the two lines only.
```

A member that is not eligible gets today's prompt (`DERIVE_PROMPT`), unchanged.

- A member's **proposed names** are the `name`s of every `in-charge` event with source `derived` that carries one, across the member's session and the sessions it continues (its lineage, as `charge_of` reads them); its **latest proposal** is the newest of them. `<current>` is the engine name the session holds when that is one of its proposed names, else its latest proposal. The latest proposal is passed whether or not the engine has applied it yet. Either way the name stays the same from one derive to the next. Without that instruction the name would be rewritten every 6 hours, because the line is: one desk-orchestrating session's derived lines, 2026-10-19/20, said the same thing seven ways ("Orchestrates the MAWS desk …", "Orchestrating the sminos desk …").
- The taken list is the aliases of the project's other non-retired members, plus the engine names of this machine's other running sessions. The engine refuses a name a live session on the same machine holds, and gives a suffixed name instead (§3). sminos refuses an alias that shadows another current member of the project (`shadowing`). Naming the taken names keeps the fork from choosing either.
- **Format: 2–4 words, lowercase ASCII, hyphen-joined, no project name.** The owner chose 2–4 words and descriptive over the 2–3 first proposed (2026-10-20). Lowercase ASCII kebab is what can follow `@` in a message without quoting. The project is already shown beside the alias everywhere a name appears, and `@<project>/<alias>` qualifies it. *Alternative:* free form, Korean allowed. That lost because a name with spaces or Hangul cannot be typed as an `@` tag.

**Parsing the answer.** Take the first mark span's text when the answer has marks (`extract_marks`, as `answer_line` does; the fork runs under the session's output style), else the whole text. The **line** is the first non-empty line that does not start with `name:` (case-insensitive), cut to `DERIVE_LINE_MAX`, which is today's `answer_line` with one skip added. The **name** is the rest of the first line that starts with `name:`. It is lowercased, and surrounding backticks, quotes and one trailing period are trimmed. It is kept only if it matches `^[a-z0-9]+(?:-[a-z0-9]+){1,3}$`, is at most 48 characters, and is not in the taken list. Otherwise this derive records the line with no name and prints why (`no name: <reason>`). A missing or invalid name never fails the derive, because the line is still worth recording.

**Recording.** The `in-charge` event gains an optional field `name` (Interfaces). It is written on a derived event when the member is eligible and the answer's name was kept. `sminos derive` prints `<alias>: <line>` as today, and then, when a name was kept, `<alias>: name <name>` on a second line.

**Cadence: derive's own, with an earlier first derive.** The name arrives with the derived line, from the same fork, so the line and the name share one threshold and one cadence. The owner first chose derive's cadence as it stood, 10 prompts from the human and the daemon's hourly `derive --all` (2026-10-20). They then found that too slow for the first name and changed two things (2026-10-21):
- **Threshold: 10 tool calls.** Derive's eligibility counts the `tool_use` blocks in the session's own assistant records in its main conversation (not sidechain or subagent records), at least 10, in place of `human_prompts` ≥ 10. It applies to the line as well. A member below it is refused with the count named (`not derived — 9 tool calls, needs 10`, in the existing refusal's form).
- **The first derive within about 5 minutes.** A member with no derived line yet is derived within about 5 minutes of reaching the threshold. Later derives keep the 6-hour spacing. M4 chooses the mechanism from a measurement: either the daemon's `derive --all` runs every 5 minutes, since a member derive refuses costs a transcript count and no fork, or, if a full run is too heavy on this machine's real project set for that interval, a cheaper check runs every 5 minutes over only the members with no line yet.

Because a first name may now be chosen from 10 tool calls, before the responsibility is clear, the keep-instruction in the prompt does not lock it in. It keeps the name unless the name no longer describes the responsibility well, because the responsibility changed or became clearer. A short session keeps its generated name. A member whose line was `set` (`sminos charge`, `spawn --brief`) is not derived and so is not named. Today that is almost only seats, which are not named anyway (§2).

## 2. Which names sminos may replace

**Eligibility is read from the session's running engine record, not from the member row.** The member row cannot be trusted for this. `held_alias` keeps the alias a session already holds, and that alias's source, whenever the engine name is one it treats as generated (`collision` among them) or would shadow another member. So an owner's `/rename` that collided, or that shadows another member's alias, still lists as the old `derived` alias (the design review ran the function: both return `('project-ab', 'derived')`). Eligibility judged from the row would overwrite those names. Derive reads the record `_on_sight` chooses, as it reads `before` (§3):

| the running engine record | named? |
|---|---|
| `nameSource` `derived` (the engine's `<dir>-<hex>`) | yes |
| `nameSource` `auto` (the engine promoted a title: SDK, MAWS, `--bg`, bridge sessions) | yes |
| `name` is one of the member's proposed names (§1), whatever its `nameSource` (`user`, as every name sminos applies reads, §3) | yes; the name is passed to the fork to keep |
| any other: `user` (the owner's `/rename` or `--name`, a name sminos never proposed), `peer` (a host named it), `collision`, a `hook` name that is not a proposal | no: the line only |
| no running record (the session is stopped) | no: the line only |
| the member is a seat | no |

`collision` is excluded because the engine also records it for the owner's own `/rename` that collided (`QTn` in the engine: a `user` request that yields is recorded `collision`). Treating it as generated would overwrite a name the owner chose.

**sminos knows its own names by its log, and only where naming needs it.** A name sminos applies reads `user`, as the engine registers every `/rename` (§3), and nothing relabels it. The proposed-names set (§1) is what tells sminos's names from the owner's, and only two places ask: the table above (derive's eligibility, judged before the fork) and `name-due` (§3). The test is "one of", not "the latest": a session that holds an applied name A while a newer proposal B waits, or was refused because B was taken, stays eligible. Nothing else needs to tell the two apart, because derive treats an owner's name as it treats any other (design change of 2026-10-21, Decision Log):
- **Derive runs for owner-named members too.** `derive_refusal` no longer refuses a member its human named. A `set` line still stops derive, as do the prompt threshold and the six-hour spacing. An owner-named member that is not eligible gets today's prompt, so its line is derived and its name is left alone.
- **A derived line outranks the name.** `charge_of` reads its sources in the order `set` > `derived` > the owner's name > the title. A name is the member's line only until its first derive.
If the owner `/rename`s a session to a name sminos never proposed, the member is no longer eligible: derive keeps deriving its line, and its name is never replaced. An owner who renames it to one of sminos's proposed names is indistinguishable from sminos, and no harm follows from that.

## 3. Applying a name: the engine's `/rename`, between turns

**The mod runs the engine's own `/rename`: `$.command.run({ command: 'rename', args: name })`.** Measured on engine 2.1.305 (2026-10-21, a scratch plugin whose `turn.complete` hook called it 3 s after the turn ended): it renamed an idle session with no prompt. The registry read `{"name": …, "nameSource": "user"}`. The transcript got `custom-title` and `agent-name` records, the `/rename` command row with its `Session renamed to: …` output, and a meta user row `The user named this session "<name>". …`, which `$.command.run` also returns as `context`. That row is how the model learns of the rename, so the mod adds no line of its own. The engine applies its collision rule as for any `/rename` the owner types: a name a live session on this machine holds yields a suffixed one recorded `collision` (Surprises). Title promotion replaces only `derived` and `auto` names, so it does not overwrite it. *Alternatives:*
- `sessionTitle` from a `classic.UserPromptSubmit` hook, the first build (M2). The engine treats it as a rename too (2.1.304 source, `aMt` → `zdt(title, "hook")`), registered `hook`, but only at the session's next prompt. Its one advantage was a source label distinct from the owner's, and sminos stopped trusting that label: a resume restores it as `user`. The owner chose the command for its simplicity (2026-10-21).
- `sessionTitle` from `SessionStart` changes only the session's title. At startup and at resume the engine name stayed what it was (spike).

**Sessions that are not interactive.** The sessions that gain most from a name are the ones the engine named by title promotion (`auto`): `--bg` jobs and SDK sessions as MAWS launches them (`sdk-ts` entrypoint, streaming input, several prompts). A plugin's slash command may be refused there (reload.tsx registers only in interactive sessions for that reason). M5 measured both kinds on engine 2.1.306 (Surprises): `$.command.run('rename')` renames each of them while it is between turns, registered `user`, and starts no model turn. So the mod has one path, and its timer runs in every session, interactive or not. In an SDK session the command leaves no meta "named" row and returns no `context`, but the model reads the command's own rows and knows its new name (measured). A `sessionTitle` fallback was planned for any kind that refused the command. None does, so it was not built. A one-shot `-p` run was not measured: it ends before any derive could reach it.

**The name the proposal replaces is read before the fork.** The fork can run for up to two minutes (`SMINOS_DERIVE_TIMEOUT`, 120 s). If the owner `/rename`s the session in that time and derive read the engine name only afterwards, the owner's new name would become the `from` the mod checks against, and `name-due` would overwrite it at the next prompt. So derive reads the member's running engine record (the one `_on_sight` reads) and decides eligibility before it starts the fork, and keeps that record's name as `before`. When the fork returns, it reads the record again. If the record's name is no longer `before`, or the session no longer runs in that process, the naming part of this derive is discarded: the line is recorded without a `name`, and `no name: renamed during derive` is printed. The next derive judges the member afresh: a `user` name sminos never proposed is not eligible there, and gets the line only.

**Handing the name to the session.** Derive runs in the daemon or a terminal, never in the session, so the name crosses through a file. After recording an event with a name:
- `before` already equals the name → remove any pending file for the session;
- it differs → write the pending file (Interfaces) with `from` set to `before`;
- no running record when derive started (the session is stopped) → nothing. A resume draws a new engine name anyway. The next derive after the session runs again writes the file.

`derive --all` also removes pending files older than 7 days. A session that went that long without being renamed (stopped, or never between turns with the mod loaded) gets a fresh file from its next derive.

**The mod checks before it applies; the CLI owns the check.** `sminos/hooks/mods/name.tsx`, registered in `sminos/hooks/mods/register.tsx`, does nothing in an internal fork (`SMNS_INTERNAL`). Otherwise, from the session's start:
1. On a timer (as `hooks/mods/reload.tsx` in doperpowers polls `installed_plugins.json`, every 15 s), read the session's pending file (`$.fs`, under the sminos home: `SMINOS_HOME`, else `DAEMON_HOME`, else `$HOME/.claude/sminos`, as `root()` resolves it). If there is none, or its text is the text this module last handled, do nothing. This read is the only standing cost.
2. While a main-conversation turn runs, or an ask's dialog is up (the sminos ask's snapshot in `$.state`, `isDialogUp`), wait for a later tick. These are reload.tsx's conditions: a slash command run during a turn waits for the turn's end, and a dialog's answer must not be taken by the command.
3. Otherwise remember the file's text as handled and run `sminos name-due --session <id>` (`$.process.run`, bounded as `address.tsx` bounds `who`). Whatever the attempt's outcome (a name, nothing, a non-zero exit, a throw or a timeout), it is the one attempt for that text, so the check runs once per pending name and not once per tick. A rename that misses through a transient failure gets another chance when the next derive rewrites the file. The one exception: if a main turn started while `name-due` ran, its answer is stale, so it is dropped and the text is left unhandled for the next idle tick.
4. If it printed a name, run `$.command.run({ command: 'rename', args: name })`. A refusal or a throw goes to the debug log, and the memo stands.

`name-due` prints the name only when the running engine record's name still equals the file's `from` and differs from the file's `name`, the record is still eligible (§2's table, the check derive makes before its fork), and the name is still free. That catches every case where something moved between derive and the rename:
- the owner `/rename`d it, which is the race this check exists for, including a rename to the very name it had;
- it was put into a seat;
- the name is already applied;
- a resume put the session in a new process under a new engine name. **Free** means two things: no other non-retired member of the session's project holds it as its alias, on any machine (else `shadowing` would keep the old alias while the engine showed the new name); and no other running session on this machine holds it as its engine name (else the engine would yield a suffixed `collision` name, which is not sminos's and so not eligible again). A proposal that is no longer free is not due. The file stays, the mod's memo stops it from asking again, and the next derive is told the name is taken and proposes another. What is left is the window between `name-due` answering and the engine applying, a fraction of a second. A collision in that window leaves the session under the engine's suffixed name, which is still descriptive. That is accepted, not handled. The check reads the engine record, not the session's custom title. A session named by title promotion (`auto`) has no custom title in its transcript (7 of the 8 such sessions on the MacBook; the eighth was later `/rename`d), so comparing against it could not tell "unchanged" from "renamed" for those. *Alternative:* the mod scans `~/.claude/sessions/*.json` itself. That lost because it re-implements in TypeScript the choice of the running record among a crashed process's leftovers, which `_on_sight`/`peer_running` already make. A process spawn once per rename is cheap.

Once the engine applies the name, nothing more is needed. `held_alias` takes a non-generated engine name as the alias. `publish_renames` (the daemon, every tick) appends `renamed` with source `user`, as for any `/rename`. `sminos who --session` (the commit address) picks it up within its minute. The guide (`smns-guide.sh`) shows it at the next compaction or resume.

## 4. Former aliases still reach the member

A rename breaks every `@alias` a peer learned. Today a name matches only a member's current alias, short, or session id (`match_members` and `find_target`'s `matches` in `sminos.py`). After this change, each lookup that matches by alias falls back, **in the same scope and only when no member's current alias matches**, to members that formerly held that alias. A former alias is any alias of the member's own `joined`/`renamed` events and its lineage's, other than its current alias and its short.

- **Precedence:** a current alias always wins. A former alias is only a fallback, so a session that now goes by a name, or later takes it, owns it. If several members formerly held it (generated names do repeat over time, as `doperpowers-19` did), the one that held it most recently wins: the latest ts among the `joined`/`renamed` events carrying it. Equal ts is refused as ambiguous, named as today.
- **Scope:** the scope rules do not change. A bare `@old` looks in the sender's project. `@old#short` looks across the org, and the short still has to match. `@<project>/old` looks in that project. Retired members still answer to nothing.
- **The note:** whenever a target was found by a former alias, the command prints `note: @<old> is now <label>` on stderr through the CLI's `note`, a sibling of `warn`, where `<label>` is the member as `candidate_labels` names it (`@alias#short`, or project-qualified across projects). This holds for `say` (once per tag) and for every member verb that goes through `find_target` (`steer`, `watch`, `charge <member>`, …). Stderr leaves stdout contracts (`--json`) unchanged, and a calling model reads both. The recorded recipient is the member's current alias, as for any tag.

This applies to any rename, including the owner's `/rename`, not only to charge names: the problem it fixes is the rename, whoever made it. The owner asked for it on 2026-10-20 ("old aliases are still found and messaged, and a note says the name changed").

## Acceptance

Each item is behavior someone can check. Items 1–5 and 7–9 run in `sminos/tests/run-sminos-tests.sh` (the `sminos` gate) against the stub `claude` its derive tests already use (`STUB_FORK_RESULT`). Item 6 runs in the mods suite and the live check.

1. **A generated-name member gets a charge name.** For a `derived`-named member whose model has made ≥10 tool calls, `sminos derive <alias>` with the fork answering `Owns the desk's uplink.\nname: desk-uplink-owner` prints `<alias>: Owns the desk's uplink.` and `<alias>: name desk-uplink-owner`. It appends an `in-charge` event `{source: derived, text: …, name: desk-uplink-owner}`, and writes `$SMINOS_HOME/names/<session>.json` with `name: desk-uplink-owner` and `from` set to the engine record's name. The fork's prompt carries the naming part and the taken list.
2. **Names it must not touch.** For members whose running engine record is named `user` (a name sminos never proposed for it), `peer`, `collision` or a foreign `hook` name, for a stopped member, and for a seat with no `set` line, derive runs (an owner-named member is no longer refused), the fork's prompt is today's `DERIVE_PROMPT` verbatim, the event carries no `name`, and no pending file is written. The same holds for a member that joined under a generated alias and was then `/rename`d by its owner to a name that collided (engine record `collision`) or that shadows another member's alias (engine record `user`). Its member row still lists the old `derived` alias, and it must still not be named. These two cases are built by renaming an already-joined member, not by fixtures whose row already says `collision` or `user`. If the stub fork changes the member's engine record to a `user` name while it runs, the line is recorded with no `name`, `no name: renamed during derive` is printed, and `name-due` prints nothing afterwards.
3. **Stability.** With a proposed name already in the log, the prompt says `Its current name is \`desk-uplink-owner\``. If the fork answers the same name and the engine name already equals it, no pending file remains. If it answers a different valid name, a pending file with the new name and `from: desk-uplink-owner` is written.
4. **Bad names are dropped, the line kept.** Answers naming `Desk Uplink`, `one-two-three-four-five`, a 60-character name, a taken alias, or no `name:` line all record the line with no `name`, print `no name: <reason>`, and write no pending file.
5. **A name sminos applied stays sminos's to change; an owner's name is never replaced.** No member row and no log event carries a `charge` source. A member whose engine record says `nameSource: "user"` and whose name is one of its proposed names lists `name_source: "user"`. Its in-charge line is the derived one (`set` > `derived` > name > title). Its next derive runs with the naming prompt and `Its current name is …`. An owner-named member with no derived line has its name as its line, and after its first derive the derived line. When the record's name changes to one sminos never proposed (the owner's `/rename`), derive still runs, but with today's prompt: no `name`, no pending file. The sequence resume → a derive proposing a different name B → B taken by another session before it applies (`name-due` prints nothing) leaves the session eligible under its applied name, and the next derive runs, is told B is taken, and its new proposal applies.
6. **The mod applies it between turns, once.** In the mods suite (`sminos/tests/mods/name.test.ts`):
   - With a pending file and `name-due` printing a name, an idle tick runs `$.command.run({ command: 'rename', args: <name> })` once. A later tick with the same file text runs no second `name-due`.
   - With no file, the CLI is never run.
   - While a main turn runs or an ask's dialog is up, nothing runs until a tick finds the session idle.
   - A turn that starts while `name-due` runs drops that answer and leaves the text for the next idle tick.
   - Under `SMNS_INTERNAL` nothing is read.

   Live (`sminos/tests/mods/live-name-check.py`, by hand, a few haiku turns):
   - An idle interactive session with the sminos plugin and a pending file whose `from` is its engine name is renamed with no prompt. Its engine record shows the name with `nameSource: "user"`, and its transcript has a `custom-title` record and the engine's meta row naming it.
   - A session `/rename`d before the tick keeps its own name.
   - The rename starts no model turn.
   - A `--bg` job and an SDK session (as MAWS launches one) are renamed between turns the same way, registered `user`.
7. **`name-due`.** It prints the name when the running record's name equals `from`, differs from `name`, and the record is eligible. It prints nothing in each of these cases:
   - the record's name equals `name`, or is neither name;
   - there is no pending file, or no record of the session runs;
   - the record is no longer eligible: the owner `/rename`d it to the very name it had (now `user`, not a proposal), or the session was put into a seat;
   - after the file was written, the name came to be held by another member of the project (a remote member, through its log events) or by another running session on this machine (its engine record).
8. **Former aliases.** After a member's alias moves from `oldname` to `newname` (a `renamed` event), `sminos say "@oldname hi"` from another member of the project records the message to `newname`, delivers it, and prints `note: @oldname is now @newname#<short>` on stderr. The same holds for `@oldname#<short>` from another project and for `sminos steer oldname …` (`find_target`). If another current member's alias is `oldname`, that member gets the message and no note is printed. If two members held `oldname`, the more recent holder gets it. A retired member's former alias reaches nothing. A seat's lifecycle verb that reaches its occupant through a former alias is bound to that occupant's session, so it never acts on a replacement that filled the seat since the lookup.
9. **Derive's threshold and first-derive latency.**
   - A member whose main conversation holds 9 `tool_use` blocks in its own assistant records is refused, with the count named. One with 10 is derived.
   - Tool calls in sidechain or subagent records do not count. Human prompts no longer matter.
   - A member with no derived line that reaches the threshold is derived by the daemon within about 5 minutes; acceptance 9 drives the daemon's tick with the interval shortened, as the existing daemon derive tests do.
   - A member that already has a derived line is derived again only after 6 hours.

## Execution

**Binding on every milestone.** The sminos plugin only: nothing in doperpowers' own `hooks/mods/` changes. The CLI stays one Python file plus its siblings under `sminos/skills/sminos/scripts/`, standard library only. Mods are TypeScript under `sminos/hooks/mods/`, typechecked by `tests/mods/typecheck.sh` (the `mods-types` gate; it needs the engine's declarations laid in `.claude-plugin/types/`, `tests/mods/typecheck.sh --lay`, or copied from the main checkout's gitignored `.claude-plugin/types/`). Verify commits with `ci-gate` from the worktree, not by running the gates locally; one focused test file while iterating is fine. The engine facts this design rests on (§3 and Surprises) are pinned by the live check in M2, not by unit tests: a unit test cannot see the engine.

### M1 — derive proposes a charge name; sminos knows its own names

*Built as written. M4 removes its `charge` source and relabel after the owner's design change of 2026-10-21.*

**At its end:** derive builds the naming prompt for eligible members, parses and validates the name, records it on the `in-charge` event, and writes or removes the pending file. Member rows report `charge` for sminos's own names. `charge_of` and `derive_refusal` stop reading those as the owner's. `sminos name-due` answers. `derive --all` sweeps stale pending files.

**Touches:** `sminos/skills/sminos/scripts/sminos.py` (`DERIVE_PROMPT` and its eligible variant, `derive_line`/`answer_line`, `cmd_derive`, `derive_refusal`, `charge_of`, `_member`, a new `name-due` verb in the parser), `sminos/skills/sminos/scripts/sminos_daemon.py` only if `publish_renames` needs a change to publish `charge` (it should not: it publishes `m.name_source`), and `sminos/tests/run-sminos-tests.sh` (the in-charge section and its stub fork).

**Interfaces:** produces the `in-charge` `name` field, the pending file, `name-due`, and the `charge` name source (Interfaces and Dependencies).

**Decisions:** eligibility is §2's table, read from the session's running engine record (never from the member row, which `held_alias` can leave stale). The taken list and `<current>` are as in §1. Parsing and validation are as in §1. The pending-file rules are as in §3. The relabel lives where the member row is built, so `list`, `find`, the daemon and the desk all read one answer. `name-due` exits 0 in every case except a usage error, because the mod reads its stdout and must never fail a prompt. The stub fork already takes `STUB_FORK_RESULT`; the tests also need to read the prompt it was given (log it in the stub, as `calls.log` logs argv), and acceptance 2's race needs the stub to rewrite the member's engine record while it runs (an environment variable naming the record and the name to write, beside the stub's existing `STUB_FORK_*` switches).

**Does not touch:** the mod, name resolution (`match_members`, `find_target`), docs, version.

**Proves:** acceptance 1–5 and 7.

### M2 — the name mod applies a pending name

*Built as written, then reworked by M5 after the owner's design change of 2026-10-21. This entry records what M2 built.*

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

### M4 — derive for every member, from 10 tool calls, soon; no `charge` source

**At its end:**
- `derive_refusal` no longer refuses a member its human named. A `set` line, the threshold and the six-hour spacing still stop derive.
- The threshold is 10 tool calls by the session's model in its main conversation, not 10 human prompts (§1). Below it, the refusal names the count.
- A member with no derived line is derived within about 5 minutes of reaching the threshold, through the mechanism §1 leaves to a measurement. Before choosing, measure what a `derive --all` that refuses everyone costs on this machine's real project set: wall time and CPU, with the per-member transcript count separated out. Measure without forking any session and without writing to the real logs, for example by timing the eligibility pass of `sminos.py`'s own functions against the real `~/.claude/sminos`, read-only. Record the numbers in the report.
- The keep-instruction in the naming prompt reads as §1's block now has it.
- `charge_of` reads `set` > `derived` > the owner's name > the title.
- The `charge` name source and every relabel that produced it are gone: `own_name_source` or whatever M1 and its fix named it, the relabel in `_member`, the one in `join_on_sight`, and the demotion of a logged `charge`. A name sminos applied reads `user`, as the engine says.
- Naming eligibility is unchanged (§2's table, the pre-fork snapshot, `name-due`'s checks, including the eligibility recheck the branch review added).

**Touches:**
- `sminos/skills/sminos/scripts/sminos.py`.
- `sminos/skills/sminos/scripts/sminos_daemon.py`: the derive cadence, and anything there that names `charge`.
- `sminos/tests/run-sminos-tests.sh`: acceptance 2 and 5 as revised. Remove the tests that pinned `charge`, including the two-machine ones, or turn them into tests of the new order.
- `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`. In §5, the source order becomes set > derived > name > title. "`derive` runs only for a local member with no source 1–2 line, at least 10 human prompts" becomes "with no `set` line, at least 10 tool calls by its model", and the daemon's derive cadence in §5 and §8 becomes what M4 chose. In the Decision Log's `charge_source` and `derive` notes, owner-named members are no longer refused. In the event table, the `joined` `name_source` values carry no `charge`, if M1 added it.
- `CLAUDE.md`'s sminos row, if it says `charge`.

**Interfaces:** removes the `charge` name source. Everything else M1 produced stands.

**Decisions:** a member that was refused before and is not eligible now gets today's `DERIVE_PROMPT`, so its owner's name is never touched. Nothing migrates log events that already say `charge`. They exist only on this unmerged branch's test fixtures and on any machine that ran it, and a reader treats an unknown source as it treats `user`. If the code needs a rule for that, state it in the report.

**Does not touch:** the mod (M5), name resolution.

**Proves:** acceptance 1–5, 7 and 9 as revised, `ci-gate --gates sminos,sminos-suites`.

### M5 — the mod renames through the engine's `/rename`, between turns

**At its end:** a running session with a due pending name is renamed with `$.command.run({ command: 'rename', args })` at the first timer tick that finds it idle, once per pending file text. Where the measurement requires it, a `--bg` or SDK session is renamed through `sessionTitle` at its next `UserPromptSubmit` (§3).

**Steps, in order:**
1. **Measure first.** Build a scratch plugin outside the repository, as the spike did under `/tmp/spike-hookname/`. With it, run the two kinds of session §3 names:
   - a `--bg` job;
   - an SDK-driven session as MAWS launches one: `sdk-ts` entrypoint, streaming input, several prompts. Read how MAWS launches one in `/Users/new/Developer/GitHub/MAWS`.

   For each kind, record whether `$.command.run({ command: 'rename', args })` renames it (registry `name`/`nameSource`, the transcript's records) and whether `sessionTitle` from `classic.UserPromptSubmit` does. Also record, for the interactive case, whether the rename starts a model turn. Record the commands and outputs in the report, and message the controller with the facts before building on them.
2. Rework `sminos/hooks/mods/name.tsx` to §3's steps:
   - the timer, as reload.tsx's watch is built;
   - the idle and dialog conditions, read as reload.tsx reads them (the sminos ask's snapshot is this plugin's own state);
   - the memo, with its one exception;
   - the command;
   - the `sessionTitle` path only for a kind step 1 found refusing the command.

   Drop the `classic.UserPromptSubmit` hook and the mod's own context line, unless the fallback needs the hook. Decide whether the timer registers only in interactive sessions from step 1's facts.
3. `sminos/tests/mods/name.test.ts`: acceptance 6 as revised.
4. `sminos/tests/mods/live-name-check.py` pins the new engine facts:
   - `$.command.run` rename renames an idle session with source `user` and leaves the meta reminder row;
   - an owner's `/rename` made before the tick is kept;
   - step 1's facts for `--bg` and SDK sessions, as far as the check can drive them.

   Drop the `SessionStart`-`sessionTitle` fact and the resume-label fact, which nothing relies on any more.
5. Docs:
   - the `name` section of `sminos/hooks/mods/README.md`;
   - CLAUDE.md's sentence on `name.tsx` (sminos row);
   - `sminos/hooks/hooks.json`'s description;
   - the project-log design §5's paragraph that says the mod applies the name "at the session's next prompt".
6. Version: sminos is already 1.4.0 on this branch. Run `scripts/bump-version.sh --check` against `origin/main`'s sminos version. Bump again (minor) only if main has reached or passed 1.4.0.

**Interfaces:** consumes the pending file and `name-due` (M1, as fixed by the branch review).

**Does not touch:** the CLI, beyond anything step 1 shows the fallback needs.

**Proves:** acceptance 6 as revised. Then the whole list: `ci-gate` (all gates) on the final HEAD, and the live check by hand.

## Concrete Steps

From the worktree root:

    sminos/tests/run-sminos-tests.sh                 # the sminos gate locally, while iterating on M1/M3
    sminos/tests/mods/run.sh                         # the sminos-mods gate, M2
    tests/mods/typecheck.sh                          # mods-types (lay or copy the engine types first)
    ci-gate                                          # every gate on the committed HEAD: GREEN <url>
    python3 sminos/tests/mods/live-name-check.py     # by hand; prints one ok/FAIL line per engine fact and behavior

A manual end-to-end check, after installing the branch's sminos: in a member session with ≥10 prompts, `sminos derive <alias>` prints the line and `name <name>`; `cat ~/.claude/sminos/names/<session>.json` shows it pending; within about 15 s of that session being between turns its footer's name changes; `sminos list` shows the new alias with its derived line; `sminos say "@<old alias> ping"` from another session prints the note.

## Interfaces and Dependencies

**`in-charge` event, field `name`** (optional string): the charge name sminos proposed with this line. It is present only on `source: derived` events of eligible members whose answer's name was kept. Readers that do not know it ignore it, as the log's events allow.

**Pending file** `$SMINOS_HOME/names/<session-uuid>.json`, directory mode 0700, file 0600, written atomically (temporary file and rename):

```json
{"session": "<uuid>", "name": "<charge name>", "from": "<engine name when written>", "line": "<in-charge line>", "ts": "<ISO 8601 UTC>"}
```

**`sminos name-due --session <uuid>`**: stdout is the name to apply (one line) or nothing. It exits 0 except on a usage error. The name is due when the pending file exists and parses, a running engine record of the session exists (as `_on_sight` chooses it), its `name` equals `from`, it differs from `name`, and `name` is still free (§3).

**No new name source.** M1 built a `charge` source; M4 removes it (design change of 2026-10-21). A name sminos applied reads `user`.

**Former-alias note**: stderr, `note: @<old> is now <label>`, once per resolution by a former alias (§4).

**Engine dependency**: Claude Code ≥ 2.1.305. `$.command.run({ command: 'rename', args })` renames a session that is between turns, with source `user` and without starting a turn, in interactive, `--bg` and SDK sessions alike. Pinned by `live-name-check.py`.

## Surprises & Discoveries

- Observation: `sessionTitle` from `UserPromptSubmit` renames the session fully; from `SessionStart` it sets only the title. Evidence: spike, engine 2.1.305, a `classic.SessionStart` hook returning `spike-start-name` and a `classic.UserPromptSubmit` hook returning `spike-prompt-name-ok`. After startup the registry read `{"name": "work-0b", "nameSource": "derived"}` while the next `UserPromptSubmit` saw `session_title: "spike-start-name"`. After the prompt it read `{"name": "spike-prompt-name-ok", "nameSource": "hook"}`, with `custom-title` and `agent-name` records written. After a resume, `SessionStart`'s title wrote a `custom-title` record and changed the footer, but the registry name stayed.
- Observation: a resume restores a hook-set name as `user`. Evidence: same spike, after `claude --resume`: `{"name": "spike-prompt-name-ok", "nameSource": "user"}`. The transcript's `custom-title` records carry no source, and the engine's restore path defaults to `user` (`JEe(R.agentName, …)` → `Wz(name, …, "user")`). This is why §2 identifies sminos's names from its log.
- Observation: sessions named by title promotion have no `custom-title` record. Evidence: of the 8 `auto`-named members on the MacBook, 7 have no `custom-title` record (5 to 2 674 `ai-title` records each); the eighth's one custom title is a later `/rename` (`sitting-fork`). This is why `name-due` compares engine names, not `session_title`.
- Observation: the engine records a collided `/rename` of the owner's as `collision`. Evidence: engine 2.1.304 `QTn`: `n === "user"` skips the pre-check, and a yield from `Zrn(e, "rename")` returns `recordSource: "collision"`. This is why `collision` is not eligible.

- Observation: `$.command.run({ command: 'rename', args })` renames an idle interactive session with no prompt, registered `user`. Evidence: the dispatching session's scratch plugin on engine 2.1.305, 2026-10-21. A `turn.complete` hook called it 3 s after the turn. The registry read `{"name": "spike-cmd-name", "nameSource": "user"}`. The transcript got `custom-title` and `agent-name` records, the `/rename` command row and its `Session renamed to: …` output, and a meta user row `The user named this session "spike-cmd-name". …`, which the call also returns as `context`.
- Observation: every kind of session that can be derived takes the command. Evidence: M5, engine 2.1.306, a scratch plugin whose 2 s `$.clock.every` ran `$.command.run('rename')` while the session was between turns.
  - Interactive (tmux): `work-50 (derived)` → `m5-cmd-interactive (user)`.
  - `--bg` job (`session.start` reads `isInteractive: true`, surface `terminal`): `alpha reply test (auto)` → `m5-cmd-bg (user)`.
  - SDK session launched as MAWS does (`claude -p --input-format stream-json …`, `CLAUDE_CODE_ENTRYPOINT=sdk-ts`, `isInteractive: false`): `work-5b (derived)` → `m5-cmd-sdk (user)`.

  None of them started a model turn. `sessionTitle` from `UserPromptSubmit` also renamed all three, registered `hook`, at their next prompt.
- Observation: in an SDK session `/rename` leaves no meta "The user named this session" row, and `$.command.run` returns `{text: "Session renamed to: …"}` with no `context`. The caveat and `<command-name>/rename` rows are written as plain user rows. Evidence: M5. Asked afterwards whether it had been given a name, haiku answered with the new name, so the model learns it from those rows.
- Observation: `name-due` reconciles the project (`members(project)`) before it answers, so it is not instant. Evidence: M1 executor. The mod's bound on it (M2) must allow for that.

- Observation: derive's forks fail, and almost always by timing out. Evidence: `~/.claude/sminos/daemon.log` on the MacBook, 2026-10-17 to 10-21: 98 `derive --all` runs and 28 fork failures, 27 of them `the fork timed out after 120s` and one `the fork failed (exit 0)`, at most 3 per member (`maws-fe` and `doperpowers-74` 3 each). At the hourly cadence that was at most one fork of up to 2 minutes per member per hour; at M4's five minutes a member whose fork keeps timing out would cost 12, so `--all` holds a member whose fork failed out for an hour (M4). Why those forks reach 120 s (a large context rebuilding its prompt cache, say) is not established here and is a separate question.
- Observation: a `derive --all` that refuses everyone costs about a second. Evidence: M4, the MacBook's real project set (39 projects, 48 local members) on a copy of `~/.claude/sminos`, four runs: 0.56–1.07 s wall, about 0.3–0.5 s CPU without the old prompt counter; reconciling every project 0.12–0.33 s; the tool-call count 0.03–0.09 s, reading 19.7 MB of 1.69 GB of transcripts, since it stops at the tenth call.
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
- Decision: branch review (reviewer-medium), three P2 findings.
  - (a) `name-due` rechecks eligibility against the running record, so an owner `/rename` to the very name it had, or seating the session, stops the rename.
  - (c) A seat lifecycle verb that reaches its occupant through a former alias is bound to that occupant's session.
  - (b) Not built: the loss of `charge` provenance on `sminos join <other-project>`.

  Rationale: (a) and (c) protect the owner's name and the addressed session, the two risks the design names. (b) became moot with the `charge` source (next entry). After a join, the proposals are not in the destination's log, so the session stops being named there, which is the conservative outcome.
  Date/Author: 2026-10-21, doperpowers-c4 (controller), with the dispatching session.
- Decision: the owner's design change.
  - The mod applies a name with the engine's `/rename` (`$.command.run`) at the first timer tick that finds the session between turns, not with `sessionTitle` at its next prompt.
  - Derive runs for owner-named members too, and `charge_of` reads `set` > `derived` > name > title.
  - The `charge` source and its relabel are removed, so a name sminos applied reads `user`.
  - Naming eligibility is unchanged: the running engine record (`derived`/`auto`, or a name among the member's proposals), the pre-fork snapshot, and `name-due`'s checks.

  Rationale: the owner chose this for simplicity. A name applies without waiting for a prompt. The engine tells the model itself. The machinery that kept sminos's names apart from the owner's (the relabel, its cross-machine publication, its demotion and join paths) existed only to keep derive running and the name out of the line, and both are now true for every member. Rejected: the `UserPromptSubmit` `sessionTitle` path, whose only advantage was a source label (`hook`) that sminos had already stopped trusting, since a resume restores it as `user`. It stays only as the fallback for a kind of non-interactive session where the command is measured refused (§3).
  Date/Author: 2026-10-21, the owner, through the dispatching session.
- Decision: the owner's second change. Derive's threshold is 10 tool calls by the session's model in its main conversation, instead of 10 human prompts. A member's first derive comes within about 5 minutes of reaching the threshold. The keep-instruction keeps a name only while it still describes the responsibility well.

  Rationale: 10 prompts from the human, then up to an hour for the daemon, was too slow for the first name. Most sessions do their work in tool calls rather than prompts, so tool calls measure how far a session has got. The line moves with the name because both come from one fork. An earlier name is chosen on less evidence, so the prompt must let it improve once the responsibility is clearer, rather than freezing the first guess. The interval for later derives stays 6 hours. Rejected: a lower prompt threshold, which still waits on the human.
  Date/Author: 2026-10-21, the owner, through the dispatching session.
- Decision: the daemon runs `derive --all` every 5 minutes (`DERIVE_EVERY = 300`), because a run that refuses everyone measured about a second (Surprises), so no separate check for line-less members was needed. `--all` holds a member whose fork failed out for an hour (a stamp under `$SMINOS_HOME/derive-failed/`, cleared by a success and swept after an hour). An explicit `sminos derive <member>` ignores the stamp. Without the hold, a fork that keeps timing out would cost 12 two-minute forks an hour instead of 1. M4's task review then found that the interval bounds when a sweep starts, not when a member's first derive happens: `--all` forks its targets one after another, each up to 120 s, so refreshes ahead of a first-timer delay it by minutes. Two changes fix that (controller, 2026-10-21). Within `--all`, members with no derived line go before refreshes. The daemon's run also forks at most a small fixed number of refreshes, oldest line first, and leaves the rest to the next run. A person's `sminos derive --all` still covers everyone.

  Rationale: M4's measurement, its task review, and the controller's fix of the latency it found.
  Date/Author: 2026-10-21, M4 executor and doperpowers-c4 (controller).
- Decision: derive refuses a re-derive when the session's transcript has not been modified since its latest derived line ("no activity since its last line, <age> ago"). It compares the transcript's mtime with that event's ts. A first derive is unchanged.

  Rationale: the owner's usage concern, 2026-10-21. Without the check, a stopped member that is never retired is re-forked every 6 hours forever. A fork of an idle session rebuilds its prompt cache, the most expensive kind of call, and its answer cannot change, since the conversation is the same.
  Date/Author: 2026-10-21, the owner, through the dispatching session.

## Outcomes & Retrospective

Pending — written at finish.
