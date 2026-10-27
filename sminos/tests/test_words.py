#!/usr/bin/env python3
"""A person's words on a cut-over machine (O12 M6), the pieces the words
pass stands on: the `member` frames the uplink sends its endpoint (every
session of this machine, in every project known here), the append receipt
that is an own writer's provenance (`projects/<id>/receipts/<writer>.jsonl`),
the delivery record's revocation marks (`delivered_revoke`: a revoked event
is never delivered and never settled out of order), the revocation matcher
over `daemon/revoked.json`, and the label a peer message carries (`from
<alias>, owned by <email>` and its other forms) in its frame and in `sminos
chat`.

The uplink runs in this process (`sminos_uplink.run_rl10`, or one `Link` on a
lane that keeps what it is sent) against sminos's endpoint stand-in
(endpoint_standin.py), in process too. Sessions are the engine's registry
records of live `sleep` processes, in projects made by `sminos project init`.

Hermetic: every test has its own HOME, SMINOS_HOME and MAWS_USER_DATA under
one temporary directory; nothing listens beyond a Unix socket there.
Run: python3 -B sminos/tests/test_words.py
"""

import base64
import json
import os
import shutil
import stat
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
BASE = tempfile.mkdtemp(prefix="smw.", dir="/tmp")   # short: a Unix socket's path is bounded
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_plane as plane  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

KEY = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
S1 = "6d000001-0000-4000-8000-0000000000d1"
S2 = "6d000002-0000-4000-8000-0000000000d2"
S3 = "6d000003-0000-4000-8000-0000000000d3"
OTHER = "othermachine/6d0000ff-0000-4000-8000-0000000000ff"
DEV_A = {"kind": "device", "member": "mem-1", "device": "dev-a", "keyId": "k-dev-a"}
DEV_B = {"kind": "device", "member": "mem-1", "device": "dev-b", "keyId": "k-dev-b"}
MACHINE_K = {"kind": "machine", "ref": "ref-other", "name": "othermachine", "keyId": "k-machine"}
NO_REVOCATIONS = {"version": 0, "devices": [], "members": [], "keys": []}


def wait_for(pred, timeout=30, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


def daemon_log():
    try:
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            return f.read()
    except OSError:
        return ""


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Lane:
    """A Link's lane that keeps what it is sent, written as taken."""

    def __init__(self):
        self.sent = []

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None:
            then({})

    def take(self):
        out, self.sent = self.sent, []
        return out

    def posting(self):
        return False

    def close(self):
        pass


class Machine(unittest.TestCase):
    """A fresh installation per test: its HOME, SMINOS_HOME and the
    endpoint's directory under MAWS_USER_DATA; `testhost` of org-1."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"),
                          MAWS_USER_DATA=os.path.join(home, "m"))
        self.home = home
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        self.epdir = os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint")
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json"),
                          {"hub": "http://127.0.0.1:9", "org": "org-1", "machine": "testhost", "client_id": "c",
                           "client_secret": "s", "key": KEY, "former": {}, "enrolled": "2026-10-01T00:00:00Z"},
                          mode=0o600)
        sminos.forget_caches()
        rl10._SAID.update(find=None, revoked=None)

    # ---- the machine

    def cut_over(self, name="testhost", former=None):
        """identity.json, as the first welcome writes it."""
        sminos.write_json(rl10.identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": name, "former": former or {},
            "ref": "machine-ref-1", "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z",
            "build": "b"}, mode=0o600)
        sminos.forget_caches()

    def revoke(self, version=2, devices=(), members=(), keys=()):
        rl10.keep_revoked({"version": version, "devices": list(devices), "members": list(members),
                           "keys": list(keys)}, True)

    def project(self, name, hub=False):
        """A project with a checkout here (a git repository named by .smns);
        with `hub`, one of org-1's hub projects."""
        root = os.path.join(self.home, name)
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", root], check=True)
        subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "project", "init", "--name", name],
                       cwd=root, check=True, capture_output=True)
        if hub:
            smns = os.path.join(root, ".smns")
            d = json.loads(Path(smns).read_text())
            d["hub"] = {"url": "http://127.0.0.1:9", "org": "org-1"}
            Path(smns).write_text(json.dumps(d))
        sminos.forget_caches()
        project = sminos.resolve_project(root)
        sminos.project_path(project, "log")   # registered: known here
        return project

    def session(self, project, sid, name=None):
        """A live session of this machine working in the project's checkout."""
        p = subprocess.Popen(["sleep", "600"])
        path = os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % p.pid)
        with open(path, "w") as f:
            json.dump({"pid": p.pid, "sessionId": sid, "name": name or sid[:4], "nameSource": "derived",
                       "cwd": project.root, "kind": "interactive", "status": "idle"}, f)

        def end():
            if p.poll() is None:
                p.kill()
                p.wait(5)
            if os.path.exists(path):
                os.unlink(path)
        self.addCleanup(end)
        sminos.forget_caches()
        return end

    def endpoint(self, **fields):
        ep = endpoint_standin.Endpoint(self.epdir, **fields)
        ep.start()
        self.addCleanup(ep.stop)
        return ep

    def uplink(self):
        """`sminos daemon uplink`'s RL10 loop, in this process, until the test ends."""
        halt, box = threading.Event(), {}
        thread = threading.Thread(target=lambda: box.update(kept=uplink.run_rl10(halt.is_set, halt)), daemon=True)
        thread.start()

        def stop():
            halt.set()
            thread.join(30)
            if box.get("kept") is not None:
                box["kept"].close()
        self.addCleanup(stop)

    def link(self):
        """One RL10 Link, its lane keeping what it is sent."""
        cred = {"org": "org-1", "hub": "http://127.0.0.1:9", "machine": "testhost", "key": None}
        link = uplink.Link(cred, {}, transport=mock.Mock(number=1), coded=False)
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        return link

    # ---- the log

    def arrive(self, project, writer, seq, kind="human", to=(S1,), signer=DEV_A, owners=None, **fields):
        """An event from outside, stored as the uplink stores an arrival over
        RL10: `verified` added (none with signer None, as a git mirror brings one)."""
        e = {"ts": "2026-10-27T01:00:%02d.000Z" % seq, "writer": writer, "seq": seq, "kind": kind,
             "from": fields.pop("sender", "alice"), "to": [{"session": s, "alias": "m"} for s in to],
             "text": fields.pop("text", "words %d" % seq), **fields}
        if signer is not None:
            e["verified"] = {"signer": signer, **({"owners": owners} if owners is not None else {})}
        self.assertEqual(hublog.append_verbatim(project, e), "appended")
        return e

    def record(self, project, sid):
        return sminos.delivered_load(project, sid)

    def delivered_lock(self, project, sid):
        return sminos.flocked(sminos.project_path(project, "delivered", sminos.reader_key(sid) + ".lock"))


def member(sid, **fields):
    """A member row as view_of makes one, for the frame builder."""
    base = dict(session=sid, short=sid[:8], alias="m", name_source="derived", machine="testhost", local=True,
                state="idle", state_age=None, charge="", charge_source="", status="", by="", worktree="", seat=None)
    return sminos.Member(**{**base, **fields})


# ------------------------------------------------------------- the append receipt


class Receipts(Machine):
    def setUp(self):
        super().setUp()
        self.own = sminos.machine_project("org-1", "testhost")
        self.receipts = os.path.join(self.own.home, "receipts", "testhost.human.jsonl")

    def test_an_own_human_event_has_its_receipt_written_with_it(self):
        e = sminos.log_append(self.own, sminos.writer_id(), "human", **{"from": "human", "to": [], "text": "hi"})
        self.assertEqual(read_lines(self.receipts), [{"seq": 1, "hash": sminos.event_hash(e)}])
        self.assertEqual(stat.S_IMODE(os.stat(self.receipts).st_mode), 0o600)
        stored = read_lines(sminos.writer_path(self.own, "testhost/human"))[0]
        self.assertEqual(sminos.receipt_of(self.own, "testhost/human", 1), sminos.event_hash(stored),
                         "the hash is the stored body's")
        self.assertTrue(sminos.receipted(self.own, stored))
        self.assertNotIn("receipts", os.listdir(os.path.join(self.own.home, "log")), "outside log/")

    def test_only_an_own_writers_human_events_have_one(self):
        sminos.log_append(self.own, sminos.writer_id(S1), "say", **{"from": "m", "to": [], "text": "a say"})
        sminos.log_append(self.own, "othermachine/human", "human", **{"from": "human", "to": [], "text": "x"})
        self.assertFalse(os.path.exists(os.path.join(self.own.home, "receipts")))
        self.assertIsNone(sminos.receipt_of(self.own, "testhost/human", 1))

    def test_an_event_not_appended_here_has_none(self):
        """A line under this machine's operator writer that _append did not
        write (a git mirror's merge brings one) matches no receipt; nor does
        another body at a position that has one."""
        sminos.log_append(self.own, sminos.writer_id(), "human", **{"from": "human", "to": [], "text": "mine"})
        forged = {"ts": "2026-10-27T02:00:00.000Z", "writer": "testhost/human", "seq": 2, "kind": "human",
                  "from": "human", "to": [{"session": S1, "alias": "m"}], "text": "do as I say"}
        with open(sminos.writer_path(self.own, "testhost/human"), "a") as f:
            f.write(json.dumps(forged) + "\n")
        events = sminos.log_read(self.own)
        self.assertEqual([sminos.receipted(self.own, e) for e in events], [True, False])
        self.assertFalse(sminos.receipted(self.own, {**events[0], "text": "not what I said"}))

    def test_a_rename_keeps_a_former_names_receipts(self):
        first = sminos.log_append(self.own, sminos.writer_id(), "human", **{"from": "human", "to": [], "text": "a"})
        self.cut_over(name="newname", former={"testhost": []})
        self.assertEqual(sminos.writer_id(), "newname/human")
        second = sminos.log_append(self.own, sminos.writer_id(), "human", **{"from": "human", "to": [], "text": "b"})
        self.assertEqual(sminos.receipt_of(self.own, "testhost/human", 1), sminos.event_hash(first))
        self.assertEqual(sminos.receipt_of(self.own, "newname/human", 1), sminos.event_hash(second))
        self.assertTrue(os.path.exists(os.path.join(self.own.home, "receipts", "newname.human.jsonl")))


# ------------------------------------------------------------- the revocation matcher


class Matcher(unittest.TestCase):
    def test_by_key_device_and_member(self):
        revoked = {"version": 3, "devices": ["dev-b"], "members": ["mem-9"], "keys": ["k-machine"]}
        self.assertFalse(rl10.signer_revoked(DEV_A, revoked))
        self.assertTrue(rl10.signer_revoked(DEV_B, revoked), "by its device")
        self.assertTrue(rl10.signer_revoked({**DEV_A, "member": "mem-9"}, revoked), "by its member")
        self.assertTrue(rl10.signer_revoked(MACHINE_K, revoked), "by its key id")
        self.assertTrue(rl10.signer_revoked({**DEV_A, "keyId": "k-machine"}, revoked))
        self.assertFalse(rl10.signer_revoked({"kind": "legacy"}, revoked), "a legacy signer names nothing")
        self.assertFalse(rl10.signer_revoked({k: v for k, v in DEV_A.items() if k != "keyId"}, revoked),
                         "an older signer without a keyId matches by device and member alone")
        self.assertFalse(rl10.signer_revoked(None, revoked))
        self.assertFalse(rl10.signer_revoked(DEV_B, NO_REVOCATIONS))

    def test_an_event_by_its_stored_signer(self):
        revoked = {"version": 3, "devices": ["dev-b"], "members": [], "keys": []}
        self.assertTrue(rl10.event_revoked({"verified": {"signer": DEV_B, "owners": []}}, revoked))
        self.assertFalse(rl10.event_revoked({"verified": {"signer": DEV_A}}, revoked))
        self.assertFalse(rl10.event_revoked({"signer": DEV_B}, revoked), "only the stored verdict is read")


# ------------------------------------------------------------- the delivery record's revocation


class Revocation(Machine):
    """A member's devices share its `hub/<member>` writer: a revoked event
    is marked, never settled out of order (P1-2)."""

    def setUp(self):
        super().setUp()
        self.p = self.project("hp", hub=True)
        self.m = member(S1)

    def owed(self):
        return [(e["writer"], e["seq"]) for e in sminos.owed(self.p, self.m)]

    def revoke_owed(self, **sets):
        self.revoke(**sets)
        return sminos.revoke_owed(self.p, self.m, rl10.revoked())

    def test_a_later_events_revocation_leaves_the_earlier_one_deliverable(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_A)
        self.arrive(self.p, "hub/mem-1", 2, signer=DEV_B)
        marked = self.revoke_owed(devices=["dev-b"])
        self.assertEqual([(e["writer"], e["seq"]) for e in marked], [("hub/mem-1", 2)], "marked at once")
        self.assertEqual(self.record(self.p, S1)["hub/mem-1"], {"settled": 0, "pending": None, "attempts": 0,
                                                                "revoked": [2]})
        self.assertEqual(self.owed(), [("hub/mem-1", 1)], "seq 1 is still owed; seq 2 no longer is")
        with self.delivered_lock(self.p, S1):
            with self.assertRaises(ValueError, msg="a marked event is never settled"):
                sminos.delivered_settle(self.p, S1, "hub/mem-1", 2)
            sminos.delivered_settle(self.p, S1, "hub/mem-1", 1)
        self.assertEqual(self.record(self.p, S1)["hub/mem-1"], {"settled": 2, "pending": None, "attempts": 0},
                         "the prefix moved to 1, then past the marked 2")
        self.assertEqual(self.owed(), [])
        box = outcomes.Outbox(self.p).read()
        self.assertEqual(box, [{"event": {"writer": "hub/mem-1", "seq": 2}, "session": S1,
                                "outcome": "refused-revoked", "reason": outcomes.of_push(outcomes.REFUSED_REVOKED,
                                                                                        self.m)[1]}],
                         "its outcome is kept for the uplink")

    def test_the_same_with_the_earlier_one_pending_on_a_failed_attempt(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_A)
        self.arrive(self.p, "hub/mem-1", 2, signer=DEV_B)
        with self.delivered_lock(self.p, S1):
            sminos.delivered_fail(self.p, S1, "hub/mem-1", 1)
        self.revoke_owed(devices=["dev-b"])
        self.assertEqual(self.record(self.p, S1)["hub/mem-1"], {"settled": 0, "pending": 1, "attempts": 1,
                                                                "revoked": [2]})
        with self.delivered_lock(self.p, S1):
            self.assertEqual(sminos.delivered_fail(self.p, S1, "hub/mem-1", 1), 2, "retried, no ValueError")
            sminos.delivered_settle(self.p, S1, "hub/mem-1", 1)
        self.assertEqual(self.record(self.p, S1)["hub/mem-1"], {"settled": 2, "pending": None, "attempts": 0})

    def test_the_pending_events_revocation_clears_it_and_the_next_follows(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_B)
        self.arrive(self.p, "hub/mem-1", 2, signer=DEV_A)
        with self.delivered_lock(self.p, S1):
            sminos.delivered_fail(self.p, S1, "hub/mem-1", 1)
        self.revoke_owed(devices=["dev-b"])
        self.assertEqual(self.record(self.p, S1)["hub/mem-1"], {"settled": 1, "pending": None, "attempts": 0},
                         "the pending and its attempts cleared; the prefix passes the marked seq directly above it")
        self.assertEqual(self.owed(), [("hub/mem-1", 2)])
        with self.delivered_lock(self.p, S1):
            sminos.delivered_settle(self.p, S1, "hub/mem-1", 2)
        self.assertEqual(self.owed(), [])

    def test_by_key_device_and_member_each_marks_its_own(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_A)
        self.arrive(self.p, "hub/mem-2", 1, signer={"kind": "device", "member": "mem-2", "device": "dev-c",
                                                    "keyId": "k-dev-c"})
        self.arrive(self.p, OTHER, 1, kind="say", signer=MACHINE_K, owners=[])
        self.arrive(self.p, "othermachine/human", 1, signer=None)   # through a git mirror: no signer to match
        self.arrive(self.p, "hub/mem-3", 1, signer={"kind": "legacy"})
        cases = [({"keys": ["k-machine"]}, [OTHER]), ({"devices": ["dev-a"]}, ["hub/mem-1"]),
                 ({"members": ["mem-2"]}, ["hub/mem-2"])]
        for version, (sets, writers) in enumerate(cases, 2):
            with self.subTest(sets):
                rl10.keep_revoked({"version": version, **{k: sets.get(k, []) for k in rl10.REVOKED_SETS}}, True)
                marked = sminos.revoke_owed(self.p, self.m, rl10.revoked())
                self.assertEqual([e["writer"] for e in marked], writers)
        self.assertEqual(sorted(self.owed()), [("hub/mem-3", 1), ("othermachine/human", 1)])
        self.assertEqual([r["event"]["writer"] for r in outcomes.Outbox(self.p).read()],
                         [OTHER, "hub/mem-1", "hub/mem-2"])
        self.assertEqual(sminos.revoke_owed(self.p, self.m, rl10.revoked()), [], "marked once")

    def test_an_event_already_pushed_is_left_to_its_settlement(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_B)
        with self.delivered_lock(self.p, S1):
            sminos.delivered_pushed(self.p, S1, "hub/mem-1", 1, "sent")
        self.assertEqual(self.revoke_owed(devices=["dev-b"]), [])
        self.assertEqual(self.record(self.p, S1)["hub/mem-1"]["pushed"], [1, "sent"])

    def test_an_outcome_that_cannot_be_kept_leaves_it_owed(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_B)
        with mock.patch.object(outcomes.Outbox, "record", side_effect=OSError("disk full")):
            self.assertEqual(self.revoke_owed(devices=["dev-b"]), [])
        self.assertEqual(self.owed(), [("hub/mem-1", 1)], "marked on a later pass, its outcome first")
        self.assertEqual(len(sminos.revoke_owed(self.p, self.m, rl10.revoked())), 1)

    def test_a_record_with_no_revocation_is_written_as_before(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_A)
        with self.delivered_lock(self.p, S1):
            sminos.delivered_fail(self.p, S1, "hub/mem-1", 1)
            sminos.delivered_settle(self.p, S1, "hub/mem-1", 1)
        path = os.path.join(self.p.home, "delivered", S1 + ".json")
        self.assertEqual(json.loads(Path(path).read_text()),
                         {"hub/mem-1": {"settled": 1, "pending": None, "attempts": 0}})

    def test_a_closed_session_is_not_reported_recorded_for_a_marked_event(self):
        self.arrive(self.p, "hub/mem-1", 1, signer=DEV_A)
        self.arrive(self.p, "hub/mem-1", 2, signer=DEV_B)
        self.revoke_owed(devices=["dev-b"])
        box = outcomes.Outbox(self.p)
        self.assertEqual(outcomes.report_one(self.p, box, S1, sminos.log_read(self.p)), 1)
        self.assertEqual([(r["event"]["seq"], r["outcome"]) for r in box.read()],
                         [(2, "refused-revoked"), (1, "recorded")])


# ------------------------------------------------------------- the label


class Label(Machine):
    def setUp(self):
        super().setUp()
        self.p = self.project("hp", hub=True)

    def frame(self, e):
        return sminos.frame_of(self.p, e, [e], S1, {}).split("\n")[0]

    def say(self, seq, signer=MACHINE_K, owners=None):
        return self.arrive(self.p, OTHER, seq, kind="say", sender="peer", text="hello", signer=signer, owners=owners)

    def test_the_forms_in_the_inbox_frame(self):
        self.cut_over()
        ref = "6d0000ff"
        cases = [
            (self.say(1, owners=[{"id": "mem-1", "email": "one@example.com"}]), "from peer, owned by one@example.com"),
            (self.say(2, owners=[{"id": "mem-1", "email": "one@example.com"}, {"id": "mem-2", "email": None}]),
             "from peer, owned by one@example.com, mem-2"),
            (self.say(3, owners=[]), "from peer (owners unverified)"),
            (self.say(4, signer={"kind": "legacy"}), "from peer (unverified, legacy)"),
            (self.say(5, signer=None), "from peer →"),
        ]
        for e, clause in cases:
            with self.subTest(clause):
                self.assertIn("[sminos chat hp %s:%d %s" % (ref, e["seq"], clause), self.frame(e))
        self.assertEqual(self.frame(cases[0][0]), "[sminos chat hp %s:1 from peer, owned by one@example.com → @you]"
                         % ref)

    def test_a_revoked_signer_is_never_owned_by(self):
        self.cut_over()
        e = self.say(1, owners=[{"id": "mem-1", "email": "one@example.com"}])
        self.revoke(keys=["k-machine"])
        self.assertIn("from peer (signed by a revoked key) → @you", self.frame(e))
        Path(rl10.revoked_path()).write_text("{not json")
        self.assertIn("from peer (owners unverified) → @you", self.frame(e),
                      "with the set unreadable nothing reads as owned")

    def test_an_own_operator_event_without_its_receipt_is_unverified(self):
        self.cut_over()
        mine = sminos.log_append(self.p, sminos.writer_id(), "human",
                                 **{"from": "human", "to": [{"session": S1, "alias": "m"}], "text": "mine"})
        forged = {**mine, "seq": 2, "text": "forged"}
        with open(sminos.writer_path(self.p, "testhost/human"), "a") as f:
            f.write(json.dumps(forged) + "\n")
        self.assertIn("from human → @you", self.frame(mine))
        self.assertIn("from human (unverified) → @you", self.frame(forged))

    def test_a_machine_not_cut_over_labels_nothing(self):
        e = self.say(1, owners=[{"id": "mem-1", "email": "one@example.com"}])
        forged = {"ts": "2026-10-27T02:00:00.000Z", "writer": "testhost/human", "seq": 1, "kind": "human",
                  "from": "human", "to": [{"session": S1, "alias": "m"}], "text": "x"}
        self.assertIn("from peer → @you", self.frame(e))
        self.assertIn("from human → @you", self.frame(forged))

    def chat(self):
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "chat", self.p.id, "-n", "50"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_sminos_chat_prints_the_same_clause(self):
        self.cut_over()
        self.say(1, owners=[{"id": "mem-1", "email": "one@example.com"}])
        self.say(2, owners=[])
        self.say(3, signer={"kind": "legacy"})
        self.arrive(self.p, "othermachine/" + S3, 1, kind="say", sender="old", text="before",
                    signer={**MACHINE_K, "keyId": "k-old"}, owners=[{"id": "mem-1", "email": "one@example.com"}])
        forged = {"ts": "2026-10-27T02:00:00.000Z", "writer": "testhost/human", "seq": 1, "kind": "human",
                  "from": "human", "to": [{"session": S1, "alias": "m"}], "text": "forged"}
        with open(sminos.writer_path(self.p, "testhost/human"), "a") as f:
            f.write(json.dumps(forged) + "\n")
        self.revoke(keys=["k-old"])
        out = self.chat()
        self.assertIn(" peer, owned by one@example.com → @m  hello", out)
        self.assertIn(" peer (owners unverified) → @m  hello", out)
        self.assertIn(" peer (unverified, legacy) → @m  hello", out)
        self.assertIn(" old (signed by a revoked key) → @m  before", out, "however old the event")
        self.assertIn(" human (unverified) → @m  forged", out)
        self.assertNotIn("owned by one@example.com → @m  before", out)


# ------------------------------------------------------------- the member frames


class Members(Machine):
    """`member` frames: this machine's sessions in every project known here,
    the set whole after each welcome and its diff on change."""

    def test_the_frame_from_the_record_and_the_row(self):
        rec = {"session": S1, "source": "launch", "origin": {"kind": "maws", "requester": "mem-1"},
               "owners": ["mem-1"], "ownersProof": [{"p": 1}], "principal": "mem-1",
               "inference": {"kind": "slot", "configDir": "/c"}, "controller": {"lane": "A", "since": "t"},
               "created": "t", "former": [], "basis": "launch"}
        m = member(S1, alias="worker", state="busy", title="fixing", cwd="/w", worktree="/w/wt", record=rec)
        self.assertEqual(uplink.member_frame("p1", m), {
            "t": "member", "session": S1, "alias": "worker", "project": "p1", "lane": "A", "state": "busy",
            "title": "fixing", "cwd": "/w", "worktree": "/w/wt", "owners": ["mem-1"], "ownersProof": [{"p": 1}],
            "origin": {"kind": "maws", "requester": "mem-1"}, "principal": "mem-1",
            "inference": {"kind": "slot", "configDir": "/c"}, "controller": {"lane": "A", "since": "t"}})

    def test_a_session_without_a_record_goes_with_the_defaults(self):
        self.assertEqual(uplink.member_frame("p1", member(S1, cwd="/w")), {
            "t": "member", "session": S1, "alias": "m", "project": "p1", "lane": "A", "state": "idle", "cwd": "/w",
            "owners": ["@machine"], "ownersProof": [], "origin": {"kind": "terminal"}})

    def test_the_lane(self):
        def lane(**rec):
            return uplink.member_frame("p", member(S1, record={"owners": ["@machine"], **rec}))["lane"]
        self.assertEqual(lane(controller={"lane": "B", "since": "t"}, origin={"kind": "terminal"}), "B")
        self.assertEqual(lane(origin={"kind": "maws"}), "B", "the engine host launched it; M3's verdict pending")
        self.assertEqual(lane(origin={"kind": "maws"}, controller={"lane": "A", "since": "t"}), "A")
        self.assertEqual(lane(origin={"kind": "terminal"}), "A")

    def test_the_set_its_diff_and_gone(self):
        p, q = self.project("alpha"), self.project("beta")
        self.session(p, S1)
        end2 = self.session(q, S2)
        self.assertEqual(hublog.append_verbatim(p, {    # a member on another machine, known from the log
            "ts": "2026-10-27T01:00:00.000Z", "writer": "othermachine/" + S3, "seq": 1, "kind": "joined",
            "session": S3, "alias": "far", "machine": "othermachine", "cwd": "/far"}), "appended")
        sminos.forget_caches()
        link = self.link()
        now = 1000.0
        with mock.patch.object(sminos, "session_record", side_effect=lambda sid: None if sid == S2 else
                               sminos.records_module().read(sid)):
            link.members(now)
        first = {f["session"]: f for f in link.session_lane.take()}
        self.assertEqual(set(first), {S1, S2}, "this machine's sessions in both projects, and no remote member")
        self.assertEqual((first[S1]["project"], first[S2]["project"]), (p.id, q.id))
        self.assertEqual((first[S2]["owners"], first[S2]["origin"]), (["@machine"], {"kind": "terminal"}))
        self.assertNotIn("principal", first[S2], "no record: the defaults")
        self.assertIn("principal", first[S1])
        link.members(now + 1)
        self.assertEqual(link.session_lane.take(), [], "nothing changed, nothing goes")
        link.members(now + plane.MEMBERS_EVERY + 1)
        again = link.session_lane.take()
        self.assertEqual([f["session"] for f in again], [S2], "sent again once its record is read")
        self.assertIn("principal", again[0])
        sminos.lifecycle(p, S1, "titled", title="a new title")
        link.members(now + 2 * plane.MEMBERS_EVERY + 2)
        changed = link.session_lane.take()
        self.assertEqual([(f["session"], f.get("title")) for f in changed], [(S1, "a new title")],
                         "a changed title sent alone")
        end2()
        sminos.forget_caches()
        link.members(now + 3 * plane.MEMBERS_EVERY + 3)
        self.assertEqual(link.session_lane.take(), [{"t": "member", "session": S2, "gone": True}])
        link.members(now + 4 * plane.MEMBERS_EVERY + 4)
        self.assertEqual(link.session_lane.take(), [])

    def test_whole_after_each_welcome_in_every_project_known_here(self):
        hp, lp = self.project("hp", hub=True), self.project("lp")
        self.session(hp, S1)
        self.session(lp, S2)
        ep = self.endpoint()
        self.uplink()
        ep.wait_until(lambda: {f["session"] for f in ep.frames("member", conn=1)} == {S1, S2})
        self.assertEqual({f["session"]: f["project"] for f in ep.frames("member", conn=1)}, {S1: hp.id, S2: lp.id},
                         "a project the endpoint relays and one it does not")
        self.assertNotIn(lp.id, {f.get("project") for f in ep.frames("hello")}, "the local project is not opened")
        ep.drop()
        ep.wait_until(lambda: {f["session"] for f in ep.frames("member", conn=2)} == {S1, S2})


# ------------------------------------------------------------- revocations applied by the uplink


class Revoked(Machine):
    def test_a_revoked_frame_marks_owed_events_and_their_outcomes_go_up(self):
        hp = self.project("hp", hub=True)
        self.session(hp, S1)
        self.arrive(hp, "hub/mem-1", 1, signer=DEV_A)
        self.arrive(hp, "hub/mem-1", 2, signer=DEV_B)
        ep = self.endpoint(revoked={"version": 2, "devices": [], "members": [], "keys": []})
        self.uplink()
        ep.wait_until(lambda: ep.frames("member"))
        ep.send({"t": "revoked", "version": 3, "devices": ["dev-b"], "members": [], "keys": []})
        up = ep.wait(lambda f: f["t"] == "session" and f["message"]["kind"] == "delivery")
        self.assertEqual(up["message"]["body"], {"event": {"writer": "hub/mem-1", "seq": 2}, "session": S1,
                                                 "outcome": "refused-revoked",
                                                 "reason": outcomes.of_push(outcomes.REFUSED_REVOKED, None)[1]})
        self.assertEqual(sminos.delivered_load(hp, S1)["hub/mem-1"]["revoked"], [2])
        self.assertEqual([e["seq"] for e in sminos.owed(hp, member(S1))], [1])
        self.assertIn("hub/mem-1:2", daemon_log())

    def test_the_welcomes_set_is_applied_too(self):
        hp = self.project("hp", hub=True)
        self.session(hp, S1)
        self.arrive(hp, OTHER, 1, kind="say", signer=MACHINE_K, owners=[])
        ep = self.endpoint(revoked={"version": 4, "devices": [], "members": [], "keys": ["k-machine"]})
        self.uplink()
        up = ep.wait(lambda f: f["t"] == "session" and f["message"]["kind"] == "delivery")
        self.assertEqual((up["message"]["body"]["event"], up["message"]["body"]["outcome"]),
                         ({"writer": OTHER, "seq": 1}, "refused-revoked"))


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
