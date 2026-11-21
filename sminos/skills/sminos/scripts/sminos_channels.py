#!/usr/bin/env python3
"""sminos_channels — what reads and decides for declared channels (CH1 of
docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md; its plan,
docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, Interfaces §1 and
§5).

A channel is a log whose id passes sminos.is_channel_id. It is no project:
its view has no members (sminos.view_of), nothing of this machine is
published under its id, and a fact about a thread goes to the thread's own
project. What is here:

- Finding a channel by its id, `name#short` or name (find_channel), with the
  one refusal for a name several logs answer to (sminos.ambiguous_name).
- Registering one as the org's directory registers a log (register).
- Whether this machine opens a channel's log without `follow`
  (opens_unfollowed): read from this machine's thread records and nothing
  else (held_channels), which MAWS counts, with a member frame naming the
  channel, as this machine holding it.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sminos  # noqa: E402


def find_channel(q, required=True):
    """The channel `q` names: by its id, `name#short` or name. Exit 4 with
    the one refusal when several logs answer, with "no channel '<q>' is
    known on this machine" for none (None instead with required=False), and
    with "'<q>' is a project, not a channel" for a project."""
    out, clash = sminos._name_tiers(q)
    if clash:
        sminos.die(sminos.ambiguous_name(q, clash), sminos.EXIT_UNKNOWN)
    if not out:
        if not required:
            return None
        sminos.die("no channel '%s' is known on this machine" % q, sminos.EXIT_UNKNOWN)
    if not sminos.is_channel_id(out[0].id):
        sminos.die("'%s' is a project, not a channel" % q, sminos.EXIT_UNKNOWN)
    return out[0]


def register(channel_id, name):
    """The channel registered here as the org's directory registers a log
    (sminos.register_if_absent: no root, the enrollment's hub), a
    registration already there kept. ValueError for an id that is no
    channel's, or on a machine not enrolled at a hub."""
    if not sminos.is_channel_id(channel_id):
        raise ValueError("%r is no channel's id" % (channel_id,))
    e = sminos.enrollment()
    if e is None:
        raise ValueError("this machine is not enrolled at a desk hub: a channel's log syncs through one")
    sminos.register_if_absent(sminos.make_project(channel_id, name, "", "", {"url": e["url"], "org": e["org"]}))
    sminos.forget_caches()
    return sminos.known_project(channel_id)


_HELD = {}   # "generation": the cache generation it was last asked in, "key": the stores' stat key, "value"


def _stores_key():
    """Both thread stores as a stat reads them: every seat record file and
    every live record of a thread its human opened (each written by atomic
    replace)."""
    out = []
    for path in sminos.record_files():
        try:
            st = os.stat(path)
        except OSError:
            continue
        out.append((os.path.basename(path), st.st_ino, st.st_size, st.st_mtime_ns))
    return tuple(out), sminos.threads_module().store_key()


def held_channels():
    """Every channel id in the set of a thread of this machine that has not
    ended (sminos_threads.all_threads; a set aside record is ended), as a
    frozenset. Read again only in a new cache generation whose stores' stat
    key moved: the uplink asks at every scan for each channel it opened."""
    generation = sminos._GENERATION[0]
    if _HELD.get("generation") == generation:
        return _HELD["value"]
    key = _stores_key()   # before the read: a write during it moves the key the next generation compares
    if _HELD.get("key") != key or "value" not in _HELD:
        threads = sminos.threads_module()
        _HELD["value"] = frozenset(c for t in threads.all_threads() if not threads.record_ended(t)
                                   for c in t.get("channels") or () if sminos.is_channel_id(c))
        _HELD["key"] = key
    _HELD["generation"] = generation
    return _HELD["value"]


def opens_unfollowed(channel_id):
    """Whether this machine opens the channel's log without `follow`: a
    thread of this machine that has not ended is in it, by its record alone
    (C1). sminos does not keep this equal to MAWS's `known`, which also needs
    that thread's member frame to name the channel."""
    return channel_id in held_channels()
