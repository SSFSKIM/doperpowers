# Tech-debt tracker — codex-workers live shakedown residue

> **Why this doc exists.** The 2026-07-11 live shakedown
> (`2026-07-10-codex-workers-shakedown.md`) fixed every defect it surfaced
> (FU-3…FU-7) but left a residue of known, accepted frictions. GitHub Issues
> are disabled on this fork, so this file is the tracker. Each item carries a
> **tier** (how much it matters) and a **trigger** (the event that promotes
> it from "accepted" to "fix now"). Update in place; strike items when fixed.
>
> Tiers: **T1** — structural; must be addressed at its named trigger, do not
> build past it. **T2** — real debt; cheap to fix, schedule at the trigger.
> **T3** — accepted/cosmetic; fix opportunistically or never.

| # | Tier | Item | Trigger |
|---|---|---|---|
| 1 | T1 | ~~Recovery from transient worker deaths is manual~~ **SHIPPED 2026-07-18** (board-sweep RECOVER pass) | — |
| 2 | T1 | ~~gh-token capture failure~~ **NA on the one-harness pipeline** (the capture lived in retired codex-spawn) | Reopens only if a codex-CLI worker is ever spawned again |
| 3 | T2 | Claude engine branch untested by the shakedown (SD-2, SD-4 deferred) | First real claude-engine dispatch |
| 4 | T2 | ~~No CI/pre-push gate on the shell test suites~~ **SHIPPED 2026-10-15** (ci-kit: PR checks per suite family on GitHub-hosted runners; `ci-gate` from any worktree). The checks are not required, so a red one does not block a merge | — |
| 5 | T2 | Automated review trigger blocked: self-hosted runner unregistered | Org admin grants (ida-solution#302) |
| 6 | T3 | `needs-human → in-review` restore is a two-hop | Review-side transient parks becoming frequent |
| 7 | T3 | Work-alone mandate is prompt-level, not mechanical | An observed post-clause violation |
| 8 | T3 | `SSL_CERT_FILE` fix is macOS-path-specific | First Linux worker host |
| 9 | T3 | Accepted notes: GH_TOKEN visible in worker env; mini ssh probe noise; resume-only daemons' run scratch un-swept until next spawn | — |
| 10 | T2 | ~~Answer relay L2~~ **SHIPPED 2026-07-18** (board-sweep RELAY pass); L3 (BOARD.html session affordances) still unbuilt | Board-map touch (L3) |
| 11 | T2 | Six board-pipeline scripts (`board-bind.sh`, `_sweep_api.sh`, `board-sweep.sh`, `execute-dispatch.sh`, `review-dispatch.sh`, `board-answer.sh`) each reimplement the seat-registry read-modify-write (flock `.metalock`, bearer-mode 0600 rule) instead of calling `sminos meta set`; coexistence is safe because sminos's writer keeps the same invariants, but the invariants live in seven places (sminos v3 seats, 2026-09-02) | Next board-pipeline touch that edits registry writes |
| 12 | T3 | `board-bind.sh`'s `projectKey` is `basename $BOARD_ROOT`, not the board's repo key — daemon-registry metadata that reads like a repo claim now that the api binding declares one (doperpowers#33 scoped it out; switching it touches resume semantics) | Next board-bind or daemon-resume change |
| 13 | T2 | gh mode's daemon-registry scans are half-filtered by board identity: `board-answer.sh`'s two scans go through `meta_is_mine` (board ticket 33 made the predicate pure, so it covers gh's `owner/name` key too) but `board-show.sh:105`, `board-reconcile.sh:73`, `board-gc.sh:68`, `board-sweep.sh:153`, `_board.py:824` do not. Two gh checkouts on one machine collide on ticket numbers exactly as two api ones did. Pre-existing; api side is complete | Next gh-mode registry change, or the first machine running two gh-bound repos |
| 14 | T3 | `_sweep_api.sh`'s successor-lane journal scan (`~:1058`) and `board-answer.sh`'s two gh scans carry the `meta_is_mine` filter with no end-to-end drill of their own — covered by the predicate's unit drill only (a first drill passed with and without the filter and was withdrawn) | When a drill can reach the successor lane with a planted foreign meta |
| 15 | T3 | Flat legacy records under `board-claims/` and `board-suppress/` — written before doperpowers#36 keyed those stores by binding — are read alongside the keyed ones by the dispatchers' reconciler, the sweep's successor scan and both suppression checks. Nothing writes there any more, so the store drains as each record is finished, and the read-both branch plus its drills can go once the last one has. No migration on purpose: a move is a second way to lose a record that is somebody's only retry handle | When the flat stores are empty on every machine running this fleet |
| 16 | T3 | The rollout guards doperpowers#36 added for the pre-key lock names (`_sweep_api.sh`'s `_LEGACY_LOCK` probe, `_board_api.legacy_surface_held` and its three callers) are check-then-lock, not atomic: an old-version tick or dispatcher that takes its flat lock between the probe and the keyed `mkdir` overlaps ours, and a stale flat lock whose `rmdir` fails is reported as free. Bounded to the one upgrade window on a machine where a pre-#36 process still runs — the same window the guards exist for. Delete the guards (and this row) rather than harden them once no host runs the pre-#36 sweep | Next touch of the lock paths, or the guard-block deletion |
| 18 | T3 | The sweep's STALL pass considers waiting LEAVES only, so an epic in `ready-for-architect` blocked by another ticket is never reported however long its blocker is dead. Inherited deliberately from the API board's pass (arkho #56, Design §4 — there the park would have to survive `passRecomposition`'s return; here it would have to survive `pull_epics` / `recompose_epics`, both of which rewrite an epic's note and would erase the report). Real but unobserved: an epic carrying an ordering edge of its own is rare, and an epic's liveness is its children's, which the other passes already judge | First epic-level dependency wait a human actually hits |
| 17 | T3 | `_binding.sh` derives the main checkout as the parent of `git rev-parse --git-common-dir` — for the credentials slug since A2 and, since doperpowers#12, for the `board.json` fallback in a linked worktree. Git does not guarantee that layout: `--separate-git-dir`, a bare-hosted worktree set, or a submodule puts the common dir elsewhere and the probe lands on an unrelated path (fallback → gh, slug → a token file nobody wrote). Every checkout this fork dispatches into is a plain clone plus `git worktree add`; resolve the primary worktree from `git worktree list --porcelain` in both places together if that ever changes | First dispatch into a separate-git-dir / bare-hosted / submodule checkout |
| 19 | T2 | Every sweep pass writes from a snapshot taken once at pass start: `pass_stall`, `pass_impact` and `pull_epics` re-derive nothing between the read and the `apply_state` write, and `set_state_label` removes only the status labels that STALE snapshot knew — so a concurrent writer inside that window leaves two `status:*` labels on one issue (`derive_state` → `conflict`, and `board-lint` FAILs it). Bounded today: the tick holds a single-instance lock, and `pass_stall`'s candidates are by construction never `B.eligible`, so neither the sweep's own dispatch nor the event-driven dispatcher can be that writer — the only one left is a human running `board-transition.sh` inside a few-second window. Fencing one pass buys no guarantee; this wants a fence every writer shares | First observed conflicted-label incident, or any move to concurrent ticks |
| 20 | T3 | `pass_stall`'s dedupe costs one paginated comment read per DUE candidate per tick, with no cross-tick cursor. The read is deliberately the last predicate checked, so a healthy board pays nothing (drilled under `board-sweep: STALL read cost`), and after any human touch the waiting ticket's own `updatedAt` suppresses it for a further full threshold. What that does not bound is a board where many tickets are re-queued onto blockers that never move: one full-trail read each, every tick — the shape IMPACT's durable cursor exists to prevent | More than a handful of standing `[dependency-stall]` re-reports on one board, or the next tick-duration complaint |
| 22 | T3 | After an observation-mode park, a human merge closes the ticket through `Closes #N` before any answer can reach the owner. `board-answer.sh` then refuses (`done, not needs-human`), and FINALIZE writes the terminal transition. The board ends correct, but the owner is never told, and the parked QA agent's `<review-tmp>` leaks. `board-gc.sh` reclaims its worktree (reviewer-fold Task 13) | Temp-directory growth on a worker host, or an owner that needs post-merge work |
| 23 | T2 | The api sweep's owner-in-review ladder recovers only an IDLE owner: `_sweep_api.sh`'s `phase_review_recover` drops any seat that is not `idle` after the sync (its idle gate), so an owner still reading WORKING whose review has gone silent — a hung turn, or a QA agent that died without ending the seat's turn — is never nudged or parked. gh mode's in-review arm covers it: its `live` case takes the transcript tree's newest mtime and runs the same ladder past the stall threshold. Parity target: that live arm, on the same tree-wide clock the idle arm now reads (reviewer-fold whole-branch review) | First api-bound review found stuck behind a working owner, or the next edit to the review-recover phase |
| 24 | T2 | A follow-up an Architect registers without a parent link is unreadable by its own QA run: the API board scopes a run bearer to its ticket and that ticket's direct children, so in the Task 12 API smoke the QA agent's `board-show 73` under run 53's bearer was refused ("bearer limited to ticket #72 and direct children") — #73 was registered by run 53 with no `--parent`. The architect protocol's residue path says `--spawned-by`, and whether that edge counts as a child under the bearer scope is unverified; the pre-registration that produced #73 used neither. The architect protocol should register follow-ups with the parent link the scope reads | The next QA run that needs to read a follow-up, or the next edit to the architect protocol's follow-up registration |
| 25 | T2 | plan-executor refused to write its report file, citing a harness system-prompt line against writing report `.md` files, and the owner transcribed the hand-back into `.architect/72/plan-executor-report.md` (Task 12 API smoke). The same line reaches other worker contexts, so every contract that names a report file (plan-executor, task-executor, qa-loop's `report:` line) disagrees with the harness, and which one a worker obeys is left to chance | The next worker that refuses or drops its named report file, or any change to the report-file contract |
| 26 | T2 | ~~An armed auto-merge never reaches `done` on the API binding by itself: `qa-loop.md`'s armed-`DONE` line says the PR's `Closes` link and the sweep's FINALIZE pass finish the ticket, but the API tick has no finalize pass and, since the closing wave, no `Closes` link. A PR that merges after the agent returned stays `in-review` until `phase_review_recover` nudges the idle owner (45 min) and the re-dispatched agent finds the merge and writes `done`. Parity target: an API finalize step in `_sweep_api.sh` — PR merged at the reviewed head → `in-review → done` under the review-trail gate (Task 12 closing wave)~~ **SHIPPED 2026-09-23** (`_sweep_api.sh` finalize phase: PR merged at the trail's reviewed head → `in-review → done`; see `docs/doperpowers/specs/2026-09-23-api-finalize-pass-design.md`) | — |
| 27 | T2 | An unattended fable seat can be paused by the harness's safeguard dialog ("Session paused — Fable 5.1's safeguards flagged this message", `[cyber]`) on a subagent hand-back whose text reads as security work: the daemon reports the session `waiting` with `waitingFor: "dialog open"`, sminos reads `blocked`, the ticket stays `in-review`, and no sweep phase acts (recovery is idle-gated). Observed on #74 (2026-09-24): 18 minutes until a person attached and took the dialog's "switch to Opus" option. Options: run Architect seats on opus (`ARCHITECT_MODEL`), or have `phase_review_recover` treat a `dialog open` owner as a park (`needs-human` carrying the dialog text) so the human sees it on the board. | a second occurrence, or the first unattended run past a workday |
| 28 | T3 | A parent cycle whose seats are all live cannot be retired: `retire --cascade` orders it (each seat visited once since 36feaacc) but each seat's live-child check sees the other, so both refuse "hosts live children". Only `seat add --parent` can build a cycle (`spawn` derives `parent` from the caller). Fix by letting a cascade's scheduled seats pass the live-child check, or by refusing a cyclic `--parent` at `seat add` (sminos family chat re-review, 2026-09-27) | First cycle seen in a real registry, or the next `retire`/`seat add` touch |
| 29 | T3 | `push_member`'s lifecycle lock (36feaacc) has no interleaving test: the stale-push probe retires the seat before the call, so it exercises the reloaded-record recheck and not the lock across reload → resume. A probe that retires the seat from a patched `live_state` between the liveness read and the lock would pin it (sminos family chat re-review, 2026-09-27) | Next change to `push_member` or `resume_session` locking |
| 30 | T3 | The status mirror is stale beside `live`: `list` prints a seat's last self-reported `status`, so a host that never ran `sminos status` reads `working` while `live=idle`; `sync` refreshes it, `list` does not. Seen in the family-chat live proof (spec Surprises, 2026-09-27); pre-existing | Next `list`/`sync` touch, or an operator misled by it |
| 31 | T2 | A usage-limit stop on a seat is handled as an ordinary errored turn: the harness job reads `failed`, `status_for_state` maps it to `error`, and `board-sweep.sh`'s `pass_recover` resumes it with a nudge at each tick until `SWEEP_RECOVERY_CAP` (3) is spent — against a limit that lifts in hours every attempt fails and the ticket parks `needs-human` with its recovery cap gone (T3 comparison §4.1, 2026-10-08). The sweep never reads the error text; a gateway limit's text carries its reset time (`… at its usage limit until Oct 9, 14:13 PDT`), Anthropic's own shape in a `--bg` transcript is unobserved. Fix, in order: CAPTURE the next limit stop on a seat (the transcript's last records and the harness row) before any code; then stamp `limited_until` on the seat and have the sweep skip recovery until it passes without spending the cap; `list`'s now column reads it as `waiting` reads `waitingFor` | The next usage-limit stop on a seat — capture first |
| 32 | T3 | The appeal mod's pass is bound to the loop, the tool, the whole input, the epoch, the loop's directory and (Bash) the loop's Bash generation, but not to a shell's recovery from a deleted directory: when another process deletes the shell's current subdirectory after a grant, Bash may recover to the project root during execution, after `tool.check`, and run a relative command there with no Bash start between (review round four, 2026-10-17). Needs another process racing the agent's own directory. ~~Separately, the live check's grant scenario found no classifier block to appeal in four candidates, so the pass path is proven by unit tests and engine facts, not live~~ **CONFIRMED LIVE 2026-10-17 evening**: the human's own sessions logged a grant re-run on a pass (`used`, an Edit blocked `[Self-Modification]`) and a grant run by the appeal itself (`relayed`, a Bash call), and an uphold where the user had not named the action (`docs/doperpowers/specs/2026-10-17-auto-mode-appeal-design.md`) | A deleted-directory recovery seen in a log |

## T1 — structural: the unattended-dispatch phase must answer these

### 1. Manual recovery from transient worker deaths

Three worker turns died on transient upstream failures during the shakedown
(model-at-capacity, two stream disconnects). `codex-resume.sh` recovered all
three — but only because an operator was watching. Unattended, a dead worker
sits in `error` and its ticket in `in-progress` until `board-reconcile.sh`
flags the orphan **and a human acts**. The auto-attach trigger phase
(doperpowers:issue-tracker `scripts/`, unbuilt) must specify a
retry-on-transient policy: distinguish transient (stream disconnect,
capacity) from real failures via the recorded turn error, bounded auto-resume
for the former, park for the latter. Do not arm unattended dispatch without
this. Reference design for the taxonomy, backoff, and stall detection:
Symphony SPEC §7–8 — see `2026-07-11-symphony-comparison.md` §2/§10.

### 2. Silent-ish gh-token capture failure

Round 2 of SD-3 launched a worker whose spawn-time `gh auth token` capture
returned empty (cause never pinned — round 1 captured fine five minutes
earlier; suspected transient keyring denial). FU-6b made the failure a loud
dispatch-time warning, which is sufficient while dispatch is an
operator-run ritual and useless once an issue-event trigger dispatches with
nobody reading stderr. The trigger phase should abort the spawn on empty
capture (env-overridable for gh-less repos and hermetic tests). If the
warning recurs before then, pin the root cause.

## T2 — real debt, cheap, scheduled

### 3. Claude engine branch untested by this shakedown

SD-2 (implement × claude) and SD-4 (review × claude) were deferred by the
human. The engine switch's claude branch, the cookbook non-nested
`codex exec` call, and the `fallback-claude` block rest on pre-shakedown
history, not live verification. One dispatch of each closes it — natural to
fold into the first real claude-engine work item that arises.

### 4. ~~No CI or pre-push gate on the test suites~~ — shipped 2026-10-15

The protocol-content test carried two stale assertions for a full
commit-cycle because suites are run by hand — found only when the shakedown
happened to run it. A pre-push hook (or minimal CI) running the three
skill-infrastructure suites (`tests/sminos/`,
`tests/issue-tracker/`, `tests/qa-loops/`) closes the class.

**Shipped** through SSFSKIM/ci-kit. `.github/ci-kit.yml` names one gate per
suite family that runs without model calls: shell-lint (the shell files a
change touched), sminos and sminos-suites, issue-tracker, board-api,
claude-code (its hermetic tier), mods, triaging-feedback, and
repo-checks. Every pull request gets the checks, which run in parallel on
GitHub's free hosted runners in about 8 minutes. `ci-gate`
from any worktree runs them for a commit without a PR. The checks are not
required: a red one does not block a merge. Still local only: the
suites that call a model, board-api/integration (Docker and
`$ARKHO_DIR`), and anything that tests the installed plugin cache.
codex-companion is not gated in CI because it is discarded (owner,
2026-10-16).

### 5. Self-hosted runner registration (external dependency)

The automated review trigger (PR event → `pr-review-dispatch.yml` →
`review-dispatch.sh`) needs a runner labeled `claude-review`; registration is
blocked on org admin for IDA-solution/ida-solution (tracked there as #302).
Blocks both engines equally; the board's cron sweep stays deliberately
un-armed meanwhile. Manual `review-dispatch.sh <PR#>` is the interim path —
proven by the shakedown.

### 10. Answer relay: L2 automation and L3 surface unbuilt

FD-9's "park = pause, not death" shipped its L1 on 2026-07-12
(`board-answer.sh` + protocol/wake-ritual clauses — the human runs the relay
by hand at wake). L2 (an issue-comment event triggering the relay so an
answer resumes the bound worker with nobody at the keyboard) belongs to the
same unattended-dispatch phase as items 1–2 and shares their machinery and
their gating. L3 (BOARD.html rendering per-ticket attach/resume affordances
from the registry binding) is a cheap board-map touch, independent of the
trigger phase. Design record:
`2026-07-11-symphony-comparison.md` §FD-9.

## T3 — accepted / cosmetic

### 6. Two-hop board restore after review-side transient parks

The schema deliberately has no `needs-human → in-review` edge (a park should
not be undone without work resuming), so an operator retrying a
transiently-failed review does `needs-human → in-progress → in-review` with
notes. Correct but chatty. Only worth a schema edge if transient review
parks become frequent — FU-6/FU-7 removed their dominant cause.

### 7. Work-alone is prompt-enforced

Nothing mechanically blocks a codex worker from calling collab tools; the
engine blocks forbid it by name and round 4 obeyed. Consistent with the
repo's skills-are-behavior philosophy. Escalation if ever violated
post-clause: disable collab tools via spawn-time `-c` config.

### 8. `SSL_CERT_FILE` is macOS-specific

**RESOLVED 2026-07-12**: `_codex_launch` and `review-engine.sh` now probe
`/etc/ssl/cert.pem` (macOS) then `/etc/ssl/certs/ca-certificates.crt`
(Debian/Ubuntu) and export the first hit; `infra/worker-host/env.example`
also pins the Linux path explicitly as belt-and-suspenders. Remaining
exposure: other distros' bundle paths — extend the probe list if a non-Debian
host ever appears.

### 9. Accepted notes (recorded, no action intended)

- **GH_TOKEN in worker env** — visible to the worker's subprocesses; parity
  with what claude workers reach via the keychain, recorded in FU-3's
  security note. A narrowing recipe now exists (token-wired remote: push
  scope in the clone's remote URL, board scope in env — see
  `2026-07-12-managed-agents-steals.md` §steal-3); apply it when
  provisioning a dedicated worker host, where scoped tokens are real. On
  this Mac the keychain token is full-power anyway, so the note stands.
- **Mini ssh probe noise** — codex's `keepRemoteControlAwakeWhilePluggedIn`
  probes the unreachable `mini` host at spawn; user config, harmless.
- **FU-2 known limitation** — a daemon resumed once and never
  spawned/resumed again leaves its run scratch un-swept until the next
  spawn; growth is bounded by active resuming.

### 1 + 10-L2: SHIPPED 2026-07-18 — the unattended sweep

`skills/issue-tracker/scripts/board-sweep.sh` (cron/launchd tick; arming in
`references/sweep-setup.md`) closed both items: RECOVER gives dead/stalled
in-progress workers a bounded resume (3 attempts, then park `needs-human`
with an orientation note — resume, not re-dispatch, per the Symphony
comparison §2.1), and RELAY resumes a parked `needs-human` worker when a
fresh human comment lands on its ticket (`board-answer.sh --posted`, with
the relayed-comment id recorded in the meta as the re-fire guard). Item 2
was verified NOT APPLICABLE on the one-harness pipeline: the gh-token spawn
capture existed only in the retired codex-spawn path — `claude --bg`
workers reach gh through the keychain, and `execute-dispatch.sh` spawns
nothing but those. Item 5's runner remains unregistered; the sweep is the
transport that needs nobody's permission, and all three lanes now ship
event templates for the runner day (`pr-review-dispatch.yml`,
`issue-dispatch.yml`, `land-on-approve.yml`).

## Resolved since tracking began

- **Dual skills source** (was the release-gating open question): the
  codex-side doperpowers marketplace plugin was uninstalled on this worker
  machine 2026-07-11 (`codex plugin remove doperpowers@doperpowers-dev`,
  orphaned hooks.state block cleaned, config backup
  `~/.codex/config.toml.bak-doperpowers-uninstall-20260711`). Verified by
  negative probe: a non-vendored workspace now surfaces **zero**
  `doperpowers:*` skills; FU-4 vendoring is the single source. The
  `doperpowers-dev` marketplace listing remains as the reinstall pointer.
  New worker machines must repeat the uninstall (or never install the codex
  plugin) — vendoring needs no install.

## `.smns` project log residue (2026-10-14, PR #192)

Left by the branch review's fix wave and the second live pass; context in
the spec's Decision Log entry "the branch review round"
(`docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`).

- **T2 — `send` to a seat-less member keeps the retire race.**
  `send_to_member` pushes to the member it read; a retire between that
  read and the push gets one frame. The window is milliseconds; the owed
  path (`deliver_next`) re-reads under the delivered lock and does not
  have it. Trigger: a retired interactive session receives a frame.
- **T2 — seat records keep `host` after a machine rename.** The daemon
  carries unpushed writer files to the new name, but seat records keep
  the old `host`, so `identity_local` treats them as another machine's in
  the resume and peer checks. Trigger: the first machine rename on a
  registry that holds seats.
- **T2 — two machines with one name strand the pre-attach stream.** Writer
  files are named by `DAEMON_HOST`, so a registry that wrote events under a
  name another machine later claimed cannot publish them under a new name;
  the refusal says so and names the two recoveries that hold. Keeping the
  name and removing the departed machine's claim works only when it pushed
  nothing under the name; otherwise the merge still meets its
  `<name>.*.jsonl` files. A carry that rewrote the files under the new name
  was tried in PR #192's fix wave and withdrawn after the re-review
  reproduced four defects in it (spec Decision Log, 2026-10-14). Durable
  fix: name writer files by the instance id in `machine.json` (§3), its own
  initiative. Trigger: a second machine joins a mirror under a name already
  claimed.
- **T3 — late exports carry the export time as `ts`.** A mark written
  while retired, or one a Stop missed, is exported later and sorts by
  export time; its own time is in `src`. Trigger: a reader needs the
  mark's own time; then `message` events take `ts` from the transcript
  record.
- **T3 — two seats of one project holding one session** resolve to the
  one whose seat id sorts last. Trigger: a legacy registry with such a
  pair misroutes.
- **T3 — a moved seat lists twice** from a directory in no project
  (deferred M2 review finding; addressing de-duplicates by seat id).
- **T3 — the sminos suites' timing assertions: fixed 2026-10-15 (ci-kit
  M3), what remains.** The class: a test that asserts how fast a loaded
  machine produced an event (TECH-DEBT's earlier list: the git-mirror
  delivery's 2 s bound, `send --wait`'s ack window, "at most once more", the
  watcher's finalize-vs-retire, `test-bridge-requests.sh`'s window cases,
  `test-uplink.sh`'s "still in the fetch"). Each is now event-driven, in its
  own commit on the ci-kit adoption branch. The suite polls with `wait_until`
  (`until_true` in the sub-suites) under one 30 s liveness ceiling
  (`LIVENESS_SECONDS`). Proven on GitHub-hosted runners under `stress-ng
  --cpu <2×nproc>`: failing before, 20 of 20 after (PR body). Under that
  load, three more failures turned out not to be timing at all:
  - kill-before-settle: the inbox stand-in held a liveness probe's empty
    connection, so the tick was killed before it pushed;
  - the watcher case read the seat id before the spawn renamed its
    record;
  - the Python suites' inbox stand-ins (`test_policy_requests.py`,
    `fake_holder.py`) recorded a frame after closing the connection.

  What remains:
  - `test-bridge-requests.sh` waits 2 s on the clock (`seen_waiting`)
    before a dialog's record leaves `waiting`. The bridge's watcher reads
    the record every 0.25 s and exposes no sign of having read it, and the
    owner declined adding one. If it flakes in CI, the run is a bug for the
    owner.
  - "reading chat is the first sminos instruction" was never a timing
    assertion: it failed deterministically from a checkout path through a
    symlink (`/tmp` on macOS), where the test's unresolved `REPO_ROOT`
    mismatched the CLI's resolved `{{SMINOS_CLI}}`. Fixed 2026-10-16
    (Arkho #82): the suite resolves `REPO_ROOT` with `pwd -P`.
  - Speed claims that only 8× load breaks (`stress-ng --cpu 32` on 4
    vCPU; all pass 20/20 at 2×) are left as their owners wrote them:
    - `test-uplink.sh`'s "an event from the hub reaches m within a second
      while the fetch hangs", 17 of 20;
    - `test_session_plane.py`'s `test_a_presence_within_a_second`, 8 of 20.
    Under ci-kit §6 these belong in a pinned-core `perf` gate, not a
    correctness gate. Trigger: a failure in the CI gates, or that gate.
- **T3 — a compact's nonce is lost when the RPC ledger is unreadable at
  start and repaired later.** `sminos_rpc.py` (desk DC7 final fix):
  compact command ids are restored from the ledger only when it loads at
  start; a ledger read fail-closed then (every RPC refused) and repaired
  while the daemon runs restores none, so a compaction already queued at
  turn end is relayed with `rpc: null`. Display only (DX4 `compact`).
  Fix: restore them on the re-read that clears the fail-closed state.
  Trigger: a ledger seen unreadable at a daemon start.
- **T3 — a non-`OSError` from the RPC claim's write leaves that RPC
  unanswered.** `sminos_rpc.py` `Rpcs.run()` (desk DC7): the claim's
  `ledger.put` catches only `OSError`; anything else (a value the JSON
  writer cannot serialize) escapes after planning, so the nonce leaves
  flight with no outcome. The claim holds only strings and numbers, so
  nothing reaches it today. Fix: treat any exception there as the
  `OSError` case (`failed`, nothing ran). Trigger: a field of another
  type added to the claim.
- **T3 — an uplink POST past its 60 s deadline can leave its worker
  alive.** `sminos_uplink.py` `post()`/`exchange()` (desk DC4 M3): on the
  whole-exchange deadline the main thread shuts `HTTPConnection.sock`,
  but `http.client` drops that attribute after `getresponse()` for an
  HTTP/1.0 or `Connection: close` answer, so a body trickled faster than
  the socket timeout keeps the abandoned worker and its socket until the
  hub finishes; `NotDelivered` then reconnects in the same process, so
  repeats could accumulate them. Stop and orphan exit are unaffected.
  Fix: keep the response's socket for the deadline's cleanup. Trigger: a
  hub or proxy seen trickling answers, or an uplink's thread count
  growing.
- **T3 — a forged position under one of this machine's session ids leaves
  a lock file.** `sminos_hublog.py` `spend_own` (desk panel fixes): a
  refused event at `<machine>/<uuid>` is spent under that writer file's
  lock, so a lying hub naming session ids this machine never ran leaves
  an empty `<machine>.<uuid>.jsonl.lock` in the log per id. Harmless (git
  excludes `*.lock`, no reader opens them). Fix: spend without the lock
  when no writer file exists and no local session holds the id. Trigger:
  lock files accumulating in a hub project's log.
- **Backlog, not debt — the other bridged RPCs could reconcile from the
  child's kept answer.** Only `steer` sends its nonce (`rpc`) with its
  bridge command (desk panel fixes, scalpel-2#2); an `interrupt`, `model`
  or `compact` claimed before a stop is still answered `interrupted`,
  though the child would keep its answer under the nonce if the daemon
  sent it. Worth it once a stop mid-RPC is seen in practice.
- **Backlog, not debt — MAWS async questions never reach the log** (§9 of
  the spec). Under `MAWS_NATIVE_TO_HUMAN` asks go through `mcp__maws__ask`,
  whose answer shape MAWS owns. Deserves its own ticket; MAWS sessions are
  the ones most affected.

## to-human style (2026-10-15, 7.158.0)

- **About 1 report in 30 comes back with no `<message>` wrapper.** In the
  ⚠ micro-test (`tests/output-styles/to-human-affected-eval.py`),
  4 of 124 final reports from Opus 5.5 under the full style were written
  unwrapped, so the view would fold them into the working record and the
  human would not see them. The rate did not differ between the 7.157.4
  style and the variants. The test sends no per-turn style reminder, which
  real sessions get, so the live rate may be lower. Trigger: a transcript
  audit of interactive to-human sessions, counting final turns with text
  and no mark, that finds the same order of rate.

- **The ask mod's transcript row does not draw the person's "Chat about this"
  feedback or an answer's notes.** `askRow` reduces the feedback to a "User
  declined to answer questions" row and `answerRows` drops added notes
  (`hooks/mods/ask.tsx`). An async answer delivered while the session is idle
  arrives as a plugin prompt carrying their words whole, which the view keeps
  as the person's (`ASK_DELIVERY` in `to-human.tsx`); an answer that reaches
  the model while it is busy, as context on a tool result, leaves no delivery
  row, so the report shows neither. Fix: draw the feedback and notes in the
  ask row; the delivery row could then fold as a duplicate. Trigger: the
  person's feedback or notes found missing from a report, or the next edit to
  `askRow`/`answerRows`.

## to-human view in the fullscreen transcript (2026-10-16, engine 2.1.302)

- **A wheel or trackpad scroll up jumps back down, 6–30 rows at a time.** It
  is the engine's, not the mod's logic: the transcript's virtual list counts a
  row it never mounted at 3 lines, a row a plugin draws mounts at 0 lines
  until the plugin answers, and the anchor correction is skipped while a
  wheel scroll is still draining, so a stretch of rows that turns out shorter
  than assumed moves the view. The report view draws most rows empty, so it
  hits this hardest. Measured on a resumed session, three fast bursts × two
  launches: no render-hook plugin 0 jumps; this plugin with every hook
  passing through 1; the report view 10. PageUp, a slow wheel, and a second
  pass over rows already laid out never jump. Nothing in the render API lets
  a mod avoid it; the fix belongs in the engine (keep the anchor delta during
  a drain, or hold a pending plugin site at the assumed height). Workaround:
  PageUp/PageDown. Reported upstream as anthropics/claude-code#102893, with a
  bare repro mod (tool rows drawn as an empty `Box`: 14 jumps in 18 bursts).
  Trigger: an engine release whose virtual list changes, or the issue being
  answered.
- ~~**Run boundaries follow the order rows first draw, which in fullscreen is
  not transcript order.**~~ **Fixed in 7.162.0**: each row's place is read
  from the transcript file on resume (a `grep` of row ids and call ids) and
  taken from each `session.append` after, and drawn rows sort by it. In the
  resumed-session repro, PageUp through the whole report found two
  back-to-back `[ working record ]` sites before and none after.

## interim-notification filter (2026-10-17, 7.165.0, PR #218)

- **Every drop leaves an engine row, "Prompt dropped by a hook: …".** The
  filter stops the wake, but the human still sees one row per dropped notice
  in the engine view and the to-human view. The row is the engine's own
  `system`/`informational` notice for any `prompt.submit` that ends without
  entering, drawn by a component that raises no render hook, so no mod can
  fold or hide it. Fix belongs in the engine: a render hook for system
  notices, a silent consume at `prompt.submit`, or the drop row at level
  `info`. Trigger: an engine release that adds any of those.
- **A queued notice is missed when its agent has already left the agent
  list.** If main reaches a queued interim notice after the agent finished
  (main in one long tool call meanwhile), `$.agent.list()` no longer names it
  and the notice passes as an unknown agent's (live round 2, R6r). Costs one
  stale notice beside the report, never a report. Trigger: stale notices
  showing up often enough to matter.
- **Collision residual.** The filter cannot tell an agent whose whole answer
  is byte for byte the engine's waiting sentence from the engine's
  placeholder in two cases: a fork that inherits its parent's hand-back
  reminder with its own contract off, and a queued notice checked against a
  later run's reminder after a permission-mode change. Only that exact
  sentence can be lost. Trigger: any observed agent-authored answer equal to
  the placeholder.
- ~~**A first notice that entered mid-turn is not seen.** The engine folds a
  notice that arrives during a tool call into that call's `tool_result`
  (under its system-notification frame), and the conversation check reads
  only user text, so the next repeat passes once more; the one after drops
  (live round 3, W-mid).~~ **Resolved in 7.171.1**: the check also counts a
  notice folded into a `tool_result`, directly under the engine's frame and
  alone in its reminder, as the API view renders it (confirmed live on
  2.1.302: the second and third notices dropped, the report arrived). It
  had let 4 of the 50 interim notices through in MAWS `37052769`. The
  residual, a tool output forging that exact fold for a live agent's task id
  and worktree, costs one placeholder and is stated in the mods README.
- **A quoted notice counts as delivered.** The worktree and orphan rules ask
  the conversation (`$.session.messages({ as: 'api' })`) for an earlier
  notice of the task, and that view keeps only role and text, so a user-role
  text quoting a notice with the same task id and worktree (a fenced example,
  a pasted transcript, a peer's relay) satisfies it and the first real
  notice drops (review round 3). A relay carries the same text the notice
  would; only a fabricated quote of a live agent's exact id and worktree
  loses anything, and then only the worktree path or the orphan's first
  notice, which the agent's report and final notice carry again. Cheap
  hardening if it ever matters: anchor the match to a text block that opens
  with the notice or the engine's notification frame. Trigger: a dropped
  first notice traced to a quote.
- **Engine loss, with or without the filter.** An auto-mode subagent that
  writes its report as plain text while its own background shell runs, and
  is then killed while parked, loses the report: the engine withholds the
  text behind the placeholder, and the kill sends no notice because the
  interim notice already claimed `notified` (live S8, both arms). Trigger:
  report upstream, or an engine release that changes `dT`'s `notified` guard.
- **`ask.tsx` type errors against the 2.1.302 typings** (lines 1462, 1504),
  seen by `tsc` during this work; the mods tests pass. Trigger: next
  `ask.tsx` change.

## devcloud secrets mod (2026-10-16, spec 2026-10-15-devcloud-design.md)

- **An oversized output can ship raw if the process dies mid-call.** The
  engine persists a large tool output to `tool-results/` before the mod's
  `tool.call` hook rewrites it scrubbed; a kill in that instant leaves the raw
  file, which the person's session store ships after its settle interval.
  Accepted at design (Decision Log, round 3). Trigger: a raw value found in
  the session store's copy of a `tool-results/` file, or the store gaining a
  reader other than the person.

## sminos bridge: a delivery wakes a stopped session (2026-10-17, e269230e)

- **A late stop drop can be lost with no refusal when its post fails.** A
  delivery the engine drops for a stop after the mod answered `submitted` goes
  to the child as a keyed `inbox` event. If the post carrying it fails before
  the child takes it in, the poster replaces the batch with a gap and a resync
  (bridge-stream.tsx), and neither carries inbox work. The message is then
  lost, its mark stays, and the daemon is never told it `failed`. Two things
  must happen together: a prompt queued in the instant the session turned
  busy, then an Esc; and a failed post to the child's local socket. Trigger:
  a delivery reported lost with no refusal, or the poster's resync gaining
  retained work for another reason.

## sminos plane: the live chain (2026-10-18, PR #239)

- **A row whose parent never comes stays unmarked, and so does all that
  follows it.** The chain places a row only once its parent is placed (the
  engine writes a child a few ms ahead of its parent around a session's
  start). A transcript whose first row names a parent outside the file — 1 of
  1,500 on this machine, a resumed subagent — leaves every row unplaced: the
  desk draws them all, as before the chain. The engine's loader treats such a
  row as a root. Trigger: a transcript the desk draws with a dead branch whose
  rows the plane left unplaced; then place a parent that has not come after a
  bound (rows read) as a root.
- **An Esc's retraction lands with the branch's first row, not at the Esc.**
  The interactive engine writes nothing when an Esc hands a prompt back; the
  rows it left behind go off when the next row is written (the prompt sent
  again, a delivery, a system notice). Until then the desk draws them as
  live. Its SDK rewind writes a `last-prompt {rewound: true}` anchor, which
  has no uuid and is no row here. Trigger: the owner reading a handed-back
  prompt as sent, or a desk-side rewind control (whose anchor the plane would
  then read).
- **An Esc that empties the conversation leaves no branch.** When the Esc
  hands back a session's first prompt (nothing before it), the engine writes
  its next row (a re-appended delivery, the wake) under the file's stale
  leaf, the abandoned turn's last row. The file's chain then runs through the
  prompt the live conversation no longer holds, and the engine's own resume
  would rebuild it too. The only trace is a `last-prompt {leafUuid:
  "00000000-…", explicit: true}` written after the next turn's first rows
  (2.1.300 class `ydt`): it says a rewind happened, not where. Seen in
  #238's evidence (run 7, `restore`). The desk keeps #42's frame-line fold
  for the delivery; the prompt draws as read. Trigger: the engine writing
  a null parent there, or a rewind trace that names the cut.
