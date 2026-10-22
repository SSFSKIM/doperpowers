# devcloud: a kept or adopted host removes its tailnet node when it leaves for good (board #118): execution report

- Ticket: board #118 (the api board binding). Its body was the statement of work, and #115's residue
  was the reason for it.
- Design home: `docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`: §4.2 step 4, §4.3
  ("The deleted host's tailnet nodes"), §4.4, §6.5 step 5, Out of scope, Surprises and the Decision
  Log (board #118).
- Branch: `devcloud-node-removal`, off origin/main at a49fb156 (devcloud 0.8.1). devcloud is bumped
  to 0.9.0.
- Executed 2026-10-22 (UTC) by a plan-executor, worked in order: there were no milestones.

## Status

Done. Every success criterion was shown live on GCE or by a unit test, and every VM this work made
was deleted by 06:30Z. The review at the high rung had two rounds: the first found one P2, fixed in
cc89c735, and the second is in the PR's Validation Evidence.

| Criterion | Evidence |
|---|---|
| `down` on a kept VM leaves no node | `dc-nrm-09a9`: the host's `remove-node` removed it during the departure (below) |
| a lease→keep→down sequence leaves no node | the same VM: `lease 2h`, then `lease keep --confirmed`, then `down` |
| an adopted machine's release leaves no node | `dc-adp-ad0f`: removed by the machine's release, before the driver looked |
| `down --force` on an unreachable kept VM removes its node through the driver | `dc-unr-9284`: tailscaled stopped, then `down --force`; the line names the node id removed |
| the Tailscale API confirms it, and the VMs are deleted the same day | the API's device list read after each run; GCE lists none of this work's VMs |
| unit tests for each path, including a removal that fails (logged, and the departure completes) | `test_departure` (DepartNodeRemovalTest, ReleaseNodeRemovalTest), `test_driver_tailnet`, `test_driver_adopt` (ReleaseRemovesTheNodeTest), `test_tailnet` (devices) |

## What was built

- **Host** (`devcloud/boot/devcloudlib/`):
  - `departure.mark_node` runs before the ready line. It records the held node's id as pending
    removal in `tailnet.json`, unless the recorded kind is ephemeral; an unknown kind counts as
    non-ephemeral.
  - `departure.remove_node` is a new step, `remove-node`, that runs right after the logout in
    `depart`, the spot reclaim and `release`. It removes every pending id through
    `steps.remove_pending`, which is #115's rejoin loop factored out. It keeps three tries, counts a
    404 as removed, and never removes the node held.
  - A failure never stops a run. In the release it comes before `remove-units` and
    `remove-credentials`, since the seed reads the OAuth client.
  - `nodekind.pend`, `steps.fetch_text`, and `tsapi.devices` with a timeout on every call.
- **Driver** (`devcloud/driver/tailnet.py`; `ops.py`, `reaper.py`, `adopt.py`, `context.py`):
  - After every successful VM delete, and after an adopted machine's verified release, the driver
    lists the devices with the hosts' client. It removes, by nodeId, each device tagged
    `tag:devcloud` whose `hostname` is exactly the host's name, and names each id on the deletion's
    line (and in `reap.log`).
  - The removal never raises, and it stops asking the API once a bounded run's time is spent.
- **Docs:** the spec (above, plus H12, Progress, Outcomes) and the README's `down` paragraph.

## Decisions

- **The driver removes after every VM delete, not only an unreachable kept VM's.** The host's own
  removal comes after the logout cuts the driver's SSH, so the driver cannot read whether it
  happened, and the delete that follows can cut it short. One rule covers both. It also removes
  ephemeral nodes of deleted hosts, which then go at once instead of an hour later. The main
  session agreed, and set the exact match: tag plus exact hostname, by node id, only after the
  delete or the verified release, ids logged.
- **No node id in provider labels.** GCE label values are lowercase and node ids are not, and every
  rejoin changes the id, so the lookup would be needed anyway.
- **Out of scope, as the brief said:** the reaper sweeping orphan `tag:devcloud` nodes. That is a
  deletion by inference, and the person has not approved one.

## Live evidence (GCE default account, 2026-10-22 UTC)

The person gave the approvals through the main session on 2026-10-22: "Start, approve both
(Recommended)" for one kept VM and one adoption, then "Approve (Recommended)" for a second kept VM
(the unreachable case). Each was used once.

| When | What | Result |
|---|---|---|
| 06:13:10–06:17:55 | `up --label nrm --keep --confirmed` | `dc-nrm-09a9`, slow path, ready in 4m45s; non-ephemeral node, `tag:devcloud`, API `hostname` = the VM's name |
| 06:18:09 | `vm lease dc-nrm-09a9 2h` | rejoined ephemeral under the same name (API: a new node id, `isEphemeral`) |
| 06:18:29 | `vm lease dc-nrm-09a9 keep --confirmed` | rejoined non-ephemeral under the same name; host record `ephemeral: false`, `remove: []` |
| 06:18:59–06:20:30 | `vm down dc-nrm-09a9`, with the API polled every 3 s | the node was listed until 06:19:12 and gone from 06:19:15. "departed and deleted", with no node note: the host's `remove-node` had removed it before the driver looked |
| 06:13:20 | a plain Ubuntu 24.04 e2-small made by hand with gcloud, no service account, login user `adopter` with the person's key | `adopt-plain-118` |
| 06:14:31 | first `vm adopt … --confirmed` | refused by the account preflight, with nothing changed: GCE's guest agent had made an account named after the Mac's user from the project's ssh-keys. Fixed with `block-project-ssh-keys=TRUE` and that account deleted on the hand-made VM |
| 06:15:23–06:28:05 | `vm adopt adopter@<address> --label adp --confirmed` | `dc-adp-ad0f`, adopted in 12m32s; non-ephemeral node |
| 06:18:01–06:22:14 | `up --label unr --keep --confirmed` (the second approval) | `dc-unr-9284`, ready in 4m12s |
| 06:22:4x | tailscaled stopped on it (`systemd-run --on-active=5`), then `vm down dc-unr-9284` | refused: "does not answer over the tailnet: pass --force" |
| 06:23:08–06:24:19 | `vm down dc-unr-9284 --force` | "deleted without its departure (unreachable); … its tailnet node n2v3…CNTRL removed through the Tailscale API"; the API lists nothing of it |
| 06:28:26–06:29:59 | `vm down dc-adp-ad0f`, with the API polled | "released; the machine keeps running". The node was gone by 06:29:40, before the driver looked. On the machine: tailscale "Logged out.", no `/var/lib/devcloud`, and `lifecycle.log` in order: status read, logout, status read, the seed's access token (the client fetch), then the unit removal |
| 06:30:29 | `adopt-plain-118` deleted by hand | GCE lists none of this work's VMs; the API lists no `dc-nrm`, `dc-unr` or `dc-adp` node |

The live hosts ran the branch's code: the driver ran from this worktree, which streams its own
`devcloud/` to a slow-path host. The two kept VMs and the adoption ran 46d05130's code. The forced
delete ran cc89c735's driver, whose only change is the bounded run's deadline.

## Resources created and deleted

| Resource | Created | Deleted |
|---|---|---|
| `dc-nrm-09a9` (kept, approval 1) | 06:13Z | 06:20Z, `down` |
| `dc-unr-9284` (kept, approval 3) | 06:18Z | 06:24Z, `down --force` |
| `adopt-plain-118` (the machine for approval 2) | 06:13Z | 06:30Z, by hand, after its release |
| the three hosts' tailnet nodes, and the two old nodes from `dc-nrm-09a9`'s rejoins | by the joins | the rejoins and the host's own removal; `dc-unr-9284`'s by the driver |

Desk: the driver's line for `dc-unr-9284` said the desk still listed it, as for any VM deleted
without its leave. `sminos machines` at 06:31Z listed none of the three.

## Review

The review ran at the high rung (`doperpowers:reviewer-high`) on a49fb156..head.

| Round | Head | Findings | Fixed in |
|---|---|---|---|
| 1 | 46d05130 | 1 P2: the bounded reaper's 60 s could be overrun inside the node lookup, because the budget was checked only on entry | cc89c735 (a fix-wave agent, failing test first) |
| 2 | cc89c735 | see the PR | — |

## Friction

- **The MacBook crashed mid-build.** The worktree's uncommitted work survived, and I committed it
  as WIP (138bbfb6). No live resource existed yet.
- **A hand-made GCE VM gets an account from project ssh-keys.** The account preflight refused the
  adoption. The friction tracker (#304) already has the row.
- **The machine's load average was 300.** The unit suites ran 10× slower than usual; nothing
  failed for it.

## Board and repository writes outside the branch

None. The ticket's transitions are the main session's.

## Residue

None.
