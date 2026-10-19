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
| 33 | T3 | Two board readers disagree about a seat whose recorded status is `awaiting-human`. `_sweep_api.sh`'s `_liveness` reads every status outside working/blocked/idle/error as dead (PR #158, dp#60), so such a bound seat's lease is withheld and the relay refuses it, while `board-answer.sh` still accepts it as a seat waiting for answers. When #158 merged this took the lease from any worker that had parked itself with `sminos mark` (the #60 review, 2026-10-18). `mark` and its judgment statuses left in 7.125.0 (#185) and nothing writes `awaiting-human` now, so only a pre-7.125.0 record can carry it, and any such run was reclaimed long ago. Drop the status from `board-answer.sh`, or read it as live in `_liveness`, so the two agree | The next edit to either reader, or a record found carrying `awaiting-human` |
| 34 | T3 | `sminos who` follows a hand-off chain (`continued` → `to`) to its last session within the project the chain started in. When that last session later moved to another project known here (a background job that ran `sminos join`), `who` draws it from the old project: the old project name, the alias it had there, and a `say --in <old project>` note line that never reaches it (its override resumes it in the new one). Lineage is per-project, so the new project holds no `continues` link back. Fix: end the walk on a `moved` to a known project and draw the session from that project's view (review of PR smns-session-address, 2026-10-19) | A hand-off address resolved to a stale project in practice |
| 35 | T3 | A `claude --bg "<prompt>"` job joins sminos under its prompt text as its alias (the harness's first name for it, `nameSource: auto`), and `held_alias` keeps that alias over the title the harness later gives it, because a generated name never replaces an alias already held. `list` shows the whole prompt as the member's name. The address line works around it by naming the short alone (`ADDRESS_ALIAS_RE`); the alias itself is unchanged | Next touch of `held_alias` / a bg member's naming |
| 36 | T3 | `hooks/mods/address.tsx` asks the sminos CLI on the request path. The engine asks for the attribution text before every model request. When the kept line is a minute old (`ADDRESS_TTL_MS`) or the session id has changed, the hook awaits a fresh `sminos who --session` (a Python start, up to its 10 s timeout) before the request goes out; concurrent callers share that one ask. Stale-while-revalidate would take it off the path: return the kept line at once and refresh it in the background, so only a session's first ask waits | Request latency traced to the attribution hook, or the next touch of `address.tsx` |

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
- ~~**`test-sync.sh`'s "alpha reconnects once its stream is silent" can overrun its 6 s bound.**~~ **FIXED 2026-10-19**: a muted stream now writes no frame (`hub_standin.py`'s stream loop); the trigger fired as four red runs in thirty minutes on CI, one at 7 s.
  - The stand-in's `mute` stops a stream's heartbeat but still writes the frames queued for it.
  - Alpha's own lease lapsing flips its online state, so the stand-in sends an `org` frame down every open stream, the muted one included.
  - That frame restarts the uplink reader's silence timer, which is a socket timeout per read, so the reconnect can come late.
  - A real half-open stream carries nothing (the stand-in's own comment on `muted` says "nothing written"), so the stand-in is what diverges: a muted stream should hold every frame.
  - T3. Trigger: the next red run of this check, or the next edit to `mute`.

## sminos daemon: restart in place (2026-10-19, 7.186.1)

Residue of the review of `daemon run`'s restart in place on a code change (`restart_in_place`, sminos_daemon.py).

- **A SIGTERM in the instant before the exec is lost.** The loop reads `stop` after the uplink has stopped, then flushes and calls `os.execv`. A SIGTERM landing between that check and the exec is caught by the old image's handler and dropped, so the new image runs on. The stop then ends only at the service manager's SIGKILL: launchd's ExitTimeOut (20 s), or systemd's TimeoutStopSec (90 s), which also outlasts devcloud step 11's 60 s `systemctl --user restart`. The window is microseconds, right after a code-triggered uplink stop. The review proposed exec'ing with SIGTERM blocked (the mask and a pending signal survive execve) and unblocking it in `cmd_run`. That was declined: a rollback to code that predates the unblock would run with SIGTERM blocked for its whole life, and so would every uplink it spawns. T3. Trigger: a daemon observed running on after a stop that coincided with a plugin update. Then block SIGTERM only once the code being exec'd is known to unblock it, for example from a marker the new code declares.
- **The run lock is free for the instant of the exec.** Its descriptor is close-on-exec, so the lock is released and the new image takes it again with `LOCK_NB`. In that sub-second gap, `daemon status` reads "not running". A `daemon run` started by hand at that moment could take the lock, and the restarted image would then exit 1, leaving the service manager to restart it under its throttle. T3. Trigger: a restart in place observed exiting with "a daemon already runs". Then retry the lock briefly, or pass the descriptor across the exec.
- **Each restart compiles `sminos.py` twice.** `sminos.py` runs as `__main__`, so it has no cached bytecode, and both the restarted daemon and its new uplink compile it (8k lines, about 0.2–0.4 s each on a loaded host). That is most of the restart's uplink gap, which measured 0.5–1.6 s here at load average ~270, with one 4.4 s outlier. It also costs every `sminos` invocation, the Stop hook's `record` included. T3. Trigger: the gap or hook latency becomes visible. Then make the launcher import `sminos` as a module.

## plugin autoreload (2026-10-19)

Residue from the review of `hooks/mods/reload.tsx` (branch `plugin-autoreload`).

- ~~**An unanswered async question holds its session's reload indefinitely.**~~ **FIXED 2026-10-19 (7.188.5):** its trigger came with a `/reload-plugins` the human types, which the hold never covered. The ask mod keeps its asks and undelivered answers in `$.state`, which outlives a reload of the module (verified in source and live on 2.1.303: the host clears it only at the session's end; a typed `/reload-plugins` re-instantiates only the modules that changed), and the autoreload now holds only while an ask's dialog is up.
- **The watch keys on install records, while a reload loads path-sourced plugins from the clone's manifest.** A marketplace refresh with no plugin update (no record change) is therefore not acted on, and the snapshot after a reload records the record's path even where the session runs the clone's version. Harmless in the normal flow, where both move together. T3. Trigger: a missed or spurious reload observed.
- **The idle check reads the ask mod's turn flag, which leaves a few narrow windows.** (7.188.3, from the review of #260.) A look that lands between one main turn's end and the start of a prompt already queued behind it (the compact mod's resume prompt, a prompt typed mid-turn) still queues the reload behind that prompt. A module loaded mid-turn by a reload the reloader did not run (a `--plugin-dir` watch) reads idle until that turn ends. Whether a `$.command.run` issued during a compaction the bridge runs between turns waits for it is unverified. Each window is a few hook round trips wide, or needs a second install inside one turn. Since 7.188.5 a reload keeps the async asks, so what such a window can still cost is the compaction. T3. Trigger: a compaction failed with "a turn is in flight" across a reload again; then key the flag by turn id as `bridge.tsx` keys `state.mainTurn`.
- **A reload the autoreloader did not run, landing while an ask's dialog is up, can let the ask be answered twice.** (7.188.5, from the review of #262.) The old module's press dispatch outlives the reload: it takes the answer, delivers it, and writes its view to `$.state`. The new module took up the ask as open at its start and never reads the state again, so it still offers the ask (band, row, the desk's pending request), and its next save writes the ask back as open. A second answer then reaches the model. The autoreloader holds while a dialog is up, and a typed `/reload-plugins` cannot be entered while the dialog has the keyboard. What is left is a `--plugin-dir` watch, or a `/reload-plugins` queued during a turn that the engine runs with the dialog showing (unverified that it does). The cost is a duplicate answer, never a lost one. T3. Trigger: a duplicate answer seen. Then keep the raised asks in the snapshot, and have the module that took them up re-read the state before it offers, accepts or saves them.

## sminos daemon CPU (2026-10-19, 7.188.1)

Residue of the fix for `daemon run` and its uplink burning a core each on a machine that follows its whole org (F1 of the org directory's acceptance run; branch `smns-daemon-cpu`).

- **A tick's engine records predate its later projects' log reads (F5).** `tick_all` reads the engine's session records once, when its first project asks, and each project's log when its turn comes. A seat spawned inside that window has its `joined` in the log but no record in the tick's copy, so its first published word is `stopped` (or `gone`), and `publish_state` publishes a first word at once. Two ticks (10 s) later the right word replaces it. Before this fix the window was the whole 10-minute tick; now it is one tick's length (about 50 ms at the Macs' scale). T3. Trigger: a wrong first word observed after this fix.
- **Passes over many sessions read a transcript index up to TRANSCRIPT_FRESH (5 s) old.** In a long-lived process, a transcript created within that window is invisible to a view's state words (`gone` for `stopped`), to `refresh_joined`, and to the seat-side hand-off scan, until the next refresh. Every write or settlement that rests on a transcript's absence or content looks again (`transcript_now`, the `fresh` rechecks, `continued_in` before an `ended`, `push_member`'s `gone`, the sweeps), a listing begun within TRANSCRIPT_SHARED (0.25 s) counting as now so that one pass's many writes share it. What remains is a view up to one refresh behind, and a write that misses a transcript created in the quarter second before it. T3. Trigger: a decision found acting on a stale miss.
- **The uplink still forgets every cache each scan (SCAN_EVERY, 2 s).** Each scan re-resolves every seat's project and re-reads every project.json. That and the session plane's member refresh are most of the uplink's remaining 1.7 % of a core at the synthetic Macs' scale (`tests/sminos/bench_scale.py`). Keeping the seat projects across scans needs an invalidation the scan does not have today. T3. Trigger: idle CPU above a few percent on a machine.
- **The per-process file caches keep entries for removed files.** `_SEAT_FILES`, `_LOG_FILES` and `HubLog.files` (its own-writer pass) drop an entry only when its file is read again and fails. Memory is bounded by the files a process has ever seen; a long-lived daemon on a machine that removes many seats or logs grows by their parsed size. T3. Trigger: daemon memory growth observed.

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
