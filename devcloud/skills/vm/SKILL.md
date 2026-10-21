---
name: vm
description: Use when work is too heavy or too long for the person's Macs (a loaded Mac, a full test matrix, a long build or soak), needs Linux, Docker or isolation, or should run on a cloud machine or a server the person owns — creating, using, extending or deleting a devcloud VM with `devcloud vm`, adopting a server, or adding a cloud that devcloud does not ship (writing a provider).
---

# devcloud VMs

`devcloud vm` (the devcloud plugin's `bin/`, on a session's PATH; `devcloud
vm --help` has every flag) makes a cloud machine that boots into a host
like the Macs: the person's home and configuration, credentials from
Secret Manager, on the tailnet and the desk, the named projects cloned
under `~/Developer/GitHub/`. It runs on the Macs only; on a host it exits
6.

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
checks and prices any of them. The boot sets each project up through its
`devenv/`; a repository without one needs it first (`devcloud:devenv`
writes it). Lease by the work: the default is 12 h, and a shorter `--ttl`
costs less if the session forgets to `down`.

## What needs the person's yes

Within the caps a session creates a VM on its own. The caps are the
person's, in their profile: at most 3 unconfirmed throwaway VMs alive at
once (across every account and every session), a lease of at most 72 h
from creation, at most 8 vCPU, and no disk added beyond the type's own
over 200 GB. Beyond any of them `up` exits 4; `--dry-run`'s caps line
gives each cap's verdict. `--keep`
(no lease), `adopt`, and registering a provider always need the person.

`--confirmed` tells the driver the person approved this exact request; it
cannot check, so the flag is honest only when they did. Get the
specification and the hourly price from `--dry-run`, ask the person
through the ask tool — type, vCPUs, lifetime, price per hour and in total
— and pass `--confirmed` only on a request identical to what they
approved. A refusal from the cloud itself (a quota, a type unavailable)
is exit 3: that is not a cap, and `--confirmed` does not lift it; choose
a smaller type, or tell the person.

## Putting work on it

    devcloud vm ssh <name> -- 'cd ~/Developer/GitHub/<repo> && make test'          # a command, as the user
    devcloud vm ssh <name> -- sminos spawn <alias> "<task>" --cwd ~/Developer/GitHub/<repo>

A seat spawned there is a session on the VM that the person sees and
steers from the desk like any other. It reports back the way any seat
does: commits pushed, pull requests, `sminos say` to you; give it your
`@short` (from `sminos who`) when it should tell you. Work that is not
pushed lives only on the VM.

## Its end

A VM is deleted at its lease end with everything on it. Thirty minutes
before, the session that created it gets a sminos message naming the
repositories with unpushed work. `devcloud vm lease <name> <duration>`
sets the end to now plus the duration (past the 72 h lifetime only with
the person's yes). When the work is done, push it and `devcloud vm down
<name>`: it refuses (exit 5) while a checkout under `~/Developer/GitHub`
has unpushed or uncommitted work, and `--force` discards that work, so
use it only for work nobody needs. `devcloud vm ls` shows every VM, its
lease and price, and the throwaway count against the cap.

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
    list        {} -> [Vm]             only servers carrying the label devcloud
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
