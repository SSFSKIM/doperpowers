#!/usr/bin/env python3
"""The bridge child's part in a gate process's receipts (O12 M4b, the
child's side): the private route's receipt activation before the OX10
hello, the M4a observer's upgrade to `legacy` settlement while it keeps
observing, and the mod's admission and release reports, recorded durably
before they are acknowledged (sminos_holder.py's docstring is the route's
contract, sminos_holder_deliveries.py's the receipts').

Each case runs a real `sminos bridge` child against test_holder.py's fake
engine host and plays the mod (its ready, acks and reports). Receipts are
written here as the deliverers write them (sminos_holder_deliveries'
layout), for the test process, which is the child's parent: claude's pid.
The deliverers' side is test_holder_deliveries.py's; the mod's, the mod
tests' (bridge-receipts.test.ts).

Hermetic: every case has its own HOME, SMINOS_HOME and CLAUDE_CONFIG_DIR.
Run: python3 -B sminos/tests/test_holder_receipts.py
"""

import json
import os
import threading
import time
import unittest

import test_holder  # sets the hermetic environment first
from test_holder import QUIET, SESSION, Case, wait_for

import sminos  # noqa: E402
import sminos_bridge  # noqa: E402
import sminos_holder_deliveries as hd  # noqa: E402

LAUNCH = "LaunchLaunchLaunchLaun1"
OTHER_SESSION = "7a000001-0000-4000-8000-0000000000a7"
TOKEN = "0123456789abcdef"


class Receipts(Case):
    """A child whose receipts live under the case's SMINOS_HOME, which this
    process reads too while the case runs."""

    def setUp(self):
        super().setUp()
        self.saved_home = os.environ.get("SMINOS_HOME")
        os.environ["SMINOS_HOME"] = os.path.join(self.home, "s")
        self.proc = hd.process(os.getpid())
        self.assertIsNotNone(self.proc, "the test process's identity is readable")

    def tearDown(self):
        os.environ["SMINOS_HOME"] = self.saved_home
        super().tearDown()

    # -- the mod's side of the route

    def ready(self, child, **activation):
        return child.post({"kind": "ready", "generation": child.bootstrap()["generation"], **activation})

    def report(self, child, kind, **body):
        return child.post({"kind": kind, "generation": child.bootstrap()["generation"], **body})

    # -- the deliverers' side, as they leave it

    def mode(self):
        return hd.read_mode(self.proc)

    def receipt(self, seq=1, session=SESSION, attempt=1, launch=LAUNCH):
        """A receipt a deliverer prepared and pushed to this process (attempt 1, the full body)."""
        keyhash = hd.key_hash("proj", session, "othermachine/peer", seq)
        rid = "%s.%s" % (keyhash, TOKEN)
        r = {"v": 1, "id": rid, "key": {"project": "proj", "session": session, "writer": "othermachine/peer", "seq": seq},
             "hash": "h%d" % seq, "words": False, "created": sminos.now(ms=True),
             "attempt": {"n": attempt, "pid": self.proc["pid"], "start": self.proc["start"], "launch": launch,
                         "body": "full", "state": "pushed", "at": sminos.now(ms=True)},
             "handed": True, "released": None, "admitted": None}
        hd._write(self.path(rid), r)
        return rid

    def path(self, rid):
        return os.path.join(hd.home(), rid.split(".")[0] + ".json")

    def stored(self, rid):
        with open(self.path(rid)) as f:
            return json.load(f)

    def gated(self, child):
        """The child ready with this process's launch, welcomed on its first connection."""
        self.ready(child, launch=LAUNCH)
        return self.welcomed(child)


class Activation(Receipts):
    def test_gate_is_persisted_before_the_hello_with_the_mods_launch(self):
        child = self.child()
        child.bootstrap()
        time.sleep(QUIET)
        self.assertIsNone(self.mode(), "nothing is chosen before the mod asks")
        retained = ["%s.%s" % ("a" * 24, TOKEN)]
        # A deliverer holds the process's mode lock: no hello while the
        # activation waits for it, and the record is there once one comes.
        with sminos.flocked(hd._mode_path(self.proc, ".lock")):
            status, answer = self.ready(child, launch=LAUNCH, retained=retained)
            self.assertEqual((status, answer["ok"]), (200, True), "ready is answered at once")
            time.sleep(QUIET)
            self.assertEqual(self.host.conns, [], "no hello before the mode is persisted")
        conn = self.host.conn(0)
        self.assertEqual(conn.wait_frames(1)[0]["t"], "hello")
        rec = self.mode()
        self.assertEqual((rec["mode"], rec["launch"], rec["by"], rec["session"], rec["retained"]),
                         ("gate", LAUNCH, "activation", SESSION, retained))
        _, st = sminos_bridge.request(os.path.join(self.home, "s", "bridge", SESSION + ".sock"), "GET", "/status")
        self.assertEqual(st["holder"]["receipts"], "gate")

    def test_a_record_already_chosen_is_kept_and_the_observer_connects_anyway(self):
        # A legacy handoff won the process's mode lock first: activation never
        # turns it, and the observer still says hello.
        rec = hd._choose(self.proc, "legacy", "handoff", session=SESSION)
        child = self.child()
        self.ready(child, launch=LAUNCH)
        self.assertEqual(self.host.conn(0).wait_frames(1)[0]["t"], "hello")
        self.assertEqual(self.mode(), rec)
        _, st = sminos_bridge.request(os.path.join(self.home, "s", "bridge", SESSION + ".sock"), "GET", "/status")
        self.assertEqual(st["holder"]["receipts"], "legacy")

    def test_a_child_restart_or_a_clear_never_changes_the_mode(self):
        first = self.child()
        self.ready(first, launch=LAUNCH)
        self.host.conn(0).wait_frames(1)
        chosen = self.mode()
        first.stop()
        second = self.child(args=("--lane", "match", "--launch=%s" % LAUNCH))
        self.ready(second, launch=LAUNCH, upgrade=True, retained=[])
        self.host.conn(1).wait_frames(1)
        self.assertEqual(self.mode(), chosen, "an existing record, gate here, is returned as it is")

    def test_an_unreadable_mode_fails_closed_and_the_observer_still_observes(self):
        with open(hd._mode_path(self.proc), "w") as f:
            f.write("{not json")
        child = self.child()
        self.ready(child, launch=LAUNCH)
        conn = self.host.conn(0)
        self.assertEqual(conn.wait_frames(1)[0]["t"], "hello")
        conn.send({"t": "welcome", "protocol": 1})
        self.assertTrue(wait_for(lambda: conn.seen("hb")), "heartbeats")
        _, st = sminos_bridge.request(os.path.join(self.home, "s", "bridge", SESSION + ".sock"), "GET", "/status")
        self.assertEqual(st["holder"]["receipts"], "unknown")
        with open(hd._mode_path(self.proc)) as f:
            self.assertEqual(f.read(), "{not json", "nothing overwrote it")

    def test_the_bootstrap_says_how_long_claudes_process_has_run(self):
        # The mod's evidence of a fresh process (one whose first module this
        # is): the process's age on the boot clock, as the deliverers read it.
        boot = self.child().bootstrap()
        self.assertIsInstance(boot["processAge"], (int, float))
        self.assertLessEqual(abs(boot["processAge"] - hd.process(os.getpid())["age"]), 5.0)

    def test_reports_wait_for_the_activation_and_are_never_answered_legacy_before_it(self):
        # The activation waits on a deliverer's mode lock: a report meanwhile
        # is answered `pending` (retryable), not `legacy`, and records nothing;
        # once the activation chose `gate`, the replay is recorded.
        child = self.child()
        rid = self.receipt()
        with sminos.flocked(hd._mode_path(self.proc, ".lock")):
            self.ready(child, launch=LAUNCH)
            status, answer = self.report(child, "admit", session=SESSION, ids=[rid])
            self.assertEqual((status, answer["ok"], answer["code"]), (200, False, "pending"))
            status, answer = self.report(child, "release", session=SESSION,
                                         items=[{"id": rid, "attempt": 1, "present": True}])
            self.assertEqual((status, answer["ok"], answer["code"]), (200, False, "pending"))
            self.assertIsNone(self.stored(rid)["admitted"])
        self.assertTrue(wait_for(lambda: self.mode() is not None))
        self.assertEqual(self.report(child, "admit", session=SESSION, ids=[rid])[1],
                         {"ok": True, "receipts": {rid: "admitted"}})

    def test_a_ready_with_a_malformed_activation_is_refused(self):
        child = self.child()
        for bad in ({"launch": 7}, {"upgrade": "yes"}, {"retained": "x"}, {"retained": [1]}, {"observe": "no"}):
            status, answer = self.ready(child, **bad)
            self.assertEqual((status, answer["code"]), (400, "shape"), bad)
        time.sleep(QUIET)
        self.assertEqual(self.host.conns, [], "no ready was taken")


class Upgrade(Receipts):
    def test_an_m4a_observers_process_records_legacy_and_keeps_observing(self):
        # M4b loaded into a process an M4a observer ran in (its module kept
        # observerStarted): legacy settlement, recorded before the hello; the
        # observer says hello, beats, relays arms and acknowledges them.
        child = self.child()
        self.ready(child, launch=LAUNCH, upgrade=True)
        conn = self.host.conn(0)
        hello = conn.wait_frames(1)[0]
        self.assertEqual((hello["t"], hello["childPid"]), ("hello", child.proc.pid))
        rec = self.mode()
        self.assertEqual((rec["mode"], rec["by"], rec["launch"]), ("legacy", "observer", None))
        conn.send({"t": "welcome", "protocol": 1})
        epoch = child.welcome_epoch()
        conn.send({"t": "arm", "fence": 3, "leaseMs": 400})
        child.wait_line(lambda ln: ln.get("epoch") == epoch and ln.get("arm") == 1)
        self.assertEqual(child.ack(epoch, 1, 3)[1]["sent"], 1)
        self.assertTrue(wait_for(lambda: conn.seen("armed") == [{"t": "armed", "fence": 3}]))
        self.assertTrue(wait_for(lambda: len(conn.seen("hb")) >= 3), "heartbeats go on")
        self.assertFalse(conn.closed, "the seen observer is not disconnected")
        # Its reports are refused whole, never recorded: nothing it handed off is a receipt.
        rid = self.receipt()
        status, answer = self.report(child, "admit", session=SESSION, ids=[rid])
        self.assertEqual((status, answer["ok"], answer["code"]), (200, False, "legacy"))
        self.assertIsNone(self.stored(rid)["admitted"])


    def test_an_existing_process_never_observed_records_legacy_and_says_no_hello(self):
        # M4b loaded into a process whose bridge never started an observer
        # (a pre-M4a module ran in it): legacy settlement, and it stays
        # unobserved: no hello, ever, from this child.
        child = self.child()
        status, answer = self.ready(child, upgrade=True, observe=False)
        self.assertEqual((status, answer["ok"]), (200, True))
        self.assertTrue(wait_for(lambda: self.mode() is not None))
        rec = self.mode()
        self.assertEqual((rec["mode"], rec["launch"]), ("legacy", None))
        time.sleep(QUIET)
        self.assertEqual(self.host.conns, [], "no hello")
        rid = self.receipt()
        self.assertEqual(self.report(child, "admit", session=SESSION, ids=[rid])[1]["code"], "legacy")


class Admission(Receipts):
    def test_an_admission_is_durable_before_its_answer_and_idempotent(self):
        child = self.child()
        self.gated(child)
        a, b = self.receipt(1), self.receipt(2)
        status, answer = self.report(child, "admit", session=SESSION, ids=[a, b])
        self.assertEqual((status, answer), (200, {"ok": True, "receipts": {a: "admitted", b: "admitted"}}))
        for rid in (a, b):
            admitted = self.stored(rid)["admitted"]
            self.assertEqual((admitted["pid"], admitted["start"], admitted["launch"]),
                             (self.proc["pid"], self.proc["start"], LAUNCH))
        status, again = self.report(child, "admit", session=SESSION, ids=[a, b])
        self.assertEqual(again, answer, "replayed, it answers the same")

    def test_another_sessions_receipt_and_a_forged_id_settle_nothing(self):
        # An old report after a /clear names the session it was admitted in:
        # a receipt of another recipient is foreign; text alone is unknown.
        child = self.child()
        self.gated(child)
        mine, theirs = self.receipt(1), self.receipt(2, session=OTHER_SESSION)
        forged = mine.split(".")[0] + ".ffffffffffffffff"
        status, answer = self.report(child, "admit", session=SESSION, ids=[theirs, forged, "nonsense"])
        self.assertEqual(answer, {"ok": True, "receipts": {theirs: "foreign", forged: "unknown", "nonsense": "unknown"}})
        self.assertIsNone(self.stored(theirs)["admitted"])
        self.assertIsNone(self.stored(mine)["admitted"])
        # The same report naming the session that receipt was delivered to settles it.
        status, answer = self.report(child, "admit", session=OTHER_SESSION, ids=[theirs])
        self.assertEqual(answer, {"ok": True, "receipts": {theirs: "admitted"}})

    def test_a_storage_failure_is_answered_retryably_and_a_replay_records_it(self):
        child = self.child()
        self.gated(child)
        good, bad = self.receipt(1), self.receipt(2)
        with open(self.path(bad)) as f:
            kept = f.read()
        with open(self.path(bad), "w") as f:
            f.write("{torn")
        status, answer = self.report(child, "admit", session=SESSION, ids=[good, bad])
        self.assertEqual((status, answer["ok"], answer["code"], answer["receipts"]),
                         (200, False, "storage", {good: "admitted", bad: "unavailable"}))
        with open(self.path(bad), "w") as f:
            f.write(kept)
        status, answer = self.report(child, "admit", session=SESSION, ids=[good, bad])
        self.assertEqual(answer, {"ok": True, "receipts": {good: "admitted", bad: "admitted"}})

    def test_a_report_to_a_restarted_child_is_recorded(self):
        # The mod replays what the child before did not acknowledge: the
        # next child records it for the same process.
        first = self.child()
        self.gated(first)
        rid = self.receipt()
        first.stop()
        second = self.child(args=("--lane", "match", "--launch=%s" % LAUNCH))
        self.ready(second, launch=LAUNCH)
        status, answer = self.report(second, "admit", session=SESSION, ids=[rid])
        self.assertEqual(answer, {"ok": True, "receipts": {rid: "admitted"}})

    def test_reports_need_no_gate_connection(self):
        # The gate has no connection at all (the host never welcomes): the
        # route still records reports.
        self.host.stop()
        child = self.child()
        self.ready(child, launch=LAUNCH)
        self.assertTrue(wait_for(lambda: self.mode() is not None), "activated before the first attempt")
        rid = self.receipt()
        self.assertEqual(self.report(child, "admit", session=SESSION, ids=[rid])[1],
                         {"ok": True, "receipts": {rid: "admitted"}})

    def test_malformed_reports_are_refused(self):
        child = self.child()
        self.gated(child)
        for body in ({"ids": "x"}, {"ids": []}, {"ids": [1]}, {"ids": ["a" * 65]}, {"ids": ["x"], "session": 5},
                     {"ids": ["x"] * 513}):
            status, answer = self.report(child, "admit", **body)
            self.assertEqual((status, answer["code"]), (400, "shape"), body)
        for items in ("x", [], [{"id": "x"}], [{"id": "x", "attempt": 0, "present": True}],
                      [{"id": "x", "attempt": 1, "present": "yes"}]):
            status, answer = self.report(child, "release", session=SESSION, items=items)
            self.assertEqual((status, answer["code"]), (400, "shape"), items)

    def test_an_admission_waiting_on_the_receipts_lock_holds_no_heartbeat(self):
        # A deliverer holds the receipts lock: the report waits for it, and
        # the gate's heartbeats keep their cadence meanwhile.
        child = self.child()
        conn, _ = self.gated(child)
        rid = self.receipt()
        answered = {}
        with sminos.flocked(os.path.join(hd.home(), "receipts.lock")):
            t = threading.Thread(target=lambda: answered.update(r=self.report(child, "admit", session=SESSION,
                                                                                ids=[rid])), daemon=True)
            t.start()
            start = time.monotonic()
            time.sleep(1.5)
            beats = [at for at in conn.times("hb") if at >= start]
            self.assertGreaterEqual(len(beats), 4, beats)
            self.assertEqual(answered, {}, "the report waits for the lock")
        t.join(10)
        self.assertEqual(answered["r"][1], {"ok": True, "receipts": {rid: "admitted"}})


class Release(Receipts):
    def test_a_release_names_its_attempt_and_the_launch_is_the_processes(self):
        child = self.child()
        self.gated(child)
        rid = self.receipt()
        status, answer = self.report(child, "release", session=SESSION,
                                     items=[{"id": rid, "attempt": 1, "present": True}])
        self.assertEqual(answer, {"ok": True, "receipts": {rid: "released"}})
        self.assertEqual((self.stored(rid)["released"]["attempt"], self.stored(rid)["released"]["present"]), (1, True))
        status, answer = self.report(child, "release", session=SESSION,
                                     items=[{"id": rid, "attempt": 2, "present": False}])
        self.assertEqual(answer, {"ok": True, "receipts": {rid: "stale"}})

    def test_a_release_in_another_launch_is_refused(self):
        child = self.child()
        self.gated(child)
        rid = self.receipt(launch="AnotherLaunchAnotherLa")
        status, answer = self.report(child, "release", session=SESSION,
                                     items=[{"id": rid, "attempt": 1, "present": True}])
        self.assertEqual(answer, {"ok": True, "receipts": {rid: "stale"}})
        self.assertIsNone(self.stored(rid)["released"])


def tearDownModule():
    test_holder.tearDownModule()


if __name__ == "__main__":
    unittest.main()
