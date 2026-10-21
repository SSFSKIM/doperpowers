# devcloud VM driver — a session gets its own cloud machine, and it cleans up after itself

**Date.** 2026-10-21. **Status.** Design approved in conversation (2026-10-20/21); two independent
reviews (spec, buildability) folded in on 2026-10-21 as the fifteen decisions dated that day in the
Decision Log. **Parent.** `docs/doperpowers/specs/2026-10-15-devcloud-design.md` (the host image
and boot program; it put "provisioning drivers" out of scope, and this spec is that driver).
**Prior art in this repository's family.** M5's throwaway provisioner (an untracked script that
created, seeded, booted and deleted one Hetzner VM by hand), and ci-kit's runner pool
(`docs/pool.md` in the ci-kit plugin: label-scoped Hetzner resources, a baked snapshot, a guard
that deletes what outlives its purpose).

## Purpose

The person runs dozens of Claude Code sessions on two Macs, and the Macs run out: a load average
above 500 on the MacBook was measured during the parent initiative. The parent made any Linux
machine a host that works like the Macs, but someone still had to create the machine by hand. After
this work a session can, on its own judgment and within limits the person set, ask for a cloud
machine, get one with its project already prepared, put work on it, and have it disappear on time
with nothing left behind but the work and the transcripts:

    devcloud vm up --label build --project owner/repo     # a few minutes later: dc-build-7f3a, ready
    devcloud vm ssh dc-build-7f3a -- sminos spawn build "run the full test matrix and open a PR" \
        --cwd ~/Developer/GitHub/repo
    # the seat runs on the VM; the person watches and steers it from the desk like any other session;
    # its transcript lands in the session store; twelve hours later the VM ends its sessions, ships
    # their last transcript lines, leaves the desk and the tailnet, and is deleted

The machine comes from whichever provider the project prefers (`devenv/host.toml`) or the person's
default: Hetzner Cloud and Google Compute Engine ship here, any other cloud can be added as a
provider executable the person registers once, and any Ubuntu server the person already runs can be
adopted instead. A throwaway machine that a session creates needs nobody; a machine meant to stay, a
bigger one, or more of them than the limit needs the person's yes.

How to see it working: from a session on a Mac, `devcloud vm up --project <a repo with devenv/>`
prints a name; `devcloud vm ssh <name> -- devcloud status` shows every boot step `ok`;
`sminos machines` lists the machine online without anyone having typed an enrollment code;
`devcloud vm lease <name> 35m` makes the creating session receive a warning, and some minutes after
the lease ends `devcloud vm ls` no longer lists the machine, the tailnet no longer shows it, and the
desk no longer counts it.

## Progress

- [x] (2026-10-21) Design approved; spec written.
- [x] (2026-10-21) Independent reviews (spec, buildability); their findings and one design decision
  of the person's folded in (Decision Log, fifteen entries dated 2026-10-21).
- [ ] M1 — Spike: the preflight, and the live facts the design leans on.
- [ ] M2 — The host side: leases and their lock, departure, release and its ledger, the closed public
  port, unattended enrollment, desk control.
- [ ] M3 — The driver core, the provider protocol and the Hetzner provider, with the reaper.
- [ ] M4 — Images and project host files.
- [ ] M5 — The GCE provider, adopt, and the open provider path.
- [ ] M6 — The skill, the always-on Mac, and acceptance.
- [ ] Whole-branch review (high rung), Outcomes & Retrospective, PR.

Human steps this initiative needs. The executor prepares each (the exact command, the page, what to
check) and escalates it at the milestone named; the person runs it when an automated attempt is
refused or it needs a browser or their judgment.

| Step | What | Owner | When |
|---|---|---|---|
| H1 | The Hetzner devcloud project's API token into Secret Manager | the person | escalated by M1's preflight if missing |
| H2 | The GCE host service account and its Secret Manager grant | the executor if its account is permitted, else the person | M1's preflight |
| H3 | The seed key file onto the always-on Mac | the person | before M6 (acceptance 5, 11) |
| H4 | A desk provisioning key, `offline_revoke_s` 24 h, into Secret Manager | the person, once the desk ships keys | M6 verifies its policy value |
| H5 | A tailnet ACL rule letting the Macs reach `tag:devcloud` on port 22 | the person | only if M1 finds it blocked |
| H6 | Removing the parent's leftover test machine `devcloud-m5` from the desk's Machines | the person | an M6 step; evidence: `sminos machines` no longer lists it |
| H7 | Confirming the registration of M5's test provider (`provider register --confirmed`) | the person | M5 |

## Terms

The parent's terms hold (host, substrate, role, boot descriptor, profile, seed credential, gateway,
session store). New here:

- **Driver**: `devcloud vm`, the command that creates, lists, reaches, leases and deletes hosts. It
  runs on the person's Macs: a driver is a machine whose profile is a configuration checkout that
  pushes, because its SSH key reaches the machines it makes through the profile (§8.3). A host
  receives configuration and never pushes it (the parent's §5), so a key a host generated could
  never reach the profile; on a host the command refuses (§8.4).
- **Driver core**: everything in the driver that is the same for every cloud — naming, caps,
  labels, leases, the reaper, seed delivery, waiting for the boot, SSH, the down guard, adopt (§1).
- **Provider**: an executable that translates the driver core's operations into one cloud's API,
  speaking the provider protocol (I13): one operation per call, JSON on stdin and stdout. The
  **shipped providers** (`hetzner`, `gce`) live in the plugin; a **profile provider** lives in the
  person's profile and is usable once its conformance test passes and the person has registered it
  (§6.2).
- **Account**: one provider login the person registered in the profile's `driver.toml` (Interfaces
  I10): a provider, the Secret Manager ids of its credentials, its settings and defaults. A project
  chooses among accounts by name; it never supplies one.
- **Lifetime**: `ttl` — the host has a lease and departs when it ends — or `keep` — no lease. This
  is independent of the parent's role: every VM the driver makes has role `persistent` (systemd, its
  own machine identity), whatever its lifetime. The parent's definition of `persistent` ("long-lived")
  is narrowed accordingly (Decision Log).
- **Lease**: a host's expiry, a Unix time. The host's descriptor (`DEVCLOUD_EXPIRES`) holds the
  authoritative value; the provider label `devcloud-expires` is a cached copy, used when the host
  cannot be reached (§4.1).
- **Lifecycle lock**: `/run/devcloud/lifecycle.lock` on a host, a `flock` that serializes lease
  writes, the lease service and departure (§4.1).
- **Departure**: what a host with an ended lease does to itself: end its sessions, ship their last
  transcript lines, leave the desk, log out of the tailnet, power off (§4.2). A departure whose ship
  fails is **held**: it stops before leaving anything and is retried.
- **Release**: the departure of an adopted machine, which also removes devcloud's firewall, restores
  the SSH access the machine had, and removes every credential its ledger lists, and keeps the
  machine running (§6.5).
- **Credential ledger**: `/var/lib/devcloud/credentials.ledger` on a host, every path where devcloud
  wrote a credential, each appended before its write; release removes what it lists (§6.5).
- **Adoption record**: the driver's file for one adopted machine,
  `~/.local/state/devcloud/adopted/<name>.json` — the one piece of lifecycle state the driver keeps
  locally (§6.5).
- **Reaper**: `devcloud vm reap`, which deletes what outlived its lease, its purpose or its
  retention, and unconfirmed throwaway VMs above the cap (§4.3).
- **Image**: a provider-side disk image with the parent's `image/setup.sh` already applied, so a VM
  starts in minutes rather than installing everything (§7).
- **Recipe hash**: a short digest of `devcloud/image/` and `devcloud/boot/` at the plugin version in
  use; an image is current when its recorded hash equals the driver's.
- **Confirmed request**: `--confirmed` on a `devcloud vm` command. It says the person approved this
  specific request; the driver requires it for anything beyond the caps, for `keep`, for `adopt`,
  and for registering a profile provider (§2, §6.2). A VM created with it carries
  `devcloud-confirmed=1` and does not count toward the throwaway cap.
- **Provisioning key**: a desk credential, reusable and revocable, that lets a machine enroll at the
  desk without a person (§10). The desk builds it; this work consumes it.

## Acceptance

Run from a session on the MacBook unless a check names the always-on Mac. `<n>` is the name `up`
prints. Every VM created is deleted the same day and its deletion recorded in Progress. The desk
parts of checks 1, 3, 5 and 7 need the sminos release that carries I15; until it is installed they
are reported "blocked on the desk", never passed (Constraints).

1. **A ready host from one command.** `devcloud vm up --label acc --project <owner/repo>` (a
   repository with a `devenv/`; the profile naming the desk's provisioning key, H4 — M6 says what
   stands in until the desk ships keys) exits 0 within 8 minutes and prints the name, the provider, the
   tailnet name, the lease end and the hourly price. Then: `devcloud vm ssh <n> -- devcloud status`
   prints every step `ok`; `devcloud vm ssh <n> -- 'cd ~/Developer/GitHub/<repo> && devenv validate'`
   exits 0; `sminos machines` lists `<n>` online, and nobody typed an enrollment code;
   `tailscale status` lists `<n>`. The user-data the provider keeps for the server, read back
   through its API, holds none of the person's secret values (the guard's known-value matcher,
   `devcloud/tests/scan-secrets.ts`, reports 0).
2. **No public door.** After `up` returns, a TCP connect to the VM's public IPv4 address on port 22
   fails (`nc -z -w 5 <ip> 22` exits non-zero), and `devcloud vm ssh <n> -- true` succeeds over the
   tailnet.
3. **Work on it, seen and steered from the desk.** `devcloud vm ssh <n> -- sminos spawn acc "reply ok
   and stop" --cwd ~/Developer/GitHub/<repo>` starts a seat; `sminos list --org` on the MacBook shows
   it on machine `<n>`; `session-mirror ls --host <n>` lists its session. From the desk, a prompt
   sent to a fresh session on `<n>` runs in it, and a permission request that session raises is
   answered from the desk and its tool call proceeds.
4. **Limits hold without the person, and give way with them.** With three unconfirmed throwaway VMs
   up, a fourth `devcloud vm up` exits 4 and its message names the cap and `--confirmed`;
   `devcloud vm up --ttl 100h --dry-run` exits 4 naming the lifetime cap;
   `devcloud vm up --type <a 16-vCPU type> --dry-run` exits 4 naming the size cap;
   `devcloud vm up --type <a type of at most 8 vCPU> --disk 500 --dry-run` exits 4 naming the disk
   cap; `--keep --dry-run` and `adopt --dry-run` without `--confirmed` exit 4. The fourth `up` with
   `--confirmed` creates the VM, labeled `devcloud-confirmed=1`, and `devcloud vm ls` still counts
   three of three throwaway VMs (then deleted).
5. **A lease ends cleanly.** In `<n>`'s project checkout an unpushed commit is made; then
   `devcloud vm lease <n> 35m`. Within 10 minutes the creating session receives a sminos message
   naming `<n>`, its lease end, and the repository with unpushed work. After the lease ends: within
   10 minutes `sminos machines` no longer counts `<n>` as enrolled and `tailscale status` no longer
   lists it; the session store holds the last line the VM's seat wrote before departure; within 25
   minutes of the lease end `devcloud vm ls` no longer lists `<n>` and the provider has no such
   server, deleted by the reaper's scheduled job on the always-on Mac (its log names the deletion).
6. **GCE, with no key on the machine.** `devcloud vm up --project <a repository whose
   devenv/host.toml selects the person's GCE account>` lands on GCE and meets checks 1–2; on it,
   `test ! -e /etc/devcloud/seed` holds (no key file was delivered) and `gcloud auth list` names the
   host service account the profile gives, not the person's key account. `devcloud vm down <n>`
   deletes it.
7. **Adopt a machine the driver did not make, and give it back.** A plain Ubuntu 24.04 server
   created by hand (no devcloud label) is adopted: `devcloud vm adopt <login user>@<ip> --label adp
   --ttl 2h --confirmed` meets check 1's status, desk and tailnet observations, and `devcloud vm ls`
   lists it as adopted. `devcloud vm down <n>` releases it: the server still runs; on it no path the
   credential ledger listed remains, nor the ledger, nor `hub.json`, nor a devcloud unit, nor the
   `inet devcloud` nftables table; the tailnet no longer lists it; `devcloud vm ls` no longer lists
   it. A new SSH connection to the original public address as the original login user succeeds, and
   again after the server reboots (a connection that survived the release does not count). Then it
   is deleted by hand.
8. **Projects choose; they cannot override the person.** A `devenv/host.toml` naming an account the
   profile does not have, or carrying an unknown key (`provider`, `command` and `executable` among
   them), makes `devcloud vm up --project` exit 2 before anything is created, naming the account or
   key. No `host.toml` field can name a machine to adopt, a credential, a provider or a command.
9. **Down protects unpushed work.** `devcloud vm down <n>` with an unpushed commit or uncommitted
   change in a checkout under the VM user's `~/Developer/GitHub` exits 5 naming the repository;
   `--force` proceeds.
10. **Images make it fast and stay few.** `devcloud vm image build` (each account whose provider has
    images) records an image labeled with the current recipe hash; the next `up` names that image and
    reaches every step `ok` within 5 minutes of `up` starting (the measured time recorded in
    Surprises); after a third build of the same account, `devcloud vm reap` leaves the newest two.
11. **The always-on Mac drives and reaps; hosts do not drive.** On the always-on Mac, a session's
    `devcloud vm up` and `devcloud vm down` work, the reaper's scheduled job is loaded (`launchctl
    list | grep devcloud-reap`), and its log shows runs every 10 minutes. On a devcloud VM,
    `devcloud vm ls` exits 6 with a one-line reason and calls no provider.
12. **Nothing personal in the public repository.** The branch's diff holds none of the profile's
    values (accounts, project ids, secret ids, the tailnet's name, host names), checked by grepping
    the diff for each value the profile lists.
13. **A cloud the driver does not ship, added once.** In a temporary profile (`DEVCLOUD_PROFILE`), an
    account whose provider is a profile provider under a name no shipped provider has (a copy of the
    shipped `hetzner` script, using the Hetzner account's credential) makes `devcloud vm up --account
    <it> --dry-run` exit 7 naming registration. `devcloud vm provider test <it>` passes and records the
    executable's sha256; `devcloud vm provider register <it> --confirmed` writes `registered = true`
    on the account; `devcloud vm up --account <it>` then creates a VM whose `devcloud status` prints
    every step `ok`, and `devcloud vm down <n>` deletes it. After a one-byte change to the script the
    account exits 7 again, and `provider test` passing once more makes it usable with no new
    registration.

## Design

### 1. Shape: one driver core, provider executables, the boot unchanged in kind

```
 Mac session                                 provider executable          the new host
 ───────────                                 ───────────────────          ────────────
 devcloud vm up ──► caps, name, lease ──► <provider> create {…}  ──────► cloud-init writes or
   │                                        (JSON on stdin; labels       stages the descriptor
   │                                         applied by the create)      (no secret)
   ├─ seed over SSH (providers without metadata_seed) ────────────────► /etc/devcloud/seed/
   └─ waits on `devcloud status` over SSH, then over the tailnet ◄──── devcloud-boot (parent
                                                                       steps 1–12, plus §4–§5,
                                                                       §10 below)
 devcloud vm reap (always-on Mac, every 10 min; and at the start of up/ls) ──► deletes what expired
```

Everything that is the same for every cloud lives in the driver core: naming, caps, the label set,
leases, the descriptor and user-data it composes, seed delivery, waiting for the boot, SSH access,
the down guard, adopt, the reaper's decisions, and the label recheck before every delete. A provider
only translates (I13): it reports its capabilities and a location's types, creates a server with its
labels, lists, gets, relabels and deletes labeled servers, and, where it can, makes, lists and
deletes images. The invariants stay in the core, where one implementation holds them for every
cloud; a provider never decides what to delete or when.

A provider is an executable the core calls once per operation, not a class inside the driver, so a
cloud the plugin does not ship can be added by writing one, in any language, in the person's
profile, with no change to the plugin (§6.2); the conformance test proves it translates faithfully
before the core relies on it. The in-process adapters this replaced lost because only a plugin
release could add a cloud, and a project that lives on a cloud the person uses would wait on one.
One script per provider owning its whole lifecycle, as M5's was, lost because the person wants
projects to pick providers (Decision Log, 2026-10-21) and because the lease, cap and cleanup rules
must be identical everywhere or a cheaper provider becomes the one that leaks.

The driver is Python (3.11+ standard library, as the parent's constraints require) calling the
provider executables, `ssh`, and `sminos`. The shipped providers are Python 3.11 scripts calling
each cloud's own CLI (`hcloud`, `gcloud`): the image and the Macs already have these, and their auth
handling is better tested than a hand-written API client.

### 2. Lifetimes and caps: who has to say yes

A session may create a **throwaway** VM (lifetime `ttl`) without asking anyone when the request is
within every cap; anything else needs the person's approval of that specific request, which the
session obtains first and then passes as `--confirmed`. The caps live in the profile (I10) with
these values the person chose:

| Cap | Value | Beyond it |
|---|---|---|
| Unconfirmed throwaway VMs alive at once, all accounts together | 3 | `--confirmed` |
| Lease at creation, and total lifetime through `lease` | default 12 h, at most 72 h | `--confirmed` (no upper bound) |
| Size | at most 8 vCPU | `--confirmed` |
| Disk | at most 200 GB | `--confirmed` |
| Lifetime `keep` | — | always `--confirmed` |
| `adopt` (sends a key to a machine the driver did not make) | — | always `--confirmed` |

`--confirmed` is not verified by the driver — it cannot see the person — so it is a contract with
the session, stated in the skill: ask through the ask tool with the specification and its cost,
and pass the flag only for what was approved. The alternative, requiring a terminal the person
types into, was rejected: sessions run without one, and the person approves from the desk or a
phone as often as from a terminal. The caps are the enforcement for everything a session does
alone; they bound the worst case to three 8-vCPU machines with 200 GB disks for 72 hours.

The disk a request asks for is `--disk`, else `host.toml`'s `disk_gb`, else the type's `disk_gb` as
the provider's `types` reports it; it is checked with the other caps, before anything is created.

A VM created with `--confirmed` carries `devcloud-confirmed=1` and does not count toward the
throwaway cap: it is an extra the person approved, and counting it would let the person's yes use up
a session's room. The count is checked before creation and again after it: two drivers (the two
Macs) racing past a count of 2 would otherwise make 4. After `create` returns, the driver lists
again; if unconfirmed throwaway VMs now exceed the cap and its own is the newest, it deletes its own
and exits 4. A driver killed between the create and the recount leaves the excess behind, so the
reaper, at each run, deletes the newest unconfirmed throwaway VMs above the cap — departing each
first, as `down` does, when it is reachable — until three remain (§4.3). Confirmed VMs are never
touched by this. Adopted machines and `keep` VMs do not count toward the throwaway cap.

### 3. `up`, step by step

1. **Resolve the request.** Flags, then the first `--project`'s `devenv/host.toml` (§9), then the
   profile's defaults (I10) give the account, type, location, disk, lifetime, lease and spot. The
   account's provider must be usable (§6.2), else exit 7. Check the caps, with the type's vCPUs and
   disk from the provider's `types` for the location; `--spot` on a provider without the `spot`
   capability exits 3. `--dry-run` stops here, printing the resolved request, the caps' verdict and
   the hourly price.
2. **Name it.** `dc-<label>-<4 hex>`: label `[a-z0-9-]{1,20}`, default `vm`. The driver rejects a
   name already used by a live server in any account, an adoption record, a tailnet node, or a desk
   machine (`sminos machines`, when the driver's machine is enrolled), and draws again.
3. **Compose the descriptor** (parent I5, from I10's `[host]`, plus I12): name, kind `vm`, role
   `persistent`, tailscale `join` with the Secret Manager id of the profile's Tailscale OAuth client,
   seed (`gce-metadata` when the provider has `metadata_seed`, else `file:`), the config repository,
   the projects, the lease, the creator (the creating session's sminos tag, from `sminos who
   --session $CLAUDE_CODE_SESSION_ID` when the driver runs in a session), `DEVCLOUD_INBOUND=tailnet`,
   `DEVCLOUD_SPOT=1` for a spot request, and the desk's provisioning key id when the profile has one.
   The descriptor carries ids, never values.
4. **Compose user-data**, when the provider has `user_data`: cloud-init that writes the authorized
   SSH keys (§8.3) and the descriptor. From an image it writes `/etc/devcloud/boot.env` directly.
   Without one (the slow path) it stages the descriptor at `/var/lib/devcloud-stage/boot.env`
   (0600), runs `setup.sh`, checks that it exited 0, and only then installs `/etc/devcloud/boot.env`:
   `setup.sh` fails while `boot.env` exists (its final check, "what the image never carries"), so a
   descriptor written first would fail every first boot without an image. It starts the boot only
   where no seed is delivered (`metadata_seed`). Nothing secret: a provider keeps user-data for the
   server's life, readable through its API and from inside the VM (parent's driver note). Without
   the `user_data` capability the driver creates the server with its SSH keys and does the same over
   SSH at the public address, through adopt's install path (§6.5).
5. **Create** through the provider's `create`, from the current image when the provider has `images`
   and one exists (§7), else from the provider's Ubuntu 24.04 by the slow path, which `up` names in
   its output. The labels (I14) — lifetime, lease, creator, driver machine, recipe hash, how it
   enrolls, and `devcloud-confirmed=1` for a confirmed request — go in the create call itself: a
   server labeled by a second call stays unlabeled if the driver dies between the two, invisible to
   the reaper and billing forever.
6. **Re-count** (§2).
7. **Deliver the seed**, unless the provider has `metadata_seed`: once cloud-init has finished (on
   the slow path, after `setup.sh` and the descriptor are in place — the seed's ledger entry creates
   `/var/lib/devcloud`, which `setup.sh`'s final check also refuses), its path appended to the
   credential ledger (§6.5), the seed key file streamed over SSH into a root-only path at the public
   address (M5's method: read from its file into `ssh`'s stdin, never argv, never printed); then
   start `devcloud-boot.service`.
8. **Wait** for the boot over SSH — over the public address until the tailnet attach step reports
   `ok`, then over the tailnet, since the boot closes the public port right after it (§5). Up to 15
   minutes; on a failed step print `devcloud status`'s lines and exit 1, leaving the VM for
   inspection (its lease still bounds it).
9. **Print** name, provider, account, location, type, tailnet name, lease end, hourly price, and the
   image used (or "built from base, slow path").

`up` exit codes are in I16. A failure before the server exists leaves nothing; after it, the VM
stays with its lease and labels, and `down` or the reaper removes it.

### 4. Leases and departure

**4.1 On the host.** The host's descriptor holds the authoritative lease; the `devcloud-expires`
label is a cached copy the reaper reads when the host does not answer. A lifecycle lock,
`/run/devcloud/lifecycle.lock` (`flock`), serializes every lease write (`devcloud lease set`), the
lease service, and `depart` and `release`, each of which re-reads `DEVCLOUD_EXPIRES` under it. Without
it an extension could land between the lease service's decision and its departure, and a host
would end its sessions with a lease that says it should live. `devcloud lease set` refuses once the
departure has started (status `departing`, `held` or `departed`): the sessions are already ended.

A descriptor with `DEVCLOUD_EXPIRES` makes the boot do three more things:

- **Join the tailnet as an ephemeral node** (`?ephemeral=true&preauthorized=true` on the OAuth
  client secret, the parameter's default per Tailscale's OAuth documentation): the coordination
  server removes an ephemeral node 30–60 minutes after it goes offline, and at once on `tailscale
  logout`, so a VM that dies without departing still leaves the tailnet (board #90). Without a lease
  the node is non-ephemeral, as the parent built it.
- **Run the lease service**, `devcloud-lease` (a timer every 5 minutes, in the parent's service list,
  I7): at 30 minutes before the lease end (or at once, when less remains when the lease is set) it
  sends one warning; at the lease end it runs the departure (the release, on an adopted machine);
  and at each later run it retries a held one.
- **Warn the creator**: `sminos say "@<creator>" "<name>'s lease ends at <time>; unpushed: <repos>"`
  as the user, where unpushed lists each git checkout under `~/Developer/GitHub` with commits not on
  its upstream or uncommitted changes. Without a creator, or unenrolled, the warning goes to the
  journal and `wall` only. One warning per lease value: extending re-arms it.

**4.2 The departure** (`devcloud depart`, root, under the lifecycle lock). It first re-reads
`DEVCLOUD_EXPIRES` and refuses with exit 3, "lease not over", unless the lease has ended or it was
given `--force` (which `down` passes): a reaper that decided on a stale label must not depart a host
whose lease was extended. Then, in this order, each step bounded so a broken one cannot keep a VM
alive:

1. **Stop admitting sessions and end the running ones**: stop the sminos daemon (no spawn, resume or
   delivery can start one after it), SIGTERM the user's `claude` processes, wait 30 seconds, SIGKILL
   what remains. The transcripts stop growing before the last ship, so the ship has the last line.
2. **Stop the continuous shipper and run `session-mirror ship --once`** as the user, bounded at
   5 minutes, while the network and the credentials are still intact.
3. `sminos hub leave` as the user (exit 0 or 1 both proceed; on 1 the desk's offline revoke removes
   the machine later, §4.4).
4. `tailscale logout`.
5. Stop devcloud's services.
6. Power off, unless `--no-poweroff` (the reaper's and `down`'s path, which delete right after).

If the ship fails, the departure stops there — no leave, no logout, no power-off — records `held
(ship failed)` and exits 4. The transcripts are the one thing a deleted VM must not lose, and a host
still on the tailnet and the desk can ship them once the cause clears. The lease service retries at
each run and the reaper at each of its runs (§4.3); a retry resumes at the ship. `--no-hold` (which
`down --force` passes) proceeds past a failed ship. The status file records `departing` when the
departure starts and `departed` with the time when it ends; `depart` is idempotent (a second run after
a completed one exits 0 doing nothing).

A GCE spot VM can be reclaimed by the provider with about 30 seconds' notice. Its descriptor carries
`DEVCLOUD_SPOT=1`, which the driver sets for a spot request, and the boot enables a shutdown unit
only then. The unit reads the metadata server's `instance/preempted`; when it is `TRUE` it runs steps
1–4 within 25 seconds, the session wait shortened to fit, and nothing holds. This is best-effort:
the provider does not guarantee the full window. An ordinary reboot runs none of this. The intent
comes from the descriptor because the driver knows it for certain; the metadata key
`instance/scheduling/provisioning-model` the first design read is not a documented one.

**4.3 The reaper** (`devcloud vm reap`, on a driver), for every usable account (§6.2):

- **Expired VMs**: every VM labeled devcloud whose label's lease ended more than 15 minutes ago.
  - Reachable over the tailnet within 10 seconds: `devcloud depart --no-poweroff` (6 minutes at most).
    Exit 0: delete. Exit 3, "lease not over": the label was stale (a lease write reached the host but
    not the label), so the reaper sets the label to the host's value and skips the VM. Exit 4, held:
    it labels the VM `devcloud-held=1` and leaves it, until 24 hours past its lease end; then it
    deletes it, with a `reap.log` line naming the unshipped loss.
  - Unreachable: `get` immediately before the delete, which proceeds only if `devcloud-expires` still
    equals the value the reaper decided on and that value is more than 15 minutes past (24 hours for a
    VM labeled `devcloud-held=1`). A lease extended between the reaper's `list` and its delete
    changed the label, so the delete does not happen.
- **Excess**: unconfirmed throwaway VMs above the cap, newest first, departed (`--force`) when
  reachable and deleted, until three remain (§2).
- **Leftovers**: builders (§7) and `provider test` servers (§6.2) older than 2 hours; images beyond
  the newest two per account.

It never touches a resource without the devcloud label, and before every delete it calls `get` and
refuses unless the label is still there (ci-kit's rule: the project holds other work's resources).
It never departs or deletes an adopted machine; the machine's own lease service releases it (§6.5).
It runs from a scheduled job on the person's always-on Mac every 10 minutes (`devcloud vm reap
--install` writes a launchd agent), and at the start of every `up` and `ls` on any driver, bounded to
60 seconds there. Each deletion is one line in `~/.local/state/devcloud/reap.log`; deleting a VM that
did not depart and was enrolled by a one-time code (`devcloud-enroll=code`) says that it stays in
the desk's Machines until someone removes it (§10).

**4.4 What covers what.**

| Event | Transcripts | Desk | Tailnet | Server |
|---|---|---|---|---|
| Lease ends, host healthy | sessions ended, then the departure ships; a failed ship holds the departure, retried | `hub leave` | `logout` | reaper deletes; a held VM 24 h past its lease end, logged as unshipped loss |
| Host hung or crashed, then lease ends | lost since the last ship (seconds, the shipper is continuous) | the desk's offline revoke after the key's 24 h (H4); a VM enrolled by a one-time code has none and stays until removed by hand, which the reaper's log names | ephemeral expiry, 30–60 min | reaper deletes on the label's lease |
| `devcloud vm down` | as a healthy lease end; held → `down` exits 1, `--force` proceeds | `hub leave` | `logout` | deleted at once |
| GCE spot reclaimed | best-effort fast departure, no hold | best-effort `hub leave`, else the offline revoke | best-effort `logout`, else ephemeral expiry | provider deletes |
| `keep` VM | never departs | stays; if stopped long enough for the offline revoke, re-enrolls at its next boot (`hub check` 3, `--replace`) | stays | only `down` |
| Adopted machine, lease ends or `down` | the release ships, as a departure | `hub leave` | `logout` | keeps running, devcloud removed (§6.5) |

### 5. Exposure: the public port closes once the tailnet is up

A VM holds the seed key (providers without `metadata_seed`, adopt), the GitHub token and the
tailnet's join; an open SSH port on a public address is the one inbound surface. With
`DEVCLOUD_INBOUND=tailnet` the boot, right after the tailnet attach step succeeds, installs an
nftables input policy and enables it at every later boot: inbound is dropped except loopback, the
`tailscale0` interface, established and related traffic, ICMP and ICMPv6 (IPv6 neighbor discovery
needs it), UDP 41641 (Tailscale's direct connections), and DHCP replies. Outbound is untouched. The
rule lives on the host so it is the same on every provider; a provider firewall would differ per
provider and would not cover `adopt`. If the tailnet is broken afterwards, the person reaches the
machine through the provider's console. The driver therefore talks to a VM over the tailnet after
step 4 of the boot (`root@<name>` or the user by MagicDNS) — which needs the tailnet's ACL to let the
Macs reach `tag:devcloud` on port 22 (M1 checks; H5 if not).

### 6. Providers

**6.1 The provider protocol.** A provider is an executable called as `<exe> <op>` with one JSON
object on stdin, answering one JSON value on stdout (the operations and shapes are I13). Exit 0 is
success. Exit 3 is the provider refusing — the project's limit, a quota, a type unavailable — with
`{"error": …, "kind": …}` on stdout, and the driver exits 3 with that line. Any other exit, or
stdout that does not parse, is a failure, and the driver exits 1. stderr is free text the driver
shows after scrubbing the account's credential values from it. `create` and the image operations
time out after 15 minutes, every other operation after 2; a `create` that timed out may still have
made a server, which carries its labels, so the reaper finds it.

An account's credentials are named in `driver.toml` as `env = { VAR = "<secret id>" }`. The driver
reads each value from Secret Manager on every call and places it only in the child's environment,
never in an argument list or a file; the account's non-secret settings (`vars`) go into the same
environment. A provider keeps no credential of its own.

`info` reports the provider's capabilities, and the core adapts to each one missing:

| Capability | With it | Without it |
|---|---|---|
| `user_data` | cloud-init writes the descriptor and keys (§3 step 4) | the server is created with the SSH keys, and the driver installs over SSH at its public address, by adopt's install path |
| `images` | `up` uses the current image (§7) | every `up` takes the slow path |
| `metadata_seed` | no seed is delivered (`DEVCLOUD_SEED=gce-metadata`) | the seed is delivered over SSH at first contact |
| `spot` | `--spot` creates a spot VM | `--spot` exits 3 |

The core keeps every invariant: the caps, the label set (I14, which every provider stores
verbatim), the lease, the reaper, and the label recheck, which calls `get` immediately before
`delete`, refuses unless the `devcloud` label is present, and fences on the lease (§4.3). The
provider only translates. Labels are applied inside `create`, never afterwards (§3 step 5).

**6.2 Profile providers and registration.** A profile provider is `<profile>/providers/<name>`
(I10's directory), executable, in any language, under a name no shipped provider has; one that
shadows a shipped name is refused with exit 2. Using one needs two things: a passing conformance
test of the exact executable, and the person's one registration.

`devcloud vm provider test <account>` runs the conformance sequence: `info`; `types` for the
account's default location; `create` the smallest available type, labeled `devcloud=test` and
`devcloud-test=<run id>`; `list` contains it; `get` returns its labels verbatim; `set-labels`
round-trips; the image operations round-trip when the provider has `images`; `delete`; then `get`
returns null and `list` lacks it within 10 minutes. A pass is recorded in
`~/.local/state/devcloud/providers/<account>.json` with the executable's sha256. `devcloud vm provider
register <account> --confirmed` is the person's one confirmation: it writes `registered = true` on
the account in `driver.toml`, and only while a current pass exists.

An account on a profile provider is usable only when it is registered and its executable's sha256
matches a passing test; otherwise every command that would call it exits 7. A changed script needs
the test again, not a new confirmation. Shipped providers need neither the test nor registration.
The test exists because the core's guarantees rest on the provider's translation — a provider that
drops a label or lists unlabeled servers makes the reaper blind or dangerous — and the confirmation
exists because a provider runs with the account's credential and spends the person's money, which a
session may not decide alone. Confirming every change was rejected: the script lives in the person's
own profile, and the test already proves each version behaves; no confirmation at all was rejected,
since a session could then write a provider and bill the person through it unasked.

**6.3 Hetzner Cloud** (the shipped `hetzner` provider). One account per Hetzner project; the
person's devcloud project holds nothing else of theirs. The script calls `hcloud` with `HCLOUD_TOKEN`
in its environment (the account's `env`), never a context file. Capabilities: `user_data`,
`images` (snapshots). The public IPv4 address is the first contact, for the seed. Shared-core types
differ by region (the US regions lack the newest series; prices there are about 1.75 times the EU's,
measured 2026-10-20), so `types` reports what `hcloud server-type describe` gives for the location
and the core never assumes a type exists. A create refused for the project's core limit
(`resource_limit_exceeded`) exits 3 with kind `limit`; the driver does not try another type on its
own.

**6.4 Google Compute Engine** (the shipped `gce` provider). Capabilities: `user_data`, `images`,
`spot`, `metadata_seed`. The seed is the VM's attached service account through the metadata server
(`DEVCLOUD_SEED=gce-metadata`, which the parent's boot already supports), so no key file reaches the
machine. That account is a dedicated host account the profile names (H2), granted Secret Manager
read on the project and nothing else: a GCE host's sessions then hold a narrower Google identity
than the Macs do. The profile may name the person's own account instead, keeping Mac-equivalence
without a key on disk; the narrow account is the default because it is what made GCE worth building
here. Instances are created with that account and the `cloud-platform` scope, an ephemeral external
IPv4 (outbound only, once §5 closes inbound), labels as given (I14's restriction makes every one a
valid GCE label), and user-data under the `user-data` metadata key, which Ubuntu's cloud-init reads;
the boot starts from cloud-init, since there is no seed to deliver. A spot request creates a spot VM
with termination action `DELETE`. Images are custom images in an image family. The script runs
`gcloud` under its own `CLOUDSDK_CONFIG` with the seed activated — the driver passes it the seed
key file's path in its environment — so the Mac's own gcloud identity is never changed.

**6.5 Adopt.** `devcloud vm adopt <user@address>` makes an existing Ubuntu 24.04 machine a host. It
is part of the core, not a provider: there is no cloud API to translate, and its target comes only
from the command line, never from a file a repository holds (§9).

Before delivering the seed, the driver writes the adoption record on the driver machine,
`~/.local/state/devcloud/adopted/<name>.json`: the target address, the login user, the name, the
lease, and the phase (`preparing`, `seeded`, `booted`, `released`). Re-running `adopt` for the same
target resumes from the recorded phase, and `ls` shows the records alongside the tailnet nodes, an
incomplete adoption with its phase. This is the one piece of lifecycle state the driver keeps
locally: an adopted machine has no provider label to carry it.

Adopt checks the OS; records the machine's state before changing it, copying root's and the login
user's `authorized_keys` to `/var/lib/devcloud/adopt/`; streams the plugin's `devcloud/` to the
machine and runs `setup.sh` (which renames the machine to the `dc-` name and creates the user);
delivers the seed; writes the descriptor with `DEVCLOUD_ADOPTED=1`; and starts the boot. Lifetime
defaults to `keep`; `--ttl` gives it a lease. `devcloud vm lease` on an adopted machine writes
`DEVCLOUD_EXPIRES` on the host only (under its lock; there are no labels) and updates the record;
at the lease end the host's lease service runs the release. `devcloud vm down <name>` runs the
release over the tailnet when the machine is reachable, else over the recorded public address; the
record is removed once the release is verified, over the public address as the original login user.

The release (`devcloud release`, root, under the lifecycle lock), in order:

1. End the sessions and ship, as the departure's steps 1–2 (§4.2), holding on a failed ship.
2. `sminos hub leave`.
3. Delete the `inet devcloud` nftables table and remove `devcloud-inbound.service`.
4. Restore the saved `authorized_keys`.
5. `tailscale logout`.
6. Stop devcloud's services and remove its units.
7. Remove every credential the ledger lists, then the ledger.

Access comes back before the tailnet goes: from step 4 on, the original login user can reach the
machine over its public address again, so a release that fails afterwards still leaves the person a
way in. Firewall rules devcloud did not create are left untouched. The tools, the user and the home's
other files stay, and the machine keeps running.

**The credential ledger.** On every host, each path where devcloud writes a credential is appended
to `/var/lib/devcloud/credentials.ledger` (root, 0600) and fsynced before the write: the seed, root's
gcloud store `/var/lib/devcloud/gcloud` (which `devcloud/boot/devcloudlib/secretmanager.py`
activates), the user's gcloud and gh configuration, the secret store, each `secrets.toml` target,
the managed settings, `/etc/devcloud/env`, the boot descriptor, and sminos's `hub.json`. Reconcile
never prunes it. Release removes every entry it lists and removes the ledger itself only after every
removal has succeeded. Release reading the current profile, as first designed, would miss a target
the profile renamed or dropped after the boot wrote it; the ledger records what was written,
whenever it was.

### 7. Images

`devcloud vm image build [--account A]`, for an account whose provider has `images`, creates a
builder through `create` (label `devcloud=builder`, the smallest type whose disk is the provider's
minimum, so the image fits every type), runs `setup.sh` from the plugin's own `devcloud/` over SSH,
checks the builder structurally — no `/etc/devcloud/boot.env`, an empty seed directory, none of the
credential files the guard knows (parent check 6(b)), no `$SMINOS_HOME/daemon/` — cleans cloud-init's
state and the machine id so each VM gets its own, powers it off, records the image through
`image-create` with labels `devcloud=image` and the recipe hash, and deletes the builder. The builder
never receives a seed, a descriptor, or any secret, which is why the bake does not need the parent's
known-value scan; that scan stays where it runs today, on the container image in the `devcloud`
gate. `up` uses the newest image of its account whose recipe hash is current; with none it takes the
slow path and the reaper, at its next run on the always-on Mac, builds one for each such account
that lacks a current image (at most once a day per account). Whether a Hetzner snapshot made in one
location creates servers in another is M1's question; if not, images are per location.

### 8. Where the driver runs, and with what

**8.1 Configuration**: the profile's `devcloud/` directory, `~/.claude/devcloud/` (`DEVCLOUD_PROFILE`
overrides it, for tests and for trying a provider in a temporary profile): `driver.toml` (I10) and
`providers/`, synced to every Mac like the rest of `~/.claude`; personal values live only there.

**8.2 Credentials**: the seed key file — `$DEVCLOUD_SEED_FILE`, else `~/.config/devcloud/seed.json`
(0600; on the MacBook a link to the existing key, on the always-on Mac a copy made for the driver
alone, H3, leaving that Mac's own gcloud account untouched). From the seed the driver takes an access
token and reads each account's credentials from Secret Manager, per call (§6.1). Without a seed the
driver refuses every command with exit 6.

**8.3 SSH**: each driver Mac has its own key, `~/.local/state/devcloud/ssh/id_ed25519`, made on
first use. Its public half is written to the profile's `driver-keys/<machine>.pub`, which the Macs'
configuration sync commits like any profile change; user-data authorizes every key in that directory
for root at first boot, and the boot's home step keeps root's and the user's `authorized_keys` equal
to it afterwards. So a VM one Mac made is reachable from the other, and the always-on Mac's reaper
reaches every VM. A host never pushes its configuration, so a key it generated could not reach this
directory, which is why hosts do not drive. Host keys are recorded on first contact (`accept-new`
into the driver's own `known_hosts`), as M5 did; providers expose no host key before first boot.

**8.4 Entry point**: the plugin's `bin/devcloud` (a plugin's `bin/` is on a session's `PATH`, as
ci-kit's `ci-gate` is) runs the plugin's `boot/devcloud` with a Python 3.11+ found on `PATH` — the
Macs' `/usr/bin/python3` is 3.9. `boot/devcloud` gains `vm`; its host commands keep their root-only
behavior and, on a machine with no `/etc/devcloud`, say so. On a devcloud host, where
`/etc/devcloud/boot.env` exists, `vm` refuses with exit 6 and one line (`devcloud vm: this machine is
a devcloud host; drive from a Mac`). `boot/devcloud` now resets `PATH` to the system directories for
its root jobs; `vm` must keep the caller's (`hcloud` and `gcloud` live under Homebrew and the user's
SDK on the Macs, and a profile provider may need its own tools).

### 9. Projects choose their host, inside the person's choices

A repository may commit `devenv/host.toml` (I11): an account name, a type, a location, a disk size,
spot. `up --project` reads it from the local checkout when the session's working tree is that
repository (so it can be iterated), else from GitHub at the requested ref (`gh api`). It may only
choose among the accounts the profile registers, and it is checked like flags: caps apply, and an
unknown key or an unknown account fails `up` with exit 2 before anything is created. It names an
account by name only — never a provider, an executable, a command, a credential or an address. The
account resolves, in the person's profile, to a provider the person shipped or registered; a public
repository that could name an executable would make the driver run that code with the person's
credentials, and one that could name a host would make it send the person's key there. With several
`--project`s, the first one's file governs; the others' are reported and ignored.

### 10. The desk: unattended enrollment, leaving, and control

Interfaces I15 pin the desk's provisioning-key interface (the desk's spec, MAWS
`docs/doperpowers/specs/2026-10-21-desk-provisioning-keys-design.md`, its "What the boot consumes"
section, as of its commit 5168e433). Boot step 11, on a role-`persistent` host whose descriptor names
`DEVCLOUD_SMINOS_SECRET`, asks the desk whether this machine's credential is accepted, as the user
in a login shell: `sminos hub check`. Its answer decides:

| `hub check` | Meaning | Step 11 does |
|---|---|---|
| 0 | accepted | nothing more (a reboot or reconcile of an enrolled host) |
| 1 | not enrolled here | fetch the key into memory; `sminos hub enroll --name <DEVCLOUD_NAME>`, the key on stdin |
| 3 | a credential is present but rejected (an admin revoke, the offline sweep, a `leave` whose answer was lost) | the same, with `--replace` (a new use of the key) |
| 4 | undecided: the desk is unreachable, answered 5xx or neither, or an Access 401 for a credential still inside the propagation grace (600 s from `hub.json`'s enrollment time) | the step is not done: keep the credential, let the daemon start, record `deferred` (which the boot's exit counts as ok), and ask again later (below). Never enroll on 4 |
| 2 | usage | fail the step |

A host whose descriptor names no `DEVCLOUD_SMINOS_SECRET` and which has no code file (below) enrolls
nothing in step 11, as the parent's unenrolled host does.

A deferred step is finished by the `devcloud-enroll` service (an I7 addition: root, every 5 minutes, on a
host whose descriptor names `DEVCLOUD_SMINOS_SECRET`), which runs `devcloud enroll`: nothing unless
the status says `deferred`, otherwise the same `hub check` and this table's action for 0, 1 or 3. The
interval is fixed and unbounded: one request every 5 minutes costs nothing, and a host that a revoke
while stopped plus a brief desk outage left unenrolled until its next reboot — the daemon never holds
the key, so it cannot re-enroll on its own — is the failure this exists to prevent. `devcloud status`
shows `enroll deferred since <time>`.

Then the daemon is installed as the parent built it. `sminos hub show` reads only the local file and
is not used for this decision. An enroll exiting 3 (name taken) or with a key refusal fails the step
with the desk's one-line reason; `mint-failed`, `busy` and no answer are retried within the step,
three times, 10 seconds apart. Nothing of the key is written to disk. The VM can still read the key
again through its seed — the desk records that broader trust as accepted (its §7); keeping the key
off disk keeps it out of images, snapshots and backups, and recovery is revoking the key and then the
machines it minted, which the desk lists by key.

The provisioning key used for leased VMs has a finite offline revoke, 24 hours (H4): the desk
revokes a machine offline that long, so a VM that died without leaving is gone from the desk a day
later, and a stopped `keep` VM it revoked re-enrolls at its next boot through `hub check` 3 and
`--replace`. M6 verifies the key's policy value; the sweep itself is the desk's to prove.

Until the desk ships keys, `up --enroll-code -` reads a one-time code from its stdin; once the boot
has finished (unenrolled), the driver writes the code over SSH to a root-only file,
`/etc/devcloud/enroll-code`, and runs `devcloud reconcile`, whose step 11 enrolls with it the same
way and deletes the file once a 0, 1 or 3 has decided, whatever the enroll's outcome (a deferred step
keeps it for `devcloud enroll`; `up` then reports the deferral and exits 0) — one path for every
provider, GCE included, where nothing is delivered before the tailnet is up. A VM enrolled by a
one-time code has no offline revoke: if it dies without leaving, it stays in the desk's Machines until
someone removes it, and the reaper's log line for its deletion says so (§4.3). Sandboxes never enroll
(the parent's rule).

**Desk control.** The desk watches and steers a session through the sminos bridge in it, and the
bridge turns itself off, withdrawing the permission requests it raised
(`sminos/hooks/mods/bridge.tsx`, `turnOff`), whenever the secrets guard is not beneath it in the hook
order: what it streams to the desk must already be scrubbed. A host's managed settings set
`prependPlugins: []` (`devcloud/boot/devcloudlib/profile.py`, `host_settings`), which loads every
plugin in the user tier, the bridge inside the guard — so on a host today the bridge is off and the
desk can neither steer a session nor answer its requests. The parent deferred seating the plugins as
the Macs do (its Decision Log entry ending "Revisit when a host must enroll or that release lands",
option E there); enrollment makes it due. M1 finds whether a host session's bridge runs on the
current engine and whether the engine release that gives remote-source plugins the prepend tier has
landed; M2 implements the plugin ordering that puts the bridge outside the guard while keeping the
guard active from a host's first session — E, or what M1 finds. If no ordering achieves both, the
work stops BLOCKED for the person: a bridge outside no guard would stream secret values to the desk,
and a first session without the guard would write them to its transcript.

### 11. The skill

`devcloud/skills/vm/SKILL.md` (`devcloud:vm`) tells a session: when a VM is the right tool (work too
heavy or long for the Macs, a loaded Mac, isolation, Linux or Docker needs) and when it is not (a
quick command, anything needing the Macs' GUI); the commands; the caps and the `--confirmed`
contract (ask first through the ask tool, with the type, lifetime and price, and pass the flag only
for what was approved); how to put work on a VM (a seat through `sminos spawn` over `vm ssh`, results
coming back as pushes, pull requests and sminos messages); that a VM is deleted at its lease end with
whatever was not pushed; to `down` what it made when the work is done; and how to write a provider
for a project's cloud — the protocol (I13), running `provider test` until it passes, and that
registration and the account's credential in Secret Manager are the person's steps. It is written
with doperpowers:writing-skills and sanity-tested in a session before it ships.

## Out of scope

- Shipped providers beyond Hetzner Cloud and GCE (Vultr, AWS, Firecracker hosts); the provider
  protocol is their extension point, and a session can write one as a profile provider (§6.2).
- Hosts as drivers: it needs a path for registering a host's public key in the profile, which a host
  never pushes to.
- Sandbox containers created by the driver on a host (the parent's sandbox role); `adopt` and VMs
  only. Sandboxes never enroll at the desk, which is where this initiative's value lies.
- A budget in money: the caps bound time, count, size and disk; the provider's billing is the record.
- Removing kept tailnet nodes or desk machines from outside the machine: the Tailscale OAuth client
  has only the auth-keys scope, and the desk offers no browserless admin revoke; ephemeral nodes and
  the desk's offline revoke cover throwaway machines.
- Workload identity federation for Hetzner hosts (a keyless seed off GCE), deferred by the parent.

## Execution

### Constraints that bind every milestone

- The parent's constraints hold (public repository, no personal values in it; Python 3.11+ standard
  library only plus the CLIs the image installs; never print a secret value; idempotent steps;
  Ubuntu 24.04; same-day deletion of test resources, recorded in Progress; devcloud's own version
  bumped through `scripts/bump-version.sh --plugin devcloud` in the commit that changes the plugin;
  every new test suite becomes or joins a ci-kit gate, and the ci-kit session is told when gates
  change).
- Every provider resource the driver creates carries the label `devcloud=<kind>` (I14), applied in
  the create call itself; no code path deletes or modifies a resource without it, and each deletion
  re-reads the label first (`get`).
- The driver gives a provider its credentials only in the child's environment, never in an argument
  list or a file; the shipped providers keep their CLIs' configuration private, never the person's
  default CLI configuration.
- Live tests that create VMs use the person's devcloud Hetzner project and GCE project (from the
  profile); a test run's VMs are labeled `devcloud-test=<run id>` as well, and the run deletes them
  before it ends, on success or failure.
- The desk's interface (I15) is owned by the desk; a change there reaches this work through the
  desk session (sminos `smns-erb-71`, the desk orchestrator). Code against I15 as written; when the
  desk's final shapes differ, the desk session says so and the Decision Log records it.
- The live checks that enroll at the desk need the sminos release that carries I15; today's installed
  CLI has only `hub enroll` and `hub show`, so `hub check` exits 2. Before any such check the executor
  verifies that the installed sminos accepts `hub check` and records its version. Until the desk
  ships that release, the desk parts of those checks are reported "blocked on the desk", never
  passed, and everything else proceeds: a VM whose descriptor has no `DEVCLOUD_SMINOS_SECRET` and no
  code file skips step 11's enrollment. The one-time-code path (`--enroll-code -`) stands in for the
  provisioning key only, not for the CLI.
- `devcloud/hooks/mods/secrets*.tsx` is not touched by this work (cua vendors it).

### Plan of Work

### M1 — Spike: the preflight, and the live facts the design leans on

A prototyping milestone: its deliverable is knowledge, recorded in Surprises & Discoveries with the
verdicts below applied, and the design revised (with Decision Log lines) where a fact contradicts it.
Use M5's provisioner (the untracked copy under `.doperpowers/sde/2026-10-20-devcloud-vm-driver/`) or
hand commands; delete everything the same day.

It opens with a **preflight** that lists which credentials and accounts are present, by id and
existence, never by value: the Hetzner devcloud project's API token in Secret Manager (H1), and the
GCE host service account with its grant (H2). The executor creates the GCE host account itself when
the person's key account is permitted (`gcloud iam service-accounts create` in the GCE account's
project, one `roles/secretmanager.secretAccessor` binding on the Secret Manager project,
`DEVCLOUD_SM_PROJECT`, and the driver's key account allowed to attach it). Whatever is missing is
escalated as H1 or H2 at once, with the exact commands, and the questions that do not need it
proceed meanwhile. The preflight also records whether the installed sminos accepts `hub check`, and
its version (Constraints).

Questions, each with what decides it:
1. **SSH over the tailnet to `tag:devcloud`.** Boot one Hetzner VM with the parent's boot; from the
   MacBook and the always-on Mac, `ssh root@<name>` over MagicDNS. Works → §5 as written. Blocked by
   the ACL → H5 (the person adds the rule), and §5 waits on it.
2. **Ephemeral join with the OAuth client.** On that VM, a second `tailscale up` as ephemeral (after
   logout) succeeds with `?ephemeral=true&preauthorized=true` and `tag:devcloud`; `tailscale logout`
   removes the node at once. Fails → the lease keeps non-ephemeral joins and §4.4's crash row
   becomes a manual removal (Decision Log).
3. **nftables policy on a Hetzner VM.** Applying §5's policy keeps the tailnet connected (direct and
   relayed), IPv6 working, and SSH over the tailnet working, across a reboot; the public port is
   closed. A rule that breaks any of these is fixed here.
4. **Hetzner images.** A snapshot of a builder on the smallest type in the US-west location creates a
   server of the default type there, and in an EU location. Records: builder type, image size, time
   from `create` to every boot step `ok` from the image (the parent's slow path measured too).
   Cross-location fails → images per location (§7).
5. **Hetzner core limit** of the devcloud project: create three default-type VMs at once (the cap);
   record whether a fourth would fit, from the error or the project's limits page (H-step if only
   the console shows it). Below the cap's worst case (3 × 8 vCPU) → the cap's size default or count
   is lowered in the profile, recorded.
6. **GCE.** In the person's GCE project: an Ubuntu 24.04 instance with the host service account
   attached and `user-data` metadata runs cloud-init's `write_files` and `runcmd`; the parent's boot
   with `DEVCLOUD_SEED=gce-metadata` reaches every step `ok` (Secret Manager read through the
   attached account); spot creation works in the chosen zone. Anything else → the GCE provider's
   design is revised before M5.
7. **A host session's bridge.** On a host booted with the parent's boot and today's managed settings,
   start a session as the user and read whether its sminos bridge runs or turns off (its toast and
   debug line naming `prependPlugins`, the bridge socket answering or not). Check whether the engine
   release that gives remote-source plugins the prepend tier has landed. The verdict names the
   ordering M2 implements: the parent's option E, the prepend tier the release gives, or none that
   keeps the guard active from the first session (then BLOCKED for the person, §10).

Promote or discard: no code is promoted; the scripts stay untracked. Done when every question has a
recorded verdict, the preflight's escalations are out, and every resource is deleted.

### M2 — The host side: leases and their lock, departure, release and its ledger, the closed public port, unattended enrollment, desk control

What exists at its end: a host booted with the new descriptor keys (I12) joins ephemeral when leased,
runs `devcloud-lease`, warns its creator, departs at its lease end, holding on a failed ship;
`devcloud depart`, `devcloud release` and `devcloud lease set <unix>` exist on hosts and serialize on
the lifecycle lock; every credential devcloud writes is in the ledger first;
`DEVCLOUD_INBOUND=tailnet` closes the public port after the tailnet attach; step 11 enrolls with a
provisioning key (or a one-time code file) without a person; root's and the user's `authorized_keys`
follow the profile's `driver-keys/`; a spot host (`DEVCLOUD_SPOT=1`) departs fast when reclaimed;
`devcloud-boot.service` waits for cloud-init where cloud-init runs; a host session's bridge runs
outside the guard with the guard active from the first session.

Touches: `devcloud/boot/devcloudlib/descriptor.py` (I12 keys, validated as the parent validates
its own: unknown keys refused; `DEVCLOUD_EXPIRES` an integer, which the boot accepts even when it
lies in the past — a VM rebooted after its lease must still boot and then depart; only the driver
refuses a lease end in the past),
`steps.py` (tailnet attach's attributes by lease; the inbound policy after it; home's
`authorized_keys`; the ledger entry before each credential write), `secretmanager.py` and every other
module that writes a credential (the ledger), `sminos_host.py` (enrollment), `services.py` (the lease
and enroll services in the list), `profile.py` (`host_settings` and the plugin seating, §10), a new
`devcloudlib/lease.py` (the lock, warning, departure, release, the unpushed scan) and
`devcloudlib/ledger.py`, `boot/devcloud` (the host commands), `image/setup.sh` (nftables installed,
the boot unit's ordering after cloud-init, the spot shutdown unit shipped disabled), tests under
`devcloud/tests/unit/` and `devcloud/tests/integration.py`.

Interfaces: produces I12, the host commands of I16, and consumes I15 (sminos's `hub check`, `hub
enroll`, `hub leave`, `say`).

Decisions:
- `DEVCLOUD_TS_SECRET`'s attributes become `?ephemeral=<true when leased>&preauthorized=true`.
  Already joined → unchanged (an existing node keeps what it was).
- The lease service is a `devcloud-<name>` periodic service like the parent's jobs (every 300 s), so
  containers (which never carry a lease; refuse `DEVCLOUD_EXPIRES` with role `sandbox`) need nothing.
- The lifecycle lock, the lease's authority and `lease set`'s refusal are §4.1; departure's order,
  bounds, lease check and hold are §4.2; release's order and the ledger are §6.5. Each step's outcome
  is a status entry. `depart` and `release` are idempotent, and a retry of a held one resumes at the
  ship.
- `release` refuses on a host without `DEVCLOUD_ADOPTED=1`, never deletes the user or the home's other
  files, and deletes only the nftables table devcloud owns.
- The enrollment follows §10's `hub check` table and I15. The provisioning key is fetched only when
  `hub check` says 1 or 3, kept in memory, and handed to the child's stdin. The one-time code file
  (`/etc/devcloud/enroll-code`, 0600 root), when present, is used in place of the key, and deleted
  once a 0, 1 or 3 has decided, whatever the enroll's outcome. Neither present → step 11 enrolls
  nothing. On 4 the step records `deferred` and the boot goes on; `devcloud enroll` (a new entry in
  `devcloud`'s jobs) and the `devcloud-enroll` service (every 5 minutes, in the service list) finish it
  as §10 says.
- The inbound policy is one nftables table devcloud owns (`inet devcloud`), loaded by a
  `devcloud-inbound.service` ordered before the network comes up at later boots; the step is a no-op
  on containers and when the key is absent or `open`.
- The spot shutdown unit is enabled by the boot only when `DEVCLOUD_SPOT=1`, and checks
  `instance/preempted` (§4.2).
- The plugin ordering on hosts is the one M1's question 7 names; a host's first session already runs
  under the guard. No ordering that achieves both → BLOCKED to the person (§10).
- The fakes in `devcloud/tests/fixtures/` grow a fake `tailscale` that records `up`'s auth-key file
  attributes and `logout`, a fake `session-mirror` whose ship can be made to fail, and the fake
  `sminos` (`fixtures/sminos.py`) learns `hub check`'s exits, `hub enroll` (with `--replace`) reading
  stdin with I15's exits, `hub leave`, `say`, and the daemon's stop.

Does not touch: the driver (`devcloud/driver/`), any provider, the guard mods.

Proves (tests pin each): a leased descriptor joins ephemeral and an unleased one does not; the warning
fires once per lease value and names dirty and unpushed checkouts; departure order and bounds — the
daemon stopped and the user's `claude` processes ended before the ship, and a hung step does not stop
the next; a failed ship holds (no leave, no logout, no power-off, status `held (ship failed)`, exit 4)
and a later run resumes at the ship; `depart` without `--force` refuses with exit 3 while the lease
is not over; the lease service racing a lease write (the lock serializes them, and the departure
reads the value the write left); `lease set` refused once the departure started; the ledger: release
after a `secrets.toml` target was renamed or removed still removes the old target, the root gcloud
store `/var/lib/devcloud/gcloud` is gone, and the ledger is removed only after every removal
succeeded; release's order, the saved `authorized_keys` restored and only the `inet devcloud` table
removed; release leaves the user and non-devcloud files; the `hub check` table (0 skip, 1 enroll, 3
enroll with `--replace`, 4 defer: no enroll, the daemon still starts, and `devcloud enroll` acts on a
later 1 or 3 and does nothing after a 0; 2 fail) and the enroll exit table (0, 1 with each retryable
and fatal reason, 2, 3); no secret and no code file → no enrollment; the key never reaches a file or
argv (assert over the fake's recorded argv and the filesystem); the nftables ruleset text (a unit test
on the generator; the live check is M1's and M6's); the spot unit enabled only with `DEVCLOUD_SPOT=1`;
a reboot past the lease boots and departs; in a container session as the parent probed it, the
bridge stays on and the guard's marker is live from the first session.

### M3 — The driver core, the provider protocol and the Hetzner provider, with the reaper

What exists at its end: from a Mac session, `devcloud vm up | ls | ssh | lease | down | reap |
provider test | provider register` (and `--dry-run`, `reap --install`) work against Hetzner through
the shipped `hetzner` provider. A partial live smoke (one or two VMs, deleted the same day) meets
acceptance 1 (its desk parts as Constraints say), 2 and 9 and the dry-run parts of 4, and `provider
test` passes on the Hetzner account. The profile has `driver.toml` and `driver-keys/`. The full cap
proof and acceptance 5 are M6's.

Touches: a new `devcloud/driver/` package (the core: caps, naming, descriptor and user-data
composition, the protocol client, SSH, the reaper, `provider test` and `register`), the shipped
provider `devcloud/driver/providers/hetzner` (an executable Python 3.11 script), `devcloud/bin/devcloud`,
`devcloud/boot/devcloud` (the `vm` dispatch, the refusal on a host, and the `PATH` pitfall of §8.4),
unit tests under `devcloud/tests/unit/` with a fake provider executable in `devcloud/tests/fixtures/`
(its servers, images and labels in a JSON file; its capabilities set per test; able to refuse, fail,
hang and print garbage), the `hetzner` script's own tests against a fake `hcloud` in the same
directory (`server create|delete|describe|list|add-label`, `server-type describe`, `image
list|delete`, `ssh-key list`), `devcloud/README.md` (the driver section), the person's profile in the
config repository (`driver.toml`, `driver-keys/` — committed there, not here).

Interfaces: produces I10, I13, I14, I16 (the `vm` commands); consumes I12 and the host commands from M2.

Decisions:
- One process per command, no daemon. Lifecycle state lives at the providers (labels), on the hosts
  (the authoritative lease) and in the profile; the local files are the SSH key, `known_hosts`, the
  reap log, the provider test records, the gce provider's private gcloud configuration (M5), and the
  adoption records (M5), the one piece of lifecycle state kept locally.
- `ls` merges every usable account's labeled VMs, the adoption records and the tailnet's
  `tag:devcloud` nodes; columns: name, provider/account, lifetime, lease end (relative), state (with
  `held` from `devcloud-held=1`), hourly price, creator, and `adopted` for adopted rows; the
  throwaway count against the cap heads it.
- `ssh` uses the tailnet name and the user by default (`--root` for root); it passes a command
  through quoted as given.
- `down` runs the down guard (acceptance 9) over SSH, then `depart --force --no-poweroff` (with
  `--no-hold` when given `--force`), then deletes after the `get` recheck; a held departure → exit 1
  naming the hold and `--force`; unreachable → asks for `--force`, which skips straight to deletion.
- `lease <name> <duration>` sets the lease end to now + duration (shorter is always allowed; longer is
  checked against the lifetime cap from the VM's creation time). It writes the host first, over the
  tailnet (`devcloud lease set` under the host's lock), then the label (`set-labels`). A host that
  refuses (departure started) or does not answer → exit 1, label untouched.
- The reaper's decisions are a pure function of (resources with labels, the hosts' answers, now) →
  actions, table-tested; the side effects are a thin layer over the protocol client.
- The protocol client owns I13's exit mapping, timeouts, environment and stderr scrub; nothing else in
  the core runs a provider.
- `devcloud-by` is the driver machine's name, lowercased; a label value outside I14's set is a bug
  the core refuses before calling a provider.

Does not touch: images (M4 — `up` takes only the slow path here), the gce provider and adopt (M5),
the skill (M6).

Proves: the cap table of §2 (each cap, the `--confirmed` bypass, a confirmed VM not counted, an
otherwise-valid low-vCPU request with too large a disk refused with exit 4 before any create); the
post-create recount deleting its own VM when racing; a driver killed right after create leaves 4
unconfirmed throwaway VMs and the next reaper run brings them back to 3, confirmed ones untouched;
names never collide with the fake's servers or tailnet nodes; user-data holds no value from the fake
seed or the fake Secret Manager (scan it); a first creation with no image stages the descriptor, runs
`setup.sh`, checks its exit, and only then installs `boot.env` (the order pinned), and the seed waits
for cloud-init's end; the labels are in the `create` request, not a later call; the reaper's
decision table (expired past grace, expired within grace, reachable and departed → delete, reachable
and "lease not over" → label repaired and skipped, reachable and held → `devcloud-held=1` and kept
until 24 h past the lease end, then deleted with the loss line, unreachable with the decided value
still in the label → delete, unlabeled, builders, test servers, image retention, excess); lease
fencing — a crash between the descriptor write and the label write leaves a stale label that the
reaper repairs without deleting, and an extension interleaving with a reaper run that had already
listed the VM stops its delete; the protocol client (exit 3 with each kind → driver exit 3, another
exit or unparsable stdout → 1, each timeout, credential values in the child's environment only and
scrubbed from the stderr shown); the conformance test passes on the fake and fails on a fake that
alters a label, lists an unlabeled server, or still lists a deleted one; `provider register` refused
without a current pass; exit 7 for an unregistered profile provider and for one whose sha256 changed,
and usable again after `provider test` with no new registration; a profile provider under a shipped
name refused; `--spot` on a provider without `spot` → exit 3; `vm` refused on a host; exit codes
(I16).

### M4 — Images and project host files

What exists at its end: `devcloud vm image build` makes a current image for a Hetzner account, `up`
uses it (acceptance 10 live, with the measured time), the reaper builds missing images and prunes
old ones; `devenv/host.toml` steers `up` (acceptance 8), read locally or through `gh api`; the
`devenv` skill mentions `host.toml` as optional.

Touches: `devcloud/driver/` (image build over the protocol, recipe hash, host-file reading), the
`hetzner` provider's image operations, `devcloud/skills/devenv/SKILL.md` (one paragraph: what
`host.toml` is for and that it only chooses among the person's accounts, checked with
doperpowers:writing-skills), tests.

Interfaces: consumes I13's image operations (defined in M3, implemented here for Hetzner); produces
I11.

Decisions:
- Recipe hash: SHA-256 over the sorted paths and bytes of `devcloud/image/` and `devcloud/boot/`, 12
  hex characters.
- A builder that fails labels itself `devcloud-bake=failed-<step>`, and the build deletes it before
  exiting non-zero; the reaper deletes any builder older than 2 hours regardless.
- The daily build in the reaper is skipped while a builder of the same account exists.

Does not touch: the gce provider and adopt (M5).

Proves: the recipe hash changes when any file under those two directories changes and not
otherwise; `up` picks the newest current image and falls back to the slow path otherwise, and a
provider without `images` always takes the slow path; the structural check fails the bake on each
forbidden file; `host.toml` validation (each key, unknown key — `provider`, `command`, `executable`
among them — unknown account, caps applied) and precedence (flags over the file over the profile).

### M5 — The GCE provider, adopt, and the open provider path

What exists at its end: `up` on a GCE account (acceptance 6 live, including spot creation and a
deletion) and `adopt` (acceptance 7 live) work; GCE images build; adopted machines appear in `ls`
from their records, lease on the host alone, and release on `down` or at their lease end; a profile
provider can be tested, registered and used (acceptance 13 live).

Touches: the shipped provider `devcloud/driver/providers/gce` (an executable Python 3.11 script with
its private `CLOUDSDK_CONFIG`), `devcloud/driver/` (adopt, the adoption records, release over the
tailnet or the public address), tests with a fake `gcloud` for the gce script (instances
create/delete/list/describe/add-labels, images create/list/delete, and the metadata it was given),
adopt's contract tests, the profile's GCE account, H7.

Interfaces: implements I13 once more; consumes M2's `release`, the ledger and the spot unit.

Decisions:
- `adopt` refuses a machine that is not Ubuntu 24.04, one that already has `/etc/devcloud/boot.env`
  (an existing host: use `ls`), and an address given without `--confirmed`.
- An adopted machine's lifetime defaults to `keep`; it does not count toward the throwaway cap.
- Adopt's contract tests drive an adoption and a later lease through the same core the live run uses,
  against a fake SSH target: each phase recorded before the step it names, a resume from each phase,
  `lease` writing the host and the record and no label, `down` releasing over the tailnet and, with
  the tailnet down, over the recorded address.
- The open-path proof (acceptance 13) uses a temporary profile (`DEVCLOUD_PROFILE`) holding a copy of
  the `hetzner` script under a name no shipped provider has, and an account on it with the Hetzner
  account's credential; registration is the person's confirmation, H7.

Does not touch: Hetzner beyond shared core fixes, the skill.

Proves: the gce script's command line for a `create` request (service account, scope, labels as
given, spot flags, user-data from a file) and that no seed delivery is attempted; the gce provider
passes the conformance test against the fake `gcloud` and live on the GCE account; adopt's refusals;
the adoption record's phases, resume, and its removal only after a verified release; `ls` showing an
incomplete adoption with its phase; the reaper never departing or deleting an adopted machine; live:
acceptance 6, 7 (a new SSH connection as the original login user after the release, and again after
a reboot) and 13.

### M6 — The skill, the always-on Mac, and acceptance

What exists at its end: `devcloud:vm` ships; the always-on Mac drives and reaps (H3, `reap
--install` there); acceptance 1–13 pass as written (their desk parts as Constraints say), including
the full cap proof and acceptance 5's deletion by the scheduled reaper; the desk's provisioning key
has a 24 h offline revoke; the parent's leftover `devcloud-m5` is gone from the desk; the devcloud
plugin's version is bumped; the README and the parent spec point here.

Touches: `devcloud/skills/vm/SKILL.md`, `devcloud/README.md`, `devcloud/.claude-plugin/plugin.json`
(description), the parent spec's Decision Log (one line naming this spec as its driver), the
always-on Mac's setup (outside the repository).

Decisions:
- The skill is drafted with doperpowers:writing-skills and sanity-tested in a real session that,
  given a heavy task and a loaded Mac, creates a VM within caps, puts the work on it, and downs it;
  given a request beyond a cap, asks before passing `--confirmed`; and, given a project on a cloud
  no provider covers, writes a provider that passes `provider test` and asks the person to register
  it.
- The full cap proof (three unconfirmed VMs plus a confirmed fourth) reuses acceptance 1's and 6's
  VMs where they are alive at the time.
- The provisioning-key path of acceptance 1 needs H4; if the desk has not shipped keys by then,
  acceptance 1 runs with `--enroll-code -` (the person pastes a one-time code) and the key path's
  live check is recorded as pending in Progress, with M2's tests standing for it.
- H4's key policy: read the key's `offline_revoke_s` from the desk and record that it is 86400.
- H6: the person removes `devcloud-m5` from the desk's Machines; `sminos machines` no longer listing
  it is the evidence, recorded in Progress.

Proves: acceptance 1–13, with the full `devcloud` gate green.

### Concrete Steps

Working directory: the `devcloud-vm` worktree.

    bash devcloud/tests/run.sh                         # unit + container integration (the devcloud gate)
    python3 -m unittest discover -s devcloud/tests/unit -p 'test_*.py'   # unit only, while iterating
    ci-gate --gates devcloud,repo-checks,shell-lint     # the committed HEAD on CI

Live (from a MacBook session; the profile's accounts):

    devcloud vm provider test <hetzner account>
    # info ok · types ok · create ok · list ok · get ok · set-labels ok · images ok · delete ok · gone ok
    # pass recorded (sha256 …)
    devcloud vm up --label acc --project <owner/repo> --dry-run
    # account   hetzner-…  location …  type …  disk … GB  lifetime ttl 12h  price €…/h
    # caps      throwaway 0/3 ok, lease 12h/72h ok, size 4/8 vCPU ok, disk …/200 GB ok
    devcloud vm up --label acc --project <owner/repo>
    # dc-acc-7f3a  hetzner  … ready in 4m12s  tailnet dc-acc-7f3a  lease ends 2026-…  image dc-img-…
    devcloud vm ssh dc-acc-7f3a -- devcloud status
    devcloud vm ls
    devcloud vm lease dc-acc-7f3a 35m
    devcloud vm down dc-acc-7f3a

Expected failure shapes (I16): a cap → exit 4, `devcloud vm: over the throwaway cap (3 alive,
cap 3): ask the person, then pass --confirmed`; the disk cap → exit 4, `devcloud vm: 500 GB is over
the disk cap (200 GB): ask the person, then pass --confirmed`; the down guard → exit 5,
`devcloud vm: <name> has unpushed work in <repo>: push it, or pass --force`; a profile provider not
usable → exit 7, `devcloud vm: provider <name> of account <account> is not registered (run
devcloud vm provider test <account>, then the person registers it)`.

### Interfaces and Dependencies

**I10 — `driver.toml`** (profile, `~/.claude/devcloud/driver.toml`, or under `$DEVCLOUD_PROFILE`;
private):

    [caps]
    throwaway = 3            # unconfirmed throwaway VMs alive at once, all accounts
    lease_default = "12h"
    lease_max = "72h"        # lifetime from creation, through `lease` too
    vcpu_max = 8
    max_disk_gb = 200

    [defaults]
    account = "<account name>"

    [host]                                   # the parent's descriptor fields every VM gets (I5)
    sm_project = "<GCP project id>"          # DEVCLOUD_SM_PROJECT
    config_repo = "<https clone URL>"        # DEVCLOUD_CONFIG_REPO
    config_branch = "main"                   # DEVCLOUD_CONFIG_BRANCH
    config_token_secret = "<Secret Manager id>"   # DEVCLOUD_CONFIG_TOKEN_SECRET
    tailscale_secret = "<Secret Manager id>"      # DEVCLOUD_TS_SECRET (the OAuth client)

    [desk]
    provisioning_secret = "<Secret Manager id>"   # optional until the desk ships keys; its key's offline_revoke_s is 24 h (H4)

    [[account]]
    name = "<name>"
    provider = "hetzner"                     # a shipped provider, or a file name under providers/
    location = "<location>"
    type = "<server type>"
    env = { HCLOUD_TOKEN = "<Secret Manager id of the project's API token>" }

    [[account]]
    name = "<name>"
    provider = "gce"
    location = "<zone>"
    type = "<machine type>"
    vars = { GCE_PROJECT = "<GCP project id>", GCE_SERVICE_ACCOUNT = "<the host account's email>",
             GCE_IMAGE_FAMILY = "devcloud" }

    [[account]]
    name = "<name>"
    provider = "<a profile provider's file name>"
    location = "<location>"
    type = "<type>"
    env = { "<VAR>" = "<Secret Manager id>" }
    vars = { "<VAR>" = "<value>" }
    registered = true                        # written only by `devcloud vm provider register --confirmed`

`env` maps an environment variable to the Secret Manager id of its value, read on every call (§6.1);
`vars` holds the account's non-secret settings, passed in the same environment. The driver adds
`DEVCLOUD_SEED_FILE`, the seed key file's path, to the shipped `gce` provider's environment only.
M5 of the parent composed the `[host]` fields by hand from the person's gcloud configuration and
config repository; `[host]` makes them the profile's. Unknown keys are refused. Profile providers live
beside this file, in `providers/<name>`.

**I11 — `devenv/host.toml`** (a repository's, committed; every key optional):

    account = "<an account name from the person's driver.toml>"
    type = "<provider type>"
    location = "<location or zone>"
    disk_gb = <integer>
    spot = true | false          # accounts whose provider has the spot capability

**I12 — Boot descriptor additions** (to the parent's I5):

    DEVCLOUD_EXPIRES=<Unix seconds>        # the lease, authoritative; absent = keep. Rewritten by `devcloud lease set`
    DEVCLOUD_CREATOR=<sminos tag>          # optional; who gets the lease warning, e.g. @alias#short
    DEVCLOUD_INBOUND=tailnet|open          # default open
    DEVCLOUD_ADOPTED=1                     # optional; lease end runs release; down runs release
    DEVCLOUD_SMINOS_SECRET=<Secret Manager id>   # optional; the desk provisioning key
    DEVCLOUD_SPOT=1                        # optional, set by the driver for a spot VM; enables the shutdown unit

**I13 — The provider protocol** (shipped providers in `devcloud/driver/providers/<name>`, profile
providers in `<profile>/providers/<name>`):

    <exe> <op>      stdin: one JSON object        stdout: one JSON value
    exit 0          ok
    exit 3          refused; stdout {"error": "<one line>", "kind": "limit"|"quota"|"unavailable"|"other"}; the driver exits 3
    any other exit, or stdout that does not parse: failure; the driver exits 1
    stderr          free text, shown with the account's credential values scrubbed
    timeouts        create, image-create, images, image-delete: 15 min; every other op: 2 min
    environment     the account's env (values from Secret Manager, per call) and vars; nothing on argv but <op>

    required
    info        {}                                   → {"protocol": 1, "capabilities": [...]}   # subset of user_data, images, spot, metadata_seed
    types       {"location"}                         → [{"type", "vcpus", "memory_gb", "disk_gb", "available", "hourly_price": number|null}]
    create      {"name", "type", "location", "image": id|null, "labels", "ssh_public_keys",
                 "user_data": string|null, "disk_gb", "spot"}   → Vm     # labels applied inside the create itself
    list        {}                                   → [Vm]             # only resources carrying the devcloud label
    get         {"id"}                               → Vm | null
    set-labels  {"id", "labels"}                     → Vm               # the full label set
    delete      {"id"}                               → {}

    with the images capability
    image-create {"id", "name", "labels"}            → Image            # from the server `id`
    images       {}                                  → [Image]          # only images carrying the devcloud label
    image-delete {"id"}                              → {}

    Vm    = {"id", "name", "location", "type", "labels", "public_ipv4": string|null, "state", "created"}
    Image = {"id", "name", "labels", "created"}
    # created: Unix seconds; state: the provider's word for it, shown by ls

The core's side of the contract — the invariants, the label recheck, the capability fallbacks — is
§6.1; the conformance test and registration are §6.2.

**I14 — Labels** (keys and values `[a-z0-9-]`, at most 63 characters, stored verbatim by every
provider):

    devcloud=vm|image|builder|test
    devcloud-lifetime=ttl|keep
    devcloud-expires=<Unix seconds>          # a cached copy of the host's lease (§4.1)
    devcloud-by=<driver machine's name, lowercased>
    devcloud-creator=<session short id>
    devcloud-recipe=<12 hex>
    devcloud-confirmed=1                     # created with --confirmed; not counted toward the throwaway cap
    devcloud-enroll=key|code                 # how the VM enrolls at the desk; absent: it does not
    devcloud-held=1                          # its departure is held on a failed ship (§4.3)
    devcloud-bake=failed-<step>              # a builder whose bake failed (M4)
    devcloud-test=<run id>                   # live test runs and provider test

**I15 — The desk's interface consumed** (desk spec "What the boot consumes", after its review,
commit 5168e433 on its branch, 2026-10-21):

- `sminos hub check`: writes nothing; a dead hub gives up at about 30 s, but an Access 401 on a
  credential past the grace is asked once more 90 s later before it answers 3, so one call can take
  about 150 s — every timeout devcloud wraps around it (step 11, `devcloud enroll`) allows 180 s. 0 the
  credential is accepted; 1 not enrolled here; 3 a credential is present but rejected; 4 undecided —
  the desk is unreachable, answered 5xx, or neither, or Access answered 401 for a credential still
  inside its propagation grace (600 s from `hub.json`'s enrollment time; a newly minted token can be
  refused until it reaches Access's edge), which answers 4 at once; 2 usage. (§10's table says what
  the boot does with each.)
- `sminos hub show`: local only, 0 or 1 on the file alone; not used for the enroll decision.
- `sminos hub enroll --name <name> [--replace]`, the code on stdin (`smns-provision-v1.…` keys,
  `smns-enroll-v1.…` one-time codes, both piped whole and never decoded): 0 enrolled; 3 name taken;
  1 refused or no answer, with one `sminos: …` stderr line (`key-revoked`, `key-expired`,
  `key-exhausted` need the person; `mint-failed`, `busy`, no answer retry the same line), and also
  enrolling while already enrolled without `--replace`; 2 invocation error, including a name outside
  the key's prefix (`dc-`).
- `sminos hub leave`: 0 not enrolled any more — it left, or the desk or its access layer already
  refuses the credential — and `hub.json` removed; 1 unreachable, 5xx, an Access 401 inside the propagation grace, or another
  error, `hub.json` kept (the desk's offline sweep revokes it); 2 usage.
- Per key, the desk revokes a machine offline longer than the key's `offline_revoke_s` (never, or
  1 h to 30 d). The key for leased VMs uses 24 h (H4). A machine enrolled by a one-time code has no
  offline revoke.
- Version floor: the sminos release that ships `hub check` and the provisioning keys; an older one
  exits 2 on `hub check` and on a provisioning key. The desk has not yet sent the version number; it
  is recorded here when it does.

**I16 — Command surface and exit codes:**

    devcloud vm up [--label L] [--project owner/repo[@ref]]... [--account A] [--type T] [--location L]
                   [--disk GB] [--ttl D | --keep] [--spot] [--enroll-code -] [--confirmed] [--dry-run]
    devcloud vm adopt <user@address> [--label L] [--project …]... [--ttl D] [--confirmed] [--dry-run]
    devcloud vm ls [--json]
    devcloud vm ssh <name> [--root] [-- command...]
    devcloud vm lease <name> <duration> [--confirmed]
    devcloud vm down <name> [--force]
    devcloud vm image build [--account A] | image ls
    devcloud vm reap [--install]
    devcloud vm provider test <account> | provider register <account> --confirmed

    0 ok · 1 failed (the step named) · 2 usage or invalid input (flags, host.toml, driver.toml)
    3 the provider refused (its kind and line shown), or a capability the request needs is missing
    4 over a cap: needs --confirmed · 5 down guard: unpushed work
    6 not a driver here: no seed key, or this machine is a devcloud host
    7 the account's provider is not usable: not registered, or no passing test of its current executable

    devcloud depart [--force] [--no-hold] [--no-poweroff] | release [--no-hold] | lease set <unix>
                                                                        # on a host, root, under the lifecycle lock
    depart, release: 0 done (or already done) · 1 failed · 2 usage · 3 lease not over (depart without --force) · 4 held (ship failed)
    lease set:       0 set · 1 failed · 2 usage · 3 the departure has started

## Surprises & Discoveries

- Observation: The gateway Mac and the MacBook are both closest to Hetzner's US-west location.
  Evidence: ping from the gateway Mac: hil 80 ms, ash 125, nbg1 180, sin 211; from the MacBook:
  hil 44, ash 96, nbg1 264 (2026-10-20).
- Observation: Hetzner's US regions price shared-core types at about 1.75 times the EU, and lack
  the newest series; dedicated-core types cost the same everywhere.
  Evidence: `hcloud server-type describe` (2026-10-20): cpx31 €0.1178/h in hil vs cpx32 €0.0673/h
  in nbg1 (cpx32 not offered in the US); ccx23 €0.165 hil vs €0.1626 nbg1.
- Observation: Hetzner projects carry a shared-core limit below 20 vCPU in the person's other
  project (ci-kit's pool documents `403 resource_limit_exceeded` at 20); the devcloud project's own
  limit is unmeasured (M1 question 5).
- Observation: A plugin's `bin/` is on a session's `PATH` (ci-kit's, cua's and ptc's are in it),
  and the Macs' `/usr/bin/python3` is 3.9.
  Evidence: `echo $PATH` in a session; `/usr/bin/python3 --version` → 3.9.6.
- Observation: Tailscale removes an ephemeral node 30–60 minutes after its last activity and at
  once on `tailscale logout`; an OAuth client secret used as an auth key defaults to ephemeral.
  Evidence: tailscale.com/kb/1111/ephemeral-nodes, tailscale.com/kb/1215/oauth-clients.
- Observation: The person's GCE project allows external IPs, has Compute Engine and Secret Manager
  enabled and billing on, and enforces `iam.disableServiceAccountKeyCreation` (so a GCE host's
  account can only be attached, never given a key — which is the point).
  Evidence: `gcloud services list --enabled`, `gcloud resource-manager org-policies describe …
  --effective` (2026-10-21).
- Observation: `setup.sh` fails at its end when `/etc/devcloud/boot.env` or `/var/lib/devcloud`
  exists, so nothing may write either before it runs on a fresh machine.
  Evidence: `devcloud/image/setup.sh`, the loop under "What the image never carries" (2026-10-21).
- Observation: The installed sminos CLI has only `hub enroll` and `hub show`; `hub check` exits 2.
  Evidence: the independent reviews of this spec (2026-10-21).

## Decision Log

- Decision: Verification. One independent spec review by the `doperpowers:adversarial-reviewer`
  agent (a technical spec) plus its buildability review of this six-milestone execution section, in
  the same round. Whole-branch review at the **high** rung of doperpowers:review-code: the driver
  moves a service-account key, opens and closes public ports, and spends money on its own.
  Rationale: execspec's default for a multi-milestone spec; the rung follows the stakes.
  Date/Author: 2026-10-21, design session.
- Decision: Provider-agnostic from the first version, with Hetzner, GCE and adopt adapters and a
  per-project `devenv/host.toml`, instead of the Hetzner-only driver first proposed.
  Rationale: the person asked that each project be able to use the provider it prefers, or a server
  it set up itself; GCE also brings a keyless host identity. Rejected: Hetzner only with the
  interface left untested, which would leave the abstraction unproven.
  Date/Author: 2026-10-21, the person, through the design session.
- Decision: The parent's role `persistent` is narrowed to "a systemd host with its own machine
  identity", which may carry a lease; lifetime (`ttl`/`keep`) is a separate axis.
  Rationale: a throwaway VM needs systemd, the desk and the tailnet like a long-lived one; only its
  end differs. Rejected: a third role, which would fork every role check in the boot for one bit.
  Date/Author: 2026-10-21, design session.
- Decision: `hub check` exit 4 means undecided (unreachable, 5xx, or an Access 401 inside the
  propagation grace); step 11 defers on it and the `devcloud-enroll` service asks again every 5
  minutes, unbounded, until 0, 1 or 3. Rationale: the desk's last review (smns-erb-71's message,
  2026-10-21) found that a VM revoked while stopped and booted during a brief outage would otherwise
  stay unenrolled until its next reboot. Rejected: retrying inside the boot step, which delays every
  boot by the outage and still gives up at a bound; exponential backoff, which buys nothing at one
  request per try. Date/Author: 2026-10-21, design session.
- Decision: The provider boundary is an executable protocol (I13, §6.1), replacing the
  in-process `Provider` class and the Python adapters. Shipped providers `hetzner` and `gce` are
  Python 3.11 scripts; a profile provider is usable once its conformance test passes and the person
  registers it once (§6.2); `host.toml` names an account only; adopt stays in the core.
  Rationale: a cloud the plugin does not ship can be added without a plugin release, while every
  invariant (caps, labels, lease, reaper, recheck) stays in one core implementation; the test makes
  the core's trust in a provider earned, and the one confirmation keeps a session from billing the
  person through code it wrote. Rejected: in-process adapters (only a plugin change adds a cloud);
  a confirmation on every script change (the profile is the person's and the test proves each
  version); no confirmation (a session could spend the person's money through its own provider).
  Date/Author: 2026-10-21, the person, through the design session.
- Decision: The desk's sminos release carrying I15 is an external readiness dependency
  (Constraints): the executor verifies `hub check` is accepted before any enrolling check and records
  the version; until then the desk parts are "blocked on the desk", and everything else proceeds.
  Rationale: today's CLI exits 2 on `hub check`, so an enrolling check would fail for a reason outside
  this work, or pass on a stand-in that proves nothing about it. Rejected: treating `--enroll-code -`
  as a stand-in for the CLI, which it is not — it replaces only the key.
  Date/Author: 2026-10-21, design session.
- Decision: A credential ledger on every host (§6.5): each credential path appended and fsynced
  before its write, never pruned by reconcile, consumed by release, removed last.
  Rationale: release must remove what was written, and the profile it would otherwise read can have
  renamed or dropped a target since. Rejected: release reading the same profile as the boot.
  Date/Author: 2026-10-21, design session.
- Decision: Release restores access before leaving the tailnet (§6.5): adopt saves root's and
  the login user's `authorized_keys` first; release removes devcloud's nftables table and inbound
  service, restores the keys, and only then logs out. Rationale: the first order logged out with the
  public port still closed and root's keys replaced by the driver keys, leaving the person no way back
  into their own machine. Rejected: flushing all firewall rules (devcloud must not touch rules it did
  not create); counting a surviving connection as proof (it says nothing about new ones).
  Date/Author: 2026-10-21, design session.
- Decision: Adopt's contract (§6.5): the target from the command line only, an adoption record
  written before the seed with a phase that `adopt` resumes from and `ls` shows, `down` releasing over
  the tailnet or the recorded public address, the lease on the host alone, the reaper never touching
  an adopted machine. Rationale: an adopted machine has no provider label to carry its state, and an
  adoption interrupted after the seed would otherwise be invisible. This is the one piece of local
  lifecycle state the driver keeps. Rejected: finding adopted machines from tailnet nodes alone,
  which loses the address and every adoption that never reached the tailnet.
  Date/Author: 2026-10-21, design session.
- Decision: M1 opens with a preflight that lists the credentials and accounts and escalates H1
  and H2 at once; M3's live run is a partial smoke; the full cap proof and acceptance 5 (needing H3)
  move to M6; H6 gets an M6 step; every human step has an owner and a milestone (Progress).
  Rationale: a missing credential found mid-milestone stalls it, and acceptance 5 needs the
  always-on Mac, which only M6 sets up. Rejected: discovering each credential when first used.
  Date/Author: 2026-10-21, design session.
- Decision: The lease is fenced (§4.1, §4.3): the descriptor is authoritative and the label a
  cache; a lifecycle lock serializes lease writes, the lease service and departure; `vm lease`
  writes the host first, then the label; `depart` refuses "lease not over" without `--force`; the
  reaper departs reachable hosts and repairs stale labels, and deletes unreachable ones only if the
  label still holds the value it decided on. Rationale: with two copies of the lease and no fence, an
  extension racing the reaper or the lease service could delete a VM its session had just kept.
  Rejected: the label as the authority (the host, which ends its own sessions, could not trust it).
  Date/Author: 2026-10-21, design session.
- Decision: Departure ends the sessions before the final ship and holds on a failed ship
  (§4.2): the daemon stopped and `claude` processes ended first; the ship while the network and
  credentials are intact; no leave, logout or power-off after a failed ship; the reaper keeps a held
  VM until 24 h past its lease end, then deletes it, logging the loss; `down --force` skips the hold;
  the spot departure is best-effort. Rationale: shipping while sessions still write loses their last
  lines, and leaving after a failed ship strands the transcripts on a machine about to be deleted.
  Rejected: shipping first and ending sessions after (the first order).
  Date/Author: 2026-10-21, design session.
- Decision: The slow path stages the descriptor at `/var/lib/devcloud-stage/boot.env`, runs
  `setup.sh`, checks its exit, and only then installs `/etc/devcloud/boot.env` (§3 step 4); the image
  path writes it directly. Rationale: `setup.sh` fails while `boot.env` exists, so the first design's
  user-data broke every image-less first boot. Rejected: making `setup.sh` tolerate a descriptor,
  which weakens the check that keeps one out of images.
  Date/Author: 2026-10-21, design session.
- Decision: Desk control on enrolled hosts (§10): M1 asks whether a host session's bridge runs
  and whether the engine release giving remote-source plugins the prepend tier has landed; M2 seats
  the bridge outside the guard with the guard active from the first session (the parent's option E,
  or what M1 finds), or stops BLOCKED for the person; acceptance 3 steers a session and answers a
  permission request from the desk. Rationale: the parent's managed `prependPlugins: []` puts the
  bridge inside the guard, so it turns itself off and an enrolled host could be seen in the desk but
  not controlled; the parent deferred E until a host must enroll, which is now. Rejected: accepting a
  desk that watches but cannot steer hosts.
  Date/Author: 2026-10-21, design session.
- Decision: The throwaway cap counts unconfirmed VMs only (`devcloud-confirmed=1` marks the
  rest), and the reaper deletes the newest unconfirmed throwaway VMs above the cap (§2, §4.3).
  Rationale: a confirmed VM is an extra the person approved, not a session's room; and a driver
  killed between create and recount left an excess nothing removed. Rejected: counting confirmed VMs
  (the person's yes would block sessions' work); relying on the recount alone.
  Date/Author: 2026-10-21, design session.
- Decision: A disk cap, `[caps] max_disk_gb = 200`, enforced before create; beyond it needs
  `--confirmed`, else exit 4. Rationale: the caps bounded time, count and vCPU but not disk, which a
  low-vCPU request could make large and costly. Rejected: leaving disk to the provider's billing.
  Date/Author: 2026-10-21, design session.
- Decision: Drivers are the Macs (Terms, §8.3, §8.4): a driver's profile is a configuration
  checkout that pushes, so its SSH key reaches the profile; on a host (`/etc/devcloud/boot.env`
  exists) `devcloud vm` refuses. Rationale: a host never pushes configuration, so a key it generated
  could never be authorized on the machines it made. Rejected: hosts as drivers, out of scope until a
  host's key can be registered in the profile.
  Date/Author: 2026-10-21, design session.
- Decision: Spot intent comes from the descriptor: the driver sets `DEVCLOUD_SPOT=1` (I12), the
  boot enables the shutdown unit only then, and the unit checks `instance/preempted` (§4.2).
  Rationale: `instance/scheduling/provisioning-model`, which the first design read, is not a
  documented metadata key; the driver knows the intent for certain. Rejected: detecting spot from
  metadata.
  Date/Author: 2026-10-21, design session.
- Decision: Desk cleanup is finite: the provisioning key for leased VMs has `offline_revoke_s`
  24 h (H4), which M6 verifies; a VM enrolled by a one-time code has no offline revoke and stays in
  the desk's Machines until removed by hand, which the reaper's log line names (§4.4, §10).
  Rationale: with "never" a crashed VM would stay counted at the desk forever; 24 h is long enough
  for a stopped `keep` VM to come back, and one revoked re-enrolls at its next boot. Rejected: relying
  on `hub leave` alone, which a crash skips.
  Date/Author: 2026-10-21, design session.

## Outcomes & Retrospective

Pending — written at finish.
