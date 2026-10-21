#!/usr/bin/env python3
"""sminos_owed — what the uplink owes the hub that no handshake rebuilds
(sminos_requests' settlements, sminos_rpc's compaction messages), kept under
daemon/ so an uplink that restarts sends it again.

A message is owed from the moment it is made until a POST carrying it was
answered 200 and the answer did not name it among the frames the hub refused
whole (DX2's `refused`, MAWS #88). One refused `not-open` stays owed and goes
again once its project is open (the refusal re-opens it); one refused
otherwise would be refused again, and leaves. A POST lost, a stream cut, or
an uplink stopped leaves it owed; a duplicate is the side to err on, since the
hub takes a settlement once per raise (MAWS desk-hub `Project.settled`,
`markSettled`).

Each owner keeps its own file, `{"version": VERSION, "owed": [...]}`, written
whole at every change. A file another version wrote is ignored, never read as
this one's (said once), and the first change replaces it. Everything here
runs on the uplink's main thread.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

VERSION = 1


class Kept:
    """One owner's owed messages on disk, at daemon/<name>."""

    def __init__(self, name, log):
        self.path = os.path.join(sminos.root(), "daemon", name)
        self.log = log
        self.failing = None

    def load(self):
        """The items kept, in order; [] when there is no file, it cannot be
        read, or another version wrote it."""
        try:
            with open(self.path) as f:
                d = json.load(f)
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as e:
            self.log("%s cannot be read (%s): nothing owed is taken from it" % (self.path, e))
            return []
        version = d.get("version") if isinstance(d, dict) else None
        if version != VERSION or not isinstance(d.get("owed"), list):
            self.log("%s is not version %d's (%r): ignored, and replaced at the next change" % (
                self.path, VERSION, version))
            return []
        return d["owed"]

    def save(self, items):
        """The items, whole. A write that fails is said once while it keeps
        failing; what is owed stays in memory, sent all the same."""
        try:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            sminos.write_json(self.path, {"version": VERSION, "owed": items})
        except (OSError, ValueError) as e:
            if self.failing is None:
                self.log("%s could not be written (%s): what it owes is lost if the uplink stops first" % (
                    self.path, e))
            self.failing = str(e)
            return
        if self.failing is not None:
            self.log("%s is written again" % self.path)
        self.failing = None
