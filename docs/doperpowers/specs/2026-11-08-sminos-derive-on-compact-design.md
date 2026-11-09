# sminos: derive a session's in-charge line after each compaction

A session's **in-charge line** is one line in its project's sminos log saying what that session is responsible for. sminos shows it beside the session in every `sminos list`. For a session whose name the engine generated, a **charge name** proposed with the line becomes the session's name (`docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md`). **Derive** (`sminos derive`, in `sminos/skills/sminos/scripts/sminos.py`) writes a line without the session's involvement: a fork of the session is asked the question, and the answer is recorded with `source: derived`. Today the sminos daemon runs `derive --all` every five minutes. A session gets its first line soon after its model's tenth tool call, and after that a refresh at most every six hours, and only if its transcript was written since its last line.

After this change, a session's line, and its name where sminos may name it, is also refreshed **as soon as each compaction of its conversation ends**. A compaction marks a long stretch of work. Someone running `sminos list` after a long session compacts sees a line that reflects what the session has been doing since, not what it was doing at its tenth tool call or up to six hours ago. The six-hour path stays as the fallback for sessions that run long without compacting: in a 1M-token window a session can work for half a day under 300k tokens and never be offered a compaction. A line derived after a compaction restarts the six-hour clock through the existing age rule, so the two paths never double up.

The human chose this on 2026-11-08: first the compaction trigger with the six-hour fallback (over compaction alone), then the trigger placed after the compaction, through a hook.

## Progress

- [ ] M1 — a compaction derives the session's line

## Design

### 1. The trigger: a `SessionStart` hook with the `compact` source

The engine runs a plugin's `SessionStart` hooks after a compaction with `source: "compact"`; the payload carries the session's `session_id`, the same id as before the compaction. A new shell hook, `sminos/hooks/smns-derive.sh`, is registered in `sminos/hooks/hooks.json` under `SessionStart` with the matcher `compact`. It reads the session id from the payload, starts `sminos derive <session-id> --compacted` detached in the background, and exits 0 at once. The session never waits on it, and it prints nothing: a `SessionStart` hook's stdout would reach the model as context. Like `smns-record.sh`, it does nothing when `SMNS_INTERNAL` is set, which marks an internal fork that sminos started.

The derive asks as derive always asks (`derive_line`). Through the session's bridge where one runs, the bridge's `btw`: a tool-less completion over the main thread's last request, read from its cache. Otherwise a headless fork, `claude -p --resume <session> --fork-session`, which now resumes the compacted conversation and so reads little. Right after a compaction, the main thread's last request is often still the one sent before it, so the `btw` answer may come from the whole conversation rather than the summary. The design does not depend on that: the summary is written as a note a reset session resumes from (doperpowers' `hooks/compact-instructions.md`), and the question asks for the session's standing responsibility, not its latest step, which such a note carries.

Running `sminos derive` from the session's own environment is an existing path, since a session's Bash tool runs `sminos derive <member>` in the same environment. One consequence helps: `derive_refusal`'s `foreign_config` check compares the session's config dir with the deriving process's, and the hook's process runs under the session's own.

*Alternative: a mod that forks the session in-process before the compaction* (`session.compact`, `$.model.fork`, then `next(e)`). It would answer from the full conversation for certain, but it needed two new CLI verbs to split derive around the fork, a new mod, and a live measurement of an engine fact (whether a fork started before `next(e)` keeps the pre-compaction prefix). That buys little over a summary written to carry exactly what the question asks. This design's first version took this route; the human questioned whether before-compaction was needed, and it lost on simplicity. *Alternative: the daemon finds compactions itself*, by looking for a `compact_boundary` row newer than the last line in each transcript. No hook needed, but the line would come up to five minutes late, and the daemon would re-read the tails of large transcripts every five minutes. The daemon's quiet-tick work (`sminos/skills/sminos/scripts/CLAUDE.md`) exists to remove exactly that kind of re-reading.

### 2. What `--compacted` changes in derive

`sminos derive <member> --compacted` derives one member. It differs from a plain `derive <member>` only in the two pacing rules of `derive_refusal`, which it waives:

| Rule in `derive_refusal` | With `--compacted` | Why |
|---|---|---|
| a derived line within the last six hours (`derived … ago`) | waived | a compaction is the evidence that much has happened since |
| the transcript not written since the last line (`no activity since its last line`) | waived | a compaction writes the transcript, so this never holds anyway; waived so the flag's meaning does not depend on the ordering |
| no session; not local; line `set`; another config dir; no transcript here | kept | they say the session cannot or must not be derived, whatever the trigger |
| fewer than ten tool calls by its model | kept | the first-line threshold; a session that compacts before ten tool calls (a `/compact` early on) has too little to say |
| `launch_refused` (macOS protected folders, in `derive_member`) | kept | it guards against a system dialog, not a pacing choice |

Naming, recording, the pending name and `name.tsx`'s application of it are unchanged: a compaction derive goes through `derive_member` like any other. A failed fork stamps `derive-failed` as it does today. That holds only the daemon's `--all` off for an hour, never a derive that names its member. `--compacted` with `--all` is a usage error: the flag speaks for one session's compaction.

### 3. The six-hour path stays, unchanged

The daemon's `derive --all` keeps its five-minute run, its first-line rule, its six-hour spacing and its two-refresh cap. A line derived after a compaction is an `in-charge` event with `source: derived` like any other, so the age rule reads it and the daemon leaves the session alone for six hours from it. If a daemon derive and a compaction derive happen to run together, both record and the later line stands, which is harmless.

## Acceptance

1. A compaction's `SessionStart` hook payload, given to `sminos/hooks/smns-derive.sh`, starts `sminos derive <session-id> --compacted` and returns at once with no output. In the suite: the hook exits 0 within a second, prints nothing, and the stub fork's call log shows the derive's fork for that session.
2. `sminos derive <member> --compacted` derives a member whose line is minutes old, and records a new `derived` line; a plain `sminos derive <member>` right after refuses with `not derived — derived … ago`.
3. `--compacted` still refuses a member whose line was set with `sminos charge` (`its line is set`), and one whose model has made fewer than ten tool calls.
4. For a session sminos may name, the compaction derive proposes a charge name and leaves the pending file, as a daemon derive does.
5. `sminos derive --all --compacted` exits 2 with the usage line.
6. With `SMNS_INTERNAL` set, the hook starts nothing.
7. The suites pass: `sminos/tests/run-sminos-tests.sh` and `ci-gate` on the branch is green.

## Execution

**Binding.** The sminos plugin only: nothing in doperpowers' own `hooks/` changes. The CLI stays `sminos.py` plus its siblings, standard library only. Verify commits with `ci-gate` from the worktree, not by running the gates locally; one focused run of the sminos suite while iterating is fine.

### M1 — a compaction derives the session's line

**At its end:** every compaction of a session in a sminos project starts a derive of that session (§1), which waives the pacing rules alone (§2).

**Touches:** `sminos/hooks/smns-derive.sh` (new), `sminos/hooks/hooks.json` (the `SessionStart` entry with matcher `compact`, and its description), `sminos/skills/sminos/scripts/sminos.py` (`derive_refusal` takes the waiver; `cmd_derive` and the `derive` parser take `--compacted`), `sminos/tests/run-sminos-tests.sh`, `sminos/hooks/CLAUDE.md` (the shell hooks' list), `sminos/skills/sminos/scripts/CLAUDE.md` only if it states derive's cadence, `docs/doperpowers/specs/2026-10-13-smns-project-log-design.md` §5 (one sentence: a compaction also starts a derive, pointing here), `docs/whats-inside.md` if its sminos row names the hooks, and the version through `scripts/bump-version.sh --plugin sminos` (minor), in the same commit as the change.

**Decisions:** the hook reads the session id the way `smns-record.sh` does and starts the CLI only for a value that `fullmatch`es a UUID. The child is started with stdin from `/dev/null` and stdout and stderr to `/dev/null`, under `nohup`, so neither the hook runner's pipes nor its exit hold or end it. derive's failures already leave their own trace (`derive-failed`, daemon.log's once-said lines). The hook does no project pre-check of its own: `derive` with a session id no member holds exits 4, which costs one Python start per compaction.

**Does not touch:** the daemon, `derive --all`'s order, cap and hold, `name.tsx`, `sminos_fork.py`.

**Proves:** acceptance 1–6 in `run-sminos-tests.sh`, beside the existing derive tests (the stub fork and `hp_peer` fixtures). The hook test waits for the backgrounded derive's fork to appear in the call log, bounded, rather than sleeping.

## Concrete Steps

From the worktree root:

    sminos/tests/run-sminos-tests.sh     # expect the new derive and hook cases PASS, no FAIL
    scripts/bump-version.sh --plugin sminos --since origin/main   # expect the bump to be accepted
    ci-gate                              # expect GREEN <run-url>

By hand, against a session `S` (a full session id) in a sminos project with a recent derived line:

    sminos derive S
    <alias>: not derived — derived 3m ago
    sminos derive S --compacted
    <alias>: <the session's line>

## Surprises & Discoveries

(none yet)

## Decision Log

- Decision: verification. The spec is one milestone, technical and small: one independent spec review by `doperpowers:adversarial-reviewer`, run alongside execution, and the branch reviewed through `doperpowers:review-code` at the medium rung (`doperpowers:reviewer-medium`).
  Rationale: the change reuses derive whole and adds one waiver and one hook; the risks (a hook that holds a compaction or prints into context, a waiver wider than the two pacing rules) are pinned by tests.
  Date/Author: 2026-11-08, derive-refresh-cadence session.
- Decision: the trigger moved from before the compaction (an in-process fork from a `session.compact` mod) to after it (a `SessionStart` `compact` hook running `derive --compacted`).
  Rationale: the human asked whether after the compaction would do; it does (§1), at a fraction of the parts. The before-compaction design is the first alternative in §1.
  Date/Author: 2026-11-08, derive-refresh-cadence session, at the human's prompt.

## Outcomes & Retrospective

Pending — written at finish.
