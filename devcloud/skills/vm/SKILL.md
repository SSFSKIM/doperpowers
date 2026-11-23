---
name: vm
description: Use when work is too heavy or too long for the person's Macs (a loaded Mac, a full test matrix, a long build or soak), needs Linux, Docker or isolation, or should run on a cloud machine or a server the person owns — creating, using, extending or deleting a devcloud VM with `devcloud vm`, adopting a server, or adding a cloud that devcloud does not ship (writing a provider).
---

# devcloud VMs

`devcloud vm` (the devcloud plugin's `bin/`, on a session's PATH; `devcloud
vm --help` has every flag) makes a cloud machine that boots into a host
like the Macs: the person's home and configuration, credentials from
Secret Manager, on the tailnet, the named projects cloned under
`~/Developer/GitHub/`. It is at the desk too, enrolled in the org so that
other machines see its sessions and they can reach you, only when it is
made to enroll: by `sminos spawn --on new`, by `up --enroll`, or with
the MAWS project under a profile that provisions it. It runs on the Macs
only; on a host it exits 6.

A VM is worth its few minutes of boot and its hourly price for work that
would take a Mac long or load it heavily, or that needs Linux, Docker or a
clean machine. It is not worth it for a quick command, nor for anything
that needs a Mac's GUI, the person's browser, or a file that exists only
on this Mac.

## Making one

    devcloud vm up --label <word> --project owner/repo [--ttl 6h] --dry-run   # the request, the caps' verdict, the price
    devcloud vm up --label <word> --project owner/repo [--ttl 6h]              # a few minutes; prints the name dc-<word>-<hex>

The account, type, location and disk come from the project's
`devenv/host.toml` if it has one, else the person's defaults. The
person's accounts, each with its default type and location, are in
their profile, `~/.claude/devcloud/driver.toml` (`$DEVCLOUD_PROFILE`
when set); `--account` and `--type` choose others, and `--dry-run`
checks and prices any of them. A host is x86-64 unless its type is Arm
(GCE's c4a, n4a and t2a, Hetzner's cax): for arm64 work, name one, e.g.
`--account gce --type c4a-standard-8`. The VM clones each project from GitHub at
its default branch, so work that exists only in this checkout never
reaches it: commit and push it to a branch, then name the branch,
`--project owner/repo@<branch>`. The boot sets each project up through its
`devenv/`; a repository without one needs it first (`devcloud:devenv`
writes it). A VM runs until `devcloud vm down`: it is usually made for
sustained work, so it is kept by default. Give it `--ttl` when the work
has a known end (a test matrix, a soak), so it deletes itself even if
nobody downs it.

## What needs the person's yes

Within the caps a session creates a VM on its own, kept or leased, with
`devcloud vm up`, or with `sminos spawn --on new`, which also opens the
session on it (below); there `--vm-confirmed` stands where `--confirmed`
does, under the same rule. The
caps are the person's, in their profile; by default at most 3 VMs made
without their yes alive at once (across every account and every
session, kept and leased together), at most 8 vCPU, and no disk added
beyond the type's own over 200 GB. Beyond any of them `up` exits 4; `--dry-run`'s
caps line gives each cap's verdict. `adopt` and registering a provider
always need the person.

`--confirmed` tells the driver the person approved this exact request;
it cannot check, so the flag is honest only when they did. Get the
specification and the hourly price from `--dry-run`, ask the person
through the ask tool — type, vCPUs, lifetime, price per hour and in
total — and pass `--confirmed` only on a request identical to what they
approved. `--on new` always asks for an enrolled, kept VM, so its
request is `devcloud vm up --dry-run --enroll --keep` with the same
projects, in the same order and at the same ref. A refusal from the
cloud itself (a quota, a type unavailable) is exit 3: that is not a cap,
and `--confirmed` does not lift it; choose a smaller type, or tell the
person.

## Putting work on it

    devcloud vm ssh <name> -- 'cd ~/Developer/GitHub/<repo> && make test'   # a command, as the user
    sminos spawn <alias> - --on <name> [--cwd <path there>] <<'EOF'          # a session on it
    <the task>
    EOF
    sminos spawn <alias> - --on new <<'EOF'                                  # a new VM, and a session on it
    <the task>
    EOF

`--on <name>` opens a seat on an enrolled VM, in its checkout of your
repository unless `--cwd` names another directory. `--on new` makes the
VM first: enrolled, kept, owned by your thread, with your worktree's
branch, which must be pushed at its commit (or the projects
`--vm-project` names). It takes no `--type`, `--account` or `--ttl`: for
another size or lifetime, make the VM with `devcloud vm up --enroll
--keep --type …` (`--ttl <duration>` in place of `--keep` for a lease),
then spawn with `--on <name>`. It takes minutes, so run it as a
background command; devcloud's own lines come through. Only devcloud's
cap line from `vm up` makes an exit 4 a question for the person. Once a
VM exists, any refusal or unknown outcome ends with the line that it is
kept: read the VM's own line above it. Where it reports the alias as
taken, spawn on that VM under another alias with `--on <name>`; where
the outcome is not known, look first as the line says, since trying
again can open a second seat, and do not spawn again because a look
found nothing: without `--channel` the line's listing reads one project
and can miss the seat. However it is opened, the seat is a
session on the VM that the person sees and steers from the desk like any
other, and its first
message names you and how to reach you: it reports back the way any seat
does, with commits pushed, pull requests and `sminos say` to you. Work
that is not pushed lives only on the VM.

## Its end

A VM is owned by a thread: the one whose session made it, or the one it
was last handed to. (A session the MAWS app launched is no thread: a VM
it makes is recorded under that session, and nothing guards that VM when
the session ends.) A kept VM costs its hourly price until someone downs
it. After three days with no activity (no transcript written, no
terminal login, no load), it sends its owning thread a sminos message
with its idle time, what it has cost, and its unpushed work, and again
every three idle days; down it when its work is done, or tell the person
why it stays. At a leased VM's lease end its departure starts, and it is
deleted with everything on it; in the lease's last thirty minutes the VM
tries to send its owning thread a message naming the repositories with
unpushed work. Each message is addressed to that thread's current
session (once the VM has seen the thread move to it) and wakes it if
stopped, as any addressed message does. Where the VM's own `say` to the
thread does not succeed (usually because it reports the thread held and
not woken, ended, or no member), the VM tries the thread's project's
live sessions, then, when none is live, its log; a machine asleep or
offline is not by itself such a case (the VM can still see a hold that
machine published before), and the message waits for it there. Only from
a VM made from now on, whose own sminos and the reader's are updated,
does it arrive from `devcloud@<name>` (the VM's own notice, which nobody
answers) and go on for a held thread. A VM made from now on, whose own
sminos is updated, also records each notice, where it can, in every
channel whose pool it reads itself in (a thread of it is in the channel,
or a member added the machine by hand; a channel its enrollment does not
carry, or whose log it cannot write, is passed over): `sminos chat
<channel>` shows it, addressed to no one, so it stands in for none of the
deliveries above. That copy is the notice's own text, the repositories
with unpushed work and the instruction to down the VM included, and
everyone who may read the channel reads it, beyond the owner's project;
downing the VM is still the owning thread's decision alone. On a Mac,
`sminos channel show <channel>` shows what this Mac's devcloud has of
each VM of the channel: who owns it, how long it has run and what it has
cost (list price times age), with a line after the pool when devcloud
could not be asked or did not cover an account. `devcloud vm lease <name>
<duration>` sets the end to now plus the duration, and `lease <name>
keep` removes it. A change between kept and leased makes the host rejoin
the tailnet under the same name, and `lease` waits until it is back.
When the work is done, push it and `devcloud vm down <name>`: it refuses
(exit 5) while a checkout under `~/Developer/GitHub` has unpushed or
uncommitted work, and `--force` discards that work, so use it only for
work nobody needs. `devcloud vm ls` shows the VMs of every account it
can list (it names the accounts it skips), each with its lease, age,
price and cost so far, and the unconfirmed count against the cap.

**Handing it on.** When you are done and another thread of this Mac
still uses the VM, or should take it over, hand it on rather than down
it:

    devcloud vm owner <name> <thread>     # any name sminos knows the thread by; prints its <alias>#<short>

From then on the VM's notices go to that thread, and it is the one that
cannot be retired while the VM exists. The verb sends that thread
nothing: tell it (`sminos say "@<alias>#<short> …"`, as the verb printed
it) that it owns the VM now and what the VM is for. `sminos retire` of a
thread that owns a VM is refused, naming the VM, `devcloud vm down` and
`devcloud vm owner`: which of the two is the owning thread's call, not
that of whoever asked for the retire.

## A cloud devcloud does not ship

devcloud ships Hetzner Cloud and Google Compute Engine. Any other cloud is
a **provider** the session can write: an executable, in any language, at
`<profile>/providers/<name>` (a name no shipped provider has), used by an
account in `<profile>/driver.toml` whose `provider` is that name; the
profile is `~/.claude/devcloud/`, or `$DEVCLOUD_PROFILE`. The protocol
(the plugin's `driver/providers/hetzner` is a complete example):

    <exe> <op>          one JSON object on stdin, one JSON value on stdout; nothing on argv but <op>
    exit 0 ok · exit 3 refused, stdout {"error": "...", "kind": "limit|quota|unavailable|other"} · anything else failed
    info        {} -> {"protocol": 1, "capabilities": [subset of user_data, images, spot, metadata_seed]}
    types       {"location"} -> [{"type", "vcpus", "memory_gb", "disk_gb", "available", "hourly_price", "currency"?}]
    create      {"name","type","location","image","labels","ssh_public_keys","user_data","disk_gb","spot"} -> Vm
                image null: the cloud's Ubuntu 24.04, the only OS the boot supports
    list        {} -> [Vm]             every server carrying the label devcloud and only those, or fail
    get         {"id"} -> Vm | null
    set-labels  {"id","labels"} -> Vm  the full label set
    delete      {"id"} -> {}
    Vm = {"id","name","location","type","labels","public_ipv4","state","created"}   state "running" when on; created in Unix seconds

The driver keeps every rule (caps, leases, cleanup); a provider only
translates, and the driver trusts it to. Labels go on in the create call
itself and come back verbatim from `list` and `get`; `list` returns only
labeled servers. A provider that drops a label or lists a server it
should not makes the reaper blind or destructive, which is what the test
below catches. It runs with a minimal environment (PATH, HOME, USER, LANG,
TMPDIR and the like) plus the account's: plain settings in `vars = { VAR
= "value" }`, and credentials, which reach it only as environment
variables, named by their Secret Manager ids in `env = { VAR = "<id>" }`.

Three steps are the person's, so prepare them and ask:
- putting the cloud's API credential into Secret Manager (give them the
  id you named in `env`);
- registering the provider: `devcloud vm provider register <account>
  --confirmed` records their approval of that exact file (its sha256),
  and it comes before anything runs it with the credential, the test
  included. They run it, or you do once they said yes to that file;
- any VM beyond the caps, as above.

Then `devcloud vm provider test <account>` runs the provider through a
real create, list, get, relabel and delete on the cloud. Fix and re-run
until it passes. Only a pass puts a version into use (it copies the tested
bytes to `providers/.pass/<account>`, which every call runs), so editing
the working file never breaks the VMs an earlier passing version made, and
an edit after registration needs a pass, not another registration.
Until the first pass, every command on the account exits 7.

## Adopting a server

`devcloud vm adopt <user>@<address> --confirmed` makes an Ubuntu 24.04
server the person already runs into a host until `down`, which gives it
back with devcloud removed and the person's access restored. It sends the
person's keys and credentials to that machine, so it always needs their
yes for that machine.
