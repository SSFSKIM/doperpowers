# devcloud VM driver — a session gets its own cloud machine, and it cleans up after itself

**Date.** 2026-10-21. **Status.** Design approved in conversation (2026-10-20/21); independent
review pending. **Parent.** `docs/doperpowers/specs/2026-10-15-devcloud-design.md` (the host image
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
    # its transcript lands in the session store; twelve hours later the VM leaves the desk and the
    # tailnet, ships its last transcript lines, and is deleted

The machine comes from whichever provider the project prefers (`devenv/host.toml`) or the person's
default: Hetzner Cloud and Google Compute Engine are built here, and any Ubuntu server the person
already runs can be adopted instead. A throwaway machine that a session creates needs nobody; a
machine meant to stay, a bigger one, or more of them than the limit needs the person's yes.

How to see it working: from a session on a Mac, `devcloud vm up --project <a repo with devenv/>`
prints a name; `devcloud vm ssh <name> -- devcloud status` shows every boot step `ok`;
`sminos machines` lists the machine online without anyone having typed an enrollment code;
`devcloud vm lease <name> 35m` makes the creating session receive a warning, and some minutes after
the lease ends `devcloud vm ls` no longer lists the machine, the tailnet no longer shows it, and the
desk no longer counts it.

## Progress

- [x] (2026-10-21) Design approved; spec written.
- [ ] Independent review (spec + buildability).
- [ ] M1 — Spike: the live facts the design leans on.
- [ ] M2 — The host side: leases, departure, release, the closed public port, unattended enrollment.
- [ ] M3 — The driver and the Hetzner adapter, with the reaper.
- [ ] M4 — Images and project host files.
- [ ] M5 — The GCE and adopt adapters.
- [ ] M6 — The skill, the always-on Mac, and acceptance.
- [ ] Whole-branch review (high rung), Outcomes & Retrospective, PR.

Human steps this initiative needs (each prepared by the executor, run by the person when an
automated attempt is refused or needs a browser): H1 the Hetzner token of the devcloud project into
Secret Manager; H2 the GCE host service account and its grant; H3 the seed key file onto the
always-on Mac; H4 a desk provisioning key into Secret Manager (once the desk ships it); H5 a
tailnet ACL rule, only if M1 finds SSH to `tag:devcloud` blocked; H6 removing the parent's leftover
test machine from the desk.

## Terms

The parent's terms hold (host, substrate, role, boot descriptor, profile, seed credential, gateway,
session store). New here:

- **Driver**: `devcloud vm`, the command that creates, lists, reaches, leases and deletes hosts. It
  runs on a machine that holds a seed key file: the person's Macs, and hosts whose seed is a file.
- **Provider adapter**: the part of the driver that speaks to one provider (Hetzner Cloud, Google
  Compute Engine) or, for `adopt`, to a machine the driver did not create. Everything else in the
  driver is the same for all of them (Design §1).
- **Account**: one provider login the person registered in the profile's `driver.toml` (Interfaces
  I10): a provider, its credentials' Secret Manager id or project, and its defaults. A project
  chooses among accounts; it never supplies one.
- **Lifetime**: `ttl` — the host has a lease and departs when it ends — or `keep` — no lease. This
  is independent of the parent's role: every VM the driver makes has role `persistent` (systemd, its
  own machine identity), whatever its lifetime. The parent's definition of `persistent` ("long-lived")
  is narrowed accordingly (Decision Log).
- **Lease**: a host's expiry, a Unix time in its descriptor (`DEVCLOUD_EXPIRES`) and in its provider
  labels.
- **Departure**: what a host with an ended lease does to itself: ship its last transcript lines,
  leave the desk, log out of the tailnet, power off (Design §4).
- **Release**: the departure of an adopted machine, which also removes every credential devcloud put
  there and keeps the machine running (Design §6.3).
- **Reaper**: `devcloud vm reap`, which deletes what outlived its lease, its purpose or its
  retention (Design §4.3).
- **Image**: a provider-side disk image with the parent's `image/setup.sh` already applied, so a VM
  starts in minutes rather than installing everything (Design §7).
- **Recipe hash**: a short digest of `devcloud/image/` and `devcloud/boot/` at the plugin version in
  use; an image is current when its recorded hash equals the driver's.
- **Confirmed request**: `--confirmed` on a `devcloud vm` command. It says the person approved this
  specific request; the driver requires it for anything beyond the caps, for `keep`, and for `adopt`
  (Design §2).
- **Provisioning key**: a desk credential, reusable and revocable, that lets a machine enroll at the
  desk without a person (Design §10). The desk builds it; this work consumes it.

## Acceptance

Run from a session on the MacBook unless a check names the always-on Mac. `<n>` is the name `up`
prints. Every VM created is deleted the same day and its deletion recorded in Progress.

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
3. **Work on it, seen from the desk.** `devcloud vm ssh <n> -- sminos spawn acc "reply ok and stop"
   --cwd ~/Developer/GitHub/<repo>` starts a seat; `sminos list --org` on the MacBook shows it on
   machine `<n>`; `session-mirror ls --host <n>` lists its session.
4. **Limits hold without the person, and give way with them.** With three throwaway VMs up, a
   fourth `devcloud vm up` exits 4 and its message names the cap and `--confirmed`;
   `devcloud vm up --ttl 100h --dry-run` exits 4 naming the lifetime cap;
   `devcloud vm up --type <a 16-vCPU type> --dry-run` exits 4 naming the size cap; `--keep --dry-run`
   and `adopt --dry-run` without `--confirmed` exit 4. The fourth `up` with `--confirmed` creates
   the VM (then deleted).
5. **A lease ends cleanly.** In `<n>`'s project checkout an unpushed commit is made; then
   `devcloud vm lease <n> 35m`. Within 10 minutes the creating session receives a sminos message
   naming `<n>`, its lease end, and the repository with unpushed work. After the lease ends: within
   10 minutes `sminos machines` no longer counts `<n>` as enrolled and `tailscale status` no longer
   lists it; the session store holds the last line the VM's seat wrote before departure; within 25
   minutes of the lease end `devcloud vm ls` no longer lists `<n>` and the provider has no such
   server, deleted by the reaper on the always-on Mac (its log names the deletion).
6. **GCE, with no key on the machine.** `devcloud vm up --project <a repository whose
   devenv/host.toml selects the person's GCE account>` lands on GCE and meets checks 1–2; on it,
   `test ! -e /etc/devcloud/seed` holds (no key file was delivered) and `gcloud auth list` names the
   host service account the profile gives, not the person's key account. `devcloud vm down <n>`
   deletes it.
7. **Adopt a machine the driver did not make.** A plain Ubuntu 24.04 server created by hand (no
   devcloud label) is adopted: `devcloud vm adopt root@<ip> --label adp --ttl 2h --confirmed` meets
   check 1's status, desk and tailnet observations. `devcloud vm down <n>` releases it: the server
   still runs; on it no seed, no materialized secret, no `hub.json`, no devcloud unit remains; the
   tailnet no longer lists it; then it is deleted by hand.
8. **Projects choose; they cannot override the person.** A `devenv/host.toml` naming an account the
   profile does not have, or carrying an unknown key, makes `devcloud vm up --project` exit 2 before
   anything is created, naming the account or key. No `host.toml` field can name a machine to adopt
   or a credential.
9. **Down protects unpushed work.** `devcloud vm down <n>` with an unpushed commit or uncommitted
   change in a checkout under the VM user's `~/Developer/GitHub` exits 5 naming the repository;
   `--force` proceeds.
10. **Images make it fast and stay few.** `devcloud vm image build` (each provider account) records
    an image labeled with the current recipe hash; the next `up` names that image and reaches every
    step `ok` within 5 minutes of `up` starting (the measured time recorded in Surprises); after a
    third build of the same account, `devcloud vm reap` leaves the newest two.
11. **The always-on Mac drives and reaps.** On the always-on Mac, a session's `devcloud vm up` and
    `devcloud vm down` work, the reaper's scheduled job is loaded (`launchctl list | grep
    devcloud-reap`), and its log shows runs every 10 minutes.
12. **Nothing personal in the public repository.** The branch's diff holds none of the profile's
    values (accounts, project ids, secret ids, the tailnet's name, host names), checked by grepping
    the diff for each value the profile lists.

## Design

### 1. Shape: one driver, thin adapters, the boot unchanged in kind

```
 Mac / host session                          provider                     the new host
 ─────────────────                           ────────                     ────────────
 devcloud vm up ──► caps, name, lease ──► adapter.create(spec, user-data) ──► cloud-init writes the
   │                                          (labels carry lifetime,        descriptor (no secret)
   │                                           lease, recipe, creator)
   ├─ seed over SSH (Hetzner, adopt) ─────────────────────────────────────► /etc/devcloud/seed/
   └─ waits on `devcloud status` over SSH, then over the tailnet ◄────────── devcloud-boot (parent
                                                                             steps 1–12, plus §4–§5,
                                                                             §10 below)
 devcloud vm reap (always-on Mac, every 10 min; and at the start of up/ls) ──► deletes what expired
```

Everything that is the same for every provider lives in the driver core: naming, caps, leases, the
descriptor and user-data it composes, seed delivery, waiting for the boot, SSH access, the down
guard, the reaper's decisions. An adapter does only what differs (Interfaces I13): create, delete,
list by label, set labels, give a first-contact address, build, list and delete images, and report
a type's vCPU count and price. The alternative — one script per provider, as M5's was — lost
because the person wants projects to pick providers (Decision Log, 2026-10-21) and because the
lease, cap and cleanup rules must be identical everywhere or a cheaper provider becomes the one
that leaks.

The driver is Python (3.11+ standard library, as the parent's constraints require) calling each
provider's own CLI (`hcloud`, `gcloud`), `ssh`, and `sminos`: the image and the Macs already have
these, and their auth handling is better tested than a hand-written API client.

### 2. Lifetimes and caps: who has to say yes

A session may create a **throwaway** VM (lifetime `ttl`) without asking anyone when the request is
within every cap; anything else needs the person's approval of that specific request, which the
session obtains first and then passes as `--confirmed`. The caps live in the profile (I10) with
these values the person chose:

| Cap | Value | Beyond it |
|---|---|---|
| Throwaway VMs alive at once, all accounts together | 3 | `--confirmed` |
| Lease at creation, and total lifetime through `lease` | default 12 h, at most 72 h | `--confirmed` (no upper bound) |
| Size | at most 8 vCPU | `--confirmed` |
| Lifetime `keep` | — | always `--confirmed` |
| `adopt` (sends a key to a machine the driver did not make) | — | always `--confirmed` |

`--confirmed` is not verified by the driver — it cannot see the person — so it is a contract with
the session, stated in the skill: ask through the ask tool with the specification and its cost,
and pass the flag only for what was approved. The alternative, requiring a terminal the person
types into, was rejected: sessions run without one, and the person approves from the desk or a
phone as often as from a terminal. The caps are the enforcement for everything a session does
alone; they bound the worst case to three 8-vCPU machines for 72 hours.

The count is checked before creation and again after it: two drivers (the two Macs) racing past a
count of 2 would otherwise make 4. After `create` returns, the driver lists again; if throwaway VMs
now exceed the cap and its own is the newest, it deletes its own and exits 4. Adopted machines and
`keep` VMs do not count toward the throwaway cap.

### 3. `up`, step by step

1. **Resolve the request.** Flags, then the first `--project`'s `devenv/host.toml` (Design §9), then
   the profile's defaults (I10) give the account, type, location, lifetime and lease. Check caps;
   `--dry-run` stops here, printing the resolved request, the caps' verdict and the hourly price.
2. **Name it.** `dc-<label>-<4 hex>`: label `[a-z0-9-]{1,20}`, default `vm`. The driver rejects a
   name already used by a live server in any account, a tailnet node, or a desk machine
   (`sminos machines`, when the driver's machine is enrolled), and draws again.
3. **Compose the descriptor** (parent I5, from I10's `[host]`, plus I12): name, kind `vm`, role `persistent`, tailscale
   `join` with the Secret Manager id of the profile's Tailscale OAuth client, seed (`file:` for Hetzner and adopt, `gce-metadata` for
   GCE), the config repository, the projects, the lease, the creator (the creating session's sminos
   tag, from `sminos who --session $CLAUDE_CODE_SESSION_ID` when the driver runs in a session),
   `DEVCLOUD_INBOUND=tailnet`, and the desk's provisioning key id when the profile has one. The
   descriptor carries ids, never values.
4. **Compose user-data**: cloud-init that writes the descriptor and the authorized SSH keys (§8.3),
   and, where the seed needs no delivery (GCE), starts the boot. Nothing secret: a provider keeps
   user-data for the server's life, readable through its API and from inside the VM (parent's
   driver note).
5. **Create** through the adapter, from the current image when one exists (§7), else from the
   provider's Ubuntu 24.04 with `setup.sh` run before the boot (the slow path, which `up` names in
   its output). Labels (I14) carry lifetime, lease, creator, driver machine and recipe hash.
6. **Re-count** (§2).
7. **Deliver the seed** when the adapter returns a first-contact address: the seed key file streamed
   over SSH into a root-only path (M5's method: read from its file into `ssh`'s stdin, never argv,
   never printed); then start `devcloud-boot.service`.
8. **Wait** for the boot over SSH — over the public address until the tailnet attach step reports
   `ok`, then over the tailnet, since the boot closes the public port right after it (§5). Up to 15
   minutes; on a failed step print `devcloud status`'s lines and exit 1, leaving the VM for
   inspection (its lease still bounds it).
9. **Print** name, provider, account, location, type, tailnet name, lease end, hourly price, and the
   image used (or "built from base, slow path").

`up` exit codes are in I16. A failure before the server exists leaves nothing; after it, the VM
stays with its lease, and `down` or the reaper removes it.

### 4. Leases and departure

**4.1 On the host.** A descriptor with `DEVCLOUD_EXPIRES` makes the boot do three more things:

- **Join the tailnet as an ephemeral node** (`?ephemeral=true&preauthorized=true` on the OAuth
  client secret, the parameter's default per Tailscale's OAuth documentation): the coordination
  server removes an ephemeral node 30–60 minutes after it goes offline, and at once on `tailscale
  logout`, so a VM that dies without departing still leaves the tailnet (board #90). Without a lease
  the node is non-ephemeral, as the parent built it.
- **Run the lease service**, `devcloud-lease` (a timer every 5 minutes, in the parent's service list,
  I7): at 30 minutes before the lease end (or at once, when less remains when the lease is set) it
  sends one warning, and at the lease end it runs the departure.
- **Warn the creator**: `sminos say "@<creator>" "<name>'s lease ends at <time>; unpushed: <repos>"`
  as the user, where unpushed lists each git checkout under `~/Developer/GitHub` with commits not on
  its upstream or uncommitted changes. Without a creator, or unenrolled, the warning goes to the
  journal and `wall` only. One warning per lease value: extending re-arms it.

**4.2 The departure** (`devcloud depart`, root), in this order, each step bounded so a broken one
cannot keep a VM alive: (1) `session-mirror ship --once` as the user, 5 minutes — the transcripts
are the one thing a deleted VM must not lose; (2) `sminos hub leave` as the user (exit 0 or 1 both
proceed; on 1 the desk's offline sweep revokes the machine later); (3) `tailscale logout`;
(4) stop devcloud's services; (5) power off, unless `--no-poweroff` (the reaper's path, which deletes
right after). The status file records `departed` with the time.

A GCE spot VM can be reclaimed by the provider with about 30 seconds' notice. A shutdown unit on
such a host reads the metadata server's `instance/preempted`; when it is `TRUE` it runs steps 1–3
within 25 seconds and skips the rest. An ordinary reboot runs none of this.

**4.3 The reaper** (`devcloud vm reap`, on the driver): for every account, every VM labeled
devcloud whose lease ended more than 15 minutes ago is departed (over the tailnet, `devcloud depart
--no-poweroff`, 6 minutes at most, skipped when unreachable within 10 seconds) and deleted. It also
deletes builders (§7) older than 2 hours, and images beyond the newest two per account. It never
touches a resource without the devcloud label, and checks the label again on the object it is about
to delete (ci-kit's rule: the project holds other work's resources). It runs from a scheduled job on
the person's always-on Mac every 10 minutes (`devcloud vm reap --install` writes a launchd agent on
macOS, a systemd user timer on Linux), and at the start of every `up` and `ls` on any driver, bounded
to 60 seconds there. Each deletion is one line in `~/.local/state/devcloud/reap.log`.

**4.4 What covers what.**

| Event | Transcripts | Desk | Tailnet | Server |
|---|---|---|---|---|
| Lease ends, host healthy | departure ships | `hub leave` | `logout` | reaper deletes |
| Host hung or crashed, then lease ends | lost since last ship (seconds, the shipper is continuous) | desk's offline revoke (per key, I15) | ephemeral expiry, 30–60 min | reaper deletes |
| `devcloud vm down` | departure ships | `hub leave` | `logout` | deleted at once |
| GCE spot reclaimed | 25 s fast departure | `hub leave` | `logout` | provider deletes |
| `keep` VM | never departs | stays | stays | only `down` |

### 5. Exposure: the public port closes once the tailnet is up

A VM holds the seed key (Hetzner, adopt), the GitHub token and the tailnet's join; an open SSH port
on a public address is the one inbound surface. With `DEVCLOUD_INBOUND=tailnet` the boot, right
after the tailnet attach step succeeds, installs an nftables input policy and enables it at every
later boot: inbound is dropped except loopback, the `tailscale0` interface, established and related
traffic, ICMP and ICMPv6 (IPv6 neighbor discovery needs it), UDP 41641 (Tailscale's direct
connections), and DHCP replies. Outbound is untouched. The rule lives on the host so it is the same
on every provider; a provider firewall would differ per adapter and would not cover `adopt`. If the
tailnet is broken afterwards, the person reaches the machine through the provider's console. The
driver therefore talks to a VM over the tailnet after step 4 of the boot (`root@<name>` or the user
by MagicDNS) — which needs the tailnet's ACL to let the Macs reach `tag:devcloud` on port 22 (M1
checks; H5 if not).

### 6. Providers

**6.1 Hetzner Cloud.** One account per Hetzner project; the person's devcloud project holds nothing
else of theirs. Calls go through `hcloud` with `HCLOUD_TOKEN` in the child's environment, the token
read from Secret Manager per call (never a context file, never argv). First contact is the public
IPv4 address, for the seed. Images are snapshots. Shared-core types differ by region (the US regions
lack the newest series; prices there are about 1.75 times the EU's, measured 2026-10-20), so the
adapter reports what `hcloud server-type describe` gives for the location and never assumes a type
exists. A create refused for the project's core limit (`resource_limit_exceeded`) exits 3 naming
the limit; the driver does not try another type on its own.

**6.2 Google Compute Engine.** The seed is the VM's attached service account through the metadata
server (`DEVCLOUD_SEED=gce-metadata`, which the parent's boot already supports), so no key file
reaches the machine. That account is a dedicated host account the profile names (H2), granted
Secret Manager read on the project and nothing else: a GCE host's sessions then hold a narrower
Google identity than the Macs do. The profile may name the person's own account instead, keeping
Mac-equivalence without a key on disk; the narrow account is the default because it is what made GCE
worth building here. Instances are created with that account and the `cloud-platform` scope, an
ephemeral external IPv4 (outbound only, once §5 closes inbound), labels (I14, values lowercased, dots
as dashes), and user-data under the `user-data` metadata key, which Ubuntu's cloud-init reads; the
boot starts from cloud-init, since there is no seed to deliver. `spot = true` (I11) creates a spot VM
with termination action `DELETE`. Images are custom images in an image family. The driver's `gcloud`
runs under its own `CLOUDSDK_CONFIG` with the driver's seed activated, so the Mac's own gcloud
identity is never changed. A GCE host cannot itself drive (its account has no key file and no
compute rights).

**6.3 Adopt.** `devcloud vm adopt <user@address>` makes an existing Ubuntu 24.04 machine a host: it
checks the OS, streams the plugin's `devcloud/` to the machine and runs `setup.sh` (which renames
the machine to the `dc-` name and creates the user), delivers the seed, writes the descriptor with
`DEVCLOUD_ADOPTED=1`, and starts the boot. Lifetime defaults to `keep`; `--ttl` gives it a lease
whose end runs the release instead of the departure. `devcloud vm down` on it runs the release:
departure steps 1–4, then removal of every credential devcloud put there (the seed, each
`secrets.toml` target, the secret store, the user's gcloud and gh credentials, managed settings,
`/etc/devcloud/env`, the boot descriptor) and of devcloud's units; the tools and the user stay, and
the machine keeps running. The address comes only from the command line, never from a file a
repository holds (§9). Adopted machines carry no provider label; `devcloud vm ls` finds them as
`tag:devcloud` tailnet nodes that match no provider VM.

### 7. Images

`devcloud vm image build [--account A]` creates a builder (label `devcloud=builder`, the smallest type
whose disk is the provider's minimum, so the image fits every type), runs `setup.sh` from the
plugin's own `devcloud/`, checks the builder structurally — no `/etc/devcloud/boot.env`, an empty
seed directory, none of the credential files the guard knows (parent check 6(b)), no
`$SMINOS_HOME/daemon/` — cleans cloud-init's state and the machine id so each VM gets its own,
powers off, records the image with labels `devcloud=image` and the recipe hash, and deletes the
builder. The builder never receives a seed, a descriptor, or any secret, which is why the bake does
not need the parent's known-value scan; that scan stays where it runs today, on the container image
in the `devcloud` gate. `up` uses the newest image of its account whose recipe hash is current; with
none it takes the slow path and the reaper, at its next run on the always-on Mac, builds one for each
account that lacks a current image (at most once a day per account). Whether a Hetzner snapshot made
in one location creates servers in another is M1's question; if not, images are per location.

### 8. Where the driver runs, and with what

**8.1 Configuration**: the profile's `driver.toml` (I10), synced to every Mac and host like the rest
of `~/.claude`; personal values live only there.

**8.2 Credentials**: the seed key file — `$DEVCLOUD_SEED_FILE`, else `~/.config/devcloud/seed.json`
(0600; on the MacBook a link to the existing key, on the always-on Mac a copy made for the driver
alone, H3, leaving that Mac's own gcloud account untouched), else, on a host, the user's application
default credentials when they are a service-account key. From the seed the driver takes an access
token and reads each account's credential from Secret Manager, per call. Without a seed the driver
refuses every command with exit 6.

**8.3 SSH**: each driver machine has its own key, `~/.local/state/devcloud/ssh/id_ed25519`, made on
first use. Its public half is written to the profile's `driver-keys/<machine>.pub`, which the Macs'
configuration sync commits like any profile change; user-data authorizes every key in that directory
for root at first boot, and the boot's home step keeps root's and the user's `authorized_keys` equal
to it afterwards. So a VM one Mac made is reachable from the other, and the always-on Mac's reaper
reaches every VM. Host keys are recorded on first contact (`accept-new` into the driver's own
`known_hosts`), as M5 did; providers expose no host key before first boot.

**8.4 Entry point**: the plugin's `bin/devcloud` (a plugin's `bin/` is on a session's `PATH`, as
ci-kit's `ci-gate` is) runs the plugin's `boot/devcloud` with a Python 3.11+ found on `PATH` — the
Macs' `/usr/bin/python3` is 3.9. `boot/devcloud` gains `vm`; its host commands keep their root-only
behavior and, on a machine with no `/etc/devcloud`, say so. `boot/devcloud` now resets `PATH` to the
system directories for its root jobs; `vm` must keep the caller's (`hcloud` and `gcloud` live under
Homebrew and the user's SDK on the Macs).

### 9. Projects choose their host, inside the person's choices

A repository may commit `devenv/host.toml` (I11): a provider, an account name, a type, a location, a
disk size, spot. `up --project` reads it from the local checkout when the session's working tree is
that repository (so it can be iterated), else from GitHub at the requested ref (`gh api`). It may
only choose among the accounts the profile registers, and it is checked like flags: caps apply, and
an unknown key, an unknown account or a provider mismatch fails `up` with exit 2 before anything is
created. It names no credential and no address — a public repository that could name a host would
make the driver send the person's key there. With several `--project`s, the first one's file
governs; the others' are reported and ignored.

### 10. The desk: unattended enrollment and leaving

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

Until the desk ships keys, `up --enroll-code -` reads a one-time code from its stdin; once the boot
has finished (unenrolled), the driver writes the code over SSH to a root-only file,
`/etc/devcloud/enroll-code`, and runs `devcloud reconcile`, whose step 11 enrolls with it the same
way and deletes the file once a 0, 1 or 3 has decided, whatever the enroll's outcome (a deferred step
keeps it for `devcloud enroll`; `up` then reports the deferral and exits 0) — one path for every provider, GCE included, where
nothing is delivered before the tailnet is up. Sandboxes never enroll (the parent's rule).

### 11. The skill

`devcloud/skills/vm/SKILL.md` (`devcloud:vm`) tells a session: when a VM is the right tool (work too
heavy or long for the Macs, a loaded Mac, isolation, Linux or Docker needs) and when it is not (a
quick command, anything needing the Macs' GUI); the commands; the caps and the `--confirmed`
contract (ask first through the ask tool, with the type, lifetime and price, and pass the flag only
for what was approved); how to put work on a VM (a seat through `sminos spawn` over `vm ssh`, results
coming back as pushes, pull requests and sminos messages); that a VM is deleted at its lease end with
whatever was not pushed; and to `down` what it made when the work is done. It is written with
doperpowers:writing-skills and sanity-tested in a session before it ships.

## Out of scope

- Providers beyond Hetzner Cloud and GCE (Vultr, AWS, Firecracker hosts); the adapter interface is
  their extension point.
- Sandbox containers created by the driver on a host (the parent's sandbox role); `adopt` and VMs
  only. Sandboxes never enroll at the desk, which is where this initiative's value lies.
- A budget in money: the caps bound time, count and size; the provider's billing is the record.
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
- Every provider resource the driver creates carries the label `devcloud=<kind>` (I14); no code
  path deletes or modifies a resource without it, and each deletion re-reads the label first.
- The driver runs provider CLIs with credentials in the child's environment or a private config
  directory, never in an argument list and never in the person's default CLI configuration.
- Live tests that create VMs use the person's devcloud Hetzner project and GCE project (from the
  profile); a test run's VMs are labeled `devcloud-test=<run id>` as well, and the run deletes them
  before it ends, on success or failure.
- The desk's interface (I15) is owned by the desk; a change there reaches this work through the
  desk session (sminos `smns-erb-71`, the desk orchestrator). Code against I15 as written; when the
  desk's final shapes differ, the desk session says so and the Decision Log records it.
- `devcloud/hooks/mods/secrets*.tsx` is not touched by this work (cua vendors it).

### Plan of Work

### M1 — Spike: the live facts the design leans on

A prototyping milestone: its deliverable is knowledge, recorded in Surprises & Discoveries with the
verdicts below applied, and the design revised (with Decision Log lines) where a fact contradicts it.
Use M5's provisioner (the untracked copy under `.doperpowers/sde/2026-10-20-devcloud-vm-driver/`) or
hand commands; delete everything the same day.

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
6. **GCE.** In the person's GCE project: an Ubuntu 24.04 instance with a service account attached
   and `user-data` metadata runs cloud-init's `write_files` and `runcmd`; the parent's boot with
   `DEVCLOUD_SEED=gce-metadata` reaches every step `ok` (Secret Manager read through the attached
   account); spot creation works in the chosen zone. Anything else → the GCE adapter's design is
   revised before M5.

Promote or discard: no code is promoted; the scripts stay untracked. Done when every question has a
recorded verdict and every resource is deleted.

### M2 — The host side: leases, departure, release, the closed public port, unattended enrollment

What exists at its end: a host booted with the new descriptor keys (I12) joins ephemeral when leased,
runs `devcloud-lease`, warns its creator, departs at its lease end; `devcloud depart`, `devcloud
release` and `devcloud lease set <unix>` exist on hosts; `DEVCLOUD_INBOUND=tailnet` closes the
public port after the tailnet attach; step 11 enrolls with a provisioning key (or a one-time code
file) without a person; root's and the user's `authorized_keys` follow the profile's
`driver-keys/`; a GCE spot host departs fast when reclaimed; `devcloud-boot.service` waits for
cloud-init where cloud-init runs.

Touches: `devcloud/boot/devcloudlib/descriptor.py` (I12 keys, validated as the parent validates
its own: unknown keys refused; `DEVCLOUD_EXPIRES` an integer, which the boot accepts even when it
lies in the past — a VM rebooted after its lease must still boot and then depart; only the driver
refuses a lease end in the past),
`steps.py` (tailnet attach's attributes by lease; the inbound policy after it; home's
`authorized_keys`), `sminos_host.py` (enrollment), `services.py` (the lease service in the list),
a new `devcloudlib/lease.py` (warning, departure, release, the unpushed scan), `boot/devcloud` (the
three host commands), `image/setup.sh` (nftables installed, the boot unit's ordering after
cloud-init, the spot shutdown unit), tests under `devcloud/tests/unit/` and `devcloud/tests/
integration.py`.

Interfaces: produces I12, the host commands of I16, and consumes I15 (sminos's `hub check`, `hub
enroll`, `hub leave`, `say`).

Decisions:
- `DEVCLOUD_TS_SECRET`'s attributes become `?ephemeral=<true when leased>&preauthorized=true`.
  Already joined → unchanged (an existing node keeps what it was).
- The lease service is a `devcloud-<name>` periodic service like the parent's jobs (every 300 s), so
  containers (which never carry a lease; refuse `DEVCLOUD_EXPIRES` with role `sandbox`) need nothing.
- Departure steps and bounds as Design §4.2; each step's outcome is a status entry. `depart` and
  `release` are idempotent: a second run after a completed one exits 0 doing nothing.
- `release` removes exactly what the boot wrote — it reads the same profile (`secrets.toml` targets,
  the store files it listed, the home files it copied are kept; credentials are not) — and never
  deletes the user or the home's other files. It refuses on a host without `DEVCLOUD_ADOPTED=1`.
- The enrollment follows Design §10's `hub check` table and I15. The provisioning key is fetched
  only when `hub check` says 1 or 3, kept in memory, and handed to the child's stdin. The one-time
  code file (`/etc/devcloud/enroll-code`, 0600 root), when present, is used in place of the key, and
  deleted once a 0, 1 or 3 has decided, whatever the enroll's outcome. On 4 the step records
  `deferred` and the boot goes on; `devcloud enroll` (a new entry in `devcloud`'s jobs) and the
  `devcloud-enroll` service (every 5 minutes, in the service list) finish it as Design §10 says.
- The inbound policy is one nftables table devcloud owns (`inet devcloud`), loaded by a
  `devcloud-inbound.service` ordered before the network comes up at later boots; the step is a no-op
  on containers and when the key is absent or `open`.
- Spot detection: only when the metadata server answers and `instance/scheduling/provisioning-model`
  is `SPOT`; the shutdown unit then checks `instance/preempted`.
- The fakes in `devcloud/tests/fixtures/` grow a fake `tailscale` that records `up`'s auth-key file
  attributes and `logout`, and the fake `sminos` (`fixtures/sminos.py`) learns `hub check`'s exits,
  `hub enroll` (with `--replace`) reading stdin with I15's exits, `hub leave`, and `say`.

Does not touch: the driver (`devcloud/driver/`), any provider, the guard mods.

Proves (tests pin each): a leased descriptor joins ephemeral and an unleased one does not; the warning
fires once per lease value and names dirty and unpushed checkouts; departure order and bounds, and a
hung step does not stop the next; `release` leaves the user and non-devcloud files and removes each
credential; the `hub check` table (0 skip, 1 enroll, 3 enroll with `--replace`, 4 defer: no enroll, the
daemon still starts, and `devcloud enroll` acts on a later 1 or 3 and does nothing after a 0;
2 fail) and the enroll exit table (0, 1 with each retryable and fatal reason, 2, 3); the key never reaches a file or argv (assert over the fake's recorded
argv and the filesystem); the nftables ruleset text (a unit test on the generator; the live check is
M1's and M6's); a reboot past the lease boots and departs.

### M3 — The driver and the Hetzner adapter, with the reaper

What exists at its end: from a Mac session, `devcloud vm up | ls | ssh | lease | down | reap`
(and `--dry-run`, `reap --install`) work against Hetzner, meeting acceptance 1, 2, 4, 5 and 9 in a
live smoke run (one or two VMs, deleted the same day); the profile has `driver.toml` and
`driver-keys/`.

Touches: a new `devcloud/driver/` package (core, caps, naming, descriptor and user-data composition,
SSH, reaper, the Hetzner adapter in its own module), `devcloud/bin/devcloud`, `devcloud/boot/devcloud`
(the `vm` dispatch and the `PATH` pitfall of §8.4), unit tests under `devcloud/tests/unit/` with a fake
`hcloud` (a small executable in `devcloud/tests/fixtures/` that keeps servers, images and labels in a
JSON file and answers `server create|delete|describe|list|add-label`, `server-type describe`,
`image list|delete`, `ssh-key list`), `devcloud/README.md` (the driver section), the person's profile
in the config repository (`driver.toml`, `driver-keys/` — committed there, not here).

Interfaces: produces I10, I13, I14, I16 (the `vm` commands); consumes I12 and the host commands from M2.

Decisions:
- One process per command, no daemon. State lives at the providers (labels) and in the profile; the
  only local state is the SSH key, `known_hosts`, the reap log and the private gcloud configuration.
- `ls` merges every account's labeled VMs and the tailnet's `tag:devcloud` nodes; columns: name,
  provider/account, lifetime, lease end (relative), state, hourly price, creator, and `adopted` for
  tailnet-only rows.
- `ssh` uses the tailnet name and the user by default (`--root` for root); it passes a command
  through quoted as given.
- `down` runs the down guard (acceptance 9) over SSH, then the departure (`--no-poweroff`), then
  deletes; unreachable → asks for `--force`, which skips straight to deletion.
- `lease <name> <duration>` sets the lease end to now + duration (shorter is always allowed; longer is
  checked against the lifetime cap from the VM's creation time), rewriting both the label and the
  host's descriptor (`devcloud lease set`).
- The reaper's decisions are a pure function of (resources with labels, now, reachability) → actions,
  table-tested; the side effects are a thin layer over the adapter.
- H1 (the Hetzner token into Secret Manager) happens here; the executor prepares the exact command
  and asks the person to run it if the automatic attempt is refused.

Does not touch: images (M4 — `up` takes only the slow path here), GCE and adopt (M5), the skill (M6).

Proves: the cap table of §2 (each cap, the `--confirmed` bypass, the post-create recount deleting
its own VM when racing); names never collide with the fake's servers or tailnet nodes; user-data
holds no value from the fake seed or the fake Secret Manager (scan it); the reaper's decision
table (expired past grace, expired within grace, unreachable, unlabeled, builders, image retention);
exit codes (I16).

### M4 — Images and project host files

What exists at its end: `devcloud vm image build` makes a current image for a Hetzner account, `up`
uses it (acceptance 10 live, with the measured time), the reaper builds missing images and prunes
old ones; `devenv/host.toml` steers `up` (acceptance 8), read locally or through `gh api`; the
`devenv` skill mentions `host.toml` as optional.

Touches: `devcloud/driver/` (image build, recipe hash, host-file reading), the Hetzner adapter's image
operations, `devcloud/skills/devenv/SKILL.md` (one paragraph: what `host.toml` is for and that it
only chooses among the person's accounts, checked with doperpowers:writing-skills), tests.

Interfaces: consumes I13's image operations (defined in M3, implemented here for Hetzner); produces
I11.

Decisions:
- Recipe hash: SHA-256 over the sorted paths and bytes of `devcloud/image/` and `devcloud/boot/`, 12
  hex characters.
- A builder that fails labels itself `devcloud-bake=failed-<step>`, and the build deletes it before
  exiting non-zero; the reaper deletes any builder older than 2 hours regardless.
- The daily build in the reaper is skipped while a builder of the same account exists.

Does not touch: GCE and adopt (M5).

Proves: the recipe hash changes when any file under those two directories changes and not
otherwise; `up` picks the newest current image and falls back to the slow path otherwise; the
structural check fails the bake on each forbidden file; `host.toml` validation (each key, unknown
key, unknown account, provider mismatch, caps applied) and precedence (flags over the file over the
profile).

### M5 — The GCE and adopt adapters

What exists at its end: `up` on a GCE account (acceptance 6 live, including spot creation and a
deletion) and `adopt` (acceptance 7 live) work; GCE images build; adopted machines appear in `ls`
and release on `down` or at their lease end.

Touches: `devcloud/driver/` (the GCE adapter, the adopt adapter, the private `CLOUDSDK_CONFIG`),
tests with a fake `gcloud` (instances create/delete/list/describe/add-labels, images
create/list/delete, and the metadata it was given), the profile's GCE account, H2.

Interfaces: implements I13 twice more; consumes M2's `release` and spot unit.

Decisions:
- The GCE host account is created by the executor as the person's key account if permitted
  (`gcloud iam service-accounts create` in the GCE account's project, one
  `roles/secretmanager.secretAccessor` binding on the Secret Manager project, `DEVCLOUD_SM_PROJECT`,
  and the driver's key account allowed to attach it); otherwise H2 with the exact commands.
- `adopt` refuses a machine that is not Ubuntu 24.04, one that already has `/etc/devcloud/boot.env`
  (an existing host: use `ls`), and an address given without `--confirmed`.
- An adopted machine's lifetime defaults to `keep`; it does not count toward the throwaway cap.

Does not touch: Hetzner beyond shared core fixes, the skill.

Proves: the GCE create command line (service account, scope, labels mapped, spot flags, user-data
from a file) and that no seed delivery is attempted; adopt's refusals; `ls` reporting a tailnet-only
`tag:devcloud` node as adopted.

### M6 — The skill, the always-on Mac, and acceptance

What exists at its end: `devcloud:vm` ships; the always-on Mac drives and reaps (H3, `reap
--install` there); acceptance 1–12 pass as written; the devcloud plugin's version is bumped; the
README and the parent spec point here.

Touches: `devcloud/skills/vm/SKILL.md`, `devcloud/README.md`, `devcloud/.claude-plugin/plugin.json`
(description), the parent spec's Decision Log (one line naming this spec as its driver), the
always-on Mac's setup (outside the repository).

Decisions:
- The skill is drafted with doperpowers:writing-skills and sanity-tested in a real session that,
  given a heavy task and a loaded Mac, creates a VM within caps, puts the work on it, and downs it;
  and, given a request beyond a cap, asks before passing `--confirmed`.
- Acceptance 4's three VMs reuse acceptance 1's and 6's where they are alive at the time.
- The provisioning-key path of acceptance 1 needs H4; if the desk has not shipped keys by then,
  acceptance 1 runs with `--enroll-code -` (the person pastes a one-time code) and the key path's
  live check is recorded as pending in Progress, with M2's tests standing for it.

Proves: acceptance 1–12, with the full `devcloud` gate green.

### Concrete Steps

Working directory: the `devcloud-vm` worktree.

    bash devcloud/tests/run.sh                         # unit + container integration (the devcloud gate)
    python3 -m unittest discover -s devcloud/tests/unit -p 'test_*.py'   # unit only, while iterating
    ci-gate --gates devcloud,repo-checks,shell-lint     # the committed HEAD on CI

Live (from a MacBook session; the profile's accounts):

    devcloud vm up --label acc --project <owner/repo> --dry-run
    # account   hetzner-…  location …  type …  lifetime ttl 12h  price €…/h
    # caps      throwaway 0/3 ok, lease 12h/72h ok, size 4/8 vCPU ok
    devcloud vm up --label acc --project <owner/repo>
    # dc-acc-7f3a  hetzner  … ready in 4m12s  tailnet dc-acc-7f3a  lease ends 2026-…  image dc-img-…
    devcloud vm ssh dc-acc-7f3a -- devcloud status
    devcloud vm ls
    devcloud vm lease dc-acc-7f3a 35m
    devcloud vm down dc-acc-7f3a

Expected failure shapes (I16): a cap → exit 4, `devcloud vm: over the throwaway cap (3 alive,
cap 3): ask the person, then pass --confirmed`; the down guard → exit 5, `devcloud vm: <name> has
unpushed work in <repo>: push it, or pass --force`.

### Interfaces and Dependencies

**I10 — `driver.toml`** (profile, `~/.claude/devcloud/driver.toml`; private):

    [caps]
    throwaway = 3            # alive at once, all accounts
    lease_default = "12h"
    lease_max = "72h"        # lifetime from creation, through `lease` too
    vcpu_max = 8

    [defaults]
    account = "<account name>"

    [host]                                   # the parent's descriptor fields every VM gets (I5)
    sm_project = "<GCP project id>"          # DEVCLOUD_SM_PROJECT
    config_repo = "<https clone URL>"        # DEVCLOUD_CONFIG_REPO
    config_branch = "main"                   # DEVCLOUD_CONFIG_BRANCH
    config_token_secret = "<Secret Manager id>"   # DEVCLOUD_CONFIG_TOKEN_SECRET
    tailscale_secret = "<Secret Manager id>"      # DEVCLOUD_TS_SECRET (the OAuth client)

    [desk]
    provisioning_secret = "<Secret Manager id>"   # optional until the desk ships keys

    [[account]]
    name = "<name>"
    provider = "hetzner"
    token_secret = "<Secret Manager id of the project's API token>"
    location = "<location>"
    type = "<server type>"

    [[account]]
    name = "<name>"
    provider = "gce"
    project = "<GCP project id>"
    zone = "<zone>"
    type = "<machine type>"
    service_account = "<the host account's email>"
    image_family = "devcloud"

M5 of the parent composed these descriptor fields by hand from the person's gcloud configuration
and config repository; `[host]` makes them the profile's. Unknown keys are refused.

**I11 — `devenv/host.toml`** (a repository's, committed; every key optional):

    provider = "hetzner" | "gce"
    account = "<an account name from the person's driver.toml>"
    type = "<provider type>"
    location = "<location or zone>"
    disk_gb = <integer>
    spot = true | false          # gce only

**I12 — Boot descriptor additions** (to the parent's I5):

    DEVCLOUD_EXPIRES=<Unix seconds>        # the lease; absent = keep. Rewritten by `devcloud lease set`
    DEVCLOUD_CREATOR=<sminos tag>          # optional; who gets the lease warning, e.g. @alias#short
    DEVCLOUD_INBOUND=tailnet|open          # default open
    DEVCLOUD_ADOPTED=1                     # optional; lease end runs release; down runs release
    DEVCLOUD_SMINOS_SECRET=<Secret Manager id>   # optional; the desk provisioning key

**I13 — Provider adapter** (`devcloud/driver/providers/<name>.py`):

    class Provider(Protocol):
        name: str                                              # "hetzner" | "gce" | "adopt"
        def create(self, spec: VmSpec, user_data: str) -> Vm: ...
        def delete(self, vm: Vm) -> None: ...                  # re-reads the devcloud label first
        def list(self) -> list[Vm]: ...                        # devcloud-labeled only
        def set_labels(self, vm: Vm, labels: dict[str, str]) -> None: ...
        def first_contact(self, vm: Vm) -> str | None: ...     # address for seed delivery; None = none needed
        def build_image(self, recipe: str, builder_script: str) -> Image: ...
        def images(self) -> list[Image]: ...
        def delete_image(self, image: Image) -> None: ...
        def type_info(self, type: str, location: str) -> TypeInfo: ...   # vcpus, available, hourly price or None

    VmSpec(name, account, type, location, image: Image | None, labels, disk_gb, spot)
    Vm(name, provider, account, id, location, type, labels, public_ipv4, state, created)

`adopt` implements `create` as "set up this address", `delete` as release, and no image operations.

**I14 — Labels** (Hetzner as given; GCE lowercased, `.` → `-`):

    devcloud=vm|image|builder
    devcloud-lifetime=ttl|keep
    devcloud-expires=<Unix seconds>
    devcloud-by=<driver machine>
    devcloud-creator=<session short id>
    devcloud-recipe=<12 hex>
    devcloud-test=<run id>          # live test runs only

**I15 — The desk's interface consumed** (desk spec "What the boot consumes", after its review,
commit 5168e433 on its branch, 2026-10-21):

- `sminos hub check`: writes nothing; a dead hub gives up at about 30 s, but an Access 401 on a
  credential past the grace is asked once more 90 s later before it answers 3, so one call can take
  about 150 s — every timeout devcloud wraps around it (step 11, `devcloud enroll`) allows 180 s. 0 the
  credential is accepted; 1 not enrolled here; 3 a credential is present but rejected; 4 undecided —
  the desk is unreachable, answered 5xx, or neither, or Access answered 401 for a credential still
  inside its propagation grace (600 s from `hub.json`'s enrollment time; a newly minted token can be
  refused until it reaches Access's edge), which answers 4 at once; 2 usage. (Design §10's table says what the boot does with
  each.)
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
  1 h to 30 d).
- The sminos version that ships this is the floor; an older one exits 2 on a provisioning key.

**I16 — Command surface and exit codes:**

    devcloud vm up [--label L] [--project owner/repo[@ref]]... [--account A] [--type T]
                   [--location L] [--ttl D | --keep] [--spot] [--enroll-code -] [--confirmed] [--dry-run]
    devcloud vm adopt <user@address> [--label L] [--project …]... [--ttl D] [--confirmed] [--dry-run]
    devcloud vm ls [--json]
    devcloud vm ssh <name> [--root] [-- command...]
    devcloud vm lease <name> <duration> [--confirmed]
    devcloud vm down <name> [--force]
    devcloud vm image build [--account A] | image ls
    devcloud vm reap [--install]
    devcloud depart [--no-poweroff] | release | lease set <unix>      # on a host, root

    0 ok · 1 failed (the step named) · 2 usage or invalid input (flags, host.toml, driver.toml)
    3 the provider refused (quota, capacity, type unavailable) · 4 over a cap: needs --confirmed
    5 down guard: unpushed work · 6 no seed key here

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

## Outcomes & Retrospective

Pending — written at finish.
