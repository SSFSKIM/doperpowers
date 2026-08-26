---
name: agora
description: Use when agents need to communicate as a group — joining an agora group, arming the inbox listener, messaging other agents from the CLI, viewing a group's topology or conversation, or spawning daemons wired into a group.
---

# Agora — the inter-agent group communication surface

## Overview

Agora is a CLI (`skills/agora/scripts/agora`) that gives a set of Claude
sessions on one machine a shared working group: a durable conversation log,
a spawn topology (who spawned whom), per-member inboxes with push delivery,
and views of all of it for both humans and agents. It layers on top of the
harness's native point-to-point messaging — think of a group as a room and
the topology as an advanced ListAgents; native SendMessage still exists for
one-off contact outside any group.

State lives under `~/.claude/agora/groups/<group>/` (override root with
`$AGORA_HOME`). A group is created by its first join and is cheap — one per
orchestration run is typical. Aliases are the addresses; `human` is the
reserved operator identity.

## The agent protocol

Joining and receiving (a daemon spawned with `AGORA_GROUP` set skips step 1 —
it is pre-joined and its task opens with this protocol rendered):

1. `agora join <group> <alias> [--parent <spawner>] [--desc "one line"]`
2. Arm the receive surface immediately — one persistent Monitor:
   `Monitor(persistent: true, command: "<path>/agora listen <group> <alias>")`.
   Messages arrive as `<agora-message from=… …>` events. Re-arm after any
   session restart; the listener resumes from a cursor, so queued messages
   from your dormant time are delivered first (an interrupted listener may
   re-deliver the last message once — duplicates are visible, drops are not).
3. Send with explicit targets: `agora send <group> --to <alias>[,<alias>] "…"`
   (long bodies via stdin). `--from` defaults from `$AGORA_ALIAS` in your env.
4. `agora topology <group>` is the machine view (nodes, edges, unread counts);
   consult it before messaging someone new.

Routing is soft-edged: your parent, your children, and `human` are always in
reach; anyone else requires `--off-edge`, which succeeds but marks the record
in the shared log and views. Prefer routing through the topology; go off-edge
when the work genuinely needs it.

A member whose process is gone is not an error: sends to it queue in its inbox
and drain on its next wake. Escalate to `human` if a dependency stays dormant.

## The operator (human) surface

The human is not a node — they see everything and edge rules never apply to
them. From any terminal:

    agora groups                 # what groups exist
    agora view <group>           # ASCII spawn tree, unread counts, off-edge traffic
    agora list <group>           # member table (the advanced ListAgents)
    agora log <group> [-n N|-f]  # the conversation, rendered; -f to follow
    agora send <group> --to <alias> "…"   # nudge any agent directly

## Spawning daemons into a group

`daemon-spawn.sh` (doperpowers:orchestrating-daemons) carries an env-injected
agora dimension:

    AGORA_GROUP=<group> [AGORA_PARENT=<your alias>] daemon-spawn.sh <name> <task> …

The child is pre-joined as a node (parent → child edge recorded), its task is
prefixed with the agora protocol preamble (`skills/agora/references/
spawn-preamble.md`), and its environment carries `AGORA_GROUP`, `AGORA_ALIAS`,
and `AGORA_PARENT=<its own alias>` — so daemons it spawns in turn become its
children automatically. Spawn without `AGORA_GROUP` and nothing agora-related
happens at all.

Always spawn agora daemons with `--no-wait`: a session whose persistent
listener is armed reports `state=working` for as long as the monitor lives
(verified empirically), so the blocking spawn watcher would never return.
