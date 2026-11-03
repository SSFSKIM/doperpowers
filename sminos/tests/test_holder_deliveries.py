#!/usr/bin/env python3
"""The receipts of deliveries to a MAWS lane B observer's process, and the
process mode that decides whether a delivery prepares one (O12 M4b):
sminos_holder_deliveries, driven through the real deliverers —
`deliver_next` (the sender's fast path and the daemon's retries alike),
`deliver_verdict` (the uplink's words verdict) and `send`'s member path.

What the bridge child and mod do (T6) is played here by calling the
functions they call: `activate` before the hello, `admit` when the mod
admitted a model request carrying a receipt's row, `release` when a stopped
receipt's hold ended in the same launch. Sessions are the engine's registry
records of live `sleep` processes, each with an inbox socket served by
inbox_standin.py; a process "restarts" as a new `sleep` under the same
session id.

Hermetic: every test has its own HOME and SMINOS_HOME under one temporary
directory; CLAUDE_CONFIG_DIR is unset (the registry is HOME's).
Run: python3 -B sminos/tests/test_holder_deliveries.py
"""

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = tempfile.mkdtemp(prefix="smh.", dir="/tmp")   # short: a Unix socket's path is bounded
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR",
            "SMINOS_HOLDER_ACTIVATION_GRACE", "MAWS_HOLDER_SOCKET"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))

import sminos  # noqa: E402
import sminos_control as control  # noqa: E402
import sminos_holder_deliveries as hd  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402

S1 = "4b000001-0000-4000-8000-0000000000b1"
S2 = "4b000002-0000-4000-8000-0000000000b2"
S3 = "4b000003-0000-4000-8000-0000000000b3"
OTHER = "othermachine/4b0000ff-0000-4000-8000-0000000000ff"
OTHER2 = "othermachine/4b0000fe-0000-4000-8000-0000000000fe"
DEV_A = {"kind": "device", "member": "mem-1", "device": "dev-a", "keyId": "k-dev-a"}
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"


def wait_for(pred, timeout=20, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


def member(sid):
    return sminos.Member(session=sid, short=sid[:8], alias="m", name_source="derived", machine="testhost",
                         local=True, state="idle", state_age=None, charge="", charge_source="", status="", by="",
                         worktree="", seat=None)


class Rig(unittest.TestCase):
    """A fresh installation per test: `testhost` of org-1, a hub project
    `hp` and a local project `lp`."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        self.home = home
        self.inboxes = {}
        self.procs = {}
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json"),
                          {"hub": "http://127.0.0.1:9", "org": "org-1", "machine": "testhost", "client_id": "c",
                           "client_secret": "s", "key": KEY, "former": {}, "enrolled": "2026-10-01T00:00:00Z"})
        sminos.forget_caches()
        rl10._SAID.update(find=None, revoked=None)
        self.hp = self.project("hp", hub=True)
        self.lp = self.project("lp")
        self.bridge = []
        patcher = mock.patch.object(control, "deliver", side_effect=lambda *a: self.bridge.append(a) or None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def project(self, name, hub=False):
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
        sminos.project_path(project, "log")
        return project

    def launch(self, sid, project=None):
        """A live process of the session (a new one each call: a resume), its
        inbox served; the process's pid. The one before it, if any, ends."""
        self.end(sid)
        p = subprocess.Popen(["sleep", "600"])
        sock = os.path.join(self.home, "in-%s-%d.sock" % (sid[:4], p.pid))
        received = self.inboxes.setdefault(sid, os.path.join(self.home, "in-%s.received" % sid[:4]))
        Path(received).touch()
        server = subprocess.Popen([sys.executable, "-B", str(HERE / "inbox_standin.py"), sock, received])
        wait_for(lambda: os.path.exists(sock), timeout=10)
        path = os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % p.pid)
        with open(path, "w") as f:
            json.dump({"pid": p.pid, "sessionId": sid, "name": sid[:4], "nameSource": "derived",
                       "cwd": (project or self.hp).root, "kind": "interactive", "status": "idle",
                       "messagingSocketPath": sock}, f)
        self.procs[sid] = (p, server, path)
        self.addCleanup(self.end, sid)
        sminos.forget_caches()
        return p.pid

    def end(self, sid):
        held = self.procs.pop(sid, None)
        if held is None:
            return
        p, server, path = held
        for proc in (p, server):
            if proc.poll() is None:
                proc.kill()
                proc.wait(5)
        if os.path.exists(path):
            os.unlink(path)
        sminos.forget_caches()

    def inbox(self, sid):
        try:
            lines = Path(self.inboxes[sid]).read_text().splitlines()
        except (KeyError, FileNotFoundError):
            return []
        return [json.loads(line)["message"]["content"] for line in lines if line.strip()]

    def arrive(self, writer, seq, project=None, kind="say", to=S1, signer=None, **fields):
        """An event from outside (another machine's, or the hub's)."""
        e = {"ts": "2026-11-02T01:00:%02d.000Z" % seq, "writer": writer, "seq": seq, "kind": kind,
             "from": fields.pop("sender", "alice"), "to": [{"session": to, "alias": "m"}],
             "text": fields.pop("text", "message %s:%d" % (writer, seq)), **fields}
        if signer is not None:
            e["verified"] = {"signer": signer}
        self.assertEqual(hublog.append_verbatim(project or self.hp, e), "appended")
        return e

    def deliver(self, sid=S1, project=None):
        return sminos.deliver_next(project or self.hp, member(sid))

    def record(self, sid=S1, project=None):
        return sminos.delivered_load(project or self.hp, sid)

    def settled(self, writer, sid=S1, project=None):
        return self.record(sid, project).get(writer, {}).get("settled", 0)

    def ids(self, sid=S1):
        """The receipt ids each inbox frame carries."""
        return [[rid for rid, _ in hd.markers(text)] for text in self.inbox(sid)]

    def receipt(self, e, sid=S1, project=None):
        path = hd._receipt_path(hd.key_hash((project or self.hp).id, sid, e["writer"], e["seq"]))
        try:
            return json.loads(Path(path).read_text())
        except FileNotFoundError:
            return None

    def outbox(self, project=None):
        return [(r["event"]["writer"], r["event"]["seq"], r["outcome"])
                for r in outcomes.Outbox(project or self.hp).read()]

    def gate(self, pid, sid=S1, launch="launch-1", retained=()):
        rec = hd.activate(pid, launch, sid, retained=retained)
        self.assertEqual(rec["mode"], "gate")
        return rec


    def said(self, words):
        """The daemon.log lines that hold `words`."""
        try:
            text = Path(sminos.root(), "daemon.log").read_text()
        except FileNotFoundError:
            return []
        return [line for line in text.splitlines() if words in line]

    def cut_over(self, devices=()):
        """This machine cut over to its endpoint, `devices` revoked."""
        sminos.write_json(rl10.identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": {}, "ref": "r",
            "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z", "build": "b"})
        self.revoke(devices)
        sminos.forget_caches()

    def revoke(self, devices, version=1):
        os.makedirs(os.path.dirname(rl10.revoked_path()), exist_ok=True)
        rl10.keep_revoked({"version": version, "devices": list(devices), "members": [], "keys": []}, True)


# ------------------------------------------------------------- the process mode


class Mode(Rig):
    def test_a_process_with_no_record_is_handed_off_legacy_and_recorded_so(self):
        pid = self.launch(S1)
        e = self.arrive(OTHER, 1)
        got = self.deliver()
        self.assertEqual([o for _, o in got["outcomes"]], ["sent"], "today's handoff settlement")
        self.assertEqual(self.settled(OTHER), 1)
        self.assertEqual(self.ids(), [[]], "no marker: no receipt")
        self.assertIsNone(self.receipt(e))
        proc = hd.process(pid)
        rec = hd.read_mode(proc)
        self.assertEqual((rec["mode"], rec["by"]), ("legacy", "handoff"))
        path = hd._mode_path(proc)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(hd.home()).st_mode), 0o700)
        self.assertEqual(hd.activate(pid, "launch-1", S1)["mode"], "legacy",
                         "the first handoff won: activation cannot enable receipts partway through the process")

    def test_activation_first_makes_every_later_delivery_prepare_a_receipt(self):
        pid = self.launch(S1)
        rec = self.gate(pid)
        self.assertEqual((rec["launch"], rec["by"], rec["session"]), ("launch-1", "activation", S1))
        self.assertEqual(hd.handoff(pid, S1), "gate", "a deliverer reads the record alone")

    def test_reload_child_restart_and_clear_never_change_the_mode(self):
        pid = self.launch(S1)
        self.gate(pid)
        self.assertEqual(hd.activate(pid, "launch-1", S2)["mode"], "gate", "a /clear's activation")
        self.assertEqual(hd.observer_upgrade(pid)["mode"], "gate", "an M4b reload stays gate")
        legacy = self.launch(S2)
        hd.observer_upgrade(legacy)
        self.assertEqual(hd.activate(legacy, "launch-2", S2)["mode"], "legacy")

    def test_every_session_a_gate_process_serves_is_marked(self):
        # A /clear's activation finds the record there: the new session is
        # marked too (C5's grace for its later resume), the mode and launch kept.
        pid = self.launch(S1)
        rec = self.gate(pid)
        self.assertFalse(hd._served(S2))
        again = hd.activate(pid, "launch-1", S2)
        self.assertEqual(again, rec, "the record as it was")
        self.assertTrue(hd._served(S2), "the session it serves after the /clear is marked")
        legacy = self.launch(S3)
        hd.observer_upgrade(legacy)
        hd.activate(legacy, "launch-2", S3)
        self.assertFalse(hd._served(S3), "a legacy process's session is not one a gate process served")

    def test_an_existing_process_no_observer_served_is_recorded_so(self):
        pid = self.launch(S1)
        rec = hd.observer_upgrade(pid, by="existing")
        self.assertEqual((rec["mode"], rec["by"]), ("legacy", "existing"))

    def test_a_new_process_may_choose_again(self):
        first = self.launch(S1)
        self.arrive(OTHER, 1)
        self.deliver()
        self.assertEqual(hd.read_mode(hd.process(first))["mode"], "legacy")
        second = self.launch(S1)
        self.assertEqual(self.gate(second)["mode"], "gate", "a resume in a new process is a new choice")

    def test_the_first_handoff_races_activation_and_the_lock_decides(self):
        """Activation and the first legacy handoff of one process, from other
        processes at once, many times over fresh processes: each process ends
        with one mode, and each side saw it."""
        for round_ in range(6):
            with self.subTest(round=round_):
                pid = self.launch(S1)
                code = ("import sys; sys.path.insert(0, %r); import sminos_holder_deliveries as hd\n"
                        "print(hd.handoff(%d, %r) if sys.argv[1] == 'h' else hd.activate(%d, 'L', %r)['mode'])"
                        % (str(SCRIPTS), pid, S1, pid, S1))
                # No grace: an earlier round's activation marked the session served.
                env = {**os.environ, "SMINOS_HOLDER_ACTIVATION_GRACE": "0"}
                procs = [subprocess.Popen([sys.executable, "-B", "-c", code, side], stdout=subprocess.PIPE, text=True,
                                          env=env)
                         for side in ("h", "a", "h", "a")]
                seen = {p.communicate(timeout=30)[0].strip() for p in procs}
                final = hd.read_mode(hd.process(pid))["mode"]
                self.assertEqual(seen, {final}, "every side saw the one mode the lock's winner wrote")

    def test_an_unreadable_or_unknown_mode_fails_closed(self):
        e = self.arrive(OTHER, 1)
        for body in ("{not json", json.dumps({"v": 1, "mode": "maybe"})):
            with self.subTest(body=body):
                pid = self.launch(S1)
                Path(hd._mode_path(hd.process(pid))).write_text(body)
                got = self.deliver()
                self.assertTrue(got["outcomes"][0][1].startswith("held:"), got)
                self.assertEqual(self.inbox(S1), [], "nothing handed off")
                w = self.record().get(OTHER, {})
                self.assertEqual((w.get("settled", 0), w.get("pending"), w.get("attempts", 0)), (0, None, 0),
                                 "owed, no attempt counted")
                with self.assertRaises(hd.Unreadable, msg="the gate is not enabled"):
                    hd.activate(pid, "launch-1", S1)
                self.assertTrue(control_refuses(S1, e), "push_live hands nothing off either")

    def test_an_m4a_observer_seen_by_m4b_stays_legacy_for_settlement(self):
        """The split's upgrade: a process whose M4a observer was running is
        recorded legacy before any delivery or activation; its deliveries are
        handed off and settled as before, never retroactively owed."""
        pid = self.launch(S1)
        self.assertEqual(hd.observer_upgrade(pid)["mode"], "legacy")
        self.assertEqual(hd.read_mode(hd.process(pid))["by"], "observer")
        self.assertEqual(hd.activate(pid, "launch-1", S1, observer_started=True)["mode"], "legacy")
        self.assertEqual(hd.activate(pid, "launch-1", S1)["mode"], "legacy", "not promoted later either")
        e = self.arrive(OTHER, 1)
        self.deliver()
        self.assertEqual((self.settled(OTHER), self.ids()), (1, [[]]))
        self.assertIsNone(self.receipt(e))
        relaunched = self.launch(S1)
        self.gate(relaunched)
        e2 = self.arrive(OTHER, 2)
        self.assertEqual([o for _, o in self.deliver()["outcomes"]], [sminos.HOLDER_AWAITING],
                         "relaunched, receipts are enabled")
        self.assertIsNotNone(self.receipt(e2))


def control_refuses(sid, e):
    """push_live's own boundary: a log-backed handoff to a process whose mode
    is not legacy, without a receipt, reaches nothing."""
    peer = sminos.peer_for_session(sid)
    try:
        control.push_live(peer, sid, "text", e, None)
    except sminos.SendFailed as err:
        return err.phase == "before"
    return False


# ------------------------------------------------------------- the receipt


class Receipt(Rig):
    def setUp(self):
        super().setUp()
        self.pid = self.launch(S1)
        self.gate(self.pid)

    def test_the_receipt_is_durable_before_the_inbox_write_and_its_id_rides_the_text(self):
        e = self.arrive(OTHER, 1, text="hello there")
        seen = {}
        real = sminos.send_frame

        def send(path, text, *a, **k):
            seen["receipt"] = self.receipt(e)
            return real(path, text, *a, **k)
        with mock.patch.object(sminos, "send_frame", side_effect=send):
            got = self.deliver()
        self.assertIsNotNone(seen.get("receipt"), "prepared before the inbox was written")
        self.assertEqual(seen["receipt"]["attempt"]["state"], "prepared")
        self.assertEqual([o for _, o in got["outcomes"]], [sminos.HOLDER_AWAITING], "pending, not PUSHED")
        self.assertEqual(got["delivered"], 0)
        r = self.receipt(e)
        self.assertEqual(r["key"], {"project": self.hp.id, "session": S1, "writer": OTHER, "seq": 1})
        self.assertEqual(r["hash"], sminos.event_hash(e))
        self.assertEqual((r["attempt"]["n"], r["attempt"]["state"], r["attempt"]["launch"], r["attempt"]["body"]),
                         (1, "pushed", "launch-1", "full"))
        self.assertEqual(stat.S_IMODE(os.stat(hd._receipt_path(r["id"].split(".")[0])).st_mode), 0o600)
        frame = self.inbox(S1)[0]
        body = frame.split("\n", 1)[1]
        self.assertTrue(body.startswith(hd.marker(r["id"], 1) + "\n"), "the marker is the envelope body's first line")
        self.assertEqual(hd.markers(frame), [(r["id"], 1)], "naming the receipt and its attempt")
        self.assertIn("hello there", frame)
        self.assertEqual(self.bridge, [], "a gate process's delivery goes to its inbox alone")
        self.assertEqual(self.settled(OTHER), 0, "the cursor waits for the admission")
        self.assertEqual(self.outbox(), [], "no outcome before the settlement")

    def test_handoff_before_an_arm_settles_only_after_its_admission(self):
        """Handed off while nothing fences; the arm comes; the request that
        takes the row in is admitted after it (proceed): settled then, not
        at the handoff."""
        e = self.arrive(OTHER, 1)
        self.deliver()
        rid = self.receipt(e)["id"]
        for _ in range(3):
            self.deliver()
        self.assertEqual(self.settled(OTHER), 0)
        self.assertEqual(hd.admit([rid], self.pid, S1), {"ok": True, "receipts": {rid: "admitted"}})
        self.assertEqual(self.settled(OTHER), 0, "the admission is recorded; the reconciler settles it")
        got = self.deliver()
        self.assertEqual([o for _, o in got["outcomes"]], ["sent"])
        self.assertEqual(self.settled(OTHER), 1)
        self.assertEqual(self.outbox(), [(OTHER, 1, "delivered")], "the outside-origin outcome, once")
        self.assertIsNone(self.receipt(e), "a settled receipt is removed")
        self.assertEqual(len(self.inbox(S1)), 1, "pushed once")
        self.assertEqual(hd.admit([rid], self.pid, S1)["receipts"][rid], "gone", "a late replay changes nothing")

    def test_handoff_during_a_fence_waits_without_flooding_or_spending_attempts(self):
        e = self.arrive(OTHER, 1)
        for _ in range(sminos.DELIVERY_ATTEMPTS + 5):
            got = self.deliver()
            self.assertEqual([o for _, o in got["outcomes"]], [sminos.HOLDER_AWAITING])
        self.assertEqual(len(self.inbox(S1)), 1, "one inbox frame for every pass")
        w = self.record().get(OTHER, {"settled": 0, "pending": None, "attempts": 0})
        self.assertEqual((w["settled"], w["pending"], w["attempts"]), (0, None, 0), "untouched: owed, no attempt")
        self.assertEqual(self.receipt(e)["attempt"]["n"], 1, "every pass saw the same attempt")

    def test_a_stopped_receipt_stays_owed_and_its_ended_process_is_pushed_nothing(self):
        e = self.arrive(OTHER, 1)
        self.deliver()
        self.end(S1)   # the host's stop, then its reap
        got = self.deliver()
        self.assertEqual([o for _, o in got["outcomes"]], [sminos.HOLDER_AWAITING],
                         "no live process: owed for a later launch, never settled `recorded`")
        self.assertEqual(self.settled(OTHER), 0)
        self.assertIsNotNone(self.receipt(e))
        self.assertEqual(self.outbox(), [])

    def test_a_writer_stops_at_its_first_pending_receipt(self):
        e1, e2 = self.arrive(OTHER, 1), self.arrive(OTHER, 2)
        got = self.deliver()
        self.assertEqual([(ev["seq"], o) for ev, o in got["outcomes"]], [(1, sminos.HOLDER_AWAITING)])
        self.assertEqual(got["pending"], 2)
        self.assertIsNone(self.receipt(e2), "nothing prepared behind a pending receipt")
        hd.admit([self.receipt(e1)["id"]], self.pid, S1)
        got = self.deliver()
        self.assertEqual([(ev["seq"], o) for ev, o in got["outcomes"]], [(1, "sent"), (2, sminos.HOLDER_AWAITING)])
        self.assertEqual(len(self.inbox(S1)), 2)
        self.assertEqual(self.ids()[1], [self.receipt(e2)["id"]])

    def test_two_writers_and_several_receipts_in_one_request(self):
        e1, e2 = self.arrive(OTHER, 1), self.arrive(OTHER2, 1)
        self.deliver()
        ids = [self.receipt(e1)["id"], self.receipt(e2)["id"]]
        self.assertEqual(sorted(sum(self.ids(), [])), sorted(ids), "a receipt per writer's event")
        self.assertEqual(len(set(ids)), 2)
        got = hd.admit(ids, self.pid, S1)
        self.assertEqual(got["receipts"], {ids[0]: "admitted", ids[1]: "admitted"})
        self.deliver()
        self.assertEqual((self.settled(OTHER), self.settled(OTHER2)), (1, 1))
        self.assertEqual(sorted(self.outbox()), sorted([(OTHER, 1, "delivered"), (OTHER2, 1, "delivered")]))

    def test_concurrent_deliverers_push_once(self):
        e = self.arrive(OTHER, 1)
        code = ("import sys; sys.path.insert(0, %r); import sminos\n"
                "m = sminos.Member(session=%r, short='x', alias='m', name_source='derived', machine='testhost',"
                " local=True, state='idle', state_age=None, charge='', charge_source='', status='', by='',"
                " worktree='', seat=None)\n"
                "print(sminos.deliver_next(sminos.resolve_project(%r), m)['outcomes'][0][1])"
                % (str(SCRIPTS), S1, self.hp.root))
        procs = [subprocess.Popen([sys.executable, "-B", "-c", code], stdout=subprocess.PIPE, text=True)
                 for _ in range(4)]
        outs = [p.communicate(timeout=60)[0].strip() for p in procs]
        self.assertEqual(outs, [sminos.HOLDER_AWAITING] * 4)
        self.assertEqual(self.ids(), [[self.receipt(e)["id"]]], "one push, one receipt")

    def test_an_admission_is_checked_against_the_receipt(self):
        e = self.arrive(OTHER, 1)
        self.deliver()
        rid = self.receipt(e)["id"]
        forged = rid.split(".")[0] + ".0123456789abcdef"
        self.assertEqual(hd.admit([forged, "not-an-id", None], self.pid, S1)["receipts"],
                         {forged: "unknown", "not-an-id": "unknown", "None": "unknown"}, "text alone settles nothing")
        self.assertEqual(hd.admit([rid], self.pid, S2)["receipts"], {rid: "foreign"},
                         "an old child's report after a /clear is another session's")
        other = self.launch(S2)
        self.assertEqual(hd.admit([rid], other, S1)["code"], "legacy", "a process that takes no receipts reports none")
        self.deliver()
        self.assertEqual(self.settled(OTHER), 0)


# ------------------------------------------------------------- restarts


class Restart(Rig):
    def setUp(self):
        super().setUp()
        self.pid = self.launch(S1)
        self.gate(self.pid)

    def test_at_prepare_the_next_pass_pushes_the_same_id(self):
        e = self.arrive(OTHER, 1)
        with mock.patch.object(sminos, "send_frame", side_effect=SystemExit("killed")):
            with self.assertRaises(SystemExit):
                self.deliver()
        r = self.receipt(e)
        self.assertEqual((r["attempt"]["state"], self.inbox(S1)), ("prepared", []))
        self.deliver()
        self.assertEqual(self.ids(), [[r["id"]]], "pushed once the deliverer is back, the same id")
        self.assertEqual(self.receipt(e)["attempt"]["n"], 1)

    def test_a_push_that_failed_before_it_reached_is_an_attempt_and_retried(self):
        e = self.arrive(OTHER, 1)
        with mock.patch.object(sminos, "send_frame", side_effect=sminos.SendFailed("before", "refused")):
            got = self.deliver()
        self.assertTrue(got["outcomes"][0][1].startswith("failed:"))
        self.assertEqual(self.record()[OTHER]["attempts"], 1)
        self.deliver()
        self.assertEqual(self.ids(), [[self.receipt(e)["id"]]])

    def test_at_the_inbox_write_the_push_is_made_again_under_the_same_id(self):
        """At least once: the frame went, the deliverer died before it noted
        so; the next pass pushes the same attempt again."""
        e = self.arrive(OTHER, 1)
        with mock.patch.object(hd, "pushed", side_effect=SystemExit("killed")):
            with self.assertRaises(SystemExit):
                self.deliver()
        self.deliver()
        rid = self.receipt(e)["id"]
        self.assertEqual(self.ids(), [[rid], [rid]])
        self.assertEqual(self.receipt(e)["attempt"]["n"], 1)
        self.deliver()
        self.assertEqual(len(self.inbox(S1)), 2, "then never again")
        self.assertEqual(self.settled(OTHER), 0)

    def test_at_admission_the_report_is_replayed_and_settles_once(self):
        e = self.arrive(OTHER, 1)
        self.deliver()
        rid = self.receipt(e)["id"]
        with mock.patch.object(sminos, "nudge_daemon", side_effect=SystemExit("killed")):
            with self.assertRaises(SystemExit):
                hd.admit([rid], self.pid, S1)
        self.assertEqual(hd.admit([rid], self.pid, S1)["receipts"], {rid: "admitted"}, "replayed")
        self.deliver()
        self.deliver()
        self.assertEqual((self.settled(OTHER), self.outbox(), len(self.inbox(S1))), (1, [(OTHER, 1, "delivered")], 1))

    def test_at_settlement_the_cursor_and_the_outcome_agree(self):
        e = self.arrive(OTHER, 1)
        self.deliver()
        hd.admit([self.receipt(e)["id"]], self.pid, S1)
        # Killed after the outcome was kept, before the cursor moved.
        with mock.patch.object(sminos, "delivered_settle", side_effect=SystemExit("killed")):
            with self.assertRaises(SystemExit):
                self.deliver()
        self.assertEqual((self.settled(OTHER), self.outbox()), (0, [(OTHER, 1, "delivered")]))
        # Killed after the cursor moved, before the receipt was removed.
        with mock.patch.object(hd, "settled", side_effect=SystemExit("killed")):
            with self.assertRaises(SystemExit):
                self.deliver()
        self.assertEqual(self.settled(OTHER), 1)
        self.assertEqual({o for _, _, o in self.outbox()}, {"delivered"}, "recorded again at most, the same outcome")
        self.assertIsNotNone(self.receipt(e), "left behind")
        self.assertEqual(self.deliver()["outcomes"], [], "nothing owed, nothing pushed")
        self.assertEqual(len(self.inbox(S1)), 1)
        self.assertEqual(hd.sweep(sminos.known_project), (0, 1), "the sweep removes it")
        self.assertIsNone(self.receipt(e))


# ------------------------------------------------------------- retries


class Retry(Rig):
    def setUp(self):
        super().setUp()
        self.pid = self.launch(S1)
        self.gate(self.pid)

    def stopped(self):
        e = self.arrive(OTHER, 1, text="the body")
        self.deliver()
        return e, self.receipt(e)["id"]

    def test_after_resume_the_same_id_wakes_a_retained_row(self):
        e, rid = self.stopped()
        resumed = self.launch(S1)
        self.gate(resumed, launch="launch-2", retained=[rid])
        self.deliver()
        frames = self.inbox(S1)
        self.assertEqual(self.ids(), [[rid], [rid]], "the same id")
        self.assertNotIn("the body", frames[1], "a wake referring to the kept row, not the body again")
        self.assertIn(hd.marker(rid, 2, "wake"), frames[1], "its marker says it is a wake")
        self.assertEqual(hd.markers(frames[1]), [(rid, 2)])
        self.assertIn(sminos.event_ref(e), frames[1])
        a = self.receipt(e)["attempt"]
        self.assertEqual((a["n"], a["pid"], a["launch"], a["body"]), (2, resumed, "launch-2", "wake"))
        self.deliver()
        self.assertEqual(len(self.inbox(S1)), 2, "one retry per launch")
        hd.admit([rid], resumed, S1)
        self.deliver()
        self.assertEqual((self.settled(OTHER), self.outbox()), (1, [(OTHER, 1, "delivered")]))

    def test_after_resume_without_the_row_the_full_body_goes_again(self):
        e, rid = self.stopped()
        resumed = self.launch(S1)
        self.gate(resumed, launch="launch-2")   # a rewind dropped the row
        self.deliver()
        self.assertEqual(self.ids(), [[rid], [rid]])
        self.assertIn("the body", self.inbox(S1)[1])
        self.assertEqual(self.receipt(e)["attempt"]["body"], "full")

    def test_a_resumed_legacy_process_takes_it_at_handoff(self):
        e, rid = self.stopped()
        resumed = self.launch(S1)
        hd.observer_upgrade(resumed)
        got = self.deliver()
        self.assertEqual([o for _, o in got["outcomes"]], ["sent"])
        self.assertEqual(self.ids()[1], [], "today's frame")
        self.assertEqual(self.settled(OTHER), 1)
        self.assertIsNone(self.receipt(e))

    def test_a_stopped_receipt_in_a_living_launch_waits_for_its_release(self):
        e, rid = self.stopped()
        for _ in range(3):
            self.deliver()
        self.assertEqual(len(self.inbox(S1)), 1, "a reconnect's welcome is no release: nothing until the mod says")
        item = {"id": rid, "attempt": 1, "present": True}
        self.assertEqual(hd.release([item], self.pid, "launch-2", S1)["code"], "launch")
        self.assertEqual(hd.release([item], self.pid, "launch-1", S2)["receipts"], {rid: "foreign"})
        self.assertEqual(hd.release([item], self.pid, "launch-1", S1)["receipts"], {rid: "released"})
        self.deliver()
        self.assertEqual(self.ids(), [[rid], [rid]], "retried once, the same id")
        self.assertNotIn("the body", self.inbox(S1)[1], "a wake: its row is in the conversation")
        self.deliver()
        self.assertEqual(len(self.inbox(S1)), 2, "a newer hold keeps it pending until another release")
        hd.release([{"id": rid, "attempt": 2, "present": False}], self.pid, "launch-1", S1)
        self.deliver()
        self.assertIn("the body", self.inbox(S1)[2], "its row gone (a rewind): the full body")
        self.assertEqual(self.receipt(e)["attempt"]["n"], 3)
        self.assertEqual(self.record().get(OTHER, {}).get("attempts", 0), 0, "no attempt counted for a hold")

    def test_a_release_from_another_process_or_after_admission_changes_nothing(self):
        e, rid = self.stopped()
        resumed = self.launch(S1)
        self.gate(resumed, launch="launch-1")   # the same launch id, another process
        item = {"id": rid, "attempt": 1, "present": True}
        self.assertEqual(hd.release([item], resumed, "launch-1", S1)["receipts"], {rid: "stale"})
        hd.admit([rid], resumed, S1)
        self.assertEqual(hd.release([item], resumed, "launch-1", S1)["receipts"], {rid: "admitted"})

    def test_a_resume_racing_its_own_activation_waits_for_it(self):
        """A young process of a session a gate process served: its first
        delivery waits, owed, rather than fix the process legacy before its
        bridge activates."""
        e, rid = self.stopped()
        resumed = self.launch(S1)
        for _ in range(3):
            got = self.deliver()
            self.assertEqual([o for _, o in got["outcomes"]], [sminos.HOLDER_AWAITING])
        self.assertIsNone(hd.read_mode(hd.process(resumed)), "nothing chosen for it yet")
        self.assertEqual(len(self.inbox(S1)), 1)
        self.assertEqual(self.record().get(OTHER, {}).get("attempts", 0), 0, "waiting counts no attempt")
        self.gate(resumed, launch="launch-2", retained=[rid])
        self.deliver()
        self.assertEqual(self.ids()[1], [rid])
        self.assertEqual(hd.read_mode(hd.process(resumed))["mode"], "gate")
        self.assertEqual(self.receipt(e)["attempt"]["pid"], resumed, "a receipt of its own")
        self.assertEqual(len(self.said("may yet activate receipts")), 1, "the grace's start, said once")
        self.assertEqual(self.said("did not activate receipts"), [], "it ended in `gate`")
        with mock.patch.object(hd, "ACTIVATION_GRACE_S", 0):
            again = self.launch(S1)
            self.deliver()
            self.assertEqual(hd.read_mode(hd.process(again))["mode"], "legacy", "past the grace: handed off")


# ------------------------------------------------------------- the other deliverers


class Deliverers(Rig):
    def test_a_lane_b_human_event_skips_the_refusing_bridge_for_its_inbox(self):
        pid = self.launch(S1, self.lp)
        self.gate(pid)
        e = sminos.log_append(self.lp, sminos.writer_id(), "human",
                              **{"from": "human", "to": [{"session": S1, "alias": "m"}], "text": "from the human"})
        got = self.deliver(project=self.lp)
        self.assertEqual([o for _, o in got["outcomes"]], [sminos.HOLDER_AWAITING])
        self.assertEqual(self.bridge, [], "the observer's bridge refuses deliver: not asked")
        self.assertEqual(self.ids(), [[self.receipt(e, project=self.lp)["id"]]])
        self.assertIn("from the human", self.inbox(S1)[0])

    def test_a_send_to_a_gate_process_shares_the_boundary(self):
        pid = self.launch(S1)
        self.gate(pid)
        m = member(S1)
        out = io.StringIO()
        with mock.patch.object(sminos, "members", return_value=[m]), contextlib.redirect_stdout(out):
            sminos.send_to_member(self.hp, m, "human", "", "via send", "abc12345")
        self.assertEqual(out.getvalue(), "sent to m (%s)\n" % sminos.HOLDER_AWAITING)
        events = [x for x in sminos.log_read(self.hp) if x.get("msg_id") == "abc12345"]
        self.assertEqual(len(events), 1)
        rid = self.receipt(events[0])["id"]
        self.assertEqual(self.ids(), [[rid]])
        self.assertIn("via send", self.inbox(S1)[0])
        self.assertEqual(self.settled(events[0]["writer"]), 0, "settled at its admission, not at the send")

    def test_a_receipt_for_another_body_at_the_position_is_none(self):
        """A git merge put another line at a position a receipt was made for:
        that receipt holds nothing for the new body, which goes afresh."""
        pid = self.launch(S1)
        self.gate(pid)
        e = self.arrive(OTHER, 1, text="first body")
        self.deliver()
        old = self.receipt(e)["id"]
        other = {**e, "text": "another body"}
        self.assertTrue(hd.exists(self.hp.id, S1, e))
        self.assertFalse(hd.exists(self.hp.id, S1, other))
        self.assertIsNone(hd.plan(self.hp.id, S1, other, sminos.event_hash(other), pid, existing_only=True))
        plan = hd.plan(self.hp.id, S1, other, sminos.event_hash(other), pid)
        self.assertEqual((plan.kind, plan.attempt, plan.body), ("push", 1, "full"))
        self.assertNotEqual(plan.receipt, old, "a new id: the old one settles nothing of it")

    def test_deliver_verdict_prepares_a_receipt_after_the_words_policy(self):
        identity = {"org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": {}, "ref": "r",
                    "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z", "build": "b"}
        sminos.write_json(rl10.identity_path(), identity)
        rl10.keep_revoked({"version": 1, "devices": [], "members": [], "keys": []}, True)
        sminos.forget_caches()
        pid = self.launch(S1)
        self.gate(pid)
        words = self.arrive("hub/mem-1", 1, kind="human", signer=DEV_A, text="words for you")
        refused = self.arrive("hub/mem-2", 1, kind="human", signer={**DEV_A, "member": "mem-2"})
        self.assertEqual(sorted(e["writer"] for e in sminos.words_due(self.hp, [member(S1)])[S1]),
                         ["hub/mem-1", "hub/mem-2"])
        self.assertEqual(sminos.deliver_verdict(self.hp, member(S1), words, "words"), sminos.HOLDER_AWAITING)
        self.assertEqual(self.bridge, [], "a gate process's words go to its inbox, marked")
        self.assertEqual(self.ids(), [[self.receipt(words)["id"]]])
        self.assertEqual(sminos.deliver_verdict(self.hp, member(S1), refused, "refuse"), outcomes.REFUSED_WORDS,
                         "the verdict's policy first: refused, nothing prepared")
        self.assertIsNone(self.receipt(refused))
        self.assertEqual([e["writer"] for e in sminos.words_due(self.hp, [member(S1)]).get(S1, [])], [],
                         "never asked again while its receipt is held")
        self.assertEqual(sminos.deliver_verdict(self.hp, member(S1), words, "words"), sminos.HOLDER_AWAITING,
                         "a repeated verdict pushes nothing more")
        self.assertEqual(len(self.inbox(S1)), 1)
        hd.admit([self.receipt(words)["id"]], pid, S1)
        self.deliver()
        self.assertEqual(self.settled("hub/mem-1"), 1, "the reconciler settles a words-gated writer's admission too")
        self.assertIn(("hub/mem-1", 1, "delivered"), self.outbox())

    def test_a_legacy_handoff_keeps_the_verdict_it_was_given(self):
        """A process with no record takes a words verdict as before: through
        its bridge (here none answers, so its inbox), settled at the handoff."""
        sminos.write_json(rl10.identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": {}, "ref": "r",
            "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z", "build": "b"})
        rl10.keep_revoked({"version": 1, "devices": [], "members": [], "keys": []}, True)
        sminos.forget_caches()
        self.launch(S1)
        words = self.arrive("hub/mem-1", 1, kind="human", signer=DEV_A)
        self.assertEqual(sminos.deliver_verdict(self.hp, member(S1), words, "words"), "sent")
        self.assertEqual([(a[0], a[2]["writer"]) for a in self.bridge], [(S1, "hub/mem-1")], "asked as words")
        self.assertEqual((self.settled("hub/mem-1"), self.ids()), (1, [[]]))

    def test_delivery_while_the_child_is_down_still_prepares_a_receipt(self):
        """No bridge child runs (nothing serves /status or /holder): the
        record alone decides."""
        pid = self.launch(S1)
        self.gate(pid)
        e = self.arrive(OTHER, 1)
        self.deliver()
        self.assertIsNotNone(self.receipt(e))
        self.assertEqual(self.ids(), [[self.receipt(e)["id"]]])


class Sweep(Rig):
    def test_the_records_of_processes_that_ended_are_swept(self):
        live = self.launch(S1)
        gone = self.launch(S2)
        hd.observer_upgrade(live)
        self.gate(gone, sid=S2)
        self.end(S2)
        self.assertEqual(hd.sweep(sminos.known_project), (1, 0))
        self.assertIsNotNone(hd.read_mode(hd.process(live)))
        self.assertEqual(sorted(os.listdir(os.path.join(hd.home(), hd.LAUNCHES))),
                         sorted(os.path.basename(hd._mode_path(hd.process(live), ext)) for ext in (".json", ".lock")))


# ------------------------------------------------------------- review fixes


class Policy(Rig):
    """A receipt proves it was prepared, not that anything was handed off:
    the revocation set and the read-only policy are read again before any
    push or retry of it; only its admission settles it unasked."""

    def setUp(self):
        super().setUp()
        self.cut_over()
        self.pid = self.launch(S1)
        self.gate(self.pid)

    def failed_first_push(self):
        e = self.arrive(OTHER, 1, signer=DEV_A, text="signed body")
        with mock.patch.object(sminos, "send_frame", side_effect=sminos.SendFailed("before", "refused")):
            got = self.deliver()
        self.assertTrue(got["outcomes"][0][1].startswith("failed:"))
        self.assertEqual(self.receipt(e)["attempt"]["state"], "prepared")
        return e

    def test_a_receipt_nothing_was_handed_off_under_is_refused_once_its_signer_is_revoked(self):
        e = self.failed_first_push()
        self.revoke(["dev-a"], version=2)
        got = self.deliver()
        self.assertEqual([o for _, o in got["outcomes"]], [outcomes.REFUSED_REVOKED])
        self.assertEqual(self.inbox(S1), [], "never pushed")
        self.assertIsNone(self.receipt(e), "its receipt goes with it")
        self.assertEqual(self.deliver()["outcomes"], [])

    def test_revoke_owed_marks_a_receipt_nothing_was_handed_off_under(self):
        e = self.failed_first_push()
        self.revoke(["dev-a"], version=2)
        self.assertEqual([x["seq"] for x in sminos.revoke_owed(self.hp, member(S1), rl10.revoked())], [1])
        self.assertIsNone(self.receipt(e))
        self.deliver()
        self.assertEqual(self.inbox(S1), [])

    def test_a_handed_off_receipt_is_left_to_its_admission(self):
        e = self.arrive(OTHER, 1, signer=DEV_A)
        self.deliver()
        rid = self.receipt(e)["id"]
        self.revoke(["dev-a"], version=2)
        self.assertEqual(sminos.revoke_owed(self.hp, member(S1), rl10.revoked()), [], "delivered before it")
        hd.admit([rid], self.pid, S1)
        self.assertEqual([o for _, o in self.deliver()["outcomes"]], ["sent"], "admission settles it, unasked")

    def test_a_handed_off_receipt_is_not_retried_once_its_signer_is_revoked(self):
        e = self.arrive(OTHER, 1, signer=DEV_A)
        self.deliver()
        self.revoke(["dev-a"], version=2)
        resumed = self.launch(S1)
        self.gate(resumed, launch="launch-2")
        got = self.deliver()
        self.assertEqual([o for _, o in got["outcomes"]], [outcomes.REFUSED_REVOKED])
        self.assertEqual(len(self.inbox(S1)), 1, "no retry into the new launch")
        self.assertIsNone(self.receipt(e))

    def test_deliver_verdict_rechecks_the_revocation_before_a_retry(self):
        words = self.arrive("hub/mem-1", 1, kind="human", signer=DEV_A, text="words for you")
        with mock.patch.object(sminos, "send_frame", side_effect=sminos.SendFailed("before", "refused")):
            self.assertTrue(sminos.deliver_verdict(self.hp, member(S1), words, "words").startswith("failed:"))
        self.revoke(["dev-a"], version=2)
        self.assertEqual(sminos.deliver_verdict(self.hp, member(S1), words, "words"), outcomes.REFUSED_REVOKED)
        self.assertEqual(self.inbox(S1), [])
        self.assertIsNone(self.receipt(words))


class Identity(Rig):
    """A process's mode identity is what every reader reads alike, whatever
    the wall clock did since: on Linux the boot and the start in ticks."""

    def proc(self, root, boot_id="0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", btime=1_700_000_000, ticks=123456):
        os.makedirs(os.path.join(root, "4242"), exist_ok=True)
        os.makedirs(os.path.join(root, "sys", "kernel", "random"), exist_ok=True)
        Path(root, "stat").write_text("cpu 1 2 3\nbtime %d\n" % btime)
        Path(root, "uptime").write_text("5000.00 9000.00\n")
        Path(root, "sys", "kernel", "random", "boot_id").write_text(boot_id + "\n")
        Path(root, "4242", "stat").write_text(
            "4242 (claude (x)) S " + " ".join(["0"] * 18) + " %d " % ticks + " ".join(["0"] * 5) + "\n")

    def read(self, root):
        sminos._BOOT.clear()
        with mock.patch.object(sminos, "PROC", root), mock.patch.object(hd, "sys", mock.Mock(platform="linux")), \
                mock.patch.object(hd, "_boot_now", return_value=5000.0):   # CLOCK_BOOTTIME is Linux's alone
            return hd.process(4242)

    def test_linux_identity_survives_a_wall_clock_step(self):
        root = os.path.join(self.home, "proc")
        self.proc(root)
        before = self.read(root)
        self.assertIsNotNone(before)
        self.proc(root, btime=1_700_000_000 + 3600)   # the clock stepped an hour
        self.assertEqual(self.read(root)["start"], before["start"])
        self.proc(root, boot_id="11111111-2222-3333-4444-555555555555")   # another boot, the same pid and ticks
        self.assertNotEqual(self.read(root)["start"], before["start"])
        self.proc(root, ticks=123457)
        self.assertNotEqual(self.read(root)["start"], before["start"])

    def test_no_boot_id_is_no_identity(self):
        root = os.path.join(self.home, "proc")
        self.proc(root)
        os.unlink(os.path.join(root, "sys", "kernel", "random", "boot_id"))
        self.assertIsNone(self.read(root), "fail closed, never a clock-derived identity")


class Release(Rig):
    def setUp(self):
        super().setUp()
        self.pid = self.launch(S1)
        self.gate(self.pid)
        self.e = self.arrive(OTHER, 1, text="the body")
        self.deliver()
        self.rid = self.receipt(self.e)["id"]

    def release(self, attempt, present=True):
        return hd.release([{"id": self.rid, "attempt": attempt, "present": present}], self.pid, "launch-1", S1)

    def test_a_replayed_release_of_an_earlier_attempt_releases_nothing(self):
        self.assertEqual(self.release(1)["receipts"], {self.rid: "released"})
        self.deliver()
        self.assertEqual(self.receipt(self.e)["attempt"]["n"], 2)
        self.assertEqual(self.release(1)["receipts"], {self.rid: "stale"}, "attempt 1 was released already")
        self.deliver()
        self.assertEqual(len(self.inbox(S1)), 2, "no third push")
        self.assertEqual(self.receipt(self.e)["attempt"]["n"], 2)

    def test_a_replayed_release_of_the_current_attempt_allows_one_retry(self):
        self.assertEqual(self.release(1)["receipts"], {self.rid: "released"})
        self.assertEqual(self.release(1)["receipts"], {self.rid: "released"}, "idempotent")
        self.deliver()
        self.deliver()
        self.assertEqual(len(self.inbox(S1)), 2)

    def test_a_release_naming_no_attempt_releases_nothing(self):
        got = hd.release([{"id": self.rid, "present": True}], self.pid, "launch-1", S1)
        self.assertEqual(got["receipts"], {self.rid: "stale"})
        self.deliver()
        self.assertEqual(len(self.inbox(S1)), 1)


class Storage(Rig):
    """A report the child could not record durably is a retryable failure,
    never an acknowledged `unknown`."""

    def setUp(self):
        super().setUp()
        self.pid = self.launch(S1)
        self.gate(self.pid)
        self.e = self.arrive(OTHER, 1)
        self.deliver()
        self.rid = self.receipt(self.e)["id"]
        self.path = hd._receipt_path(self.rid.split(".")[0])

    def test_an_unreadable_receipt_fails_an_admission_retryably(self):
        kept = Path(self.path).read_text()
        Path(self.path).write_text("{")
        got = hd.admit([self.rid], self.pid, S1)
        self.assertEqual((got["ok"], got["code"]), (False, "storage"))
        Path(self.path).write_text(kept)
        self.assertEqual(hd.admit([self.rid], self.pid, S1), {"ok": True, "receipts": {self.rid: "admitted"}},
                         "the replay records it")

    def test_a_write_that_fails_fails_the_report(self):
        with mock.patch.object(hd, "_write", side_effect=OSError(28, "No space left on device")):
            got = hd.admit([self.rid], self.pid, S1)
        self.assertEqual((got["ok"], got["code"]), (False, "storage"))
        self.assertIsNone(self.receipt(self.e)["admitted"])
        with mock.patch.object(hd, "_write", side_effect=OSError(28, "No space left on device")):
            got = hd.release([{"id": self.rid, "attempt": 1, "present": True}], self.pid, "launch-1", S1)
        self.assertEqual((got["ok"], got["code"]), (False, "storage"))

    def test_an_unreadable_receipt_fails_a_release_retryably(self):
        Path(self.path).write_text("{")
        got = hd.release([{"id": self.rid, "attempt": 1, "present": True}], self.pid, "launch-1", S1)
        self.assertEqual((got["ok"], got["code"]), (False, "storage"))

    def test_an_invalid_token_is_still_unknown(self):
        forged = self.rid.split(".")[0] + ".0123456789abcdef"
        self.assertEqual(hd.admit([forged], self.pid, S1), {"ok": True, "receipts": {forged: "unknown"}})


class Grace(Rig):
    def test_the_grace_is_bounded_at_30_seconds_and_0_is_the_literal_rule(self):
        for value, grace in (("999", 30.0), ("0", 0.0), ("12", 12.0), ("", 30.0)):
            with mock.patch.dict(os.environ, {"SMINOS_HOLDER_ACTIVATION_GRACE": value}):
                self.assertEqual(hd._grace(), grace, value)

    def test_no_activation_within_the_grace_is_legacy_after_it_and_one_handoff(self):
        pid = self.launch(S1)
        self.gate(pid)
        e = self.arrive(OTHER, 1)
        self.deliver()
        hd.admit([self.receipt(e)["id"]], pid, S1)
        self.deliver()
        resumed = self.launch(S1)
        self.arrive(OTHER, 2)
        for _ in range(sminos.DELIVERY_ATTEMPTS + 2):
            self.assertEqual([o for _, o in self.deliver()["outcomes"]], [sminos.HOLDER_AWAITING])
        self.assertEqual(len(self.inbox(S1)), 1, "nothing handed off while it may activate")
        self.assertEqual(self.record().get(OTHER, {}).get("attempts", 0), 0)
        real = hd.process

        def older(p):
            got = real(p)
            return dict(got, age=got["age"] + hd.ACTIVATION_GRACE_S + 1) if got else got
        with mock.patch.object(hd, "process", side_effect=older):
            self.assertEqual([o for _, o in self.deliver()["outcomes"]], ["sent"])
            self.assertEqual(self.deliver()["outcomes"], [])
        self.assertEqual(hd.read_mode(hd.process(resumed))["mode"], "legacy")
        self.assertEqual(len(self.inbox(S1)), 2, "exactly one handoff")
        self.assertEqual(len(self.said("may yet activate receipts")), 1)
        self.assertEqual(len(self.said("did not activate receipts")), 1)


class SweepIdentity(Rig):
    def test_a_live_process_whose_start_cannot_be_read_keeps_its_mode(self):
        live = self.launch(S1)
        self.gate(live)
        path = hd._mode_path(hd.process(live))
        with mock.patch.object(hd, "process", return_value=None):
            self.assertEqual(hd.sweep(sminos.known_project), (0, 0))
        self.assertTrue(os.path.exists(path), "not proof it ended")
        self.assertEqual(hd.read_mode(hd.process(live))["mode"], "gate")

    def test_a_record_of_another_process_under_a_reused_pid_is_swept(self):
        live = self.launch(S1)
        stale = os.path.join(hd.home(), hd.LAUNCHES, "%d-%s.json" % (live, "0"))
        Path(stale).write_text("{}")
        self.assertEqual(hd.sweep(sminos.known_project), (1, 0))
        self.assertFalse(os.path.exists(stale))


# ------------------------------------------------------------- review fixes, round 2


class ClockSteps(Rig):
    """C5's bound is on the boot clock: no wall-clock step lengthens (or
    shortens) a process's grace."""

    def setUp(self):
        super().setUp()
        pid = self.launch(S1)
        self.gate(pid)
        e = self.arrive(OTHER, 1)
        self.deliver()
        hd.admit([self.receipt(e)["id"]], pid, S1)
        self.deliver()
        self.resumed = self.launch(S1)

    def test_a_backward_step_does_not_extend_the_grace(self):
        wall, boot = time.time(), hd._boot_now()
        with mock.patch.object(hd.time, "time", return_value=wall - 3600), \
                mock.patch.object(hd, "_boot_now", return_value=boot + hd.ACTIVATION_GRACE_S + 1):
            self.assertEqual(hd.handoff(self.resumed, S1), "legacy", "31 s of its life went by: the grace is over")

    def test_a_forward_step_does_not_cut_the_grace_short(self):
        with mock.patch.object(hd.time, "time", return_value=time.time() + 3600):
            self.assertEqual(hd.handoff(self.resumed, S1), "wait")


class Exits(Rig):
    def test_a_recipient_that_exits_before_its_retry_leaves_it_owed(self):
        pid = self.launch(S1)
        self.gate(pid)
        e = self.arrive(OTHER, 1)
        with mock.patch.object(sminos, "send_frame", side_effect=sminos.SendFailed("before", "refused")):
            self.deliver()
        real, calls = sminos.peer_for_session, []

        def peer(sid):   # live for the dry plan, gone by the retry
            calls.append(sid)
            return real(sid) if len(calls) == 1 else None
        with mock.patch.object(sminos, "peer_for_session", side_effect=peer):
            got = self.deliver()
        self.assertEqual([o for _, o in got["outcomes"]], [sminos.HOLDER_AWAITING])
        self.assertIsNotNone(self.receipt(e))
        self.assertEqual(self.inbox(S1), [])


class UnreadableHandoff(Rig):
    def test_revocation_defers_an_event_whose_receipt_cannot_be_read(self):
        self.cut_over()
        pid = self.launch(S1)
        self.gate(pid)
        e = self.arrive(OTHER, 1, signer=DEV_A)
        self.deliver()
        hd.admit([self.receipt(e)["id"]], pid, S1)
        path = hd._receipt_path(hd.key_hash(self.hp.id, S1, OTHER, 1))
        kept = Path(path).read_text()
        Path(path).write_text("{")
        self.revoke(["dev-a"], version=2)
        self.assertEqual(sminos.revoke_owed(self.hp, member(S1), rl10.revoked()), [], "not known unhanded: deferred")
        self.assertEqual(Path(path).read_text(), "{", "its receipt kept")
        self.assertTrue(self.deliver()["outcomes"][0][1].startswith("held:"))
        Path(path).write_text(kept)
        self.assertEqual([o for _, o in self.deliver()["outcomes"]], ["sent"], "its admission settles it")


if __name__ == "__main__":
    unittest.main(verbosity=1)
