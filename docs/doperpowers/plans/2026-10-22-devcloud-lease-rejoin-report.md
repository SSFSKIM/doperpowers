# devcloud: a host's tailnet node kind follows its lease (board #115): execution report

- Ticket: board #115 (the api board binding), "devcloud vm: a host's tailnet node kind follows its
  lease (rejoin on keep↔lease)". Its body was the statement of work; the person's decision is in it.
- Design home: `docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`, §4.1 (the node
  kind passage), §6.5, I16, Out of scope, Surprises (2026-10-22) and Decision Log (board #115).
- Branch: `devcloud-lease-rejoin`, off origin/main at c3310869 (the driver's merge, devcloud 0.7.0).
- Executed 2026-10-22 (UTC) by a plan-executor, worked in order: no milestones.

## Status

STATUS_PLACEHOLDER

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
