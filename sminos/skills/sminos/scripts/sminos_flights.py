#!/usr/bin/env python3
"""sminos_flights — an outbox's messages on their way to the hub, per
project, for what no handshake rebuilds (sminos_requests' settlements,
sminos_rpc's compaction messages).

The uplink queues a message on a sender lane (`send`), and the POST carrying
it is answered later on the main thread, or never. Three facts decide when a
message is the hub's:

- A 200 is not enough. The hub answers a POST 200 even for the session
  frames it refuses `not-open` (it lost the project's open state), and that
  refusal comes down the stream apart from the answer, before it or after
  it. So a message answered 200 is only `held`, kept to be owed again, until
  a `hello` of its project queued after it is answered (`confirm`). A frame
  answered before that hello was even queued was taken by the hub before the
  hello, so a `not-open` of it was written down the stream before the hub
  read the hello; one that still came after the hello's answer (the hub's
  refusals and its replies go on separate lanes) would be the one loss left.
  The hold is bounded by the hellos the uplink sends: every open, every
  change of `follow`, every archive period (SMINOS_ARCHIVE_EVERY, 15
  minutes, unless it is 0), and a new stream.
- A `not-open` (`refuse`) makes every attempt of the project before it void:
  its project's epoch moves, so a POST of an older epoch answered 200 later
  takes nothing, and every message of the project in flight or held is owed
  again, to go with or after the re-open.
- A new stream (`reset`) voids every lane before it: what was in flight or
  held is owed again.

A message owed twice may reach the hub twice; the hub takes a settlement once
per raise (MAWS desk-hub `Project.settled`, `markSettled`), so a duplicate is
the side to err on. Everything here runs on the uplink's main thread.
"""

import collections
import itertools


class Flights:
    """The messages of one outbox in flight and held, keyed by the frame
    objects the outbox holds."""

    def __init__(self):
        self.epoch = collections.Counter()  # project → how many `not-open`s voided its attempts
        self.flying = {}                    # id(frame) → (frame, project, epoch, stamp): queued, not answered
        self.held = {}                      # project → [(stamp, frame)]: answered 200, not yet confirmed
        self.stamps = itertools.count()

    def send(self, pid, frames):
        """`frames` of project `pid` queued on a lane: in flight. The attempt
        (its epoch), which `answered` is handed back."""
        epoch = self.epoch[pid]
        for f in frames:
            self.flying[id(f)] = (f, pid, epoch, next(self.stamps))
        return epoch

    def in_flight(self, frame):
        """Whether the frame is on a lane in an attempt that still stands:
        not to be queued again."""
        entry = self.flying.get(id(frame))
        return entry is not None and entry[2] == self.epoch[entry[1]]

    def answered(self, frame, epoch):
        """The POST of attempt `epoch` carrying the frame was answered 200:
        whether the frame leaves its outbox (held now, until `confirm`). An
        attempt a `not-open` voided takes nothing: the frame stays owed."""
        entry = self.flying.get(id(frame))
        if entry is None or entry[2] != epoch or epoch != self.epoch[entry[1]]:
            return False
        del self.flying[id(frame)]
        self.held.setdefault(entry[1], []).append((entry[3], frame))
        return True

    def mark(self):
        """Taken as a hello is queued: what was queued before it."""
        return next(self.stamps)

    def confirm(self, pid, mark):
        """A hello of the project queued at `mark` was answered: the held
        messages queued before it are the hub's. They are returned."""
        held = self.held.get(pid, [])
        done = [f for stamp, f in held if stamp < mark]
        left = [(stamp, f) for stamp, f in held if stamp >= mark]
        if left:
            self.held[pid] = left
        else:
            self.held.pop(pid, None)
        return done

    def refuse(self, pid):
        """The hub refused the project `not-open`: its attempts so far are
        void. The held messages are returned, owed again; those in flight are
        owed again as they stand (no longer `in_flight`)."""
        self.epoch[pid] += 1
        return [f for _, f in self.held.pop(pid, [])]

    def reset(self):
        """A new stream: nothing is in flight; the held messages are
        returned as (project, frame), owed again."""
        self.flying.clear()
        out = [(pid, f) for pid, held in self.held.items() for _, f in held]
        self.held.clear()
        return out
