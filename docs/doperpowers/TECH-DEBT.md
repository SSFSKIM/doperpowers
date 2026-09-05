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
| 4 | T2 | No CI/pre-push gate on the shell test suites | Next test-drift incident, or opportunistically |
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
| 17 | T3 | `_binding.sh` derives the main checkout as the parent of `git rev-parse --git-common-dir` — for the credentials slug since A2 and, since doperpowers#12, for the `board.json` fallback in a linked worktree. Git does not guarantee that layout: `--separate-git-dir`, a bare-hosted worktree set, or a submodule puts the common dir elsewhere and the probe lands on an unrelated path (fallback → gh, slug → a token file nobody wrote). Every checkout this fork dispatches into is a plain clone plus `git worktree add`; resolve the primary worktree from `git worktree list --porcelain` in both places together if that ever changes | First dispatch into a separate-git-dir / bare-hosted / submodule checkout |

## T1 — structural: the unattended-dispatch phase must answer these

### 1. Manual recovery from transient worker deaths

Three worker turns died on transient upstream failures during the shakedown
(model-at-capacity, two stream disconnects). `codex-resume.sh` recovered all
three — but only because an operator was watching. Unattended, a dead worker
sits in `error` and its ticket in `in-progress` until `board-reconcile.sh`
flags the orphan **and a human acts**. The auto-attach trigger phase
(doperpowers:executing `scripts/`, unbuilt) must specify a
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

### 4. No CI or pre-push gate on the test suites

The protocol-content test carried two stale assertions for a full
commit-cycle because suites are run by hand — found only when the shakedown
happened to run it. A pre-push hook (or minimal CI) running the three
skill-infrastructure suites (`tests/sminos/`,
`tests/executing/`, `tests/qa-loops/`) closes the class.

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
