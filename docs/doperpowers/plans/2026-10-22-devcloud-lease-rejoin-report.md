# devcloud: a host's tailnet node kind follows its lease (board #115): execution report

- Ticket: board #115 (the api board binding), "devcloud vm: a host's tailnet node kind follows its
  lease (rejoin on keep↔lease)". Its body was the statement of work; the person's decision is in it.
- Design home: `docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`, §4.1 (the node
  kind passage), §6.5, I16, Out of scope, Surprises (2026-10-22) and Decision Log (board #115).
- Branch: `devcloud-lease-rejoin`, off origin/main at c3310869 (the driver's merge, devcloud 0.7.0).
- Executed 2026-10-22 (UTC) by a plan-executor, worked in order: no milestones.

## Status

Done. Every success criterion of the ticket was shown live on GCE, and the board #115 entries are
in the spec. The high-rung review took three rounds and the last was clean. Every resource this
work made is deleted. The PR is open against main, not merged.

| Criterion | Evidence |
|---|---|
| `lease <n> 2h` on a keep VM makes the node ephemeral, same name, `vm ssh -- true` works | `dc-kpt-e642`, 01:47:44Z: API `isEphemeral`, name unchanged, ssh exit 0 (live table) |
| the same on an adopted machine; its release at lease end passes acceptance 7's give-back checks | `dc-adp-c8b4`, 01:50:57Z, and the timed release at 02:14Z (live table) |
| `lease <n> keep --confirmed` rejoins non-ephemeral | `dc-kpt-e642`, 01:48:22Z; unconfirmed `keep` exits 4 |
| unit tests for the decision logic | `test_tailnet` (NodeKindTest, RejoinRunTest, TsApiTest), `test_lease` (keep, NodeKindFollowsTheLeaseTest), `test_driver_ops` (LeaseKeepAndRejoinTest, cut-off answers), `test_driver_adopt`, `test_driver_reaper`, `test_driver_provider`, `test_descriptor_lease`; the whole unit suite ran 677 tests OK |
| one live GCE run, VM deleted the same day | the approved keep VM (deleted 01:50Z) and adoption (02:16Z), plus three throwaway VMs, all deleted |
| the Decision Log gets the person's decision; the TECH-DEBT entry removed | spec Decision Log, board #115 entries; the entry is gone from `docs/doperpowers/TECH-DEBT.md` |

## The open question, answered first

`tailscale logout` does not remove a non-ephemeral tagged node. Measured on a throwaway leased GCE VM
(`dc-lgt-3d09`, 01:03–01:46Z):

| Step | What the tailnet did |
|---|---|
| ephemeral node, logout, `up` non-ephemeral | the old node left at once; the new node kept the name (as M1 found) |
| non-ephemeral node, logout | the node stayed in every peer's status, offline and `Expired`, under its name; the API still listed it |
| `up` ephemeral after that | joined as `dc-lgt-3d09-1` |
| `tailscale up --force-reauth` with a key of the other kind | a new node again (`-2`); a node's kind cannot change in place |

The API's device record carries `isEphemeral: true` for an ephemeral node and omits it otherwise.
The API is the one place a node's kind shows, and the live checks below use it.

The OAuth client hosts joined with turned out to hold far more than the spec's "only the auth-keys
scope". Its token reported `devices:core:read devices:posture_attributes policy_file dns auth_keys
users`, so every host could rewrite the tailnet's policy. It could not remove a device.

## The fork, and what the person decided

Removing the old non-ephemeral node needs the `devices:core` scope. I put two options to the main
session:

- **A:** a client with `auth_keys` + `devices:core` on `tag:devcloud`; the host removes its own old
  node.
- **B:** every node ephemeral, leased or kept, and a re-join after an outage.

The main session first leaned to B. The reason: a `devices:core` credential can probably remove any
device in the tailnet, and tags do not bound that. The person chose A knowing this. Their guard is a
soft-deny auto mode rule in the profile: an agent deletes no tailnet device without the user's
authorization of that device.

The main session then replaced the client: version 2 of the same Secret Manager secret, scopes
`auth_keys` + `devices:core` on `tag:devcloud` only. It revoked the old, broader client and disabled
version 1. Both hosts made after the switch joined with the new client: the API's `oauthClientId`
on each names the new client.

## What was built

- **Host** (`devcloud/boot/`):
  - `nodekind.py` records the kind each join asked for, and the name the tailnet gave, in
    `/var/lib/devcloud/tailnet.json`; a node whose recorded kind is not the one its lease wants is
    behind.
  - `tsapi.py` covers the Tailscale API from the standard library: the OAuth token with its scopes,
    and the removal of a node by id.
  - `steps.py` holds the join and the rejoin:
    - A join records the kind it made. A joined node that is behind rejoins:
      1. The token's scope is checked before anything changes, for a node that is not ephemeral.
      2. Logout.
      3. API removal of the old node by id, tried three times.
      4. `up` as the wanted kind.
      5. The new name is recorded.
    - `devcloud rejoin` runs that rejoin as the `devcloud-rejoin` unit, under the lifecycle lock,
      leaving a running boot to its own tailnet attach. It refuses once the departure has started.
    - The boot's tailnet attach converges the kind the same way. A refusal there does not fail the
      boot.
  - `lease.py`:
    - `lease set keep` removes the lease.
    - A lease write that leaves the node behind records `rejoining`, starts the unit, and prints
      `rejoin <kind>` before the lease.
    - The lease service restarts the rejoin while the node stays behind, on kept hosts too, and
      never at the cost of the lease end's departure.
- **Driver** (`devcloud/driver/`):
  - `lease <name> keep` needs `--confirmed`. It relabels the VM `keep` and confirmed, with its
    expiry label dropped (`set_labels(..., drop=…)`).
  - On a `rejoin` line the driver waits up to 10 minutes, reading the host's record over SSH by name
    until the node is joined as the wanted kind under the host's name.
  - Adopted machines do the same through their record.
- **Docs:** the spec (§4.1, §6.5, I16, Out of scope, Surprises, Decision Log), the README, the vm
  skill's lease paragraph, and `docs/doperpowers/TECH-DEBT.md`, whose entry is removed. devcloud is
  bumped 0.7.0 → 0.8.0.

## Live evidence (GCE default account, 2026-10-22 UTC)

The two approved resources were used once each, as approved. The person gave both approvals on
2026-10-22 through the main session, "Approve (Recommended)" each.

| When | What | Result |
|---|---|---|
| 01:34:51–01:39:29 | `up --label kpt --keep --confirmed` (the approved keep VM) | `dc-kpt-e642`, slow path, ready in 4m37s; joined non-ephemeral with the new client (API `oauthClientId`), `tag:devcloud` |
| 01:47:44 | `vm lease dc-kpt-e642 2h` | "rejoining … as an ephemeral node", back in 15 s under the same name. The API shows `isEphemeral`; the record says "the old node … removed through the API"; `vm ssh dc-kpt-e642 -- true` exit 0; labels `ttl`, expires set, confirmed 1 |
| 01:48:22 | `vm lease dc-kpt-e642 keep` | exit 4, "needs the person's yes … --confirmed"; nothing written |
| 01:48:22 | `vm lease dc-kpt-e642 keep --confirmed` | rejoined non-ephemeral in 15 s under the same name ("the ephemeral node left at its logout"). The API shows non-ephemeral; ssh exit 0; no `DEVCLOUD_EXPIRES` on the host; labels `keep`, no expires, confirmed 1 |
| 01:48:52–01:50:33 | `vm lease … 2h`, then `vm down dc-kpt-e642` | rejoined ephemeral in 14 s; then "departed and deleted"; the API no longer lists the node |
| 01:33:08 | a plain Ubuntu 24.04 e2-small made by hand with gcloud, no service account, a login user with the person's key | `adopt-plain-115` |
| 01:34:39–01:45:34 | `vm adopt <login>@<address> --label adp --confirmed` (the approved adoption; lifetime keep) | `dc-adp-c8b4`, adopted in 10m45s; non-ephemeral, the new client |
| 01:50:57 | `vm lease dc-adp-c8b4 20m` | rejoined ephemeral in 8 s under the same name; the old node removed through the API; ssh exit 0 |
| 02:10 (lease end) | the lease service's release | the creator's warning reached the main session first ("dc-adp-c8b4's lease ends at 2026-10-22T02:10Z; unpushed: none"). The node left the tailnet at 02:14:07Z. The release journal: logout ok, 16 credential paths and the ledger removed, released |
| 02:14:48 | acceptance 7's give-back checks, over a new SSH as the original login | no ledgered path remains; the ledger, `hub.json`, devcloud's units and the `inet devcloud` table are gone; tailscale `NeedsLogin` |
| 02:15:19 | `vm down dc-adp-c8b4`, then a reset of the machine | "already released …; its record is removed"; `vm ls` no longer lists it; a new SSH as the original login after the reset worked |
| 02:16:50 | the hand-made VM deleted by hand | GCE lists none of this work's VMs; the tailnet lists no `dc-` node |

Both live hosts ran the branch as it stood at 01:34Z: the commits through 275f8fc2, plus the
working tree's code, which then equalled 08a0a3c1's. Later commits changed only failure paths that
these runs did not take; see the fix wave below.

## Resources created and deleted

| Resource | Created | Deleted |
|---|---|---|
| `dc-lgt-3d09` (throwaway, the measurement) | 01:03Z | 01:46Z, `down --force` (unreachable by name, its node renamed by the measurement). The desk still lists it: its leave never ran. The main session asked the person to remove it by hand |
| its tailnet nodes `dc-lgt-3d09` (expired) and `dc-lgt-3d09-2` (non-ephemeral) | the measurement | 01:47Z, through the API by node id, authorized by the person for exactly these two |
| `dc-lgt-3d09-1` (ephemeral) | the measurement | expired by itself (gone by 02:16Z) |
| `dc-kpt-e642` (the approved keep VM) | 01:34Z | 01:50Z, `down` |
| `adopt-plain-115` (the approved adoption's machine) | 01:33Z | 02:16Z, by hand |

A third throwaway VM, `dc-rck-60ac` (02:32–02:49Z), re-checked the fix waves' code live. A record
faked to claim a non-ephemeral node made `devcloud rejoin` log out and remove the old node: the API
answered 404, already gone. It then rejoined ephemeral under the same name and left nothing
pending. This ran twice, on 5321a4e8's code and on d5e5a2ab's, copied onto the host. A hard reset
then booted with "already joined" and the same node id. A logged-out daemon reports an empty
`Self.ID`, so the second round's guard does not cancel a removal after a real logout.

## Review

The review ran at the high rung (`doperpowers:reviewer-high`) on c3310869..head, in three rounds.
Each round's fixes came from a fix-wave agent, with a failing test first.

| Round | Head | Findings | Fixed in |
|---|---|---|---|
| 1 | 0020899c | 4 P2: the old node id lost between logout and removal; a Stopped or Starting backend taken for no node; a complete `lease set` answer dropped when the rejoin cut SSH; the reaper unable to relabel a host that became kept | a1bd8fd3, 72d10505, 5321a4e8 |
| 2 | 5321a4e8 | 2 P2 in that fix: a pending removal could delete the node still held (a logout that failed without effect, then a reversed lease); a boot with an unreadable status recorded a kind it could not know | d5e5a2ab |
| 3 | d5e5a2ab | none: "correct" | — |

Some smaller points the fix wave raised were left as they are, each logged in
`docs/doperpowers/TECH-DEBT.md` under the driver's section:
- a `-1` name kept after a late removal;
- a refused rejoin retried without backoff;
- a Stopped node whose rejoin is refused stays Stopped;
- two loose messages.

## CI

The ci-kit gates on GitHub Actions:
- 275f8fc2 and 0020899c were GREEN.
- 5321a4e8 and d5e5a2ab passed every gate but `mods-types`, which was cancelled both times. That
  gate's `npm i -g @anthropic-ai/claude-code` step hung until its timeout. This change touches no
  mods code. The result on the final head is in the PR.

## Decisions and deviations

- **The design changed after the measurement, through the person.** The ticket assumed a
  logout could remove the old node. It cannot for a non-ephemeral node, so the host removes it
  through the API. That needed the `devices:core` scope, and the person chose it (A) over making
  every node ephemeral (B), knowing its reach.
- **The kind is recorded, not read.** No status field shows it. An unrecorded or unknown kind
  counts as behind; that is safe, because a removal never touches the node the daemon holds.
- **The lease service converges every persistent host**, not only leased ones, so a rejoin that
  failed or never started is retried, and a pending removal with it.
- **The driver accepts a cut-off `lease set` answer** when it holds a `rejoin` line and the lease:
  the rejoin can cut the SSH session that asked for it.
- **Out of the ticket's scope, left as residue:** removing a kept host's non-ephemeral node when it
  departs, is released, or is deleted unreachable. The main session suggested it "if small"; it
  touches the departure's logout step and the reaper, and I left it for its own ticket.

## Friction

- **An auto mode block on an approved adoption.** `devcloud vm adopt … --confirmed` was blocked as
  "[Real-World Transactions]", though the person's approval had been relayed. An appeal quoting the
  relayed message was granted. I updated the matching row of the friction tracker (#304).
- **`systemctl reboot` from a transient unit on a GCE VM did nothing.** The VM kept its uptime, and
  `gcloud compute instances reset` did the reboot instead. Seen once; not tracked.
- **The `mods-types` gate's `npm i -g` hung twice** (above).
- **The secrets guard redacts made-up literals in test files when it shows them.** A heredoc edit
  anchored on the shown text then fails to match; the Edit tool restores the values. Known
  behavior; it cost one retry.

## Board and repository writes outside the branch

- The friction tracker issue #304: one row updated.
- The person's profile repository (`~/.claude`): the client-id comment, committed locally and not
  pushed. The main session asked for the edit, and its sync owns the pushes there.
- Board #115 moved to in-review with the PR, as the brief asked.

## Residue

- **Remove a kept host's tailnet node when it leaves for good.** A non-ephemeral node stays listed,
  expired, after a departure's or a release's logout. That covers `down` of a kept VM and the
  release of a kept adoption; a kept VM deleted unreachable (`down --force`) leaves its node online
  in the listing until it expires nowhere. The host now holds a `devices:core` client: the
  departure could remove its own node after the logout, and the driver could remove the node of a
  kept VM it deletes without a departure.
- **Desk machine `dc-lgt-3d09`.** The measurement VM was deleted without its leave, so the desk still
  lists it. The main session has asked the person to remove it by hand.
