#!/usr/bin/env python3
"""Message reach on the log plane (P5 O18 M3; MAWS's
docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md, D5 and D6): the
hub stand-in applying M1's rules, and sminos's side of the hub's refusals
and admission.

- HubStandin: hub_standin.py as two machines meet it over DX2 — the reader
  check on fan-out, `have` and the backlog; the `audience` refusal; the
  registry's `not-reachable` with its tombstone and its resends;
  `state-unavailable`; admission held back; `have.withheld`.
- Admitted: what a `have` confirms for the archive (`archive_have`), and the
  projection copy_log writes from it.
- Retry: a `state-unavailable` position on a direct stream goes up again
  after the wait, with no reconnect and no further write.
- Dead: an `audience` refusal stops its writer past the stream; an event
  appended to it revives it, a `void` at each refused position; a `void`
  from elsewhere is nothing to a reader.

Hermetic: HOME and SMINOS_HOME are temporary, one pair per test.
Run: python3 -B sminos/tests/test_reach.py
"""

import base64
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = tempfile.mkdtemp(prefix="smr.", dir="/tmp")
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "SMINOS_ASK_MS"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import sminos  # noqa: E402
import sminos_archive as archive  # noqa: E402
import sminos_audience  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_hublog as hublog  # noqa: E402

KEY = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
RAW_KEY = bytes(range(32))
SID = "6e000001-0000-4000-8000-0000000000a1"
OTHER_SID = "6e000001-0000-4000-8000-0000000000b2"
M1, M2 = "4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c", "5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d"


def mac():
    return {"nonce": base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode(),
            "value": base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()}


def event(writer, seq, kind="say", **fields):
    return {"ts": "2026-11-05T00:00:%02d.000Z" % (seq % 60), "writer": writer, "seq": seq, "kind": kind,
            "mac": mac(), **fields}


# ------------------------------------------------------------- the hub stand-in, as two machines meet it


class Hub:
    """hub_standin.py in a process of its own, and two machines on it:
    testhost (enrolled at start) and other (enrolled here)."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(dir=BASE)
        port_file = os.path.join(self.dir, "port")
        self.proc = subprocess.Popen([sys.executable, "-B", str(HERE / "hub_standin.py"), port_file, "cid-0",
                                      "secret-0", "60000"])
        for _ in range(400):
            if os.path.exists(port_file):
                break
            time.sleep(0.025)
        self.port = int(Path(port_file).read_text())
        self.creds = {"testhost": ("cid-0", "secret-0")}
        token = self.call("POST", "/control/enrollment", {})[1]["token"]
        got = self.call("POST", "/machine/enroll", {"token": token, "machine": "other"})[1]
        self.creds["other"] = (got["client_id"], got["client_secret"])

    def call(self, method, path, body=None, headers=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        data = raw if raw is not None else (None if body is None else json.dumps(body))
        c.request(method, path, body=data, headers={"Content-Type": "application/json", **(headers or {})})
        r = c.getresponse()
        text = r.read()
        c.close()
        return r.status, json.loads(text or b"{}")

    def stop(self):
        self.proc.kill()
        self.proc.wait()

    def state(self):
        return self.call("GET", "/control/state")[1]


class Machine:
    """One machine's DX2 stream on the stand-in: the frames down, kept, and
    POSTs of frames up under its generation."""

    def __init__(self, hub, name):
        self.hub, self.name = hub, name
        cid, secret = hub.creds[name]
        self.auth = {"CF-Access-Client-Id": cid, "CF-Access-Client-Secret": secret}
        self.frames, self.cv = [], threading.Condition()
        self.conn = http.client.HTTPConnection("127.0.0.1", hub.port, timeout=60)
        self.conn.request("GET", "/machine/stream", headers=self.auth)
        self.resp = self.conn.getresponse()
        threading.Thread(target=self.read, daemon=True).start()
        self.generation = self.wait(lambda f: f["t"] == "welcome")["generation"]

    def read(self):
        for line in self.resp:
            line = line.decode().strip()
            if line.startswith("data: "):
                with self.cv:
                    self.frames.append(json.loads(line[6:]))
                    self.cv.notify_all()

    def wait(self, pred, timeout=10, start=0):
        deadline = time.monotonic() + timeout
        with self.cv:
            while True:
                got = next((f for f in self.frames[start:] if pred(f)), None)
                if got is not None:
                    return got
                if time.monotonic() > deadline:
                    raise TimeoutError("no such frame: %r" % self.frames[-5:])
                self.cv.wait(0.05)

    def post(self, *frames):
        status, body = self.hub.call("POST", "/machine/frames", raw="\n".join(json.dumps(f) for f in frames),
                                     headers={**self.auth, "X-Desk-Generation": str(self.generation)})
        assert status == 200, (status, body)
        return body

    def mark(self):
        with self.cv:
            return len(self.frames)

    def since(self, mark, t=None):
        with self.cv:
            return [f for f in self.frames[mark:] if t is None or f["t"] == t]

    def hello(self, pid, have=None):
        m = self.mark()
        self.post({"t": "hello", "project": pid, "name": "work", "have": have or {}})
        self.wait(lambda f: f["t"] == "have" and f["project"] == pid, start=m)
        time.sleep(0.2)   # its backlog, written behind it
        return self.since(m)


class HubStandin(unittest.TestCase):
    PID = "6e000004-0000-4000-8000-0000000000c1"

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub()

    @classmethod
    def tearDownClass(cls):
        cls.hub.stop()

    def setUp(self):
        self.pid = "6e000004-0000-4000-8000-%012x" % (int(time.time() * 1e6) % (1 << 48))
        self.a = Machine(self.hub, "testhost")
        self.b = Machine(self.hub, "other")
        self.a.hello(self.pid)
        self.b.hello(self.pid)

    def refusals(self, machine, mark):
        time.sleep(0.2)
        return [f["refusal"] for f in machine.since(mark, "refused")]

    def stored(self, writer):
        return self.hub.state()["projects"][self.pid]["writers"].get(writer, [])

    def joined(self, machine, sid, seq=1, **fields):
        return event("%s/%s" % (machine, sid), seq, "joined", session=sid, alias="x", **fields)

    def test_an_event_naming_a_session_nobody_exposed_is_withheld_and_its_writer_goes_on(self):
        w = "testhost/human"
        m = self.a.mark()
        body = event(w, 1, to=[{"session": "never-exposed-" + self.pid, "alias": "o"}], text="hi")
        self.a.post({"t": "events", "project": self.pid, "events": [body, event(w, 2, to="*", text="after")]})
        self.assertEqual(self.refusals(self.a, m), [{"reason": "not-reachable", "writer": w, "seq": 1}],
                         "refused not-reachable, with no message")
        self.assertEqual([(e["seq"], e.get("withheld"), e.get("text")) for e in self.stored(w)],
                         [(1, True, None), (2, None, "after")], "a tombstone at its position; the writer goes on")
        self.assertEqual(self.stored(w)[0], {"writer": w, "seq": 1, "withheld": True})
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [body]})
        self.assertEqual(self.refusals(self.a, m), [{"reason": "not-reachable", "writer": w, "seq": 1}],
                         "the same body sent again: refused the same way")
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [{**body, "text": "another"}]})
        self.assertEqual([r["reason"] for r in self.refusals(self.a, m)], ["conflict"], "another body: conflict")
        self.assertEqual(self.b.wait(lambda f: f["t"] == "events" and f["events"][0]["writer"] == w)["events"][0],
                         {"writer": w, "seq": 1, "withheld": True}, "the other machine gets the tombstone")
        own = self.a.hello(self.pid)
        have = next(f for f in own if f["t"] == "have")
        self.assertEqual((have["have"][w], have["withheld"]), (2, {w: [1]}),
                         "the own machine's have counts it and lists it withheld")
        self.assertNotIn("withheld", next(f for f in self.b.hello(self.pid) if f["t"] == "have"),
                         "never another machine's")

    def test_a_session_exposed_first_by_its_own_snapshot_is_reachable(self):
        m = self.a.mark()
        self.b.post({"t": "events", "project": self.pid, "events": [self.joined("other", OTHER_SID)]})
        self.a.post({"t": "events", "project": self.pid, "events": [
            event("testhost/human", 1, to=[{"session": OTHER_SID, "alias": "o"}], text="hi")]})
        self.assertEqual(self.refusals(self.a, m), [])
        self.assertEqual(self.stored("testhost/human")[0]["text"], "hi")
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [self.joined("testhost", OTHER_SID)]})
        self.assertEqual(self.refusals(self.a, m), [{"reason": "not-reachable", "writer": "testhost/" + OTHER_SID,
                                                     "seq": 1}],
                         "a snapshot of a session bound to another machine is withheld")

    def test_a_batch_naming_a_session_whose_first_joined_it_carries_later_is_admitted(self):
        """A seat spawned and messaged at once: the message's writer is drawn
        before the seat's own, so its first `joined` comes later in the batch.
        Known by the batch's own snapshot (the first pass), the message goes
        through (the batch-order race in M1's replay, fixed in M2)."""
        new = "ffffffff-0000-4000-8000-%012x" % (int(time.time() * 1e6) % (1 << 48))
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [
            event("testhost/human", 1, to=[{"session": new, "alias": "n"}], text="hello, new seat"),
            self.joined("testhost", new)]})
        self.assertEqual(self.refusals(self.a, m), [])
        self.assertEqual(self.stored("testhost/human")[0].get("text"), "hello, new seat")

    def test_runs_of_withheld_positions_are_compressed(self):
        w = "testhost/human"
        evs = [event(w, s, to=[{"session": "gone-%d" % s, "alias": "g"}]) for s in (1, 2, 3)] + \
            [event(w, 4, to="*")] + [event(w, 5, to=[{"session": "gone-5", "alias": "g"}])]
        self.a.post({"t": "events", "project": self.pid, "events": evs})
        have = next(f for f in self.a.hello(self.pid) if f["t"] == "have")
        self.assertEqual(have["withheld"], {w: [[1, 3], 5]})

    def test_an_audience_its_writer_does_not_name_is_refused_audience(self):
        w = "testhost/" + SID
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [
            event(w, 1, "say", audience=[M1], to="*"), event(w, 2, "say", to="*")]})
        self.assertEqual([(r["reason"], r["seq"]) for r in self.refusals(self.a, m)], [("audience", 1)],
                         "an audience under a plain writer, and the writer stopped for the frame")
        self.assertEqual(self.stored(w), [], "nothing stored")
        stream = w + "~" + sminos.audience_digest([M2])
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [event(stream, 1, "say", audience=[M1], to="*")]})
        self.assertEqual([r["reason"] for r in self.refusals(self.a, m)], ["audience"], "a digest not its audience's")
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [event(stream, 1, "say", to="*")]})
        self.assertEqual([r["reason"] for r in self.refusals(self.a, m)], ["audience"], "a stream's event carries one")

    def test_a_stream_goes_only_to_a_machine_that_reads_it(self):
        stream = "testhost/%s~%s" % (SID, sminos.audience_digest([M1]))
        self.hub.call("POST", "/control/reader", {"machine": "testhost", "owners": [M1]})
        m = self.b.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [
            {**self.joined("testhost", SID, policyRev=1), "writer": stream, "audience": [M1]},
            event("testhost/human", 1, to="*", text="plain")]})
        self.assertEqual(self.stored(stream)[0]["kind"], "joined", "admitted: its sender inside its audience")
        time.sleep(0.3)
        self.assertEqual([e["writer"] for f in self.b.since(m, "events") for e in f["events"]], ["testhost/human"],
                         "fan-out: the plain writer alone to a machine on DX2")
        frames = self.b.hello(self.pid)
        self.assertNotIn(stream, next(f for f in frames if f["t"] == "have")["have"], "nor in its have")
        self.assertNotIn(stream, [e["writer"] for f in frames if f["t"] == "events" for e in f["events"]],
                         "nor in its backlog")
        self.assertIn(stream, next(f for f in self.a.hello(self.pid) if f["t"] == "have")["have"],
                      "the machine's own writer is its own")
        self.hub.call("POST", "/control/reader", {"machine": "other", "owners": [M1]})
        self.assertNotIn(stream, next(f for f in self.b.hello(self.pid) if f["t"] == "have")["have"],
                         "its owners inside, but a connection that reads no streams")
        self.hub.call("POST", "/control/reader", {"machine": "other", "owners": [M2], "streams": True})
        self.assertNotIn(stream, next(f for f in self.b.hello(self.pid) if f["t"] == "have")["have"],
                         "streams read, its owners outside")
        self.hub.call("POST", "/control/reader", {"machine": "other", "owners": [M1, M2], "streams": True})
        frames = self.b.hello(self.pid)
        self.assertIn(stream, next(f for f in frames if f["t"] == "have")["have"], "its owners meet the audience")
        self.assertIn(stream, [e["writer"] for f in frames if f["t"] == "events" for e in f["events"]])
        self.hub.call("POST", "/control/reader", {"machine": "other", "owners": [], "streams": False})
        self.hub.call("POST", "/control/reader", {"machine": "testhost", "owners": []})

    def test_a_member_reading_only_the_plain_writers_never_names_the_private_session(self):
        """What reaches a machine outside a private session's audience,
        through the stand-in's filter, read as sminos projects it: no member
        for the session and no trace of its id or short, though a listed
        session messaged it beside a public one (its split) and was spawned
        by it (redacted)."""
        priv, pub, child = "9d0000d4-0000-4000-8000-0000000000d4", OTHER_SID, "6e000001-0000-4000-8000-0000000000c3"
        s_stream = "testhost/%s~%s" % (priv, sminos.audience_digest([M1]))
        c_stream = "testhost/%s~%s" % (child, sminos.audience_digest([M1]))
        self.hub.call("POST", "/control/reader", {"machine": "testhost", "owners": [M1]})
        self.hub.call("POST", "/control/reader", {"machine": "other", "owners": [M2], "streams": True})
        self.b.post({"t": "events", "project": self.pid, "events": [self.joined("other", pub)]})
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [
            {**self.joined("testhost", priv, policyRev=1), "writer": s_stream, "audience": [M1]},
            event(s_stream, 2, "state", session=priv, state="working", audience=[M1]),
            self.joined("testhost", child, origin={"kind": "sminos-spawn", "spawnerSession": None}),
            {**event(c_stream, 1, text="@%s hi" % priv[:8], to=[{"session": priv, "alias": "p"}]),
             "audience": [M1]},
            event("testhost/" + child, 2, text="@pub hi", to=[{"session": pub, "alias": "pub"}])]})
        self.assertEqual(self.refusals(self.a, m), [])
        got = [e for f in self.b.hello(self.pid) if f["t"] == "events" for e in f["events"]]
        self.assertTrue(got, "the plain writers reach it")
        self.assertNotIn(priv, json.dumps(got))
        self.assertNotIn(priv[:8], json.dumps(got))
        info = sminos._projection([{k: v for k, v in e.items() if k != "mac"} for e in got])
        self.assertNotIn(priv, info)
        self.assertIn(child, info)
        self.hub.call("POST", "/control/reader", {"machine": "other", "owners": [], "streams": False})
        self.hub.call("POST", "/control/reader", {"machine": "testhost", "owners": []})

    def test_a_registry_that_cannot_be_read_stores_nothing_and_recovers(self):
        w = "testhost/human"
        self.b.post({"t": "events", "project": self.pid, "events": [self.joined("other", OTHER_SID)]})
        self.hub.call("POST", "/control/policies", {"available": False})
        try:
            m = self.a.mark()
            body = event(w, 1, to=[{"session": OTHER_SID, "alias": "o"}], text="hi")
            self.a.post({"t": "events", "project": self.pid, "events": [body, event(w, 2, to="*")]})
            self.assertEqual([(r["reason"], r["seq"]) for r in self.refusals(self.a, m)], [("state-unavailable", 1)])
            self.assertEqual(self.stored(w), [], "nothing at its position, no tombstone either")
        finally:
            self.hub.call("POST", "/control/policies", {"available": True})
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [body]})
        self.assertEqual(self.refusals(self.a, m), [])
        self.assertEqual(self.stored(w)[0]["text"], "hi", "sent again once it can be read: stored")

    def test_admission_held_back_decides_at_its_release(self):
        w = "testhost/human"
        self.hub.call("POST", "/control/admission", {"held": True})
        m = self.a.mark()
        self.a.post({"t": "events", "project": self.pid, "events": [
            event(w, 1, to="*", text="ok"), event(w, 2, to=[{"session": "gone", "alias": "g"}])]})
        self.assertEqual((self.stored(w), self.refusals(self.a, m)), ([], []), "taken, nothing decided")
        self.assertNotIn(w, next(f for f in self.a.hello(self.pid) if f["t"] == "have")["have"])
        self.hub.call("POST", "/control/admission", {"held": False})
        self.assertEqual(self.refusals(self.a, m), [{"reason": "not-reachable", "writer": w, "seq": 2}],
                         "its refusal goes down the stream at the release")
        self.assertEqual([e.get("text", "withheld") for e in self.stored(w)], ["ok", "withheld"])


# ------------------------------------------------------------- sminos's side


class Plane(unittest.TestCase):
    """A fresh installation per test, `testhost` enrolled in org-1 (DX2's
    hub.json), with one hub project, `work`, whose remote archives it."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json"),
                          {"hub": "http://127.0.0.1:9", "org": "org-1", "machine": "testhost", "client_id": "c",
                           "client_secret": "s", "key": KEY, "former": {"oldname": []},
                           "enrolled": "2026-10-28T00:00:00Z"}, mode=0o600)
        sminos.forget_caches()
        self.p = sminos.make_project("6e000004-0000-4000-8000-000000000001", "work", "", "",
                                     {"url": "http://127.0.0.1:9", "org": "org-1"})
        sminos.project_path(self.p, "log")

    def hl(self, coded=True):
        return hublog.HubLog(self.p, {"key": RAW_KEY if coded else None, "machine": "testhost"}, coded=coded)

    def put(self, writer, *events):
        """Events as they are, into a writer file (another machine's as imported, an own one as written)."""
        path = sminos.writer_path(self.p, writer)
        with open(path, "a") as f:
            for seq, fields in events:
                f.write(json.dumps({"ts": "2026-11-05T00:00:%02d.000Z" % seq, "writer": writer, "seq": seq,
                                    "kind": "say", "from": "x", "to": "*", **fields}) + "\n")
        return path

    def say(self, writer, text, **fields):
        return sminos.log_append(self.p, writer, "say", **{"from": "x", "to": "*", "text": text, **fields})

    def uploaded(self, hl):
        return [(e["writer"], e["seq"], e["kind"], e.get("text")) for frame, _ in hl.uploads() for e in frame["events"]]

    def uplink(self):
        return json.loads(Path(self.p.home, hublog.STATE_FILE).read_text())


class Admitted(Plane):
    def copied(self, writer):
        clone = tempfile.mkdtemp(dir=BASE)
        names = archive.copy_log(self.p, clone)
        path = os.path.join(clone, writer.replace("/", ".") + ".jsonl")
        held = [json.loads(line) for line in Path(path).read_text().splitlines()] if os.path.exists(path) else None
        return names, held

    def test_a_have_saves_its_own_writers_vector_and_withheld_list_beside_archive_at(self):
        self.hl().on_have({"have": {"testhost/human": 5, "oldname/" + SID: 2, "other/human": 9},
                           "withheld": {"testhost/human": [2, [4, 5]], "oldname/" + SID: [1]}, "archive": True})
        d = self.uplink()
        self.assertEqual(d["archive_have"], {"have": {"testhost/human": 5, "oldname/" + SID: 2},
                                             "withheld": {"testhost/human": [2, [4, 5]], "oldname/" + SID: [1]}},
                         "own writers only, a former name's among them, never another machine's")
        self.assertIsInstance(d["archive_at"], float)
        self.assertNotIn("archive_have_error", d)

    def test_a_former_names_withheld_positions_outlive_the_rename(self):
        """The hub lists only the name now's withheld positions: a former
        name's, listed before the rename, are kept, so the archive still
        tombstones them."""
        self.hl().on_have({"have": {"oldname/" + SID: 3}, "withheld": {"oldname/" + SID: [2]}, "archive": True})
        self.hl().on_have({"have": {"oldname/" + SID: 3, "testhost/human": 1}, "withheld": {}, "archive": True})
        self.assertEqual(self.uplink()["archive_have"]["withheld"], {"oldname/" + SID: [2]})

    def test_a_withheld_list_that_disagrees_with_its_vector_confirms_nothing(self):
        for withheld, why in (({"testhost/human": [7]}, "past that writer's head"),
                              ({"testhost/human": [[3, 2]]}, "not seqs"),
                              ({"testhost/human": "1-3"}, "not seqs"),
                              ([1, 2], "is not {writer")):
            self.hl().on_have({"have": {"testhost/human": 5}, "withheld": withheld, "archive": True})
            d = self.uplink()
            self.assertIsNone(d["archive_have"], withheld)
            self.assertIn(why, d["archive_have_error"])
            with self.assertRaises(daemon.SyncFailed) as raised:
                archive.copy_log(self.p, tempfile.mkdtemp(dir=BASE))
            self.assertIn(why, str(raised.exception), "the run fails, saying why")

    def test_no_have_yet_fails_the_run(self):
        with self.assertRaises(daemon.SyncFailed):
            archive.copy_log(self.p, tempfile.mkdtemp(dir=BASE))

    def test_the_projection_is_plain_writers_admitted_and_withheld_positions_as_tombstones(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "refused, body kept here"}), (3, {"text": "three"}),
                 (4, {"text": "not admitted yet"}))
        self.put("other/human", (1, {"text": "theirs"}), (3, {"text": "past a spent hole"}))
        self.put("oldname/" + SID, (1, {"text": "a former name's"}), (2, {"text": "held back"}))
        stream = "testhost/%s~%s" % (SID, sminos.audience_digest([M1]))
        self.put(stream, (1, {"text": "private"}))
        self.put("other/%s~%s" % (OTHER_SID, sminos.audience_digest([M1])), (1, {"text": "theirs, private"}))
        self.hl().on_have({"have": {own: 3, "oldname/" + SID: 1, "other/human": 3, stream: 1},
                           "withheld": {own: [2]}, "archive": True})
        names, held = self.copied(own)
        self.assertEqual([(e["seq"], e.get("text"), e.get("withheld")) for e in held],
                         [(1, "one", None), (2, None, True), (3, "three", None)],
                         "up to the hub's vector, the withheld position its tombstone, whatever the file holds")
        self.assertEqual(held[1], {"writer": own, "seq": 2, "withheld": True})
        self.assertEqual([e["text"] for e in self.copied("other/human")[1]], ["theirs", "past a spent hole"],
                         "another machine's as imported, whole")
        self.assertEqual([e["text"] for e in self.copied("oldname/" + SID)[1]], ["a former name's"],
                         "a former name's writer is this machine's: up to the vector")
        self.assertEqual(sorted(names), sorted(["testhost.human.jsonl", "other.human.jsonl",
                                                "oldname.%s.jsonl" % SID]), "no stream file")

    def test_a_refusal_the_have_names_is_honoured_whatever_the_local_file_holds(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (3, {"text": "three"}))   # 2 spent here
        self.hl().on_have({"have": {own: 3}, "withheld": {own: [2, 3]}, "archive": True})
        self.assertEqual(self.copied(own)[1], [{"ts": "2026-11-05T00:00:01.000Z", "writer": own, "seq": 1,
                                                "kind": "say", "from": "x", "to": "*", "text": "one"},
                                               {"writer": own, "seq": 2, "withheld": True},
                                               {"writer": own, "seq": 3, "withheld": True}])

    def test_positions_refused_audience_or_voided_here_are_tombstones_whatever_the_have_says(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "refused audience"}), (3, {"text": "voided"}),
                 (4, {"text": "four"}))
        self.hl().on_have({"have": {own: 4}, "archive": True})
        d = self.uplink()
        d.update(dead={own: {"at": [2], "last": 4}}, voided={own: [3]})
        Path(self.p.home, hublog.STATE_FILE).write_text(json.dumps(d))
        self.assertEqual([e.get("text", "tombstone") for e in self.copied(own)[1]],
                         ["one", "tombstone", "tombstone", "four"])

    def test_nothing_is_copied_from_a_conflict_kept_on(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "the hub holds another"}))
        hl = self.hl()
        hl.on_have({"have": {own: 2}, "archive": True})
        hl.bound(own, 1, conflict=True)
        self.assertEqual([e["text"] for e in self.copied(own)[1]], ["one"])


class Retry(Plane):
    def refuse(self, hl, writer, seq, reason="state-unavailable"):
        hl.on_refused({"t": "refused", "project": self.p.id,
                       "refusal": {"reason": reason, "writer": writer, "seq": seq, "message": "m"}})

    def test_a_position_the_registry_could_not_check_goes_up_again_after_the_wait(self):
        os.environ["SMINOS_ASK_MS"] = "30000"
        self.addCleanup(os.environ.pop, "SMINOS_ASK_MS")
        own = "testhost/human"
        for i in (1, 2, 3):
            self.say(own, "s%d" % i)
        hl = self.hl()
        hl.on_have({"have": {own: 1}})
        self.assertEqual([x[1] for x in self.uploaded(hl)], [2, 3])
        hl.took({own: 3})
        clock = [1000.0]
        with mock.patch.object(hublog.time, "monotonic", lambda: clock[0]):
            self.refuse(hl, own, 2)
            self.assertEqual(self.uploaded(hl), [], "nothing before the wait")
            hl.on_resend({"project": self.p.id, "writer": own, "from": 2})   # a later frame's gap
            self.assertEqual(self.uploaded(hl), [], "a resend meanwhile does not cut the wait short")
            clock[0] += 29.9
            self.assertEqual(self.uploaded(hl), [])
            clock[0] += 0.2
            self.assertEqual([x[1] for x in self.uploaded(hl)], [2, 3], "from the refused position, unasked")
            hl.took({own: 3})
            self.refuse(hl, own, 2)
            self.refuse(hl, own, 3)
            clock[0] += 15
            self.refuse(hl, own, 2)   # another refusal within the wait: the retry stays where it was
            clock[0] += 15.1
            self.assertEqual([x[1] for x in self.uploaded(hl)], [2, 3], "one retry per writer per wait")
        self.assertEqual(hl.taken().get(own, 0), 1, "never taken past what the hub could not check")

    def test_the_endpoint_rewinds_on_rl10_and_a_new_stream_starts_from_the_have(self):
        own = "testhost/human"
        self.say(own, "s1")
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        hl.took({own: 1})
        self.refuse(hl, own, 1)
        self.assertEqual(hl.paused, {}, "RL10: no pause here; the endpoint opens the hole")
        hl = self.hl()
        hl.on_have({"have": {}})
        hl.took({own: 1})
        self.refuse(hl, own, 1)
        hl.reset()
        hl.on_have({"have": {}})
        self.assertEqual([x[1] for x in self.uploaded(hl)], [1], "a new stream starts again from the hub's have")


class Dead(Plane):
    def refuse(self, hl, writer, seq):
        hl.on_refused({"t": "refused", "project": self.p.id,
                       "refusal": {"reason": "audience", "writer": writer, "seq": seq, "message": "stale"}})

    def check_revival(self, writer, audience=None):
        sminos_audience.keep_stream(self.p, writer, audience)
        self.say(writer, "one")
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        self.assertEqual([x[1] for x in self.uploaded(hl)], [1])
        hl.took({writer: 1})
        self.refuse(hl, writer, 1)
        self.assertEqual(self.uploaded(hl), [], "a stop: no retry")
        hl.reset()
        hl.on_have({"have": {}})   # a reconnect
        self.assertEqual(self.uploaded(hl), [], "dead across a reconnect")
        self.assertEqual(self.uplink()["dead"], {writer: {"at": [1], "last": 1}}, "kept in uplink.json")
        self.say(writer, "two")
        frames = [e for frame, _ in hl.uploads() for e in frame["events"]]
        void = {"ts": frames[0]["ts"], "writer": writer, "seq": 1, "kind": "void", "of": 1,
                **({"audience": audience} if audience else {})}
        self.assertEqual(frames[0], void, "revived: a content-free void at the refused position")
        self.assertEqual((frames[1]["seq"], frames[1]["text"]), (2, "two"), "then the rest as stored")
        self.assertEqual([e["text"] for e in sminos.log_read(self.p) if e["writer"] == writer], ["one", "two"],
                         "the local file keeps the original body")
        self.assertEqual(self.uplink()["voided"], {writer: [1]})
        self.assertNotIn(writer, self.uplink()["dead"])
        hl.took({writer: 2})
        echo = {"event": {**void, "created": void["ts"], "sig": {"kid": "k", "sig": "s"}, "attest": {},
                          "audience": audience or [M1], "policyRev": 3},
                "signer": {"kind": "machine", "name": "testhost"}}
        self.assertEqual(hl.take([echo]), (0, []), "the void's echo reads present")
        hl.reset()
        hl.on_have({"have": {}})
        self.assertEqual([e["kind"] for frame, _ in hl.uploads() for e in frame["events"]], ["void", "say"],
                         "a later upload of the position sends the void again")

    def test_a_plain_writer_refused_audience_stays_dead_until_written_again(self):
        self.check_revival("testhost/" + SID)

    def test_a_stream_writer_revives_with_its_audience_claimed(self):
        self.check_revival("testhost/%s~%s" % (SID, sminos.audience_digest([M1, M2])), [M1, M2])

    def test_an_operator_stream_whose_first_position_was_refused(self):
        self.check_revival("testhost/human~%s" % sminos.audience_digest([M1]), [M1])

    def test_a_stream_whose_audience_is_not_known_here_stays_put(self):
        writer = "testhost/%s~%s" % (SID, sminos.audience_digest([M1]))
        self.say(writer, "one")
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        hl.took({writer: 1})
        self.refuse(hl, writer, 1)
        self.say(writer, "two")
        self.assertEqual(self.uploaded(hl), [], "no claim to make: nothing goes up in its place")

    def test_a_void_from_elsewhere_is_nothing_to_a_reader(self):
        hl = self.hl()
        hl.on_have({"have": {}})
        v = hublog.seal(RAW_KEY, self.p.id, {"ts": "2026-11-05T00:00:01.000Z", "writer": "other/" + OTHER_SID,
                                              "seq": 1, "kind": "void", "of": 1, "audience": [M1]})
        self.assertEqual(hl.take([v]), (1, []), "imported as the hub sent it")
        sminos.forget_caches()
        self.assertEqual(sminos.view_of(self.p, titles=False).members, [], "no member of it")
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "chat", "work", "-n", "5"],
                             capture_output=True, text=True, timeout=60, cwd=BASE)
        self.assertIn("(no messages)", out.stdout, out.stdout + out.stderr)
        self.assertEqual(sminos._owed(sminos.log_read(self.p), SID, {}), [], "owed to no one")

    def test_a_tombstone_the_hub_sends_is_a_spent_position_never_reported(self):
        hl = self.hl()
        hl.on_have({"have": {}})
        w = "other/human"
        after = hublog.seal(RAW_KEY, self.p.id, {"ts": "2026-11-05T00:00:02.000Z", "writer": w, "seq": 2,
                                                  "kind": "say", "from": "o", "to": "*", "text": "after"})
        self.assertEqual(hl.take([{"writer": w, "seq": 1, "withheld": True}, after]), (1, []),
                         "the tombstone spent, nothing rejected, the writer's next event appended")
        self.assertEqual(hl.spent(), {w: {1}})
        self.assertEqual(hl.vector()[w], 2)


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
