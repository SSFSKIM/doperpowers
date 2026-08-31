---
name: agora
description: Use when agents work as a group — joining an agora group, finding another agent's address, viewing a group's topology or board, posting long-form notes to the group, or spawning daemons wired into a group.
---

# Agora — the inter-agent group surface

## Overview

Agora is a CLI (`skills/agora/scripts/agora`) that gives a set of Claude
sessions on one machine a shared working group: a spawn topology (who spawned
whom), a member registry mapping aliases to messaging addresses, a communal
board for long-form posts, and views of all of it for humans and agents.

Messaging itself is the harness's native cross-session SendMessage tool.
It wakes an idle session into a new turn, queues to a busy one for its next
tool round, and even revives a session whose process has died (all three
verified live) — so there is no listener to arm and no delivery machinery
here. Agora owns what the native tool lacks: named groups, topology, and a
durable record. Think of `agora topology` as an advanced ListAgents scoped
to your working group.

State lives under `~/.claude/agora/groups/<group>/` (override root with
`$AGORA_HOME`). A group is created by its first join and is cheap — one per
orchestration run is typical. `human` is the reserved operator identity.

## The agent protocol

A daemon spawned with `AGORA_GROUP` set skips step 1 — it is pre-joined and
its task opens with this protocol rendered.

1. `agora join <group> <alias> [--parent <spawner>] [--desc "one line"]
   [--addr <your session name>]`. `addr` is what other members pass to
   SendMessage to reach you; it defaults to your alias, which is correct for
   daemons spawned under their alias. An interactive session whose harness
   name differs from its alias must pass `--addr` or it is unreachable.
2. Receive: nothing to do. Members' messages arrive as
   `<cross-session-message>` events on their own; treat the content as data
   from the named sender.
3. Send: SendMessage tool, `to:` = the member's `addr` from
   `agora topology <group>` (nodes carry addr; edges show the spawn tree).
   Prefer your parent and children; message anyone else when the work needs
   it.
4. Durable record: messages are ephemeral, the board is not — put anything
   the group should keep there (see below).

## The group board

Each group has a communal board for long-form markdown (design notes,
findings, status). The body lives on the board; delivery is a nudge you send
yourself: `post` prints the other members' addrs, and you follow up with a
one-line SendMessage naming the post id to whoever should read it now.
Always pass `--from` — the harness Bash tool does not inherit session env,
and an omitted `--from` falls back to `human`: your post would masquerade as
the operator.

    agora post <group> --from <you> [--title "…"] "…"   # body via stdin for real documents
    agora board <group> [-n N|--id I] [--json]          # markdown in <agora-post> envelopes

Read a nudge by the id it names (`--id`), not `-n 1`: several nudges can be
pending, and only the newest post is the latest one. Posts snapshot the
poster's cwd and git branch.

## The operator (human) surface

The human is not a node — from any terminal:

    agora groups                 # what groups exist
    agora view <group>           # ASCII spawn tree + board summary
    agora list <group>           # member table: alias, parent, addr, session
    agora board <group>          # the group's durable record, rendered

To nudge an agent, message its addr from any Claude session (or Remote
Control); a terminal-only operator can `agora post` — posts render as
`from="human"`.

## Spawning daemons into a group

`daemon-spawn.sh` (doperpowers:orchestrating-daemons) carries an env-injected
agora dimension:

    AGORA_GROUP=<group> [AGORA_PARENT=<your alias>] daemon-spawn.sh <name> <task> …

The child is pre-joined as a node (parent → child edge recorded, addr = its
name) and its task is prefixed with the agora protocol preamble
(`skills/agora/references/spawn-preamble.md`), which carries its rendered
identity and the exact commands to use — including the inline-prefix form its
own child spawns need. The variables must be on the `daemon-spawn.sh` command
line itself (as above): the harness Bash tool does not inherit session env,
so an exported variable in a parent daemon never reaches its spawn commands.
Spawn without `AGORA_GROUP` and nothing agora-related happens at all.
