# Setting up sminos on a machine and in a repository

The one-time work: a project's `.smns` and its mirror, a machine's
enrollment at the desk hub, the daemon, and the machine's policy. The CLI
is the sminos plugin's `skills/sminos/scripts/sminos`
(`sminos/skills/sminos/scripts/sminos` in the doperpowers repository; not
on PATH); `sminos help` describes
every verb, the operator's rare ones (`meta`, `seat add`, `sync`,
`remove`, `migrate`, `chart`, `tui`) included. It runs on the first
`python3` on PATH, which must be 3.10 or newer; an older one (macOS's
own `/usr/bin/python3` is 3.9) stops, saying what fixes it.

## The project

    sminos project init [--name N] [--remote URL] [--hub]   # writes .smns at the repository root
    sminos project show [DIR]                       # the project a directory resolves to, and why
    sminos project attach [DIR]                     # adopt log/ into the remote's mirror

Commit `.smns`: a collaborator's clone, and every worktree, then lands in
the same project, and several repositories carrying one id are one
project; a linked worktree checked out at a head without the file reads
its main checkout's. Live sessions whose directory the new file claims
move into the project within one daemon tick.

On a machine enrolled at the desk hub a repository needs no step at all:
one no `.smns` claims is a project by its remote — `origin`, else its
only remote, normalized (scheme, user and default port dropped, path
lower-cased), so every clone and worktree of one remote on every
enrolled machine is one project, named after the remote's last path
segment as the hub first saw it. A repository with no remote, a
local-path remote, or several remotes none named `origin` derives
nothing; it and every directory outside git are in the machine's own
project (named after the machine). `project show` names the source
(`.smns at …`, `remote origin → …`, or why the machine project). On a
machine not enrolled a repository without `.smns` is a local project
named after itself, and `spawn --cwd` into a directory that is no
project registers a local project named after the directory.

A `.smns` is how a project is declared rather than inferred, and it wins
over the remote. It gives what a remote cannot: a name you choose (the
answer when two remotes share a basename), one project across several
repositories, an identity that outlives a renamed remote or a swapped
`origin`, a project for a repository that derives none, and identity on
a machine not enrolled. `project init --hub` in a repository that
resolves by its remote writes that project's id and name into the new
file (`--name` changes the name only), so committing it moves no session
and splits no history. Pin before changing a remote: without a `.smns`,
a changed remote is a new project, its live sessions move there within a
tick, and sminos says so once, naming both projects.

The log lives at `$SMINOS_HOME/projects/<id>/log/`, one append-only file
per writer, so two machines never write one file. With a `remote` in
`.smns` (any git URL the machines can push to over SSH; a bare
repository on a reachable host works) and no hub, `log/` is a git mirror
of it, and members on the project's other machines appear in `list`
with `@<machine>`. Without a daemon, a message reaches a local member
only at the moment it is sent; one that failed waits for the recipient's
next `chat`.

**The import is one-way.** The first sminos call on a machine imports
the per-host family chats (`chats/<host-seat-id>.jsonl`) into their
projects' logs and renames each to `.imported`. `migrate` runs before
every verb, so running a working copy's CLI against the real
`~/.claude/sminos` performs it — point `HOME` and `SMINOS_HOME` at
temporary directories when testing.

## The desk hub

    sminos hub enroll [--name N] [--replace]   # this machine at the desk hub
    sminos hub show                            # its enrolled name, hub, org, and the names it wrote under before (local; exit 1 when none)
    sminos hub check                           # does the hub still accept this machine's credential? (changes nothing)
    sminos hub leave                           # end this machine's enrollment, at the hub and here
    sminos project init --hub                  # this repository syncs through the hub, never git

The desk's **Machines → Enroll a machine** gives a one-time code.
`hub enroll` reads it at a hidden prompt, or from stdin when piped
(`sminos hub enroll <<<"$CODE"`, or from a file), and refuses it as an
argument: the code carries the org key, which argv and the shell's
history would expose. The enrolled name is this machine's name from
then on, in every project — what it writes is `<name>/…`, because the
hub takes from a machine only its own writers. Without `--name` it keeps
the name it writes under now (its host name, or `DAEMON_HOST`) when the
hub admits it. What it wrote under an earlier name stays on this machine
and never reaches the hub. `--replace` enrolls again with a new code.
The credential is `$SMINOS_HOME/daemon/hub.json` (mode 0600; never print
it).

**At provisioning time** (a VM's boot, no human), an admin's
**Machines → Provisioning keys** gives a reusable, revocable code,
`smns-provision-v1.…`, that enrolls any name starting with its prefix
(`dc-`) until it expires, is revoked, or is used up. It carries the org
key too: keep it in a secret store and pipe it, never write it to the
host — `printf %s "$CODE" | sminos hub enroll --name dc-build-7f3a`. The
name is `--name`, else the host's, and one not under the prefix is
refused before anything is sent (exit 2). A name another machine holds
exits 3 (pick another suffix, same code); every other refusal — the key
revoked, expired or used up, which need an admin, or a hub that did not
answer, which a rerun of the same line covers — exits 1.

**`hub check`** asks the hub whether it still accepts the stored
credential, and writes nothing: exit 0 accepted, 1 not enrolled here, 3
rejected (revoked by an admin, by the key's offline auto-revoke, or by a
`leave` whose answer was lost), 4 undecided — the hub unreachable, an
answer that is neither, or Access refusing a credential enrolled less
than ten minutes ago, which may not have reached its edge (Access's 401 is
read as a revocation only past that grace and when it holds on a recheck
90 s later, `SMINOS_ACCESS_RECHECK_S`). A boot's rule, before it starts
the daemon: 0 skip enrolling; 1 enroll; 3 enroll again with `--replace`,
the same code and name; 4 keep the credential and run `check` again later,
with backoff, until it answers 0, 1 or 3 — never re-enroll or remove
anything on 4.

**`hub leave`** revokes this machine's enrollment at the hub (a VM's
teardown runs it) and removes `hub.json`, after which the daemon stops its
uplink within a second: exit 0 when it left, when the hub had already
revoked the credential (the same reading as `check`'s), or when nothing
was enrolled here; exit 1, the credential kept, when the hub could not be
told — run it again, or let the key's offline auto-revoke finish it.

`project init --hub` writes the enrolled org into `.smns` —
`"hub": {"org": "<org>"}`, no URL: each machine reaches the hub its own
enrollment names — in a new file, or added to the one there, changing
nothing else. Commit it. A hub project is never synced through git (a
`remote` it names stays the log's archive). Every enrolled machine
follows every project of its org — it reads and delivers them without a
checkout. On a machine not enrolled in the org a `.smns` names, the
project is local there, never synced, and a reading verb says so once a
day. An enrolled machine's sessions are told who they are at session
start (the `smns-guide.sh` hook).

## The daemon

    sminos daemon run [--interval 5]   # the loop, one per machine
    sminos daemon tick                 # one iteration over every project known here
    sminos daemon install              # write the machine's service: a launchd agent (macOS), a systemd user unit (Linux)
    sminos daemon status               # whether a loop and its uplink run; each project's last tick
    sminos daemon owed                 # what this machine still owes, per project; exit 0 when nothing

Install it on every machine whose sessions should reach, and be reached
by, other machines. Each tick, per project: sync the mirror (projects
with a remote), join sessions seen on this machine and move those whose
project changed, publish state changes and renames, retry owed
deliveries (a failed push is retried each tick and given up after 60
with a line in `$SMINOS_HOME/daemon.log`); every five minutes, `derive --all`. On an
enrolled machine the loop also keeps its `uplink` child, the one stream
to the hub that carries every hub project both ways.

`daemon owed` prints a line for each project that still owes something —
the count of each kind and the oldest item's age, and at most three
references a kind (`writer:seq → recipient`), never a message body: `deliveries` owed
to a session of this machine not yet made; `words`, those a cut-over
machine's endpoint has yet to decide; and what has not reached the hub or
the endpoint yet — `upload` (this machine's own events), `kept` (the
settlements and RPC messages kept under `daemon/`), `host` (a cut-over
machine's unsent host events) and `outcomes` (delivery outcomes). It
prints `nothing owed` and exits 0 when no project owes anything, else
exits 1. A state file it cannot read (unreadable, not JSON, another
version's) is named on a line of its own, never its content, and makes it
exit 1 too: it cannot say nothing is owed. Events owed to a closed terminal session are on a line of their
own and owe nothing: they are in the log, delivered if the session comes
back. It only reads, so it runs beside the daemon; O14's cutover gate
runs it before a machine moves to its endpoint.

`daemon install` writes, on macOS,
`~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist` and prints
the `launchctl bootstrap` and `bootout` lines; on Linux,
`~/.config/systemd/user/sminos-daemon.service` and prints the
`systemctl --user` lines that enable and disable it, and `loginctl
enable-linger`, without which the user's services stop at logout and do
not start at boot. Nothing is loaded until those lines run. To install
again over a loaded agent on macOS, run the `bootout` line, then the
`bootstrap` one; a `bootstrap` right after the `bootout` can fail with
error 5 ("Input/output error"), and a retry a few seconds later loads
it. Either file
is mode 0600 (the gateway route in it in plain text). The service runs
the Python the install ran on, pinned; once that Python is removed,
install again. From an installed plugin it points the service at the
marketplace clone's `sminos/skills/sminos/scripts/sminos.py`, a stable
path, not the versioned cache, and refuses when no clone is known. A
service still naming the path before the carve-out,
`skills/sminos/scripts/sminos.py`, no longer starts once its clone has
moved past it: the Python's error is in `$SMINOS_HOME/daemon.out`, the
service's stdout and stderr; install again. Once its own code changes and holds still, `run`
stops its uplink and executes itself again in the same process on the
new code, so the service manager sees no exit and its restart throttle
does not hold the machine off the hub; `KeepAlive` or `Restart=always`
restarts it only after a crash, code that does not import included.
Two machines with the same host name would write the same files: the
second one's daemon refuses, naming the claim, until one sets
`DAEMON_HOST` or the stale claim is removed.

## The machine's policy

    sminos daemon policy [--read-only on|off] [--ceiling MODE|settings]

The owner's bound on what reaches this machine from outside it: the
desk, the hub, other machines. With no flags it prints the policy.
`--read-only on` delivers nothing written elsewhere — such a message is
recorded in the log and settled undelivered (`refused-read-only`, the
outcome the desk shows) — and refuses every request from the desk; this
machine's own sessions still reach each other. `--ceiling` is the
loosest permission mode a session spawned from outside may run under
(`plan`, `default`, `acceptEdits`, `auto`, `dontAsk`,
`bypassPermissions`); `settings`, the default, follows your settings'
`defaultMode`. The policy is read at every use, so a change holds from
the next delivery. A policy file that cannot be read keeps the machine
read-only until `daemon policy` writes it again. It is the owner's
setting: report it, and change it only when they ask.
