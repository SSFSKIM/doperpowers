# Tech-debt tracker — codex-workers live shakedown residue

> **Why this doc exists.** The 2026-07-11 live shakedown
> (`2026-07-10-codex-workers-shakedown.md`) fixed every defect it surfaced
> (FU-3…FU-7) but left a residue of known, accepted frictions. This file
> was written as their tracker while GitHub Issues were disabled on this fork,
> and it still tracks them. Each item carries a
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
| 33 | T3 | Two board readers disagree about a seat whose recorded status is `awaiting-human`. `_sweep_api.sh`'s `_liveness` reads every status outside working/blocked/idle/error as dead (PR #158, dp#60), so such a bound seat's lease is withheld and the relay refuses it, while `board-answer.sh` still accepts it as a seat waiting for answers. When #158 merged this took the lease from any worker that had parked itself with `sminos mark` (the #60 review, 2026-10-18). `mark` and its judgment statuses left in 7.125.0 (#185) and nothing writes `awaiting-human` now, so only a pre-7.125.0 record can carry it, and any such run was reclaimed long ago. Drop the status from `board-answer.sh`, or read it as live in `_liveness`, so the two agree | The next edit to either reader, or a record found carrying `awaiting-human` |
| 34 | T3 | `sminos who` follows a hand-off chain (`continued` → `to`) to its last session within the project the chain started in. When that last session later moved to another project known here (a background job that ran `sminos join`), `who` draws it from the old project: the old project name, the alias it had there, and a `say --in <old project>` note line that never reaches it (its override resumes it in the new one). Lineage is per-project, so the new project holds no `continues` link back. Fix: end the walk on a `moved` to a known project and draw the session from that project's view (review of PR smns-session-address, 2026-10-19) | A hand-off address resolved to a stale project in practice |
| 35 | T3 | A `claude --bg "<prompt>"` job joins sminos under its prompt text as its alias (the harness's first name for it, `nameSource: auto`), and `held_alias` keeps that alias over the title the harness later gives it, because a generated name never replaces an alias already held. `list` shows the whole prompt as the member's name. The address line works around it by naming the short alone (`ADDRESS_ALIAS_RE`); the alias itself is unchanged | Next touch of `held_alias` / a bg member's naming |
| 36 | T3 | ~~`hooks/mods/address.tsx` asks the sminos CLI on the request path~~ **SHIPPED 2026-10-21** (sminos 1.5.3: a kept line past its time is served at once while the CLI is asked in the background, so only a session's first ask waits; the line is asked for every ten minutes, not every minute) | — |

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
change touched), sminos and sminos-suites-a/b/c, issue-tracker, board-api,
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
    - `test-uplink.sh`'s "a web human reaches m within a second while
      the fetch hangs" (RL10; its DX2 original, since removed, passed 17
      of 20);
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
- **T3 — a forged position under one of this machine's session ids leaves
  a lock file.** `sminos_hublog.py` `spend_own` (desk panel fixes): a
  refused event at `<machine>/<uuid>` is spent under that writer file's
  lock, so a lying endpoint naming session ids this machine never ran leaves
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
- ~~**Open — a session MAWS launched is no project member, so nothing of it
  reaches the log**~~ **Resolved in 7.184.0**: the owner ruled MAWS
  sessions members (2026-10-18); MAWS sets `SMNS_MEMBER` to its own pid on
  every engine it spawns, and the hook, the bridge's child and a verb the
  session's tools run admit an SDK run whose engine that pid spawned
  (`member_mark`, the spec's Decision Log).
  Was: (board #76's finding). The readers know MAWS's ask now
  (`mcp__maws__ask` with `blocking` false and its `[MAWS ask <id>]` steer,
  `extract_asks`, and the bridge's export), but MAWS launches every session
  with `CLAUDE_CODE_ENTRYPOINT=sdk-ts`, and an `sdk*` entrypoint never joins
  on sight (the M3 ruling that keeps headless runs out, `joinable`). So a
  MAWS session records no `joined`, no message, no question, and the desk
  has no presence or transcript for it. Admitting it is a membership
  decision (presence, deliveries and `@all` reach it too), and MAWS sets no
  marker of its own on every launch to tell its sessions from another
  TypeScript SDK tool's. Trigger: the owner's call on whether MAWS sessions
  are members.
- ~~**T3 — an answer reaches the log only at the session's next Stop.** The
  bridge exports an async question as its call and acceptance are written,
  but no answer row (the plugin's delivery, MAWS's steer): an answer taken
  into a long running turn shows on the desk, and in `chat --host`, as open
  until that turn ends. Fix: export the delivery and steer rows in
  `exportRow` too (the `prompt` row, and the attachment rows as the
  bridge's doors present them). Trigger: an answered question seen open on
  the desk for long.~~ **Resolved in 7.185.0**: the owner ruled an open
  async question counts on the desk until it is answered (2026-10-18), so
  `exportRow` now hands the child every main-loop row that may answer one,
  as it is kept: the `prompt` row (the plugin's delivery submitted while
  idle, MAWS's steer as the human's prompt) as kept, and the
  `hook_additional_context` (door `hook-context`) and `queued_command`
  (door `delivery`) attachments, their payload read back from their
  renderings, the only form the hook is handed (`answerRecord`): the
  engine's exact framing stripped, the queued prompt whole, so a message
  that quotes a steer is read as written and answers nothing. The child's
  `host_events` decides, under the Stop hook's `(kind, src)`, so the Stop
  appends nothing more (`tests/sminos/test-bridge-export.sh`). What still
  waits for the Stop: an answer past 65,536 characters; a prompt row the
  transcript keeps with no origin (the hook reads it as `unclassified`,
  which sminos does not take for the human); an attachment whose rendering
  is not in that framing, or holds `&lt;` (the engine's escape of a
  system-reminder tag, which a literal one typed by the human reads the
  same as). Residual: a context attachment's entries
  reach the hook joined a line apart, so a line another hook appended after
  a delivery in the same attachment would ride in that answer's `text` (its
  `src` is right); none of the 66 delivery attachments in this machine's
  transcripts (2.1.300–2.1.302) held one. This plugin can write one: in
  auto mode, when the call that carries a held answer is blocked, the
  appeal mod (outer to the ask's `tool.call`) appends its block notice
  after the answer, and the live `answered` text then ends with that notice
  and wins the `(answered, src)` key over the Stop hook's clean reading.
  Fix: the ask mod records the exact entries it attached and the bridge
  exports those, or skips the live export when anything follows them.
  Trigger: an `answered` seen in the log ending with an appeal notice.

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
- **An older subagent's transcript hides some of its own rows (to-human
  0.7.4).** A row no loop was seen to keep stands in no run. A subagent that
  ran before the module loaded is one: its rows were never appended under its
  `agentId` while this module ran. A prompt row of such a loop that reads as
  working record draws nothing, as a queued delivery's preview does. Its own
  instructions (origin `coordinator`) still show. What stays hidden is the
  rest: its tasks' notifications, a nested agent's hand-back. The band's
  `full transcript ›` draws them. Telling them apart from a queued preview of
  the main conversation's needs more than the event says. T3. Trigger:
  someone needs those rows in an agent's transcript.

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

- ~~**A late stop drop can be lost with no refusal when its post fails.**~~
  **Gone 2026-10-18** (smns-esc-owner): a delivery the engine drops for a
  stop no longer travels as an `inbox` event; its words go in as a row
  (`$.session.append`), so no post carries them. What a failed post can still
  lose is the wake (next item).
- **A wake is lost when the post carrying it fails.** The bridge's `inbox`
  event (the wake after a stop) is not retained work: a failed post to the
  child's local socket replaces the batch with a gap and a resync
  (bridge-stream.tsx), which carries no wake. The delivered row is in the
  conversation, so nothing is lost, but the session is not woken and reads it
  only at its next turn. T3. Trigger: a stopped session found holding an
  unread delivered row with no wake sent, or the poster's resync gaining
  retained work for another reason.
- **A delivered text with no sminos frame line gets a wake with no
  `Unread:` line.** A wake names the rows it points at by their frame lines, so no two
  wakes are one text (the engine drops a peer message identical to its
  sender's last within 30 s). sminos frames every event it pushes, so only a
  `deliver` command sent by hand with a bare text (the live probe's direct
  path did, until it framed its texts) can produce two identical wakes in that
  window, the second dropped. T3. Trigger: a sender of `deliver` that does
  not frame its text.

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

## api tick: the successor's rescue (2026-10-18, PR #242, re-landing PR #153's review)

- **A predecessor record naming a sibling worktree of the same repository
  passes both guards.** The rescue checks that the worktree belongs to the
  governed repository and that its branch is the dispatcher-created one, but
  a stale record pointing at another ticket's worktree of the same repository
  satisfies both, so the tick would publish that ticket's branch under this
  one's recovery. Deferred by PR #153's review and still open after #242. T2.
  Trigger: a recovery tick whose predecessor record's worktree carries a
  ticket number other than its own; then bind the worktree to the ticket's
  seat name before pushing.
- **`remote.origin.pushurl` can redirect the rescue's push.** W1-6 pinned the
  recovery's reset to the commit the tick verified, but the push itself still
  follows whatever `pushurl` the worktree's config names. T3. Trigger: a
  worktree whose `remote.origin.pushurl` differs from `remote.origin.url`;
  then push to the resolved `url` explicitly.

## sminos org directory (2026-10-19)

Residue from the whole-branch review of `docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md` and its closing review.

- **`find_target` still reaches a retired project.** The fix wave filtered `org_retired` from `resolve_tag`, so a tag `@<project>/<alias>` into a project the org retired is refused. `find_target`, which `send`, `status` and `retire` use, still builds its passes from unfiltered `project_tiers(proj)` and `known_projects()` (sminos.py ~4433–4438). `send pr/stale4` therefore records a message for a remote member in a retired project's log, and the uplink never uploads it. Reaching it takes a revoked machine's project still registered here. T3. Trigger: the first revocation of an enrolled machine. Then apply the same `org_retired` filter to `find_target`'s tiers and its no-project scope.
- **`position_carry` compares positions by offset.** A position without a uuid (one `position_init` wrote on a transcript whose last row has none) can compare one row short. The cost is at most one re-exported row, never a lost one. T3. Trigger: a duplicate export observed after a move.
- **A one-tick gap in a `--bg` hand-off with a join override.** Between `hand_off` retiring the predecessor in the override's project and the successor joining there, the log alone holds no member under the predecessor's alias. A sender on another machine is refused for that interval; a local verb reconciles and finds the successor. T3. Trigger: a refused cross-machine tag during a hand-off.
- **Each Mac holds the other's machine project (F6 of the live acceptance run).**
  - Seat records with the same session ids exist on both Macs. The uplink's `holds()` (`sminos_uplink.py`) counts the plane's local members, so each machine opens the other's machine project as held, leases it as a holder, and the desk counts it among that project's machines.
  - At 2026-10-19 09:09Z on the MacBook, 8 of `mini`'s 92 members read `@macbook`, all `gone`.
  - This is legacy data: cleaning the duplicated seat records ends it.
  - T3. Trigger: a machine project's machine count on the desk misleads someone, or the next cleanup of seat records.

## sminos daemon: restart in place (2026-10-19, 7.186.1)

Residue of the review of `daemon run`'s restart in place on a code change (`restart_in_place`, sminos_daemon.py).

- **A SIGTERM in the instant before the exec is lost.** The loop reads `stop` after the uplink has stopped, then flushes and calls `os.execv`. A SIGTERM landing between that check and the exec is caught by the old image's handler and dropped, so the new image runs on. The stop then ends only at the service manager's SIGKILL: launchd's ExitTimeOut (20 s), or systemd's TimeoutStopSec (90 s), which also outlasts devcloud step 11's 60 s `systemctl --user restart`. The window is microseconds, right after a code-triggered uplink stop. The review proposed exec'ing with SIGTERM blocked (the mask and a pending signal survive execve) and unblocking it in `cmd_run`. That was declined: a rollback to code that predates the unblock would run with SIGTERM blocked for its whole life, and so would every uplink it spawns. T3. Trigger: a daemon observed running on after a stop that coincided with a plugin update. Then block SIGTERM only once the code being exec'd is known to unblock it, for example from a marker the new code declares.
- **The run lock is free for the instant of the exec.** Its descriptor is close-on-exec, so the lock is released and the new image takes it again with `LOCK_NB`. In that sub-second gap, `daemon status` reads "not running". A `daemon run` started by hand at that moment could take the lock, and the restarted image would then exit 1, leaving the service manager to restart it under its throttle. T3. Trigger: a restart in place observed exiting with "a daemon already runs". Then retry the lock briefly, or pass the descriptor across the exec.
- **A change that reverts within the settle still restarts.** (sminos 1.1.2, from the review of #289.) `settle_code` waits for the scripts to hold still but never compares the settled code with the code the loop started on. A script that changes and changes back within CODE_SETTLE therefore costs a restart. One example is the sub-millisecond gap between the marketplace refresh's two renames, when a listing could find the directory missing. This is rare, and a restart is the old behaviour. Trigger: a restart logged with no change in sminos's bytes.
- **Each restart compiles `sminos.py` twice.** `sminos.py` runs as `__main__`, so it has no cached bytecode, and both the restarted daemon and its new uplink compile it (8k lines, about 0.2–0.4 s each on a loaded host). That is most of the restart's uplink gap, which measured 0.5–1.6 s here at load average ~270, with one 4.4 s outlier. It also costs every `sminos` invocation, the Stop hook's `record` included. T3. Trigger: the gap or hook latency becomes visible. Then make the launcher import `sminos` as a module.

## plugin autoreload (2026-10-19)

Residue from the review of `hooks/mods/reload.tsx` (branch `plugin-autoreload`).

- ~~**An unanswered async question holds its session's reload indefinitely.**~~ **FIXED 2026-10-19 (7.188.5):** its trigger came with a `/reload-plugins` the human types, which the hold never covered. The ask mod keeps its asks and undelivered answers in `$.state`, which outlives a reload of the module (verified in source and live on 2.1.303: the host clears it only at the session's end; a typed `/reload-plugins` re-instantiates only the modules that changed), and the autoreload now holds only while an ask's dialog is up.
- **The watch keys on install records, while a reload loads path-sourced plugins from the clone's manifest.** A marketplace refresh with no plugin update (no record change) is therefore not acted on, and the snapshot after a reload records the record's path even where the session runs the clone's version. Harmless in the normal flow, where both move together. T3. Trigger: a missed or spurious reload observed.
- **The idle check reads the ask mod's turn flag, which leaves a few narrow windows.** (7.188.3, from the review of #260.) A look that lands between one main turn's end and the start of a prompt already queued behind it (the compact mod's resume prompt, a prompt typed mid-turn) still queues the reload behind that prompt. A module loaded mid-turn by a reload the reloader did not run (a `--plugin-dir` watch) reads idle until that turn ends. Whether a `$.command.run` issued during a compaction the bridge runs between turns waits for it is unverified. Each window is a few hook round trips wide, or needs a second install inside one turn. Since 7.188.5 a reload keeps the async asks, so what such a window can still cost is the compaction. T3. Trigger: a compaction failed with "a turn is in flight" across a reload again; then key the flag by turn id as `bridge.tsx` keys `state.mainTurn`. Fired twice (2026-10-21 07:03, session b4948247; 2026-10-24 06:07, session 050b9612): a `/reload-plugins` the tick queued during the turn that called compact ran at that turn's end, ahead of the compaction. Since 7.205.1 the compact mod tells the model the compaction did not run and hands its request back, so such a window costs one turn rather than the compaction; the reload-side fix stays open.
- **A reload the autoreloader did not run, landing while an ask's dialog is up, can let the ask be answered twice.** (7.188.5, from the review of #262.) The old module's press dispatch outlives the reload: it takes the answer, delivers it, and writes its view to `$.state`. The new module took up the ask as open at its start and never reads the state again, so it still offers the ask (band, row, the desk's pending request), and its next save writes the ask back as open. A second answer then reaches the model. The autoreloader holds while a dialog is up, and a typed `/reload-plugins` cannot be entered while the dialog has the keyboard. What is left is a `--plugin-dir` watch, or a `/reload-plugins` queued during a turn that the engine runs with the dialog showing (unverified that it does). The cost is a duplicate answer, never a lost one. T3. Trigger: a duplicate answer seen. Then keep the raised asks in the snapshot, and have the module that took them up re-read the state before it offers, accepts or saves them.

## sminos daemon CPU (2026-10-19, 7.188.1)

Residue of the fix for `daemon run` and its uplink burning a core each on a machine that follows its whole org (F1 of the org directory's acceptance run; branch `smns-daemon-cpu`).

- **A tick's engine records predate its later projects' log reads (F5).** `tick_all` reads the engine's session records once, when its first project asks, and each project's log when its turn comes. A seat spawned inside that window has its `joined` in the log but no record in the tick's copy, so its first published word is `stopped` (or `gone`), and `publish_state` publishes a first word at once. Two ticks (10 s) later the right word replaces it. Before this fix the window was the whole 10-minute tick; now it is one tick's length (about 50 ms at the Macs' scale). T3. Trigger: a wrong first word observed after this fix.
- **Passes over many sessions read a transcript index up to TRANSCRIPT_FRESH (5 s) old.** In a long-lived process, a transcript created within that window is invisible to a view's state words (`gone` for `stopped`), to `refresh_joined`, and to the seat-side hand-off scan, until the next refresh. Every write or settlement that rests on a transcript's absence or content looks again (`transcript_now`, the `fresh` rechecks, `continued_in` before an `ended`, `push_member`'s `gone`, the sweeps), a listing begun within TRANSCRIPT_SHARED (0.25 s) counting as now so that one pass's many writes share it. What remains is a view up to one refresh behind, and a write that misses a transcript created in the quarter second before it. T3. Trigger: a decision found acting on a stale miss.
- ~~**The uplink still forgets every cache each scan (SCAN_EVERY, 2 s).**~~ **FIXED 2026-10-28 (sminos 1.27.10):** its trigger came (the uplink at 5–16 % of a core idle); a scan now reads within the generation the session plane renews, and forgets only at a nudge or a welcome. See "sminos idle CPU" below.
- **The per-process file caches keep entries for removed files.** `_SEAT_FILES`, `_LOG_FILES`, `_FILE_BYTES` (sminos 1.27.11) and `HubLog.files` (its own-writer pass) drop an entry only when its file is read again and fails. Memory is bounded by the files a process has ever seen; a long-lived daemon on a machine that removes many seats or logs grows by their parsed size. T3. Trigger: daemon memory growth observed.

## sminos requests: a complete pending set on the RL10 lane (2026-10-28, sminos 1.27.2; board #149)

Residue of the bound on a raised request's input (`RAISED_INPUT_MAX`, `sminos_requests.shown_input`; PR #424). Board #153 moved it from DX2's lane to the RL10 lane, where it holds unchanged.

- **A project's complete `pending` set can still pass the RL10 lane's 16 MiB.** The bound keeps one raise at 256 KiB, but the set carries every request pending in the project as one frame (as parts), so some sixty requests at the bound at once pass `SEND_QUEUE_MAX`, and the lane ends with `NotDelivered` and reconnects, sending the set again. T3. Trigger: a daemon.log line "the RL10 lane holds more than 16 MiB unsent" with many requests pending in one project.

## sminos requests: a request raised again (2026-10-19, 7.188.2)

Residue of the daemon's relay keying settlements by request and `t` (sminos_requests.py; MAWS #65).

- **The bridge child refuses a live `raised` for an id it holds settled.** `_apply`'s `raised` branch (sminos_bridge.py) ignores it but still fans the event out. So a raise again within one child (an in-process `/resume` back to an ask withdrawn earlier in the same process) is missing from the child's pending set, and its snapshots omit the request: the daemon's complete set drops it at the hub, and a desk answer to it is refused 409 "already settled". The engine's own answer still settles it and goes up. A resync is first-wins the same way: a child that takes two settlements of one request from the mod's list keeps the earlier. T2. Trigger: an ask found unanswerable from the desk after an in-process `/resume`, or the next edit to `_apply`. Closes when the child takes such a raise as pending again and forgets the earlier settlement, with a case in `tests/sminos/test_policy_requests.py`.
- **The mod stamps a settlement's `t` twice.** `settle` (bridge-requests.tsx) keeps one `Date.now()` in `state.settled`, and `emit` stamps the live event with another, so the two can differ by a millisecond. A child the same module respawns (`startChild`, after its child exited on its own) takes the settlement from the resync's `state.settled`, after the old child fanned out the live event: it can then list it under a `t` the daemon never relayed, and it goes up again. (A lost live post sends it once, under `settle`'s stamp; a reloaded module's resync lists no earlier settlement.) If its request is pending again, the same snapshot lists it pending and the settlement is passed by; otherwise the hub takes it as a resend. T3. Trigger: a settlement seen relayed twice. Then stamp once.

## async asks in a copy of a session (2026-10-19, 7.188.10)

Residue of rebuilding a copy's asks from the conversation it copied (`historyAsks` in ask.tsx) and of exporting its answers under the asking session (`append_host`, `position_init`'s `since` in sminos.py). A copy is a session the engine starts under a new id with the original's conversation: `--fork-session`, a `--bg --resume` while another process holds the session, `/branch`.

- **A copy does not rebuild the asks from before its last compaction, or past the newest 4096 messages.** What the engine copies, and what `$.session.messages()` holds, starts at the compaction boundary, so an ask asked before it is not in the copy, nor in its own later resumes (its transcript starts at the boundary too). Each form of `$.session.messages()` also keeps only its newest 4096 messages, which a long tool-heavy stretch on a 1M-context model can pass; that cap hides an ask, never marks one wrongly (the rows form, the narrower window, is where the calls come from). `/branch`'s transcript, written before the session starts, is read whole instead. The original still holds the ask, and shows it when resumed. Two ways to close it: restate the asks still open into the conversation after a compaction stands, which carries them past every boundary for every rebuild and for the model (it changes what the model reads, so it is the owner's call); or find the boundary's home transcript by the ask's tool_use id and its `logicalParentUuid` (0.1–1.6 s, and ambiguous across earlier copies). T2. Trigger: a question missing from a copy observed.
- **A copy reads an answer given as context from the model's rendering of it** (`HOOK_CONTEXT`, the engine's `ROe` on 2.1.302). The rows form leaves that answer out. If the rendering changes, a copy shows such an answered ask open, and the human could answer it twice. T3. Trigger: the engine version changes (recheck as the interim audit is rechecked).
- **A copy's export leaves out records older than its SessionStart hook's clock.** The copied records keep their own times and every later one is newer, except a record entered before the hook ran (a prompt the human typed within its first instant), which is not exported. A prompt is no host event; only an answer or a mark in that instant would be lost. The filter also takes every copied record as exported by the original, which holds once the original reached a Stop after it or the bridge exported it live: a tail the original never exported (it crashed mid-turn without the bridge, or its bridge's child had not taken the rows when it exited) is exported by no one until the original is resumed and stops. The fix, if it matters: export the copied records' events whose (kind, src) no other writer of the machine holds, as `_askers` looks up questions (the copied records keep the original's uuids and call ids). T3. Trigger: a copy's first mark or answer missing from the log, or an original's last turn missing after a fork.
- **An answer a copy gives does not close the ask in the original.** The original's transcript never holds it, so the original, resumed, offers the ask again. An answer given there has the same (kind, src) key and is dropped from the log, which keeps the copy's answer. This follows from the engine's fork, which splits one conversation into two. T3. Trigger: an ask answered twice, once in a copy and once in the original.

## sminos guide on the engine's start paths (2026-10-19, 7.189.1)

Residue of board #99's fix (the guide on `/branch` and an in-session `/resume`; PR #269).

- **An in-session `/resume` can be guided under a name its record does not take.** (From the review of #269.) When no record names the session yet, `_hook_engine` names it by the payload's `session_title`, else by the process's current name. That matches `/branch`, which renames the process to the branch's title as the user's. After an in-session `/resume` the engine instead renames the process from the resumed transcript's agent name (as the user's when the transcript has a custom title, else `auto`), and keeps the process's name when there is none. So a session renamed by custom title alone, one whose title and agent name differ, or a former `--bg` job (agent name `auto`) reads an alias in its guide other than the one the log joins it under; its short, project and machine are right. T3. Trigger: a resumed session found addressing itself by the wrong alias. Then, for `source == "resume"`, take the name from the transcript's last `agent-name` as the engine does.

## the bridge's raise and the secrets guard (2026-10-19, 7.189.3)

Residue of raising a permission with its call as the bridge's `tool.call` hook was handed it (bridge.tsx), so a handle the devcloud guard restores beneath the bridge never reaches the desk.

- **A raise shows the call before any rewrite beneath the bridge.** With doperpowers seated outside the other plugins (`prependPlugins`), a settings PreToolUse hook's `updatedInput`, and every other plugin's `tool.call` hook, run beneath the bridge. The desk then draws and digests the model's call, and an allow runs the rewritten one. Today nothing rewrites a permission's input beneath the bridge on the owner's machines: the user PreToolUse hooks return no `updatedInput`, and only the ask mod rewrites, and only its question dialogs. Two ways to close it: a `rewritten` flag on `raised`, carried through sminos_requests.py and the hub, so the desk can say what runs differs (under the guard that is only at the handles); or leaving a permission whose engine form differs from the bridge's view beyond the guard's handles to the terminal, which couples the bridge to devcloud's handle grammar. T2. Trigger: a rewriting PreToolUse hook or plugin configured on a machine running the bridge.
- **A result the guard scrubbed, when doperpowers sits outside devcloud, reaches the desk as its record, not as the model read it.** devcloud answers `{ result, context }` with no `text`, so the bridge's `tool` result event draws that scrubbed record (a string whole, a content-block array as its text blocks, any other record as JSON; `shownText` in bridge.tsx, whose fallback also draws this plugin's own hook-answered tools (ask, compact, appeal), which posted no text before), since core's text holds the values; the tool's own mapper, which turns a record into the model's text, is not reachable from a hook. The same result gives an interrupt no text to find a backgrounded Bash's task id in, so a desk interrupt during a Bash whose output the guard scrubbed leaves that shell running. T3. Trigger: the desk's drawing of such results found unreadable, or a desk interrupt that left a shell running; then read `backgroundTaskId` from the record for the interrupt.

## appeal's pass and the secrets guard (2026-10-19, 7.190.0)

Residue of appeal leaving no pass for a grant whose call carries a guard's handle (`carriesHandle` and `applyRuling` in hooks/mods/appeal-judge.tsx, `NO_PASS`), found by the sminos plugin's M3 review.

- **A grant on any call that quotes a handle leaves no pass, though the guard restores only some tools' input.** The rule's premise, that the guard beneath appeal restores the handle before the permission check so the pass keyed on what appeal saw never matches the re-run, holds only for the tools devcloud restores into (`RESTORED` in devcloud/hooks/mods/secrets.tsx: Write, Edit, MultiEdit, NotebookEdit, Bash), and only where a guard is loaded. A subagent's call to another tool, or a main-loop call to a tool appeal never relays (`NOT_RELAYED`: Agent, AskUserQuestion, Workflow), whose input quotes a handle reaches `tool.check` unchanged, so its pass would have matched: the grant is inert, `NO_PASS` gives the model a reason that does not hold, and each re-run is a fresh block to appeal. Left as it is because it errs safe (no pass is ever applied to a call it does not match) and is narrow (a handle quoted in such a call), and because the fix copies devcloud's restore set into doperpowers, a second place to keep in step with the guard. T3. Trigger: a granted appeal observed inert on such a call, or devcloud's restore set changing. Then leave the pass when the tool is not one the guard restores, reading the set from a contract devcloud publishes rather than a copy.

## to-human's reload line after a compaction (2026-10-20, to-human 0.3.1)

Residue of the reload line's hook reading the conversation for a mark when a reload that updated to-human has started its module over (since 0.3.2 the module's start-up read, `started` in to-human/hooks/mods/to-human.tsx), found by its review.

- **A session that compacted and has sent no mark since reads as one that never sent one.** `$.session.messages()` starts at the last compaction, so when to-human is updated while a session sits idle after a `/compact` the person typed (the autoreload runs only between main turns), the reload line reaches the report and the view stays unfolded until the model's next message. The compact mod's own compaction is followed by a resume turn whose reply usually carries a mark, and a reload of any other plugin keeps the module and its state. To close it, keep the view's state (`hasSeenMark`, and `isFullTranscript`, which a fresh module also resets) in `$.state` under a to-human contract, as the sminos ask keeps its asks. The catch: `$.state.set` is refused while a `ui.render` hook draws, and the mark is first seen in one, so the write has to come from another event (the response row's `session.append`, the band's press). T3. Trigger: the reload line, or an unfolded view, seen after a to-human update in a compacted session.

## the fullscreen transcript's hold, released at the window's top (2026-10-20, to-human 0.3.2)

Residue of the report view's scroll fix (`started` and the `[ fold to report ]` press in to-human/hooks/mods/to-human.tsx), engine 2.1.304.

- **A row folded while off the window still pulls the view down as it scrolls back in, after a resume and after full transcript → report.** The engine holds an off-window row at the height it last laid out (`ur`/`fr`, cli.pretty.js:940950) and lets go when the row re-enters at the window's top edge and is dispatched again (`mr`, :940946); the scroll anchor is that same straddling row (`pt`, :60693), so nothing corrects the scroll. 0.3.2 removes the view's own triggers (a module restart: 18 jumps → 0 over 120 wheel steps; a fold at a long run's end: 3 → 0), but a `--resume` (its first frame is the engine's, drawn before the module loads: 12 jumps of up to 4 lines on the first pass) and the band's switch back to the report (14 of up to 17 lines in 60 steps) still jump, and so would any plugin that shrinks a row off the window. The fix is upstream: when a held row at or above the window's top is released, shift scrollTop by the height it frees (or anchor on the first row that starts inside the window).

## the message tool's export and evals (2026-10-20, sminos 1.4.0, 7.201.0)

Residue of the to-human message tool (`docs/doperpowers/specs/2026-10-20-to-human-message-tool-design.md`, PR #312).

- **An async ask's pair does not hold the live exports that follow it.** The live export (`sminos/hooks/mods/bridge-rows.tsx`) holds everything kept after a message call until the call's pair is whole, so the project's log keeps transcript order. An async ask's call holds nothing. So a span written after an async ask can reach the log before the ask's question, as it could before the message tool. The fix is about one line: treat the ask's call as a held pair, as a message call is treated. T3. Trigger: a desk or log reader seen showing a message ahead of the question it followed.
- **The Stop path's flush wait misses a message call whose row is not yet on disk.** It reads the transcript's tail. If the call and its result are both still in the engine's write queue (about 100 ms), the tail shows no call, and the message goes out at the next Stop, or through the bridge when it runs. This is rare, because the hook takes longer than one flush to start. An unconditional wait on an empty `last_assistant_message` would add up to 2 s to every Stop after an Esc. T3. Trigger: a message seen exported a turn late in a session without the bridge.
- **The agent-step eval's fake shell does not expand `$?`** (`tests/output-styles/to-human-agent-step-eval.py`, `canned()`). In 2 of the 4 keep_working variant runs, the model remarked on it. T3. Trigger: the next rerun of that eval. Then answer `echo $?` with `0`.

## to-human's start-up read under a long session (2026-10-21, to-human 0.5.1)

Residue of bounding the start-up read (`started`, `begin` and `startUp` in to-human/hooks/mods/to-human.tsx), after a reload unloaded to-human in the three longest sessions on 2026-10-20.

- **A search that outlasts the 3 s wait leaves the rows in arrival order until it lands.** The mark comes from the conversation first, so the rows fold, but runs are cut by the order the rows drew in, and they move once the search lands. The search outlasts the wait on a machine with no rg (grep: 10.3 s for 437 MB) and under heavy load even with rg: in the live check, at a load average near 500, rg took 13.6 s of wall time on 0.55 s of CPU. T3. Trigger: runs seen to move after a reload. The fix is to keep the rows' places in `$.state`, so a reloaded module needs no search (the same contract the 0.3.1 entry above asks for).
- **Each draw's run lookup is linear in the rows drawn** (`order.indexOf` in `runStart`/`runEnd`), and a reload asks about every row at once, so the total work is quadratic in a long session. The waiters' pause through `$.clock.now()` spreads it across the worker's turns but does not reduce it. T3. Trigger: a heartbeat verdict that names to-human ("no answer to a heartbeat"), or to-human draws seen slow in a long session's debug log. The fix is an index from id to slot that is kept current across the splice.

## the devcloud VM driver (2026-10-21, devcloud 0.7.0)

This is what the devcloud VM driver left behind (`docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`, branch `devcloud-vm`).

- **A trickling HTTP response can outlast the reaper's 60 s bound.** urllib's timeout applies to each socket operation, not to the whole response. Accepted at M3 as best-effort. T3. Trigger: an `up` or `ls` seen waiting on the reaper for more than 60 s.
- **Nothing retires Hetzner `devcloud=sshkey` resources.** Each driver machine registers its key once (the MacBook's, then the always-on Mac's on 2026-10-21), and the key stays registered after that machine is gone. T3. Trigger: a driver machine retired, or its key rotated.
- **Every Secret Manager read is a fresh call; there is no cache.** On a network that blackholes IPv6, each read waits out the IPv6 attempt, which made commands take minutes before the LAN was fixed. T3. Trigger: a slow `up` or `ls` traced to secret reads.
- **Price lines are approximate.** GCE `--dry-run` prices only the machine type, not an added disk, and a spot request shows the on-demand rate. T3. Trigger: a price-based decision going wrong.
- **The caps line puts a type's own disk against the disk cap.** It reads "disk 160/200 GB ok" even for a type whose own disk is larger than 200 GB, which looks like a contradiction. T3. Trigger: a session misreading it.
- **`up --project` does not check that the repository exists until the boot.** `--dry-run` passes for a repository that does not exist. T3. Trigger: a boot seen failing on a typo'd project.
- **A released machine cannot be adopted again.** Release deliberately keeps the home, and `setup.sh`'s final check refuses the paths it keeps (`~/.claude/.git`, an empty `~/.config/claude-secrets`, `~/.claude/sminos/daemon`). Supporting it means teaching that check to tell an adoption from an image bake. T3. Trigger: the person wanting to re-adopt a machine.
- **`/var/lib/devcloud-stage` survives a release.** It holds the staged descriptor's text: names only, no credential. The ledger does not list it. T3. Trigger: the next edit to release.
- **A node renamed `<name>-1` keeps the suffix after its old node is finally removed.** This happens when a rejoin's API removal kept failing, and a later run removed the old node. Taking the name back would need one more logout and join, and it is unmeasured whether Tailscale renames the node by itself once the name is free. The driver reports the other name as a failure until then. Board #115. T3. Trigger: a `lease` reporting a `-1` name.
- **A refused rejoin is retried every 5 minutes without backoff.** One example is an OAuth client that lacks `devices:core`. Each lease-service run fetches the client and a token, is refused, and journals it; the node stays as it was. Board #115. T3. Trigger: a noisy `devcloud-rejoin` journal on a host.
- **A Stopped node whose rejoin is refused stays Stopped.** Nothing runs `up` to resume it as its old kind. This only matters when something ran `tailscale down` on a host. Board #115. T3. Trigger: a host found Stopped on the tailnet.
- **Two node-kind messages read loosely when only a removal is pending.** `lease set` prints `rejoin <kind>`, and the lease service says "the tailnet node is not <kind>", though the kind is right. The record's detail for a `-1` node still blames an older node after the API removed it. Board #115. T3. Trigger: the next edit to those messages.
- **The v2 delegation's provisioning code expires around 2027-01-26.** It replaces the retired v1 desk key (devcloud 0.16.0); its renewal is tracked as MAWS board #512.
- **An older driver's image reaper can remove the image baked for a new recipe.** Retention (`reaper.surplus_images`, run by the reaper, `vm ls`'s included) keeps the newest two ready images of each architecture, those of the driver's own recipe first; a driver still on an older recipe hash, beside two ready images of that hash, deletes the image just baked for the new one, which undoes the replacement bake until the next build. True of every change to `devcloud/boot/` (seen in EN.G1's frontier review), not of one change: it ends once no older driver runs. T3. Trigger: an image of the current recipe observed deleted by an older driver.
- **`owned-by` reads a hand-edited profile as it stands** (devcloud 0.18.1, PR #595). An account is `unused` when its provider has no pass artifact under this profile, so three hand edits make an account that holds a host read as never passed: the profile restored to a state before the account's pass (both artifacts gone); an account moved from a shipped provider, which writes no artifacts, to a profile provider that has not passed yet; an account renamed and its old name reused for another cloud account. The rule is the owner's (2026-11-22), and the driver keeps no record of which accounts it has called. T3. Trigger: any of the three met. Then the driver writes a record the first time it calls an account, and `owned-by` reads that in place of the pass artifacts.

## `sminos daemon owed` and a conflict lost to a failed write (2026-10-27, sminos 1.27.0)

Residue of O12 M7c's review (doperpowers:reviewer-high, round 3), left as a bounded storage-failure case.

- **A conflict whose record could not be written can be forgotten after a restart.** `uplink-taken.json` keeps an own writer's `conflict` refusal past the stream, so `daemon owed` shows it as `refused` and exits 1. When the write that would add the conflict fails (ENOSPC), the fail-safe removes the file. `daemon owed` then over-counts, which is safe. But if the uplink restarts after the disk recovers, the next opening `have` that covers the writer rebuilds a clean file, and the conflict is gone: `next_upload()` is None, so no re-upload finds it again. The fix is to keep the conflict evidence through the failure, for example a conflict-only file written before anything else, or replaying conflicts from daemon.log's refusal line. The trigger needs an own-writer conflict, which is already an anomaly, to coincide with a full disk and a restart. T3. Trigger: a conflict seen in daemon.log without a matching `refused` in `daemon owed`, or the next change to `sminos_hublog`'s taken file.

## sminos idle CPU (2026-10-28, sminos 1.27.10)

Residue of the fix for the daemons' idle cost (branch `sminos-uplink-idle-cpu`): on a copy of the MacBook's state the uplink went from 5.8 % to 1.3 % of a core, `daemon run` from 4.8 % to 3.1 %.

- ~~**`daemon run` still reads every project's view every tick.**~~ **FIXED in part 2026-10-28 (sminos 1.27.11):** its trigger came (an idle `daemon run` at 3.4 % of a core on the copy, 4.6 % on the MacBook, bursts of 22–64 % on the mini). A quiet tick writes nothing, scans no log that did not move, and reads again by stat what it read before; every project's view and duties still run each tick. See "sminos quiet tick" below.
- **Each bridged session is probed every BRIDGE_RECHECK (2 s).** A thread and a `GET /status` per bridged session, which each bridge child answers; not measured (the copy had no bridges). A socket's new inode already probes at once, so a longer recheck would cost only same-socket changes. T3. Trigger: a machine with tens of bridged sessions and the uplink above 2 %.
- **Latency moved for two rare cases.** An append to an own writer quiet for HOT_FOR (10 min) whose session is not running, by a process that does not nudge the daemon, goes up at the next scan (2 s) rather than the next pass (0.5 s). A change a member read draws on outside `Plane.inputs` (a `.smns` under a member's directory, a transcript the engine relocated) reaches the plane when the daemon's tick writes it into the log, else within MEMBERS_WHOLE (60 s) rather than 10 s. T3. Trigger: a desk view seen lagging by either.
- **One log holds 35 k events of a two-machine title loop.** manim-master's log carries 18 k `titled` and 16 k `renamed` events of one session (457367a8), written by macbook and mini against each other from 2026-10-20 to 10-22, and none since. Unchanged it now costs nothing, but every append to it merges all of them again, on both machines. T3. Trigger: a log compaction, or that loop seen again.

## sminos quiet tick (2026-10-28, sminos 1.27.11)

Residue of making a quiet tick of `daemon run` write nothing (branch `sminos-idle-tick`; the doctrine in `sminos/skills/sminos/scripts/CLAUDE.md`). Measured on a copy of the MacBook's state (88 projects, 56 k events, `realcopy.py` in `~/.local/share/p5-desk-track-owner/bench/`) and on `bench_scale.py`'s machine at 1× and 3×.

- **A quiet tick still re-resolves every project and seat.** `tick_all` forgets every cache, so each project's root, each seat's and running session's launch directory is walked up again for its `.smns` and `.git` (stats, the files themselves read by stat since 1.27.11): about 1,600 of the copy's 4,100 stats a tick, a third of what is left of its CPU. A generation kept across ticks would take as long to notice a `.smns` written or a worktree made; keying each resolution on its directories' stat would not, but touches every resolver. T3. Trigger: an idle `daemon run` above 1 % of a core again, or a machine with many more checkouts than the Macs.
- **Every log file is stat'ed every tick** (`_store_whole`'s check; 1,210 on the copy). An append moves no directory's mtime, so nothing cheaper tells a file moved. T3. Trigger: as above.
- **Each project's view and duties still run every tick**, on the kept indexes: `_member` builds a row for every joined session of every project, another machine's too. Skipping a project whose inputs did not move needs every duty's "later" (a report whose record failed, a title not yet published, a delivery retried) to say so, or a whole tick every so often. T3. Trigger: as above.
- **The engine's records of the running sessions are opened every tick** (`peer_records`, one open each). The engine writes them, and whether whole by rename is not known: a stat key could miss a same-size rewrite on a coarse file clock, and the state words come from them. T3. Trigger: tens of running sessions on one machine.
- **The launch cache is rewritten every tick a running session's transcript grew** (`launch/<id>.json`: its `size` is where the next reader of any process starts). Never on a quiet machine; on a busy one, one rename per active session per tick (14 a minute on the MacBook's copy, its live sessions' transcripts linked in). Writing it only when the launch directory moved would leave a hook to read up to `LAUNCH_REACH` (1 MiB) of a long session. T3. Trigger: the cache seen among a busy machine's writes.
- **A git-mirrored project still fetches every tick.** A quiet mirror's tick is now the fetch and one look at the refs (two git processes, 0.04 s of git, from fourteen and 0.13 s); a remote's change is not seen without the fetch. Fetching less often while neither side moves would trade latency for it, which is the owner's call. T3. Trigger: the mini's mirrors measured, or a machine with many mirrors.
- **The loop looks for a nudge every 50 ms** (one stat each, 1,200 a minute). A file-system event (kqueue, inotify) would cost nothing idle, per platform. T3. Trigger: the poll seen in a profile.

## sminos daemon profile (2026-11-12, sminos 1.46.2)

Residue of the profile window on the live daemon (`sminos daemon profile`, `sminos_profile.py`).

- **A request made in the instant another is taken can be removed unread.** The loop reads its request file and then unlinks it; a verb that withdraws its request while a second verb creates one in that instant can leave the loop unlinking the second's, and that verb then reports that no profile came back. T3. Trigger: two people profiling one machine at once and one of them seeing that line.
- **Own time is approximate while threads overlap.** From Python 3.12 cProfile sees every thread with one stack, so a function's own time can land on another's (a reviewer measured a loop's 18 ms read as 11 ms); call counts are exact, and the table's header says so. Timers on each pass, as `bench_scale.py`'s hook takes them, would give CPU by pass on a live machine too. T3. Trigger: a live profile whose own times contradict its counts.

## sminos uplink idle cost (2026-11-11, sminos 1.46.1; 2026-11-12, 1.46.3)

Residue of the second pass at the uplink's idle cost (branch `sminos-uplink-idle`; the doctrine in `sminos/skills/sminos/scripts/CLAUDE.md`). Measured on the MacBook with `fs_usage` and `sample` (101 projects, 58 hub projects open, 73 seats, 55 session records, 75 k log events): `daemon uplink` at 11–13 % of a core, 7,550 file calls a second with nothing happening, on both Macs. 1.46.1 reads uplink.json by stat and once a project's pass, answers where an unreadable session is recorded from one listing of each log a cache generation, asks the working directory only inside a protected folder, reads the plugin manifest by stat, keeps the words pass's addressee index while the log holds still, and walks a host file only once it moved or holds something past its cursor; by the counts, about 60 % of the calls and most of the burst's interpreter work. What is left changes ordering or latency, so each waits for a measurement on the new code. The shares are of the 7,550 calls a second before 1.46.1.

- **The member set is published twice a tick.** `Link.tick` calls `Link.members` before the upload pass and again after the plane's tick, and each lists `bridge/` and stats every session record (110 record stats and 4 bridge listings a tick). Since 1.46.3 an unchanged member costs that stat alone: its frame is built again only once its record's stat, row, launch or the visibility moved (`Link.fresh_frame`), and the sockets come from the listing's inodes, no stat each (`bridge_socks`); the parses and frame builds, about 350 a second, and the 30 socket stats a tick are gone. Publishing the second time only when the plane re-read a project or a probe's answer changed would save the second round of record stats (about 170 a second); a record change would go up a tick (0.25 s) later, `members_before` still re-reading every record an upload depends on. T3. Trigger: the record stats seen as the uplink's largest share after 1.46.3, or a machine with many more live sessions.
- **Each member read takes `seats()` again.** `Plane.refresh` passes no `all_seats` to `view_of`, so every re-read project lists the seats and stats all of them (73 on the MacBook): about 230 calls a second (3 %) in the window that held a `MEMBERS_WHOLE` round. Measured since in a live profile of the MacBook's uplink (2026-11-12 15:07Z, 1.46.2): its whole round's 104 reads took `seats()` 104 times, 8,905 seat files listed, 0.082 s of the reads' 0.311 s. One `seats()` a member-read pass, handed in, would read a seat written during the pass at the next one. T3. Trigger: a trace that shows the seat stats at that rate.
- **Every scan looks at every own writer file.** The whole look (`look_whole` at each scan, a nudge and a words pass) stats all 777 own writers of the 58 open projects: about 466 of the 634 `log/<machine>.*` stats a second. A whole look once a `MEMBERS_EVERY` saves up to 370 a second (5 %), at the cost of an append to an own writer quiet for `HOT_FOR`, whose session is not running, by a process that does not nudge, going up within 10 s rather than 2 s. T3. Trigger: the stats seen as the uplink's largest share after 1.46.1, or the owner's ruling on that latency.
- **`Plane.tick` forgets every cache at `MEMBERS_EVERY` whatever `stale` finds.** Each forget is a new generation: the resolutions of every seat (walks for `.smns` and `.git`, `getcwd` inside a protected folder), the transcript index's refresh (one lstat of each `~/.claude/projects/<dir>`, 138 a second, 1.8 %) and, since 1.46.1, one listing of each log for the unreadable sessions. Forgetting only when `stale` is non-empty, as `Link.members` does, cuts the bursts on a truly idle machine; on the measured one an active session kept a project stale, and it lets a scan's resolutions live until `MEMBERS_WHOLE` (60 s). T3. Trigger: a burst still seen every 10 s on a machine with no session running.
- **The upload pass probes the host store and the outbox of every open project.** For each of the 58 projects, each pass (1.63 a second): a stat of `log/`, of `outcomes.jsonl` (missing for 50), a glob of `host/` (missing for 50) and a stat of each of the 78 host files: about 450 calls a second (6 %). Probing a project with no local member and no host store only at a scan saves up to 160 a second (2 %), its first host event or outcome going up within 2 s rather than 0.5 s; ~~listing `host/` only once its mtime moved~~ done in 1.46.3 (`HubLog.host_paths`, keyed on the directory's inode, mtime and ctime by `own_paths`' rule). T3. Trigger: these probes seen as the uplink's largest share after 1.46.1.
- **`last_project` still opens every project's files under every name.** While the statements are unknown (between an upgrade's welcome and the first frame's `locations`), each session `_session_project` resolves by files costs what `recorded_project` cost before 1.46.1: for each registered project an lstat of its `project.json`, its registration, a missing `streams.json` stat and an open of `log/<name>.<session>.jsonl` under each name, once a cache generation. It is left so on purpose: a reconciliation moves a session on its answer, so a listing another lookup took earlier in the generation could hide a file made since, and the window is transient. T3. Trigger: a machine seen to stay in that window (an endpoint that advertises `locations` and never sends them).
- ~~**`bench_scale.py` cannot reproduce this cost.**~~ **FIXED 2026-11-12:** `--preset macbook` and `--preset mini` build a machine of each Mac's shape, and at the MacBook's the bench reproduces what that Mac measured across 1.46.0 and 1.46.1 (uplink CPU ratio 0.61 against 0.64; file calls 6,676 to 3,066 a second against 7,807 to about 2,950). `run --idle-gate` judges a run by its counts of calls, which a runner's load does not move, and the `sminos-idle` gate runs it. What is left:
  - ~~**The bench's plane rereads members about five projects a second; a live uplink does not.**~~ **NOT SO (2026-11-12):** the 103 reads in 20 s are one `MEMBERS_WHOLE` round, the 58 projects open on the stream (`Plane.tick`'s) and the 45 known but not open (`Link.members`'s: the local and the retired), and a live uplink makes it too: a profile of the MacBook's at 15:07Z holds 104 in 30 s, the 12:37Z one fell between two rounds. A copy of the scripts that logged each round's moved inputs showed every round between two whole ones stale for the working session's project alone (its engine record, then its writer file). A window shorter than 60 s holds the round or not as its phase falls; the bench's docstring says so.
  - **A member read weighs more in the bench than on the MacBook.** In 60 s windows at 1.46.2 the reads are 7.9 % of the bench's tick and 4.3 % of the MacBook's (cProfile on both): a whole round builds 900 member rows in the bench and 192 on the MacBook (12 of the other machine's members in every hub project, 100 in its own), and its reads list 42 engine records each where the MacBook now has 16. Those rows and records cost the bench 0.08 s a round, 2 % of its tick at 1.46.2; the presets' `remote`, `mini` and `gone` were not read on the Macs. T3. Trigger: a change to the member read, which the bench would weigh high, or the remote members counted on a Mac.
  - ~~**The mini preset builds 54 member rows; the live mini publishes 96.**~~ **FIXED 2026-11-12:** each preset's member rows are its Mac's published members, 57 and 96, by its seat members (42 and 82).
  - **The B2 gate's default machine reads 4.99 % against its 5 % limit** at 1.46.1 (its 600 own writers all count as hot for their first ten minutes), and no CI gate runs it. T3. Trigger: the next use of `run` without a preset as a gate.
- **What 1.46.3 left (2026-11-12, the bench at the MacBook's shape, idle).** 1.46.3 builds a member's frame once per record state, keeps what a writer's name says by name, takes bridge sockets from the listing, makes a registration's project once while its file holds, keeps each member's owed events while log and delivery record hold, and lists a host store only once it moved: uplink CPU 3.7 % → 3.0 % of a VM core, Python-function calls 56.2–56.9 k → 36.9–37.2 k a second, file calls (strace) 3,020–3,034 → 2,853–2,865. What is left, by the profiled passes over a 60 s window (CPU, the bench's hook): the upload pass (33 %: its stats of the hot own writers, uplink.json, `log/` and `outcomes.jsonl`, each the observation itself), the two member publishes (18 %, a record stat and a few lock reads a member), the whole member round (12 %, one a minute, as a live uplink makes it, above), and the 2 s scan (10 %: `hub_projects`'s seat resolutions, renewed each cache generation, the row on `Plane.tick`'s forgetting above). None of these is cheaper without seeing something later. T3. Trigger: a profile of a live uplink after 1.46.3 that puts something else first.
- **Live after 1.46.3 (2026-11-12).** The MacBook's uplink: 8.0 % of a core at 1.46.2 to about 6.5 % (pairs of 32 s windows with no profiler: 6.3 and 6.1, then 6.4 and 7.1), 19 % less, as the bench said (3.7 % to 3.0 % of a VM core); 148.5 k calls a second under the profiler to 64–86 k. The mini: 7.0 % over 64 s (11.4 % at 1.46.0; no like reading at 1.46.2), 144.7 k calls a second to 88.6 k. A kept member frame still costs a stat, its key and the launch read, twice a tick a member.
- **A loop that works only on what changed: measured, not built (2026-11-12).** Proposed as the next step, then measured before any design was approved.
  - **The floor.** The bench with every count at 0 (two open projects, no member, no session) reads 1,477 Python-function calls and 86 file calls a second at 3.90 ticks a second, 0.3 % of a core, against the MacBook shape's 30,464 and 2,718: about 95 % of the idle cost is looking at the machine's contents.
  - **The looks.** The live MacBook uplink makes 2,583 file calls a second over about 3,600 paths: own writer files 29 %, session records 16 %, the upload pass's four probes a project 17 %, seats 6 %, the transcript index's lstat of every engine project directory 6 %, host files 6 %, checkout walks 5 %. A bare `os.stat` loop over the same tree made 5,018 stats a second for 1.7 % of a core, so the cost is the Python around each look.
  - **OS notifications** (kqueue, 12 minutes on the live tree). With a descriptor a file nothing was missed and each event came within about 1 ms. With directory watches alone 306 of 453 changes were missed: every append in place, every in-place rewrite (the engine rewrites `~/.claude/sessions/<pid>.json` in place) and every mtime touch (`nudge`). The tree takes 2,533 descriptors (265 for its directories alone) where a launchd agent starts with 256, and a file replaced by rename needs its watch opened again. Not pursued: beside a stat sweep it would add a few tenths of a point.
  - **The ceiling.** A throwaway uplink recorded what its ticks read in a minute, then skipped the whole tick body unless an item arrived, the nudge moved, a deadline fell due, the 60 s whole round came, or a stat sweep of those inputs found one moved; the bridges' probes and pid liveness kept running. On a dedicated VM (180 s windows, three runs, no profiler) the MacBook's shape went from 2.95 % of a VM core to 1.81 % (39 % less), and to 1.56 % (47 % less) with a file written by rename covered by its directory and sminos's own appends by one touched file. Both miss what was estimated before the run (1.0 %, and 1.2–1.35 %). What stays: the whole member round (0.47 s a minute: 105 projects at 4.5 ms each), the sweep with liveness (0.50 s a minute, 0.24 s two-level) and the probes (0.13 s). The flat sweep makes as many file calls as today's tick (2,671 against 2,668 a second). With one engine record rewritten a second the variants read 2.82 % and 2.50 % against 2.98 %: a body let through costs 10–11 ms where a tick costs 7.4 ms, so above about 1.3 to 1.7 bodies a second such a loop costs more than today's. At the mini's shape, with its 11 transcript subscriptions held, the same builds saved nothing (4.75 % and 4.27 % against 4.24 %): a subscription's wake is an item, and an item runs the body. With those wakes running only the subscriptions' part, the two-level build read 2.66 % (37 % less).
  - **Why it is not built.** A real one needs every pass to say when it is settled (pending work lives in about 25 fields of `Link`, `Requests`, `Rpcs`, `Leaving` and `Plane`; `Bridges.answers` starts the probes as a side effect of the publish; the words pass, the retries and the leaving clock run by being called), its inputs traced (14–17 k distinct paths a minute, 1,679 of them the engine's project directories), and a rate limit, for at most the figures above. T3. Trigger: the uplink's idle share named as a problem on a machine again, or the passes given a settled state for another reason.
- **A held main subscription wakes the uplink twice a second, whatever it finds.** Its pump asks the transcript worker for the disk facts of its subagent tree every `METAS_EVERY` (0.5 s), and every answer but `waiting` wakes the loop: 21 answers a second for 11 held idle subscriptions at the mini's shape, about 1.9 more ticks a second. Eleven held cost 0.9 to 1.3 points of a VM core at 1.46.1 (3.84 % to 4.72 % at the mini's shape, 3.73 % to 5.03 % at the MacBook's). Running only the subscriptions' part on such a wake, the full tick at `POLL` as before, was measured on 1.46.3: 4.24 % to 3.90 % (8 % less, where 25 % was predicted), since the ticks it removes come right after a full one and are the cheap ones. Not waking for an answer equal to the last, or looking at the tree only once its directory moved, would take the wakes and part of the looks; neither is measured. T3. Trigger: a machine's uplink seen above its idle share while a desk holds transcripts open.
- **Small per-tick reads the floor showed.** `Records.scan` asks for `config-dirs` fresh each tick; the file is missing on both Macs, so each tick lists the sminos root and takes `realpath` of the default config directory (about 22 file calls a second). `bridge_socks` lists `bridge/` four times a tick, once a caller. T3. Trigger: the next change to `Records.scan` or `bridge_socks`.
- **The idle gate's margin was spent without a note.** `bench_scale.py`'s limit is 33,570 Python calls a second, 30,515 measured on 1.46.3 plus ten percent. `main` at 1.52.2 read 32,582 (run 44883661949), so about seven of the ten percent went to the releases between, T1 and T2 the largest, with no line at the limit saying what was bought. CH1 was built to add nothing for a machine with no channel and ended at 32,230 (`78074970`); about 4.0% is left on that run, and runs differ by about 2.6%. What T1 and T2 added per tick is not measured. Either give it back, or derive the limit again from a fresh measurement with the reason in the diff. T3. Trigger: `sminos-idle` red on a change that adds nothing to the tick, or CH2's first milestone.

## the style reminder's rule after a reload (2026-10-28, to-human 0.7.2)

Residue of the `output_style` attachment hook in `to-human/hooks/mods/reminder.tsx` (PR #432), left by its review.

- **A request rendered right after a plugin reload can cache the style reminder without the rule.** After a reload the engine invalidates attachment answers but does not await the new module's `session.start`, and `isMessageToolOn()` is false until message.tsx's registration settles (env, config, `tool.register`). A request rendered in that window caches the reminder without `STYLE_FINAL`; later rows carry it. The prompt-cache cost is one miss over the context, since the re-asked rows differ from what was cached before. The window is narrow: the reload mod reloads only while the session is idle, so it takes a prompt arriving within milliseconds of the reload. The `prompt.submit` reminder and the final-message turn ending read the same flag in the same window. The fix is to have the hook await the registration's settling, bounded under the engine's 10 s hook budget, or to compute eligibility in the hook as `hooks/mods/compact.tsx` does. T3. Trigger: a reminder seen without the rule after a reload, or the next change to the message tool's registration.

## the copied final line (2026-10-31, to-human 0.7.2)

Found by a transcript audit of main conversations since 0.7.2 (41 sessions, about 3 days, priced at Opus 5.5 API rates; scripts in `~/.local/share/final-audit/`). Left as is by the owner's ruling: the cost does not justify a change.

- **The model writes `Message sent to the human.` itself when a request follows a final message.** The plugin's made-up response (`FINAL_ANSWER`) stays in the history as an assistant turn, so the model copies it when a request follows a final message: 45 times in the window. 37 of these came after a final message sent beside another tool call (49 such batches, Bash in most), which the plugin rightly lets go. A copy lacks the `answeredWithoutRequest` flag, so the view draws it as a `› working record` after the message, and `sminos reply` returns it as a seat's reply. Agents do set `final`: of 483 final messages, 395 ended the turn with no request. The 49 extra requests after a batched final message cost $3.92 of the sessions' $1,042 (0.4%; $0.08 each, median context 315k). Honoring `final` beside other calls would have cut 5 of those 49 turns short of work the model went on to do. The engine's own turn end (`_meta["claude/endTurn"]` on an MCP tool's result) would leave no row to copy, but the mod API gives a plugin's tool no way to set it; an empty made-up response would draw the engine's "no visible output" nudge. Stronger style wording targets `final`, which is already set. T3. Trigger: the copied line seen to mislead a reader (a seat's reply, the report), or the mod API letting a tool's result end the turn.
- **`deferred_tools_record` lets the request after a final message go.** The engine's bookkeeping record renders to nothing for the model, but it is not in `STANDING_ATTACHMENTS`, so a final message that it follows makes a request (4 times in the window). Adding it is a one-line change with a test. T3. Trigger: the next change to `message.tsx`.

## the spawner as owner (2026-11-01, sminos 1.28.0)

Residue of O12 M11's sminos half (MAWS's `docs/doperpowers/plans/2026-10-27-p5-o12-sminos-owners.md`, M11), left by its reviews. None of it can move an owner today: owners change only through O8's record actions, which do not exist yet. Revisit them when O8's M10 is written.

- **Behind an unreadable predecessor, a hand-off's or a background job's lineage takes the hook's own final evidence.** `lineage_provenance` now stops at a predecessor whose record file exists but cannot be read. An M11 continuation then gets no evidence, so its record stays provisional until the predecessor reads again. The other lineages fall back to the hook's evidence, which is final, so a changed owner on the unreadable predecessor would not carry over. Making that fallback provisional too is the fix.
- **`claim` can still replace an unreadable record file.** It runs only for a brand-new session binding its pending launch at startup, where an existing record file is all but impossible. Applying `unreadable()` there is one line.
- **An unreadable record is logged once per process.** Each hook is its own process, so such a session adds one daemon.log line per hook run. One line in total would need a marker on disk.

## manager query's fork agent (2026-11-01, session manager M2)

Residue of the bridge's `ask` op (`sminos/hooks/mods/bridge-ask.tsx`), from its live measurements; spec `docs/doperpowers/specs/2026-10-31-session-manager-design.md`.

- **A haiku session's fork can follow the session's own unanswered prompt mid-turn instead of the question.** On a session mid-turn, the fork's inherited conversation ends with the session's prompt (for example "Run sleep 20, then reply …"). On haiku, 2 of 5 forks ran the pending call and wrote the session's reply, and the result was the same with the tail left out (3/5 clean), so the tail is not the cause. Opus and Sonnet were clean 10/10. The guard refuses any write a fork attempts. The lever is how the question is framed against that inherited prompt, not the tail. T3. Trigger: the manager queried against haiku sessions, or the live check's judged pending-call check failing on a stronger model.

## fold summaries (2026-11-13, to-human 0.8.0)

Residue of the run tracker (`to-human/hooks/mods/folds.tsx`, PR #500), left by its execution; spec `docs/doperpowers/specs/2026-11-12-fold-summaries-design.md`, report `docs/doperpowers/specs/2026-11-12-fold-summaries-report.md`.

- **A forked session starts with no summaries.** Summaries are kept in one file per session id, and a fork's new id has none, so the folds the fork inherits read `working record`, as every fold did before 0.8.0. A fork made inside a running process still has the parent's runs in the tracker's memory when its `classic.SessionStart` resets them; whether the fork's rows keep the parent's ids, and whether the event names the parent for a fork made at launch, is not probed. T3. Trigger: the owner forks sessions and misses the labels.
- **The tracker's spawns are not remembered across a reload.** Its set of spawns the report shows starts empty when the module starts over, so the failure notification of a spawn made before the reload is a delivery to the tracker while the view, whose spawns refill as rows redraw, shows it as a row the person reads. One fold's bound differs between the two, so that fold's button can read `working record` in place of its label. Publishing the spawn ids in `$.state` closes it. T3. Trigger: a wrong label seen after a reload with an agent running.
- **One run drawn as several folds, as first reported: a likely cause, not confirmed.** PR #499 fixed three reproduced causes (a subagent's transcript, a queued prompt's preview, a run unfolded across such a row); the stretch the owner photographed held none of the three by its transcript. A fourth was found on 0.7.4 and fixed in 0.8.1 (`rowKey`): after a message of more than one block the engine draws every later text and prompt row under a derived id, which no table knew, so before 0.7.4 each such row stood where it first drew, and a prompt or message row drawn late in a fullscreen window could land inside a run and cut it. That session had drawn under derived ids since 00:19Z by its transcript, an hour before the photograph, but no dump exists from before 0.7.4 to show the order. `/to-human-dump` writes the view's order and runs to a file. Trigger: a sighting on 0.8.1 or later; run the command before any reload.

## the backtick guard (2026-11-17, sminos 1.48.0)

Residue of the guard that refuses a sminos call with a live backtick (`sminos/hooks/mods/backticks.tsx`, branch `sminos-cli-path-guard`), from its three reviews and its executor's report. The corpus named below is every distinct Bash command of the MacBook's transcripts from 2026-10-27 to 2026-11-17 that mentions sminos: 32,707 commands, 4,483 of them holding a backtick, six refused.

- **A quoted parameter pattern in an unquoted heredoc body is read as a substitution.** In `cat <<EOF`, a body line `${text#'$(sminos say "…")'}` whose quoted pattern holds a backtick is literal in bash and zsh: neither substitution runs. The body's lexer does not track parameter-expansion context, reads the pattern's `$(` as a command substitution, and the guard refuses the call. A wrong refusal, of a shape the corpus does not hold. Giving up on a `${…}` whose pattern holds a quote closes it. T3. Trigger: a session refused while generating text that quotes a sminos call.
- **Misses left by design.** A live backtick in an argument of a command piped into sminos (`printf '%s' "…" | sminos say -`: such substitutions are often meant), and a sminos call inside a `bash -c` or `eval` string. A miss leaves the shell doing what it did before the guard; none is in the corpus. T3. Trigger: one seen in a transcript.
- **A peer message's reply line still models a double-quoted body under an absolute path** (`reply_line` in `sminos/skills/sminos/scripts/sminos.py`). Its reader may have no `sminos` on PATH: a session started before 1.48.0, or one MAWS launched. It is the example sessions copy most, and the guard does refuse a reply that puts a live backtick into it. T2. Trigger: the skill's rewrite for channels and threads.

## query-transcript (2026-11-18, doperpowers 7.221.0)

Residue of `query-transcript` (`skills/query-transcript/scripts/query_transcript.py`, PR #512), from its builder's report and the first live runs. (The builder's other note, a $0.01 cost for forks of 44k and 73k tokens, is the list price: haiku bills $0.10 per million up to a 100k-token prompt and $0.50 beyond.)

- **The answerer can name a replay notice as the session's.** The resume appends notices the session never saw (a tool call "interrupted", background work that "didn't finish before the previous session ended"); the frame says so and the quote check marks them not found, yet an answer once called one "the first task-notification" while labelling it replay-added. T3. Trigger: an answer that builds a conclusion on one.

## derive on compaction (2026-11-18, sminos 1.49.0)

Residue of the compaction's derive (`clear_status` and `cmd_derive` in `sminos/skills/sminos/scripts/sminos.py`), from its code review; spec `docs/doperpowers/specs/2026-11-08-sminos-derive-on-compact-design.md` §4.

- **The clear can take a status set after the compaction.** The hook (`smns-derive.sh`) starts `derive --compacted` detached, so a `sminos status` the session runs in the second or so before the derive reads the log is cleared with the one the compaction made stale. Clearing only a status older than the compaction (its time passed to the derive as a cutoff) closes it. T3. Trigger: a status seen lost right after a compaction.
- **The compaction count is not serialized.** `compaction_due`'s read-increment-write of the count is not serialized with `derive_member`'s record-then-reset. When a detached compaction derive overlaps a daemon derive, one compaction can be lost or counted twice, so that derive comes one compaction early or late. The fix would be a per-session lock across the increment and the record/reset pair, not held during the fork. T3. Trigger: a derive seen at the wrong compaction.

## sminos threads (2026-11-19, T1 of the channels-and-threads composite)

Residue of T1 (`docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md`), each with what would promote it.

- **A held event does not follow a continuation.** A stopped session its human opened, reopened and handed to a background job before the next delivery pass, leaves what was held for it addressed to the old session id: `_owed` reads no lineage, and everything after it (the delivery record and its lock, receipts, the reach gate's decision, the outcome) is keyed by the addressed session, so following it would deliver under a decision made for another session. The job reads it at its next `chat` through the cursor the hand-off carries, and nothing counts it owed, as for a live session handed off with something owed. Never across a refill. A wake's push does not meet it: a wake starts the addressed session itself and pushes to that process, so only a reopening by hand and a hand-off before the daemon's next pass still can (T2). T3. Trigger: a reopen and a hand-off inside one daemon interval seen to lose a held message's push.

Residue of T1's branch review (2026-11-19 to 11-20): one review of the whole range, two of its fix diffs, and three rounds of attack on the held-message guarantee alone. They raised 82 findings (44, 13, 14, and 7, 3 and 1); one was dismissed against the plan's Decision Log (reach follows the conversation after a refused hand-off) and the others were fixed on the branch, all but these.

- **A late first-spawn absorption is not durable after the seat's promotion.** With a child that already has a human record, the launcher promotes the seat and writes only metadata after `repoint_seat` refuses; killed before the later `thread_transition`, it leaves the seat vacant with no entry to replay and the job read as human-opened. Closing it means making the promotion itself the absorption's `begin`: one write that creates the named seat from the provisional record with its thread keys, `current` and the absorb entry (a `rename_from` path through `_change`/`begin`/`thread_transition`), with the absorb's begin moved ahead of `ensure_record` in `spawn_fresh`; a `begin` on the provisional record before the rename would leave a `joined` stamped with an id no record has. [branch review 2, item 10] A wake's push does not meet it: the seat it leaves is vacant, and no wake starts a vacant seat (T2). T3. Trigger: a spawned job seen as human-opened beside a vacant seat.
- **A `/clear` between the last hop's binding and the inbox write delivers the old session's text to the new one.** `bound_peer` binds the session, pid and socket together and is checked again before each route, but the engine can move the same process and socket to a new session between that last check and `send_frame`'s write, and the inbox takes any frame. A wake's push meets it as any live push does, through the same last hop. The engine's inbox already refuses a frame whose `session_id` is another session's (`wake-spike-2.md` §16, on 2.1.329), which sminos's frames do not carry yet; closing it is sending that field, once what a sender observes of such a refusal (the socket's answer, and so the settlement) is measured, which is this row's next step, outside T2. [held-message verification, 2026-11-20] T3. Trigger: a frame seen in a conversation it was not addressed to, or the refusal's answer measured.
- **An unreadable delivery record is replaced as though empty.** `delivered_load` answers `{}` for a record it cannot read, and the next write replaces it, losing its settled prefix and its `held` marks (re-delivery of what was settled, and a held event read as never held). It is a storage or permissions fault; treating it as "defer" would stop every delivery to that session on one bad file. [held-message verification, 2026-11-20] A wake's push meets it as any push does: the wake writes no delivery record, and the push after it settles through the same one (T2). T3. Trigger: a delivery record seen unreadable, or a message pushed twice after a disk fault.
- **A bridge that takes the connection and closes without reading the request settles a held event.** The bridge client reads no answer as a possible submission (`sent?`), and a held event is settled on it though nothing reached the session. A retry is not safe today: the bridge's duplicate check is a mark in its process's memory, lost at a restart, and a retry that finds no bridge falls back to the inbox frame, which carries no key, so the text could arrive twice. Closing it needs a durable answer at the bridge to "was this event's key submitted" and a durable bridge-only constraint on the event in sminos. A wake's push meets it: a woken process is pushed to as a live one, by the same routes (T2). T3. Trigger: a held message seen settled with nothing in the reopened session.
- **An older copy's delivery write drops held marks.** A copy before 1.51.0 rewrites a session's delivery record from its own load, which knows no `held`, so every writer's marks go with it. Seen in three shapes: a seat an older copy made over the human-opened session (its `daemon tick`, addressed `say` and `send`), a read-only policy with an outside event owed (its `daemon tick`), and an older daemon's pass over a session reopened with no socket yet (settles the held events unpushed). The event is then decided afresh by the next pass of this code, which holds it again if the session is still stopped. A spawned thread meets the like from 1.51.0 itself: that copy's pass keeps a hold for a thread its human opened alone, so what this code held for a seat is settled `recorded` with its mark, pushed to nothing (seen for a seat with no conversation on the machine, which 1.51.0 does not resume; `test-older-cli.sh`). Nothing an older copy can be taught; it ends when no copy before 1.51.0 runs, and for a spawned thread when no copy before T2 does. [held-message verification, third round, 2026-11-20] A wake adds no shape of its own: it writes no delivery record (T2). T3. Trigger: a held message lost on a machine where a session started before 1.51.0 still runs.
- **A hand-off's settlement of what was held for the session left reports the end's reason to the hub.** The outcome for a hub outside event says the session's thread has ended, where the thread went on in its successor. Cosmetic; give the continuation its own reason text. A wake does not meet it: it settles nothing (T2). T3. Trigger: a hub reader misled by it.

Residue of T2's frontier review (2026-11-21): the holder's whole-range review of M1 to M4 confirmed 30 findings; these were logged rather than fixed, each with its reason.

- **The live push's own window: a hand-off between the last reading and the handoff.** A push to a live session reads the hold and the peer, then hands the frame through `bound_peer` (the session, the pid and the socket read together); nothing a transition takes is held meanwhile, so a hand-off can move the thread's `current` on in between while the old process still answers, and the frame goes to a session that no longer fills the thread. It is the base's (sminos 1.51.0, `deliver_next` → `push_member` → `push_live`), not the wake's: a push after a wake is now made under the wake's hold, which every transition opens its entry under. Closing it for the live push means holding the wake lock across every push, a cost the idle path was kept from. [frontier review, scalpel-3#2] T3. Trigger: a frame seen in a predecessor's conversation after its hand-off.
- **A newly held backlog rewrites the delivery record once per event.** `deliver_next` marks each addressed event of a held writer's queue through `delivered_held`, which loads and writes the whole record each time: N events, N rewrites of a growing record (quadratic), and a fully marked backlog is loaded N times on each visit. A stopped thread's backlog is short. [frontier review, sweep#6] T3. Trigger: a held backlog of hundreds of events, or a tick slowed by one.
- **A returned seat whose task's stream refuses the append.** `stream_choice` decides the route, not that the task's own stream can be appended to: a project that can be read while that stream cannot be written starts the returned seat, and the task is then nowhere in the log. Needs a store whose streams differ in permission, which no machine has. [frontier review, scalpel-1#5] T3. Trigger: a store whose log files carry different permissions.
- **An older CLI run by hand against the same store.** A 1.27.10 or 1.51.0 copy, run by hand: a seat it reassigns A, B, A keeps `waking` (its line, retry schedule and saved-options hint read again as A's); a shadow seat over a human-opened session is resume-locked by its seat id where a wake locks the thread id, so both can launch; a resume of a session whose wake note is still on the record can get the note: since round 2 of the frontier review only a note bound to the session's job and written before the process started goes, which a same-id resume shares until a wake or the sweep counts the dead launch (at most `WAKE_GRACE`). D7 accepts what an older copy run by hand does; no machine of the fleet runs one. [frontier review, scalpel-2#2, scalpel-2#4, scalpel-2#7] T3. Trigger: an older copy found running on a machine of the fleet.
- **A 1.51.0 tick can publish `woken` over a newer `held`.** Its `publish_state` refreshes a stopped spawned seat's `wake` to `woken` (its `hold_for` covers only threads their human opened), and the remote fold takes the latest state, so until this code's next tick a remote sender reads `woken` where `held` (with its `why`) stands. The message is recorded and decided by the thread's machine either way; only a remote sender's words are wrong for that interval. [frontier review, scalpel-2#5] T3. Trigger: a mixed-version machine kept past the upgrade.
- **The board's relay records an answer again at each tick for a held session.** `phase_relay` (`skills/issue-tracker/scripts/_sweep_api.sh`) reads a stopped, idle seat as live and delivers an answer by `send --wait`, which since T2 records it and holds it (exit 4) for a stopped thread that is not woken; nothing is acked, so each tick records another copy, and the session meets every copy when it runs. An owed resume's folded answers (sweep#3) now stay on the feed and can reach this path too. The board's dispatch is dormant (2026-10-18), so nothing runs it today. Closing it: the relay reads `owed: <session>` as recorded and owed, and records an answer owed to that session no second time. [frontier review fix wave, 2026-11-21] T3. Trigger: the board's dispatch armed again.
- **A not-reachable notice can carry a wake's line.** `show_notices` (`sminos_hublog.py`) pushes `[sminos: your message to … was not delivered …]` through `push_live`, which puts a pending wake's line after any text it hands over; a notice that reaches a just-woken background process before the message that woke it takes the line, which then misnames what woke the session, and that message arrives without it. The window is E18's (another push before the launcher returns); the manager shows such a notice's note too, since a notice opens with no frame. [frontier review fix wave, 2026-11-21] T3. Trigger: a woken session found reading its wake's line under a notice.
- **A seatless `resume` waits for the delivery lock with no deadline while it holds the wake lock.** After stopping the turn it lets its message's delivery lock go and runs the delivery pass under the wake lock it keeps; the pass's `flocked` waits with no bound, so a sender stalled on that delivery lock stalls the resume and keeps the wake lock held. A sender stalled there stalls delivery to the session at the base too, and every other taker of the wake lock polls with a bound, so nothing deadlocks. [frontier review round 2, scalpel-1#3] T3. Trigger: a resume seen hanging behind a stalled sender.
- **A lane B session reopened as lane A.** Three shapes, all needing a MAWS lane B session (whose process alone activates receipts) reopened by hand as lane A: `end_lane_b_seat` commits a reconciliation's retirement of a stopped lane B seat with no lifecycle lock and no fresh lane or peer check, so it can land after the seat was woken in lane A and a direct send pushes to a retired seat's process; on a machine whose endpoint decides reach, a receipt left awaiting is classed a retry that needs reach while `reach_due` leaves out an awaiting receipt, so no permit is asked and its writer waits; and the wake's preflight asks reach with the words gate's verdict rather than the receipt's, which a gated person's event cannot pass. [frontier review round 2, scalpel-1#4, scalpel-3#3, scalpel-3#4] T3. Trigger: a MAWS session reopened in a terminal on a machine of the fleet.
- **A delayed `/clear` release refuses a launching wake's own writes.** The release is journaled without the wake lock (the one transition that takes none), and `update` refuses every write while its entry is open, so a wake launching then loses its writes of `waking`: an accepted job without its grace, or a failure without its count and retry time, for that one attempt. Finishing the release does not apply them. [frontier review round 2, scalpel-2#3] T3. Trigger: a woken session replaced as lingering, or retried with no backoff, right after a `/clear`.
- **What `reply_to`'s rule leaves to `--wait`'s polling.** `reply_to` reads the reply to a message from the rows after the one holding it, or after the bridge's wake naming that row, to the next prompt that starts a turn; `_wait_reply` polls it as rows arrive and stops once the engine's record reads `idle`. Three cases it does not settle: a waiter that reads `idle` between the end of the turn that missed its row and the bridge's wake prints that turn's answer; a waiter reading rows as they come closes the reply at a person's prompt queued ahead of the wake; and a prompt the engine injects into a running turn as a `queued_command` attachment is read by neither the rule nor the poll. Each prints a wrong or short reply to `--wait`; nothing is lost or pushed twice, and `sminos reply` reads the session's last reply after. [frontier review round 3] T3. Trigger: a `--wait` seen printing another turn's answer, or a cut-short reply.
- **A sender whose own call wakes the thread for an earlier held message is told `sent`, not `sent (woken)`.** The wake is made while the pass pushes the writer's earlier event, so the sender's own event is then a plain live push and its outcome carries no `woken` (`deliver_say`, `send_to_member`). §5 asks for ` (woken)` after a message pushed after a wake; the message is delivered once either way. Cosmetic. [M5's several-senders suite, which asserts it as it is] T3. Trigger: a sender misled by it.
- **A copy a wake removes stays a member until the three-day rule.** The engine's copy (rows 11 to 13 of the wake: a session held elsewhere, saved options, a copy the engine made) runs its `SessionStart` hook before `remove_copy` takes it down (source `fork`, measured on 2.1.330: `claude --bg --resume <id> -n <name>` over a row started `bc743a4e`, which `sminos list` then showed as a stopped member). It ran no turn, so nothing is owed to it, but retiring it where it is removed is more than one write: `remove_copy` has only the copy's short (its session id is in the job list before the removal), and the hook made a thread record for it too, which an end must close. It stays listed as stopped and ends by the three-day rule; promote if copies start to clutter a project's list.
- **A state directory whose path holds glob characters lists no seat and no registered project.** `seats()` and `record_files()` list `root()/*.json`, and the project registrations `projects_root()/*/project.json`, each with the directory unescaped, as the migration's listings do; under a `SMINOS_HOME` such as `state[1]` they match nothing. The log stores were escaped with #581 (`_store_paths`); these were left because no supported setup names its state directory so, and the fix is the same `glob.escape` at each.
- **A long-lived process can hold a message for a transcript that is on disk.** `hold_of` → `not_woken(whole=False)` takes a miss of the process's transcript index as final. `TranscriptIndex.paths` lists again for an ordinary lookup only when the listing is at least `TRANSCRIPT_FRESH` (5 s) old and `forget_caches()` has marked it stale since, so a process whose index was listed before a session's transcript appeared (a new session's first write, or a transcript put back for a stopped one) answers `transcript` for a send to that session, stopped, until both hold: in the daemon and the uplink, which forget their caches each pass, the first pass 5 s after the listing; in a process that never forgets, for as long as it runs. Meanwhile the message waits and the reason says no conversation of it is on the machine. A CLI call is a new process and lists for itself, so the wake tests met it first (every verb in one process; two reds of `sminos-suites-a` on 2026-11-21, fixed in the fixtures `Wakers.seat` and `Deliveries.seat_in`, which now list the index again). A fix at the delivery boundary is `hold_of(session, fresh=True)` on the `hold_now` path passing `fresh` down to `transcript_file`, the rule `transcripts_now`'s docstring already states; it does not cover an event that needs a `words?` or `reach?` verdict, which `words_due` and `reach_due` can leave out of the asking on the cached `hold_for` before delivery reaches `hold_now`, so a whole fix looks again there too. Not taken with the test fix: no user has met it.

## sminos environments (2026-11-21, EN.G1 of the channels-and-threads composite; sminos 1.53.0, devcloud 0.18.0)

Residue of EN.G1 (`docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md`, its last section): what the child accepts, each with what would promote it.

- **An addressed event that names a session its thread has left is not pushed.** Delivery is keyed by the session an event names (`_owed`, `deliver_owed`), and a hand-off carries the chat cursor, not the delivery record. So an event written by a sender whose view lags names the session the thread left: it is in the project's log and counted unread for the current session, which reads it at its next `sminos chat`, and it is pushed to no process and wakes none. A VM's notice is one such event: the window is the time between a change of session on the owning machine and the VM reading it, seconds while both are connected and as long as a disconnect otherwise, and a lease warning, sent once thirty minutes before the VM is deleted, can land in it. The owner confirmed it as a limit on 2026-11-21 ("한계로 기록 (Recommended)", the plan's Decision Log). The sized fix: keep in the thread record the project log's positions at each change of session and let `_owed` read, for the current session, what names a former one past them. T2. Trigger: a notice or message observed lost in that window, or the owner asking for it closed.
- **The census window after a handover.** The three-day rule reads devcloud's answer up to one spacing old (`SMINOS_THREAD_END_EVERY`, an hour), so a thread that took a VM by `devcloud vm owner` within that hour, and has been stopped three days, can be ended on an answer from before the handover. The VM is not lost, but the thread stays ended when the next census names it: it is reopened by its human, filled, or the VM is handed on. `retire` asks afresh and has no window. T3. Trigger: a thread observed ended within an hour of taking a VM.
- **A host names its owner's project by name until a handover writes the id.** `vm up` writes the id only where `sminos who --thread` answers for the creating session itself (`context.creator_project`); a session that is no thread, a thread that has gone on in another session, or an older sminos leaves the name, and an adopted machine's descriptor names no project at all. A notice that goes on to the project then names it by a name two logs of the host may share, which `say` refuses as ambiguous or reads as the first of its tiers, and an adopted machine's goes from the owning thread straight to its journal. T3. Trigger: a notice observed in the wrong log or none, or a change to `devcloud vm adopt`.
- **A host built before its send lock can send its former owner one notice after a handover.** The handover's program waits for the host's send lock, which hosts built since 2026-10-28 take while they send; an older host's lease service reads its descriptor before it sends and nothing there waits, so a tick that read it before the handover can still send to the thread that gave the host up after `vm owner` has returned. T3. Trigger: such a notice observed, or never once no host built before the lock remains.
- **`spawn --on` refuses a spawner whose reach is not the default.** The thread opened on the VM takes the VM's default reach, and carrying the spawner's is not built, so a private session, one with shares, and one whose record could not be read or is not settled are refused (`sminos_on.reach_refusal`); a background job that continues no session (one a person started with `claude --bg`) never has a settled record and is always refused. T3. Trigger: the first session that needs `--on` from a narrower reach, or a person's own background job that needs it.
- **`spawn --on new` cannot size its VM.** It passes `vm up` only its projects and `--vm-confirmed`, with no type, account or lease, so the VM is what `up` picks from the first project's `devenv/host.toml` or the person's defaults; another size or lifetime is `devcloud vm up --enroll` with the flags it needs and then `spawn --on <name>`. T3. Trigger: a session that needs another size from `--on new` (pass `--vm-type` and `--vm-account` through).
- **An older driver's `vm lease` can put a former owner back in an adopted machine's record.** A devcloud driver from before 0.18.0, still on the `PATH` of a session started before the update, saves an adopted machine's whole record in `vm lease` without the per-host lock, so its save can land after a handover and name the former owner again while the host's descriptor names the new one. Accepted by the holder after the frontier review: it needs an adopted machine, an old session's `vm lease` and a handover in the same seconds; `devcloud vm owner` run again repairs it; nothing new can make an old driver take a lock; it ends when no session runs an older driver. T3. Trigger: such a record observed, or never once no pre-0.18.0 driver runs.
- **Two long notice senders can show alike in the inbox envelope.** `from-name` is cut at the engine's 64 code points (`peer_envelope`), so two senders that agree on their first 64 show the same name there; the frame's own line keeps them apart, and routing never reads the envelope. Display only. T3. Trigger: a session observed confusing two such senders.
- **`vm up` can make a VM and never name it.** A provider whose create is acknowledged and whose describe after it fails (Hetzner's two calls) leaves `up` without the generated name, so it prints no `created` line and the VM, kept and unlabelled in no output, bills until found; `spawn --on new` now ends such a failure saying a VM may exist and that `devcloud vm ls` shows it, but `up` itself is unchanged. Older than EN.G1 (the frontier review's F1, logged by the holder). T3. Trigger: a VM found that no `up` named, or the next change to `up`'s create.
- **A deleted VM can be said kept when devcloud cannot forget its host key.** `Context.delete` calls `remote.forget()` after the provider deleted the server, and `forget` can raise while it unlinks `known_hosts.old`, so `vm up`'s recount prints no deletion and `spawn --on new` says the VM is kept. Older than EN.G1 (devcloud's delete), and it errs on the safe side: the reader runs `devcloud vm down`, which finds nothing (the second frontier review, logged by the holder). T3. Trigger: a VM reported kept that `vm ls` does not list, or the next change to `Context.delete`.
- **A server that lost its `devcloud` label cannot be found by `vm down`.** Where the provider refuses to delete a server that lost the label between its create and `up`'s recount, the recount says the VM is kept and both CLIs name `devcloud vm down`, but `Context.find` searches only servers with the label, so the server keeps billing until it is removed in the provider's console. Older than EN.G1 (the second frontier review, logged by the holder). T3. Trigger: a recount whose delete was refused, observed on a real provider.
- **The branch preflight asks origin through the person's git configuration.** `spawn --on new` runs `git ls-remote <url> refs/heads/<branch>` in the caller's worktree, where an `insteadOf` mirror can answer for a branch the canonical GitHub host lacks; the VM then clones from GitHub and cannot check it out, and is named and kept, which the outcome says. Asking without the person's configuration would lose their credentials for a private repository, so this is accepted as a limit (the second frontier review, logged by the holder). T3. Trigger: a VM whose clone failed for a branch the preflight passed.
- **A machine still downloading a project's log reads a member's absence as a fact.** Found by EN.G1's live check (2026-11-22). A machine that just enrolled downloads each hub project's log first: the hub sends the backlog writer by writer in lexical order of writer name, a page at a time, and whatever is written after the machine's hello is queued behind the whole backlog. Until a session's writer arrives the machine holds no row of it, so `say "@<short>"` and `who --thread` answer exit 4, "no member", exactly as for a name nothing answers to. The machine cannot tell the two apart: the hub's opening `have` vector lives only in the uplink's memory, and nothing compares it with what is held.
  - **On the fleet** the import ran at about 4.4 events/s, so a project of 12,530 events takes most of an hour. A VM's owning thread was never resolved in the 20 minutes the VM lived, and its notice went on to the project's broadcast (X8 as built: exit 4 goes on).
  - **Not sminos's import:** the real uplink loop imports that whole log from the endpoint stand-in in 2.8 s, the hub's order and pages, and 3.2 s with one event per frame.
  - **Where the rate is set (MAWS's measurement):** the endpoint's verification of each event. Org-protocol's `certViews` re-verifies every machine certificate about three times an event, 240 ms an event at 150 certificates, and the inbound index is fsynced once an event. MAWS is fixing both. It expects about 143 events/s, about a minute and a half for a log this size, from a host's next boot install. That is still longer than a new thread takes to send its first message, so the VM's wait for its spawner below stays. sminos assumes no order among a backlog's writers, so it still holds if MAWS later sends recently active writers first.
  - **The sized fix on sminos's side**, needing no new wire: the hub's `have`, the vector of what this machine may read, reaches sminos before any backlog page.
    - The uplink keeps a per-project mark: the project is behind while any writer it has imported is below that `have`, with `spent` advancing past refused and withheld positions.
    - a name that matches nothing while it stands is refused with its own exit and words (not caught up, how far behind);
    - `notices.deliver` keeps a notice on that exit instead of going on to the project, which is a boot-library change and so a new image.
  - The promotion condition is met on our side. The window is most of an hour now, and about a minute and a half after MAWS's fix, which is still longer than a thread's first message. T2. Trigger: MAWS's fix on the hosts, or a notice or message observed lost in the window.
- **The wait for a VM to read its spawner can outlast the Mac's eleven minutes.** `spawn --on` opens no thread until the VM's log answers for the spawner's session (EN.G1's plan §8 step 4b, `spawner-unknown`), and the Mac waits within the one wait it gives enrollment (§7 rows 26a and 27a). Until MAWS's endpoint fix reaches the hosts, a first download of a large project's log runs at a few events a second and the spawner's writer can come after the wait ends: then no thread is opened, the VM is kept and the spawner's thread owns it, and the person is told to run `sminos spawn --on <vm>` again later (exit 75).
  - A VM on sminos 1.53.0, the first that reads `--asked-from`, does not wait: it launches at once (an older VM refuses the call as a usage error, which the Mac says as an outcome not known), and the child's first message can reach no one in those minutes, until the host updates.
  - T3. Trigger: a `spawn --on` observed ending at row 27a, or MAWS's fix on the hosts (which brings the download to about a minute and a half, inside the wait).

## sminos channels (2026-11-22, CH1 of the channels composite; sminos 1.54.0)

Residue of CH1 (`docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md`): what the child accepts (its constraints' accepted list, the composite's reviews), what it leaves to CH2, and what its frontier review logged rather than fixed, each with what would promote it.

Accepted by the composite's reviews, built as accepted:

- **A sender removed from the org between a request's import and the endpoint's answer is honoured.** sminos holds a sender as verified from the key the import stored (`verified`), and the endpoint's `deliver` does not say whether it delivered for a verified sender, so a revocation that lands in that window is not seen. Closing it needs MAWS's answer to say which. T3. Trigger: MAWS's `reach?` answer gaining that field, or a removed sender seen to place a thread.
- **An absorption an older copy finishes drops what the provisional record had gained.** The merge (`_merge_absorbed`) is a step only this code's `finish` runs; a 1.51.0 or 1.52.0 finisher clears the entry without it, so the job's own adds are gone and a request it had answered is carried out again by the next pass. T3. Trigger: a mixed-version machine kept past the upgrade, or a job's membership seen lost at its absorption.
- **A return that keeps where a membership began from before the end.** An older copy's return writes no `began` (`test-older-cli.sh` asserts 1.51's and 1.52's), and so does this code's return over a channel whose log is there and cannot be read, for that channel (the holder's ruling, M3): what the channel gained while the thread was ended counts as after its membership began, so CH2 may push it once at the return. Nothing is lost or misaddressed. T3. Trigger: CH2 seen pushing an event from the thread's ended interval, or a channel log seen unreadable on a healthy machine.
- **A session an older copy joined into a channel and closed before this code's next reconciliation is listed in neither.** The undo (`retired` `moved`) and the re-join act on what a process or a seat holds; a closed session is left as the older copy left it until it runs again (`test-older-cli.sh`, `channel_join … closed`). T3. Trigger: an older copy found running by hand on a machine of the fleet.
- **A 1.51.0 or 1.52.0 copy's `list --json` shows a spawned thread's `began` and `answered`, and hides its `channels`.** Its `public_seat` hides only the seat keys it knows; the positions name the channel's other writers. Asserted as it is (`channel_seat`). T3. Trigger: a reader of an older copy's `list --json` found relying on those keys, or never once no copy before 1.54.0 runs.
- **A narrowing whose withdrawn audience could not be named leaves the old row standing in a roster,** as it does in the project's view: the roster is the view's rows. T3. Trigger: the project view's rule changing (the roster follows it), or a private thread seen in a roster it left.
- **Requests of two machines whose clocks disagree are carried out in the stamped order, and one stamped more than seven days behind is never carried out.** The merged log's order is by timestamp, and the expiry is read from the request's own `ts`. T3. Trigger: a request seen expired on arrival, or an add and a remove seen applied out of their real order.
- **Two adds contending for a thread's last place under the limit are not ordered.** Requests for different channels are not ordered against each other; the first that can be carried out takes the 128th place. T3. Trigger: a thread seen near the limit.
- **Two machines, or two commands at once, creating one name make two channels of that name.** `create` refuses a name a log known here answers to, but two creators who do not see each other's registration both mint; the name then resolves to neither and each is named by `name#short` or its id. T3. Trigger: two channels of one name seen in an org.
- **No lock holds a channel's log still.** Where a membership began, and the order of requests, are observed at the last read before the record's write, so an event imported between that read and the write counts as after it (a message so placed is one CH2 pushes; a request so placed is carried out as a later arrival). The rereads bound what one call acts on and close no window. T3. Trigger: CH2 seen pushing a message from before a membership began, or a request seen carried out ahead of an earlier one.

Left to CH2:

- **`chat <channel>`, `list <channel>` and a target qualified by a channel are refused.** `find_project` refuses a channel (`'<c>' is a channel, not a project: sminos channel show <c> prints it`), and `find_target` a `<channel>/<alias>` target (`… names a thread through a channel, which is not available in this version of sminos yet`): reading a channel's log as a conversation, and addressing through the roster, are CH2's, with speaking in a channel. T2. Trigger: CH2's plan.

Logged by the holder's triage of the frontier review (2026-11-22, `frontier-triage-1`):

- **A roster can list a thread's obsolete row for a moment.** While the reader holds a moved thread's destination `joined` and its end there but not yet the source's retirement, the source's row stands in the roster; it clears when the retirement arrives. Checking cross-project evidence for every live row is a read per row, and the roster's read cost is CH2's to measure. [sweep#5] T3. Trigger: CH2's measurement of the roster's cost leaving room.
- **A `join` between the choice of a statement's project and its write leaves the answer in the project left.** The set is repaired by the reconciliation in the project the thread moved to, but the answer is not copied there, so a requester who cannot read the old project reads the request pending until it expires. The holder's M2 ruling (no lock; a move in that window is the reconciliation's) stands; this is its cost. [scalpel-1#2] T3. Trigger: a request seen stuck pending this way.
- **A pool edit checked before the wait to append can be recorded by a thread removed meanwhile,** and is honoured if that thread is added again. The pool constrains nothing. Cosmetic. [scalpel-1#7] T3. Trigger: a pool seen to show a machine nobody added since.

Found while building:

- **The message path trusts a machine name.** `sminos_policy.outside_origin(e)` decides "outside" by the writer's machine name alone (`is_self`), and three read-only refusals rest on it: `deliver_next`, the words verdict and the words pass. So on a read-only machine a session-writer message the hub brings back under this machine's own name (a name reused after a machine was retired, a home rebuilt) is not treated as outside. A channel request is held to what this machine appended or receipted (`appended_here`, the frontier review's A2 and the holder's ruling on rows 8 to 11); a message is not. T3. Trigger: a machine name reused in an org.
- **A human-opened record a channel purge keeps cannot be purged by an ordinary `retire --purge` or `remove`.** An older copy's purge whose `retired` was owed to a channel's log keeps the ended record (`sminos_threads._finish`), since that record is then what keeps the session from being adopted again. `ended_target` reaches an ended record only through a real project's ended row, and the session's last event there is the older copy's `retired` `moved`, which gives none, so a full id does not reach it either. The record stays set aside, holding nothing live once its process is gone. Making it addressable by full id once its process is gone means a lookup outside the views. [L9; scalpel-3#3] T3. Trigger: such a record seen on a machine, or a request to remove one.
- **The uplink's thread can block in `finish_thread`.** A reconciling read (`view_of` → `_reconcile` → `finish_thread`, and the reconciliation's own writes) runs with no bound on the uplink's consumer thread, so a finisher lock or a writer lock held long stalls the uplink. The callers that still reach one there: every plane refresh (`Plane.tick`'s and `Link.members`' rereads, `Link.open`'s refresh of a project it opens), `members_before` at an upload and at the message words pass, and `member_under` at an upload of a channel's log (`senders_before`). Beside them, the request pass's own finish (`carry_out`'s `finish_thread(..., only=)`, its other locks bounded) still takes the registration's lock with no bound where the registration changed since the pass read it: `lifecycle` → `_append` → `store_path` → `project_path`, which rewrites `project.json` under `project.json.lock`. `member_under` at a channel's upload and that finish are CH1's (the first fix wave's A1, up to two projects read for a sender's frame; M7's request pass); the others predate CH1 (`bef6f74e` has them). CH1's request pass no longer reaches one (the second fix wave, C1: it tries every lock, finishes only the entry it committed, and reads its target's frame as the plane last read it, `member_on_lane`). Bounding the rest means a deadline through every reconciliation's writes, not only its finisher. T3. Trigger: a stalled uplink observed.

Logged by the holder's triage of the frontier review's second round (2026-11-22, `frontier-triage-2`; L9 is the row above that names it, and C9 was fixed, so there is no L16):

- **A remote-only add after the last holder left, and after its target dropped the subscription, is never seen by the target.** The requester's append reopens the channel's log on its own machine only as a follower; that puts the channel back neither in the directory nor on the target's machine, so a healthy target never reads the request, and it expires. [L4; sweep#2] T3. Trigger: a remote add seen expiring unread, or CH2's placement through the roster.
- **A request's authority is judged before the positions are read and not again after.** Two cases, of which only the first is the window the constraints accept (a reach narrowed between the evaluation and the record's write, under the session record's lock): with no endpoint word there is no reach check after the read, so a terminal's add can commit after the target's record changed to owners who did not authorize it. The second is not accepted, and is this row: with or without a word, a receiving machine that turned read-only during the read is not noticed, so an outside request is honoured past the switch. [L5; scalpel-1#1] T3. Trigger: a request seen honoured past an owner change or a read-only switch.
- **The last project guard misses a destination that joined during the positions read while the source has not retired.** The guard checks that the session is still a member of the source, so the answer is journaled to the project it is leaving; the destination's restatement recovers the set, not the answer (the cost of the logged `join` row above). [L6; scalpel-1#2] T3. Trigger: a request seen pending to its requester after its target moved.
- **The reach ask cannot say that a signed event was imported with no local receipt.** A store restored without its receipts reads an old signed request as from elsewhere, and MAWS's endpoint picks its local branch by the writer's name, which prefers the current member owners over the attested ones, so the new owners' reach can allow an old request. The holder tells MAWS's architect. [L7; scalpel-1#3] T3. Trigger: MAWS's `reach?` gaining a field for an import's provenance, or a store restored without receipts.
- **An older copy's refill addressed to a channel, cut before the channel's `joined`, leaves a queued replacement that no pass promotes.** A legacy entry is found through a channel's `joined`, and the daemon takes the channel pass only for channels it knows; a refill that vacated the seat and queued its replacement in a real project first is finished only by an explicit finisher of that thread (a verb that finishes its open entry before its own write, such as `channel add`, `retire` or `fill`); no reconciliation does, since each replays only the entries addressed to its own project (`open_entries`). [L8; scalpel-3#2] T3. Trigger: an older copy found running by hand, or a seat seen vacant with a queued `next`.
- **A legacy channel registration that names another org is not normalized when the directory lists the id.** `register_listed_channel` completes a registration with no well-formed hub; one naming another org is kept, so its stale label and org win, the uplink leaves the listed channel out as another org's, and its writes are refused (C3). Telling such a registration from real history of another enrollment needs a mark the registration does not carry. [L10; scalpel-3#4] T3. Trigger: a channel the directory lists seen left out as another org's.
- **An answer's attribution can rest on stamps of the answering writer alone.** `answer_of` takes a statement whose writer's session the thread's roster row lists, or, failing that, one whose writer's own `joined` is stamped with the target's thread; in the second case both come from that writer, and the endpoint's signature does not vouch for the thread, so an enrolled writer could mark a request applied or refused for a thread it never had and clear the requester's reason to follow the log. An enrolled writer is trusted, as in the machine-name row. [L11; scalpel-5#3] T3. Trigger: MAWS attesting a session's thread, or a writer seen answering for another's thread.
- **The leaving scan's duplicate check is quadratic in a channel's requests.** Each request is checked against all the earlier ones: 0.11, 0.42 and 1.58 s for 2,000, 4,000 and 8,000 requests of a followed channel, with no disk read. A one-pass index must keep the older expired requests, which still establish a duplicate. [L12; scalpel-5#4] T3. Trigger: a channel holding thousands of requests, or the leaving scan seen in the uplink's tick time.
- **`project init` converts an existing hubless `.smns` that holds a channel id before refusing it.** It hands the file to `add_hub`, which rewrites it and reports a hub project, and checkout resolution then refuses the channel id. The refusal belongs before the write. [L13; sweep#5] T3. Trigger: a `.smns` seen rewritten this way, or the next change to `project init`.
- **`create` checks a name against names only, not against a project id of the same text.** With a project whose id is `local-old` (named `old`), `create local-old` succeeds, but `show local-old` resolves the project's id first and refuses it: the new channel is reachable by its id and `name#short` only. [L14; scalpel-4#3] T3. Trigger: a channel seen unreachable by the name it was created with.
- **A followed channel whose legacy registration has a protected checkout root stays subscribed.** The leaving rule still applies the unreadable-root veto, which no channel needs (a channel holds no checkout), so such a channel with no member and no outstanding request is never let go, even once complete directories stop listing it. [L15; scalpel-4#4] T3. Trigger: a channel seen followed past the counted period.

Accepted by CH2 (`docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md`), built as accepted:

- **A message in a channel that names a thread an absorption took into another is owed to no one.** A channel's debt is keyed by the thread named (`sminos_channels.owed`), and no absorbed thread's id is kept: after the merge the thread that goes on is owed what names its own id, and what named the provisional thread, before or after, reaches no one; that thread's delivery record under the channel stays on disk, read by nothing, as an ended thread's does (the holder's ruling of 2026-11-22: an absorbable record is the one a session got of its own before its hand-off was read, so it lives for moments, and keeping its mail would need a key in the merge, a second record and lock for one event and a stale-mark rule in the wake). T3. Trigger: a report of a message in a channel that named a thread absorbed moments later and reached no one.
