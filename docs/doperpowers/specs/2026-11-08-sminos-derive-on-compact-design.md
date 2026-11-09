# sminos: derive a session's in-charge line before each compaction

A session's **in-charge line** is one line in its project's sminos log saying what that session is responsible for; sminos shows it beside the session in every `sminos list`, and for a session whose name the engine generated, a **charge name** proposed with it becomes the session's name (`docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md`). **Derive** (`sminos derive`, in `sminos/skills/sminos/scripts/sminos.py`) is how a line is written without the session's involvement: a fork of the session is asked the question, and the answer is recorded with `source: derived`. Today the sminos daemon runs `derive --all` every five minutes; a session gets its first line soon after its model's tenth tool call, and a refresh at most every six hours, only if its transcript was written since its last line.

After this change, a session's line (and, where sminos may name it, its name) is also refreshed **just before every compaction** of its main conversation. That is the moment the session knows its work best: the full conversation is still in context, the prompt cache is warm because the compaction is about to read the same prefix, and right after it the session holds only a summary. Someone running `sminos list` after a long session compacts sees a line that reflects what it has been doing since, not what it was doing at its tenth tool call or six hours ago. The six-hour path stays as the fallback for sessions that run long without compacting (a session in a 1M window can work for half a day under 300k tokens and never be offered a compaction); a line derived at compaction restarts its six-hour clock through the existing age rule, so the two never double up.

The human chose this shape on 2026-11-08 (option a: compaction trigger plus the six-hour fallback, rather than compaction alone).

## Progress

- [ ] M1 — the CLI asks and records for an in-session fork
- [ ] M2 — the derive mod forks at compaction; live check, docs, version

## Design

### Orientation

| Part | Where | Role today |
|---|---|---|
| The daemon's derive duty | `sminos/skills/sminos/scripts/sminos_daemon.py` (`derive_duty`, `DERIVE_EVERY = 300`, `DERIVE_REFRESHES = 2`) | runs `sminos derive --all --refreshes 2` every five minutes |
| derive | `sminos.py`: `cmd_derive`, `derive_member`, `derive_refusal`, `charge_naming`, `naming_prompt`, `derive_line`, `answer_line`, `answer_name`, `charge_name_refusal`, `hand_name`, `DERIVE_EVERY = 6 * 3600` | decides who is asked, asks through `btw` or a headless fork (`sminos_fork.py`), records the line and hands a name over |
| The name mod | `sminos/hooks/mods/name.tsx` | every 15 s reads `<sminos home>/names/<session>.json`, and at an idle moment applies the name with the engine's `/rename` once `sminos name-due` says it is still due |
| The side question | `sminos/hooks/mods/bridge-btw.tsx` (`BTW_FRAME`, `framed`) | the bridge's `btw`: `$.model.fork` over the session's own last request |

A **mod** is a TypeScript module the engine loads from a plugin (`hooks.json`'s `modules`, here `sminos/hooks/mods/register.tsx`) and calls on engine events through `on(event, matcher?, handler)`; `$` is the engine interface it acts through. The engine declarations are in `sminos/.claude-plugin/types/claude-code/index.d.ts` (gitignored; `tests/mods/typecheck.sh --lay` lays them).

### 1. Where the fork runs: in the session, through `$.model.fork`, from `session.compact`

A new mod, `sminos/hooks/mods/derive.tsx`, hooks `session.compact` for the triggers `manual` (`/compact`), `auto` (the threshold) and `plugin` (doperpowers' compact tool), on the main conversation only (`e.agentId` absent), and not `precompute` (a speculative summary that replaces nothing). Before it calls `next(e)`, the conversation is still whole. It asks `$.model.fork` — one tool-less completion over the main thread's last request, served from that request's cache — the derive question, framed with `BTW_FRAME` (imported from `bridge-btw.tsx`: an auto compaction fires mid-turn, and an unframed fork mid-turn continues the task, which the btw work measured).

*Alternative:* have the hook run `sminos derive <member>` in the background and let the CLI ask through the bridge's `btw`. That lost because it races the compaction: by the time the CLI's process is up and its bridge op posted, the compaction may have replaced the conversation, and the fork would answer from the summary — the exact loss this change exists to avoid. It also needs a bridge, which not every session runs. *Alternative:* a classic `PreCompact` command hook. That lost because a command hook cannot reach `$.model.fork`; it could only start the racing CLI above.

### 2. The fork runs beside the compaction, not before it

The hook gets the prompt from the CLI (§3), **starts** the fork, and calls `next(e)` without awaiting the fork; it records the answer when the fork resolves. The fork's request is the main thread's last request, which the compaction does not replace until the next main-thread request after it completes, so starting it first is enough to pin the pre-compaction prefix. What the session waits on is only the CLI's prompt call (a Python start, about a tenth of a second).

*Alternative:* await the fork before `next(e)`. Deterministic by construction, but every compaction then waits for a completion over a few hundred thousand cached tokens (several seconds), and `ModelForkRequest` takes no abort signal, so a stalled API call could only be bounded by racing a timer. M2's live check verifies the pinning (the fork's `usage` reads the pre-compaction prefix from cache and its answer cites something only the pre-compaction conversation holds). If it shows otherwise, the hook awaits the fork before `next(e)`, bounded at 60 s (past the bound it proceeds and lets the fork finish on its own), and that change is recorded in the Decision Log; the rest of the design is unchanged.

### 3. The CLI keeps derive's rules; the mod only carries the question and the answer

Everything derive decides stays in `sminos.py`: whether the session may be asked, whether it may also be named, the prompt, the taken names, parsing the answer, the "renamed during derive" check, the log event, the pending name. Two verbs split today's `derive_member` around its fork (Interfaces):

- `sminos derive-prompt --session <id>` — whether the session may be asked now, and the prompt; with the naming state the answer is checked against.
- `sminos derive-answer --session <id>` — the fork's answer on stdin, recorded exactly as `derive_member` records a fork's answer today.

The post-fork half of `derive_member` (from `derive_failed_mark(m.session, False)` to the end) becomes one function both paths call, so a daemon derive and a compaction derive cannot drift apart.

*Alternative:* port the naming and recording rules into the mod. That lost because it duplicates the rules in two languages, and the name rules (§2 of the charge-names design) are exactly the ones whose drift would overwrite a name the owner gave.

**Which sessions `derive-prompt` refuses**, and why it is not `derive_refusal`: `derive_refusal` gates a fork the daemon starts from outside. Its rules about a fork's environment (the session runs on another machine, under another config dir, no transcript here) do not apply to a fork inside the session itself, and its pacing rules (a line derived within six hours, no activity since the last line, fewer than ten tool calls) are what the compaction trigger replaces: a compaction is itself the evidence that much has happened. `derive-prompt` refuses only:

| Refusal | Why |
|---|---|
| the session is no member of a project known here | there is no log to write the line to |
| its latest line has `source: set` | an owner or a brief set it; derive never overrides a set line (as `derive_refusal`) |

The mod itself skips when `SMNS_INTERNAL` is set in its environment (an internal fork sminos started, which must record nothing, as `name.tsx` and `address.tsx` already do).

### 4. Failure is silent to the session

Nothing in the hook may fail or delay a compaction beyond the prompt call. Every step is caught; a failure is one line in the mod's log (as `name.tsx` logs) and the compaction proceeds as if the mod were absent:

| Step | Failure | Effect |
|---|---|---|
| `derive-prompt` | throws, times out (10 s bound, as `NAME_DUE_TIMEOUT_MS`), exits non-zero, or stdout is not the JSON of Interfaces | logged; no fork; `next(e)` |
| `derive-prompt` | `{ "refused": … }` | no fork, not logged (an expected answer); `next(e)` |
| the fork | `isAnswered: false` (`nothing-to-fork`, `api-error`, `empty-reply`, `aborted`) | logged with the reason; nothing recorded. A failed in-session fork does not stamp `derive-failed`: that stamp holds the daemon's headless fork off for an hour, and a failure here says nothing about it |
| `derive-answer` | throws, times out (10 s), exits non-zero | logged; nothing more |

A compaction the engine then skips (`next(e)` resolves `{ skip }`) still records the line: the conversation the fork read is the session's as it stands, so the answer is as true as before.

### 5. The six-hour path stays, unchanged

The daemon's `derive --all` keeps its five-minute run, its first-line rule, its six-hour spacing and its two-refresh cap. A line derived at compaction is an `in-charge` event with `source: derived` like any other, so `derive_refusal`'s age rule reads it and the daemon leaves the session alone for six hours from it. A daemon derive and a compaction derive that happen to run together both record; the later line stands, which is harmless.

## Acceptance

1. In a session with the worktree's sminos plugin loaded, a `/compact` after some tool use records a new `derived` in-charge line in its project's log, written within about a minute of the compaction, and `sminos list` shows it beside the session. The fork's answer reflects the conversation before the compaction: in the live check, a fact planted only in the pre-compaction conversation (a code word the session was told and never wrote to a file) appears in or shapes the recorded line, and the fork's usage shows a cache read of the order of the pre-compaction context.
2. For a session whose name the engine generated, the same compaction also hands a charge name over (`<sminos home>/names/<session>.json`), and `name.tsx` applies it at the next idle tick, as a daemon derive's name is applied today.
3. A session whose latest line was set with `sminos charge` keeps that line through a compaction: no fork runs, nothing is recorded.
4. A compaction whose `derive-prompt` fails, or whose fork fails, completes as it would without the mod, and the session sees nothing of it.
5. A subagent's own compaction, and a `precompute`, start no fork.
6. After a compaction-derived line, `sminos derive <member>` prints `not derived — derived … ago` until six hours have passed (the existing age rule reading the new line).
7. The suites pass: `sminos/tests/run-sminos-tests.sh`, `sminos/tests/mods/run.sh`, `tests/mods/typecheck.sh`, and `ci-gate` on the branch is green.

## Execution

**Binding on every milestone.** The sminos plugin only: nothing in doperpowers' own `hooks/mods/` changes. The CLI stays `sminos.py` plus its siblings under `sminos/skills/sminos/scripts/`, standard library only. Mods are TypeScript under `sminos/hooks/mods/`, typechecked by `tests/mods/typecheck.sh` (it needs the engine declarations: `tests/mods/typecheck.sh --lay`, or copy the main checkout's gitignored `sminos/.claude-plugin/types/`). Verify commits with `ci-gate` from the worktree, not by running the gates locally; one focused test file while iterating is fine. Engine facts (the fork's prefix pinning, §2) are pinned by the live check, not by unit tests: a unit test cannot see the engine.

### M1 — the CLI asks and records for an in-session fork

**At its end:** `sminos derive-prompt --session <id>` prints the prompt a fork should be asked, with the naming state, or why it is refused; `sminos derive-answer --session <id>` records a fork's answer from stdin as a `derived` in-charge line (with a charge name and pending file where the session may be named), exactly as a daemon derive records one. `derive_member` records through the same function.

**Touches:** `sminos/skills/sminos/scripts/sminos.py` (the two verbs and their argparse entries; the post-fork half of `derive_member` extracted), `sminos/tests/run-sminos-tests.sh`.

**Interfaces:** produces `derive-prompt` and `derive-answer` (Interfaces and Dependencies).

**Decisions:** the refusals are §3's table and no others. The member is found from the session id the way `name-due` finds it (`record_project` and the running engine record), falling back to the project members when the engine record is absent; a session found nowhere is refused, not an error. The naming state in `derive-prompt`'s output is `charge_naming`'s `before` and `pid`, and `derive-answer` checks "renamed during derive" against them as `derive_member` does today; `taken` is recomputed at answer time by `charge_name_refusal`'s caller, as today. `derive-answer` reads the line with `answer_line`; an answer with no line records nothing and says so on stdout (`<alias>: not derived — the fork answered nothing`), exit 0. `derive-answer` clears the `derive-failed` stamp on success (a line now exists), as `derive_member` does; neither verb sets it (§4). Both verbs exit 0 except on a usage error (a session id that is not a UUID, malformed stdin JSON), because the mod reads their output and must never fail a compaction; an unexpected error is a stderr warning with exit 0, as `cmd_name_due` handles it.

**Does not touch:** `derive_refusal`, the daemon, `derive --all`'s order or cap, the headless or `btw` paths.

**Proves:** acceptance 3 at the CLI level (`derive-prompt` refuses a set line), and 6 (a line recorded by `derive-answer` makes `sminos derive <member>` refuse with `derived … ago`). Tests also pin: `derive-answer` with a naming answer for an eligible session writes the `in-charge` event with `name` and the pending file; with the engine record renamed between `derive-prompt` and `derive-answer`, it records the line with no name and prints `no name: renamed during derive`; a daemon derive (the stub fork, `STUB_FORK_RESULT`) still records the same event shape as before the extraction.

### M2 — the derive mod forks at compaction; live check, docs, version

**At its end:** a session's compaction of its main conversation derives its line (and name where eligible) from the pre-compaction conversation, per §1, §2 and §4; the live check proves it against a real engine; the docs describe the new trigger.

**Touches:** `sminos/hooks/mods/derive.tsx` (new), `sminos/hooks/mods/register.tsx` (register it after the name), `sminos/tests/mods/derive.test.ts` (new, beside `name.test.ts`), `sminos/tests/mods/live-derive-check.py` (new, built on `live-name-check.py`'s isolation), `sminos/hooks/mods/README.md` (the mods manual: a `derive` section), `sminos/hooks/mods/CLAUDE.md` (the hooks' list), `sminos/hooks/hooks.json` (its description names the trigger), `sminos/skills/sminos/scripts/CLAUDE.md` where it states derive's cadence, `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md` §5 (one sentence: derive also runs in-session at each compaction, pointing here), and the version through `scripts/bump-version.sh --plugin sminos` (minor bump, in the same commit as the mod).

**Interfaces:** consumes `derive-prompt` and `derive-answer`.

**Decisions:** the hook's steps, in order: skip unless main loop, trigger in {manual, auto, plugin}, `SMNS_INTERNAL` unset; read the session id (`$.session.id()`); run `derive-prompt` (10 s bound); if it gave a prompt, start `$.model.fork({ prompt: framed(prompt) })` and attach the recording continuation (fork answered → `derive-answer` with stdin `{ "text": r.text, "naming": <from derive-prompt> }`, 10 s bound); then `return next(e)`. The CLI is run as `name.tsx` runs it (`${$.plugin.root}/skills/sminos/scripts/sminos`), with `$.process.run`'s `stdin` for the answer. The mod's state is per call; nothing goes in `$.state` (a reload mid-fork loses one refresh, which the next compaction or the six-hour path makes up). Tests drive the hook through an injected io, as `name.test.ts` drives `createNamer`, and pin: the skips (subagent, `precompute`, internal), `next(e)` called exactly once and not after the fork resolves (a fork that never resolves does not hold the compaction), each §4 failure row leaving the compaction's result untouched, the stdin `derive-answer` receives, and the frame on the fork's prompt.

The live check (spends model calls, run by hand with the gateway's keys, as `live-name-check.py`): a session with no name, told a code word and asked to make ten or more trivial tool calls, then `/compact`; it asserts acceptance 1 (a new `derived` line, written after the compaction began, that carries or reflects the code word; the mod's log shows the fork's cache read), 2 (the pending name applied, `nameSource: "user"`), and 5 for a subagent if the engine lets the check force a subagent compaction cheaply (else recorded as covered by unit tests only). If the code word is absent and the cache read is of the summary's size, §2's fallback applies: switch to awaiting the fork, record it in the Decision Log, and re-run.

**Does not touch:** `name.tsx`, `bridge-btw.tsx` beyond importing `framed`, the daemon, doperpowers' `hooks/`.

**Proves:** acceptance 1, 2, 4, 5 (unit tests, and the live check for 1 and 2), and executes the whole acceptance section as written at the end, with 7's suites and `ci-gate`.

## Concrete Steps

From the worktree root:

    tests/mods/typecheck.sh --lay        # once, if sminos/.claude-plugin/types/ is absent
    sminos/tests/run-sminos-tests.sh     # CLI suite; expect every case PASS
    sminos/tests/mods/run.sh             # mods suite; expect derive.test.ts among the passing files
    tests/mods/typecheck.sh              # expect no output, exit 0
    python3 sminos/tests/mods/live-derive-check.py   # live, by hand; expect each assertion line OK
    ci-gate                              # expect GREEN <run-url>

The CLI by hand, against a running session's id `S` that has a derived line:

    sminos derive-prompt --session S
    {"prompt": "In one line: what is this session in charge of …", "naming": {"before": "…", "pid": 12345}}
    echo '{"text": "Owns the derive cadence work in doperpowers.", "naming": null}' | sminos derive-answer --session S
    <alias>: Owns the derive cadence work in doperpowers.
    sminos derive <alias>
    <alias>: not derived — derived 0s ago

## Interfaces and Dependencies

**`sminos derive-prompt --session <uuid>`** — stdout is exactly one JSON object, then a newline:

    {"prompt": "<the derive prompt: naming_prompt(naming) when charge_naming gives one, else DERIVE_PROMPT>",
     "naming": {"before": "<engine name read now>", "pid": <engine pid>} | null}

or

    {"refused": "<reason, one of §3's table, in derive's own wording>"}

Exit 0 except a usage error (not a UUID: exit 2 with the usage line on stderr).

**`sminos derive-answer --session <uuid>`** — stdin is one JSON object:

    {"text": "<the fork's whole answer>", "naming": <derive-prompt's naming, verbatim>}

It records as `derive_member` records after a fork, printing the same lines (`<alias>: <line>`, `<alias>: name <name>`, `<alias>: no name: <reason>`). Exit 0 except a usage error (not a UUID, stdin not that JSON). A session `derive-prompt` would refuse now (its line was set meanwhile, it left the project) is refused here too, printing `<alias>: not derived — <reason>`: the state may have moved during the fork.

**The extracted recorder** in `sminos.py`: one function taking the project, the member, the derived line, the whole answer text, and the naming state (`before`, `pid`, or none), returning what `derive_member` returns today (`"derived"`), used by `derive_member` and `derive-answer`.

**The mod** `sminos/hooks/mods/derive.tsx` exports a factory taking an injected io (`prompt(session)`, `fork(prompt)`, `answer(session, stdin)`, `log(line)`, `isInternal()`), as `name.tsx` exports `createNamer`, and `registerDerive(on)`.

## Surprises & Discoveries

(none yet)

## Decision Log

- Decision: verification. One independent spec review by `doperpowers:adversarial-reviewer` (the spec is technical-heavy), and, the execution section having two milestones, its buildability review in the same round. The branch is reviewed through `doperpowers:review-code` at the medium rung (`doperpowers:reviewer-medium`).
  Rationale: the risks are an engine fact (the fork's prefix, pinned by the live check, not a reviewer) and drift between the daemon's and the mod's recording (removed by construction, §3); the charge-names precedent judged the medium rung proportionate for the same rules.
  Date/Author: 2026-11-08, derive-refresh-cadence session.

## Outcomes & Retrospective

Pending — written at finish.
