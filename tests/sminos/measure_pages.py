#!/usr/bin/env python3
"""DC8.G1's measurement (the desk, DC8 M2): pages and the open off the
uplink's thread, on transcripts of at least 150 MB and 10,000 rows. Run by
hand, one at a time on a busy machine, never in the suites:

    /tmp/maws-review/with-slot.sh python3 tests/sminos/measure_pages.py \\
        [--copy TRANSCRIPT]... [--synthetic-mb 160 | --no-synthetic] [--heartbeat-ms 1200]

Each transcript — a synthetic one this writes (12,000 rows and records of
the engine's other kinds, at least 150 MB) and a copy of each --copy file,
made under a temporary HOME (the original is only read, once) — is measured
twice over:

1. In this process: one full parse as the plane did it before DC8 (the
   file read whole, every line given to json.loads; each page and each open
   cost this), against the offset index's build, then a second build of the
   same file (it reads nothing).
2. Through `sminos daemon uplink` against the hub stand-in, daemon-side: a
   subscribe's snapshot, from the moment the stand-in flushed the
   `subscribe` frame down the stream to the moment the POST carrying the
   snapshot reached it; every `rows` page the same way, paging from the
   newest row to the first line; a second subscription's snapshot. (The
   time from the test's own control request is kept beside it, as
   `pages_end_to_end`.) Throughout, timed by phase — idle, while the
   subscribe builds, while pages run: each heartbeat answer (the `hb`'s `at`
   to its `hb-ack`'s arrival); each presence (the session's engine record
   rewritten every 0.3 s to its `presence` message's arrival); and each
   delivery (an outside-origin `human`, sealed as the hub stores a web send,
   written down the stream every 0.3 s for another live member, to its
   frame's arrival on that member's inbox socket).

The load average is read at each transcript's start and end.
Hermetic: HOME and SMINOS_HOME are temporary; nothing reaches beyond
127.0.0.1.
"""

import argparse
import base64
import gc
import json
import math
import os
import random
import re
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid as uuidlib
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import test_session_plane as tsp  # noqa: E402 — its import isolates HOME and SMINOS_HOME under a temporary root

import fake_session  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_plane as plane  # noqa: E402

T = tsp.T
SMINOS = os.path.join(tsp.SCRIPTS, "sminos")
PROBE_EVERY = 0.3
KEY = bytes(range(32))                   # the org key the credential below names
MEMBER = "4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c"  # the web member whose sends are probed


class Inbox(threading.Thread):
    """A live member's inbox socket: when each delivery probe's frame came."""

    def __init__(self, path):
        super().__init__(daemon=True)
        self.path = path
        self.came = {}       # probe number → arrival
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(16)
        self.start()

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            data = b""
            while True:
                chunk = c.recv(65536)
                if not chunk:
                    break
                data += chunk
            at = time.time()
            c.close()
            for k in re.findall(r"dprobe-(\d+)-x", data.decode("utf-8", "replace")):
                self.came.setdefault(int(k), at)


def full_parse_before_dc8(path):
    """The plane's read of a whole transcript before DC8 (rows_of)."""
    with open(path, "rb") as f:
        data = f.read()
    end = data.rfind(b"\n")
    out = []
    for line in data[:end].split(b"\n"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("uuid"), str) and row["uuid"]:
            out.append((row["uuid"], row))
    return out


def synthetic(path, megabytes, rows=12000):
    """A transcript shaped as the engine writes one: user and assistant rows
    of varied sizes (some tool results carrying a nested `uuid` of their own),
    and between them the engine's records that are not rows (`api-request`
    bodies, queue operations), to at least `megabytes` MB."""
    rnd = random.Random(8)
    words = "the plane reads only what a page needs from the index it keeps ".split()
    parent = None
    with open(path, "w") as f:
        i = 0
        while i < rows or f.tell() < megabytes * 1e6:
            u = str(uuidlib.UUID(int=rnd.getrandbits(128)))
            text = " ".join(rnd.choice(words) for _ in range(rnd.choice((20, 200, 1200, 2400))))
            row = {"parentUuid": parent, "isSidechain": False, "type": "user" if i % 2 else "assistant",
                   "message": {"role": "user" if i % 2 else "assistant", "content": [{"type": "text", "text": text}]},
                   "uuid": u, "timestamp": "2026-10-17T00:00:%02d.000Z" % (i % 60)}
            if i % 7 == 0:
                row["toolUseResult"] = {"uuid": str(uuidlib.UUID(int=rnd.getrandbits(128))), "status": "completed"}
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
            if i % 3 == 0:
                f.write(json.dumps({"type": "api-request", "body": {"messages": [text] * 3}},
                                   separators=(",", ":")) + "\n")
            f.write(json.dumps({"type": "queue-operation", "operation": "dequeue"}) + "\n")
            parent = u
            i += 1
    return i


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return time.perf_counter() - t0, out


def in_process(path):
    """Today's full parse against the index's build and a second build."""
    with open(path, "rb") as f:
        while f.read(64 << 20):
            pass   # the page cache warm for both
    before, rows = timed(lambda: full_parse_before_dc8(path))
    count = len(rows)
    del rows   # what the parse kept would weigh on the build's collections
    gc.collect()
    t = plane.Transcript(path)
    built, _ = timed(t.extended)
    again, _ = timed(t.extended)
    return {"size_mb": round(os.path.getsize(path) / 1e6, 1), "rows": count, "indexed": len(t.index.uuids),
            "full_parse_before_s": round(before, 3), "index_build_s": round(built, 3),
            "second_build_s": round(again, 4), "index_parsed_mb": round(t.index.parsed / 1e6, 1)}


def epoch(at):
    return datetime.strptime(at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


class Rig:
    """The hub stand-in, an enrolled machine, a hub project, its uplink."""

    def __init__(self, heartbeat_ms):
        self.procs = []
        self.seq = 0      # the probed web member's last seq
        home = os.environ["HOME"]
        bindir = os.path.join(T, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "claude"), "w") as f:
            f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
        os.chmod(os.path.join(bindir, "claude"), 0o755)
        os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        os.environ["SMINOS_DERIVE_EVERY"] = "0"
        port_file = os.path.join(T, "hub.port")
        self.spawn([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1", "secret-1",
                    str(heartbeat_ms)])
        deadline = time.time() + 10
        while not (os.path.exists(port_file) and tsp.read(port_file)) and time.time() < deadline:
            time.sleep(0.05)
        self.url = "http://127.0.0.1:%s" % tsp.read(port_file)
        cred = os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")
        os.makedirs(os.path.dirname(cred), exist_ok=True)
        with open(cred, "w") as f:
            json.dump({"hub": self.url, "org": "org-1", "machine": "testhost", "client_id": "cid-1",
                       "client_secret": "secret-1", "key": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"}, f)
        os.chmod(cred, 0o600)
        self.root = os.path.join(T, "hp")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
        subprocess.run(git + ["init", "-q", self.root], check=True)
        subprocess.run([SMINOS, "project", "init", "--name", "measured"], cwd=self.root, check=True,
                       capture_output=True)
        smns = os.path.join(self.root, ".smns")
        d = json.loads(tsp.read(smns))
        d["hub"] = {"url": self.url, "org": "org-1"}
        with open(smns, "w") as f:
            json.dump(d, f, indent=2)
        self.project = d["project"]
        self.home = home
        self.seen = {"sessions": 0, "hb_acks": 0}
        self.sessions, self.acks = [], []

    def spawn(self, argv):
        p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        return p

    def session(self, sid=None):
        """A live session in the project: (its id, its record's path, its process)."""
        sid = sid or tsp.new_session()
        holder = self.spawn(["sleep", "3600"])
        return sid, os.path.join(self.home, ".claude", "sessions", "%d.json" % holder.pid), holder

    def record(self, sid, path, holder, waiting, inbox=None):
        rec = {"pid": holder.pid, "sessionId": sid, "cwd": self.root, "kind": "interactive", "status": "busy",
               "waitingFor": waiting, **({"messagingSocketPath": inbox} if inbox else {})}
        with open(path + ".tmp", "w") as f:
            json.dump(rec, f)
        os.replace(path + ".tmp", path)

    def start(self):
        subprocess.run([SMINOS, "daemon", "tick"], check=True, capture_output=True)
        self.spawn([SMINOS, "daemon", "uplink"])

    def poll(self):
        _, body = tsp.call(self.url, "GET", "/control/since?sessions=%d&hb_acks=%d" % (
            self.seen["sessions"], self.seen["hb_acks"]))
        self.seen["sessions"] += len(body["sessions"])
        self.seen["hb_acks"] += len(body["hb_acks"])
        self.sessions += body["sessions"]
        self.acks += body["hb_acks"]
        return body["sessions"]

    def send(self, frame):
        """Writes the frame down the stream; when it was flushed there."""
        status, body = tsp.call(self.url, "POST", "/control/send", {"frames": [frame]})
        assert status == 200, body
        return body["at"]

    def human(self, sid, k):
        """Delivery probe `k`: a web send to member `sid`, sealed as the hub
        stores it, written down the stream as the hub fans it out; when."""
        draft = {"kind": "human", "from": "human", "member": MEMBER, "to": [{"session": sid, "alias": sid[:8]}],
                 "text": "dprobe-%d-x" % k, "created": "2026-10-17T00:00:00.000Z"}
        sealed = codes.seal(KEY, "log", self.project, draft, codes.b64url(os.urandom(16)))
        e = {**sealed, "writer": "hub/" + MEMBER, "seq": k, "ts": "2026-10-17T00:00:00.000Z"}
        return self.send({"t": "events", "project": self.project, "events": [e]})

    def wait(self, test, what, timeout=120.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for s in self.poll():
                if test(s["message"]):
                    return s
            time.sleep(0.005)
        try:
            with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
                sys.stderr.write("".join(f.readlines()[-30:]))
        except OSError:
            pass
        raise SystemExit("timed out waiting for %s" % what)

    def close(self):
        for p in reversed(self.procs):
            p.terminate()
        for p in self.procs:
            p.wait(10)


def spread(values):
    if not values:
        return {"n": 0}
    values = sorted(values)
    p95 = values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)]   # nearest rank
    return {"n": len(values), "median_ms": round(statistics.median(values) * 1000, 1),
            "p95_ms": round(p95 * 1000, 1), "max_ms": round(values[-1] * 1000, 1)}


def through_uplink(rig, sid, record_path, holder, postbox, inbox):
    """Subscribe, page to the first line, subscribe again, daemon-side;
    heartbeats, presence and deliveries timed throughout, by phase."""
    probes, humans, stop = {}, {}, threading.Event()   # humans: delivery probe number → when written down

    def probe():
        k = 0
        while not stop.is_set():
            k += 1
            probes["probe %d" % k] = time.time()
            rig.record(sid, record_path, holder, "probe %d" % k)
            stop.wait(PROBE_EVERY)

    def deliver():
        while not stop.is_set():
            rig.seq += 1
            humans[rig.seq] = rig.human(postbox, rig.seq)
            stop.wait(PROBE_EVERY)

    load = [os.getloadavg()[0]]
    phases = [("idle", time.time())]
    probers = [threading.Thread(target=f, daemon=True) for f in (probe, deliver)]
    for p in probers:
        p.start()
    time.sleep(3)
    sub = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    phases.append(("subscribe", time.time()))
    at = rig.send({"t": "subscribe", "project": rig.project, "session": sid, "agentId": None, "sub": sub})
    snap = rig.wait(lambda m: m.get("sub") == sub, "the snapshot")
    assert snap["message"]["kind"] == "snapshot", snap["message"]
    first_snapshot = snap["received"] - at
    rows = snap["message"]["body"]["rows"]
    phases.append(("pages", time.time()))
    pages, ends, before, total = [], [], rows[-1]["uuid"], len(rows)
    while True:
        t0 = time.time()
        at = rig.send({"t": "rows", "project": rig.project, "session": sid, "agentId": None, "sub": sub,
                       "before": before, "limit": 1000})
        got = rig.wait(lambda m: m.get("sub") == sub and m["kind"] in ("rows", "end"), "page %d" % len(pages))
        assert got["message"]["kind"] == "rows", got["message"]
        body = got["message"]["body"]
        pages.append(got["received"] - at)
        ends.append(got["received"] - t0)
        total += len(body["rows"])
        if not body["more"]:
            break
        before = body["rows"][-1]["uuid"]
    phases.append(("after", time.time()))
    again = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    at = rig.send({"t": "subscribe", "project": rig.project, "session": sid, "agentId": None, "sub": again})
    snap2 = rig.wait(lambda m: m.get("sub") == again, "the second snapshot")
    second_snapshot = snap2["received"] - at
    time.sleep(2)
    stop.set()
    for p in probers:
        p.join()
    load.append(os.getloadavg()[0])
    rig.poll()
    for s in (sub, again):
        rig.send({"t": "unsubscribe", "project": rig.project, "sub": s})
    phases.append(("end", time.time()))

    def phase_of(t):
        name = None
        for n, start in phases:
            if t >= start:
                name = n
        return name

    hb, presence = {}, {}
    for a in rig.acks:
        try:
            sent = epoch(a["at"])
        except (TypeError, ValueError):
            continue
        if sent >= phases[0][1]:
            hb.setdefault(phase_of(sent), []).append(a["received"] - sent)
    for s in rig.sessions:
        m = s["message"]
        if m.get("kind") == "presence" and m.get("session") == sid:
            waiting = ((m["body"] or {}).get("record") or {}).get("waitingFor")
            if waiting in probes:
                sent = probes.pop(waiting)
                presence.setdefault(phase_of(sent), []).append(s["received"] - sent)
    deliveries, undelivered = {}, 0
    for k, at in humans.items():
        if k in inbox.came:
            deliveries.setdefault(phase_of(at), []).append(inbox.came[k] - at)
        elif at < phases[-2][1] - 1:
            undelivered += 1
    shown = ("idle", "subscribe", "pages")
    return {"load_average_1m": [round(x) for x in load], "rows_reached": total,
            "first_snapshot_ms": round(first_snapshot * 1000, 1),
            "second_snapshot_ms": round(second_snapshot * 1000, 1), "pages": spread(pages),
            "pages_over_200ms": sorted(round(p * 1000) for p in pages if p > 0.2),
            "pages_end_to_end": spread(ends),
            "heartbeat_answers": {k: spread(v) for k, v in hb.items() if k in shown},
            "presence": {k: spread(v) for k, v in presence.items() if k in shown},
            "presence_probes_unanswered": len([k for k, t in probes.items() if t < phases[-2][1] - 1]),
            "deliveries": {k: spread(v) for k, v in deliveries.items() if k in shown},
            "deliveries_unanswered": undelivered}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--copy", action="append", default=[], help="a transcript to measure a copy of")
    ap.add_argument("--synthetic-mb", type=float, default=160)
    ap.add_argument("--no-synthetic", action="store_true", help="measure the copies alone")
    # Above the uplink's ACK_GAP (1 s), so each heartbeat is answered on its own.
    ap.add_argument("--heartbeat-ms", type=int, default=1200)
    a = ap.parse_args()
    rig = Rig(a.heartbeat_ms)
    results = []
    try:
        cases = []
        for name in ([] if a.no_synthetic else ["synthetic"]) + a.copy:
            # A copy keeps its own session id: its rows name it.
            sid, record_path, holder = rig.session(
                None if name == "synthetic" else os.path.basename(name)[:-len(".jsonl")])
            fake = fake_session.FakeSession(os.environ["HOME"], os.environ["SMINOS_HOME"], sid)
            dest = fake.path(None)
            if name == "synthetic":
                synthetic(dest, a.synthetic_mb)
            else:
                shutil.copyfile(name, dest)
            rig.record(sid, record_path, holder, "start")
            cases.append((name, sid, record_path, holder, dest))
        # The member the delivery probes go to: a live session with an inbox.
        postbox, postbox_record, postbox_holder = rig.session()
        inbox = Inbox(os.path.join(T, "inbox.sock"))
        rig.record(postbox, postbox_record, postbox_holder, "", inbox=inbox.path)
        rig.start()
        deadline = time.time() + 120
        while not all(any(s["message"].get("kind") == "presence" and s["message"].get("session") == sid
                          for s in rig.sessions) for sid in [c[1] for c in cases] + [postbox]):
            if time.time() > deadline:
                raise SystemExit("timed out waiting for the sessions' presence")
            rig.poll()
            time.sleep(0.05)
        for name, sid, record_path, holder, dest in cases:
            sys.stderr.write("measuring %s\n" % os.path.basename(name))
            result = {"transcript": os.path.basename(name), **in_process(dest)}
            result.update(through_uplink(rig, sid, record_path, holder, postbox, inbox))
            results.append(result)
            print(json.dumps(result, indent=2), flush=True)
    finally:
        rig.close()
        if os.environ.get("MEASURE_KEEP"):
            sys.stderr.write("kept: %s\n" % T)
        else:
            shutil.rmtree(T, ignore_errors=True)
    return results


if __name__ == "__main__":
    main()
