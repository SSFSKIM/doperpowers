# agora v3 — seats: one fleet registry, the daemon substrate folded into the agora CLI

This ExecPlan is a living document maintained under the ExecPlan contract
vendored at `skills/execplan/references/PLANS.md`. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds. It builds on two checked-in plans it
supersedes in part: `docs/doperpowers/execplans/2026-08-27-agora.md` (agora v1:
groups, topology, board) and `docs/doperpowers/execplans/2026-08-31-agora-native-transport.md`
(agora v2: messaging moved onto the harness's native SendMessage tool). Nothing
in those files is required reading; everything this plan relies on is restated
here.

## Purpose / Big Picture

Today this repository has two tools that each describe half of the same thing.
`skills/orchestrating-daemons/scripts/` is a set of bash scripts that spawn,
resume, track, and retire durable background Claude Code sessions ("daemons"),
keeping one JSON record per daemon under `~/.claude/orchestrating-daemons/`.
`skills/agora/scripts/agora` is a bash CLI that gives a set of sessions a named
working group: who spawned whom, a member registry mapping aliases to messaging
addresses, and a communal board. The daemon registry knows a session's task,
worktree, model, and liveness but nothing about the group it works in; agora
knows the group and the spawn tree but nothing about the process. An operator
who asks "what is my fleet doing" runs two list commands with two vocabularies,
and an agent that wants to spawn a child wired into its group has to remember
an environment-variable prefix on a script in another skill's directory.

After this change there is one tool, `agora`, and one registry. Its unit is
the **seat**: a named position in a group, with a role, that a Claude Code
session fills. A seat outlives the process that fills it — when the session
ends or dies, the seat stays in the registry with its role, brief, and history,
and can be filled again by resuming the old session or by spawning a fresh one.
Every background session spawned through agora is a seat, including the
workers the board pipeline dispatches, so `agora list` is the whole fleet and
`agora view <group>` is one group's organisation chart with live state on every
node. The operator can message any live seat from a plain terminal (`agora
send`), wake a stopped one (`agora wake`), attach to one (`agora attach`), and
see at a glance which seats are busy, idle, blocked, stopped, or vacant.

You can see it working like this. From any terminal:

    agora spawn architect "Design the login flow; report on the board." --group login --role architect
    agora spawn impl-a "Implement the flow the architect posts." --group login --parent architect --role implementer
    agora view login          # tree: architect [architect] · idle  └── impl-a [implementer] · busy
    agora send impl-a "status?"   # arrives in impl-a's session as a peer message; idle sessions wake
    agora retire impl-a && agora fill impl-a --resume "continue"   # the seat survives; the session resumes under the same id

and the board pipeline's own dispatchers (`skills/executing/scripts/execute-dispatch.sh`,
`skills/qa-loops/scripts/review-dispatch.sh`, `skills/issue-tracker/scripts/*.sh`)
spawn, wake, finalize, and retire their workers through the same `agora` verbs,
so those workers appear in the same fleet view. The `orchestrating-daemons`
skill directory is deleted.

## Progress

- [x] (2026-09-01 20:30Z) Brainstorming grill with the human partner completed; four rounds of decisions recorded in the Decision Log below (seat model, single registry on the daemon-meta layout, Python core, `seat` as the canonical term, full retirement of the daemons skill, text-view panel this phase, autonomous track).
- [x] (2026-09-01 21:10Z) Feasibility spike: a message frame written from a plain shell to a background session's inbox socket woke the idle session and was delivered as a peer message (see Surprises). Probe session retired.
- [x] (2026-09-01 21:20Z) M0 — plan authored and committed (da08c828) on branch `worktree-agora-seats`; `skills/agora/scripts/lib.sh` written first so both parallel workers can source it; design-level adversarial review dispatched (codex `adversarial-review`, gpt-5.6-sol, xhigh). M1 and M2 run in parallel as two workers with disjoint file ownership; review findings are folded in as they land (remaining: fold findings).
- [x] (2026-09-01 22:05Z) M1 — `skills/agora/scripts/agora.py` (1956 lines, stdlib only) + 6-line bash launcher + `lib.sh`; registry model with read-time fallbacks; atomic-rename migration with the `.migrated-v3` one-time pass (group stamping + codex retirement); all verbs including the review-added `resume`, lifecycle locks, live-name refusal, and the acknowledged `wake --wait`; `tests/agora/run-agora-tests.sh` rebuilt (755 lines, stub `claude` with same-id resume and a copy mode, a real unix-socket inbox server, fabricated peer records) — 251 assertions green, independently re-run by the orchestrator; shell lint clean on the three shell files. Commit 758fd1ea (M1 worker).
- [x] (2026-09-01 22:50Z) M2 — board pipeline repointed (commits 4921f5ee, 27b18aa9, 65897e99, de096f6c; M2 worker): five dispatch/sweep scripts call `agora` verbs (spawn / resume --wait / sync / retire) through the `AGORA_CLI` seam and run `agora migrate --quiet` after their preflight; `review-dispatch.sh` sources `skills/agora/scripts/lib.sh`; the registry default is `~/.claude/agora` in every script (`_lib.sh`, `board-gc.sh`, `board-register.sh`, `board-bind.sh`, `board-lint.sh`, `_board.py` included); `board-answer.sh` lost the codex engine branch and gained the codex-binding refusal before any board write (+2 assertions); twelve pipeline test files stub one `agora` executable (verbs spawn / retire / sync / resume / migrate / meta get); all 23 hermetic suites green with assertion counts identical to the pre-M2 baseline (+2), shellcheck unchanged. The eight `board-api/integration` drills skip (exit 77, no board service) before and after — the rewritten stub was exercised by hand instead.
- [ ] M3 — skill surface: `skills/agora/SKILL.md` and `references/spawn-preamble.md` rewritten for seats (daemon doctrine absorbed), `skills/orchestrating-daemons/` and `tests/orchestrating-daemons/` deleted, every cross-reference in other skills/docs/manifests updated, `tests/skill-links` green.
- [x] (2026-09-02 07:40Z local / 2026-09-01 22:40Z) M4 — live fleet proof on real `claude` (transcript in Artifacts): the real registry migrated by rename+symlink (36 records stamped, 3 v2 nodes converted, 2 codex records retired, `agora list` prints no `null`); this session registered as `orchestrator`; `agora spawn scout` (sonnet) → scout spawned `scribe` from its preamble → three-level `agora view` tree with roles and live state; scribe's board post and scout's native `SCOUT-READY` arrived unprompted; `agora send scribe` from the shell woke the idle seat (`PONG-FROM-SCRIBE` arrived natively); `agora retire scribe` then `agora fill scribe --resume` continued the same session id and short (`RESUMED-VIA-AGORA` arrived). The first `fill --resume` attempts exposed the saved-options rule (flags on `--bg --resume` start a copy) — fixed in 66dec83f, 262 assertions. Dogfood seats purged, harness rows removed, group board deleted.
- [ ] M5 — exit gate. Done: codex code-review PANEL round 1 (`workflows/code-review.mjs --args {"base":"main"}`, run `wf-mtj88koo-ldukt9`, 18 min; 59 files / +4510 −4413 was past the single-reviewer threshold) → verdict incorrect, 29 confirmed findings (13 P1), all verified and adopted (see Decision Log, "exit gate"); fix wave landed: agora.py + tests in b440aa67 (all 26 items; suite 262 → 297 assertions, with new cases for re-fill vs live refusal, secret redaction, send ambiguity, recycled-pid liveness, native-wake sync, socket-failure fallback, codex purge, owning-repo grouping, missing-cwd refusal), pipeline in 9fc1d5b4 (fail-closed migrate with 3 new assertions; AGORA_HOME precedence in 10 defaults). Real registry re-checked after the wave: `agora list` prints no `null`, `agora migrate` is a silent no-op; all 27 suites green. Panel round 2 (`wf-mtj9n3b3-omv07r`) → 25 findings (14 P1), 24 adopted (see Decision Log "round 2"), second fix wave: agora.py + tests landed in d9ad851c (suite 297 → 353 assertions; the real registry re-migrated idempotently: root 0700, 69 files 0600, 4 duplicate historical aliases renamed `<alias>@<short>`), pipeline part in 47685259 (one root rule with both names exported by every entrypoint; migrate gated before direct reads; attempts-aware outage streak; review-dispatch 322 → 326 assertions). Remaining: suites → one converging review round (panel; stop when what remains is debt or dismissals) → version bump via `scripts/bump-version.sh` → PR opened and merged → retrospective.

## Surprises & Discoveries

- Observation: (spike, 2026-09-01) The harness's per-session inbox socket accepts a message frame from an unrelated shell process. A `claude --bg` probe in permission mode `auto` was idle; a Python one-liner connected to `/tmp/cc-socks/<pid>.sock` and wrote `{"type":"user","message":{"role":"user","content":"PROBE-1 …"}}`. The session started a new turn within seconds and saw the text framed as "Another Claude session sent a message: … This came from another Claude session — not typed by your user", with no sender name (the frame carries none). The probe wrote the witness line `PROBE-1 shell-socket-user-frame 21:09:21Z CROSS-SESSION (sender name not specified in message)` and ended its turn. This is the load-bearing result for `agora send` and the live branch of `agora wake`: a script can ride the native transport; sender identity must travel in the text body.
  Evidence: `claude logs 511214ae` showed the peer-message framing; witness file content above.
- Observation: (research, 2026-09-01) `claude --bg --resume <session-id>` now continues the session "in the background under the same ID, or starts a copy and says so when the session is already running" (`claude --help`, v2.1.257). The daemon substrate's fork-and-purge resume (`claude stop` old turn → `--bg --resume` forks a new id → chain it in `current` → `claude rm` the old one) was built when a resume forked a new session; that whole mechanism, its resume lock, and its "one visible session per daemon" bookkeeping are no longer needed.
- Observation: (research, 2026-09-01) The harness keeps a peer registry at `~/.claude/sessions/<pid>.json` with `name`, `sessionId`, `cwd`, `kind`, `status`, `messagingSocketPath`, `procStart`, and (per the binary's parser) optional `state`, `detail`, `tempo`, `needs`, and `tmux` fields. Records of dead sessions linger, so liveness is pid-alive plus a connectable socket, never record presence alone. Background sessions started with `-n <name>` are not renamed on a name collision (only interactive sessions get the two-word-suffix variant), so a seat's alias is a reliable SendMessage address as long as no other live session on the machine uses the same name.
- Observation: (research, 2026-09-01) Native agent teams (experimental) are one team per session, no nesting, lead fixed for life, in-process teammates not restorable on resume, team directories removed when the lead exits. Those are exactly the properties an institution must not have, so they do not displace agora; their split-pane tmux mode is prior art for the next-phase interactive view.

- Observation: (design review, 2026-09-01) The codex adversarial review of this plan returned six findings (2 critical, 3 high, 1 medium), all real and all adopted (Decision Log entries dated 2026-09-01 "design review"). The critical one reframed the wake design: the board pipeline's successor path and answer relay carry the run's identity (`BOARD_RUN_TOKEN`/`BOARD_RUN_ID`/`BOARD_RUN_FENCE`) as an environment prefix on the resume invocation, so "continue this seat" has two genuinely different meanings — deliver text to the running process, or start a fresh process from my environment — and one verb cannot serve both. Note for a later initiative, not this one: the pipeline's worker bootstrap tells workers to use "the credentials already in your environment", while agora v1's live finding was that the harness Bash tool does not inherit the claude process's environment; whether `BOARD_RUN_*` actually reaches a worker's tools has only ever been asserted by stubs. Recorded, not resolved here.
  Evidence: `_sweep_api.sh` comment "`agora wake` forks a fresh process from OUR env, so the successor credentials ride the invocation or the worker can write nothing"; `review-worker-bootstrap.md:22`.

- Observation: (M1, 2026-09-01) After a same-id `claude --bg --resume`, `claude agents --json --all` holds two rows for one session id — the stopped old job and the new one — so a lookup by session id alone is ambiguous. `agora.py`'s `harness_row(seat)` therefore prefers the row whose short id is the seat's recorded `short` (the latest launch), then a running row, then the last match; `live_state`, `sync`, `attach`, and the wake acknowledgement all resolve through it. Corollary: `resume` must `claude stop` a lingering idle session too, not only a busy or blocked one, or the harness starts a copy.
  Evidence: stub-driven suite section "resume" (copy detection) plus the M1 worker's observation on the real harness listing.
- Observation: (M1) `argparse` cannot parse `agora post <group> --from x "free text"` once a zero-or-more positional has matched; `post` is hand-parsed in `main()` while every other verb uses argparse. The suite's prompt-keyed launch log (`bg-env:` lines keyed by the task text) caught a first-cut bug where the launch argv omitted the task text entirely — a case the old bash suite never pinned.

- Observation: (M4, 2026-09-02) `claude --bg --resume <id>` continues a stopped background session under the same id only when it is passed NO other flags: "background session 4d6ccff7 keeps its own saved options, so the flags you passed started a copy as 74fb1903. Without flags, the same command continues 4d6ccff7 itself." (harness note, v2.1.257). With no flags: "note: woke session 4d6ccff7 with its saved options (--permission-mode, -n, --model)." and the row keeps its short and session id. The first agora `fill --resume` runs therefore always produced a copy (stopped by the M1 copy guard, record untouched, exit 1) because the resume argv carried `-n`/`--permission-mode`/model flags — exactly what `spawn` needs and `resume` must not pass. The old daemon-resume forked on purpose, so it never met this rule.
  Evidence: two copies (3124bd4e, 092d5aa6) reported and stopped by `agora fill --resume`; raw no-flag resume woke 4d6ccff7 in place (`claude agents --json`: id 4d6ccff7, state working, pid 71138).

## Decision Log

- Decision: The unit of the registry is the seat — a named position in a group with a role, filled by zero or one Claude Code session at a time, persisting across sessions. Rejected: node = live session only (the v2 model; a session dying would erase the organisation it belonged to, and "re-fill" would be impossible to express). Deferred: group templates (define an organisation once, instantiate it with fresh sessions) — a natural follow-on once seats exist, not this initiative.
  Date/Author: 2026-09-01, human partner + Claude (grill round 1).
- Decision: One registry, owned by agora, with every background session spawned through agora recorded as a seat — board-pipeline workers included. Rejected: two linked layers (daemon registry for the process, agora for the institution; two list commands with two vocabularies is exactly the incoherence this plan removes).
  Date/Author: 2026-09-01, human partner + Claude (grill round 1).
- Decision: The seat record IS the existing daemon meta file — `<seat-id>.json` at the registry root, seat id = the first session's uuid (or a fresh uuid4 for a seat created vacant), `current` = the session filling it now — extended with `alias`, `group`, `parent`, `addr`, `role`, `brief`, `now`. Rationale: the daemon meta already has the seat shape (stable identity by original uuid, `current` chaining, `role`, `ticket`, `note`), and six board-pipeline scripts read and write that layout directly — they keep working with only a default-path change. Rejected: agora's v2 layout (`groups/<g>/nodes/<alias>.json`) as canonical with the pipeline rewritten to it (six writers, a dozen readers, ~20 test files rewritten; the plan would become a board-pipeline rewrite).
  Date/Author: 2026-09-01, human partner + Claude (grill round 2).
- Decision: Registry root moves to `~/.claude/agora` (env `AGORA_HOME`; `DAEMON_HOME` honored as a fallback name for the same root because the pipeline scripts and their tests use that variable). First run migrates the old root by moving its contents and leaving `~/.claude/orchestrating-daemons` as a symlink to the new root, so anything still holding the old path (a live worker's bootstrap-log path, a stale prose reference) keeps resolving. Rejected: keeping the path named after a deleted skill; a copy-based migration (two roots drift).
  Date/Author: 2026-09-01, Claude (grill round 2 silent decision, confirmed by the human partner's acceptance of the round).
- Decision: Implementation is a single stdlib-only Python module `skills/agora/scripts/agora.py` behind a two-line bash launcher `skills/agora/scripts/agora`, plus a small sourced shell helper `skills/agora/scripts/lib.sh` for the one consumer that sources library functions. Rationale: the daemon substrate was already ~60% Python inside bash heredocs, the registry's flock/JSON/subprocess work is native to Python, `jq` stops being a dependency, and the next-phase interactive view (curses, stdlib) imports the same module. Tests stay bash and drive the CLI. Rejected: staying bash+jq+heredocs (~1200 lines with the JSON logic scattered; a language switch would land in the middle of the TUI phase instead).
  Date/Author: 2026-09-01, human partner + Claude (grill round 2).
- Decision: Canonical term is `seat`; the session filling it is the agent; topology nodes are seats. Rejected: `node` (graph vocabulary, says nothing about persistence), `post` (collides with board posts), `member` (a person word).
  Date/Author: 2026-09-01, human partner + Claude (grill round 2).
- Decision: `skills/orchestrating-daemons/` is deleted outright; its scripts become agora verbs, its doctrine (where work goes, permission mode `auto` and never `--dangerously-skip-permissions`, worktree isolation for code-writing seats, spawn-prompt hygiene, long turns, blocked-on-AskUserQuestion handling, never hand-drive a pipeline worker) is absorbed into `skills/agora/SKILL.md`, and every in-repo consumer is repointed. No compatibility shims at the old paths: this is a personal fork with no external consumers. The legacy codex-CLI worker scripts (`codex-spawn.sh`, `codex-resume.sh`, `_codex_lib.sh`) are deleted too; the six `engine: codex` records in the live registry (all retired/idle since July) stay readable in `agora list` and can be removed with `agora remove`.
  Date/Author: 2026-09-01, human partner + Claude (grill round 1).
- Decision: The fork-based resume is retired. `agora wake <seat> <msg>` delivers to a live session by writing a frame to its inbox socket (native delivery: an idle session starts a new turn, a busy one reads it between tool calls), and to a stopped session by `claude --bg --resume <current>` which continues under the same id. No `claude stop` of the old turn, no purge, no `current` chain in the normal case; `current` changes only if the harness reports a different id after resume (a "copy" was started because the session was already running), which the plan records as a Surprise if it ever happens. A per-seat resume lock (flock on `<seat-id>.resume.lock`, held for the resume path only) stays, because two concurrent resumes of a stopped session would start a copy.
  Date/Author: 2026-09-01, Claude (grill round 2).
- Decision: `agora send` exists again, shell-side only, riding the native socket; it refuses when the target has no live socket (exit 4, pointing at `agora wake`). Sender identity travels in the text body as a first line `[agora message from <from>]` because the socket frame carries no sender name. Inter-agent messaging stays the native SendMessage tool (its frames carry the sender's session name). Rejected: a `peer_message`-shaped frame reverse-engineered from the binary (undocumented; the `type:"user"` frame is the one the harness documents for scripts).
  Date/Author: 2026-09-01, Claude (spike result).
- Decision: The `status` field keeps its mirror semantics (`working`, `blocked`, `idle`, `error`, `retired`, plus the judgment states `done` and `awaiting-human`) because the board pipeline dedupes and counts lane slots on it; `agora sync` is the reconciliation verb (the former `daemon-finalize.sh`) and prints the same five-word vocabulary (`noop`, `live`, `absent`, `idle`, `error`) the pipeline switches on. Views additionally compute a harness-derived `live` state at read time and never write it. Rejected: deriving status at read time everywhere (the pipeline's `_liveness` paths would all change in this initiative).
  Date/Author: 2026-09-01, Claude.
- Decision: The spawn banner keeps the substring `[<short> / <uuid>]` because three pipeline scripts parse it with the sed pattern `.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*`. Default is no-wait (register as soon as the uuid materialises, return); `--wait` blocks to the turn's end and prints `--- reply ---`. `--no-wait` is accepted and ignored so existing call sites keep working until repointed.
  Date/Author: 2026-09-01, Claude.
- Decision: Seats spawned without an explicit `--group` are filed under a group derived from the working directory: the basename of `git rev-parse --show-toplevel` when cwd is in a git repository, else the directory's basename, else `fleet`. Board-pipeline workers therefore group by repository without the dispatchers learning about groups. The agora preamble is prepended to the task only when `--group` is explicit, so pipeline workers' rendered protocols are unchanged.
  Date/Author: 2026-09-01, Claude.
- Decision: Two self-description fields on a seat: `now` (one line, written by the agent itself with `agora status <seat> "…"`) and `note` (written by the orchestrator with `agora mark`). The earlier idea of a Stop hook that updates status is shelved: hooks fire inside the turn and cannot summarise it, while the harness already tracks liveness; if the harness's session record exposes an activity `detail` for background sessions, views show it opportunistically.
  Date/Author: 2026-09-01, Claude.
- Decision: (design review, 2026-09-01) Two continuation verbs, not one. `agora resume <seat> <msg> [--wait]` is process-level: it stops a live turn (`claude stop <short>`, exactly as the old `daemon-resume.sh` did) and runs `claude --bg --resume <current>` so the continuation is a fresh process that inherits the invoking environment — the board pipeline's answer relay and successor path prefix that invocation with `BOARD_RUN_TOKEN`/`BOARD_RUN_ID`/`BOARD_RUN_FENCE`, and a socket frame cannot change a running process's environment. `agora wake` stays the interactive verb (socket when live, resume when stopped). Pipeline call sites use `resume --wait`. Rejected: one `wake` verb serving both (codex adversarial review finding 1: the live-socket branch silently drops the successor run identity).
  Date/Author: 2026-09-01, Claude, adopting codex adversarial-review F1.
- Decision: (design review) Migration is an atomic directory rename, not an entry-by-entry move: when the old root is a real directory, agora renames any existing `~/.claude/agora` aside, renames `~/.claude/orchestrating-daemons` to `~/.claude/agora`, moves the v2 `groups/` back in, and only then creates the symlink at the old path; a legacy writer sees either the whole old tree or the whole new one. Every pipeline entrypoint runs `"$AGORA_CLI" migrate` right after its preflight so a board sweep, answer relay, or dispatch is never the first process to look at an empty new root. Rejected: migration only on agora verbs (F2: the pipeline scans the registry directly and could dedupe against an empty fleet).
  Date/Author: 2026-09-01, Claude, adopting F2.
- Decision: (design review) `wake --wait` requires evidence of delivery before it accepts an idle state: the frame's first line carries a message id, and the watcher first waits (bounded, `AGORA_ACK_TIMEOUT`, default 120s) for that id to appear in the target's transcript or for the session to report busy, then waits for idle. No evidence → exit 1, nothing printed as a reply. Rejected: polling straight to idle (F3: the target is idle before delivery, so the wait would return the previous reply immediately).
  Date/Author: 2026-09-01, Claude, adopting F3.
- Decision: (design review) A per-seat lifecycle lock (`$AGORA_HOME/locks/<group>__<alias>.lock`, flock) is held from the availability check through record commit in `spawn`, `fill`, `seat add`, and through the process start in `resume`; a resume whose harness row reports a different session id than `current` (a copy — the session was running after all) stops that copy and exits 1 instead of adopting it. Rejected: adopting the copy (F4: two live processes answering to one address).
  Date/Author: 2026-09-01, Claude, adopting F4.
- Decision: (design review) `spawn`, `fill`, and `seat add` refuse (exit 4) when a live harness session already answers to the alias — checked against the harness peer registry, so non-agora sessions count too — unless `--session` registers that very session. The v2 warning is replaced by a refusal because the registry can now see the machine-wide namespace. Rejected: group-qualified harness names (F5's alternative; it would make every SendMessage address longer and break the alias-is-the-address rule agents rely on).
  Date/Author: 2026-09-01, Claude, adopting F5.
- Decision: (design review) Legacy `engine: codex` records are marked `retired` by migration, and `wake`, `resume`, and `fill` refuse them (exit 4) before any side effect; `board-answer.sh` checks the bound record's engine before it transitions the ticket. Rejected: leaving them wakeable (F6: two such records still carry a ticket, and a relay would unpark the ticket and then fail to resume a codex thread through claude).
  Date/Author: 2026-09-01, Claude, adopting F6.
- Decision: (M1) Migration's one-time pass marker is `$AGORA_HOME/.migrated-v3` and covers both group stamping and codex retirement in one pass; `topology` emits both `seats` and `nodes` (one release of v2-preamble compatibility) and accepts `--json` as a no-op; the wake frame carries its message id even without `--wait`, so a receiver's transcript always shows which shell send produced a turn.
  Date/Author: 2026-09-01, M1 worker; accepted by the orchestrator.
- Decision: (M4) The resume launch is exactly `claude --bg --resume <current> <msg>` — no name, permission-mode, model, settings, effort, or worktree flags — because a background session keeps its saved options and any flag makes the harness start a copy. `resume` and `fill --resume` accept `--model/--settings/--effort` for argv compatibility, ignore them with a one-line stderr note, and leave the recorded fields untouched; changing those options means `fill` without `--resume` (a fresh session). The gateway env scrub still applies on the plain route. The banner text "started a copy as" is treated as a copy signal in addition to the uuid comparison.
  Date/Author: 2026-09-02, Claude (M4 live proof).
- Decision: (exit gate, 2026-09-02) The codex code-review panel (one sweep, five derived lenses, one verifier; 18 minutes) returned 13 P1 / 15 P2 / 1 P3 confirmed findings; all were verified against the code and all adopted in one fix wave (two workers: agora.py + tests, pipeline defaults). The two that reverse earlier decisions: (a) pipeline entrypoints now FAIL CLOSED when `agora migrate` fails (the M2 brief said `|| true`; a half-migrated registry must never read as an empty fleet); (b) `spawn` on an existing seat re-fills it when the seat is vacant, stopped, gone, or retired (the M1 build refused every existing alias, which broke the pipeline's retire-then-respawn on deterministic worker names). Notable others: `run_bearer` redacted from every model-visible JSON/table; the migration cutover takes a machine-wide lock and recovers a stranded aside directory; the watcher's final writes (`--wait`, `sync`) are conditional on the record not having moved; the lifecycle lock is keyed by harness name (machine-wide) and also taken by retire/remove; `derive_group` uses the owning repository (a linked worktree's toplevel is the worktree directory); legacy records with no `current` key resume from their uuid; v2 node conversion never deletes what it did not convert; spawn launches under the advertised addr; an invalid `--cwd` is refused instead of silently replaced by HOME.
  Date/Author: 2026-09-02, Claude.
- Decision: (exit gate round 2, 2026-09-02) Panel round 2 (run `wf-mtj9n3b3-omv07r`, 21 min) returned 14 P1 / 11 P2, all verified; 24 adopted in a second fix wave, 1 moot. The blocking one: the re-fill banner printed the NEW session uuid instead of the record filename, so the pipeline's bind-by-filename would never have matched a deterministic respawn — a bug the hermetic suites could not see because the pipeline tests stub agora; an integration-shaped assertion (banner bracket == record filename) now pins the contract. Reversals of round-1 adoptions: resume of a seat whose cwd vanished now REFUSES (round 1 said warn-and-run-from-HOME; an unattended auto-mode worker in the wrong directory is worse than a refusal), and migration no longer signals legacy codex pids at all (identity_local accepts missing host/boot fields, so the kill could hit a recycled pid). Structural adoptions: a per-record `gen` counter guards every late write (finalizers, sync, wake) so a retire can never be undone by a stale snapshot; `sync` and `wake` take the lifecycle lock; the lock is keyed by the harness address; one registry-root precedence rule (AGORA_HOME, then DAEMON_HOME) in the CLI and every pipeline default, exported to children; migrate runs before every direct registry read via issue-tracker's `_lib.sh`; re-fills keep `attempts` and a bounded `history` so the pipeline's outage streak survives the one-record-per-alias model; `meta get` refuses secret-shaped fields; registry root and records tightened to 0700/0600; migration dedupes historical same-alias records (the live registry had four `review-pr-470`).
  Date/Author: 2026-09-02, Claude.
- Decision: (round 2, pipeline worker) The migrate preflight that issue-tracker's `_lib.sh` runs for the direct-reading board scripts is gated on the cutover actually being pending (the legacy root still a real directory) rather than unconditional: `agora migrate` takes the registry lock, and running it at every source would make read-only board scripts acquire the write lock — and deadlock a caller that already holds it (the lock-wait race test constructs exactly that). The gate is one `stat`; every CLI-mediated path still runs the full implicit migrate. Likewise `_wt_occupied` frees a worktree only for a terminated row that belongs to an *unregistered* previous occupant; a parked (non-retired) worker's stopped row keeps occupying its worktree because that worktree is its resume context (a pinned assertion). Both accepted by the orchestrator.
  Date/Author: 2026-09-02, M2 worker; accepted.
- Decision: The six board-pipeline scripts that write registry fields directly (with their own flock-and-rewrite) are left as they are; `agora meta get|set` exists for new code and tests, and consolidating the existing writers behind it is logged as follow-on debt. Rationale: their invariants (flock `.metalock`; recreate at the existing mode, 0600 when `run_bearer` is present; unlink `.tmp` before create) are preserved by agora's own writer, so coexistence is safe, and rewriting them is a board-pipeline change with its own risk.
  Date/Author: 2026-09-01, Claude.

## Outcomes & Retrospective

Pending — written at finish.

## Context and Orientation

This repository is `doperpowers`, a Claude Code plugin: skills (instruction
documents plus helper scripts) that load into coding-agent sessions. There is
no application build; the product is `skills/`. Tests are bash scripts under
`tests/`, run directly. `scripts/lint-shell.sh --all` is the shellcheck gate.
Versions across manifests are bumped only with `scripts/bump-version.sh`.

Terms used in this plan:

A **session** is one running `claude` process with its conversation. A
**background session** is one started with `claude --bg`: it runs detached
from any terminal, appears in `claude agents` and `claude agents --json`, can be
attached to with `claude attach <short-id>`, stopped with `claude stop`, and
deleted with `claude rm`. The harness supervisor gives each background session
an 8-hex **short id** (shown in listings) and every session a **session id**
(a uuid, also the name of its transcript file under
`~/.claude/projects/<project>/<uuid>.jsonl`). The older word **daemon** in this
repository means a background session driven by scripts; this plan retires the
word along with the scripts.

The **harness** is Claude Code itself. Two harness facts this plan relies on:
`claude agents --json --all` prints a JSON array of sessions with fields `id`
(short), `sessionId`, `name`, `cwd`, `pid`, `kind` (`background` or
`interactive`), `state` (background: `working`, `blocked`, `done`, `failed`,
`stopped`) and `status` (`busy`/`idle`); and every live session with
cross-session messaging binds an **inbox socket**, a unix domain socket at
`/tmp/cc-socks/<pid>.sock` (or `/tmp/cc-socks-<uid>/`), and registers itself in
the **peer registry** `~/.claude/sessions/<pid>.json` (fields include `name`,
`sessionId`, `cwd`, `kind`, `status`, `messagingSocketPath`, `procStart`).
Writing one line `{"type":"user","message":{"role":"user","content":"<text>"}}`
to that socket delivers `<text>` to the session as a peer message. Between
sessions, agents use the harness's own `SendMessage` tool addressed by session
name; `-n <name>` on `claude --bg` sets that name.

A **seat** is agora's unit: a JSON record at `$AGORA_HOME/<seat-id>.json`. A
**group** is a named set of seats with a communal **board**
(`$AGORA_HOME/groups/<group>/board.jsonl`, long-form markdown posts). A seat's
**alias** is its name within its group (unique per group) and, for a seat agora
spawned, also the harness display name of its session; its **addr** is the name
other sessions pass to SendMessage (defaults to the alias; an interactive
session registers with `--addr <its harness name>`). A seat's **parent** is the
alias of the seat that spawned it (the spawn tree is the topology). The
**preamble** is a text block rendered from `skills/agora/references/spawn-preamble.md`
and prepended to a spawned seat's task, telling the agent its seat, group,
parent, and the agora commands to use.

The **board pipeline** is the ticket-driven worker system in
`skills/issue-tracker/`, `skills/executing/`, and `skills/qa-loops/`: scripts
that read a GitHub-issues board, spawn implement and review workers as
background sessions, bind them to tickets, sweep for stuck ones, and relay the
human's answers to parked workers. It treats the registry as a shared
namespace: besides the fields the substrate writes, it writes its own
(`ticket`, `board`, `run_id`, `fence`, `run_bearer`, `bind_confirmed`,
`run_ended_at`, `lane`, `role`, `nonce`, `parent_pin`, `closure_package`,
`retired_from`, `sweep_recoveries`, `relayed_comment`) under the shared flock
file `$AGORA_HOME/.metalock`, and keeps sibling directories there
(`board-claims/`, `board-suppress/`, `surface-locks/`, `sweep/`) plus loose
files (`sweep.log`, `.sweep-api.lock`, `board-sweep.lock`,
`<name>.bootstrap.log`, `<name>.dispatch.lock`, `<name>-control.*`,
`.surfaces-fetch-stamp`). None of that moves except the root directory.

Files this plan touches, by area:

The substrate to fold in: `skills/orchestrating-daemons/SKILL.md` and
`scripts/{_lib.sh,daemon-spawn.sh,daemon-resume.sh,daemon-reply.sh,daemon-list.sh,daemon-mark.sh,daemon-retire.sh,daemon-finalize.sh,codex-spawn.sh,codex-resume.sh,_codex_lib.sh}`,
tested by `tests/orchestrating-daemons/{test-daemon-scripts.sh,test-codex-scripts.sh}`
(the former builds a stub `claude` on PATH that mimics the bg banner,
`agents --json`, transcript files, and `stop`; reuse that technique).

The CLI to grow: `skills/agora/scripts/agora` (bash+jq today, 346 lines),
`skills/agora/SKILL.md`, `skills/agora/references/spawn-preamble.md`, tested by
`tests/agora/run-agora-tests.sh` (34 assertions today against a temp
`AGORA_HOME`).

Pipeline call sites (line numbers as of the branch point; re-grep before
editing): `skills/executing/scripts/execute-dispatch.sh` (`DAEMON_SCRIPTS`
seam :53, `DAEMON_HOME` :54, preflight :81, banner regex :93, spawns :347 :844
:856, retires :135 :363 :871); `skills/qa-loops/scripts/review-dispatch.sh`
(seam :136, `DAEMON_HOME` :137, sources `_lib.sh` :138-139, preflight :157,
`_identity_local` :308 :1126, finalize :839 :1134, spawns :927 :939, retire
:323); `skills/issue-tracker/scripts/_sweep_api.sh` (`DAEMON_HOME` :90, seam
:91, finalize :407, resumes :694 :1300, spawn :1381, banner :1385, retire
:1421, seam re-export :1707); `skills/issue-tracker/scripts/board-sweep.sh`
(seam :80, `DAEMON_HOME` :81, finalize :257 :335 :649, `nohup` resume :247,
retires :275 :298 :318 :338); `skills/issue-tracker/scripts/board-answer.sh`
(seam :120-121, finalize :140, retire :142, engine branch + resumes :294-297,
error prose :191); registry defaults in `skills/issue-tracker/scripts/_lib.sh:50`
and `skills/issue-tracker/scripts/board-gc.sh:51`; error prose in
`skills/issue-tracker/scripts/board-transition.sh:156-157`.

Pipeline tests that stub the substrate through the `DAEMON_SCRIPTS`
environment variable: `tests/executing/test-execute-dispatch.sh`,
`tests/qa-loops/test-review-dispatch.sh`, `tests/issue-tracker/test-board-scripts.sh`,
`tests/issue-tracker/test-board-sweep.sh`, `tests/claude-code/board-api/{test-answer.sh,test-dispatch-claim.sh,test-review-dispatch-claim.sh,test-sweep-renew-relay.sh,test-sweep-resume.sh}`,
`tests/claude-code/board-api/integration/{drill-lib.sh,test-transcript-diff.sh}`.
Two more pin literals: `tests/executing/test-protocol-content.sh:182` (asserts
`skills/issue-tracker/SKILL.md` mentions `daemon-spawn.sh` and
`DAEMON_CLAUDE_SETTINGS`) and `tests/qa-loops/test-bootstrap-parity.sh:163`
(asserts the worker bootstrap names `~/.claude/orchestrating-daemons/…bootstrap.log`).

Prose that names the substrate outside its own directory:
`skills/issue-tracker/SKILL.md:243,252,270`, `skills/qa-loops/references/operation-manual.md:8,29`,
`skills/qa-loops/references/review-worker-bootstrap.md:153`,
`skills/issue-tracker/references/sweep-setup.md:79,82`, `skills/execplan/SKILL.md:35`,
`skills/agora/SKILL.md:81-93`, `skills/agora/references/spawn-preamble.md:30`,
`.claude-plugin/plugin.json:20` (a keyword), `infra/worker-host/env.example:34`,
`infra/worker-host/cloud-init.yaml:17`, `docs/doperpowers/TECH-DEBT.md:69`.
`tests/skill-links/test-cross-doc-refs.sh` fails on any `doperpowers:<name>`
reference whose skill directory does not exist, so every
`doperpowers:orchestrating-daemons` mention must go in the same commit that
deletes the directory.

Live registry at the branch point (for migration testing): 36 records under
`~/.claude/orchestrating-daemons/` (16 idle, 13 retired, 5 done, 2 working),
6 of them `engine: codex`, 13 carrying `ticket`, 2 carrying `role`, 1 carrying
`agora_group`; agora v2 state under `~/.claude/agora/groups/{demo,dogfood}/`
(throwaway).

## Plan of Work

### M0 — plan, branch, design review

Work happens in the worktree at `.claude/worktrees/agora-native` on branch
`worktree-agora-seats`, created from `origin/main` at `a1d580c5`. Commit this
file, then dispatch a design-level adversarial review of it through the
codex-companion skill's `adversarial-review` verb (model `gpt-5.6-sol`, effort
`xhigh`, run in a background shell with stderr to a scratch file, focus text
naming this plan's path and asking for failure modes in the registry contract,
the wake/send semantics, and the pipeline repoint). Start M1 while it runs;
fold verified findings into this plan and M1/M2 before M2 begins.

### M1 — the Python core and its tests

Create `skills/agora/scripts/agora.py` (Python 3, stdlib only: `json`, `os`,
`fcntl`, `socket`, `subprocess`, `uuid`, `glob`, `re`, `argparse`, `datetime`,
`shutil`, `time`). Replace the bash `skills/agora/scripts/agora` with a
launcher of the form `exec python3 "$(dirname "$(readlink -f "$0")")/agora.py" "$@"`
(mode 755; `readlink -f` because the pipeline may resolve the seam through a
relative path). Add `skills/agora/scripts/lib.sh`, a sourced helper exporting
`AGORA_HOME` (default `$HOME/.claude/agora`, honoring `DAEMON_HOME` when set),
`DAEMON_HOME` (same value, for consumers that still spell it that way),
`DAEMON_HOST`, `DAEMON_BOOT_ID`, `DAEMON_TIMEOUT` (default 18000), `_now`,
`_identity_local`, and `_pid_alive`, ported verbatim from the daemon `_lib.sh`
with their comments.

Inside `agora.py`, organise the module in sections: registry (paths, the
locked read-modify-write `meta_set` preserving the mode rules, `meta_get`,
`resolve_seat` accepting a seat id, a seat-id prefix, a current short id, a
current session id, `group/alias`, or a bare alias when unique), harness
(`agents_json()` calling `claude agents --json --all`, `peer_records()` reading
`~/.claude/sessions/*.json`, `live_state(seat)` combining them into one of
`busy`, `idle`, `blocked`, `stopped`, `gone`, `vacant`, `transcript_path`,
`transcript_reply` including the pending-AskUserQuestion rendering and the
blocked-on-harness-prompt marker, `gateway_env_keys` reading the top-level
`env` keys of `~/.claude/clodex-settings.json` never including `PATH`),
migration, spawn/fill/wake/send, sync/mark/status/retire/remove, views, board,
and the argparse dispatcher.

The registry root is `$AGORA_HOME` (fallback `$DAEMON_HOME`, then
`~/.claude/agora`). Every command first runs the migration check (also
exposed as the verb `agora migrate [--quiet]`, which the pipeline entrypoints
call after their preflight): if the default root is in use and
`~/.claude/orchestrating-daemons` exists as a real directory, rename any
existing `~/.claude/agora` aside (`~/.claude/agora.v2-<timestamp>`), rename the
old root to `~/.claude/agora` (one atomic `rename`, so a concurrent legacy
writer sees either the whole old tree or the whole new one), move the aside
directory's `groups/` back in, then create the symlink at the old path and
print one line to stderr. Mark every `engine: codex` record `status: retired`
(they are unwakeable through claude). Then, if `groups/<g>/nodes/*.json` exist (v2 layout), convert
each into a seat record (seat id = the node's `session` if it looks like a
uuid, else `uuid.uuid4()`; `alias`, `parent`, `addr`, `brief` from `desc`,
`cwd`, `group` = the directory name, `status` = `retired`, `current` = the
session) and remove the `nodes/` directory. Finally, stamp `group` on any seat
record lacking it, derived from its `cwd` (git toplevel basename, then
directory basename, then `fleet`). Migration is idempotent: a symlink at the
old path means it already happened; conversion and stamping only touch records
missing the fields.

Seat record fields written by agora: `uuid` (the seat id), `current`, `short`,
`name`, `alias`, `group`, `parent`, `addr`, `role`, `brief`, `task`, `now`,
`note`, `cwd`, `worktree`, `model`, `settings`, `effort`, `status`, `host`,
`boot_id`, `created`, `updated`, `turns`, `pending_short` (failure path only).
Read-time fallbacks, applied by one `load_seat` function so no view ever prints
`null`: `alias ← name`, `addr ← alias`, `group ← "fleet"`, `parent`, `role`,
`brief`, `now`, `note` ← empty string. Names are validated as
`[A-Za-z0-9._-]{1,64}` and never `.` or `..`; `human` is reserved and never a
seat. `addr` is a harness session name and is not name-validated.

`agora spawn <alias> <task> [--group G] [--parent P] [--role R] [--brief B]
[--cwd C] [--worktree W] [--model M] [--settings S] [--effort E] [--addr A]
[--wait] [--no-wait]`: validates; takes the seat lifecycle lock (flock on
`$AGORA_HOME/locks/<group>__<alias>.lock`, held through record commit) so two
concurrent spawns cannot both pass the checks; refuses if `<group>/<alias>`
already holds a seat that is not vacant, retired, or dead (`agora fill` is for
those); refuses (exit 4) if a live harness session — any peer record under
`~/.claude/sessions/` whose pid is alive — already answers to the alias,
because that name is the SendMessage address and the harness does not rename
background sessions on collision;
renders the preamble (placeholders `{{GROUP}}`, `{{ALIAS}}`, `{{PARENT}}`,
`{{AGORA_CLI}}` = absolute path of the launcher) only when `--group` was given
and prepends it plus `brief` to the task; takes `--settings`/`--effort` from
`DAEMON_CLAUDE_SETTINGS`/`DAEMON_CLAUDE_EFFORT` when the flags are absent;
scrubs the gateway env keys when the settings route is plain and always
`RUNNER_TRACKING_ID`; runs `claude --bg --permission-mode auto -n <alias>
[--worktree <w>] [--model] [--settings] [--effort] <task>` in `cwd` with stdin
from `/dev/null`, strips ANSI, parses `backgrounded · <short>`; writes the seat
record immediately (status `working`, `current` empty) so the seat exists
during its first turn; polls `claude agents --json --all` every 2s up to
`AGORA_UUID_POLL` (default 30) times for a row with that short and a non-empty
`sessionId`, then stores `uuid` (if the seat id was fresh, the record file is
named after this session uuid — write it under that name and remove the
provisional file), `current`, `cwd` (the actual cwd from the row, which is the
worktree path when `--worktree` was used), `host`, `boot_id`; if the row's
turn already ended, records the reply and the true status. Prints
`seat spawned: <alias>  [<short> / <uuid>]  group=<g>  status=<s>  (reply: agora reply <short>)`.
With `--wait`, instead polls to a terminal state (`done`/`blocked`/`failed`/`stopped`,
normalising `state=working, status=idle` to done) for up to `DAEMON_TIMEOUT/2`
iterations, records the reply, and prints `--- reply ---` followed by the reply
text; a watcher timeout leaves status `working` and exits 1 with a note. A
launch that prints no short id exits 1 and writes no record.

`agora seat add <group> <alias> [--role R] [--brief B] [--parent P] [--addr A]
[--session <uuid>]` creates a vacant seat, or registers an existing session
(typically the interactive orchestrator) as a seat with `current` = that
session; `agora join` is an alias of it with v2's argument order
(`join <group> <alias> [--parent] [--desc] [--session] [--addr]`, `--desc`
mapping to `brief`), kept because long-lived sessions still carry v2 preambles.

`agora fill <seat> <task> [--resume] [--model M] [--settings S] [--effort E]`:
for a seat whose live state is `vacant`, `stopped`, or `gone`, spawns a fresh
session with the same alias, cwd, worktree, group, and preamble rules as
`spawn` (the seat id stays; `current` becomes the new session; `turns` resets
to 1); with `--resume`, instead continues the recorded `current` session
exactly as `wake` does for a stopped session. Refuses on a `busy`/`idle`/`blocked`
seat (it is filled — use `wake` or `send`).

`agora resume <seat> <msg> [--wait] [--model M] [--settings S] [--effort E]`
is the process-level continuation the board pipeline uses (its answer relay
and successor path prefix the call with `BOARD_RUN_TOKEN`/`BOARD_RUN_ID`/
`BOARD_RUN_FENCE`, which only a fresh process can inherit): it refuses
`engine: codex` records and seats with no `current` (exit 4), takes the
per-seat lifecycle lock, runs `claude stop <short>` if the session is live
(what the old `daemon-resume.sh` did), then `claude --bg --resume <current>
--permission-mode auto -n <alias> [--model] [--settings] [--effort] <msg>` in
the seat's cwd (same env scrub as spawn), parses the banner, and polls for the
uuid. If the harness reports a session id other than `current`, a copy was
started because the session was still running: the copy is stopped, the record
is left untouched, and the command exits 1. Status becomes `working`; `--wait`
polls that turn to its end as `spawn --wait` does and prints `--- reply ---`.

`agora wake <seat> <msg> [--wait] [--from F]` is the interactive verb: it
resolves the seat's `current` session; if its peer record's pid is alive and
its socket accepts a connection, it writes the frame with content
`[agora wake from <F|human> id=<8 hex>]\n<msg>` and returns (status `working`,
`updated` stamped); otherwise it behaves exactly like `resume`. With `--wait`
in the socket branch it first waits — bounded by `AGORA_ACK_TIMEOUT`, default
120s — until the message id appears in the target's transcript or the harness
row shows the session busy, then waits for idle and prints `--- reply ---`;
without that evidence it exits 1 and prints no reply (the target was idle
before delivery too, so "idle" alone proves nothing). A seat with no `current`
exits 4 pointing at `agora fill`.

`agora send <seat-or-addr> <msg> [--from F]`: socket branch only; resolves a
seat (as above) or, failing that, a live peer record whose `name` equals the
argument; content `[agora message from <F|human>]\n<msg>`; exits 4 with
`not live — use: agora wake <seat> "<msg>"` when there is no connectable socket.

`agora reply <seat>` prints the seat header (`<alias>  [<seat-id>]  group=…
status=… turns=…`), `task:` (first line only, the full task is in the record),
`--- latest reply ---`, and the reply: for status `working` the live
transcript's last assistant text, else the recorded reply file, falling back
to the transcript when the file is empty.

`agora sync [<seat>] [--all]`: for one seat prints exactly one word — `noop`
(status not `working`/`blocked`), `live` (harness row shows a running or
prompt-blocked turn, or an unknown new state), `absent` (no row for `current`;
record untouched), `idle` (row shows the turn ended, including the lingering
`state=working|blocked, status=idle` shapes; reply recorded, status `idle`),
`error` (row `failed`/`stopped`; reply recorded, status `error`). `--all`
applies it to every `working`/`blocked` seat and prints `alias word` lines.

`agora mark <seat> <status> [note]` stamps a judgment status and note. `agora
status <seat> <one line>` writes `now`. `agora retire <seat> [--purge]` runs
`claude stop <short>` when the record's host/boot identity is local, sets
status `retired`, prints the still-resumable hint and the branch note for a
worktree'd seat; `--purge` also deletes the record, reply, and err files (never
the transcript, worktree, or branch). `agora remove <seat>` (alias `leave
<group> <alias>`) stops and deletes the record regardless of status.

Views: `agora list [group] [--status S] [--json]` prints
`ALIAS GROUP ROLE STATUS LIVE SHORT ADDR NOW` (NOW falls back to the first 46
characters of the latest reply), newest `updated` first, `(no seats)` when
empty; `--json` prints the loaded seats with `live`. `agora view <group>`
prints `agora group: <g>`, the spawn tree with `├──`/`└──` glyphs and
accumulating child prefixes, each row `alias [role] · live · now`, a
`(dangling — parent 'x' unknown)` section for orphans, and the board summary
line. `agora topology <group> [--json]` prints
`{"group":…, "seats":[…each loaded seat plus live…], "edges":[{"from":parent,"to":alias}…]}`
(the key is `seats`; the v2 key `nodes` is also emitted with the same array for
one release so v2 preambles keep parsing). `agora groups` prints
`<group> <n> seats (<m> live)  last post: <ts>`. `agora attach <seat>` execs
`claude attach <short>` when the seat is live and the terminal is a TTY, else
prints the command.

Board: `agora post <group> [--from F] [--title T] [text…|stdin]` and `agora
board <group> [-n N|--id I] [--json]` port unchanged from v2 (append under a
mkdir spinlock, `<agora-post>` envelopes with the closing-tag neutralisation
and `@html`-style attribute escaping, nudge list of the other seats' addrs
printed after a post; `--from` must be `human` or a seat in the group).
`agora meta get <seat> <field>` and `agora meta set <seat> <field> <value>…`
expose the locked writer. `listen` and `log` still refuse with a pointer at
SendMessage/`agora send`; `help` prints the usage.

Tests: rewrite `tests/agora/run-agora-tests.sh` as one hermetic suite. It sets
`HOME` and `AGORA_HOME` to temp dirs, puts a stub `claude` first on PATH (port
`tests/orchestrating-daemons/test-daemon-scripts.sh`'s stub: `--bg` prints a
coloured `backgrounded · <short>` banner and records argv; `agents --json
--all` prints rows from a state dir with controllable state/status; `--resume`
records the id and, by default, reuses it; `stop`/`rm` log calls; transcripts
are written under `$HOME/.claude/projects/stub/<uuid>.jsonl`), and starts a
tiny Python unix-socket server plus a fabricated `$HOME/.claude/sessions/<pid>.json`
record for the socket cases. Cover at least: migration (old root with a real
meta and a v2 nodes dir → symlink, seat records, `group` stamped, `null` never
printed); spawn default no-wait banner shape and record fields; preamble only
with explicit `--group`; gateway env taken from `DAEMON_CLAUDE_*` and scrubbed
on the plain route (PATH survives); `--wait` reply recording and the
AskUserQuestion rendering; wake socket branch (frame content and `from`
line), wake resume branch (`--resume <current>` argv, same-id continuation,
copy detection when the stub returns a new id), resume lock refusal; send
refusal on a dead seat (exit 4) and success on a live one; fill fresh vs
`--resume`; sync's five words including both lingering shapes; retire/purge/
remove side effects and the worktree note; list/view/topology on a
three-level tree including a dangling parent and a v1-shaped record; board
post/board/--id/nudge/envelope escaping; name validation, traversal segments,
reserved `human`; addr collision warning across groups; umask 077 on created
files. Run `scripts/lint-shell.sh --all` for the launcher and `lib.sh`.

### M2 — repoint the board pipeline

In each of the five scripts, replace the `DAEMON_SCRIPTS` seam with
`AGORA_CLI="${AGORA_CLI:-$(cd "<skill-dir>/../agora/scripts" && pwd)/agora}"`
and the preflight with `[ -x "$AGORA_CLI" ]`; change the `DAEMON_HOME` default
literal to `$HOME/.claude/agora` (keep the variable name); replace calls:
`daemon-spawn.sh --no-wait <n> <p> <cwd> <wt> <model>` →
`"$AGORA_CLI" spawn <n> <p> --cwd <cwd> --worktree <wt> --model <model>`
(gateway env variables stay on the command prefix as today; empty `<wt>` or
`<model>` values are simply omitted); `daemon-retire.sh <id>` → `"$AGORA_CLI"
retire <id>`; `daemon-finalize.sh <id>` → `"$AGORA_CLI" sync <id>`;
`daemon-resume.sh <id> <msg>` → `"$AGORA_CLI" resume --wait <id> <msg>`
(the process-level verb: the callers' `BOARD_RUN_*` prefixes must reach a
fresh process; this also preserves their blocking expectation and the
`DAEMON_TIMEOUT` override — pipeline scripts never call `wake`). Right after
each script's `[ -x "$AGORA_CLI" ]` preflight, add
`"$AGORA_CLI" migrate --quiet >/dev/null 2>&1 || true` so no pipeline process
is ever the first to look at an empty new root. In `review-dispatch.sh`, source
`skills/agora/scripts/lib.sh` instead of the daemon `_lib.sh` (update the
shellcheck source directive). In `board-answer.sh`, delete the `engine` branch,
always `exec "$AGORA_CLI" resume --wait`, and before any board write refuse a
bound record whose `engine` is `codex` (`"$AGORA_CLI" meta get <uuid> engine`),
pointing the human at `agora retire` and the fresh-dispatch path. Update the human-facing error prose in `board-transition.sh`
and `board-answer.sh` to name `agora list`, `agora wake`, `agora retire`. In
`_sweep_api.sh:1707`, pass `AGORA_CLI` where it re-exported `DAEMON_SCRIPTS`.

In the eleven test files, replace the stub directory of four scripts with one
stub executable named `agora` whose first argument selects the behaviour
(`spawn` prints the real banner with the bracket form and honours `--wait`
flags by ignoring them; `retire`, `sync`, `wake` log their argv and, for
`sync`, print the word the test needs), and export `AGORA_CLI` to it instead
of `DAEMON_SCRIPTS`. Keep every assertion's meaning; only the stub name and
argv shape change. Update `tests/executing/test-protocol-content.sh:182` to
assert `agora spawn` (and still `DAEMON_CLAUDE_SETTINGS`) and
`tests/qa-loops/test-bootstrap-parity.sh:163` to the new bootstrap-log path
once the prose in `review-worker-bootstrap.md` changes. Run
`tests/executing/*.sh`, `tests/qa-loops/*.sh`, `tests/issue-tracker/*.sh`,
`tests/claude-code/board-api/*.sh` and the integration drills; all green.

### M3 — the skill surface

Rewrite `skills/agora/SKILL.md`: description stays trigger-only (working as a
group; spawning, waking, listing, attaching to background sessions; finding an
agent's address; viewing a group's topology or board); body covers the seat
model in a paragraph, the agent protocol (you are a seat; receive is nothing to
do; send is SendMessage by addr from `agora topology`; the board is the
durable record; spawn children with `agora spawn <alias> "<task>" --group
<yours> --parent <your alias>`), the operator surface (`list`, `view`,
`send`, `wake`, `attach`, `reply`, `retire`, `fill`), and the absorbed
doctrine in its own section: where work goes (board for ticket-shaped work,
native subagents for in-session fan-out, a raw seat only when work must
survive the session and no board holds it), permission mode `auto` and why
`--dangerously-skip-permissions` is banned (a gated op is an escalation, not
a bug), worktree isolation for any seat that writes code and that its work is
a committed branch not merged, spawn-prompt hygiene (scope, deliverable, end
the turn stating above-scope decisions), long turns (`DAEMON_TIMEOUT` bounds
the watcher, never the turn), blocked shapes (AskUserQuestion rendered in the
reply; harness prompt marker; answer with `agora wake`), and never hand-drive
a pipeline worker (answers belong on the ticket; the sanctioned relay is
`board-answer.sh`). Rewrite `references/spawn-preamble.md` for the new spawn
form and the `seats` topology key; keep the `--from` masquerade warning for
posts. Delete `skills/orchestrating-daemons/` and `tests/orchestrating-daemons/`.
Update every cross-reference listed in Context and Orientation (prose,
`plugin.json` keyword → `agora`, infra comments, `TECH-DEBT.md`). Run
`tests/skill-links/test-cross-doc-refs.sh`.

### M4 — live fleet proof and migration

With real `claude`: run any `agora` command once and verify
`~/.claude/orchestrating-daemons` is now a symlink and `agora list` shows the
36 historical seats with groups derived from their cwd and no `null`. Register
this session as `orchestrator` in group `seats-dogfood` with `--addr <this
session's harness name>`. `agora spawn scout "<task: from your preamble, spawn
one child seat named scribe as your child whose task is to post a one-line
board note and end its turn; then end your turn>" --group seats-dogfood
--parent orchestrator --role scout --model sonnet`. Observe `agora view
seats-dogfood` show the three-level tree with roles and live states, and the
board post arrive. From the shell, `agora send scribe "reply to orchestrator
with one word via SendMessage"` and observe the `<cross-session-message>`
arrive here. `agora retire scribe`, then `agora fill scribe --resume "say
RESUMED to orchestrator"` and confirm the same session id continued and the
message arrived. `agora retire --purge` both seats and `agora remove` the
orchestrator seat; remove the dogfood board directory. Record transcripts in
Artifacts.

### M5 — exit gate

Run every suite named above plus `tests/agora/run-agora-tests.sh` and
`scripts/lint-shell.sh --all`. Dispatch the whole-branch codex review
(`review --base main --model gpt-5.6-sol`, stderr to a scratch file, background
shell); verify each finding against the code; fix the ones that survive via a
subagent fix wave; re-run suites. Bump the version with
`scripts/bump-version.sh` (minor), commit, open the PR against `main`, merge,
and write Outcomes & Retrospective.

## Concrete Steps

All commands run from the worktree root
`/Users/new/Developer/GitHub/doperpowers/.claude/worktrees/agora-native` on
branch `worktree-agora-seats`.

M0:

    git switch worktree-agora-seats
    git add docs/doperpowers/execplans/2026-09-02-agora-seats.md && git commit -m "docs(agora): execplan for v3 seats — substrate fold-in"

M1 (iterate until green):

    tests/agora/run-agora-tests.sh            # expect: ok … lines, final "all N assertions passed", exit 0
    scripts/lint-shell.sh --all                # expect: no findings

M2:

    tests/executing/test-execute-dispatch.sh && tests/executing/test-protocol-content.sh
    tests/qa-loops/test-review-dispatch.sh && tests/qa-loops/test-bootstrap-parity.sh
    for t in tests/issue-tracker/test-*.sh; do "$t"; done
    for t in tests/claude-code/board-api/test-*.sh tests/claude-code/board-api/integration/test-*.sh; do "$t"; done

M3:

    tests/skill-links/test-cross-doc-refs.sh
    grep -rn "orchestrating-daemons\|daemon-spawn.sh\|daemon-resume.sh\|daemon-retire.sh\|daemon-finalize.sh\|DAEMON_SCRIPTS" skills tests docs .claude-plugin infra   # expect: only docs/doperpowers/execplans and historical docs

M4 (real harness; see Plan of Work for the scenario):

    skills/agora/scripts/agora list | head
    ls -la ~/.claude/orchestrating-daemons      # expect: a symlink to ~/.claude/agora

M5:

    scripts/bump-version.sh <next-minor>
    gh pr create --base main --fill && gh pr merge --merge

## Validation and Acceptance

After M1, `tests/agora/run-agora-tests.sh` passes with every case listed in
M1's test paragraph, and `agora spawn x "t"` against the stub prints a banner
containing `[<8-hex> / <uuid>]`. After M2, every pipeline suite passes with the
`agora` stub and no file under `skills/` or `tests/` references
`DAEMON_SCRIPTS` or a `daemon-*.sh` name. After M3, `skills/orchestrating-daemons`
does not exist and the cross-doc linter passes. After M4, the transcripts in
Artifacts show: a three-level tree in `agora view`, a shell `agora send` that
produced a `<cross-session-message>` in this session, and a `fill --resume`
whose session id equals the retired seat's `current`. After M5, the PR is
merged and `agora --help` on `main` lists the verbs above.

## Idempotence and Recovery

Every registry write is an atomic replace under the shared flock; every verb
is safe to re-run (`spawn` refuses a filled seat instead of double-spawning;
`sync` is a pure reconciliation; `retire` and `remove` tolerate an
already-stopped session; migration checks for the symlink first). The
migration moves files rather than copying, so a crash mid-move leaves some
records in each root: re-running any command finishes the move (the old dir
still exists as a directory), and nothing is deleted until the symlink
replaces an empty old directory. Tests never touch real state (`HOME` and
`AGORA_HOME` under `mktemp -d`). M4's live seats are throwaway names; their
cleanup is `agora retire --purge` plus removing `~/.claude/agora/groups/seats-dogfood`.
If a pipeline suite fails after M2 in a way that suggests a wire-format
mismatch, the banner substring and the `sync` vocabulary are the two things to
compare first.

## Artifacts and Notes

Spike transcript (2026-09-01, shell → probe session inbox socket):

    $ python3 post.py agora-sock-probe "PROBE-1 shell-socket-user-frame 21:09:21Z"
    target: {'name': 'agora-sock-probe', 'pid': 86252, 'sessionId': '511214ae-…', 'kind': 'bg', 'status': 'idle', 'messagingSocketPath': '/tmp/cc-socks/86252.sock'}
    sent: {"type": "user", "message": {"role": "user", "content": "PROBE-1 shell-socket-user-frame 21:09:21Z"}}
    # ~20s later, witness.txt written by the probe's own Bash call:
    PROBE-1 shell-socket-user-frame 21:09:21Z CROSS-SESSION (sender name not specified in message)
    # claude logs showed the framing: "Another Claude session sent a message: PROBE-1 … This came from another Claude session — not typed by your user …"

M4 live proof (2026-09-01/02, real harness, this session as `orchestrator`):

    $ skills/agora/scripts/agora migrate
    agora: migrated: renamed /Users/new/.claude/orchestrating-daemons -> /Users/new/.claude/agora (old path is now a symlink); converted 3 v2 node(s) into seats; stamped group on 36 record(s), retired 2 legacy codex record(s)
    $ ls -ld ~/.claude/orchestrating-daemons
    lrwx------  … /Users/new/.claude/orchestrating-daemons -> /Users/new/.claude/agora
    $ agora list | grep -ci null        → 0   (40 rows; groups derived: fleet 25, ida-solution 9, demo 2, …)

    $ agora seat add seats-dogfood orchestrator --session 30e0568a-… --addr agora-native-aa --role orchestrator --brief "…"
    $ agora spawn scout "<task: find parent addr; spawn child scribe from your preamble; set status; SendMessage SCOUT-READY <short>>" \
        --group seats-dogfood --parent orchestrator --role scout --model sonnet --cwd <scratch>
    seat spawned: scout  [03e00b92 / 03e00b92-1d9c-45b9-93ef-d484f1046fb0]  group=seats-dogfood  status=working
    # ~90s later, with no further operator action:
    $ agora view seats-dogfood
    agora group: seats-dogfood
    orchestrator [orchestrator] · busy
    └── scout [scout] · busy
        └── scribe [scribe] · busy          ← spawned by scout through its preamble's spawn command
    $ agora board seats-dogfood
    <agora-post id="1" from="scribe" ts="2026-09-01T22:08:00Z" …>  ## hello  scribe seat is online and reporting in.
    # arrived in this session as a native event:
    <cross-session-message from-name="scout">SCOUT-READY 4d6ccff7</cross-session-message>
    $ agora list seats-dogfood      → scout: STATUS working LIVE idle NOW "spawned scribe"; scribe: NOW "posted hello"
    $ agora sync scout              → idle      (mirror reconciled from the harness row)
    $ agora send scribe "… SendMessage the orchestrator PONG-FROM-SCRIBE …" --from human
    sent to seats-dogfood/scribe (scribe)
    $ agora list seats-dogfood      → scribe LIVE busy   (was idle one second earlier: the shell frame woke it)
    # arrived here natively: <cross-session-message from-name="scribe">PONG-FROM-SCRIBE</cross-session-message>
    $ agora retire scribe
    retired seats-dogfood/scribe [4d6ccff7-75c3-4c53-9f73-3b4a0be480e6] (seat kept; re-fill with: agora fill seats-dogfood/scribe --resume "<task>")
    $ agora list seats-dogfood      → scribe STATUS retired LIVE stopped
    # first two attempts (before commit 66dec83f) hit the saved-options rule and were refused as copies — see Surprises
    $ agora fill scribe --resume "… SendMessage the orchestrator RESUMED-VIA-AGORA …"
    filled seats-dogfood/scribe  [4d6ccff7 / 4d6ccff7-75c3-4c53-9f73-3b4a0be480e6]  via --bg --resume  status=working  turns=2
    $ agora meta get scribe current → 4d6ccff7-75c3-4c53-9f73-3b4a0be480e6   (same session id; same short)
    # arrived here natively: <cross-session-message from-name="scribe">RESUMED-SCRIBE</cross-session-message> (raw no-flag resume)
    #                        <cross-session-message from-name="scribe">RESUMED-VIA-AGORA</cross-session-message> (agora fill --resume)

## Interfaces and Dependencies

`skills/agora/scripts/agora` (bash launcher) → `skills/agora/scripts/agora.py`
(Python ≥ 3.9, stdlib only). External commands: `claude` (≥ 2.1.257 for
same-id `--bg --resume` and the inbox socket), `git` (group derivation, board
branch snapshot). No `jq` after M1.

Environment: `AGORA_HOME` (registry root; `DAEMON_HOME` honored as fallback),
`AGORA_CLI` (consumers' seam to the launcher), `DAEMON_CLAUDE_SETTINGS` /
`DAEMON_CLAUDE_EFFORT` (gateway route for `spawn`/`fill`/`wake` when flags are
absent), `DAEMON_TIMEOUT` (watcher bound, default 18000s, 0 = forever),
`AGORA_UUID_POLL` (uuid poll iterations, default 30), `DAEMON_HOST` /
`DAEMON_BOOT_ID` (identity overrides for tests), `CLODEX_SETTINGS` (gateway
settings file whose `env` keys are scrubbed on the plain route).

Wire formats frozen for the pipeline: the spawn banner substring
`[<short> / <uuid>]`; `agora sync <seat>` printing exactly one of `noop`,
`live`, `absent`, `idle`, `error`; the registry file layout
`$AGORA_HOME/<seat-id>.json`, `<seat-id>.reply.txt`, `<seat-id>.err`, the
`.metalock` flock, the `*.reply.json` exclusion when globbing, and the mode
rule (recreate at the existing mode; 0600 whenever `run_bearer` is present).

Module-level functions in `agora.py` that the next-phase interactive view will
import: `load_seat(path) -> dict` (fallbacks applied), `seats(group=None) ->
list[dict]`, `live_state(seat) -> str`, `tree(group) -> list[(depth, seat)]`,
`send_frame(socket_path, text) -> None`.
