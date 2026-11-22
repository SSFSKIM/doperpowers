"""The check that nothing is published under a channel id (CH1 of
docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md, C1 and C4;
docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, Interfaces §9).
Called by every suite of CH1 that runs an uplink, and by CH2's.

It judges what this code added to the store it was given, so a suite over a
store an older copy wrote into takes the baseline first, before any verb,
tick or uplink of this code reads the store (a reading verb reconciles):

    before = baseline(sminos_home, channel_ids)
    ... the suite runs ...
    published(endpoint.received, channel_ids, before)   # [] for none
    written(sminos_home, channel_ids, machine, before)  # [] for none

Each returns one line per breach. A breach on the wire:
- a `member` frame whose `project` is a channel id;
- a session-plane message whose project is one (`presence`, `machine`,
  `host`, a subscription's, a request's settlement), but the `end` that
  refuses a `subscribe`;
- a `pending` frame, a `words?`, or a `reach?` whose event is no
  `channel-request`, for one;
- a `snapshots` answer for one that carries an event;
- an `events` frame for one carrying, at a position the baseline does not
  hold for that channel with that same event, a kind outside `allowed`;
  and a `retired` there that is not the undo of an older `joined`: its
  reason `moved`, the baseline holding in that same channel a `joined` of
  its session with no `retired` after it;
- a `member` frame whose `channels` is empty, holds more than 128 ids or an
  id that is no channel's, or that carries the key on a connection whose
  welcome did not list `channels` (`welcomed`: the numbers of those whose
  did).
And on disk, for this machine's writers (`machine`: its name, or its names
now and former): an event in a channel's log at a position the baseline
does not hold with that event, of a kind outside `allowed`, and the
`retired` rule above; anything in a channel's host store; and (in CH1, its
default) a delivery record under a channel's log. An event the baseline
holds is uploaded in its writer's order as any own event is, and is no
breach. CH2 passes the kinds it adds, and `deliveries=False`, under which a
channel's `delivered/` holds a thread's delivery record and its lock and
nothing else (CH2's M2: one record a thread, by its id): a file there named
by anything but an id (`human.json`, a person's), or a record that is no
JSON object of writer entries, is a breach.
"""
import glob
import json
import os
import re

ALLOWED = ("channel-request", "channel-env", "retired", "void")
CHANNEL_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-8[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
LIMIT = 128
HOST_STORE = "host"
THREAD_FILE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(json|lock)")


def is_channel(value):
    return isinstance(value, str) and CHANNEL_ID.fullmatch(value) is not None


def _log_events(sminos_home, cid):
    out = []
    for path in sorted(glob.glob(os.path.join(sminos_home, "projects", cid, "log", "*.jsonl"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict) and isinstance(e.get("writer"), str) and type(e.get("seq")) is int:
                    out.append(e)
    return out


def _same(a, b):
    """Whether two copies are one event: the upload carries it as stored, less `verified`."""
    def strip(e):
        return {k: v for k, v in e.items() if k != "verified"}
    return strip(a) == strip(b)


def baseline(sminos_home, channel_ids):
    """{(channel id, writer, seq): the event held there} for every event the
    channels' logs hold now."""
    return {(cid, e["writer"], e["seq"]): e for cid in channel_ids for e in _log_events(sminos_home, cid)}


def _undoes_older_joined(cid, e, before):
    """Whether a `retired` new under channel `cid` is the undo of a `joined`
    an older copy wrote there: reason `moved`, and the baseline holding in
    `cid` a `joined` of its session with no `retired` of it after."""
    if e.get("reason") != "moved" or not isinstance(e.get("session"), str):
        return False
    own = sorted((x for (c, _, _), x in before.items() if c == cid and x.get("session") == e["session"]
                  and x.get("kind") in ("joined", "retired")), key=lambda x: (str(x.get("ts") or ""), x["seq"]))
    return bool(own) and own[-1].get("kind") == "joined"


def _event_breach(cid, e, before, allowed, where):
    held = before.get((cid, e.get("writer"), e.get("seq")))
    if held is not None and _same(held, e):
        return None
    kind = e.get("kind")
    if kind not in allowed:
        return "%s: a %r event under channel %s at %s:%s" % (where, kind, cid, e.get("writer"), e.get("seq"))
    if kind == "retired" and not _undoes_older_joined(cid, e, before):
        return "%s: a retired under channel %s at %s:%s that undoes no older joined of %s" % (
            where, cid, e.get("writer"), e.get("seq"), e.get("session"))
    return None


def _frames(frames):
    """(connection number or None, frame) for each frame given, alone or as a stand-in's (number, frame)."""
    for f in frames:
        if isinstance(f, tuple) and len(f) == 2 and isinstance(f[1], dict):
            yield f
        elif isinstance(f, dict):
            yield None, f


def published(frames, channel_ids, before={}, allowed=ALLOWED, welcomed=()):  # noqa: B006 — read, never written
    """Each breach among the frames a stand-in kept, one line each."""
    ids = set(channel_ids)
    out = []
    for conn, f in _frames(frames):
        t = f.get("t")
        pid = f.get("project")
        if t == "member":
            if pid in ids or is_channel(pid):
                out.append("a member frame of %s names channel %s as its project" % (f.get("session"), pid))
            if "channels" in f:
                chs = f["channels"]
                if conn not in welcomed:
                    out.append("a member frame of %s carries channels on connection %s, whose welcome listed none"
                               % (f.get("session"), conn))
                if not isinstance(chs, list) or not chs:
                    out.append("a member frame of %s carries channels %r: none is sent as no key" % (f.get("session"),
                                                                                                    chs))
                elif len(chs) > LIMIT or not all(is_channel(c) for c in chs):
                    out.append("a member frame of %s carries channels past the limit or not a channel's" % f.get(
                        "session"))
        elif t == "session":
            m = f.get("message") or {}
            mp = m.get("project")
            if mp in ids or is_channel(mp):
                if not (m.get("kind") == "end" and (m.get("body") or {}).get("reason") == "error"):
                    out.append("a session-plane %r message under channel %s" % (m.get("kind"), mp))
        elif t == "pending" and (pid in ids or is_channel(pid)):
            out.append("a pending set under channel %s" % pid)
        elif t == "words?" and (pid in ids or is_channel(pid)):
            out.append("a words? under channel %s" % pid)
        elif t == "reach?" and (pid in ids or is_channel(pid)) \
                and (f.get("event") or {}).get("kind") != "channel-request":
            out.append("a reach? under channel %s for a %r" % (pid, (f.get("event") or {}).get("kind")))
        elif t == "snapshots" and (pid in ids or is_channel(pid)) and f.get("events"):
            out.append("a snapshots answer for channel %s carries %d events" % (pid, len(f["events"])))
        elif t == "events" and (pid in ids or is_channel(pid)):
            for e in f.get("events") or ():
                line = _event_breach(pid, e, before, allowed, "uploaded")
                if line:
                    out.append(line)
    return out


def written(sminos_home, channel_ids, machine, before={}, allowed=ALLOWED, deliveries=True):  # noqa: B006
    """The same over the store: each channel's log files of this machine's
    writers, its host store, and (with `deliveries`) any delivery record
    under it."""
    names = (machine,) if isinstance(machine, str) else tuple(machine)
    out = []
    for cid in channel_ids:
        home = os.path.join(sminos_home, "projects", cid)
        for e in _log_events(sminos_home, cid):
            if e["writer"].partition("/")[0] in names:
                line = _event_breach(cid, e, before, allowed, "written")
                if line:
                    out.append(line)
        host = [p for p in glob.glob(os.path.join(home, HOST_STORE, "*")) if not p.endswith(".lock")]
        if host:
            out.append("channel %s's host store holds %s" % (cid, ", ".join(sorted(map(os.path.basename, host)))))
        if deliveries:
            held = [p for p in glob.glob(os.path.join(home, "delivered", "*")) if not p.endswith(".lock")]
            if held:
                out.append("channel %s holds delivery records: %s" % (cid, ", ".join(sorted(map(os.path.basename,
                                                                                               held)))))
        else:
            out.extend(_delivery_breaches(cid, os.path.join(home, "delivered")))
    return out


def _delivery_breaches(cid, d):
    """A channel's `delivered/` as CH2 writes it: `<thread id>.json`, a JSON
    object of writer entries, and `<thread id>.lock`, and nothing else."""
    out = []
    for p in sorted(glob.glob(os.path.join(glob.escape(d), "*"))):
        m = THREAD_FILE.fullmatch(os.path.basename(p))
        if m is None:
            out.append("channel %s's delivered/ holds %s, which is no thread's record" % (cid, os.path.basename(p)))
            continue
        if m.group(2) == "lock":
            continue
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            rec = None
        if not (isinstance(rec, dict) and all(isinstance(v, dict) for v in rec.values())):
            out.append("channel %s's delivery record %s is no record of writer entries" % (cid, os.path.basename(p)))
    return out
