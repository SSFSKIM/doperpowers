# sminos — one name, one state word, one delivery verb

A seat (a named position in a sminos group that a Claude Code session
fills; `skills/sminos/SKILL.md`) is addressed today by five identifiers —
its alias, `group/alias`, a stored harness address (`addr`), its seat id,
and its session's short id — and `sminos list` describes it in eight
columns, two of which (`STATUS`, the recorded turn state, and `LIVE`, the
harness-derived one) name the same fact in different words and disagree on
most rows of the real fleet (`working stopped`, `idle gone`). Two verbs
deliver a message to a seat, `send` (live only) and `wake` (live or
stopped). After this change a seat has **one name**, its alias, which is
also the name the harness knows it by; **one state word** out of seven, read
live from the same file the harness's own ListAgents reads; and **one
delivery verb**, `send`, which reaches a live seat over its socket and
resumes a stopped one. The socket is the machine's route to a seat and is
never typed or shown.

The harness settled this model first: every session writes
`~/.claude/sessions/<pid>.json` with one `name`, a `messagingSocketPath`,
and a `status` (`busy`, `idle`, `waiting`, `shell`), and its ListAgents tool
prints one row per session, `name [ref] · kind · status`, using the ref
only when two rows share a name. Sminos already delivers on that socket.
This spec makes its surface say no more than the harness's does.

To see it working: from a terminal in this repository,
`skills/sminos/scripts/sminos spawn lead "…" --group one` starts a seat;
`sminos list` prints

    one
      lead   busy      (the task's first line, or the seat's own status line)

and `idle` once the turn ends; `sminos send lead "carry on"` starts its
next turn; `sminos spawn a "…" --group two` while `one/a` is live succeeds,
and `sminos send a "x"` answers `ambiguous seat 'a' matches: one/a, two/a`
where `sminos send two/a "x"` delivers.

## Progress

- [x] (2026-09-29, reviewed clean) M1 — one state word: `state()` from the session record and the seat record; `list` grouped, `STATE` column, `--state`; `--json` carries `state`; chart and TUI vocabulary, glyphs, and hide rule; tests.
- [x] (2026-09-29, reviewed clean) M1 follow-up — `gone` reinstated as a seventh word (Decision Log, 2026-09-29): `state()` reads the harness listing for a seat with no live peer; `REFILLABLE` gains it; glyphs (`✕` gone, a distinct `retired` glyph); the hide rule becomes retired-or-gone; tests.
- [x] (2026-09-30, reviewed clean with M3's fix wave, 979b51e4) M1 follow-up, predicate revised — `gone` is "no transcript on this machine", not "no harness row"; `claude agents` leaves `state()`; tests.
- [x] (2026-09-29, reviewed clean) M2 — one name: `addr` leaves the record, the flags, the prints, and the locks; uniqueness is per group; a target is an alias, `group/alias`, or a full id; tests.
- [x] (2026-09-30, reviewed clean) M3 — one delivery verb: `send` absorbs `wake` (resume, `--wait`, the lifecycle lock, the frame id); `wake` answers with a pointer; the board's five call sites (Decision Log) and their test stubs move; the TUI's `s` key follows; tests, board suites green.
- [x] (2026-09-30, reviewed clean, 51c6947d + 850e1115) M4, the words — `SKILL.md`, the module docstring (the preamble names nothing that moved); version bump to 7.130.0; acceptance 10's grep empty.
- [x] (2026-09-30, the owning session) M4, the proof — live proof on the real harness: acceptance 1–6, 8 and 11 held as written (Surprises); 7 is a by-hand item and was not run.
- [x] (2026-09-30) M4, the close — whole-branch review at reviewer-medium: no material findings, verdict correct; retrospective written.

## Terms

- **Seat, group, alias, `parent`, `current`, `short`, host, family, reach, the board pipeline, `SMINOS_CLI`** — as `skills/sminos/SKILL.md` and the module docstring of `skills/sminos/scripts/sminos.py` define them. A seat's record is `$SMINOS_HOME/<seat-id>.json`.
- **Session record** — the file `~/.claude/sessions/<pid>.json` the harness writes for every running session: `sessionId`, `name`, `nameSource` (`derived` for a `<cwd-slug>-<2 hex>` name, `user` for a title the person set, absent for a `-n` name), `messagingSocketPath`, `status`, `waitingFor`, `kind`, `cwd`, `pid`, `procStart`. `peer_records()` in `sminos.py` reads them; `peer_live(rec)` is true when the pid is alive, is the same process the record described, and the socket accepts a connection. A **live peer** is a session record for which `peer_live` holds.
- **Recorded status** — the `status` field on a seat's record (`working`, `blocked`, `idle`, `done`, `error`, `retired`, `vacant`), written by the launch and by the `--wait` watcher and reconciled by `sminos sync`. The board's `execute-dispatch.sh`, `review-dispatch.sh`, and `_sweep_api.sh` read it straight from the file under the shared lock. **It does not change in this spec**; it leaves every human-facing surface.
- **State word** — the one word this spec gives a seat, defined below.
- **Frame** — the text written to a session's inbox socket: a bracketed first line naming the sender, then the message.

## The one name

A seat's name is its alias: `[A-Za-z0-9._-]{1,64}`, not `human` or `all`.
It is the harness name of every seat sminos spawns (`claude --bg -n
<alias>`, as today), so the native `SendMessage` reaches the seat by it, a
family member tags it as `@alias`, and the operator types it to `send`,
`attach`, `retire`, `fill`, `status`. A session that joins a group with
`seat add --session` keeps the harness name it already has; sminos never
delivers by name, so nothing needs to know it.

**Uniqueness is per group.** A group holds one seat per alias, as today
(spawning an alias whose seat is filled is refused; a retired, vacant, or
stopped one is re-filled). Two live groups may both hold an `a`. The
refusal that a spawn or `seat add` met when *any* live session on the
machine already answered to the alias (`refuse_live_name`) goes: it
guarded native `SendMessage`, whose names are machine-wide, and the harness
now disambiguates a shared name itself with the `[ref]` its ListAgents
prints. The alternative, keeping the fleet-wide refusal, kept concurrently
live groups from reusing role names (`implementer`, `reviewer`), which is
the common case for families.

**What a command accepts as a seat.** `alias` when exactly one seat has it
(a family seat's ambiguity is first narrowed to its reach, as today);
`group/alias`; a full seat id; a full session id. The last two are for
scripts — the board addresses its workers by seat uuid — and appear in no
human-facing text. Gone: a seat-id prefix, the harness short id, and
short-id or session-id prefixes (`find_seat`'s last two stages). Exact
names are matched before ids, as today, so a one-letter alias is never
lost to an id.

**`addr` goes.** The stored field, its fallback in `load_seat`, the
`--addr` flag of `spawn` and `seat add`, the `ADDR` column, the `addr:` in
`seat add`'s confirmation line, and `--json`'s `addr` key. Records already
on disk keep a stale `addr` key that nothing reads; `migrate` does not
strip it. The record's `name` field, which held the addr, holds the alias.
The one place `addr` did work — as a key in `lock_names`, because a
machine-wide name had to serialize across groups — becomes the seat key:
`lock_seat` and the spawn-time lock take `group/alias`. The `seat add`
refusal that keeps a live occupant from being stranded by a repoint
survives for `--session` alone.

## The one state word

| word | meaning | how it is read |
| --- | --- | --- |
| `retired` | ended on purpose | the seat record's recorded status is `retired` |
| `vacant` | no session to continue | `current` is empty |
| `busy` | its turn is running | a live peer for `current` whose `status` is neither `idle` nor `waiting` (`busy`, `shell`, absent) |
| `idle` | live, between turns | a live peer whose `status` is `idle` |
| `waiting` | live, stopped on a question or a permission | a live peer whose `status` is `waiting` |
| `stopped` | a saved session and no process; `send` resumes it | `current` set, no live peer, and its transcript is on this machine (`transcript_path(current)` finds `~/.claude/projects/*/<session id>.jsonl`) |
| `gone` | a saved session id with nothing here to resume; `send` cannot resume it — `fill` it fresh or `retire` it | `current` set, no live peer, and no transcript for it on this machine |

Read in that order; the first row that holds is the word. A live seat's
word comes from the session record and one socket connect, the same file
the harness's ListAgents reads; a seat with no live peer is `stopped` or
`gone` by whether its transcript is on this machine — what a `claude --bg
--resume <session id>` needs. `claude agents --json --all` is not
consulted to describe a seat (it stays where the `--wait` watcher,
`attach`, and `sync` need a harness row): it is the harness's job list,
not its transcript store, and a session it no longer lists resumes fine
when its transcript is here. Gone from every human surface: `working` and
`done` (the live word says it), `blocked` (the harness's word is
`waiting`, and it says what for), `error`, `failed`, and `unknown` (the
harness can no longer fail to be asked). `FILLED` is `(busy, idle, waiting)`;
`REFILLABLE` is `(vacant, stopped, gone)`; both keep their callers.

`gone` is its own word, not folded into `stopped`, because `stopped` means
"`send` resumes it", and that is false for a seat whose session has no
transcript on this machine — 19 of the real registry's seats when this
was decided, most from other hosts. The operator's moves differ (`send`
for one; `fill` or `retire` for the other), so it carries its name. Two
alternatives were rejected: folding it into `stopped` and letting `send`
learn from the harness's refusal (the first draft), and reading it from
the harness's job listing (the first revision), which called resumable
sessions `gone`; see the Decision Log.

**The now column.** The seat's own status line (`sminos status <seat>
"…"`) when it has one; for a `waiting` seat without one, the session
record's `waitingFor`; otherwise the first line of its latest reply, as
`now_or_reply` does today.

### `list`

    sminos list [group] [--state W] [--json]

Groups are headings, in order of their most recently updated seat; under
each, its seats by `updated`, newest first; a family seat sees its reach,
as today. A row is two spaces, the alias padded to the group's longest (at
most 24 cells), the state word padded to 8, then the now column, opened by
the role in upper case and ` · ` when the seat has a role:

    fam
      lead   idle      integrating a and b
      a      busy      parsing the schema
      b      waiting   input needed
    doperpowers
      60-api-qagent   stopped   QAGENT · reviewing: PR #158

No header line. `--state W` keeps the rows whose word is `W` (it replaces
`--status S`, which filtered on the recorded status). `--json` prints each
seat's public record with a `state` key and without `live` or `addr`; ids
(`seat_id`, `current`, `short`) stay, which is how a script gets them.
`(no seats)` when nothing matches.

### `chart` and `tui`

The state word replaces the live word in every box, glyph line, flash, and
count: `●` busy, `○` idle, `◐` waiting, `■` stopped, `✕` gone, `◌` vacant,
`⊘` retired. The TUI's `N live` counts `FILLED`. **Hidden by default**,
shown with `--all` / the `a` key and counted in the `+N` tail: a `retired`
or `gone` seat — the word decides, with no harness test of the hide rule's
own — so the default chart stays the seats one can act on without a
`fill`. The TUI's `s` key opens the send line for any seat that is not
`vacant`, `retired`, or `gone` (a `stopped` one is resumed by the send);
Enter attaches as today, and a seat with no short id says so.

## The one delivery verb

    sminos send <seat | session name | codex:<id|exact name> | thread id> "<msg>" [--wait] [--from F]

- **A seat** — resolved as above; under the seat's lifecycle lock. A live
  peer: the frame goes on its socket and the recorded status is set
  `working` (what `wake` did; the old `send` wrote nothing). `stopped`:
  the seat is resumed with the frame as its message (`claude --bg --resume
  <session id> <frame>`, `resume_session`), as `wake` did. `vacant`:
  refused, pointing at `fill`. `retired`: refused, pointing at `fill`.
  `gone`: refused in one line pointing at `fill` (fresh) or `retire`.
  `--wait` waits for evidence the frame landed and then for the turn's end
  and prints the reply (`wait_socket_turn`, `finish_turn`, unchanged).
- **A live harness session by name**, when no seat matched and the caller
  is not a family seat: the frame on its socket; one live holder required,
  more are ambiguous. `--wait` on such a target is refused in one line:
  there is no record to watch.
- **A Codex thread**: unchanged (`codex:` prefix, or a bare thread id when
  nothing else matched); `--wait` refused the same way.
- **Reach**: unchanged. A family seat reaches its family; a raw name or a
  Codex thread from a family seat gets the reach hint.
- **The frame**: every delivery, socket or resume or Codex queue, opens
  with `[sminos message from <sender> id=<8 hex>]`. The id is what
  `--wait` finds in the transcript; carrying it always costs nothing and
  removes the second header (`[sminos wake from …]`). `<sender>` is
  `default_from` as today: the caller's alias, else its harness name, else
  `human` from a terminal.

**`wake` goes.** `sminos wake …` exits 2 with one line on stderr, `sminos:
wake was folded into send — sminos send <seat> "<msg>" [--wait] [--from
F]`, the shape the board verbs took when they were retired. There is no
alias. `resume` stays: it is the process-level continuation that carries
the invoking environment, which the board's relay needs and `send` must
not do.

**The board's call sites move with it.** `skills/issue-tracker/scripts/board-answer.sh`
(one `wake --wait`), `_sweep_api.sh` (three), and `board-sweep.sh` (one;
see the Decision Log) call `send` with the same
arguments; their comments that explain "wake, not resume" keep the
reasoning under the new name. Their test stubs, which log
`wake:<uuid>:<head>` and `from:wake:<uuid>:<from>` and accept the verb in a
`resume|wake)` case, log and accept `send` instead, and the assertions
that read them follow. The board scripts' semantics do not move: each
site addresses a seat by full uuid with `--wait`, which `send` accepts
exactly as `wake` did.

## Acceptance

Run from a terminal at the repository root, with `S=skills/sminos/scripts/sminos`
and `SMINOS_HOME` pointing at an empty directory. "Prints" means stdout.

1. `$S spawn lead "say hello, then wait" --group one`; `$S list` prints a
   `one` heading and one row, `lead` `busy`, no header line and no
   `ADDR`, `SHORT`, `LIVE`, or `STATUS` column; when the turn ends the row
   reads `idle`. No word other than the seven appears in any `list`, `chart`,
   or `tui` output during this section.
2. `$S spawn a "wait" --group one`, then `$S spawn a "wait" --group two`
   while `one/a` is live: the second exits 0. `$S send a "x"` exits 4 with
   `ambiguous seat 'a' matches: one/a, two/a`; `$S send two/a "x"` prints
   `sent to two/a …` and `two/a` reads `busy` then `idle`.
3. With `two/a` idle, `$S send two/a "reply DONE" --wait` prints the
   reply block containing `DONE`; the frame in its transcript opens with
   `[sminos message from human id=` followed by eight hex digits.
4. After `claude stop <two/a's short id>` (or the session's end), `$S
   list` reads `two/a` as `stopped`; `$S send two/a "back" --wait` prints
   `via --bg --resume` and the reply; the row reads `busy` and then `idle`
   again.
5. `$S wake two/a "x"` exits 2 and stderr reads `wake was folded into
   send`; `$S spawn z "t" --group one --addr q` and `$S seat add one q
   --addr q` exit 2 as unknown arguments; `$S list --json` rows carry
   `"state"` and no `"addr"` or `"live"` key.
6. `$S send <first 8 characters of two/a's seat id> "x"` exits 4 with `no
   seat matching`; the full seat id delivers.
7. `$S seat add one me --session $CLAUDE_CODE_SESSION_ID` from inside a
   Claude session whose harness name is not `me` succeeds and the row
   reads `me` with this session's live word.
8. `$S retire one/lead`, `$S retire one/a`, `$S retire two/a`; `$S list`
   reads all three `retired`; `$S chart` shows none of them, `$S chart
   --all` shows them with `⊘`.
9. `tests/sminos/run-sminos-tests.sh` passes; `tests/issue-tracker/test-board-sweep.sh`
   passes; `tests/claude-code/run-skill-tests.sh` passes (it drives the
   `board-api/test-*.sh` suites); `tests/skill-links/test-cross-doc-refs.sh`
   passes; `scripts/lint-shell.sh` is at its baseline.
10. `grep -rn "sminos wake\|--addr" skills agents CLAUDE.md` prints nothing
    outside `docs/doperpowers/specs/`.
11. `$S seat add one x --session <a uuid the harness does not know>`; `$S
    list` reads `x` as `gone`; `$S send one/x "hi"` exits 4 with one line
    pointing at `fill`; `$S chart` does not show `x` and `$S chart --all`
    shows it with `✕`.

## Plan of Work

Constraints that bind every milestone: the recorded status, `sync`,
`resume`, `say`, `chat`, `fill`, `retire`, `spawn`'s launch arguments
(`-n <alias>`), and every board script's *behavior* are outside this spec
— a board script changes only where it spells `wake`. Tests are the
existing suites extended; the sminos suite already fakes session records
under a redirected `HOME` and runs a unix-socket server, which is the
source the new state word reads. Names in the CLI's own output are
alias-first (`group/alias` where ambiguity is possible), never ids. No
attribution lines in commits.

### M1 — one state word

**What exists at its end.** `sminos list` prints the grouped table above
with one `STATE` word per seat; `--state` filters on it; `--json` carries
`state`; `chart` and `tui` draw the same word and hide by the new rule; no
view consults `claude agents` to describe a seat.

**Touches.** `skills/sminos/scripts/sminos.py` (`state()` beside
`live_state`, which it replaces; `FILLED`, `REFILLABLE`; `cmd_list`;
`now_or_reply`; every `live_state` caller — `push_member`'s stopped check,
`cmd_spawn`'s and `cmd_fill`'s filled check, `cmd_attach`, `cmd_send`'s
refusal text, `cmd_reply`'s summary line, the cascade's live-children
test), `skills/sminos/scripts/sminos_chart.py` (`GLYPH`, `is_dead`,
`seat_node`), `skills/sminos/scripts/sminos_tui.py` (the `s` key rule,
`attach_target`, `glyph_line`, the counts), `tests/sminos/run-sminos-tests.sh`.

**Interfaces.** `state(seat) -> str` and `peer_state(rec) -> str` in
Interfaces and Dependencies. M2 and M3 consume `state`.

**Decisions.** `state()` reads `peer_for_session(current)`; `peer_live`
already proves the socket. The `waitingFor` text reaches `now_or_reply`
through the peer record, so `now_or_reply` takes the record or looks it up
once. `push_member`'s "resume a tagged stopped member" now includes a
member the harness has forgotten; its resume fails and is recorded as that
member's `failed: …` outcome, as any refused resume is — verify the
fan-out still survives it. The chart's hide rule is the only place the
old `gone` test remains; it calls `harness_row` and nothing else does for
display. `list`'s sort is by group recency then seat recency; a group's
name is its heading exactly, no count. The `--status` flag is removed,
not aliased.

**Does not touch.** `send`, `wake`, `addr`, the locks, `find_seat`, the
recorded status, `sync`, the board scripts.

**Proves.** Acceptance 1, 8, and the `list --json` half of 5. Tests pin:
each of the six words from a constructed record and session record
(including `shell` → `busy`, an absent `status` → `busy`, a dead pid with
a socket file → `stopped`); the row shape and group order; `--state`;
`--json` keys; the hide rule with and without a harness row; the TUI's
`s` on a stopped seat opening the send line (headless).

### M1 follow-up — `gone` reinstated

Added after M1 landed (Decision Log, 2026-09-29, the human partner's
course change); it supersedes M1's "the chart's hide rule is the only
place the old `gone` test remains". Its predicate was revised the same
day (Decision Log, "the predicate, not the word"): first landed as "the
harness listing has no row" (39c17bd7), it is now "no transcript on this
machine", and `claude agents` leaves `state()` again.

**What exists at its end.** `state()` returns `gone` for a seat with a
`current`, no live peer, and no transcript for the session on this
machine (`transcript_path(current)` empty); `stopped` when the transcript
is there.
`REFILLABLE` is `(vacant, stopped, gone)`. `list --state gone` filters
like the others. The chart and TUI draw `✕` for `gone` and a distinct
`⊘` for `retired`, hide retired-or-gone by the word alone (the hide rule's
own `harness_ok()`/`harness_row` test goes), and the TUI's `s` refuses a
`gone` seat pointing at `fill`/`retire`.

**Touches.** `sminos.py` (`STATES`, `REFILLABLE`, `state()`, and any
caller whose branch on `stopped` must now also see `gone` — spawn's and
fill's refill checks, `push_member`'s tagged-resume guard, the old
`send`'s refusal text), `sminos_chart.py` (`GLYPH`, `is_dead`),
`sminos_tui.py` (the `s` rule, styles), `tests/sminos/run-sminos-tests.sh`.

**Decisions.** The transcript is found by the existing
`transcript_path(session_id)`, which globs by the unique session id; a
`retired`, `vacant`, or live seat never looks. `list` runs no `claude
agents` at all. `push_member`'s tagged resume skips a `gone`
member as `recorded`, not `failed:` — a resume that cannot work is not
attempted, which is also what the pre-branch code did — and, when the
member was tagged, warns as a retired one is warned: `<alias> is gone
— no transcript for its session on this machine; fill it to reach it`
(this replaces M1's
forgotten-member-resume test).

**Proves.** Acceptance 11's `list` and `chart` halves. Tests pin: `gone`
from a record with a session id, no peer, and no transcript; `stopped`
from a record with a session id, a transcript file, no peer, and no
harness row; `list` invoking no `claude agents` (the stub's call log);
`list --state gone`; `chart` hides and `chart --all` shows a gone seat
with `✕`, a retired one with `⊘`.

### M2 — one name

**What exists at its end.** A spawn or `seat add` succeeds while another
group's live seat holds the alias; `addr` is gone from the record, flags,
prints, and JSON; a prefix or a short id no longer names a seat.

**Touches.** `skills/sminos/scripts/sminos.py` (`load_seat`, `spawn_fresh`'s
launch record, `cmd_spawn`, `cmd_seat_add`, `refuse_live_name` and its
callers, `lock_names`' docstring and `lock_seat`, `find_seat`, the parser,
the module docstring's address sentence), `tests/sminos/run-sminos-tests.sh`.

**Decisions.** `lock_names` keeps its sha1-of-name file scheme with the
seat key `group/alias` as the name; `spawn` locks that key before it knows
whether the seat exists. `refuse_live_name` is deleted, not stubbed;
`live_name_holders` stays for `send`'s raw-name route. `find_seat`'s
stages become: `group/alias`; exact seat id or session id; unique alias.
The `seat add` strand-guard keeps its `--session` half verbatim. The
launch record's `name` is the alias; nothing writes `addr`.

**Does not touch.** The verbs, the views beyond the `ADDR` column (M1
removed it), the recorded status, the board scripts.

**Proves.** Acceptance 2 (the spawn half), 6, 7, and the flag half of 5.
Tests pin: same-alias spawn across two groups both live; `send a`
ambiguous with the `group/alias` list; the record without `addr` and
with `name == alias`; the prefix and short-id lookups answering `no seat`;
a joined session whose harness name differs from its alias listing under
the alias.

### M3 — one delivery verb

**What exists at its end.** `send` delivers to a live seat, resumes a
stopped one, waits with `--wait`, and refuses `--wait` for a non-seat
target; `wake` prints its pointer and exits 2; the board's four relay
sites and their stubs call `send`; every frame opens with the one header.

**Touches.** `skills/sminos/scripts/sminos.py` (`cmd_send` absorbs
`_wake`; `cmd_wake` becomes the pointer; the parser; the frame text;
`compose` of the codex text), `skills/sminos/scripts/sminos_tui.py`
(`send_argv` unchanged; the flash text), `skills/issue-tracker/scripts/board-answer.sh`,
`skills/issue-tracker/scripts/_sweep_api.sh`, `skills/issue-tracker/scripts/board-sweep.sh`, the stubs and assertions in
`tests/issue-tracker/test-board-sweep.sh` and
`tests/claude-code/board-api/test-answer.sh`, `test-sweep-stall.sh`,
`test-sweep-finalize.sh`, `test-sweep-renew-relay.sh`,
`test-sweep-review-recover.sh`, `test-read-verbs.sh`,
`test-review-dispatch-claim.sh` (each where it spells `wake`),
`tests/sminos/run-sminos-tests.sh`.

**Decisions.** The seat path is `_wake`'s body under `send`'s name: lock,
reload, refuse codex, vacant → `fill` pointer, `gone` → one line pointing
at `fill`/`retire` (exit 4), live → frame + `working`,
else `resume_session`. The old `send`'s seat branch (no lock, no status
write) is deleted. `--wait` with a non-seat target dies before any
delivery. The frame id is minted for every path. The pointer for `wake`
is a parser-level catch (`sub.add_parser("wake")` with a handler that
dies), so `sminos wake` never reaches `find_seat`. In the board scripts
the argument order stays `send --wait "$uuid" "$text" --from sweep`
where it was `wake --wait …`, so the stubs' positional reads keep
working after their verb case changes. The `ACK` and delivery-uncertain
messages name `send` where they named `wake`.

**Does not touch.** `resume`, `say`'s push, the reach rule, the codex
queue, `board-answer.sh`'s relay logic beyond the verb.

**Proves.** Acceptance 2 (the send half), 3, 4, 5 (the `wake` line), 11 (the `send` half), and
9's board suites. Tests pin: a `send` to a live seat marks `working` and
carries `id=`; a `send` to a stopped seat resumes with the frame as its
message; `send --wait` on a session name and on `codex:x` refused before
delivery; `wake` exits 2 with the pointer; the board stubs' logs read
`send:` and `from:send:`.

### M4 — the words and the proof

**What exists at its end.** `skills/sminos/SKILL.md` describes the one
name, the state table, the grouped `list`, and `send` as the delivery
verb, and names none of `wake`, `addr`, `live`, `blocked` (`gone` is one
of the seven words, Decision Log 2026-09-29); the
module docstring's usage block and address sentence match; the version is
bumped; the acceptance section has been run on the real harness and the
record written.

**Touches.** `skills/sminos/SKILL.md` (frontmatter description: `spawn,
send, list, attach to, or retire`; the overview's `send`/`wake` paragraph;
the agent protocol; the joining paragraph and its aliases sentence; the
operator table; the `live`/`status` paragraph → the state table; the
permissions paragraph's `sminos wake <seat> "<answer>"`; "message it with
sminos send/wake"), `skills/sminos/references/spawn-preamble.md` (only if
it names anything that moved; today it does not), the module docstring,
`.version-bump.json`'s files via `scripts/bump-version.sh <version>`, this
document's record.

**Decisions.** The version is the next minor above main's at merge time
(main is 7.129.0 as this is written; PR #186 also carries 7.129.0 and is
re-bumped when it merges). The live proof is run by the session that owns
this spec, not the executor, on the real harness with a real `SMINOS_HOME`
in a temporary directory, and its transcript lines go into Surprises &
Discoveries. The whole-branch review runs through doperpowers:review-code
at `reviewer-medium`: the diff is a focused refactor of one module and a
verb rename at a seam the board suites pin.

**Does not touch.** `docs/doperpowers/specs/` history, `CLAUDE.md` (its
repo map does not spell these verbs), the issue-tracker skill (its "wake
ritual" is the human's, not this verb).

**Proves.** Acceptance 10 and, at the owner's hands, 1–8 live.

## Concrete Steps

Working directory: the repository root (this worktree).

    tests/sminos/run-sminos-tests.sh                 # the sminos suite; ends "N assertions, 0 failures"
    tests/issue-tracker/test-board-sweep.sh          # the sweep suite; ends with its pass count
    tests/claude-code/run-skill-tests.sh             # drives board-api/test-*.sh among others
    tests/skill-links/test-cross-doc-refs.sh         # doc links
    scripts/lint-shell.sh                            # shellcheck baseline
    skills/sminos/scripts/sminos list                # on the real registry: grouped, one word per row
    scripts/bump-version.sh <version>                # M4 only

## Interfaces and Dependencies

In `skills/sminos/scripts/sminos.py`:

    STATES = ("busy", "idle", "waiting", "stopped", "gone", "vacant", "retired")
    FILLED = ("busy", "idle", "waiting")
    REFILLABLE = ("vacant", "stopped", "gone")

    def peer_state(rec) -> str:
        """busy | idle | waiting from a LIVE peer record's `status`
        (idle and waiting exact; anything else, including absent, is busy)."""

    def state(seat) -> str:
        """One of STATES, read in the table's order: retired (recorded
        status), vacant (no `current`), then peer_state of the live peer
        for `current`, else stopped when the session's transcript is on
        this machine (transcript_path), else gone. Replaces live_state."""

    def needs_probe(seat) -> bool:
        """False for a retired or vacant seat — its word needs no peer."""

    def seat_state(seat, peer) -> str:
        """The word from ONE already-made probe (`peer` is the live peer
        record or None). state() is needs_probe + one peer_for_session +
        seat_state; send and push_member route on the same probe they
        classify with."""

The frame header, everywhere a message is delivered:

    [sminos message from <sender> id=<8 hex>]

`list --json`: the array of `public_seat(s)` plus `"state": state(s)`,
without `live` and without `addr`.

`send`'s argv: `send <target> <msg> [--wait] [--from F]`. `wake`'s
pointer: exit 2, stderr `sminos: wake was folded into send — sminos send
<seat> "<msg>" [--wait] [--from F]`.

## Surprises & Discoveries

- (M1) The suite's stub `claude --bg` writes a harness row but never a
  session record, so under the new rule every stub-spawned seat reads
  `stopped` unless the test writes a peer record; the `st_peer` and
  `org_peer` helpers in `tests/sminos/run-sminos-tests.sh` are the shape
  M2 and M3 tests use for a `busy` or `idle` seat.
- (M1) `harness_row` keeps callers after M1 — `attach`, the TUI's
  `attach_short`, `resume_session`, `sync` (after the predicate revision
  the hide rule reads the word only); `harness_ok` is used only by `sync`.
- (M3 fix wave) `transcript_path` globbed `projects/**/<sid>.jsonl`
  recursively: 0.61 s per call on the real machine, 4.61 s for the 22
  peerless seats a `list` classifies. It now globs one level,
  `projects/*/<sid>.jsonl` (0.004 s per call; the same 3 transcripts
  found), and returns the newest copy when a session's transcript sits
  under two project dirs (3b8a42d7 does, under Developer/ and Documents/).
  The one-level glob also no longer matches subagent-depth files. `sminos
  list` on the real registry: 0.65/0.35/0.35 s before, 0.48/0.40/0.41 s
  after.
- (M1) Between M1 and M3 the TUI's `s` on a stopped seat opens the send
  line and the send is refused (`not live — use sminos wake`); M3's fold
  closes it.
- (M3) The stall nudge's no-`--wait` call never runs under
  `test-board-sweep.sh`'s stub (which refuses a call without `--wait`):
  that suite runs the gh binding only (`board-sweep.sh` execs
  `_sweep_api.sh` only under `BOARD_BINDING=api`); the nudge runs under
  `test-sweep-stall.sh`'s own stub, which never checks `--wait`.
- (M3) The board scripts did not change, but what they reach through
  `send` is stricter than `wake` was: `wake` attempted a resume of any
  seat with a `current` and no live peer, retired and harness-forgotten
  ones included; `send` refuses `retired` and `gone` with exit 4. The
  relays already read a nonzero exit as "not delivered, settled next
  tick", and `_liveness` classes retired seats dead before relaying, so no
  board path relays to a retired seat. With `gone` read from the
  transcript (the predicate revision), the board loses nothing: a worker
  whose transcript is here reads `stopped` and is resumed as `wake` did,
  and one without could never be resumed by `wake` either.
- (predicate revision) A `claude --bg --resume <session id>` with no
  transcript is not refused at launch: it prints the `backgrounded ·`
  banner, exits 0, and the job reads `failed` within seconds — which is
  what `wake` did for such a worker before this branch (the sweep saw a
  failed job, not an error exit). `send`'s immediate exit-4 refusal on
  `gone` is a strict improvement for the board.
- (M3) The sminos suite's `grep -c` on an empty `calls.log` exits 1 under
  `set -e`; those counts use `|| true`. The assert helpers read a
  here-string now (a `printf | grep -q` under `pipefail` could SIGPIPE).
- (live proof, 2026-09-30) Acceptance 1–6, 8 and 11 held as written on
  the real harness with three haiku seats and a temporary `SMINOS_HOME`.
  Evidence: `one/lead` read `busy` then `idle`; `two/a` spawned while
  `one/a` was live (`rc=0`), `send a "x"` answered `ambiguous seat 'a'
  matches: one/a, two/a` (`rc=4`), `send two/a "x"` printed `sent to two/a`;
  `send two/a "reply DONE" --wait` printed the reply block with `DONE`, and
  the transcript's frame read `[sminos message from sminos id=86388163]`
  (the sender is this session's harness name, as `default_from` says);
  after `kill <pid>` the row read `stopped` and `send two/a "back" --wait`
  printed `sent to two/a [99ff00a5 / …] via --bg --resume status=idle
  turns=2` and the reply; `wake` exited 2 with the pointer; `--addr`
  exited 2 as an unrecognized argument; `list --json` keys held `state`
  and neither `addr` nor `live`; the 8-character prefix answered `no seat,
  live session, or codex thread matching` (`rc=4`) and the full id
  delivered; `seat add two ghost --session <made-up uuid>` listed as
  `gone`, `send` on it exited 4 with the transcript wording, `chart`
  showed it 0 times and `chart --all` once; after `retire` all three rows
  read `retired`, `chart` printed the fold note and `chart --all` drew
  `⊘ retired`. Two cosmetic observations: argparse's own usage line, on an
  unrecognized-argument error, still lists `wake` among the commands
  because the pointer is a subparser; and the chart's group box reads
  `1 seats` (pre-existing). `sminos list` on the real registry: 0.45 s.

## Decision Log

- Decision (2026-09-29, at authoring): the three forks the human partner
  chose after the assessment — uniqueness per group (over keeping the
  fleet-wide refusal), one state word in the harness's vocabulary (over
  two columns, and over keeping `blocked`), and `send` as the surviving
  verb with `wake` folded into it (the assessment had proposed the reverse,
  `wake` surviving; the human partner chose `send`, and the design reads
  the same either way: one verb that delivers, resuming when it must).
  Verification: no independent spec review
  — the design is three chosen forks and the mechanics are a rename and
  a fold whose seams the board suites already pin; the whole-branch
  review at `reviewer-medium` is the independent read. M1–M3 run under a
  `doperpowers:plan-executor`; M4's docs are the executor's and its live
  proof is the owning session's.
  Date/Author: 2026-09-29, Claude with the human partner's answers.
- Decision (2026-09-29, pre-flight, execution controller): the board's
  `wake` call sites are five, not four, and not all carry `--wait` —
  `board-answer.sh:330` (`wake --wait`), `_sweep_api.sh` at the stall
  nudge (`wake`, no `--wait`), the renew relay and the review-recover relay
  (`wake --wait`), and `board-sweep.sh`'s auto-recovery relay (`nohup …
  wake --wait`), which the design section's count missed. All five move to
  `send` with their arguments unchanged; the no-`--wait` site keeps no
  `--wait` (a `send` without it resumes a stopped seat exactly as `wake`
  did). Acceptance 10's grep covers `skills/`, so the comments and
  operator notes in those three scripts that spell `sminos wake` (and
  `board-sweep.sh`'s exhausted-recovery note) name `send` too — text only.
  The issue-tracker's "wake ritual" and "wake queue" are the human's and
  stay. Reason: the intent is one delivery verb; a call site left on the
  pointer verb would exit 2 at runtime.
  Date/Author: 2026-09-29, plan-executor (SDE controller).
- Decision (2026-09-29, M1): the gaps M1 resolved. `now_or_reply(s, st)`
  takes the state word and reads the session record only for a `waiting`
  seat with no status line. An alias longer than 24 cells overflows its
  row rather than being cut — it is the name the operator types. The
  chart's fold note and the TUI's group detail read `+N hidden` / `N
  hidden`, since the hidden count now includes stopped seats the harness
  forgot, which `list` calls `stopped`. The TUI detail line drops the
  recorded status. The hide rule is `stopped and harness_ok() and no
  harness row` — a harness that cannot be asked shows the seat — and a
  recorded `failed`/`error` no longer hides one. spawn and fill refuse
  `state in FILLED` naming the word, and both keep the "previous occupant
  still answers" refusal for a retired seat whose session runs; fill
  checks it before its `--resume` branch so such a seat is not stopped and
  resumed. The TUI's `s` on a vacant or retired seat refuses and points at
  `fill`. `push_member` keeps its `state(fresh) != "stopped"` guard; a
  tagged member the harness forgot now gets a resume attempt, and its
  refusal is that member's `failed:` outcome while the fan-out delivers
  to the rest (pinned).
  Date/Author: 2026-09-29, M1 task-executor, folded by the controller.
- Decision (2026-09-29, controller): the recorded status leaves the
  *views* — `list`, `chart`, `tui`, `reply`'s summary — not the one-shot
  launch banners of `spawn`, `fill`, and `resume_session` (`… status=working`,
  `via --bg --resume  status=…  turns=…`). Those are the lifecycle verbs
  this spec does not touch, `execute-dispatch.sh` documents the spawn
  banner's shape, and acceptance 4 only pins `via --bg --resume`. The line
  M3 writes for `send`'s socket delivery is `sent to <group>/<alias>`,
  alias-first with no ids or status (acceptance 2).
  Date/Author: 2026-09-29, plan-executor (SDE controller).
- Decision (2026-09-29, M1 review): the chart's `prune` keeps a hidden
  seat that still has a visible descendant, drawn with its own word (`✕`,
  `■`), as it did before this spec — the chart is a tree, and a hidden
  parent is the edge its visible children hang from; promoting them would
  draw them as roots they are not. "Hidden by default" means a hidden
  seat is not drawn *for itself*. The M1 task review raised it; dismissed
  as the existing tree-drawing intent, unchanged.
  Date/Author: 2026-09-29, plan-executor (SDE controller).
- Decision (2026-09-29, course change after M1): `gone` is reinstated as a
  seventh state word — a saved session id the harness no longer lists (no
  row in `claude agents --json --all`, no live peer). Read order: retired,
  vacant, live peer (busy/idle/waiting), then `stopped` if the harness
  lists the session or the listing cannot be read, else `gone`.
  `REFILLABLE` is `(vacant, stopped, gone)`; `FILLED` unchanged. The
  chart/TUI hide rule becomes retired-or-gone by the word, with no harness
  test of its own; `gone` keeps its old `✕` and `retired` takes `⊘`.
  `send` on a gone seat refuses in one line pointing at `fill`/`retire`
  (M3); acceptance 11 pins it. Rejected alternative: the first draft's
  fold of `gone` into `stopped`, letting `send` learn from the harness's
  refusal — `stopped` is defined as "`send` resumes it", which is false
  for about thirty seats in the real registry, and the hide rule already
  computed the distinction. This supersedes M1's hide-rule entry above
  (`stopped and harness_ok() and no harness row`) and M1's
  forgotten-member resume in `push_member`: a gone member is `recorded`,
  not attempted. Landed as an M1 follow-up after M2, before M3.
  Date/Author: 2026-09-29, the human partner's decision, relayed by the
  owning session; written in by the controller.
- Decision (2026-09-29, M2): the gaps M2 resolved. Both ambiguity paths
  share one `ambiguous_seat()` helper printing sorted `group/alias` names,
  no ids. A seat send prints exactly `sent to <group>/<alias>`.
  `load_seat` reads `name` as the alias and drops a stale `addr` in memory
  (the file is untouched), so an old record's custom addr never shows as
  a second name. `lock_names` lost its `label` (every caller locks one
  key, built by `seat_key()`; the refusal reads `'g/a' is being changed by
  another sminos process`). `find_seat` keeps ids before the unique alias,
  per the milestone's stage list — with prefixes gone the two orders
  differ only for an alias that is itself a full uuid. migrate's v2
  conversion stops writing `addr` too. The strand guard's message drops
  `at addr '…'`; its logic is verbatim.
  Date/Author: 2026-09-29, M2 task-executor, folded by the controller.
- Decision (2026-09-29, M1 follow-up): the TUI's refusal for a `gone`
  seat names both moves (`sminos fill <g>/<a> "<task>" or sminos retire
  <g>/<a>`). `push_member` returns `recorded` for an untagged member before
  it reads the state, so an untagged message never reads the listing and
  only a tagged member is warned. The listing read is pinned: exactly one
  `claude agents` call for a group with peerless seats, none for an
  all-live-or-vacant group. On the real registry `list --state gone`
  showed 21 seats that day.
  Date/Author: 2026-09-29, M1 task-executor, folded by the controller.
- Decision (2026-09-29, M3): the gaps M3 resolved. A `retired` seat is
  refused (pointing at `fill`) even while its session answers — the design
  section's rule; the milestone's Decisions list had left it out. A send
  probes the peer once and derives the word from that probe (a second
  probe used up the suite's one-shot socket and hid the pre-write
  fallback). `resume_session`'s verb for a send is `sent to`, so every
  seat delivery opens `sent to g/a` (the resume banner keeps its bracket
  and tail). With `--wait` the socket path prints `sent to g/a` before it
  waits, then the reply block. `--wait` on a non-seat exits 2 (`--wait
  needs a seat: … no record to watch`), after the family reach check.
  `wake` takes every argv shape (NUL `prefix_chars`) so old forms like
  `wake --wait x y` get the pointer, never argparse's error.
  `board-sweep.sh`'s `_recover` verb argument is `send` too, so its log
  reads `send attempt 1/3`. `tests/issue-tracker/test-board-scripts.sh`
  also pinned `wake --wait` and moved with the others. In the board-api
  tests only the logged verb changed; `$WAKE`/`wakes()` name the nudge
  and stay.
  Date/Author: 2026-09-29, M3 task-executor, folded by the controller.
- Decision (2026-09-29, the predicate, not the word): `gone` is a saved
  session id with no live peer and **no transcript for it on this
  machine** (`transcript_path(current)` empty); `stopped` is no live peer
  with the transcript present. Read order: retired, vacant, live peer →
  busy/idle/waiting, transcript present → stopped, else gone. `claude
  agents` leaves `state()` entirely — the spec's original aim — and the
  hide rule stays retired-or-gone by the word. Rejected: the course
  change's first predicate, "no row in `claude agents --json --all`" (as
  landed in 39c17bd7), because the listing is the harness's job list, not
  its transcript store. Evidence, run by the owning session on the real
  harness: `agora-msg-probe` (seat 3b8a42d7…, absent from the listing,
  transcript on disk) — `claude --bg --resume
  3b8a42d7-93b9-4dbd-913e-3034ef632054 "Reply with exactly one word: ok"`
  printed `backgrounded · 3b8a42d7`, and five seconds later the listing
  held `{'id': '3b8a42d7', …, 'name': 'agora-msg-probe', 'status': 'busy',
  'state': 'working'}`. Of the 21 unlisted seats in the real registry, 2
  have transcripts on this machine (resumable) and 19 do not (from other
  hosts). From the other side: `claude --bg --resume
  12345678-1234-4123-8123-123456789abc "x"` (no transcript anywhere)
  printed the `backgrounded · 12345678` banner and exited 0, and four
  seconds later the listing read `{'id': '12345678', 'name': 'x', 'state':
  'failed'}`, no transcript written, `claude logs` answering "job not
  found". M3's `send` refusal on `gone` stands and is now honest; the
  tagged-member warning names the transcript, not the harness.
  Date/Author: 2026-09-29, the owning session's harness evidence;
  written in by the controller.
- Decision (2026-09-30, M3 fix wave): a send classifies and routes on one
  peer probe. The M3 task review found `send_to_seat` routing on its own
  probe but classifying through `state()`'s second one, so a failed-first,
  live-second probe resumed a live seat (a stop and relaunch of its turn)
  instead of writing to its socket. `needs_probe(seat)` and
  `seat_state(seat, peer)` (Interfaces) carry the single probe; `state()`
  is built on them, and `push_member` passes its earlier no-peer result.
  Pinned: `live-first:1:socket dead-first:1:resume`. The spawn and fill
  "previous occupant still answers" hints read `use sminos resume, or stop
  it first` (`send` refuses a retired seat). No per-invocation transcript
  cache: the one-level glob is cheap enough. The family fixtures keep
  their harness rows, which the resume path and `pending_short` read.
  Date/Author: 2026-09-30, M3 task-executor, folded by the controller.
- Decision (2026-09-30, M4 words): `SKILL.md` keeps the literal
  `[blocked on a harness prompt …]` marker the reply prints (only the verb
  beside it moved, to `send`), and "live" as an adjective (only the column
  and field went). It says `list --json` carries the ids for scripts, not
  that ids are hidden — the TUI's detail panel still shows them. The
  hide-rule sentence names the visible-descendant exception (the M4 task
  review's Minor). The docstring's exit-codes line names `send`'s exit-4
  refusals and `wake`'s exit-2 pointer. The version is 7.130.0: origin/main
  moved to 7.129.1 during execution, and the next minor is the same.
  Date/Author: 2026-09-30, M4 task-executor, folded by the controller.

## Outcomes & Retrospective

Achieved, against the purpose: a seat is one alias, one state word, and
one delivery verb. `list` on the real registry prints every group as a
heading over rows of `alias  state  now` in 0.45 s, reading the
harness's per-session record, one socket probe, and the transcript's
presence, and never `claude agents`; the same seven words draw the
chart and the TUI; `send` delivers or resumes and refuses what it
cannot reach in one line; `wake` and `addr` are gone from the CLI, the
record, the flags, and the skill; the board's five relays call `send`
with their arguments unchanged. Suite 746 → 856 assertions; board
suites green; live proof held on acceptance 1–6, 8, 11; the
whole-branch review at reviewer-medium found nothing material.

What remains: acceptance 7 (a joined interactive session) was not run
live; the argparse usage line lists `wake` among the commands because
the pointer is a subparser (cosmetic; an argv intercept before parsing
would hide it); the chart's `1 seats` grammar predates this branch;
existing stderr noise in the raw-name failure-injection test and
`test-sweep-renew-relay.sh`'s teardown line stay as they were.

Lessons: the word was chosen before its predicate was tested — `gone`
was reinstated on the right argument (a word must not promise a
resume that fails) and then defined by the wrong observable (the
harness listing), and two live resume attempts settled it in five
minutes, which the design discussion had not. Test the predicate
behind a state word on the real system before it names anything. The
one-probe defect in `send` came from composing a classifier and a
router that each probed liveness; when a verb both decides and acts,
it reads the world once. And a hide rule that still computed a
distinction the vocabulary had dropped was the sign the vocabulary was
short a word.
